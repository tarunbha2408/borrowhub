import threading
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Tuple, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text, and_, or_, desc
from backend.app.core.security import generate_otp, hash_token_or_otp
from backend.app.models.borrow import BorrowRequest, BookedDate, Loan, TemporaryOTP
from backend.app.models.catalog import Item
from backend.app.models.user import AppUser
from backend.app.services.notification_service import create_notification
from backend.app.schemas.borrow import BorrowRequestCreate, BorrowRequestOut

# Thread-safe in-memory cache for fast OTP lookups
_otp_lock = threading.Lock()
_active_loan_otps: Dict[Tuple[int, str], Dict[str, Any]] = {}


def get_stored_otp(loan_id: int, stage: str, db: Optional[Session] = None) -> Optional[str]:
    """Retrieve active OTP from thread-safe memory or persistent DB table."""
    now = datetime.now(timezone.utc)

    with _otp_lock:
        entry = _active_loan_otps.get((loan_id, stage))
        if entry:
            if entry["expires_at"] > now:
                return entry["otp"]
            else:
                del _active_loan_otps[(loan_id, stage)]

    # Query DB fallback
    target_session = db
    close_after = False
    if target_session is None:
        try:
            from backend.app.core.database import SessionLocal
            target_session = SessionLocal()
            close_after = True
        except Exception:
            return None

    try:
        # temporary_otp keeps the displayable code (short TTL, borrower-only
        # endpoint). Verification never trusts this table: it always compares
        # SHA-256 hashes against loan.handover_otp_hash / loan.return_otp_hash.
        record = target_session.query(TemporaryOTP).filter(
            TemporaryOTP.loan_id == loan_id,
            TemporaryOTP.stage == stage,
            TemporaryOTP.expires_at > now
        ).order_by(TemporaryOTP.otp_id.desc()).first()

        if record:
            exp = record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=timezone.utc)
            with _otp_lock:
                _active_loan_otps[(loan_id, stage)] = {
                    "otp": record.otp_code,
                    "expires_at": exp
                }
            return record.otp_code
    except Exception:
        pass
    finally:
        if close_after and target_session:
            target_session.close()

    return None


def store_loan_otp(loan_id: int, stage: str, otp: str, expire_hours: int = 72, db: Optional[Session] = None):
    """Store active OTP in thread-safe memory and persistent database table."""
    exp = datetime.now(timezone.utc) + timedelta(hours=expire_hours)

    with _otp_lock:
        _active_loan_otps[(loan_id, stage)] = {
            "otp": otp,
            "expires_at": exp
        }

    target_session = db
    close_after = False
    if target_session is None:
        try:
            from backend.app.core.database import SessionLocal
            target_session = SessionLocal()
            close_after = True
        except Exception:
            return

    try:
        # Clear any prior OTPs for this loan and stage
        target_session.query(TemporaryOTP).filter(
            TemporaryOTP.loan_id == loan_id,
            TemporaryOTP.stage == stage
        ).delete()

        record = TemporaryOTP(
            loan_id=loan_id,
            stage=stage,
            otp_code=otp,
            expires_at=exp
        )
        target_session.add(record)
        target_session.flush()
        if close_after:
            target_session.commit()
    except Exception:
        if close_after and target_session:
            target_session.rollback()
    finally:
        if close_after and target_session:
            target_session.close()


def create_borrow_request(db: Session, borrower: AppUser, data: BorrowRequestCreate) -> BorrowRequest:
    # Fetch item
    item = db.query(Item).filter(
        Item.item_id == data.item_id,
        Item.deleted_at.is_(None)
    ).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    if item.listing_status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This listing is currently paused or inactive."
        )

    if item.item_condition == "DAMAGED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This item is currently damaged and cannot be borrowed."
        )

    # Prevent self-borrowing
    if item.owner_id == borrower.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot borrow your own listing."
        )

    # Validate dates
    today = date.today()
    if data.start_date < today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Borrowing start date cannot be in the past."
        )

    duration_days = (data.end_date - data.start_date).days + 1
    if duration_days > item.max_borrow_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Requested period ({duration_days} days) exceeds maximum allowed borrowing duration ({item.max_borrow_days} days)."
        )

    # Check for date conflicts in booked_date
    conflicts = db.query(BookedDate).filter(
        BookedDate.item_id == data.item_id,
        BookedDate.booked_date >= data.start_date,
        BookedDate.booked_date <= data.end_date
    ).count()

    if conflicts > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This item is already booked for some or all of the selected dates."
        )

    # Create borrow request
    req = BorrowRequest(
        item_id=data.item_id,
        borrower_id=borrower.user_id,
        start_date=data.start_date,
        end_date=data.end_date,
        request_message=data.request_message.strip() if data.request_message else None,
        status="PENDING",
    )
    db.add(req)
    db.flush()

    # Create notification for owner
    create_notification(
        db=db,
        user_id=item.owner_id,
        title="New borrow request",
        message=f"{borrower.full_name} requested to borrow '{item.title}' from {data.start_date} to {data.end_date}.",
        event_type="REQUEST_RECEIVED",
        reference_type="REQUEST",
        reference_id=req.request_id,
        related_request_id=req.request_id,
    )
    db.commit()
    db.refresh(req)
    return req


