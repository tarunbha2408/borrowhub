# Troubleshooting — sign-in and database problems

Run this first (from the project root, the folder that contains `START_HERE.txt`):

```bash
python diagnose_login.py
```

The script is **read-only** — it changes nothing. It checks the three places a sign-in
can break and prints the exact fix for each problem:

1. Is `.env` in the right place, and what does it say about `DATABASE_URL` / `JWT_SECRET_KEY`?
2. Does MySQL connect, do the seed accounts exist, and does the `Svnit@2026!` hash match?
3. Is the backend running, and what exactly does `POST /api/auth/login` answer?

Fix the first `FAIL` at the top, then run the script again.

---

## The six most common causes

### 1. `.env` is in the wrong place  ← most common
The application reads **`backend/.env` only**; a `.env` in the project root is ignored.

```
BorrowHub/
├── backend/
│   ├── .env          ← this one
│   └── .env.example
├── database/
└── START_HERE.txt
```

On Windows Notepad sometimes saves it as `.env.txt`. Confirm with `dir /a backend`.

**Fix:** copy `backend\.env.example` → `backend\.env` (same folder, exact name).

### 2. `DATABASE_URL` does not match your MySQL account
The default is `root:12345@localhost:3306/borrowhub`. If your root password is something
else, sign-in returns **500** and the server terminal shows
`Access denied for user 'root'@'localhost'`.

**Fix:** put your real password in `backend\.env`:

```env
DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@localhost:3306/borrowhub?charset=utf8mb4
```

If the password contains `@`, `:`, `/` or `#`, URL-encode it (`@` → `%40`, `#` → `%23`),
otherwise the URL breaks. The server must be restarted (`.env` is read at startup only).

### 2b. MariaDB `unix_socket` authentication → `Access denied` (error 1698)  ← Arch / Fedora / Ubuntu default
If `python diagnose_login.py` reports:

```
DB connect FAIL: OperationalError (1698, "Access denied for user 'root'@'localhost'")
```

then the root account does not accept a password at all — it uses the `unix_socket`
plugin. Create a dedicated user for the application:

```bash
sudo mariadb < database/create_app_user.sql
```

(interactive: `sudo mariadb` → `SOURCE database/create_app_user.sql;`)

That file runs:

```sql
CREATE USER IF NOT EXISTS 'borrowhub'@'localhost' IDENTIFIED BY 'BorrowHub2026';
CREATE DATABASE IF NOT EXISTS borrowhub CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON borrowhub.* TO 'borrowhub'@'localhost';
FLUSH PRIVILEGES;
```

Then set this in `backend/.env` and **restart the server**:

```env
DATABASE_URL=mysql+pymysql://borrowhub:BorrowHub2026@localhost:3306/borrowhub?charset=utf8mb4
```

Verify:

```bash
mariadb -u borrowhub -pBorrowHub2026 borrowhub -e "SELECT COUNT(*) FROM app_user;"   # 7
```

`ALL PRIVILEGES ON borrowhub.*` includes `TRIGGER`, `EXECUTE` and `CREATE ROUTINE`, so
the whole application works with that account.

### 2c. Tables were created in UPPERCASE → `Table 'borrowhub.app_user' doesn't exist`
If `sudo mariadb -e "USE borrowhub; SHOW TABLES;"` shows names like:

```
| APP_USER |
| ITEM     |
| LOAN     |
```

then an **older release of `schema.sql`** was applied. It created UPPERCASE identifiers,
and table names are **case-sensitive on Linux**, so the application's lowercase
`FROM app_user` fails — sign-in returns 500 and the terminal shows
`Table 'borrowhub.app_user' doesn't exist`.

**How to recognise it:** that older schema had only 25 tables + 5 views, and `app_user`
had no `password_changed_at` column.

**Fix:** apply the current `schema.sql` + `seed.sql`:

```bash
bash database/setup_database.sh          # schema + seed + application user, in one go
```

