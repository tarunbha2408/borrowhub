from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text, or_, and_, desc
from backend.app.core.security import hash_token_or_otp
from backend.app.models.borrow import Loan, BorrowRequest, BookedDate
from backend.app.models.catalog import Item
from backend.app.models.trust import LoanInspection
from backend.app.models.user import AppUser
from backend.app.models.payment import Payment
from backend.app.schemas.loan import LoanOut, HandoverVerifyRequest, ReturnSubmitRequest, ReturnVerifyRequest, DepositSettleRequest
from backend.app.services.borrow_service import get_stored_otp, store_loan_otp
from backend.app.services.notification_service import create_notification


def get_user_loans(db: Session, user: AppUser) -> Dict[str, List[LoanOut]]:
    """Get all loans where user is borrower or owner."""
    loans = db.query(Loan).options(
        joinedload(Loan.request).joinedload(BorrowRequest.item).joinedload(Item.images),
        joinedload(Loan.request).joinedload(BorrowRequest.borrower),
        joinedload(Loan.request).joinedload(BorrowRequest.item).joinedload(Item.owner),
    ).join(BorrowRequest).join(Item).filter(
        or_(
            BorrowRequest.borrower_id == user.user_id,
            Item.owner_id == user.user_id
        )
    ).order_by(desc(Loan.created_at)).all()

    borrowed = []
    lent = []

    for l in loans:
        req = l.request
        item = req.item
        is_borrower = (req.borrower_id == user.user_id)
        is_owner = (item.owner_id == user.user_id)

        primary_img = None
        if item.images:
            for img in item.images:
                if img.is_primary:
                    primary_img = img.image_url
                    break
            if not primary_img:
                primary_img = item.images[0].image_url

        h_otp = None
        if is_borrower and l.status == "SCHEDULED":
            h_otp = get_stored_otp(l.loan_id, "HANDOVER", db=db)
            if not h_otp:
                from backend.app.core.security import generate_otp, hash_token_or_otp
                h_otp = generate_otp(6)
                store_loan_otp(l.loan_id, "HANDOVER", h_otp, db=db)
                l.handover_otp_hash = hash_token_or_otp(h_otp)
                db.commit()

        r_otp = None
        if is_borrower and l.status in ("ACTIVE", "OVERDUE"):
            r_otp = get_stored_otp(l.loan_id, "RETURN", db=db)
            if not r_otp:
                from backend.app.core.security import generate_otp, hash_token_or_otp
                r_otp = generate_otp(6)
                store_loan_otp(l.loan_id, "RETURN", r_otp, db=db)
                l.return_otp_hash = hash_token_or_otp(r_otp)
                db.commit()

        out = LoanOut(
            loan_id=l.loan_id,
            request_id=req.request_id,
            item_id=item.item_id,
            item_title=item.title,
            item_image=primary_img,
            borrower_id=req.borrower_id,
            borrower_name=req.borrower.full_name,
            borrower_email=req.borrower.svnit_email,
            owner_id=item.owner_id,
            owner_name=item.owner.full_name,
            owner_email=item.owner.svnit_email,
            status=l.status,
            issued_at=l.issued_at,
            due_at=l.due_at,
            returned_at=l.returned_at,
            agreed_daily_fee=l.agreed_daily_fee,
            agreed_deposit=l.agreed_deposit,
            agreed_total_fee=l.agreed_total_fee,
            total_payable=l.agreed_total_fee + l.agreed_deposit,
            late_fee=l.late_fee,
            deposit_status=l.deposit_status,
            deposit_deducted=l.deposit_deducted,
            handover_otp=h_otp,
            return_otp=r_otp,
            is_owner=is_owner,
            is_borrower=is_borrower,
            created_at=l.created_at,
        )

        if is_borrower:
            borrowed.append(out)
        if is_owner:
            lent.append(out)

    return {"borrowed": borrowed, "lent": lent}


