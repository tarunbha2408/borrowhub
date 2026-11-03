# Deployment — public demo on a PaaS (step by step)

Goal: **a public link that feels like a real site, but cannot be broken by visitors.**

**Stack:** Render (web service) + Aiven MySQL (managed) + optional Cloudinary.
No server administration — everything happens in dashboards.

> First-time setup: ~40–60 minutes. After that, every update is `git push` = auto deploy.

---

## 0. What makes the demo break-proof

| Risk | How this setup handles it |
|---|---|
| A visitor creates accounts / listings / borrow requests and the data becomes junk | **Nightly reset** (`scripts/reset_demo.py`, Render cron) — the database returns to its seeded state every night |
| Someone signs in as admin and deletes records | The nightly reset restores everything; you can also trigger it manually at any time |
| A real payment is triggered | `DEMO_MODE=true` → payments are **always simulated**, even if live keys are pasted by mistake |
| Login/registration spam | Built-in rate limiter (per IP, 100 requests/min on auth) + Cloudflare in front (optional) |
| Uploads fill the disk | 5 MB limit + magic-byte validation; the reset also clears the upload directory |
| Tracebacks or database details leak | `DEBUG=False` → generic message to the user, details in the server log only |
| Secrets leak into the repository | `.env` is never committed (`.gitignore`); PaaS injects them as environment variables |
| Someone runs a write query through the console | Query Lab is admin-only and read-only; everything else is parameterised ORM |
| The site goes down | `/api/health` health check; Render restarts the service on failure |

The important one is the **reset**: whatever a visitor does, the demo returns to a clean
state, and every evaluator sees the same seeded accounts and items.

---

## 1. Create the database (Aiven MySQL — free plan)

Render does not offer managed MySQL, so a separate managed database is required.