or manually:

```bash
sudo mariadb -e "SOURCE database/schema.sql"
sudo mariadb -e "SOURCE database/seed.sql"
sudo mariadb -e "USE borrowhub; SHOW TABLES;"     # should now be lowercase
```

The application also detects this at startup and says so explicitly:
`table 'app_user' exists as 'APP_USER' (UPPERCASE) - that comes from an older schema.sql ...`

### 3. `seed.sql` was not run → no accounts at all
The schema exists but no users do → sign-in returns **401 "Invalid SVNIT email or password"**.

In MySQL Workbench: open `database/seed.sql` → ⚡ Execute (on the whole file).
Verify: `SELECT COUNT(*) FROM app_user;` → **7**.

### 4. An old dump was applied (`password_changed_at` missing)
An older dump has no `password_changed_at` column, so sign-in and password changes return 500.

**Fix:** rebuild the database:

```sql
DROP DATABASE IF EXISTS borrowhub;
CREATE DATABASE borrowhub CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

then apply `database/schema.sql` → `database/seed.sql`.

### 5. The page is not served by the backend
Opening `index.html` by double-click (or through VS Code Live Server) sends `/api/...`
calls somewhere else → "Network error" / "Failed to fetch" on sign-in.

**Fix:** open the page from **http://localhost:8000** (the same server `uvicorn` runs).

### 6. `schema.sql` did not run completely in Workbench (DELIMITER handling)
`schema.sql` contains 33 stored routines and 30 triggers. Execute the whole file in one go
("Execute (All or selection)"); the result grid showing only the last statement's output is
normal. Check:

```sql
SELECT COUNT(*) FROM information_schema.routines WHERE routine_schema='borrowhub';  -- 33
SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema='borrowhub';  -- 30
SELECT COUNT(*) FROM information_schema.tables   WHERE table_schema='borrowhub';    -- 32
```

If the numbers are lower:

```sql
SOURCE C:\path\to\BorrowHub\database\schema.sql;
```

or from the command line: `mysql -u root -p borrowhub < database/schema.sql`

---

## Demo accounts (created by `seed.sql`)

| Role | Email | Password |
|---|---|---|
| Administrator | `admin@svnit.ac.in` | `Svnit@2026!` |
| Owner / lender | `priya@coed.svnit.ac.in` | `Svnit@2026!` |
| Borrower | `aarav@coed.svnit.ac.in` | `Svnit@2026!` |
| Borrower | `u23cs001@svnit.ac.in` | `Svnit@2026!` |

The password is case-sensitive: `Svnit@2026!` — capital S, an `@`, and a `!` at the end.
The sign-in modal also has **quick sign-in chips** (Priya / Aarav / Rohit / Admin). If a
chip works but typing the password does not, the problem is the typing, not the app.

---

## What each status code means

| Status | Meaning | Where to look |
|---|---|---|
| **401** Invalid email or password | Server is fine, the database has no matching email/password | Was seed.sql run? Email spelling? Password case? |
| **403** Account suspended | `is_active = 0` | `UPDATE app_user SET is_active=1 WHERE svnit_email='...';` |
| **500** | Database connection or outdated schema | Traceback in the server terminal |
| **503** "Database unavailable: ..." | The app names the exact database problem (password / missing database / outdated schema / MySQL down) | Fix what the message says, restart |
| **Network error / Failed to fetch** | Backend stopped, or the page came from the wrong URL | port 8000 and `http://localhost:8000` |

Changing `.env` **requires a server restart** — settings are read at startup, and even a
`--reload` server does not pick up `.env` changes on its own.

Do not close the server terminal: the full traceback of a failed sign-in is printed there.

---

## Still stuck?

Send these three things — they identify the cause exactly:

1. the full output of `python diagnose_login.py`
2. Browser DevTools → **Network** → the `login` request → **Response** tab
3. the part of the server terminal printed during the sign-in attempt (if it shows an error)
