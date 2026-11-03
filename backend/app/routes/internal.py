"""Operational endpoints for the public demo deployment.

``POST /api/internal/reset-demo`` drops every table/view/routine in the connected
schema and rebuilds it from ``database/schema_paas.sql`` + ``database/seed_paas.sql``.
It exists so a free external cron (Render cron job, cron-job.org, GitHub Actions)
can put the demo back into its pristine state every night - visitors may create
accounts, listings and borrow requests, but nothing accumulates.

Security:
  * disabled unless ``DEMO_RESET_TOKEN`` is configured,
  * the caller must send it in the ``X-Demo-Reset-Token`` header,
  * comparison is constant-time,
  * the endpoint is rate limited to one run per 5 minutes.
"""

import hmac
import logging
import time

from fastapi import APIRouter, Header, HTTPException, status

from backend.app.core.config import settings

logger = logging.getLogger("borrowhub.demo")
router = APIRouter(prefix="/internal", tags=["Operations"])

_last_reset_at = 0.0
_MIN_INTERVAL_SECONDS = 300


@router.post("/reset-demo")
def reset_demo(
    x_demo_reset_token: str = Header(default="", alias="X-Demo-Reset-Token"),
):
    global _last_reset_at

    if not settings.DEMO_RESET_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo reset is not enabled on this deployment.",
        )

    if not hmac.compare_digest(x_demo_reset_token, settings.DEMO_RESET_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid reset token.",
        )

    now = time.time()
    if now - _last_reset_at < _MIN_INTERVAL_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Reset already ran {int(now - _last_reset_at)}s ago; wait "
                   f"{_MIN_INTERVAL_SECONDS}s between runs.",
        )

    from backend.app.core.db_bootstrap import reset_demo_database

    started = time.perf_counter()
    try:
        report = reset_demo_database()
    except Exception as exc:
        logger.exception("Demo reset failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reset failed: {exc}",
        ) from exc

    _last_reset_at = now
    report["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
    logger.info("Demo database reset: %s", report)
    return {"status": "reset", **report}
