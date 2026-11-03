import os
import secrets
import logging
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("borrowhub.config")

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


class Settings(BaseSettings):
    PROJECT_NAME: str = "BorrowHub"
    VERSION: str = "1.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Database
    DATABASE_URL: str = "mysql+pymysql://root:12345@localhost:3306/borrowhub?charset=utf8mb4"

    # Let SQLAlchemy create missing tables at startup.
    # Keep this OFF: database/schema.sql is the single source of truth (tables,
    # triggers, routines, views). Turning it on can silently create a second,
    # empty copy of a table when the ORM name and the SQL name disagree.
    AUTO_CREATE_TABLES: bool = False

    # Admin Management (role promotion on sign-in for these addresses)
    ADMIN_EMAILS: List[str] = ["admin@svnit.ac.in"]

    # Security
    JWT_SECRET_KEY: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    OTP_EXPIRY_MINUTES: int = 15
    MAX_OTP_ATTEMPTS: int = 5

    # Razorpay Payment Gateway
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    # When no real Razorpay keys are configured the checkout runs in simulated
    # mode. Signatures are still verified whenever real keys are present.
    PAYMENTS_SIMULATED: bool = True

    # Cloudinary Image Upload
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # SMTP / real email dispatch. Leave empty to print OTPs to the console.
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@borrowhub.local"
    SMTP_FROM_NAME: str = "BorrowHub SVNIT"
    SMTP_TLS: bool = True

    # --- Public demo mode -------------------------------------------------
    # When DEMO_MODE is on, the deployment is treated as a public showcase:
    #   * payments are always simulated (no real money can move)
    #   * e-mail OTPs are echoed back to the browser, because a demo visitor has
    #     no inbox on this domain and would otherwise be stuck at verification
    #   * the scheduled reset endpoint is available (see DEMO_RESET_TOKEN)
    DEMO_MODE: bool = False
    # Shared secret for POST /api/internal/reset-demo. Empty = endpoint disabled.
    DEMO_RESET_TOKEN: str = ""

    # Where uploaded listing images are written when Cloudinary is not configured.
    # On PaaS the filesystem is ephemeral - point this at a mounted disk
    # (e.g. /var/data/uploads on Render) or configure Cloudinary instead.
    UPLOAD_DIR: str = os.path.join(_BACKEND_DIR, "static", "uploads")

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    model_config = SettingsConfigDict(
        env_file=os.path.join(_BACKEND_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def masked_database_url(self) -> str:
        """DATABASE_URL with the password hidden - safe to print in logs."""
        import re as _re
        return _re.sub(r"://([^:@/]+):([^@]*)@", r"://\1:***@", self.DATABASE_URL)

    @property
    def resolved_jwt_secret(self) -> str:
        """JWT signing key. Generated once per process when not configured."""
        global _EPHEMERAL_SECRET
        if self.JWT_SECRET_KEY:
            return self.JWT_SECRET_KEY
        if _EPHEMERAL_SECRET is None:
            _EPHEMERAL_SECRET = secrets.token_urlsafe(48)
        return _EPHEMERAL_SECRET

    @property
    def razorpay_configured(self) -> bool:
        return bool(self.RAZORPAY_KEY_ID and self.RAZORPAY_KEY_SECRET)

    @property
    def payments_simulated(self) -> bool:
        # A public demo must never be able to move real money, even if somebody
        # accidentally pastes live Razorpay keys into the host's env vars.
        if self.DEMO_MODE:
            return True
        return self.PAYMENTS_SIMULATED or not self.razorpay_configured


_EPHEMERAL_SECRET: Optional[str] = None

settings = Settings()

if not settings.JWT_SECRET_KEY:
    logger.warning(
        "JWT_SECRET_KEY is not set. A random key is generated for this process only, "
        "so existing sessions become invalid after a restart. Set JWT_SECRET_KEY in "
        "backend/.env for a stable value."
    )