def approve_borrow_request(db: Session, request_id: int, owner: AppUser, note: Optional[str] = None) -> Loan:
    req = db.query(BorrowRequest).options(
        joinedload(BorrowRequest.item),
        joinedload(BorrowRequest.borrower)
    ).filter(BorrowRequest.request_id == request_id).first()

    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Borrow request not found.")

    if req.item.owner_id != owner.user_id and owner.role not in ("ADMIN", "MODERATOR"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the item owner can approve this request."
        )

    if req.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only PENDING requests can be approved. Current status: {req.status}."
        )

    # Concurrency check on booked_date
    conflicts = db.query(BookedDate).filter(
        BookedDate.item_id == req.item_id,
        BookedDate.booked_date >= req.start_date,
        BookedDate.booked_date <= req.end_date
    ).count()

    if conflicts > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Item dates are no longer available due to a conflicting booking."
        )

    # Generate secure 6-digit handover and return OTPs
    handover_otp = generate_otp(6)
    return_otp = generate_otp(6)
    h_hash = hash_token_or_otp(handover_otp)
    r_hash = hash_token_or_otp(return_otp)

    # Set MySQL session variables for trigger execution
    db.execute(text(
        "SET @current_user_id = :uid, "
        "@pending_handover_otp_hash = :h_hash, "
        "@pending_return_otp_hash = :r_hash"
    ), {"uid": owner.user_id, "h_hash": h_hash, "r_hash": r_hash})

    req.status = "APPROVED"
    req.decided_at = datetime.now(timezone.utc)
    req.decision_note = note.strip() if note else "Approved by owner."

    db.flush()

    # trg_request_au has created the LOAN and populated BOOKED_DATE
    loan = db.query(Loan).filter(Loan.request_id == req.request_id).first()
    if not loan:
        # Fallback if trigger didn't fire in test environment
        days = (req.end_date - req.start_date).days + 1
        loan = Loan(
            request_id=req.request_id,
            status="SCHEDULED",
            due_at=datetime.combine(req.end_date, datetime.max.time()),
            agreed_daily_fee=req.item.daily_fee,
            agreed_deposit=req.item.deposit_amount,
            agreed_total_fee=req.item.daily_fee * days,
            handover_otp_hash=h_hash,
            return_otp_hash=r_hash,
        )
        db.add(loan)
        db.flush()

        curr_d = req.start_date
        while curr_d <= req.end_date:
            db.add(BookedDate(item_id=req.item_id, booked_date=curr_d, request_id=req.request_id))
            curr_d += timedelta(days=1)

    # Store active raw OTPs in secure DB and memory cache
    store_loan_otp(loan.loan_id, "HANDOVER", handover_otp, db=db)
    store_loan_otp(loan.loan_id, "RETURN", return_otp, db=db)

    # Handover notification for the owner (meetup and payment instructions; secret OTP is kept strictly with borrower)
    rent_total = float(loan.agreed_total_fee or 0)
    dep_total = float(loan.agreed_deposit or 0)
    grand_total = rent_total + dep_total
    borrower_name = req.borrower.full_name if req.borrower else "Borrower"

    create_notification(
        db=db,
        user_id=owner.user_id,
        title="Handover Scheduled",
        message=f"Borrow request approved for '{req.item.title}'. Meet {borrower_name} on campus to hand over the item. Collect ₹{grand_total:.2f} (rental: ₹{rent_total:.2f}, deposit: ₹{dep_total:.2f}) and verify their Handover OTP during meetup.",
        event_type="REQUEST_APPROVED",
        reference_type="LOAN",
        reference_id=loan.loan_id,
        related_request_id=req.request_id,
        related_loan_id=loan.loan_id,
    )

    # Automatically reject other pending requests that overlap
    overlapping_pending = db.query(BorrowRequest).filter(
        BorrowRequest.item_id == req.item_id,
        BorrowRequest.request_id != req.request_id,
        BorrowRequest.status == "PENDING",
        BorrowRequest.start_date <= req.end_date,
        BorrowRequest.end_date >= req.start_date
    ).all()

    for other_req in overlapping_pending:
        other_req.status = "REJECTED"
        other_req.decision_note = "Dates no longer available due to approved booking."
        create_notification(
            db=db,
            user_id=other_req.borrower_id,
            title="Request dates unavailable",
            message=f"Your request for '{req.item.title}' was declined because the item was booked for overlapping dates.",
            event_type="REQUEST_REJECTED",
            reference_type="REQUEST",
            reference_id=other_req.request_id,
            related_request_id=other_req.request_id,
        )

    db.commit()
    db.refresh(loan)
    return loan