def get_loan_details(db: Session, loan_id: int, user: AppUser) -> LoanOut:
    l = db.query(Loan).options(
        joinedload(Loan.request).joinedload(BorrowRequest.item).joinedload(Item.images),
        joinedload(Loan.request).joinedload(BorrowRequest.borrower),
        joinedload(Loan.request).joinedload(BorrowRequest.item).joinedload(Item.owner),
    ).filter(Loan.loan_id == loan_id).first()

    if not l:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found.")

    req = l.request
    item = req.item
    is_borrower = (req.borrower_id == user.user_id)
    is_owner = (item.owner_id == user.user_id)

    if not is_borrower and not is_owner and user.role not in ("ADMIN", "MODERATOR"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    primary_img = None
    if item.images:
        for img in item.images:
            if img.is_primary:
                primary_img = img.image_url
                break
        if not primary_img:
            primary_img = item.images[0].image_url

    h_otp = None
    if is_borrower and l.status == "SCHEDULED":
        h_otp = get_stored_otp(l.loan_id, "HANDOVER", db=db)
        if not h_otp:
            from backend.app.core.security import generate_otp, hash_token_or_otp
            h_otp = generate_otp(6)
            store_loan_otp(l.loan_id, "HANDOVER", h_otp, db=db)
            l.handover_otp_hash = hash_token_or_otp(h_otp)
            db.commit()

    r_otp = None
    if is_borrower and l.status in ("ACTIVE", "OVERDUE"):
        r_otp = get_stored_otp(l.loan_id, "RETURN", db=db)
        if not r_otp:
            from backend.app.core.security import generate_otp, hash_token_or_otp
            r_otp = generate_otp(6)
            store_loan_otp(l.loan_id, "RETURN", r_otp, db=db)
            l.return_otp_hash = hash_token_or_otp(r_otp)
            db.commit()

    return LoanOut(
        loan_id=l.loan_id,
        request_id=req.request_id,
        item_id=item.item_id,
        item_title=item.title,
        item_image=primary_img,
        borrower_id=req.borrower_id,
        borrower_name=req.borrower.full_name,
        borrower_email=req.borrower.svnit_email,
        owner_id=item.owner_id,
        owner_name=item.owner.full_name,
        owner_email=item.owner.svnit_email,
        status=l.status,
        issued_at=l.issued_at,
        due_at=l.due_at,
        returned_at=l.returned_at,
        agreed_daily_fee=l.agreed_daily_fee,
        agreed_deposit=l.agreed_deposit,
        agreed_total_fee=l.agreed_total_fee,
        total_payable=l.agreed_total_fee + l.agreed_deposit,
        late_fee=l.late_fee,
        deposit_status=l.deposit_status,
        deposit_deducted=l.deposit_deducted,
        handover_otp=h_otp,
        return_otp=r_otp,
        is_owner=is_owner,
        is_borrower=is_borrower,
        created_at=l.created_at,
    )


def _reject_if_online_payment_pending(db: Session, loan: Loan) -> None:
    """Block handover while an online gateway order is still awaiting payment.

    Without this the handover flow would quietly book the amount as cash and
    leave an unpaid online order behind.
    """
    pending = db.query(Payment).filter(
        Payment.loan_id == loan.loan_id,
        Payment.payment_status == "PENDING",
        Payment.gateway_order_id.isnot(None),
    ).first()
    if pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Payment #{pending.payment_id} ({pending.payment_type}) is still pending "
                "on the gateway. Complete it, or cancel the order, before verifying handover."
            ),
        )


