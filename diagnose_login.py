"""
BorrowHub - login diagnostic script.

Run it from the project root (the folder that contains START_HERE.txt):

    python diagnose_login.py

The script is read-only: it changes nothing and deletes nothing. It checks the
three places a sign-in can break - the .env file, the database and the backend -
and prints the exact fix for every problem it finds.
"""

import os
import re
import sys
import json
import socket
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT, "backend")
ENV_FILE = os.path.join(BACKEND_DIR, ".env")
ROOT_ENV_FILE = os.path.join(ROOT, ".env")
DEFAULT_URL = "mysql+pymysql://root:12345@localhost:3306/borrowhub?charset=utf8mb4"
SEED_PASSWORD = "Svnit@2026!"
SEED_EMAILS = [
    "admin@svnit.ac.in",
    "u23cs001@svnit.ac.in",
    "priya@coed.svnit.ac.in",
]

problems = []
checks = []


def ok(msg, hint=""):
    checks.append(("OK  ", msg, hint))


def bad(msg, hint):
    checks.append(("FAIL", msg, hint))
    problems.append((msg, hint))


def warn(msg, hint=""):
    checks.append(("WARN", msg, hint))


def mask(url):
    return re.sub(r"://([^:@/]+):([^@]*)@", lambda m: f"://{m.group(1)}:***@", url)


def read_env_value(key):
    for path in (ENV_FILE, ROOT_ENV_FILE):
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    name, value = line.split("=", 1)
                    if name.strip() == key:
                        return value.strip().strip('"').strip("'"), path
    return None, None


# ---------------------------------------------------------------- 1. .env file
print("=" * 78)
print("1) .env file")
print("=" * 78)
if os.path.exists(ENV_FILE):
    ok(f"found backend/.env -> {ENV_FILE}")
else:
    bad(
        f"backend/.env is missing (looked in {ENV_FILE})",
        "Copy backend\\.env.example to backend\\.env. An .env file placed in the "
        "project root is ignored - it must live inside the backend folder.",
    )

if os.path.exists(ROOT_ENV_FILE) and not os.path.exists(ENV_FILE):
    warn(
        f"an .env file exists in the project root ({ROOT_ENV_FILE}) but the app only reads backend/.env",
        "Move that file to backend\\.env.",
    )

db_url, url_source = read_env_value("DATABASE_URL")
if not db_url:
    db_url = DEFAULT_URL
    warn(
        "DATABASE_URL is not set in .env - the default will be used: " + mask(DEFAULT_URL),
        "If your MySQL root password is not 12345, sign-in will return 500. "
        "Put your real DATABASE_URL in backend\\.env.",
    )
else:
    ok(f"DATABASE_URL found ({os.path.basename(url_source)}): {mask(db_url)}")

jwt_key, _ = read_env_value("JWT_SECRET_KEY")
if jwt_key and len(jwt_key) >= 32:
    ok("JWT_SECRET_KEY is set (>= 32 characters)")
elif jwt_key:
    warn(f"JWT_SECRET_KEY is short ({len(jwt_key)} characters)",
         "Use at least 32 characters, otherwise sessions break on every restart.")
else:
    warn("JWT_SECRET_KEY is not set",
         "The server generates a new random key on every restart, so old tokens become "
         "invalid. Put a stable 32+ character value in backend\\.env.")

# ------------------------------------------------------------- 2. MySQL connect
print()
print("=" * 78)
print("2) Database connection + data")
print("=" * 78)
match = re.match(r"mysql\+pymysql://([^:]+):([^@]*)@([^:/]+)(?::(\d+))?/([^?]+)", db_url)
if not match:
    bad(f"could not parse DATABASE_URL: {mask(db_url)}",
        "The format must be: mysql+pymysql://user:password@host:3306/borrowhub?charset=utf8mb4")
    conn = None
