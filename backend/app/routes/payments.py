import json
import hmac
import hashlib
from typing import List
from fastapi import APIRouter, Depends, Request, Header, HTTPException, status
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.dependencies.auth import get_current_user
from backend.app.models.user import AppUser
from backend.app.models.payment import Payment, PaymentWebhookEvent
from backend.app.schemas.payment import (
    OrderCreateRequest, OrderCreateResponse, PaymentVerifyRequest,
    CashPaymentConfirmRequest, PaymentOut
)
from backend.app.services.payment_service import (
    create_payment_order, verify_razorpay_payment,
    confirm_cash_payment, get_payment_history
)

router = APIRouter(prefix="/payments", tags=["Payment Gateway"])

# Razorpay event -> internal webhook_event_status
_EVENT_MAP = {
    "payment.captured": "PAYMENT_CAPTURED",
    "payment.failed": "PAYMENT_FAILED",
    "refund.processed": "REFUND_PROCESSED",
}


@router.post("/create-order", response_model=OrderCreateResponse)
def create_order(
    data: OrderCreateRequest,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return create_payment_order(db, data.loan_id, current_user, data.payment_type)


@router.post("/verify", response_model=PaymentOut)
def verify_payment(
    data: PaymentVerifyRequest,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return verify_razorpay_payment(db, data, current_user)


@router.post("/cash-confirm", response_model=PaymentOut)
def confirm_cash(
    data: CashPaymentConfirmRequest,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return confirm_cash_payment(db, data.payment_id, current_user)


@router.get("/history", response_model=List[PaymentOut])
def payment_history(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_payment_history(db, current_user)


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(None),
    db: Session = Depends(get_db)
):
    """Gateway callback: verifies the signature and applies the event.

    The event is recorded in payment_webhook_event (idempotent on the gateway
    event id) and, for a successful capture, the matching payment row is
    completed through sp_process_payment_webhook so that the deposit/loan
    bookkeeping stays inside the database layer.
    """
    raw_body = await request.body()

    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook secret is not configured, refusing to process the call.",
        )

    expected_sig = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    signature_ok = hmac.compare_digest(expected_sig, (x_razorpay_signature or "").strip())
    if not signature_ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature.")

    try:
        payload = json.loads(raw_body.decode())
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload.")

    event_name = payload.get("event") or ""
    internal_status = _EVENT_MAP.get(event_name)
    if not internal_status:
        # Unknown/irrelevant event: acknowledge so the gateway stops retrying.
        return {"status": "ignored", "event": event_name}

    entity = (
        payload.get("payload", {}).get("payment", {}).get("entity")
        or payload.get("payload", {}).get("refund", {}).get("entity")
        or {}
    )
    order_id = entity.get("order_id")
    gateway_payment_id = entity.get("id")
    amount_paise = entity.get("amount") or 0
    amount = round(float(amount_paise) / 100.0, 2)
    gateway_event_id = payload.get("id") or f"{event_name}:{gateway_payment_id}"

    payment = None
    if order_id:
        payment = db.query(Payment).filter(Payment.gateway_order_id == order_id).first()
    if not payment and gateway_payment_id:
        payment = db.query(Payment).filter(
            Payment.transaction_reference == gateway_payment_id
        ).first()
    if not payment:
        return {"status": "unmatched", "event": event_name, "order_id": order_id}

    # Idempotency: the same gateway event must only be applied once.
    duplicate = db.query(PaymentWebhookEvent).filter(
        PaymentWebhookEvent.gateway_event_id == gateway_event_id
    ).first()
    if duplicate:
        return {"status": "duplicate", "event": event_name, "payment_id": payment.payment_id}

    event = PaymentWebhookEvent(
        payment_id=payment.payment_id,
        gateway_event_id=gateway_event_id,
        event_type=internal_status,
        transaction_reference=gateway_payment_id or "unknown",
        amount_reported=amount,
        signature_verified=1,
        event_status="VERIFIED",
        payload=json.loads(raw_body.decode()),
    )
    db.add(event)
    db.flush()

    if internal_status == "PAYMENT_CAPTURED" and payment.payment_status != "COMPLETED":
        payment.payment_status = "COMPLETED"
        payment.paid_at = event.received_at
        payment.transaction_reference = gateway_payment_id
        if payment.loan and payment.loan.agreed_deposit > 0 and payment.payment_type == "DEPOSIT":
            payment.loan.deposit_status = "HELD"

    elif internal_status == "PAYMENT_FAILED" and payment.payment_status == "PENDING":
        payment.payment_status = "FAILED"

    db.commit()
    return {"status": "processed", "event": event_name, "payment_id": payment.payment_id}