def reject_borrow_request(db: Session, request_id: int, owner: AppUser, note: Optional[str] = None) -> BorrowRequest:
    req = db.query(BorrowRequest).options(joinedload(BorrowRequest.item)).filter(
        BorrowRequest.request_id == request_id
    ).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Borrow request not found.")

    if req.item.owner_id != owner.user_id and owner.role not in ("ADMIN", "MODERATOR"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can decline this request.")

    if req.status != "PENDING":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Request is already {req.status}.")

    db.execute(text("SET @current_user_id = :uid"), {"uid": owner.user_id})
    req.status = "REJECTED"
    req.decided_at = datetime.now(timezone.utc)
    req.decision_note = note.strip() if note else "Declined by owner."

    create_notification(
        db=db,
        user_id=req.borrower_id,
        title="Request declined",
        message=f"Your request for '{req.item.title}' was declined by the owner.",
        event_type="REQUEST_REJECTED",
        reference_type="REQUEST",
        reference_id=req.request_id,
        related_request_id=req.request_id,
    )

    db.commit()
    db.refresh(req)
    return req


def cancel_borrow_request(db: Session, request_id: int, user: AppUser) -> BorrowRequest:
    req = db.query(BorrowRequest).options(joinedload(BorrowRequest.item)).filter(
        BorrowRequest.request_id == request_id
    ).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")

    if req.borrower_id != user.user_id and req.item.owner_id != user.user_id and user.role not in ("ADMIN", "MODERATOR"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")

    if req.status in ("REJECTED", "CANCELLED"):
        return req

    db.execute(text("SET @current_user_id = :uid"), {"uid": user.user_id})
    req.status = "CANCELLED"
    req.decided_at = datetime.now(timezone.utc)
    req.decision_note = "Cancelled by user."

    # Delete any booked dates
    db.query(BookedDate).filter(BookedDate.request_id == req.request_id).delete()

    # Cancel associated loan if scheduled
    loan = db.query(Loan).filter(Loan.request_id == req.request_id).first()
    if loan and loan.status == "SCHEDULED":
        loan.status = "CANCELLED"

    db.commit()
    db.refresh(req)
    return req


def get_borrow_request_details(db: Session, request_id: int) -> BorrowRequestOut:
    req = db.query(BorrowRequest).options(
        joinedload(BorrowRequest.item).joinedload(Item.images),
        joinedload(BorrowRequest.borrower),
        joinedload(BorrowRequest.loan)
    ).filter(BorrowRequest.request_id == request_id).first()

    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")

    return _format_borrow_request_out(req)


def _format_borrow_request_out(req: BorrowRequest) -> BorrowRequestOut:
    days = (req.end_date - req.start_date).days + 1
    total_fee = req.item.daily_fee * days
    total_payable = total_fee + req.item.deposit_amount

    primary_img = None
    if req.item.images:
        for img in req.item.images:
            if img.is_primary:
                primary_img = img.image_url
                break
        if not primary_img:
            primary_img = req.item.images[0].image_url

    return BorrowRequestOut(
        request_id=req.request_id,
        item_id=req.item_id,
        item_title=req.item.title,
        item_image=primary_img,
        item_condition=req.item.item_condition,
        borrower_id=req.borrower_id,
        borrower_name=req.borrower.full_name,
        borrower_email=req.borrower.svnit_email,
        borrower_roll=req.borrower.roll_number,
        owner_id=req.item.owner_id,
        owner_name=req.item.owner.full_name if req.item.owner else "Owner",
        start_date=req.start_date,
        end_date=req.end_date,
        days_count=days,
        daily_fee=req.item.daily_fee,
        deposit_amount=req.item.deposit_amount,
        total_fee=total_fee,
        total_payable=total_payable,
        request_message=req.request_message,
        status=req.status,
        requested_at=req.requested_at,
        decided_at=req.decided_at,
        decision_note=req.decision_note,
        loan_id=req.loan.loan_id if req.loan else None,
        loan_status=req.loan.status if req.loan else None,
    )


def get_incoming_borrow_requests(db: Session, owner: AppUser) -> List[BorrowRequestOut]:
    requests = db.query(BorrowRequest).options(
        joinedload(BorrowRequest.item).joinedload(Item.images),
        joinedload(BorrowRequest.borrower),
        joinedload(BorrowRequest.loan)
    ).join(Item).filter(
        Item.owner_id == owner.user_id
    ).order_by(desc(BorrowRequest.requested_at)).all()

    return [_format_borrow_request_out(r) for r in requests]


def get_outgoing_borrow_requests(db: Session, borrower: AppUser) -> List[BorrowRequestOut]:
    requests = db.query(BorrowRequest).options(
        joinedload(BorrowRequest.item).joinedload(Item.images),
        joinedload(BorrowRequest.borrower),
        joinedload(BorrowRequest.loan)
    ).filter(
        BorrowRequest.borrower_id == borrower.user_id
    ).order_by(desc(BorrowRequest.requested_at)).all()

    return [_format_borrow_request_out(r) for r in requests]