else:
    user, password, host, port, dbname = match.groups()
    port = int(port or 3306)
    try:
        import pymysql  # noqa: F401
    except ImportError:
        bad("pymysql is not installed", "pip install -r backend/requirements.txt")
        pymysql = None

    conn = None
    if "pymysql" in dir():
        try:
            import pymysql
            conn = pymysql.connect(host=host, port=port, user=user, password=password,
                                   database=dbname, connect_timeout=5)
            ok(f"connected to MySQL ({user}@{host}:{port}/{dbname})")
        except Exception as exc:
            errno = exc.args[0] if exc.args else None
            detail = str(exc)
            if errno == 1698 or "auth_socket" in detail or "unix_socket" in detail:
                bad(f"MySQL connection failed: {detail}",
                    "This is MariaDB/MySQL 'unix_socket' authentication - the root user does "
                    "not accept a password (the default on Arch and Fedora). Fix: "
                    "(1) run 'sudo mariadb < database/create_app_user.sql', "
                    "(2) set DATABASE_URL in backend\\.env to the new user: "
                    "mysql+pymysql://borrowhub:BorrowHub2026@localhost:3306/borrowhub?charset=utf8mb4 "
                    "(3) restart the server. Details: docs/TROUBLESHOOTING.md -> Fix 2b.")
            elif errno == 1045:
                bad(f"MySQL connection failed: {detail}",
                    "Wrong password. Check the user:password in DATABASE_URL inside backend\\.env "
                    "(the default root:12345 is only a placeholder). Or create a dedicated user: "
                    "sudo mariadb < database/create_app_user.sql")
            elif errno == 1049:
                bad(f"MySQL connection failed: {detail}",
                    "The database does not exist. Run CREATE DATABASE borrowhub; then apply "
                    "schema.sql and seed.sql.")
            else:
                bad(f"MySQL connection failed: {type(exc).__name__}: {exc}",
                    "1) Is the MySQL service running? (test the connection in Workbench) "
                    "2) Are the password/host/port in backend\\.env correct? "
                    "3) Is the database named exactly 'borrowhub'? - "
                    "CREATE DATABASE borrowhub; then apply schema.sql and seed.sql.")

if conn:
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM app_user")
        total = cur.fetchone()[0]
        if total == 0:
            bad("the app_user table is empty - no accounts exist",
                "database/seed.sql was not run. Run it (open the file in Workbench and execute).")
        else:
            ok(f"app_user holds {total} accounts")
    except Exception as exc:
        bad(f"could not read the app_user table: {exc}",
            "schema.sql was probably not applied completely. Re-run database/schema.sql.")

    # password hash check (the most common real cause)
    try:
        cur.execute("SELECT svnit_email, password_hash, role, is_active, is_verified, "
                    "deleted_at FROM app_user "
                    "WHERE svnit_email IN (%s, %s, %s)",
                    tuple(SEED_EMAILS))
        rows = cur.fetchall()
        import bcrypt
        if not rows:
            bad("the seed accounts (admin@svnit.ac.in etc.) are not in the database",
                "Run database/seed.sql - the demo accounts are created by that file.")
        for email, pw_hash, role, active, verified, deleted in rows:
            state = []
            if not active:
                state.append("is_active=0 (SUSPENDED)")
            if deleted:
                state.append("deleted_at set (DELETED)")
            if not verified:
                state.append("is_verified=0")
            try:
                works = bcrypt.checkpw(SEED_PASSWORD.encode(), pw_hash.encode())
            except Exception as exc:
                works = False
                state.append(f"hash could not be read ({exc})")
            if works:
                ok(f"{email}: hash matches '{SEED_PASSWORD}', role={role}"
                   + (f", {', '.join(state)}" if state else ""))
            else:
                bad(f"{email}: the password hash does not match '{SEED_PASSWORD}'",
                    "Were you using an older database? The easiest fix is to drop the "
                    "borrowhub database and re-run schema.sql + seed.sql, or reset the "
                    "password through the app's 'Forgot password' flow.")
    except Exception as exc:
        bad(f"password check could not run: {exc}", "pip install bcrypt")

    # schema completeness
    try:
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s", (dbname,))
        tables = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM information_schema.routines WHERE routine_schema=%s", (dbname,))
        routines = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema=%s", (dbname,))
        triggers = cur.fetchone()[0]
        ok(f"schema: {tables} tables, {routines} routines, {triggers} triggers")
        if tables < 20:
            bad("too few tables - schema.sql did not run completely",
                "Re-run database/schema.sql (execute the whole file in Workbench).")
        if routines < 30:
            warn(f"only {routines} routines found (33 expected) - some procedures are missing",
                 "Re-run the part of schema.sql that creates the procedures.")
        cur.execute("SHOW COLUMNS FROM app_user LIKE 'password_changed_at'")
        if not cur.fetchone():
            bad("app_user has no password_changed_at column (outdated schema)",
                "That column is new - an old dump breaks sign-in and password changes. "
                "Rebuild the database from database/schema.sql.")
    except Exception as exc:
        warn(f"schema summary unavailable: {exc}")
    cur.close()
    conn.close()

# ------------------------------------------------------------ 2b. Python setup
print()
print("=" * 78)
print("2b) Python packages")
print("=" * 78)
for module, pip_name in (("pymysql", "pymysql"), ("bcrypt", "bcrypt"), ("fastapi", "fastapi"),
                         ("sqlalchemy", "sqlalchemy"), ("jwt", "pyjwt")):
    try:
        __import__(module)
        ok(f"{pip_name} installed")
    except ImportError:
        bad(f"{pip_name} is not installed",
            "pip install -r backend/requirements.txt   (or: pip install %s)" % pip_name)

