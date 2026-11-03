import os
import sys
from pathlib import Path

# Ensure repository root is on sys.path
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from backend.app.core.config import settings
from backend.app.core.database import Base, engine
import backend.app.models  # ensure models are registered
from backend.app.routes import (
    auth, items, borrow, loans, payments,
    notifications, reviews, disputes, admin, upload, explorer, query_lab, internal
)

logger = logging.getLogger("borrowhub.startup")

# database/schema.sql is the single source of truth for tables, triggers,
# routines and views. Automatic table creation is opt-in only, because a
# mismatch between an ORM table name and the SQL name would silently create a
# second empty table and hide every existing row.
if settings.AUTO_CREATE_TABLES:
    Base.metadata.create_all(bind=engine)

_STARTUP_REQUIRED_COLUMNS = {
    "app_user": ("user_id", "svnit_email", "password_hash", "password_changed_at", "deleted_at"),
    "item": ("item_id", "owner_id", "listing_status", "deleted_at"),
}


def _startup_database_check() -> None:
    """Print one clear, actionable block about the database state at boot.

    The application deliberately starts even when the database is unusable (so
    the UI and /api/health still respond), but it must say out loud *why* every
    database-backed call will fail instead of leaving opaque 500s behind.
    """
    from sqlalchemy import inspect

    try:
        with engine.connect() as conn:
            server = conn.execute(text("SELECT VERSION()")).scalar()
            database = conn.execute(text("SELECT DATABASE()")).scalar()
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - startup diagnostics
        logger.error("=" * 78)
        logger.error("DATABASE CONNECTION FAILED - every database-backed API call will fail.")
        logger.error("  reason : %s", exc)
        logger.error("  url    : %s", settings.masked_database_url)
        logger.error("  fix    : 1) Is the MySQL/MariaDB service running?")
        logger.error("           2) Are the user/password/host/port in backend/.env correct?")
        logger.error("           3) Does the database exist and has schema.sql been applied?")
        logger.error("  guide  : docs/TROUBLESHOOTING.md  |  python diagnose_login.py")
        logger.error("=" * 78)
        return

    logger.info("Database connected: MySQL/MariaDB %s, schema '%s'", server.split("-")[0], database)

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    # Table names are case-sensitive on Linux. Older releases of schema.sql
    # created UPPERCASE identifiers, which makes the application's lowercase
    # queries fail with "Table 'borrowhub.app_user' doesn't exist" - so that
    # specific situation is reported explicitly instead of as "missing".
    lower_map = {name.lower(): name for name in existing}
    problems = []
    for table, columns in _STARTUP_REQUIRED_COLUMNS.items():
        if table not in existing:
            stored_as = lower_map.get(table)
            if stored_as:
                problems.append(
                    f"table '{table}' exists as '{stored_as}' (UPPERCASE) - that comes from an "
                    "older schema.sql; table names are case-sensitive on Linux. "
                    "Re-apply the current database/schema.sql."
                )
            else:
                problems.append(f"table '{table}' missing")
            continue
        present = {c["name"] for c in inspector.get_columns(table)}
        missing = [c for c in columns if c not in present]
        if missing:
            problems.append(f"table '{table}' missing columns: {', '.join(missing)} "
                            "(outdated schema - re-apply database/schema.sql)")

    try:
        with engine.connect() as conn:
            routines = conn.execute(text(
                "SELECT routine_type, COUNT(*) FROM information_schema.routines "
                "WHERE routine_schema = DATABASE() GROUP BY routine_type"
            )).all()
            triggers = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema = DATABASE()"
            )).scalar()
            conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.routines "
                "WHERE routine_schema = DATABASE() AND routine_name = 'sp_record_login_attempt'"
            )).scalar()
        counts = {row[0]: row[1] for row in routines}
        logger.info("Schema objects: %s stored routines, %s triggers, %s tables",
                    sum(counts.values()), triggers, len(existing))
        if not counts.get("PROCEDURE"):
            problems.append("stored procedures missing (the routine section of schema.sql did not run)")
        if not triggers:
            problems.append("triggers missing (the trigger section of schema.sql did not run)")
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not inspect routines/triggers: %s", exc)

    try:
        with engine.connect() as conn:
            users = conn.execute(text("SELECT COUNT(*) FROM app_user")).scalar()
        if not users:
            problems.append("app_user is empty - run database/seed.sql (it creates the demo accounts)")
        else:
            logger.info("Accounts in app_user: %s", users)
    except Exception as exc:  # pragma: no cover
        problems.append(f"app_user read failed: {exc}")

    if problems:
        logger.error("=" * 78)
        logger.error("DATABASE SETUP IS INCOMPLETE - sign-in and API calls will fail:")
        for item in problems:
            logger.error("  - %s", item)
        logger.error("  fix: run database/schema.sql, then database/seed.sql (both).")
        logger.error("  guide: docs/TROUBLESHOOTING.md  |  python diagnose_login.py")
        logger.error("=" * 78)
    else:
        logger.info("Database setup looks complete.")

    if settings.DEMO_MODE:
        logger.info("=" * 78)
        logger.info("DEMO MODE ON - public showcase deployment")
        logger.info("  * payments are simulated (no real money can move)")
        logger.info("  * e-mail OTPs are returned to the browser (no SMTP on this domain)")
        logger.info("  * scheduled reset: POST /api/internal/reset-demo %s",
                    "(enabled)" if settings.DEMO_RESET_TOKEN else "(DISABLED - set DEMO_RESET_TOKEN)")
        logger.info("=" * 78)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Verify the database once on startup (replaces the deprecated on_event)."""
    _startup_database_check()
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.PROJECT_NAME,
    description="BorrowHub – Complete Full-Stack Campus Resource Sharing Platform for SVNIT Surat",
    version=settings.VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Configure CORS (including allow_private_network for direct local file testing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_private_network=True,
)

# Prevent browser from caching static assets during development
@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/uploads"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Static files for uploaded images
static_uploads = settings.UPLOAD_DIR
os.makedirs(static_uploads, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=static_uploads), name="uploads")

# Mount API routers
app.include_router(auth.router, prefix="/api")
app.include_router(items.router, prefix="/api")
app.include_router(borrow.router, prefix="/api")
app.include_router(loans.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(disputes.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(explorer.router, prefix="/api")
app.include_router(query_lab.router, prefix="/api")
app.include_router(internal.router, prefix="/api")


# ---------------------------------------------------------------------------
# Error surfacing
# A broken database must never reach the browser as a bare "Internal Server
# Error" - developers lose hours on it. These handlers turn the common
# infrastructure failures into one actionable sentence.
# ---------------------------------------------------------------------------
from fastapi.responses import JSONResponse  # noqa: E402
from sqlalchemy.exc import OperationalError, ProgrammingError  # noqa: E402


def _database_hint(exc: Exception) -> str:
    text_error = str(getattr(exc, "orig", exc))
    lowered = text_error.lower()
    if "access denied" in lowered:
        return ("MySQL refused the login. Check the user/password in DATABASE_URL "
                "inside backend/.env (the placeholder is root:12345).")
    if "unknown database" in lowered:
        return ("The database does not exist. Run CREATE DATABASE borrowhub; then apply "
                "database/schema.sql and database/seed.sql.")
    if "can't connect" in lowered or "connection refused" in lowered or "timed out" in lowered:
        return ("Could not reach the MySQL server. Is the MySQL/MariaDB service running? "
                "Are the host and port in backend/.env correct?")
    if "unknown column" in lowered:
        return ("The database schema is outdated (a column is missing). Re-apply database/schema.sql.")
    if "doesn't exist" in lowered or "does not exist" in lowered:
        return ("A table is missing - apply the full database/schema.sql (including the stored routines).")
    if "no module named 'pymysql'" in lowered:
        return "pymysql is not installed: pip install -r backend/requirements.txt"
    if "execute command denied" in lowered:
        return ("The MySQL user may not execute routines/triggers. Grant EXECUTE on the "
                "schema or connect with a user that has it.")
    return "Database error - see the traceback in the server terminal (docs/TROUBLESHOOTING.md)."


@app.exception_handler(OperationalError)
@app.exception_handler(ProgrammingError)
async def database_error_handler(request, exc):  # pragma: no cover - error path
    hint = _database_hint(exc)
    logger.error("Database error on %s %s -> %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={"detail": f"Database unavailable: {hint}", "error_type": type(exc).__name__},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request, exc):  # pragma: no cover - error path
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    content = {"detail": "Internal server error. See the traceback in the server terminal."}
    if settings.DEBUG:
        # Development keeps the real reason so the browser shows something useful.
        content["detail"] = f"{type(exc).__name__}: {exc}"
        content["hint"] = _database_hint(exc)
    return JSONResponse(status_code=500, content=content)


@app.get("/api/health", tags=["Health"])
def health_check():
    """Liveness + a quick database readiness signal."""
    database = {"connected": False}
    try:
        with engine.connect() as conn:
            database = {
                "connected": True,
                "database": conn.execute(text("SELECT DATABASE()")).scalar(),
                "accounts": conn.execute(text("SELECT COUNT(*) FROM app_user")).scalar(),
            }
    except Exception as exc:  # pragma: no cover
        database = {"connected": False, "hint": _database_hint(exc)}
    return {
        "status": "healthy" if database["connected"] else "degraded",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "version": settings.VERSION,
        "database": database,
    }


# Mount frontend static directory if present
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