1. [aiven.io](https://aiven.io) → sign up → **Create service** → **MySQL** → plan **Free**
   → region **Singapore** (or the closest one) → Create.
2. When the service is running, open **Overview → Connection information** and copy:
   - Host, Port, User (`avnadmin`), Password, Database (`defaultdb`)
3. Build the URL (URL-encode the password):

```env
DATABASE_URL=mysql+pymysql://avnadmin:YOUR_PASSWORD@mysql-xxxx.aivencloud.com:12345/defaultdb?charset=utf8mb4
```

Aiven enforces TLS. If your client requires the CA certificate, download it from the
service page, save it as `backend/certs/aiven-ca.pem`, and extend the URL:

```env
DATABASE_URL=mysql+pymysql://avnadmin:PASS@host:port/defaultdb?charset=utf8mb4&ssl_ca=backend/certs/aiven-ca.pem
```

4. **Load the schema and the seed data** (the PaaS variant has no `DROP DATABASE`/`GRANT`):

```bash
mysql -h HOST -P PORT -u avnadmin -p --ssl-mode=REQUIRED defaultdb < database/schema_paas.sql
mysql -h HOST -P PORT -u avnadmin -p --ssl-mode=REQUIRED defaultdb < database/seed_paas.sql
```

Verify in the Aiven SQL console:

```sql
SELECT COUNT(*) FROM app_user;   -- 7
SELECT COUNT(*) FROM item;       -- 6
```

> Railway MySQL works too (add the plugin, `DATABASE_URL` is generated). Load the same
> two files against it.

---

## 2. Publish the repository

```bash
cd proj
git init
git add .
git commit -m "BorrowHub: campus resource sharing platform"
git branch -M main
git remote add origin https://github.com/<username>/borrowhub.git
git push -u origin main
```

The repository already contains: `README.md` (architecture, screenshots), `docs/`
(database design, API, security, performance, deployment), `LICENSE`, `.gitignore`,
`.github/workflows/ci.yml` (26+ tests on every push), `Dockerfile`, `render.yaml`.

**Check before pushing:**

```bash
git status --short | grep -i "\.env$"      # should print nothing
git ls-files | grep -E "\.env$|uploads/"   # should print nothing
```

---

## 3. Deploy on Render

**Option A — Blueprint (recommended, `render.yaml` is in the repo)**

1. [dashboard.render.com](https://dashboard.render.com) → **New +** → **Blueprint** → select the repository.
2. Render reads `render.yaml` and creates a web service plus a nightly cron job.
3. Fill in the variables marked `sync: false`:
   - `DATABASE_URL` → the Aiven URL
4. **Apply** → build (~3–5 minutes) → deploy.

**Option B — Manual**

1. **New +** → **Web Service** → repository → runtime **Docker**.
2. Environment variables (from `.env.production.example`):

```
ENVIRONMENT=production
DEBUG=False
DATABASE_URL=mysql+pymysql://avnadmin:PASS@host:port/defaultdb?charset=utf8mb4
JWT_SECRET_KEY=<48 random characters>
DEMO_MODE=true
DEMO_RESET_TOKEN=<32 random characters>
CORS_ORIGINS=["https://borrowhub.onrender.com"]
PAYMENTS_SIMULATED=True
UPLOAD_DIR=/var/data/uploads
```

3. **Disk** → add a disk → mount path `/var/data`, 1 GB (for uploads).
4. Health check path: `/api/health`.

**Free plan note:** a free instance sleeps after 15 minutes of inactivity, so the first
request takes 30–60 seconds. Open the site once before sending the link (a warm-up), or
use the starter plan ($7/month). Free instances have no disk — configure **Cloudinary**
for uploads, otherwise images disappear on restart.

---

## 4. Generate the secrets

```bash
python -c "import secrets;print('JWT_SECRET_KEY =', secrets.token_urlsafe(48))"
python -c "import secrets;print('DEMO_RESET_TOKEN =', secrets.token_urlsafe(32))"
```

Paste them into the Render dashboard → Environment. **Never into the repository.**

---

## 5. Schedule the nightly reset

**Render cron (already defined in the blueprint):**
`render.yaml` → `type: cron`, schedule `30 18 * * *` (18:30 UTC = 00:00 IST),
command `python scripts/reset_demo.py`.

**Manual reset (any time):**

```bash
curl -X POST https://your-app.onrender.com/api/internal/reset-demo \
     -H "X-Demo-Reset-Token: $DEMO_RESET_TOKEN"
```

Response: `{"status":"reset","tables":32,"routines":33,"triggers":30,"accounts":7,"items":6,...}`

**External free cron (if the Render cron plan is not available):**
[cron-job.org](https://cron-job.org) → daily at 00:00 IST → method POST → that URL →
custom header `X-Demo-Reset-Token`.

> The endpoint runs at most once every 5 minutes; without the token it returns `401`, and
> if no token is configured it returns `404`.

---

## 6. Post-deployment checklist (5 minutes)

```bash
BASE=https://your-app.onrender.com

curl -s $BASE/api/health
# {"status":"healthy", ..., "database":{"connected":true,"accounts":7}}

curl -s -o /dev/null -w "%{http_code}\n" $BASE/            # 200 (frontend)
curl -s -o /dev/null -w "%{http_code}\n" $BASE/api/docs     # 200 (Swagger)

# sign-in
curl -s -X POST $BASE/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@svnit.ac.in","password":"Svnit@2026!"}' | head -c 90

# reset
curl -s -X POST $BASE/api/internal/reset-demo -H "X-Demo-Reset-Token: $DEMO_RESET_TOKEN" | head -c 120
```

In the browser:
1. open `$BASE` → the sign-in page appears (the welcome screen clears within 400 ms)
2. **Admin** chip → **Data Studio** → the cards load
3. **Query Lab** → pick an example → **Run query** → rows, timing and plan appear
4. Student chip (Priya) → item list, borrow request flow, OTP flow (the OTP is shown on screen in demo mode)
5. `$BASE/api/docs` → Swagger loads completely

The startup log (Render → Logs) should contain:

```
Database connected: MySQL/MariaDB 8.x, schema 'defaultdb'
Schema objects: 33 stored routines, 30 triggers, 32 tables
Accounts in app_user: 7
Database setup looks complete.
DEMO MODE ON - public showcase deployment
```

---

## 7. What to send the evaluator

`docs/DEMO_GUIDE.md` contains the demo accounts, a 5-minute tour and the feature map.
Send three lines:

```
Live demo : https://your-app.onrender.com
GitHub    : https://github.com/<username>/borrowhub
Docs      : <repo>/README.md  (+ docs/API_DOCUMENTATION.md)
```

Demo accounts (public, seeded):

| Role | Email | Password |
|---|---|---|
| Admin | `admin@svnit.ac.in` | `Svnit@2026!` |
| Lender | `priya@coed.svnit.ac.in` | `Svnit@2026!` |
| Borrower | `aarav@coed.svnit.ac.in` | `Svnit@2026!` |

---

## 8. Common PaaS problems

| Symptom | Cause | Fix |
|---|---|---|
| Deploy succeeds, sign-in returns 503 | Wrong DB URL / TLS missing | Logs show "DATABASE CONNECTION FAILED" — check the URL and `ssl_ca` |
| `Table 'defaultdb.app_user' doesn't exist` | Schema not loaded | Run `schema_paas.sql` + `seed_paas.sql` |
| `Access denied ... to database` | Managed DB gave no grants | The provider user owns its database — check the DB name in the URL |
| Images disappear after a restart | Ephemeral disk | Configure Cloudinary or mount a disk |
| First request takes 60 s | Free instance asleep | Warm-up request, or a paid plan |
| Reset returns 401 | Token mismatch | The dashboard value and the header must match exactly |
| `DEMO_RESET_TOKEN` set but 404 | Stale deployment | Redeploy / restart after saving the environment variable |

More: `docs/TROUBLESHOOTING.md`, `docs/DEPLOYMENT.md` (VPS/nginx variant).