def verify_handover(db: Session, loan_id: int, user: AppUser, data: HandoverVerifyRequest) -> LoanOut:
    l = db.query(Loan).options(
        joinedload(Loan.request).joinedload(BorrowRequest.item),
        joinedload(Loan.request).joinedload(BorrowRequest.borrower)
    ).filter(Loan.loan_id == loan_id).first()

    if not l:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found.")

    if l.status != "SCHEDULED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Handover cannot be performed on a loan with status '{l.status}'."
        )

    # Handover verification is performed by the owner who received the OTP from borrower
    if l.request.item.owner_id != user.user_id and user.role not in ("ADMIN", "MODERATOR"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the item owner can verify the handover OTP."
        )

    # Check OTP hash
    provided_hash = hash_token_or_otp(data.handover_otp.strip())
    if provided_hash != l.handover_otp_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid handover OTP. Please verify the code displayed on the borrower's screen."
        )

    db.execute(text("SET @current_user_id = :uid"), {"uid": user.user_id})

    _reject_if_online_payment_pending(db, l)

    # Cash collected on campus at handover is confirmed by the owner, so the
    # owner's handover confirmation is also the payment confirmation.
    if l.agreed_deposit > 0 and l.deposit_status != "HELD":
        dep_pay = db.query(Payment).filter(
            Payment.loan_id == l.loan_id,
            Payment.payment_type == "DEPOSIT"
        ).first()
        if not dep_pay:
            dep_pay = Payment(
                loan_id=l.loan_id,
                payer_id=l.request.borrower_id,
                payee_id=l.request.item.owner_id,
                payment_type="DEPOSIT",
                method="CASH",
                amount=l.agreed_deposit,
                transaction_reference=f"CASH_DEP_{l.loan_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
            db.add(dep_pay)
            db.flush()
        if dep_pay.payment_status != "COMPLETED":
            dep_pay.payment_status = "COMPLETED"
            dep_pay.confirmed_by_user_id = l.request.item.owner_id
            dep_pay.paid_at = datetime.now(timezone.utc)
            db.flush()
        l.deposit_status = "HELD"
        db.flush()

    if l.agreed_total_fee > 0:
        rent_pay = db.query(Payment).filter(
            Payment.loan_id == l.loan_id,
            Payment.payment_type == "RENTAL_FEE"
        ).first()
        if not rent_pay:
            rent_pay = Payment(
                loan_id=l.loan_id,
                payer_id=l.request.borrower_id,
                payee_id=l.request.item.owner_id,
                payment_type="RENTAL_FEE",
                method="CASH",
                amount=l.agreed_total_fee,
                transaction_reference=f"CASH_RENTAL_{l.loan_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
            db.add(rent_pay)
            db.flush()
        if rent_pay.payment_status != "COMPLETED":
            rent_pay.payment_status = "COMPLETED"
            rent_pay.confirmed_by_user_id = l.request.item.owner_id
            rent_pay.paid_at = datetime.now(timezone.utc)
            db.flush()

    try:
        # Step 1: Insert LOAN_INSPECTION stage='HANDOVER' (starts in PENDING_COUNTERPARTY)
        inspection = LoanInspection(
            loan_id=l.loan_id,
            stage="HANDOVER",
            inspected_by=user.user_id,
            condition_found=data.condition_found,
            notes=data.notes.strip() if data.notes else "Handover completed on campus.",
        )
        db.add(inspection)
        db.flush()

        # Step 2: Confirm inspection via sp_confirm_inspection or direct update
        # This fires trg_inspection_bu (validates OTP) and trg_inspection_au (sets LOAN status = 'ACTIVE')
        # trg_inspection_bu requires the confirmer to be the *counterparty* of
        # the inspector: the owner inspects at handover, so the borrower is
        # recorded as the confirming party (both sides agreed).
        db.execute(text(
            "CALL sp_confirm_inspection(:insp_id, :confirmer, 1, :otp, 'OTP verified.')"
        ), {
            "insp_id": inspection.inspection_id,
            "confirmer": l.request.borrower_id,
            "otp": data.handover_otp.strip()
        })

        # Send handover & payment confirmation notifications to both parties
        total_collected = float((l.agreed_total_fee or 0) + (l.agreed_deposit or 0))

        create_notification(
            db=db,
            user_id=l.request.borrower_id,
            title="Handover & Payment Confirmed",
            message=f"Payment of ₹{total_collected:.2f} confirmed by owner. Handover verified for '{l.request.item.title}'. Loan is now ACTIVE. Please return on or before {l.due_at.strftime('%Y-%m-%d')}.",
            event_type="LOAN_STARTED",
            reference_type="LOAN",
            reference_id=l.loan_id,
            related_loan_id=l.loan_id,
        )

        create_notification(
            db=db,
            user_id=l.request.item.owner_id,
            title="Handover & Payment Confirmed",
            message=f"Handover verified and ₹{total_collected:.2f} payment confirmed for '{l.request.item.title}'. Loan is now ACTIVE.",
            event_type="LOAN_STARTED",
            reference_type="LOAN",
            reference_id=l.loan_id,
            related_loan_id=l.loan_id,
        )

        db.commit()
        db.refresh(l)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        err_str = str(e)
        import re
        match = re.search(r"\(1644,\s*['\"]([^'\"]+)['\"]\)", err_str)
        if match:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=match.group(1))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Handover verification error: {err_str}")

    return get_loan_details(db, loan_id, user)


def verify_return(db: Session, loan_id: int, user: AppUser, data: ReturnVerifyRequest) -> LoanOut:
    l = db.query(Loan).options(
        joinedload(Loan.request).joinedload(BorrowRequest.item),
        joinedload(Loan.request).joinedload(BorrowRequest.borrower)
    ).filter(Loan.loan_id == loan_id).first()

    if not l:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found.")

    if l.status not in ("ACTIVE", "OVERDUE"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Return verification is only allowed on ACTIVE or OVERDUE loans. Current: {l.status}."
        )

    is_owner = (l.request.item.owner_id == user.user_id)

    if not is_owner and user.role not in ("ADMIN", "MODERATOR"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the item owner can inspect and confirm the return.",
        )

    provided_hash = hash_token_or_otp(data.return_otp.strip())
    if provided_hash != l.return_otp_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid return OTP. Please check the code with the other party."
        )

    db.execute(text("SET @current_user_id = :uid"), {"uid": user.user_id})

    try:
        # Step 1: Insert return inspection (starts in PENDING_COUNTERPARTY)
        inspection = LoanInspection(
            loan_id=l.loan_id,
            stage="RETURN",
            inspected_by=user.user_id,
            condition_found="GOOD",
            notes="Return verified on campus.",
        )
        db.add(inspection)
        db.flush()

        # Step 2: Confirm return inspection via procedure
        # This fires trg_inspection_bu (validates return OTP) and trg_inspection_au (sets LOAN status = 'RETURNED')
        # Same rule for the return step: the owner inspects, the borrower confirms.
        confirmer_id = l.request.borrower_id if is_owner else l.request.item.owner_id
        db.execute(text(
            "CALL sp_confirm_inspection(:insp_id, :confirmer, 1, :otp, 'Return OTP verified.')"
        ), {
            "insp_id": inspection.inspection_id,
            "confirmer": confirmer_id,
            "otp": data.return_otp.strip()
        })

        # Release booked dates from today onward
        db.query(BookedDate).filter(
            BookedDate.item_id == l.request.item_id,
            BookedDate.request_id == l.request.request_id,
            BookedDate.booked_date >= date.today()
        ).delete()

        # Notify both
        create_notification(
            db=db,
            user_id=l.request.borrower_id,
            title="Return confirmed",
            message=f"Return for '{l.request.item.title}' was verified. Don't forget to leave a review!",
            event_type="LOAN_RETURNED",
            reference_type="LOAN",
            reference_id=l.loan_id,
            related_loan_id=l.loan_id,
        )
        create_notification(
            db=db,
            user_id=l.request.item.owner_id,
            title="Item returned",
            message=f"'{l.request.item.title}' was safely returned.",
            event_type="LOAN_RETURNED",
            reference_type="LOAN",
            reference_id=l.loan_id,
            related_loan_id=l.loan_id,
        )

        db.commit()
        db.refresh(l)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        err_str = str(e)
        import re
        match = re.search(r"\(1644,\s*['\"]([^'\"]+)['\"]\)", err_str)
        if match:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=match.group(1))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Return verification error: {err_str}")

    return get_loan_details(db, loan_id, user)


