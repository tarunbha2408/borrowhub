from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from backend.app.core.database import get_db
from backend.app.dependencies.auth import get_current_user
from backend.app.models.borrow import Loan, BorrowRequest
from backend.app.models.catalog import Item
from backend.app.models.trust import Review
from backend.app.models.user import AppUser
from backend.app.schemas.review import ReviewCreate, ReviewOut

router = APIRouter(prefix="/reviews", tags=["Reviews & Trust"])


@router.post("", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def submit_review(
    data: ReviewCreate,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    loan = db.query(Loan).options(
        joinedload(Loan.request).joinedload(BorrowRequest.item)
    ).filter(Loan.loan_id == data.loan_id).first()

    if not loan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found.")

    if loan.status != "RETURNED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reviews can only be submitted after the loan has been RETURNED."
        )

    borrower_id = loan.request.borrower_id
    owner_id = loan.request.item.owner_id

    if current_user.user_id not in (borrower_id, owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only parties to this loan (borrower or owner) can submit a review."
        )

    reviewee_id = owner_id if current_user.user_id == borrower_id else borrower_id

    # Check duplicate review
    existing = db.query(Review).filter(
        Review.loan_id == data.loan_id,
        Review.reviewer_id == current_user.user_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already submitted a review for this loan."
        )

    rev = Review(
        loan_id=data.loan_id,
        reviewer_id=current_user.user_id,
        reviewee_id=reviewee_id,
        rating=data.rating,
        review_text=data.review_text.strip() if data.review_text else None,
    )
    db.add(rev)
    db.commit()
    db.refresh(rev)

    reviewee = db.query(AppUser).filter(AppUser.user_id == reviewee_id).first()
    return ReviewOut(
        review_id=rev.review_id,
        loan_id=rev.loan_id,
        reviewer_id=rev.reviewer_id,
        reviewer_name=current_user.full_name,
        reviewee_id=rev.reviewee_id,
        reviewee_name=reviewee.full_name if reviewee else "Student",
        rating=rev.rating,
        review_text=rev.review_text,
        created_at=rev.created_at,
    )


@router.get("/user/{user_id}", response_model=List[ReviewOut])
def get_user_reviews(user_id: int, db: Session = Depends(get_db)):
    revs = db.query(Review).options(
        joinedload(Review.reviewer),
        joinedload(Review.reviewee)
    ).filter(Review.reviewee_id == user_id).order_by(Review.created_at.desc()).all()

    return [
        ReviewOut(
            review_id=r.review_id,
            loan_id=r.loan_id,
            reviewer_id=r.reviewer_id,
            reviewer_name=r.reviewer.full_name if r.reviewer else "Student",
            reviewee_id=r.reviewee_id,
            reviewee_name=r.reviewee.full_name if r.reviewee else "Student",
            rating=r.rating,
            review_text=r.review_text,
            created_at=r.created_at,
        )
        for r in revs
    ]