# ------------------------------------------------------ 2c. routines callable
if os.path.exists(ENV_FILE):
    print()
    print("=" * 78)
    print("2c) Stored routines")
    print("=" * 78)
    try:
        import pymysql
        m = re.match(r"mysql\+pymysql://([^:]+):([^@]*)@([^:/]+)(?::(\d+))?/([^?]+)", db_url)
        if m:
            u, pw, h, pt, dbn = m.groups()
            c2 = pymysql.connect(host=h, port=int(pt or 3306), user=u, password=pw,
                                 database=dbn, connect_timeout=5)
            cur2 = c2.cursor()
            for routine in ("sp_record_login_attempt", "sp_user_login_data", "sp_application_statistics"):
                cur2.execute("SELECT COUNT(*) FROM information_schema.routines "
                             "WHERE routine_schema=%s AND routine_name=%s", (dbn, routine))
                exists = cur2.fetchone()[0]
                if exists:
                    ok(f"routine {routine} exists")
                else:
                    bad(f"routine {routine} is missing",
                        "The routine section of schema.sql did not run completely - re-run "
                        "schema.sql (press Execute on the whole file in Workbench, not on a "
                        "single line).")
            cur2.close()
            c2.close()
    except Exception as exc:
        warn(f"routine check skipped: {exc}")

# ---------------------------------------------------------------- 3. Backend API
print()
print("=" * 78)
print("3) Backend server (http://127.0.0.1:8000)")
print("=" * 78)
BASE = "http://127.0.0.1:8000"


def http(method, path, payload=None, timeout=8):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


sock = socket.socket()
sock.settimeout(2)
try:
    sock.connect(("127.0.0.1", 8000))
    ok("port 8000 is open (the server is running)")
except Exception:
    bad("nothing is listening on port 8000 - the backend server is stopped",
        "From the project root: bash run_local.sh   (or: "
        "python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000). "
        "If you started it on another port, change BASE at the top of this script.")
finally:
    sock.close()

status, body = http("GET", "/api/health")
if status == 200:
    ok(f"/api/health -> 200 {body[:80]}")
elif status is None:
    bad(f"/api/health unreachable: {body}",
        "The server is stopped, or you are opening the wrong port.")
else:
    bad(f"/api/health -> {status}: {body[:120]}", "Check the server logs.")

status, body = http("POST", "/api/auth/login",
                    {"email": "admin@svnit.ac.in", "password": SEED_PASSWORD})
if status == 200 and "access_token" in body:
    ok("login test PASSED - got a token for admin@svnit.ac.in")
elif status == 401:
    bad("login -> 401 'Invalid SVNIT email or password'",
        "The backend is running but the database does not hold the email/password you typed. "
        "See check 2 above: was seed.sql run? Does the password hash match?")
elif status == 503:
    try:
        hint = json.loads(body).get("detail", body[:200])
    except Exception:
        hint = body[:200]
    bad(f"login -> 503 (database problem): {hint}",
        "The server already reported the database issue. Most likely the DATABASE_URL "
        "password in backend\\.env does not match your MySQL account. Fix it and RESTART "
        "the server. Guide: docs/TROUBLESHOOTING.md")
elif status == 500:
    bad(f"login -> 500 (server error): {body[:200]}",
        "This is a database or environment problem. Read the traceback in the server "
        "terminal - it is usually 'Access denied for user' (wrong password in .env) or "
        "'Table borrowhub.app_user doesn't exist' (schema.sql not applied).")
elif status is None:
    bad(f"login request failed: {body}",
        "Cannot reach the server - check the port and URL.")
else:
    bad(f"login -> {status}: {body[:200]}", "Check the server logs.")

# --------------------------------------------------------------- final summary
print()
print("=" * 78)
for tag, msg, hint in checks:
    print(f"[{tag}] {msg}")
    if hint and tag != "OK  ":
        print(f"        -> {hint}")
print("=" * 78)

if not problems:
    print("Everything looks correct. If the browser still cannot sign in:")
    print("  * open the page from http://127.0.0.1:8000 (do not double-click index.html)")
    print("  * hard-refresh with Ctrl+Shift+R (an old script.js may be cached)")
    print("  * DevTools -> Network -> check the response of /api/auth/login")
else:
    print(f"{len(problems)} problem(s) found - follow the '->' fix under each FAIL above.")
    print("Fix the first one at the top, then run the script again.")
