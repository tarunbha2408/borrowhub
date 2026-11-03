from datetime import datetime, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.security import decode_access_token
from backend.app.models.user import AppUser

security_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db)
) -> AppUser:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid credentials. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(AppUser).filter(
        AppUser.user_id == int(user_id),
        AppUser.deleted_at.is_(None)
    ).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or has been deleted.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended or deactivated. Contact campus support.",
        )
    _reject_stale_token(payload, user)
    return user


def _reject_stale_token(payload: dict, user: AppUser) -> None:
    """Kill tokens that were minted before the last credential change.

    JWT access tokens are stateless, so simply revoking rows in ``auth_token``
    would not log anybody out. ``app_user.password_changed_at`` is the anchor:
    a token whose ``iat`` is older than that moment must not work any more.
    """
    changed = getattr(user, "password_changed_at", None)
    if not changed:
        return
    issued = payload.get("iat")
    if issued is None:
        return
    if isinstance(issued, (int, float)):
        issued_dt = datetime.fromtimestamp(float(issued), tz=timezone.utc).replace(tzinfo=None)
    else:
        return
    changed_dt = changed
    if isinstance(changed_dt, str):
        try:
            changed_dt = datetime.fromisoformat(changed_dt)
        except ValueError:
            return
    if changed_dt.tzinfo is not None:
        changed_dt = changed_dt.astimezone(timezone.utc).replace(tzinfo=None)
    if issued_dt < changed_dt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your password changed, so this session was signed out. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_active_student(
    current_user: AppUser = Depends(get_current_user)
) -> AppUser:
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your SVNIT email address to access this feature.",
        )
    return current_user


def get_current_admin(
    current_user: AppUser = Depends(get_current_user)
) -> AppUser:
    if current_user.role not in ("ADMIN", "MODERATOR"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required.",
        )
    return current_user


def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db)
) -> Optional[AppUser]:
    if not credentials:
        return None
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        return None
    user = db.query(AppUser).filter(
        AppUser.user_id == int(payload["sub"]),
        AppUser.is_active == 1,
        AppUser.deleted_at.is_(None)
    ).first()
    return user
