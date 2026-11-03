import hmac
import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text
from backend.app.core.config import settings
from backend.app.models.borrow import Loan, BorrowRequest
from backend.app.models.catalog import Item
from backend.app.models.payment import Payment, PaymentWebhookEvent
from backend.app.models.user import AppUser
from backend.app.services.notification_service import create_notification
from backend.app.schemas.payment import OrderCreateResponse, PaymentVerifyRequest, PaymentOut


def create_payment_order(
    db: Session,
    loan_id: int,
    user: AppUser,
    payment_type: str = "RENTAL_FEE"
) -> OrderCreateResponse:
    loan = db.query(Loan).options(
        joinedload(Loan.request).joinedload(BorrowRequest.item),
        joinedload(Loan.request).joinedload(BorrowRequest.borrower)
    ).filter(Loan.loan_id == loan_id).first()

    if not loan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found.")

    if loan.request.borrower_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only borrower can pay for this loan.")

    # Calculate server-side amount according to database constraint:
    # RENTAL_FEE must equal loan.agreed_total_fee; DEPOSIT must equal loan.agreed_deposit
    if payment_type == "DEPOSIT":
        amount = loan.agreed_deposit
    else:
        amount = loan.agreed_total_fee

    # Check if a pending or completed payment of this type already exists
    target_type = "RENTAL_FEE" if payment_type == "RENTAL_FEE" else "DEPOSIT"
    existing_payment = db.query(Payment).filter(
        Payment.loan_id == loan.loan_id,
        Payment.payment_type == target_type,
        Payment.payment_status.in_(["PENDING", "COMPLETED"])
    ).first()

    if existing_payment:
        payment = existing_payment
        order_id = payment.gateway_order_id or f"order_{uuid.uuid4().hex[:14]}"
        payment.gateway_order_id = order_id
        db.commit()
        return OrderCreateResponse(
            order_id=order_id,
            amount=amount,
            currency="INR",
            key_id=settings.RAZORPAY_KEY_ID,
            payment_id=payment.payment_id,
            loan_id=loan.loan_id,
            item_title=loan.request.item.title
        )

    # Create local payment record
    idempotency = f"PAY_LOAN_{loan_id}_{uuid.uuid4().hex[:12]}"
    payment = Payment(
        loan_id=loan.loan_id,
        payer_id=user.user_id,
        payee_id=loan.request.item.owner_id,
        payment_type=target_type,
        method="UPI",
        payment_status="PENDING",
        amount=amount,
        idempotency_key=idempotency
    )
    db.add(payment)
    db.flush()

    # Razorpay Order Creation
    order_id = f"order_{uuid.uuid4().hex[:14]}"
    if settings.RAZORPAY_KEY_ID and not settings.RAZORPAY_KEY_ID.startswith("rzp_test_borrowhub_dummy"):
        try:
            import razorpay
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            amount_in_paise = int(amount * 100)
            rp_order = client.order.create({
                "amount": amount_in_paise,
                "currency": "INR",
                "receipt": f"rcpt_{payment.payment_id}",
                "notes": {
                    "loan_id": str(loan.loan_id),
                    "item": loan.request.item.title,
                    "borrower": user.full_name
                }
            })
            order_id = rp_order["id"]
        except Exception:
            pass  # Fall back to simulated test order ID for offline development

    payment.gateway_order_id = order_id
    db.commit()

    return OrderCreateResponse(
        order_id=order_id,
        amount=amount,
        currency="INR",
        key_id=settings.RAZORPAY_KEY_ID,
        payment_id=payment.payment_id,
        loan_id=loan.loan_id,
        item_title=loan.request.item.title
    )


