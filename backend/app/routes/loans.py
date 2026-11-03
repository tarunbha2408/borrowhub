from typing import Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.dependencies.auth import get_current_user
from backend.app.models.user import AppUser
from backend.app.schemas.loan import (
    LoanOut, HandoverVerifyRequest, ReturnSubmitRequest,
    ReturnVerifyRequest, DepositSettleRequest
)
from backend.app.services.loan_service import (
    get_user_loans, get_loan_details, verify_handover,
    verify_return, settle_deposit
)
from backend.app.services.borrow_service import get_stored_otp

router = APIRouter(prefix="/loans", tags=["Loan Management"])


@router.get("", response_model=Dict[str, List[LoanOut]])
def list_my_loans(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_user_loans(db, current_user)


@router.get("/{loan_id}", response_model=LoanOut)
def get_loan(
    loan_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_loan_details(db, loan_id, current_user)


@router.get("/{loan_id}/handover-otp")
def get_handover_otp(
    loan_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    loan = get_loan_details(db, loan_id, current_user)
    if not loan.is_borrower:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Security rule: Handover OTP is confidential and displayed only to the borrower."
        )
    otp = get_stored_otp(loan_id, "HANDOVER", db=db)
    if not otp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Handover OTP has expired or was already used."
        )
    return {"loan_id": loan_id, "handover_otp": otp, "instructions": "Show this 6-digit code to the item owner when collecting the item."}


@router.post("/{loan_id}/verify-handover", response_model=LoanOut)
def handover_verify(
    loan_id: int,
    data: HandoverVerifyRequest,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return verify_handover(db, loan_id, current_user, data)


@router.get("/{loan_id}/return-otp")
def get_return_otp(
    loan_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    loan = get_loan_details(db, loan_id, current_user)
    if not loan.is_borrower:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Security rule: the Return OTP is confidential and displayed only to the borrower.",
        )
    otp = get_stored_otp(loan_id, "RETURN", db=db)
    if not otp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Return OTP is not active.")
    return {"loan_id": loan_id, "return_otp": otp, "instructions": "Share this 6-digit code upon item return."}


@router.post("/{loan_id}/verify-return", response_model=LoanOut)
def return_verify(
    loan_id: int,
    data: ReturnVerifyRequest,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return verify_return(db, loan_id, current_user, data)


@router.post("/{loan_id}/settle-deposit", response_model=LoanOut)
def deposit_settlement(
    loan_id: int,
    data: DepositSettleRequest,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return settle_deposit(db, loan_id, current_user, data)
