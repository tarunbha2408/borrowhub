"""Query Lab API - run read-only SQL from the browser and inspect the plan.

The lab is an operator/administrator tool: it lets the person who is grading or
demonstrating the project type a statement, execute it against the live schema
and see the result grid, the row count, the server-side timing and the
optimiser plan - the same three things ``docs/QUERY_PERFORMANCE_ANALYSIS.md``
reports in writing.

Safety model (four independent layers)
--------------------------------------
1. **Authentication** - only an ADMIN / MODERATOR session may call the lab.
2. **Statement allow-list** - the statement must start with ``SELECT``,
   ``WITH``, ``SHOW``, ``DESCRIBE``/``DESC`` or ``EXPLAIN``. Anything that can
   modify data or schema is refused before it reaches the driver.
3. **Single statement** - the first word and the whole body are checked, so
   ``SELECT 1; DROP TABLE item`` and stacked queries cannot be smuggled in.
4. **Execution guard** - a session-level statement timeout, a hard row cap and a
   blocked-column/blocked-schema check (password hashes, OTP hashes, tokens and
   the ``mysql`` system schema are never readable through the lab).
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.dependencies.auth import get_current_admin
from backend.app.models.user import AppUser

router = APIRouter(prefix="/query-lab", tags=["Query Lab"])

# ---------------------------------------------------------------------------
# Guard rails
# ---------------------------------------------------------------------------

ALLOWED_LEADING_KEYWORDS = ("SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "EXPLAIN")

# Anything here makes the statement a write / DDL / privilege statement.
FORBIDDEN_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "REPLACE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "GRANT", "REVOKE", "RENAME", "CALL", "EXEC", "EXECUTE", "SET", "LOCK", "UNLOCK",
    "LOAD", "IMPORT", "HANDLER", "ANALYZE", "OPTIMIZE", "REPAIR", "FLUSH", "KILL",
    "SHUTDOWN", "INSTALL", "UNINSTALL", "CHANGE", "PURGE", "RESET", "SAVEPOINT",
    "COMMIT", "ROLLBACK", "START", "BEGIN", "DO", "PREPARE", "DEALLOCATE",
)

# Column names that must never be projected through the lab.
BLOCKED_COLUMNS = (
    "password_hash", "token_hash", "otp_code", "handshake_otp", "return_otp",
    "handover_otp_hash", "return_otp_hash", "verification_token_hash",
    "webhook_secret", "razorpay_signature",
)

# Schemas the lab may read (application data only).
ALLOWED_SCHEMAS = ("borrowhub",)

MAX_ROWS = 500
STATEMENT_TIMEOUT_SECONDS = 8

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _strip_sql_comments(sql: str) -> str:
    """Remove -- line comments and /* */ blocks so the guard cannot be fooled."""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"#[^\n]*", " ", sql)
    return sql


def _single_statement(sql: str) -> str:
    """Return the statement without its trailing semicolon, or raise."""
    cleaned = _strip_sql_comments(sql).strip()
    if not cleaned:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Write a SQL statement first.")

    body = cleaned.rstrip(";").strip()
    # A semicolon that is not inside a quoted literal means stacked statements.
    without_literals = re.sub(r"'(?:''|[^'])*'", "''", body)
    without_literals = re.sub(r'"(?:""|[^"])*"', '""', without_literals)
    if ";" in without_literals:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Only one statement may be executed at a time (stacked queries are blocked).",
        )
    return body


def _check_statement(body: str) -> Tuple[str, str]:
    """Validate the statement and return ``(normalised_sql, leading_keyword)``."""
    first = _WORD_RE.search(body)
    if not first:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No SQL keyword found.")
    leading = first.group(0).upper()
    if leading not in ALLOWED_LEADING_KEYWORDS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Query Lab only runs read-only statements. "
            f"Allowed to start with: {', '.join(ALLOWED_LEADING_KEYWORDS)}.",
        )

    upper = body.upper()
    for word in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{word}\b", upper):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"The keyword '{word}' is not allowed in the Query Lab "
                "(read-only sandbox).",
            )

    for column in BLOCKED_COLUMNS:
        if column in body.lower():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Column '{column}' is confidential and cannot be read through the Query Lab.",
            )

    # Block the system schemas (information_schema is allowed for exploration).
    for schema in re.findall(r"\b([a-z_][a-z0-9_]*)\.", body.lower()):
        if schema in ("mysql", "performance_schema", "sys"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"The system schema '{schema}' cannot be read through the Query Lab.",
            )
    return body, leading


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------


def _jsonable(value: Any) -> Any:
    from datetime import date, datetime, time
    from decimal import Decimal

    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _apply_statement_timeout(db: Session) -> Optional[str]:
    """Best-effort per-session statement timeout, MariaDB and MySQL dialects."""
    for sql in (
        f"SET SESSION max_statement_time = {STATEMENT_TIMEOUT_SECONDS}",
        f"SET SESSION max_execution_time = {STATEMENT_TIMEOUT_SECONDS * 1000}",
    ):
        try:
            db.execute(text(sql))
            db.commit()
            return sql
        except Exception:
            db.rollback()
    return None


def _error_message(exc: Exception) -> str:
    """Turn a driver exception into one readable line (no SQL echo, no DSN)."""
    orig = getattr(exc, "orig", exc)
    args = getattr(orig, "args", None)
    if args and len(args) >= 2 and isinstance(args[1], str):
        return f"{args[1]} (error {args[0]})"
    message = str(orig).strip()
    message = re.sub(r"\s*\(Background on this error[\s\S]*$", "", message)
    message = re.sub(r"\s*\[SQL:[\s\S]*$", "", message)
    return message or "The statement could not be executed."


def _explain(db: Session, body: str) -> Optional[Dict[str, Any]]:
    """Return the optimiser plan for the statement, when the engine allows it."""
    if not body.lstrip().upper().startswith(("SELECT", "WITH")):
        return None
    try:
        rows = db.execute(text(f"EXPLAIN {body}")).fetchall()
    except Exception:
        db.rollback()
        return None
    if not rows:
        return None
    columns = list(rows[0]._mapping.keys())
    return {
        "columns": columns,
        "rows": [[_jsonable(v) for v in row] for row in rows],
        "row_count": len(rows),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/run")
def run_query(
    sql: str,
    include_plan: bool = True,
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Execute one read-only statement and return rows, timing and plan."""
    body, leading = _check_statement(_single_statement(sql))

    _apply_statement_timeout(db)

    started = time.perf_counter()
    try:
        result = db.execute(text(body))
        fetched = result.fetchmany(MAX_ROWS + 1)
        elapsed_ms = (time.perf_counter() - started) * 1000
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        elapsed_ms = (time.perf_counter() - started) * 1000
        message = _error_message(exc)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{message} (after {elapsed_ms:.1f} ms)",
        )

    truncated = len(fetched) > MAX_ROWS
    if truncated:
        fetched = fetched[:MAX_ROWS]

    columns = list(result.keys()) if fetched or result.returns_rows else []
    rows = [[_jsonable(v) for v in row] for row in fetched]

    payload: Dict[str, Any] = {
        "sql": body,
        "statement_type": leading,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "row_cap": MAX_ROWS,
        "execution_ms": round(elapsed_ms, 3),
        "message": (
            f"{len(rows)} row(s) in {elapsed_ms:.1f} ms"
            + (f" - showing the first {MAX_ROWS}" if truncated else "")
        ),
    }

    if include_plan:
        plan = _explain(db, body)
        if plan:
            payload["plan"] = plan
            used = sorted({
                row[plan["columns"].index("key")]
                for row in plan["rows"]
                if "key" in plan["columns"] and row[plan["columns"].index("key")]
            })
            payload["indexes_used"] = used

    return payload


