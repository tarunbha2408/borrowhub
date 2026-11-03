"""Pytest fixtures for the BorrowHub integration suite.

The suite talks to a **real MySQL/MariaDB server**, because the project's
business rules live in triggers and stored procedures that an SQLite stand-in
could never reproduce.

Earlier the suite pointed at the development database, so running the tests
deleted and archived rows of the database the application was using. Every test
run therefore now happens against a throw-away database (``borrowhub_test`` by
default) that is rebuilt from ``database/schema.sql`` and ``database/seed.sql``
at the start of the session:

* the schema + seed files are replayed with a small DELIMITER-aware splitter,
* ``DROP DATABASE`` / ``CREATE DATABASE`` / ``USE`` are retargeted at the test
  schema, and GRANT/CREATE ROLE statements (which need super-user rights) are
  skipped, so the suite works for an ordinary application user too.

Set ``BORROWHUB_TEST_DATABASE=0`` to opt out and run against the real database.
"""
import os
import re
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

_TEST_DB_NAME = "borrowhub_test"
_USE_ISOLATED_DB = os.getenv("BORROWHUB_TEST_DATABASE", "1") not in ("0", "false", "False")

# ---------------------------------------------------------------------------
# Point the application at the test database *before* any app module is
# imported: backend.app.core.config builds its Settings object at import time.
# ---------------------------------------------------------------------------
def _configured_database_url() -> str:
    """DATABASE_URL from the environment, else from ``backend/.env``.

    ``backend.app.core.config`` builds its Settings object at import time, so
    the value has to be known *before* the first application import - reading
    the .env file directly here is the only reliable way to do that.
    """
    from os import environ

    if environ.get("DATABASE_URL"):
        return environ["DATABASE_URL"]
    env_file = _repo_root / "backend" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "mysql+pymysql://root:12345@localhost:3306/borrowhub?charset=utf8mb4"


if _USE_ISOLATED_DB:
    _base_url = _configured_database_url()
    _test_url = re.sub(r"/([A-Za-z0-9_]+)(\?|$)",
                       f"/{_TEST_DB_NAME}\\2",
                       _base_url, count=1)
    os.environ["DATABASE_URL"] = _test_url
    os.environ["BORROWHUB_RESOLVED_TEST_URL"] = _test_url

import pytest
import pymysql
from sqlalchemy.engine import make_url


# ---------------------------------------------------------------------------
# Schema bootstrap helpers
# ---------------------------------------------------------------------------


_COMPOUND_START = re.compile(
    r"^\s*CREATE\s+(OR\s+REPLACE\s+)?(DEFINER\s*=\s*\S+\s+)?"
    r"(PROCEDURE|FUNCTION|TRIGGER|EVENT)",
    re.IGNORECASE,
)


def _split_statements(sql_text: str):
    """Split a MySQL dump into statements, honouring ``DELIMITER`` directives.

    ``schema.sql`` sets ``DELIMITER $$`` before the routine block but keeps
    plain ``;``-terminated views inside that same block, which the mysql client
    tolerates. To reproduce that behaviour: a buffer that starts a compound
    statement (procedure / function / trigger / event) can only be closed by the
    custom delimiter, while anything else also closes on ``;``.
    """
    statements, buffer, delimiter = [], [], ";"
    for raw_line in sql_text.splitlines():
        stripped = raw_line.strip()
        if stripped.upper().startswith("DELIMITER "):
            delimiter = stripped.split(None, 1)[1].strip()
            continue
        if stripped.startswith("--") or stripped.startswith("#") or not stripped:
            continue
        buffer.append(raw_line)
        if not buffer:
            continue

        compound = _COMPOUND_START.match(buffer[0]) is not None
        closes = stripped.endswith(delimiter)
        if not closes and not compound and stripped.endswith(";"):
            closes = True

        if closes:
            statement = "\n".join(buffer).strip()
            for terminator in (delimiter, ";"):
                if terminator and statement.endswith(terminator):
                    statement = statement[: -len(terminator)].strip()
                    break
            if statement:
                statements.append(statement)
            buffer = []
    if buffer:
        trailing = "\n".join(buffer).strip()
        if trailing:
            statements.append(trailing)
    return statements


