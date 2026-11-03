from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, text
from backend.app.core.database import get_db
from backend.app.dependencies.auth import get_current_admin
from backend.app.models.user import AppUser
from backend.app.models.catalog import Item
from backend.app.models.borrow import Loan, BorrowRequest
from backend.app.models.payment import Payment
from backend.app.models.dispute import Dispute
from backend.app.models.audit import AuditLog
from backend.app.schemas.auth import UserProfile
from backend.app.schemas.item import ItemOut
from backend.app.schemas.dispute import DisputeResolve, DisputeOut
from backend.app.schemas.admin import (
    UserStatusUpdate, UserRoleUpdate, ItemStatusUpdate,
    SystemStatsOut, AuditLogOut
)

router = APIRouter(prefix="/admin", tags=["Admin & Moderation"])


@router.get("/users", response_model=List[UserProfile])
def list_users(
    role: Optional[str] = None,
    is_active: Optional[int] = None,
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    query = db.query(AppUser).filter(AppUser.deleted_at.is_(None))
    if role:
        query = query.filter(AppUser.role == role)
    if is_active is not None:
        query = query.filter(AppUser.is_active == is_active)
    return query.order_by(AppUser.user_id.desc()).all()


@router.put("/users/{user_id}/status")
def update_user_status(
    user_id: int,
    data: UserStatusUpdate,
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    user = db.query(AppUser).filter(AppUser.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    user.is_active = 1 if data.is_active else 0
    # Audit log
    db.add(AuditLog(
        actor_id=current_admin.user_id,
        action="ADMIN_USER_STATUS_CHANGE",
        entity_type="APP_USER",
        entity_id=user_id,
        new_value={"is_active": user.is_active}
    ))
    db.commit()
    return {"message": f"User status set to {'ACTIVE' if data.is_active else 'SUSPENDED'}."}


@router.put("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    data: UserRoleUpdate,
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    user = db.query(AppUser).filter(AppUser.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    user.role = data.role
    db.add(AuditLog(
        actor_id=current_admin.user_id,
        action="ADMIN_USER_ROLE_CHANGE",
        entity_type="APP_USER",
        entity_id=user_id,
        new_value={"role": user.role}
    ))
    db.commit()
    return {"message": f"User role updated to {data.role}."}


@router.get("/items", response_model=List[ItemOut])
def list_admin_items(
    listing_status: Optional[str] = None,
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    query = db.query(Item).options(
        joinedload(Item.owner),
        joinedload(Item.category),
        joinedload(Item.location),
        joinedload(Item.images)
    )
    if listing_status:
        query = query.filter(Item.listing_status == listing_status)
    items = query.order_by(Item.created_at.desc()).limit(100).all()

    results = []
    for it in items:
        primary_img = None
        if it.images:
            for img in it.images:
                if img.is_primary:
                    primary_img = img.image_url
                    break
            if not primary_img:
                primary_img = it.images[0].image_url

        results.append(ItemOut(
            item_id=it.item_id,
            owner_id=it.owner_id,
            owner_name=it.owner.full_name if it.owner else "Student",
            owner_email=it.owner.svnit_email if it.owner else "",
            owner_hostel=it.owner.hostel_or_dept if it.owner else None,
            category_id=it.category_id,
            category_name=it.category.category_name if it.category else "",
            location_id=it.location_id,
            location_name=it.location.name if it.location else "SVNIT Campus",
            title=it.title,
            description=it.description,
            item_condition=it.item_condition,
            deposit_amount=it.deposit_amount,
            daily_fee=it.daily_fee,
            max_borrow_days=it.max_borrow_days,
            listing_status=it.listing_status,
            primary_image_url=primary_img,
            is_favorite=False,
            created_at=it.created_at,
        ))
    return results


@router.put("/items/{item_id}/status")
def update_item_status(
    item_id: int,
    data: ItemStatusUpdate,
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    item = db.query(Item).filter(Item.item_id == item_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    old_status = item.listing_status
    item.listing_status = data.listing_status
    db.add(AuditLog(
        actor_id=current_admin.user_id,
        action="ADMIN_ITEM_MODERATION",
        entity_type="ITEM",
        entity_id=item_id,
        old_value={"status": old_status},
        new_value={"status": item.listing_status}
    ))
    db.commit()
    return {"message": f"Item status updated to {data.listing_status}."}


@router.get("/stats", response_model=SystemStatsOut)
def get_stats(
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    total_students = db.query(AppUser).filter(AppUser.role == "STUDENT", AppUser.deleted_at.is_(None)).count()
    total_listings = db.query(Item).count()
    active_listings = db.query(Item).filter(Item.listing_status == "ACTIVE").count()
    active_loans = db.query(Loan).filter(Loan.status.in_(("SCHEDULED", "ACTIVE", "OVERDUE"))).count()
    completed_loans = db.query(Loan).filter(Loan.status == "RETURNED").count()

    volume = db.query(func.coalesce(func.sum(Payment.amount), Decimal("0.00"))).filter(
        Payment.payment_status == "COMPLETED",
        Payment.payment_type.in_(("RENTAL_FEE", "DEPOSIT"))
    ).scalar() or Decimal("0.00")

    held_dep = db.query(func.coalesce(func.sum(Loan.agreed_deposit), Decimal("0.00"))).filter(
        Loan.deposit_status == "HELD"
    ).scalar() or Decimal("0.00")

    pending_disp = db.query(Dispute).filter(Dispute.status.in_(("OPEN", "UNDER_REVIEW"))).count()

    return SystemStatsOut(
        total_students=total_students,
        total_listings=total_listings,
        active_listings=active_listings,
        active_loans=active_loans,
        completed_loans=completed_loans,
        total_rental_volume=volume,
        total_held_deposits=held_dep,
        pending_disputes=pending_disp
    )


@router.get("/audit-logs", response_model=List[AuditLogOut])
def get_audit_logs(
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(100).all()
    return logs


@router.get("/disputes", response_model=List[DisputeOut])
def list_admin_disputes(
    status: Optional[str] = None,
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    query = db.query(Dispute).options(
        joinedload(Dispute.raiser),
        joinedload(Dispute.against_user),
        joinedload(Dispute.evidence)
    )
    if status:
        query = query.filter(Dispute.status == status)
    disps = query.order_by(Dispute.created_at.desc()).all()
    return [
        DisputeOut(
            dispute_id=d.dispute_id,
            loan_id=d.loan_id,
            raised_by=d.raised_by,
            raised_by_name=d.raiser.full_name if d.raiser else "Student",
            against_user_id=d.against_user_id,
            against_user_name=d.against_user.full_name if d.against_user else "Student",
            dispute_type=d.dispute_type,
            description=d.description,
            status=d.status,
            amount_claimed=d.amount_claimed,
            amount_awarded=d.amount_awarded,
            resolution_note=d.resolution_note,
            evidence_urls=[e.image_url for e in d.evidence] if d.evidence else [],
            created_at=d.created_at,
            resolved_at=d.resolved_at,
        )
        for d in disps
    ]


@router.get("/loans")
def list_admin_loans(
    status: Optional[str] = None,
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    query = db.query(Loan).options(
        joinedload(Loan.request).joinedload(BorrowRequest.item),
        joinedload(Loan.request).joinedload(BorrowRequest.borrower)
    )
    if status:
        query = query.filter(Loan.status == status)
    loans = query.order_by(Loan.created_at.desc()).limit(100).all()
    results = []
    for l in loans:
        req = l.request
        item = req.item if req else None
        borrower = req.borrower if req else None
        results.append({
            "loan_id": l.loan_id,
            "status": l.status,
            "item_id": item.item_id if item else None,
            "item_title": item.title if item else "Unknown Item",
            "owner_name": item.owner.full_name if (item and item.owner) else "Owner",
            "owner_email": item.owner.svnit_email if (item and item.owner) else "",
            "borrower_name": borrower.full_name if borrower else "Borrower",
            "borrower_email": borrower.svnit_email if borrower else "",
            "agreed_daily_fee": float(l.agreed_daily_fee),
            "agreed_deposit": float(l.agreed_deposit),
            "deposit_status": l.deposit_status,
            "start_date": str(req.start_date) if (req and getattr(req, "start_date", None)) else (l.issued_at.strftime("%Y-%m-%d") if l.issued_at else "N/A"),
            "end_date": str(req.end_date) if (req and getattr(req, "end_date", None)) else (l.due_at.strftime("%Y-%m-%d") if l.due_at else "N/A"),
            "created_at": l.created_at.isoformat() if l.created_at else None
        })
    return results


@router.post("/disputes/{dispute_id}/resolve", response_model=DisputeOut)
def resolve_dispute(
    dispute_id: int,
    data: DisputeResolve,
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    disp = db.query(Dispute).options(
        joinedload(Dispute.raiser),
        joinedload(Dispute.against_user)
    ).filter(Dispute.dispute_id == dispute_id).first()

    if not disp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispute not found.")

    disp.status = data.status
    disp.amount_awarded = data.amount_awarded
    disp.resolution_note = data.resolution_note
    disp.resolved_by = current_admin.user_id
    disp.resolved_at = datetime.now(timezone.utc)

    # Settle loan deposit if amount awarded covers damage
    if disp.loan:
        if data.amount_awarded > 0:
            disp.loan.deposit_status = "FORFEITED" if data.amount_awarded >= disp.loan.agreed_deposit else "SETTLED"

    db.add(AuditLog(
        actor_id=current_admin.user_id,
        action="DISPUTE_RESOLVED",
        entity_type="DISPUTE",
        entity_id=dispute_id,
        new_value={"status": disp.status, "amount_awarded": float(data.amount_awarded)}
    ))
    db.commit()
    db.refresh(disp)

    return DisputeOut(
        dispute_id=disp.dispute_id,
        loan_id=disp.loan_id,
        raised_by=disp.raised_by,
        raised_by_name=disp.raiser.full_name if disp.raiser else "Student",
        against_user_id=disp.against_user_id,
        against_user_name=disp.against_user.full_name if disp.against_user else "Student",
        dispute_type=disp.dispute_type,
        description=disp.description,
        status=disp.status,
        amount_claimed=disp.amount_claimed,
        amount_awarded=disp.amount_awarded,
        resolution_note=disp.resolution_note,
        created_at=disp.created_at,
        resolved_at=disp.resolved_at,
    )


# ---------------------------------------------------------------------------
# Office-hours guard (borrow_request modification window)
# ---------------------------------------------------------------------------


@router.get("/office-hours")
def get_office_hours(
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Current state of the office-hours guard on `borrow_request` updates."""
    rows = db.execute(
        text("SELECT config_key, config_value, description FROM app_config "
             "WHERE config_key LIKE 'office_hours%' OR config_key = 'enforce_office_hours'")
    ).mappings().all()
    config = {r["config_key"]: r["config_value"] for r in rows}
    return {
        "enabled": config.get("enforce_office_hours", "0") == "1",
        "allowed_day": config.get("office_hours_day", "Monday"),
        "allowed_window": config.get("office_hours_window", "14:00-16:00"),
        "detail": [dict(r) for r in rows],
    }


@router.put("/office-hours")
def set_office_hours(
    enabled: bool,
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Enable / disable the office-hours guard through `sp_set_office_hours_guard`."""
    try:
        db.execute(text("CALL sp_set_office_hours_guard(:enable)"), {"enable": 1 if enabled else 0})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Office-hours guard could not be changed: {exc}",
        )
    return get_office_hours(current_admin=current_admin, db=db)
