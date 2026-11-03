# Deployment — step by step

Each step ends with **"what you should see"**. If that is not what you see, stop and
check the *Common problems* section at the bottom.

8 steps · about 45 minutes · cost **0** (free plans only)

---

## STEP 1 — Get the latest project

1. Download **`BorrowHub_final.zip`**.
2. Extract it; you get a `proj` folder.
3. Keep a backup of the old folder and copy your settings over:

```bash
cd /path/to/your/workspace
mv proj proj_old
# extract the new zip here so the new "proj" folder is created
cd proj
cp ../proj_old/backend/.env backend/.env
```

✅ **What you should see:** `ls` lists `Dockerfile`, `render.yaml`, `Procfile`, `scripts`.

---

## STEP 2 — Run it locally once

```bash
cd /path/to/workspace/proj
bash run_local.sh
```

The script creates `.venv`, installs the dependencies and starts the server on
**http://127.0.0.1:8010** (change with `PORT=8020 bash run_local.sh`).

The terminal should print:

```
Database connected: MySQL/MariaDB 13.0.2, schema 'borrowhub'
Schema objects: 33 stored routines, 30 triggers, 32 tables
Accounts in app_user: 7
Database setup looks complete.
```

Open the site → **Sign In** → **Admin** chip.

✅ **What you should see:** the home page loads, sign-in works, `Data Studio` and
`Query Lab` appear in the navigation. Stop the server with `Ctrl + C` when done.

---

## STEP 3 — Create the GitHub repository

**3a.** Sign in at [github.com](https://github.com).

**3b.** Top-right **`+`** → **New repository** → name `borrowhub` → **Public** →
**Create repository** (do not add a README, .gitignore or licence).

**3c.** Push the code:

```bash
cd /path/to/workspace/proj
git init
git add .
git commit -m "BorrowHub - campus resource sharing platform"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/borrowhub.git
git push -u origin main
```

If Git asks for a password, use a **personal access token**
(GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) →
scope `repo`), not your account password.

**3d.** Confirm no secret was committed:

```bash
git ls-files | grep -E "\.env$|uploads/"
```

✅ **What you should see:** the command prints nothing, and
`https://github.com/YOUR_USERNAME/borrowhub` shows the files with the README rendered.

---

## STEP 4 — Create the database (Aiven, free)

Render does not provide MySQL, so a managed database is needed.

1. [aiven.io](https://aiven.io) → sign up.
2. **Create service** → **MySQL** → plan **Free** → region closest to you → **Create**.
3. Wait 2–3 minutes until the service is running.
4. **Overview → Connection information → Copy**. You get host, port, user (`avnadmin`),
   password and database (`defaultdb`).

**5. Load the schema and the seed data:**

```bash
mysql -h HOST -P PORT -u avnadmin -p defaultdb < database/schema_paas.sql
mysql -h HOST -P PORT -u avnadmin -p defaultdb < database/seed_paas.sql
```

**6. Verify:**

```bash
mysql -h HOST -P PORT -u avnadmin -p defaultdb -e "SELECT COUNT(*) FROM app_user;"
```

✅ **What you should see:** `7`.

---

## STEP 5 — Deploy on Render

1. [dashboard.render.com](https://dashboard.render.com) → sign up with GitHub.
2. **New +** → **Blueprint** → connect GitHub → select the `borrowhub` repository.
3. Render reads `render.yaml` and shows two resources: `borrowhub` (web) and
   `borrowhub-demo-reset` (cron). Press **Apply**.
4. It asks for `DATABASE_URL`. Paste one line:

```
mysql+pymysql://avnadmin:YOUR_AIVEN_PASSWORD@YOUR_HOST:PORT/defaultdb?charset=utf8mb4
```

URL-encode special characters in the password (`@` → `%40`, `#` → `%23`, `:` → `%3A`).

5. **Apply** → the build takes ~4–6 minutes.

✅ **What you should see:** the service status becomes **Live**, and **Logs** contain
`Database setup looks complete.`

---

## STEP 6 — Required settings (Environment)

Render → your service → **Environment** → add or edit these:

| Key | Value |
|---|---|
| `DEBUG` | `False` |
| `DEMO_MODE` | `true` |
| `JWT_SECRET_KEY` | see below |
| `DEMO_RESET_TOKEN` | see below |
| `CORS_ORIGINS` | `["https://YOUR-APP.onrender.com"]` |
| `PAYMENTS_SIMULATED` | `True` |

Generate the two secrets locally:

```bash
python -c "import secrets;print(secrets.token_urlsafe(48))"
python -c "import secrets;print(secrets.token_urlsafe(32))"
```

The first is `JWT_SECRET_KEY`, the second `DEMO_RESET_TOKEN`.
Use the URL Render shows at the top of the dashboard for `CORS_ORIGINS`.

**Save** → Render restarts automatically (~2 minutes).

✅ **What you should see:** the logs contain `DEMO MODE ON - public showcase deployment`.

---

## STEP 7 — Test the deployment (5 minutes)

```bash
# 1) is the service alive?
curl -s https://YOUR-APP.onrender.com/api/health
# -> "status":"healthy" and "accounts":7

# 2) does sign-in work?
curl -s -X POST https://YOUR-APP.onrender.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@svnit.ac.in","password":"Svnit@2026!"}' | head -c 80
# -> {"access_token":"eyJ...

# 3) does the reset work?
curl -s -X POST https://YOUR-APP.onrender.com/api/internal/reset-demo \
  -H "X-Demo-Reset-Token: YOUR_DEMO_RESET_TOKEN"
# -> {"status":"reset","accounts":7,...}
```

In the browser: the site loads, the Admin chip signs in, **Data Studio** cards load,
**Query Lab** runs an example with rows, timing and plan, and a student account shows items.

✅ **What you should see:** everything above works with no red errors in the console.

> The first request may take 30–60 seconds (a free instance sleeps). Open the site once
> before sharing the link.

---

## STEP 8 — Send it to the evaluator

```
Live demo : https://YOUR-APP.onrender.com
Code      : https://github.com/YOUR_USERNAME/borrowhub
Guide     : docs/DEMO_GUIDE.md (inside the repository)
```

Demo accounts:

| Role | Email | Password |
|---|---|---|
| Admin | `admin@svnit.ac.in` | `Svnit@2026!` |
| Lender | `priya@coed.svnit.ac.in` | `Svnit@2026!` |
| Borrower | `aarav@coed.svnit.ac.in` | `Svnit@2026!` |

Data is reset every night at 00:00 IST, so visitors cannot damage the demo.

---

## Common problems

| Problem | What to do |
|---|---|
| Render build fails | Copy the error from the logs |
| Sign-in returns 503 | `DATABASE_URL` is wrong — check the URL-encoded password |
| `schema_paas.sql` fails to load | Check host/port/password; try the `mysql` client or the Aiven SQL console |
| Images disappear after a restart | Configure Cloudinary (free Render instances have no disk) |
| The site takes 60 s | Free plan sleep — normal, or move to the starter plan |
| Reset returns 401 | `DEMO_RESET_TOKEN` and the header must match exactly |

More detail: `docs/DEPLOYMENT_PAAS.md`, `docs/TROUBLESHOOTING.md`.