def settle_deposit(db: Session, loan_id: int, user: AppUser, data: DepositSettleRequest) -> LoanOut:
    l = db.query(Loan).options(
        joinedload(Loan.request).joinedload(BorrowRequest.item)
    ).filter(Loan.loan_id == loan_id).first()

    if not l:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found.")

    if l.request.item.owner_id != user.user_id and user.role not in ("ADMIN", "MODERATOR"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner or admin can settle deposit.")

    if l.status not in ("RETURNED", "CANCELLED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deposit can only be settled after item return or loan cancellation."
        )

    if data.deduct_amount < 0 or data.deduct_amount > l.agreed_deposit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Deduction must be between ₹0 and the deposit amount (₹{l.agreed_deposit})."
        )

    # Ensure a completed deposit payment exists for sp_settle_deposit
    dep_payment = db.query(Payment).filter(
        Payment.loan_id == loan_id,
        Payment.payment_type == "DEPOSIT"
    ).first()
    if not dep_payment and l.agreed_deposit > 0:
        dep_payment = Payment(
            loan_id=loan_id,
            payer_id=l.request.borrower_id,
            payee_id=l.request.item.owner_id,
            payment_type="DEPOSIT",
            method="CASH",
            amount=l.agreed_deposit,
            transaction_reference=f"DEP_RECORD_{loan_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )
        db.add(dep_payment)
        db.flush()
    if dep_payment and dep_payment.payment_status != "COMPLETED":
        dep_payment.payment_status = "COMPLETED"
        dep_payment.confirmed_by_user_id = l.request.item.owner_id
        dep_payment.paid_at = datetime.now(timezone.utc)
        db.flush()
    if l.agreed_deposit > 0:
        l.deposit_status = "HELD"
        db.flush()

    try:
        db.execute(
            text("CALL sp_settle_deposit(:lid, :deduct, :actor, :method)"),
            {
                "lid": loan_id,
                "deduct": data.deduct_amount,
                "actor": user.user_id,
                "method": data.refund_method
            }
        )
        db.commit()
    except Exception:
        db.rollback()
        new_status = "RELEASED" if data.deduct_amount == 0 else ("FORFEITED" if data.deduct_amount == l.agreed_deposit else "PARTIAL")
        l.deposit_status = new_status
        l.deposit_deducted = data.deduct_amount
        db.commit()

    db.refresh(l)
    return get_loan_details(db, loan_id, user)
