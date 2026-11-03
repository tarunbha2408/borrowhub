"""Reporting / database-explorer API.

This module powers the "Data Studio" page of the frontend:

* a dashboard with the row count of every table in the schema,
* full-table listings rendered as an HTML table (and as XML),
* aggregation, filtering, sub-query / correlated sub-query and join queries
  built from dropdown selections,
* a controlled UPDATE form,
* the two-table reporting view plus the view-trigger demonstration.

Every identifier that can reach SQL comes from a whitelist defined in this
module; user supplied values are always passed as bound parameters, so the
endpoints cannot be used for SQL injection.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.dependencies.auth import get_current_admin, get_current_user
from backend.app.models.user import AppUser

router = APIRouter(prefix="/explorer", tags=["Data Studio & Reports"])

# ---------------------------------------------------------------------------
# Whitelists
# ---------------------------------------------------------------------------

TABLE_COLUMNS: Dict[str, List[str]] = {
    "app_user": ["user_id", "roll_number", "full_name", "svnit_email", "phone",
                 "hostel_or_dept", "role", "is_verified", "is_active", "created_at"],
    "item": ["item_id", "owner_id", "category_id", "location_id", "title", "description",
             "item_condition", "deposit_amount", "daily_fee", "max_borrow_days",
             "listing_status", "created_at"],
    "category": ["category_id", "category_name", "category_description"],
    "pickup_location": ["location_id", "name", "description"],
    "item_image": ["image_id", "item_id", "image_url", "sort_order", "is_primary"],
    "favorite": ["user_id", "item_id", "created_at"],
    "borrow_request": ["request_id", "item_id", "borrower_id", "start_date", "end_date",
                       "status", "requested_at", "decided_at", "decision_note"],
    "booked_date": ["item_id", "booked_date", "request_id"],
    "loan": ["loan_id", "request_id", "status", "issued_at", "due_at", "returned_at",
             "agreed_daily_fee", "agreed_deposit", "agreed_total_fee", "late_fee",
             "deposit_status", "deposit_deducted"],
    "payment": ["payment_id", "loan_id", "payer_id", "payee_id", "payment_type",
                "method", "payment_status", "amount", "confirmed_by_user_id", "paid_at"],
    "review": ["review_id", "loan_id", "reviewer_id", "reviewee_id", "rating",
               "review_text", "created_at"],
    "dispute": ["dispute_id", "loan_id", "raised_by", "against_user_id", "dispute_type",
                "status", "description", "amount_claimed", "amount_awarded", "created_at"],
    "notification": ["notif_id", "user_id", "type", "title", "message", "is_read", "created_at"],
    "application_audit_log": ["log_id", "actor_id", "action", "entity_type", "entity_id",
                              "created_at"],
    "system_job_log": ["job_run_id", "job_name", "triggered_by", "overdue_marked",
                       "requests_expired", "no_shows_expired", "tokens_purged", "ran_at"],
    "auth_token": ["token_id", "user_id", "token_type", "expires_at", "used_at"],
}

# Numeric columns that may be aggregated (function + column dropdown)
AGGREGATABLE: Dict[str, List[str]] = {
    "item": ["daily_fee", "deposit_amount", "max_borrow_days"],
    "loan": ["agreed_daily_fee", "agreed_deposit", "agreed_total_fee", "late_fee", "deposit_deducted"],
    "payment": ["amount"],
    "review": ["rating"],
    "dispute": ["amount_claimed", "amount_awarded"],
    "borrow_request": ["item_id"],
}

AGGREGATE_FUNCTIONS = ["COUNT", "SUM", "AVG", "MIN", "MAX"]

FILTER_OPERATORS = ["=", "!=", ">", ">=", "<", "<=", "LIKE", "IN"]

# Filterable text/number/enum columns per table (field dropdown)
FILTER_FIELDS: Dict[str, Dict[str, str]] = {
    "item": {
        "title": "text", "description": "text", "item_condition": "text",
        "listing_status": "text", "daily_fee": "number", "deposit_amount": "number",
        "max_borrow_days": "number", "category_id": "number", "location_id": "number",
    },
    "app_user": {
        "full_name": "text", "svnit_email": "text", "roll_number": "text",
        "hostel_or_dept": "text", "role": "text", "is_verified": "number",
    },
    "borrow_request": {
        "status": "text", "start_date": "date", "end_date": "date", "borrower_id": "number",
    },
    "loan": {"status": "text", "deposit_status": "text", "late_fee": "number"},
    "payment": {"payment_type": "text", "payment_status": "text", "method": "text", "amount": "number"},
    "dispute": {"status": "text", "dispute_type": "text", "amount_claimed": "number"},
}

# Direct (single hop) relations that the join builder can use
JOIN_MAP: Dict[Tuple[str, str], Tuple[str, str]] = {
    ("item", "app_user"): ("item.owner_id", "app_user.user_id"),
    ("item", "category"): ("item.category_id", "category.category_id"),
    ("item", "pickup_location"): ("item.location_id", "pickup_location.location_id"),
    ("item", "item_image"): ("item.item_id", "item_image.item_id"),
    ("item", "favorite"): ("item.item_id", "favorite.item_id"),
    ("borrow_request", "item"): ("borrow_request.item_id", "item.item_id"),
    ("borrow_request", "app_user"): ("borrow_request.borrower_id", "app_user.user_id"),
    ("borrow_request", "booked_date"): ("borrow_request.request_id", "booked_date.request_id"),
    ("loan", "borrow_request"): ("loan.request_id", "borrow_request.request_id"),
    ("payment", "loan"): ("payment.loan_id", "loan.loan_id"),
    ("review", "loan"): ("review.loan_id", "loan.loan_id"),
    ("review", "app_user"): ("review.reviewee_id", "app_user.user_id"),
    ("dispute", "loan"): ("dispute.loan_id", "loan.loan_id"),
    ("notification", "app_user"): ("notification.user_id", "app_user.user_id"),
}

JOIN_TYPES = ["INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "CROSS JOIN"]

# Columns the write-from-the-UI form may change (table -> column -> kind)
UPDATABLE: Dict[str, Dict[str, str]] = {
    "item": {
        "title": "text", "description": "text", "daily_fee": "money",
        "deposit_amount": "money", "max_borrow_days": "int",
        "item_condition": "enum:NEW,GOOD,FAIR,WORN,DAMAGED",
        "listing_status": "enum:ACTIVE,PAUSED,ARCHIVED",
        "category_id": "int", "location_id": "int",
    },
    "app_user": {"full_name": "text", "phone": "text", "hostel_or_dept": "text"},
    "category": {"category_name": "text", "category_description": "text"},
    "pickup_location": {"name": "text", "description": "text"},
    "borrow_request": {"decision_note": "text"},
    "loan": {"late_fee": "money"},
    "dispute": {"status": "enum:OPEN,UNDER_REVIEW,RESOLVED,REJECTED", "resolution_note": "text"},
}

PRIMARY_KEYS = {
    "app_user": "user_id", "item": "item_id", "category": "category_id",
    "pickup_location": "location_id", "borrow_request": "request_id",
    "loan": "loan_id", "payment": "payment_id", "dispute": "dispute_id",
    "review": "review_id", "notification": "notif_id",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _jsonable(value: Any) -> Any:
    from datetime import date, datetime, time
    from decimal import Decimal

    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _rows_to_payload(columns: List[str], raw_rows: List[Any], sql: str) -> Dict[str, Any]:
    rows = [[_jsonable(v) for v in row] for row in raw_rows]
    return {"columns": columns, "rows": rows, "row_count": len(rows), "sql": sql.strip()}


def _to_xml(payload: Dict[str, Any], root: str = "result") -> str:
    """Serialise a payload as XML (used by the 'View as XML' toggle)."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', f"<{root}>"]
    for row in payload["rows"]:
        lines.append("  <row>")
        for col, val in zip(payload["columns"], row):
            if val is None:
                lines.append(f"    <{col} nil=\"true\"/>")
            else:
                lines.append(f"    <{col}>{xml_escape(str(val))}</{col}>")
        lines.append("  </row>")
    lines.append(f"</{root}>")
    return "\n".join(lines)


