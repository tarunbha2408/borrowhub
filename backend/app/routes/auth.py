from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.rate_limit import rate_limit_auth
from backend.app.dependencies.auth import get_current_user
from backend.app.models.user import AppUser
from backend.app.schemas.auth import (
    UserRegister, VerifyEmailRequest, ResendOtpRequest, UserLogin,
    TokenResponse, UserProfile, PasswordResetRequest, PasswordResetVerify, PasswordResetConfirm,
    LoginDataOut, ChangePasswordRequest
)
from backend.app.services.auth_service import (
    register_user, verify_email_otp, resend_verification_otp,
    authenticate_user, request_password_reset, verify_password_reset_otp, reset_password,
    get_login_data, change_login_data
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _expose_otp_for_local_dev(email_sent: bool, otp: str):
    """Only echo an OTP back to the caller on a local dev box without SMTP.

    As soon as real mail delivery is configured (or the environment is not
    "development") the code exists solely in the recipient's inbox.
    """
    from backend.app.core.config import settings

    if email_sent:
        return None
    # Local development without SMTP, and the public DEMO deployment (where the
    # visitor cannot receive mail on this domain) - both need the code on screen.
    if settings.ENVIRONMENT.lower() != "development" and not settings.DEMO_MODE:
        return None
    return otp or None


@router.post("/register", response_model=TokenResponse, dependencies=[Depends(rate_limit_auth)])
def register(data: UserRegister, db: Session = Depends(get_db)):
    user, otp = register_user(db, data)
    from backend.app.services.email_service import send_email_otp
    email_sent, email_msg = send_email_otp(
        to_email=user.svnit_email,
        recipient_name=user.full_name,
        otp=otp,
        purpose="VERIFICATION"
    )
    from backend.app.core.config import settings
    from backend.app.core.security import create_access_token
    access_token = create_access_token(
        data={"sub": str(user.user_id), "role": user.role, "email": user.svnit_email}
    )
    debug_otp = _expose_otp_for_local_dev(email_sent, otp)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserProfile.model_validate(user),
        verification_token_or_otp=debug_otp,
        email_sent=email_sent,
        message=email_msg
    )


@router.post("/verify-email")
def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = verify_email_otp(db, data.email, data.otp)
    from backend.app.core.security import create_access_token
    access_token = create_access_token(
        data={"sub": str(user.user_id), "role": user.role, "email": user.svnit_email}
    )
    return {
        "message": "Email verified successfully.",
        "is_verified": bool(user.is_verified),
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserProfile.model_validate(user).model_dump(),
    }


@router.post("/resend-otp", dependencies=[Depends(rate_limit_auth)])
def resend_otp(data: ResendOtpRequest, db: Session = Depends(get_db)):
    otp = resend_verification_otp(db, data.email)
    from backend.app.models.user import AppUser
    from backend.app.services.email_service import send_email_otp
    user = db.query(AppUser).filter(AppUser.svnit_email == data.email.strip().lower()).first()
    recipient_name = user.full_name if user else "Student"
    email_sent, email_msg = send_email_otp(
        to_email=data.email,
        recipient_name=recipient_name,
        otp=otp,
        purpose="VERIFICATION"
    )
    from backend.app.core.config import settings
    debug_otp = _expose_otp_for_local_dev(email_sent, otp)
    return {"message": "Verification OTP resent.", "otp_debug": debug_otp, "email_sent": email_sent, "detail": email_msg}


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit_auth)])
def login(data: UserLogin, db: Session = Depends(get_db)):
    user, access_token = authenticate_user(db, data)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserProfile.model_validate(user)
    )


@router.get("/me", response_model=UserProfile)
def get_current_profile(current_user: AppUser = Depends(get_current_user)):
    return UserProfile.model_validate(current_user)


@router.get("/login-data", response_model=LoginDataOut)
def my_login_data(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Login record of the signed-in user (stored procedure `sp_user_login_data`)."""
    return get_login_data(db, current_user.user_id)


@router.post("/change-password", response_model=LoginDataOut, dependencies=[Depends(rate_limit_auth)])
def change_password(
    data: ChangePasswordRequest,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change password / login e-mail through `sp_update_user_login`.

    Every open session of the account is revoked by the procedure, so the
    client has to sign in again with the new credential.
    """
    return change_login_data(db, current_user, data)


@router.post("/forgot-password", dependencies=[Depends(rate_limit_auth)])
def forgot_password(data: PasswordResetRequest, db: Session = Depends(get_db)):
    otp = request_password_reset(db, data.email)
    if not otp:
        # Unknown address: return the same shape of response so that account
        # enumeration is not possible, but do not dispatch any code.
        return {
            "message": "If that SVNIT email is registered, a reset code has been sent.",
            "otp_debug": None,
            "email_sent": False,
            "detail": "No account matched the supplied address.",
        }
    from backend.app.models.user import AppUser
    from backend.app.services.email_service import send_email_otp
    user = db.query(AppUser).filter(AppUser.svnit_email == data.email.strip().lower()).first()
    recipient_name = user.full_name if user else "Student"
    email_sent, email_msg = send_email_otp(
        to_email=data.email,
        recipient_name=recipient_name,
        otp=otp,
        purpose="PASSWORD_RESET"
    )
    debug_otp = _expose_otp_for_local_dev(email_sent, otp)
    return {
        "message": "Password reset code sent to your email.",
        "otp_debug": debug_otp,
        "email_sent": email_sent,
        "detail": email_msg
    }


@router.post("/verify-reset-otp", dependencies=[Depends(rate_limit_auth)])
def verify_reset_otp_endpoint(data: PasswordResetVerify, db: Session = Depends(get_db)):
    verify_password_reset_otp(db, data.email, data.otp)
    return {"message": "Reset code verified! Please set your new password.", "verified": True}


@router.post("/reset-password", dependencies=[Depends(rate_limit_auth)])
def reset_user_password(data: PasswordResetConfirm, db: Session = Depends(get_db)):
    reset_password(db, data.email, data.otp_or_token, data.new_password)
    return {"message": "Password updated successfully. You can now sign in."}
