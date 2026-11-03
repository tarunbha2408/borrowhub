import time
from collections import defaultdict
from fastapi import HTTPException, status, Request
from backend.app.core.config import settings

# In-memory sliding window rate limiter
_request_records = defaultdict(list)


_MAX_TRACKED_KEYS = 10_000


def _prune(now: float, window_seconds: int) -> None:
    """Drop keys whose window has fully expired so the dict cannot grow forever."""
    if len(_request_records) <= _MAX_TRACKED_KEYS:
        return
    for key in [k for k, v in _request_records.items()
                if not v or now - v[-1] > window_seconds]:
        _request_records.pop(key, None)


def check_rate_limit(key: str, max_requests: int = 30, window_seconds: int = 60):
    """
    Check if a key (e.g. IP address or email) has exceeded max_requests in window_seconds.
    Raises HTTPException(429) if exceeded.
    """
    if settings.ENVIRONMENT == "test":
        return

    now = time.time()
    _prune(now, window_seconds)
    records = _request_records[key]
    _request_records[key] = [t for t in records if now - t < window_seconds]
    if len(_request_records[key]) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down and try again later.",
        )
    _request_records[key].append(now)


async def rate_limit_auth(request: Request):
    """Rate limit dependency for sensitive auth endpoints.

    The ``x-test-mode`` escape hatch is honoured only when the application is
    demonstrably not running as production; otherwise any caller could switch
    the limiter off with a single header.
    """
    if settings.ENVIRONMENT == "test":
        return
    if (request.headers.get("x-test-mode") == "true"
            and settings.ENVIRONMENT.lower() in ("test", "development", "local")):
        return
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(f"auth:{client_ip}", max_requests=100, window_seconds=60)