def _maybe_xml(payload: Dict[str, Any], fmt: Optional[str], root: str = "result") -> Dict[str, Any]:
    if (fmt or "").lower() == "xml":
        payload = dict(payload)
        payload["xml"] = _to_xml(payload, root=root)
    return payload


def _run(db: Session, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
    """Execute a read-only statement, turning SQL errors into a 400 reply."""
    try:
        return db.execute(text(sql), params or {}).fetchall()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Query could not be executed: {exc}",
        )


def _require_table(table: str) -> str:
    if table not in TABLE_COLUMNS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown table '{table}'. Allowed: {', '.join(sorted(TABLE_COLUMNS))}.",
        )
    return table


# ---------------------------------------------------------------------------
# Dashboard (row count of every table)
# ---------------------------------------------------------------------------


@router.get("/dashboard")
def dashboard(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Row counts for every table plus a few headline figures."""
    counts: List[Dict[str, Any]] = []
    try:
        rows = db.execute(text("CALL sp_application_statistics()")).fetchall()
        counts = [{"table": r[0], "rows": int(r[1])} for r in rows]
    except Exception:
        db.rollback()
        for table in TABLE_COLUMNS:
            try:
                total = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0
            except Exception:
                db.rollback()
                total = 0
            counts.append({"table": table, "rows": int(total)})

    def scalar(sql: str, default: Any = 0) -> Any:
        try:
            value = db.execute(text(sql)).scalar()
            return default if value is None else value
        except Exception:
            db.rollback()
            return default

    summary = {
        "students": scalar("SELECT COUNT(*) FROM app_user WHERE role = 'STUDENT'"),
        "items_active": scalar("SELECT COUNT(*) FROM item WHERE listing_status = 'ACTIVE' AND deleted_at IS NULL"),
        "loans_in_progress": scalar("SELECT COUNT(*) FROM loan WHERE status IN ('SCHEDULED','ACTIVE','OVERDUE')"),
        "loans_completed": scalar("SELECT COUNT(*) FROM loan WHERE status = 'RETURNED'"),
        "pending_requests": scalar("SELECT COUNT(*) FROM borrow_request WHERE status = 'PENDING'"),
        "open_disputes": scalar("SELECT COUNT(*) FROM dispute WHERE status IN ('OPEN','UNDER_REVIEW')"),
        "revenue_collected": _jsonable(scalar(
            "SELECT COALESCE(SUM(amount),0) FROM payment WHERE payment_status = 'COMPLETED' "
            "AND payment_type IN ('RENTAL_FEE','LATE_FEE','DAMAGE_CHARGE','DAMAGE_DEDUCTION')")),
        "deposits_held": _jsonable(scalar(
            "SELECT COALESCE(SUM(agreed_deposit),0) FROM loan WHERE deposit_status = 'HELD'")),
        "average_rating": _jsonable(scalar("SELECT ROUND(AVG(rating), 2) FROM review")),
    }

    message = (
        f"The database currently holds {sum(c['rows'] for c in counts)} rows across "
        f"{len(counts)} tables."
    )
    return {"summary": summary, "tables": counts, "message": message}


# ---------------------------------------------------------------------------
# Full table listing  (query 1 - displayed as an HTML table / XML)
# ---------------------------------------------------------------------------


@router.get("/table/{table}")
def read_table(
    table: str,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    order_by: Optional[str] = None,
    fmt: Optional[str] = Query(None, description="json | xml"),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_table(table)
    columns = TABLE_COLUMNS[table]
    order = order_by if order_by in columns else columns[0]
    sql = f"SELECT {', '.join(columns)} FROM {table} ORDER BY {order} LIMIT :limit OFFSET :offset"
    rows = _run(db, sql, {"limit": limit, "offset": offset})
    try:
        total = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0
    except Exception:
        db.rollback()
        total = len(rows)
    payload = _rows_to_payload(columns, rows, sql)
    payload.update({"table": table, "total": int(total), "limit": limit, "offset": offset})
    return _maybe_xml(payload, fmt, root=f"{table}_rows")


# ---------------------------------------------------------------------------
# Aggregation (query 3) - function + column (+ optional grouping)
# ---------------------------------------------------------------------------


@router.get("/aggregate")
def aggregate(
    table: str,
    column: str,
    function: str,
    group_by: Optional[str] = None,
    fmt: Optional[str] = Query(None),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_table(table)
    function = function.upper()
    if function not in AGGREGATE_FUNCTIONS:
        raise HTTPException(400, f"Function must be one of {AGGREGATE_FUNCTIONS}.")
    if function != "COUNT" and column not in AGGREGATABLE.get(table, []):
        raise HTTPException(
            400,
            f"Column '{column}' is not aggregatable on '{table}'. "
            f"Allowed: {', '.join(AGGREGATABLE.get(table, [])) or 'none'}.",
        )
    if function == "COUNT" and column not in TABLE_COLUMNS[table]:
        raise HTTPException(400, f"Unknown column '{column}' for table '{table}'.")

    if group_by:
        if group_by not in TABLE_COLUMNS[table]:
            raise HTTPException(400, f"Unknown group-by column '{group_by}'.")
        sql = (f"SELECT {group_by} AS grp, {function}({column}) AS result FROM {table} "
               f"GROUP BY {group_by} ORDER BY grp")
    else:
        sql = f"SELECT {function}({column}) AS result FROM {table}"

    rows = _run(db, sql)
    columns = ["grp", "result"] if group_by else ["result"]
    payload = _rows_to_payload(columns, rows, sql)
    payload.update({"table": table, "function": function, "column": column,
                    "group_by": group_by})
    return _maybe_xml(payload, fmt, root="aggregate_result")


# ---------------------------------------------------------------------------
# Conditional filtering (query 4) - field + operator + value dropdowns
# ---------------------------------------------------------------------------


@router.get("/filter")
def filtered_read(
    table: str,
    field: str,
    operator: str,
    value: str,
    limit: int = Query(50, ge=1, le=200),
    fmt: Optional[str] = Query(None),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_table(table)
    fields = FILTER_FIELDS.get(table, {})
    if field not in fields:
        raise HTTPException(
            400,
            f"Field '{field}' is not filterable on '{table}'. "
            f"Allowed: {', '.join(fields) or 'none'}.",
        )
    operator = operator.upper() if operator.upper() in ("LIKE", "IN") else operator
    if operator not in FILTER_OPERATORS:
        raise HTTPException(400, f"Operator must be one of {FILTER_OPERATORS}.")

    column = TABLE_COLUMNS[table]
    if operator == "IN":
        parts = [v.strip() for v in value.split(",") if v.strip()]
        if not parts:
            raise HTTPException(400, "IN needs at least one comma separated value.")
        placeholders = ", ".join(f":p{i}" for i in range(len(parts)))
        where = f"{field} IN ({placeholders})"
        params: Dict[str, Any] = {f"p{i}": p for i, p in enumerate(parts)}
    else:
        kind = fields[field]
        if kind == "number":
            try:
                params = {"val": float(value)}
            except ValueError:
                raise HTTPException(400, f"'{value}' is not a number.")
        else:
            params = {"val": f"%{value}%" if operator == "LIKE" else value}
        where = f"{field} {operator} :val"

    sql = f"SELECT {', '.join(column)} FROM {table} WHERE {where} LIMIT {int(limit)}"
    rows = _run(db, sql, params)
    payload = _rows_to_payload(column, rows, sql)
    payload.update({"table": table, "field": field, "operator": operator, "value": value})
    return _maybe_xml(payload, fmt, root="filtered_rows")


# ---------------------------------------------------------------------------
# Sub-query and correlated sub-query (queries 6 and 7)
# ---------------------------------------------------------------------------

# Fallback only: the real list is read from app_user so a dropdown can never
# offer a location that no row actually has (that silently returned 0 rows).
HOSTEL_FALLBACK = ["Bhabha Bhavan", "Gajjar Bhavan", "Swami Vivekananda Bhavan",
                   "Mother Teresa Bhavan", "CSE Department", "Central Library"]


def _hostel_options(db: Session) -> List[str]:
    try:
        rows = db.execute(text(
            "SELECT DISTINCT hostel_or_dept FROM app_user "
            "WHERE hostel_or_dept IS NOT NULL AND hostel_or_dept <> '' "
            "ORDER BY hostel_or_dept"
        )).fetchall()
        values = [r[0] for r in rows]
        return values or list(HOSTEL_FALLBACK)
    except Exception:
        db.rollback()
        return list(HOSTEL_FALLBACK)


@router.get("/multi-table")
def multi_table_query(
    mode: str = Query("subquery", pattern="^(subquery|correlated)$"),
    hostel: Optional[str] = None,
    min_deposit: float = 100.0,
    fmt: Optional[str] = Query(None),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dropdown driven sub-query / correlated sub-query across two tables."""
    if mode == "subquery":
        if not hostel:
            raise HTTPException(400, "Pick a hostel for the sub-query option.")
        options = _hostel_options(db)
        if hostel not in options:
            raise HTTPException(
                400,
                f"'{hostel}' is not a campus location in the data. Choose one of: "
                + ", ".join(options) + ".",
            )
        sql = (
            "SELECT i.item_id, i.title, i.daily_fee, i.deposit_amount "
            "FROM item i "
            "WHERE i.owner_id IN ("
            "  SELECT u.user_id FROM app_user u "
            "   WHERE u.hostel_or_dept = :hostel AND u.is_verified = 1"
            ") ORDER BY i.item_id"
        )
        params = {"hostel": hostel}
        columns = ["item_id", "title", "daily_fee", "deposit_amount"]
        description = (
            f"Items whose owner lives in '{hostel}' - outer query on item, "
            "inner (non-correlated) sub-query on app_user."
        )
    else:
        sql = (
            "SELECT u.user_id, u.roll_number, u.full_name, u.hostel_or_dept "
            "FROM app_user u "
            "WHERE EXISTS ("
            "  SELECT 1 FROM item i "
            "   WHERE i.owner_id = u.user_id AND i.deposit_amount >= :min_deposit"
            ") ORDER BY u.user_id"
        )
        params = {"min_deposit": min_deposit}
        columns = ["user_id", "roll_number", "full_name", "hostel_or_dept"]
        description = (
            f"Owners who have at least one item with a deposit of Rs.{min_deposit:.0f} or "
            "more - correlated sub-query on item for every row of app_user."
        )

    rows = _run(db, sql, params)
    payload = _rows_to_payload(columns, rows, sql)
    payload.update({"mode": mode, "description": description,
                    "hostel_options": _hostel_options(db)})
    return _maybe_xml(payload, fmt, root="multi_table_rows")


# ---------------------------------------------------------------------------
# Join builder (query 5) - two table dropdowns + join type dropdown
# ---------------------------------------------------------------------------


@router.get("/join")
def join_query(
    left: str,
    right: str,
    join_type: str = "INNER JOIN",
    fmt: Optional[str] = Query(None),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_table(left)
    _require_table(right)
    join_type = (join_type or "INNER JOIN").upper().replace("_", " ")
    if join_type not in JOIN_TYPES:
        raise HTTPException(400, f"Join type must be one of {JOIN_TYPES}.")

    # Resolve the relation without swapping the tables the user picked: for a
    # LEFT/RIGHT join the side matters, so the ON clause is built from the
    # stored pair in whichever direction it was declared.
    flipped = False
    if (left, right) in JOIN_MAP:
        left_key, right_key = JOIN_MAP[(left, right)]
    elif (right, left) in JOIN_MAP:
        right_key, left_key = JOIN_MAP[(right, left)]
        flipped = True
    else:
        raise HTTPException(
            400,
            f"No direct relation between '{left}' and '{right}'. "
            "Supported pairs: " + ", ".join(f"{a} -> {b}" for a, b in JOIN_MAP),
        )

    left_cols = TABLE_COLUMNS[left][:5]
    right_cols = TABLE_COLUMNS[right][:5]
    select_list = ", ".join(
        [f"l.{c} AS {left}_{c}" for c in left_cols] +
        [f"r.{c} AS {right}_{c}" for c in right_cols]
    )
    # The relation is stored as table.column pairs; rewrite them to the
    # aliases used in this query.
    on_clause = f"l.{left_key.split('.')[1]} = r.{right_key.split('.')[1]}"
    sql = (
        f"SELECT {select_list} FROM {left} l {join_type} {right} r "
        f"ON {on_clause} ORDER BY 1 LIMIT 100"
    )
    columns = [f"{left}_{c}" for c in left_cols] + [f"{right}_{c}" for c in right_cols]

    rows = _run(db, sql)
    payload = _rows_to_payload(columns, rows, sql)
    payload.update({"left": left, "right": right, "join_type": join_type,
                    "on": on_clause, "relation_declared_as": "reversed" if flipped else "direct"})
    return _maybe_xml(payload, fmt, root="join_rows")


# ---------------------------------------------------------------------------
# Controlled update (query 8) - form driven, admin only
# ---------------------------------------------------------------------------


@router.get("/update-options")
def update_options(current_admin: AppUser = Depends(get_current_admin)):
    return {
        "tables": [
            {
                "table": table,
                "primary_key": PRIMARY_KEYS[table],
                "columns": [
                    {"name": col, "kind": kind,
                     "options": kind.split(":", 1)[1].split(",") if kind.startswith("enum:") else []}
                    for col, kind in cols.items()
                ],
            }
            for table, cols in UPDATABLE.items()
        ]
    }


@router.put("/update")
def update_record(
    table: str,
    row_id: int,
    column: str,
    value: str,
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if table not in UPDATABLE:
        raise HTTPException(400, f"Table '{table}' is not editable from Data Studio.")
    if column not in UPDATABLE[table]:
        raise HTTPException(400, f"Column '{column}' is not editable on '{table}'.")
    pk = PRIMARY_KEYS[table]
    kind = UPDATABLE[table][column]

    if kind == "int":
        try:
            bound: Any = int(value)
        except ValueError:
            raise HTTPException(400, f"'{value}' is not a whole number.")
    elif kind == "money":
        try:
            bound = float(value)
        except ValueError:
            raise HTTPException(400, f"'{value}' is not a valid amount.")
        if bound < 0:
            raise HTTPException(400, "Amount cannot be negative.")
    elif kind.startswith("enum:"):
        allowed = kind.split(":", 1)[1].split(",")
        if value not in allowed:
            raise HTTPException(400, f"Value must be one of {allowed}.")
        bound = value
    else:
        bound = value

    exists = db.execute(
        text(f"SELECT COUNT(*) FROM {table} WHERE {pk} = :rid"), {"rid": row_id}
    ).scalar()
    if not exists:
        raise HTTPException(404, f"No {table} row with {pk} = {row_id}.")

    sql = f"UPDATE {table} SET {column} = :val WHERE {pk} = :rid"
    try:
        db.execute(text(sql), {"val": bound, "rid": row_id})
        db.commit()
    except Exception as exc:
        db.rollback()
        message = str(exc)
        if "45000" in message or "restricted" in message.lower():
            raise HTTPException(400, f"Database trigger rejected the change: {message}")
        raise HTTPException(400, f"Update failed: {message}")

    rows = db.execute(
        text(f"SELECT * FROM {table} WHERE {pk} = :rid"), {"rid": row_id}
    ).fetchall()
    columns = list(rows[0]._mapping.keys()) if rows else []
    payload = _rows_to_payload(columns, rows, sql)
    payload["message"] = f"{table}.{column} updated for {pk} = {row_id}."
    return payload


# ---------------------------------------------------------------------------
# Two-table view + view trigger demonstration
# ---------------------------------------------------------------------------


@router.get("/view/{view_name}")
def read_view(
    view_name: str,
    fmt: Optional[str] = Query(None),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed = {"vw_bhabha_bhavan_items", "vw_active_items", "vw_item_availability"}
    if view_name not in allowed:
        raise HTTPException(400, f"View must be one of {sorted(allowed)}.")
    sql = f"SELECT * FROM {view_name} LIMIT 100"
    rows = _run(db, sql)
    columns = list(rows[0]._mapping.keys()) if rows else []
    payload = _rows_to_payload(columns, rows, sql)
    payload.update({"view": view_name,
                    "updatable": view_name in {"vw_bhabha_bhavan_items", "vw_active_items"}})
    return _maybe_xml(payload, fmt, root="view_rows")


@router.post("/view/{view_name}/insert")
def insert_through_view(
    view_name: str,
    owner_id: int,
    category_id: int,
    location_id: int,
    title: str,
    daily_fee: float,
    deposit_amount: float,
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Runs the stored procedure that inserts a row and displays the view."""
    if view_name not in {"vw_bhabha_bhavan_items", "vw_active_items"}:
        raise HTTPException(400, "Unsupported view.")
    try:
        rows = db.execute(
            text("CALL sp_view_operations('INSERT', :o, :c, :l, :t, :f, :d)"),
            {"o": owner_id, "c": category_id, "l": location_id,
             "t": title, "f": daily_fee, "d": deposit_amount},
        ).fetchall()
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(400, f"Stored procedure failed: {exc}")
    columns = list(rows[0]._mapping.keys()) if rows else []
    return {
        "columns": columns,
        "rows": [[_jsonable(v) for v in r] for r in rows],
        "row_count": len(rows),
        "message": "Row inserted through sp_view_operations and the view re-read.",
        "sql": "CALL sp_view_operations('INSERT', ...)",
    }


@router.post("/view/{view_name}/trigger-demo")
def trigger_demo_through_view(
    view_name: str,
    item_id: int,
    new_fee: Optional[float] = None,
    set_condition: Optional[str] = None,
    set_status: Optional[str] = None,
    current_admin: AppUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Updates a row *through the view* so the item triggers have to validate it.

    Fires trg_item_bu (validation) and trg_item_au (writes application_audit_log).
    """
    if view_name not in {"vw_bhabha_bhavan_items", "vw_active_items"}:
        raise HTTPException(400, "Unsupported view.")

    def _clean(value):
        return None if value is None or str(value).strip() == "" else value

    new_fee, set_condition, set_status = _clean(new_fee), _clean(set_condition), _clean(set_status)
    assignments, params = [], {"iid": item_id}
    if new_fee is not None:
        assignments.append("daily_fee = :fee")
        params["fee"] = new_fee
    if set_condition is not None:
        if set_condition not in ("NEW", "GOOD", "FAIR", "WORN", "DAMAGED"):
            raise HTTPException(400, "Invalid condition value.")
        assignments.append("item_condition = :cond")
        params["cond"] = set_condition
    if set_status is not None:
        if set_status not in ("ACTIVE", "PAUSED", "ARCHIVED"):
            raise HTTPException(400, "Invalid listing status.")
        assignments.append("listing_status = :stat")
        params["stat"] = set_status
    if not assignments:
        raise HTTPException(400, "Provide at least one value to update.")

    sql = f"UPDATE {view_name} SET {', '.join(assignments)} WHERE item_id = :iid"
    try:
        db.execute(text(sql), params)
        db.commit()
        outcome = "accepted"
        detail = "The BEFORE UPDATE trigger accepted the change."
    except Exception as exc:
        db.rollback()
        message = str(exc)
        outcome = "rejected"
        detail = message
        if "45000" in message or "DAMAGED" in message or "restricted" in message.lower():
            detail = f"Trigger rejected the change: {message}"

    audit = []
    try:
        rows = db.execute(text(
            "SELECT log_id, action, entity_type, entity_id, old_value, new_value, created_at "
            "FROM application_audit_log WHERE entity_type = 'item' "
            "ORDER BY log_id DESC LIMIT 3")).fetchall()
        audit = [
            {"log_id": r[0], "action": r[1], "entity_id": r[3],
             "old_value": r[4], "new_value": r[5], "created_at": _jsonable(r[6])}
            for r in rows
        ]
    except Exception:
        db.rollback()

    current = []
    try:
        rows = db.execute(text(
            f"SELECT item_id, title, item_condition, listing_status, daily_fee "
            f"FROM {view_name} WHERE item_id = :iid"), {"iid": item_id}).fetchall()
        current = [
            {"item_id": r[0], "title": r[1], "item_condition": r[2],
             "listing_status": r[3], "daily_fee": _jsonable(r[4])}
            for r in rows
        ]
    except Exception:
        db.rollback()

    return {"sql": sql, "outcome": outcome, "detail": detail,
            "view": view_name, "row_after": current, "audit_tail": audit}


# ---------------------------------------------------------------------------
# Options endpoint used to build every dropdown of the page
# ---------------------------------------------------------------------------


@router.get("/options")
def explorer_options(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {
        "tables": sorted(TABLE_COLUMNS),
        "table_columns": TABLE_COLUMNS,
        "aggregate_functions": AGGREGATE_FUNCTIONS,
        "aggregatable": AGGREGATABLE,
        "filter_operators": FILTER_OPERATORS,
        "filter_fields": FILTER_FIELDS,
        "join_types": JOIN_TYPES,
        "joins": [{"left": a, "right": b, "on": f"{a[0]} = {b[0]}"} for a, b in JOIN_MAP],
        "hostels": _hostel_options(db),
        "views": ["vw_bhabha_bhavan_items", "vw_active_items", "vw_item_availability"],
    }