def _retarget(statement: str, db_name: str) -> str:
    """Point database-level statements at the test schema."""
    statement = re.sub(r"DROP\s+DATABASE\s+(IF\s+EXISTS\s+)?`?borrowhub`?",
                       f"DROP DATABASE IF EXISTS `{db_name}`", statement,
                       flags=re.IGNORECASE)
    statement = re.sub(r"CREATE\s+DATABASE\s+(IF\s+NOT\s+EXISTS\s+)?`?borrowhub`?",
                       f"CREATE DATABASE IF NOT EXISTS `{db_name}`", statement,
                       flags=re.IGNORECASE)
    statement = re.sub(r"^USE\s+`?borrowhub`?", f"USE `{db_name}`", statement,
                       flags=re.IGNORECASE)
    return statement


_SKIP = re.compile(r"^\s*(GRANT|REVOKE|CREATE\s+ROLE|DROP\s+ROLE|SET\s+DEFAULT\s+ROLE|CALL\s+sp_create_role_user)",
                   re.IGNORECASE)


def _connect(url: str, database: str | None = None):
    """Raw pymysql connection.

    The schema file contains literal ``%`` characters (the e-mail REGEXP
    constraint), and SQLAlchemy's ``exec_driver_sql`` runs every statement
    through ``cursor.execute(sql, ())`` which would interpret them as format
    specifiers. Going straight to the driver with ``args=None`` avoids that.
    """
    parsed = make_url(url)
    return pymysql.connect(
        host=parsed.host or "127.0.0.1",
        port=parsed.port or 3306,
        user=parsed.username or "root",
        password=parsed.password or "",
        database=database or parsed.database,
        charset="utf8mb4",
        autocommit=True,
    )


def _load_sql_file(url: str, path: Path, db_name: str) -> None:
    body = path.read_text(encoding="utf-8")
    skipped = 0
    connection = _connect(url, database=db_name)
    try:
        cursor = connection.cursor()
        for statement in _split_statements(body):
            if _SKIP.match(statement):
                skipped += 1
                continue
            cursor.execute(_retarget(statement, db_name))
    finally:
        connection.close()
    if skipped:
        print(f"  (skipped {skipped} privilege statement(s) while loading {path.name})")


def _database_url_without_schema(url: str) -> str:
    return re.sub(r"/([A-Za-z0-9_]+)(\?|$)", r"/\2", url, count=1)


if _USE_ISOLATED_DB:
    @pytest.fixture(scope="session", autouse=True)
    def prepared_test_database():
        """Recreate ``borrowhub_test`` from schema + seed once per session."""
        test_url = os.environ["BORROWHUB_RESOLVED_TEST_URL"]
        server_url = _database_url_without_schema(test_url)

        server = _connect(server_url)
        try:
            cur = server.cursor()
            cur.execute(f"DROP DATABASE IF EXISTS `{_TEST_DB_NAME}`")
            cur.execute(
                f"CREATE DATABASE `{_TEST_DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        finally:
            server.close()

        _load_sql_file(test_url, _repo_root / "database" / "schema.sql", _TEST_DB_NAME)
        _load_sql_file(test_url, _repo_root / "database" / "seed.sql", _TEST_DB_NAME)
        yield


from fastapi.testclient import TestClient  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.core.database import SessionLocal  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_headers_student_a(client):
    res = client.post("/api/auth/login", json={
        "email": "u23cs001@svnit.ac.in",
        "password": "Svnit@2026!"
    })
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_student_b(client):
    res = client.post("/api/auth/login", json={
        "email": "u23cs002@svnit.ac.in",
        "password": "Svnit@2026!"
    })
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_admin(client):
    res = client.post("/api/auth/login", json={
        "email": "admin@svnit.ac.in",
        "password": "Svnit@2026!"
    })
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