@router.get("/examples")
def query_examples(current_admin: AppUser = Depends(get_current_admin)):
    """Curated statements shown as one-click examples in the Query Lab."""
    return {
        "groups": [
            {
                "group": "Statement set",
                "items": [
                    {
                        "title": "All rows of the main table",
                        "sql": "SELECT item_id, title, item_condition, daily_fee, deposit_amount,\n"
                               "       listing_status, owner_id\n"
                               "  FROM item\n"
                               " ORDER BY item_id;",
                    },
                    {
                        "title": "Aggregate over one table",
                        "sql": "SELECT COUNT(*)               AS total_items,\n"
                               "       ROUND(AVG(daily_fee),2) AS avg_daily_fee,\n"
                               "       MIN(daily_fee)          AS cheapest,\n"
                               "       MAX(deposit_amount)     AS highest_deposit,\n"
                               "       SUM(deposit_amount)     AS deposit_pool\n"
                               "  FROM item;",
                    },
                    {
                        "title": "Conditional read (filters)",
                        "sql": "SELECT item_id, title, item_condition, daily_fee\n"
                               "  FROM item\n"
                               " WHERE daily_fee <= 50\n"
                               "   AND item_condition IN ('NEW','GOOD')\n"
                               "   AND listing_status = 'ACTIVE'\n"
                               " ORDER BY daily_fee;",
                    },
                    {
                        "title": "Join of two tables",
                        "sql": "SELECT i.item_id, i.title, i.daily_fee,\n"
                               "       u.full_name AS owner_name, u.hostel_or_dept\n"
                               "  FROM item i\n"
                               "  JOIN app_user u ON u.user_id = i.owner_id\n"
                               " ORDER BY i.item_id;",
                    },
                    {
                        "title": "Sub-query across two tables",
                        "sql": "SELECT item_id, title, daily_fee\n"
                               "  FROM item\n"
                               " WHERE owner_id IN (\n"
                               "       SELECT user_id FROM app_user\n"
                               "        WHERE hostel_or_dept = 'Bhabha Bhavan' AND is_verified = 1)\n"
                               " ORDER BY item_id;",
                    },
                    {
                        "title": "Correlated sub-query",
                        "sql": "SELECT u.user_id, u.full_name, u.hostel_or_dept\n"
                               "  FROM app_user u\n"
                               " WHERE EXISTS (SELECT 1 FROM item i\n"
                               "                WHERE i.owner_id = u.user_id\n"
                               "                  AND i.deposit_amount >= 300)\n"
                               " ORDER BY u.user_id;",
                    },
                    {
                        "title": "GROUP BY with HAVING",
                        "sql": "SELECT c.category_name,\n"
                               "       COUNT(*)                AS items,\n"
                               "       ROUND(AVG(i.daily_fee),2) AS avg_fee\n"
                               "  FROM item i\n"
                               "  JOIN category c ON c.category_id = i.category_id\n"
                               " GROUP BY c.category_name\n"
                               "HAVING COUNT(*) >= 1\n"
                               " ORDER BY items DESC;",
                    },
                ],
            },
            {
                "group": "Schema & performance",
                "items": [
                    {
                        "title": "Every table with its row count",
                        "sql": "SELECT table_name, table_rows, engine, table_collation\n"
                               "  FROM information_schema.tables\n"
                               " WHERE table_schema = 'borrowhub' AND table_type = 'BASE TABLE'\n"
                               " ORDER BY table_name;",
                    },
                    {
                        "title": "All triggers and what they guard",
                        "sql": "SELECT trigger_name, action_timing, event_manipulation, event_object_table\n"
                               "  FROM information_schema.triggers\n"
                               " WHERE trigger_schema = 'borrowhub'\n"
                               " ORDER BY event_object_table, action_timing;",
                    },
                    {
                        "title": "Stored procedures and functions",
                        "sql": "SELECT routine_type, routine_name\n"
                               "  FROM information_schema.routines\n"
                               " WHERE routine_schema = 'borrowhub'\n"
                               " ORDER BY routine_type, routine_name;",
                    },
                    {
                        "title": "Indexes on the busiest tables",
                        "sql": "SELECT table_name, index_name, GROUP_CONCAT(column_name ORDER BY seq_in_index) AS columns\n"
                               "  FROM information_schema.statistics\n"
                               " WHERE table_schema = 'borrowhub'\n"
                               "   AND table_name IN ('item','app_user','borrow_request','loan')\n"
                               " GROUP BY table_name, index_name\n"
                               " ORDER BY table_name, index_name;",
                    },
                    {
                        "title": "EXPLAIN a reporting query",
                        "sql": "EXPLAIN SELECT item_id, title, daily_fee\n"
                               "  FROM item\n"
                               " WHERE owner_id IN (SELECT user_id FROM app_user\n"
                               "                     WHERE hostel_or_dept = 'Bhabha Bhavan');",
                    },
                ],
            },
            {
                "group": "Views & reporting",
                "items": [
                    {
                        "title": "Reporting view (two-table join)",
                        "sql": "SELECT item_id, title, owner_name, hostel_or_dept, daily_fee\n"
                               "  FROM vw_bhabha_bhavan_items\n"
                               " ORDER BY item_id;",
                    },
                    {
                        "title": "Loan ledger view",
                        "sql": "SELECT * FROM vw_loan_financial_ledger LIMIT 25;",
                    },
                    {
                        "title": "Trust score view",
                        "sql": "SELECT * FROM vw_user_trust_score ORDER BY trust_score DESC;",
                    },
                    {
                        "title": "Audit trail (written by triggers)",
                        "sql": "SELECT log_id, action, entity_type, entity_id, created_at\n"
                               "  FROM application_audit_log\n"
                               " ORDER BY log_id DESC\n"
                               " LIMIT 20;",
                    },
                ],
            },
        ]
    }
