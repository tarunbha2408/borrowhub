from datetime import datetime
import re
from typing import Optional, Any
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict


class UserRegister(BaseModel):
    roll_number: str = Field(..., min_length=3, max_length=30)
    full_name: str = Field(..., min_length=2, max_length=120)
    svnit_email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    phone: Optional[str] = Field(None, max_length=20)
    hostel_or_dept: Optional[str] = Field(None, max_length=100)

    @field_validator("svnit_email")
    @classmethod
    def validate_svnit_domain(cls, v: str) -> str:
        email = v.strip().lower()
        # Must match svnit.ac.in or subdomains like coed.svnit.ac.in
        pattern = r"^[a-zA-Z0-9._%+-]+@([a-zA-Z0-9-]+\.)*svnit\.ac\.in$"
        if not re.match(pattern, email):
            raise ValueError("Only official SVNIT email addresses (@svnit.ac.in, @coed.svnit.ac.in) are allowed.")
        return email

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v


class VerifyEmailRequest(BaseModel):
    email: Optional[EmailStr] = None
    svnit_email: Optional[EmailStr] = None
    otp: str = Field(..., min_length=4, max_length=8)

    @model_validator(mode="before")
    @classmethod
    def resolve_email(cls, data: Any) -> Any:
        if isinstance(data, dict):
            em = data.get("email") or data.get("svnit_email")
            if not em:
                raise ValueError("Email is required.")
            data["email"] = em
            data["svnit_email"] = em
        return data


class ResendOtpRequest(BaseModel):
    email: EmailStr


class UserLogin(BaseModel):
    email: Optional[EmailStr] = None
    svnit_email: Optional[EmailStr] = None
    password: str

    @model_validator(mode="before")
    @classmethod
    def resolve_email(cls, data: Any) -> Any:
        if isinstance(data, dict):
            em = data.get("email") or data.get("svnit_email")
            if not em:
                raise ValueError("Email is required.")
            data["email"] = em
            data["svnit_email"] = em
        return data


class UserProfile(BaseModel):
    user_id: int
    roll_number: str
    full_name: str
    svnit_email: str
    phone: Optional[str] = None
    hostel_or_dept: Optional[str] = None
    role: str
    is_verified: int
    is_active: int

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile
    verification_token_or_otp: Optional[str] = None
    email_sent: bool = False
    message: Optional[str] = None


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetVerify(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=4, max_length=8)


class PasswordResetConfirm(BaseModel):
    email: EmailStr
    otp_or_token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class LoginDataOut(BaseModel):
    """Login / account data of one user, produced by ``sp_user_login_data``."""

    user_id: int
    roll_number: str
    full_name: str
    svnit_email: str
    role: str
    is_verified: int
    is_active: int
    last_login_at: Optional[datetime] = None
    failed_login_count: int = 0
    active_sessions: int = 0

    model_config = ConfigDict(from_attributes=True)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)
    new_email: Optional[str] = Field(default=None, max_length=254)