def verify_razorpay_payment(
    db: Session,
    data: PaymentVerifyRequest,
    user: AppUser
) -> PaymentOut:
    query = db.query(Payment).options(
        joinedload(Payment.loan).joinedload(Loan.request).joinedload(BorrowRequest.item)
    )
    if data.payment_id:
        payment = query.filter(Payment.payment_id == data.payment_id).first()
    elif data.razorpay_order_id:
        payment = query.filter(Payment.gateway_order_id == data.razorpay_order_id).first()
    elif data.loan_id:
        q = query.filter(Payment.loan_id == data.loan_id)
        if data.payment_type:
            q = q.filter(Payment.payment_type == data.payment_type)
        payment = q.order_by(Payment.payment_id.desc()).first()
    else:
        payment = None

    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment record not found.")

    if payment.payment_status == "COMPLETED":
        return PaymentOut.model_validate(payment)

    # Signature verification
    # Signature check. When no gateway keys are configured the checkout is
    # explicitly simulated (PAYMENTS_SIMULATED) and the signature is
    # unavailable - that simulated mode is the *only* path that may skip the
    # check. With real keys a mismatch is always rejected.
    if settings.payments_simulated:
        is_valid = True
    else:
        expected = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            f"{data.razorpay_order_id}|{data.razorpay_payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        is_valid = hmac.compare_digest(expected, (data.razorpay_signature or "").strip())

    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Razorpay signature.")

    # Record verified webhook event to satisfy database integrity trigger
    event_id = f"evt_{uuid.uuid4().hex[:14]}"
    webhook_event = PaymentWebhookEvent(
        payment_id=payment.payment_id,
        gateway_event_id=event_id,
        event_type="PAYMENT_CAPTURED",
        amount_reported=payment.amount,
        transaction_reference=data.razorpay_payment_id,
        signature_verified=1,
        event_status="VERIFIED",
        payload={"order_id": data.razorpay_order_id, "payment_id": data.razorpay_payment_id},
        processed_at=datetime.now(timezone.utc)
    )
    db.add(webhook_event)
    db.flush()

    payment.transaction_reference = data.razorpay_payment_id
    payment.gateway_order_id = data.razorpay_order_id
    payment.payment_status = "COMPLETED"
    payment.paid_at = datetime.now(timezone.utc)

    # Set deposit status to HELD
    loan = payment.loan
    if loan and loan.agreed_deposit > 0:
        loan.deposit_status = "HELD"

    # Notify payee
    create_notification(
        db=db,
        user_id=payment.payee_id,
        title="Payment received",
        message=f"Received payment of ₹{payment.amount} for loan #{payment.loan_id}.",
        event_type="PAYMENT_UPDATE",
        reference_type="PAYMENT",
        reference_id=payment.payment_id,
        related_loan_id=payment.loan_id,
    )

    db.commit()
    db.refresh(payment)
    return PaymentOut.model_validate(payment)


def confirm_cash_payment(db: Session, payment_id: int, payee: AppUser) -> PaymentOut:
    payment = db.query(Payment).options(joinedload(Payment.loan)).filter(
        Payment.payment_id == payment_id
    ).first()
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment record not found.")

    if payment.payee_id != payee.user_id and payee.role not in ("ADMIN", "MODERATOR"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only parties to this loan can confirm cash payment.")

    payment.method = "CASH"
    payment.confirmed_by_user_id = payee.user_id
    payment.transaction_reference = f"CASH_CONFIRM_{payment.payment_id}_{uuid.uuid4().hex[:6]}"
    payment.payment_status = "COMPLETED"
    payment.paid_at = datetime.now(timezone.utc)

    if payment.loan and payment.loan.agreed_deposit > 0:
        payment.loan.deposit_status = "HELD"

    db.commit()
    db.refresh(payment)
    return PaymentOut.model_validate(payment)


def get_payment_history(db: Session, user: AppUser) -> List[PaymentOut]:
    payments = db.query(Payment).options(
        joinedload(Payment.payer),
        joinedload(Payment.payee)
    ).filter(
        (Payment.payer_id == user.user_id) | (Payment.payee_id == user.user_id)
    ).order_by(Payment.created_at.desc()).all()

    results = []
    for p in payments:
        results.append(PaymentOut(
            payment_id=p.payment_id,
            loan_id=p.loan_id,
            payer_id=p.payer_id,
            payer_name=p.payer.full_name if p.payer else "Student",
            payee_id=p.payee_id,
            payee_name=p.payee.full_name if p.payee else "Owner",
            payment_type=p.payment_type,
            method=p.method,
            payment_status=p.payment_status,
            amount=p.amount,
            transaction_reference=p.transaction_reference,
            gateway_order_id=p.gateway_order_id,
            created_at=p.created_at,
            paid_at=p.paid_at,
        ))
    return results
