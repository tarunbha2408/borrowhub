from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from backend.app.core.database import get_db
from backend.app.dependencies.auth import get_current_user
from backend.app.models.borrow import Loan, BorrowRequest
from backend.app.models.catalog import Item
from backend.app.models.dispute import Dispute, DisputeEvidence
from backend.app.models.notification import Notification
from backend.app.models.user import AppUser
from backend.app.schemas.dispute import DisputeCreate, DisputeOut

router = APIRouter(prefix="/disputes", tags=["Dispute Resolution"])


@router.post("", response_model=DisputeOut, status_code=status.HTTP_201_CREATED)
def raise_dispute(
    data: DisputeCreate,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    loan = db.query(Loan).options(
        joinedload(Loan.request).joinedload(BorrowRequest.item)
    ).filter(Loan.loan_id == data.loan_id).first()

    if not loan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found.")

    borrower_id = loan.request.borrower_id
    owner_id = loan.request.item.owner_id

    if current_user.user_id not in (borrower_id, owner_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only parties to the loan can raise a dispute.")

    against_id = owner_id if current_user.user_id == borrower_id else borrower_id

    disp = Dispute(
        loan_id=data.loan_id,
        raised_by=current_user.user_id,
        against_user_id=against_id,
        dispute_type=data.dispute_type,
        description=data.description.strip(),
        amount_claimed=data.amount_claimed,
        status="OPEN"
    )
    db.add(disp)
    db.flush()

    # Save attached photo proof
    if data.evidence_urls:
        for url in data.evidence_urls[:5]:
            if url and url.strip():
                db.add(DisputeEvidence(
                    dispute_id=disp.dispute_id,
                    image_url=url.strip()
                ))

    # Notify campus admins of new damage claim / dispute (in-app and email alert)
    from backend.app.services.email_service import send_dispute_alert_email
    admins = db.query(AppUser).filter(AppUser.role.in_(("ADMIN", "MODERATOR"))).all()
    for adm in admins:
        db.add(Notification(
            user_id=adm.user_id,
            type="DISPUTE_UPDATE",
            reference_type="DISPUTE",
            reference_id=disp.dispute_id,
            related_loan_id=disp.loan_id,
            title="⚠️ New Damaged Item / Dispute Filed",
            message=f"{current_user.full_name} filed a {data.dispute_type} claim for Loan #{data.loan_id} (Claim: ₹{data.amount_claimed}). Tap to review proof and mediate."
        ))
        try:
            send_dispute_alert_email(
                admin_email=adm.svnit_email,
                admin_name=adm.full_name,
                dispute_id=disp.dispute_id,
                loan_id=disp.loan_id,
                dispute_type=disp.dispute_type,
                claimed_amount=float(disp.amount_claimed or 0),
                description=disp.description,
                raised_by_name=current_user.full_name,
                evidence_urls=data.evidence_urls or []
            )
        except Exception:
            pass

    db.commit()
    db.refresh(disp)

    against_user = db.query(AppUser).filter(AppUser.user_id == against_id).first()
    return DisputeOut(
        dispute_id=disp.dispute_id,
        loan_id=disp.loan_id,
        raised_by=disp.raised_by,
        raised_by_name=current_user.full_name,
        against_user_id=against_id,
        against_user_name=against_user.full_name if against_user else "Student",
        dispute_type=disp.dispute_type,
        description=disp.description,
        status=disp.status,
        amount_claimed=disp.amount_claimed,
        amount_awarded=disp.amount_awarded,
        resolution_note=disp.resolution_note,
        evidence_urls=[e.image_url for e in disp.evidence] if disp.evidence else [],
        created_at=disp.created_at,
        resolved_at=disp.resolved_at,
    )


@router.get("", response_model=List[DisputeOut])
def list_my_disputes(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    disps = db.query(Dispute).options(
        joinedload(Dispute.raiser),
        joinedload(Dispute.against_user),
        joinedload(Dispute.evidence)
    ).filter(
        (Dispute.raised_by == current_user.user_id) | (Dispute.against_user_id == current_user.user_id)
    ).order_by(Dispute.created_at.desc()).all()

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
