from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.app.core.config import settings
from backend.app.core.security import hash_password, verify_password, create_access_token, generate_otp, hash_token_or_otp
from backend.app.models.user import AppUser, AuthToken
from backend.app.schemas.auth import UserRegister, UserLogin, UserProfile, LoginDataOut, ChangePasswordRequest


def register_user(db: Session, data: UserRegister) -> Tuple[AppUser, str]:
    """Register a new student account and create an email verification OTP."""
    # Check duplicate roll number
    if db.query(AppUser).filter(AppUser.roll_number == data.roll_number.strip().upper()).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Roll number '{data.roll_number}' is already registered."
        )

    # Check duplicate email
    email = data.svnit_email.strip().lower()
    if db.query(AppUser).filter(AppUser.svnit_email == email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email '{email}' is already registered. Please sign in."
        )

    # Create user
    pw_hash = hash_password(data.password)
    admin_list = [e.lower() for e in getattr(settings, "ADMIN_EMAILS", [])]
    assigned_role = "ADMIN" if email in admin_list else "STUDENT"
    user = AppUser(
        roll_number=data.roll_number.strip().upper(),
        full_name=data.full_name.strip(),
        svnit_email=email,
        phone=data.phone.strip() if data.phone else None,
        hostel_or_dept=data.hostel_or_dept.strip() if data.hostel_or_dept else None,
        password_hash=pw_hash,
        role=assigned_role,
        is_verified=0,
        is_active=1
    )
    db.add(user)
    db.flush()

    # Generate 6-digit email verification OTP
    otp = generate_otp(6)
    token_hash = hash_token_or_otp(otp)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)

    auth_token = AuthToken(
        user_id=user.user_id,
        token_type="EMAIL_OTP",
        token_hash=token_hash,
        expires_at=expires_at
    )
    db.add(auth_token)
    db.commit()
    db.refresh(user)

    return user, otp


def verify_email_otp(db: Session, email: str, otp: str) -> AppUser:
    """Verify email OTP and mark student account verified."""
    email = email.strip().lower()
    user = db.query(AppUser).filter(AppUser.svnit_email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found."
        )
    if user.is_verified:
        return user

    token_hash = hash_token_or_otp(otp.strip())
    now = datetime.now(timezone.utc)

    token = db.query(AuthToken).filter(
        AuthToken.user_id == user.user_id,
        AuthToken.token_type == "EMAIL_OTP",
        AuthToken.token_hash == token_hash,
        AuthToken.expires_at > now,
        AuthToken.used_at.is_(None)
    ).first()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification OTP."
        )

    token.used_at = now
    user.is_verified = 1
    db.commit()
    db.refresh(user)
    return user


def resend_verification_otp(db: Session, email: str) -> str:
    """Generate and return a new email OTP for an unverified account."""
    email = email.strip().lower()
    user = db.query(AppUser).filter(AppUser.svnit_email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found."
        )
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is already verified."
        )

    otp = generate_otp(6)
    token_hash = hash_token_or_otp(otp)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)

    auth_token = AuthToken(
        user_id=user.user_id,
        token_type="EMAIL_OTP",
        token_hash=token_hash,
        expires_at=expires_at
    )
    db.add(auth_token)
    db.commit()
    return otp


def authenticate_user(db: Session, login_data: UserLogin) -> Tuple[AppUser, str]:
    """Authenticate student with email and password and issue JWT."""
    email = login_data.email.strip().lower()
    user = db.query(AppUser).filter(
        AppUser.svnit_email == email,
        AppUser.deleted_at.is_(None)
    ).first()

    if not user or not verify_password(login_data.password, user.password_hash):
        # Record the failed attempt for the audit trail, then reject.
        _record_login_attempt(db, user.user_id if user else None, email, "failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid SVNIT email or password."
        )

    if not user.is_active:
        _record_login_attempt(db, user.user_id, email, "blocked")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is suspended. Contact campus admin."
        )

    # Ensure configured admin emails have ADMIN role
    admin_list = [e.lower() for e in getattr(settings, "ADMIN_EMAILS", [])]
    if email in admin_list and user.role != "ADMIN":
        user.role = "ADMIN"
        db.commit()
        db.refresh(user)

    _record_login_attempt(db, user.user_id, email, "success")

    access_token = create_access_token(
        data={"sub": str(user.user_id), "role": user.role, "email": user.svnit_email}
    )
    return user, access_token


