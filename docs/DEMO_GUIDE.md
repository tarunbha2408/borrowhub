# BorrowHub — 5-minute demo guide

**Live:** `https://<your-app>.onrender.com` · **Code:** `https://github.com/<you>/borrowhub`

BorrowHub is a campus resource-sharing platform: students list things they own
(calculators, books, lab kits…) and other students borrow them per day. The full
lifecycle is implemented — request → owner approval → OTP handover → active loan →
return inspection → dispute/review.

---

## 1. Sign in

The sign-in modal has **quick sign-in chips** for one-click access:

| Role | Email | Password |
|---|---|---|
| Administrator | `admin@svnit.ac.in` | `Svnit@2026!` |
| Lender / owner | `priya@coed.svnit.ac.in` | `Svnit@2026!` |
| Borrower | `aarav@coed.svnit.ac.in` | `Svnit@2026!` |
| Borrower | `u23cs001@svnit.ac.in` | `Svnit@2026!` |

> This is a demo deployment: you can also register a new account, and the verification
> OTP is displayed on screen (no mail leaves this domain). Data is **reset every night**,
> so nothing you do is permanent. Payments are simulated.

---

## 2. Student flow (2 minutes)

1. Sign in as **Priya** → **My Listings** shows two active items (calculator, drafter).
2. **Explore Items** → filters (category, hostel, price) → open an item → gallery.
3. Sign out → sign in as **Aarav** → open an item → **Request to borrow** → dates + message.
4. Back as **Priya** → **Requests** → approve and hand over the OTP → the loan becomes active.
5. On the loan page, complete the **return OTP** flow → inspection → deposit settlement → **review**.

---

## 3. Admin / evaluator side (2 minutes) — the technical marks are here

**Data Studio** (admin only) has nine cards plus the Query Lab:

| Card | What it shows |
|---|---|
| 1 Browse table | HTML and XML output for any table, with a row limit |
| 2 Aggregate / filter builder | COUNT/SUM/AVG, GROUP BY and WHERE through dropdowns |
| 3 Sub-query / correlated | hostel-wise filters, sub-query vs join |
| 4 Join two tables | both tables from dropdowns, INNER/LEFT/RIGHT via a safe allow-list |
| 5 Update a record | whitelisted columns, triggers and audit logging shown live |
| 6 Views & triggers | read a view, insert through it (updatable view + trigger), audit trail |
| 7 Login & policy | `sp_user_login_data`, password change (revokes sessions), office-hours guard |
| 8 Dashboard stats | nine metrics plus live row counts for all 25 tables |
| **Query Lab** | **any read-only SQL** — timing, `EXPLAIN` plan, indexes used, CSV export, 16 examples |

**Try this in the Query Lab:**

```sql
SELECT i.title, u.full_name AS owner, COUNT(l.loan_id) AS loans
FROM item i
JOIN app_user u ON u.user_id = i.owner_id
LEFT JOIN loan l ON l.item_id = i.item_id
GROUP BY i.item_id, i.title, u.full_name
ORDER BY loans DESC;
```

- **Run query** → rows, `statement type SELECT` and execution time in ms
- **Show plan** → `EXPLAIN` output and which index was used
- `DELETE FROM item` → **blocked** (read-only sandbox)
- `SELECT password_hash FROM app_user` → **blocked** (confidential column)

---

## 4. Technical highlights (for a viva)

- **Database:** 25 core tables, 7 views, **30 triggers**, **33 stored routines**
  (27 procedures + 6 functions), RBAC roles, audit trail.
- **Triggers:** deposit and rental calculation, listing-status automation, inspection
  enforcement, office-hours guard, audit logging.
- **Concurrency:** double-booking prevention (date overlap), transaction-safe handover.
- **Security:** bcrypt, JWT with `password_changed_at` invalidation, hashed OTPs, rate
  limiting, IDOR checks, upload magic-byte validation, five-layer Query Lab guards.
- **Performance:** indexed queries with a benchmark document
  (`docs/QUERY_PERFORMANCE_ANALYSIS.md`); one query improved by **71%** after indexing.
- **Quality:** 29 automated tests, CI on every push, Docker + PaaS deployment,
  Swagger at `/api/docs`.

Docs: `README.md`, `docs/DATABASE_DESIGN.md`, `docs/API_DOCUMENTATION.md`,
`docs/SECURITY_ASSESSMENT.md`, `docs/QUERY_PERFORMANCE_ANALYSIS.md`.
