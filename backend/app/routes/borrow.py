from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.dependencies.auth import get_current_user, get_current_active_student
from backend.app.models.user import AppUser
from backend.app.schemas.borrow import BorrowRequestCreate, BorrowRequestOut, BorrowDecisionRequest
from backend.app.schemas.loan import LoanOut
from backend.app.services.borrow_service import (
    create_borrow_request, approve_borrow_request, reject_borrow_request,
    cancel_borrow_request, get_borrow_request_details,
    get_incoming_borrow_requests, get_outgoing_borrow_requests
)
from backend.app.services.loan_service import get_loan_details

router = APIRouter(prefix="/borrow-requests", tags=["Borrowing Workflow"])


@router.post("", response_model=BorrowRequestOut, status_code=status.HTTP_201_CREATED)
def submit_borrow_request(
    data: BorrowRequestCreate,
    current_user: AppUser = Depends(get_current_active_student),
    db: Session = Depends(get_db)
):
    req = create_borrow_request(db, current_user, data)
    return get_borrow_request_details(db, req.request_id)


@router.get("/incoming", response_model=List[BorrowRequestOut])
def list_incoming_requests(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_incoming_borrow_requests(db, current_user)


@router.get("/outgoing", response_model=List[BorrowRequestOut])
def list_outgoing_requests(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_outgoing_borrow_requests(db, current_user)


@router.get("/{request_id}", response_model=BorrowRequestOut)
def get_request(
    request_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    req = get_borrow_request_details(db, request_id)
    if (current_user.user_id not in (req.borrower_id, req.owner_id)
            and current_user.role not in ("ADMIN", "MODERATOR")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own borrow requests.",
        )
    return req


@router.post("/{request_id}/approve", response_model=LoanOut)
def approve_request(
    request_id: int,
    data: BorrowDecisionRequest = BorrowDecisionRequest(),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    loan = approve_borrow_request(db, request_id, current_user, data.decision_note)
    return get_loan_details(db, loan.loan_id, current_user)


@router.post("/{request_id}/reject", response_model=BorrowRequestOut)
def reject_request(
    request_id: int,
    data: BorrowDecisionRequest = BorrowDecisionRequest(),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    req = reject_borrow_request(db, request_id, current_user, data.decision_note)
    return get_borrow_request_details(db, req.request_id)


@router.post("/{request_id}/cancel", response_model=BorrowRequestOut)
def cancel_request(
    request_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    req = cancel_borrow_request(db, request_id, current_user)
    return get_borrow_request_details(db, req.request_id)
