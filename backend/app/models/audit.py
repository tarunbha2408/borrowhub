from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, ForeignKey,
    Enum as SQLEnum, JSON
)
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class AuditLog(Base):
    """Application audit trail.

    Physical table is ``application_audit_log`` (see database/schema.sql).
    Every data-changing trigger in the schema writes its rows here, and the
    admin API reads the same table, so trigger-generated and
    application-generated audit entries live in one place.
    """

    __tablename__ = "application_audit_log"

    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    actor_id = Column(Integer, ForeignKey("app_user.user_id", ondelete="SET NULL"), nullable=True)
    action = Column(String(60), nullable=False)
    entity_type = Column(String(40), nullable=False)
    entity_id = Column(BigInteger, nullable=False)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    actor = relationship("AppUser")


class SystemJobLog(Base):
    """Result row of a scheduled maintenance run (sp_run_system_maintenance)."""

    __tablename__ = "system_job_log"

    job_run_id = Column(BigInteger, primary_key=True, autoincrement=True)
    job_name = Column(String(60), nullable=False)
    triggered_by = Column(
        SQLEnum("EVENT_SCHEDULER", "ON_DEMAND", "CRON", name="job_trigger_source"),
        nullable=False,
        default="ON_DEMAND",
    )
    overdue_marked = Column(Integer, nullable=False, default=0)
    requests_expired = Column(Integer, nullable=False, default=0)
    no_shows_expired = Column(Integer, nullable=False, default=0)
    tokens_purged = Column(Integer, nullable=False, default=0)
    ran_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