def _record_login_attempt(db: Session, user_id: Optional[int], email: str, outcome: str) -> None:
    """Persist a sign-in attempt through the database routine (audit trail)."""
    try:
        db.execute(
            text("CALL sp_record_login_attempt(:uid, :email, :status)"),
            {"uid": user_id, "email": email, "status": outcome},
        )
        db.commit()
    except Exception:
        db.rollback()


def request_password_reset(db: Session, email: str) -> str:
    """Create a password reset OTP for the user."""
    email = email.strip().lower()
    user = db.query(AppUser).filter(
        AppUser.svnit_email == email,
        AppUser.deleted_at.is_(None)
    ).first()
    if not user:
        # Never reveal whether the address exists, and never hand out a code
        # that could be used to reset an account: return an empty string.
        return ""

    otp = generate_otp(6)
    token_hash = hash_token_or_otp(otp)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)

    token = AuthToken(
        user_id=user.user_id,
        token_type="PASSWORD_RESET",
        token_hash=token_hash,
        expires_at=expires_at
    )
    db.add(token)
    db.commit()
    return otp


def verify_password_reset_otp(db: Session, email: str, otp_or_token: str) -> bool:
    """Verify that a password reset OTP is valid and not expired, without consuming it yet."""
    email = email.strip().lower()
    user = db.query(AppUser).filter(
        AppUser.svnit_email == email,
        AppUser.deleted_at.is_(None)
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User account not found.")

    token_hash = hash_token_or_otp(otp_or_token.strip())
    now = datetime.now(timezone.utc)

    token = db.query(AuthToken).filter(
        AuthToken.user_id == user.user_id,
        AuthToken.token_type == "PASSWORD_RESET",
        AuthToken.token_hash == token_hash,
        AuthToken.expires_at > now,
        AuthToken.used_at.is_(None)
    ).first()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset code. Please check your email or request a new code."
        )
    return True


def reset_password(db: Session, email: str, otp_or_token: str, new_password: str) -> bool:
    """Reset user password using verification token/OTP."""
    email = email.strip().lower()
    user = db.query(AppUser).filter(
        AppUser.svnit_email == email,
        AppUser.deleted_at.is_(None)
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    token_hash = hash_token_or_otp(otp_or_token.strip())
    now = datetime.now(timezone.utc)

    token = db.query(AuthToken).filter(
        AuthToken.user_id == user.user_id,
        AuthToken.token_type == "PASSWORD_RESET",
        AuthToken.token_hash == token_hash,
        AuthToken.expires_at > now,
        AuthToken.used_at.is_(None)
    ).first()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset code."
        )

    token.used_at = now
    user.password_hash = hash_password(new_password)
    db.commit()
    return True

def _routine_message(exc: Exception, fallback: str) -> str:
    """Return only the message raised by a SIGNAL inside a stored routine.

    SQLAlchemy would otherwise echo the whole statement (including the bcrypt
    hash) back to the client, which is both noisy and a small information leak.
    """
    args = getattr(getattr(exc, "orig", None), "args", None)
    if args and len(args) > 1 and isinstance(args[1], str):
        return args[1]
    return fallback


def get_login_data(db: Session, user_id: int) -> LoginDataOut:
    """Login / account data of one user, read through ``sp_user_login_data``.

    The identity, verification state, last successful sign-in, failed attempt
    count and number of open sessions all come back from one database call.
    """
    row = db.execute(text("CALL sp_user_login_data(:uid)"), {"uid": user_id}).mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Login record not found.",
        )
    return LoginDataOut.model_validate(dict(row))


def change_login_data(db: Session, user: AppUser, data: ChangePasswordRequest) -> LoginDataOut:
    """Change the signed-in user's password and (optionally) login e-mail.

    The write goes through ``sp_update_user_login``, which validates the SVNIT
    domain, blocks duplicates and invalidates every open session of the user.
    """
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )

    new_pw_hash = hash_password(data.new_password)
    try:
        db.execute(
            text("CALL sp_update_user_login(:uid, :email, :pw)"),
            {"uid": user.user_id, "email": data.new_email, "pw": new_pw_hash},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_routine_message(exc, "Login details could not be updated."),
        )

    db.expire_all()
    return get_login_data(db, user.user_id)
