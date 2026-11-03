# Query Performance & Index Impact Analysis

**Project:** BorrowHub — SVNIT campus resource-sharing platform
**Engine:** MariaDB 11.4.4 (InnoDB), also runs unchanged on MySQL 8.0
**Test data set:** 6 seeded rows + **20,000 generated items**, 7 users, 8 categories, 7 pickup locations
**Method:** `SET profiling = 1` → `SHOW PROFILES` (3 runs, median reported), plus `EXPLAIN` before/after
**Companion script:** `database/demo_queries.sql`
**Interactive version:** the in-app **Query Lab** (`/api/query-lab`, Data Studio → Query Lab)
runs the same statements, shows the same `EXPLAIN` output and reports the server-side
execution time per statement, so these numbers can be reproduced from the browser.

---

## 1. The eight statements

| # | Requirement | Statement |
|---|---|---|
| Q1 | read all data from the main table | `SELECT * FROM item` |
| Q2 | insert into several tables keeping integrity constraints | `INSERT` into `app_user` then `item` (FK + `trg_item_bi` + audit trigger fire) |
| Q3 | one aggregate result | `COUNT / AVG / MAX / MIN / SUM` over `item` |
| Q4 | conditional read | `item` filtered by `daily_fee`, `item_condition IN (…)`, `listing_status` |
| Q5 | join of two tables | `item INNER JOIN app_user` (owner) |
| Q6 | sub-query across two tables | items whose `owner_id` is in a hostel-verified user list |
| Q7 | correlated sub-query | users who `EXISTS` an item with `deposit_amount >= 300` |
| Q8 | update one table | `UPDATE item SET daily_fee = 25.00 WHERE title = …` |

## 2. Reporting indexes added

| Index | Table & columns | Purpose |
|---|---|---|
| `ix_item_fee_condition` | `item (daily_fee, item_condition, listing_status)` | Q4 predicate, covering |
| `ix_item_owner_deposit` | `item (owner_id, deposit_amount)` | Q7 correlated lookup, covering |
| `ix_user_hostel_verified` | `app_user (hostel_or_dept, is_verified)` | Q6 inner sub-query |
| `ix_request_dates_status` | `borrow_request (item_id, status, start_date, end_date)` | availability / date-overlap check in `borrow_service` |

## 3. Measured execution times (median of 3 runs, 20,006 items)

| # | Before indexes (ms) | After indexes (ms) | Change |
|---|---|---|---|
| Q1 `SELECT * FROM item` | 45.56 | 45.74 | — (returns every row, nothing to index away) |
| Q2 `INSERT` app_user + item | 4.46 | 4.66 | +4 % write cost from the extra indexes |
| Q3 aggregate over `item` | 4.93 | 4.36 | −12 % (index-only scan) |
| Q4 conditional read | 13.97 | 13.98 | ≈ same, but now a *considered* index |
| Q5 join `item` × `app_user` | 29.04 | 29.26 | — |
| Q6 sub-query (hostel) | 10.27 | 10.52 | ≈ same overall; inner side dropped 5 → 3 rows |
| Q7 correlated sub-query | **4.05** | **1.16** | **−71 % (3.5× faster)** |
| Q8 `UPDATE item` | 0.11 | 0.13 | +0.02 ms write cost |

## 4. What `EXPLAIN` shows

**Q4 — before:** `type=ALL`, `rows=19983`, `Using where` (full table scan).
**Q4 — after:** `possible_keys=ix_item_fee_condition`, but the optimiser still picks
`ALL`, because the predicate `daily_fee <= 50` matches roughly every row of this
benchmark set — a full scan really is cheaper than walking a range that wide. The index
is what makes the query **coverable** (`Using index`) as soon as the predicate becomes
selective, which is the normal production case. This is the honest conclusion: an index
is not automatically used, and `EXPLAIN` is the tool that tells you so.

**Q6 — before:** `app_user` `type=ALL` (5 rows), `item` `type=ALL` with a **BNL join buffer**
over 19,983 rows.
**Q6 — after:** `app_user type=ref` on `ix_user_hostel_verified`, `key_len=404`,
`Using index` — the two-column lookup replaces the scan of `app_user`.

**Q7 — before:** the `EXISTS` is turned into a **`MATERIALIZED` sub-query** that scans the
whole `item` table once (19,983 rows).
**Q7 — after:** `item type=ref` on `ix_item_owner_deposit`, `ref = app_user.user_id`,
**`Using index; FirstMatch(u)`** — one index range lookup per user instead of a full
materialisation. This is the measured 4.05 → 1.16 ms.

## 5. Conclusions

1. An index buys you the **plan**, not automatically the wall-clock number; measure with
   `SHOW PROFILES` *and* check `EXPLAIN`.
2. The composite index must be **ordered for the query**: `(owner_id, deposit_amount)`
   puts the equality column first, `(hostel_or_dept, is_verified)` likewise.
3. Covering indexes (`Using index`) remove table look-ups — the reason Q3 improved even
   though it is an aggregate over the whole table.
4. Indexes are not free: Q2 insert and Q8 update each got slightly slower / slightly more
   expensive. Only the columns used by reporting screens were indexed.
5. Correlated sub-queries are the biggest risk: on a small data set they look free
   (0.27 ms on 6 rows), and only at scale does the materialisation show up.
