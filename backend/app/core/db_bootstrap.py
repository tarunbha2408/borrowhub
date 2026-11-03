"""
Database bootstrap helpers for the public demo deployment.

The demo site is public, so visitors *can* create accounts, lists and borrow
requests - that is the point, an evaluator should get the real experience. What
must not happen is the database slowly filling up with junk or someone leaving it
broken. This module drops and rebuilds every object in the connected schema from
``database/schema_paas.sql`` + ``database/seed_paas.sql``.

Only objects inside the current database are touched; the database itself, the
MySQL users and the provider's own metadata are never dropped (that is why the
PaaS variant of the schema has no DROP/CREATE DATABASE and no GRANTs).
"""

from __future__ import annotations

import os
import re
from typing import Dict, Iterator, List, Tuple

_DELIMITER_RE = re.compile(r"^\s*DELIMITER\s+(\S+)\s*$", re.IGNORECASE)
_COMPOUND_START = re.compile(
    r"^\s*(CREATE\s+(DEFINER\s*=\s*\S+\s+)?(PROCEDURE|FUNCTION|TRIGGER|EVENT)|BEGIN\b)",
    re.IGNORECASE,
)


def _split_statements(sql_text: str) -> Iterator[str]:
    """Split a MySQL dump into statements, honouring ``DELIMITER $$`` blocks.

    Inside a custom-delimiter block only the compound objects (procedures,
    functions, triggers, events) keep the custom terminator. Views and plain
    statements that appear between two blocks still end with ``;`` - the mysql
    command-line client accepts that, a naive splitter does not.
    """
    delimiter = ";"
    buffer: List[str] = []

    def is_compound(text: str) -> bool:
        for line in text.splitlines():
            if line.strip():
                return bool(_COMPOUND_START.match(line))
        return False

    for raw_line in sql_text.splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("--") or stripped.startswith("#"):
            continue

        match = _DELIMITER_RE.match(stripped)
        if match:
            delimiter = match.group(1)
            continue

        buffer.append(line)
        joined = "\n".join(buffer).rstrip()
        if not joined:
            continue

        compound = is_compound(joined)
        closes = joined.endswith(delimiter)
        if delimiter != ";" and not compound and joined.endswith(";"):
            closes, terminator = True, ";"
        else:
            terminator = delimiter

        if not closes:
            continue

        statement = joined[: -len(terminator)].strip()
        buffer = []
        if statement:
            yield statement


def _statements_for_file(path: str) -> Iterator[str]:
    with open(path, encoding="utf-8") as handle:
        yield from _split_statements(handle.read())


def _quote(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def _drop_everything(connection) -> Dict[str, int]:
    """Remove every table/view/routine/trigger owned by the connected schema."""
    dropped = {"tables": 0, "views": 0, "routines": 0, "triggers": 0}
    with connection.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        cursor.execute(
            "SELECT table_name, table_type FROM information_schema.tables "
            "WHERE table_schema = DATABASE()"
        )
        objects = cursor.fetchall()
        for name, table_type in objects:
            if table_type == "VIEW":
                cursor.execute(f"DROP VIEW IF EXISTS {_quote(name)}")
                dropped["views"] += 1
            else:
                cursor.execute(f"DROP TABLE IF EXISTS {_quote(name)}")
                dropped["tables"] += 1

        cursor.execute(
            "SELECT routine_name, routine_type FROM information_schema.routines "
            "WHERE routine_schema = DATABASE()"
        )
        for name, routine_type in cursor.fetchall():
            cursor.execute(f"DROP {routine_type} IF EXISTS {_quote(name)}")
            dropped["routines"] += 1

        cursor.execute(
            "SELECT trigger_name FROM information_schema.triggers "
            "WHERE trigger_schema = DATABASE()"
        )
        for (name,) in cursor.fetchall():
            cursor.execute(f"DROP TRIGGER IF EXISTS {_quote(name)}")
            dropped["triggers"] += 1

        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    return dropped


def _run_file(connection, path: str, label: str) -> int:
    executed = 0
    # Raw pymysql cursor: parameters are never supplied, so '%' inside the SQL
    # (regexes, LIKE patterns) stays literal and is not treated as formatting.
    with connection.cursor() as cursor:
        for statement in _statements_for_file(path):
            lowered = statement.strip().lower()
            if lowered.startswith(("drop database", "create database", "use ", "grant",
                                   "revoke", "create user", "alter user", "flush privileges")):
                continue  # managed MySQL forbids these
            if re.match(r"^call\s+sp_create_role_user", lowered):
                continue
            try:
                cursor.execute(statement)
            except Exception as exc:  # pragma: no cover - surfaced to the caller
                raise RuntimeError(f"{label}: failed near: {statement[:160]}... ({exc})") from exc
            executed += 1
    return executed


def reset_demo_database(database_url: str | None = None) -> Dict[str, object]:
    """Drop and rebuild the demo schema + seed data. Returns a small report."""
    import pymysql

    url = database_url or os.environ.get("DATABASE_URL", "")
    match = re.match(
        r"mysql\+pymysql://([^:]+):([^@]*)@([^:/]+)(?::(\d+))?/([^?]+)", url
    )
    if not match:
        raise RuntimeError("DATABASE_URL is missing or not a mysql+pymysql URL")
    user, password, host, port, database = match.groups()
    port = int(port or 3306)

    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    schema = os.path.join(here, "database", "schema_paas.sql")
    seed = os.path.join(here, "database", "seed_paas.sql")
    for path in (schema, seed):
        if not os.path.exists(path):
            raise RuntimeError(f"required SQL file missing: {path}")

    connection = pymysql.connect(
        host=host, port=port, user=user, password=password, database=database,
        autocommit=True, connect_timeout=15,
    )
    try:
        dropped = _drop_everything(connection)
        executed = _run_file(connection, schema, "schema_paas.sql")
        executed += _run_file(connection, seed, "seed_paas.sql")

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT "
                " (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()),"
                " (SELECT COUNT(*) FROM information_schema.routines WHERE routine_schema = DATABASE()),"
                " (SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema = DATABASE()),"
                " (SELECT COUNT(*) FROM app_user),"
                " (SELECT COUNT(*) FROM item)"
            )
            tables, routines, triggers, accounts, items = cursor.fetchone()
    finally:
        connection.close()

    return {
        "dropped": dropped,
        "statements_executed": executed,
        "tables": tables,
        "routines": routines,
        "triggers": triggers,
        "accounts": accounts,
        "items": items,
    }
