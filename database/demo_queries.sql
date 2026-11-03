-- =====================================================================
-- BorrowHub - Reporting query pack & index impact analysis
-- =====================================================================
-- Run this file AFTER database/schema.sql and database/seed.sql.
--
--   mysql -u root -p < database/demo_queries.sql
--
-- It executes the eight reporting statements against the project tables,
-- measures each one, adds supporting indexes and re-measures, so the effect
-- of the indexes can be compared side by side.
-- =====================================================================

USE borrowhub;
SET profiling = 1;
SET profiling_history_size = 100;

-- ---------------------------------------------------------------------
-- SECTION 1 - THE EIGHT REPORTING STATEMENTS (before indexing)
-- ---------------------------------------------------------------------
SELECT '--- Q1: all data from the main item table ---' AS step;
SELECT * FROM item;

SELECT '--- Q2: insert into several tables keeping integrity constraints ---' AS step;
-- The owner must already be verified and active (trg_item_bi enforces it)
-- and the category/location must exist (foreign keys enforce it).
INSERT INTO app_user (roll_number, full_name, svnit_email, phone, hostel_or_dept,
                      password_hash, is_verified, is_active)
VALUES ('U24CS111', 'Karan Desai', 'u24cs111@svnit.ac.in', '9876543210',
        'Bhabha Bhavan', 'hash_karan', 1, 1)
ON DUPLICATE KEY UPDATE full_name = VALUES(full_name);

INSERT INTO item (owner_id, category_id, location_id, title, description,
                  item_condition, deposit_amount, daily_fee, max_borrow_days)
VALUES (
    (SELECT user_id       FROM app_user        WHERE roll_number  = 'U24CS111'),
    (SELECT category_id   FROM category        WHERE category_name = 'Electronics'),
    (SELECT location_id   FROM pickup_location WHERE name          = 'Bhabha Bhavan'),
    'Casio FX-991CW Scientific Calculator',
    'Non-programmable calculator for semester exams',
    'NEW', 300.00, 20.00, 5
);

SELECT '--- Q3: one aggregate result from the item table ---' AS step;
SELECT COUNT(*)             AS total_items,
       ROUND(AVG(daily_fee), 2) AS avg_daily_fee,
       MAX(deposit_amount)  AS max_deposit,
       MIN(daily_fee)       AS min_daily_fee,
       SUM(deposit_amount)  AS total_deposit_pool
  FROM item;

SELECT '--- Q4: conditional read from the item table ---' AS step;
SELECT item_id, title, item_condition, daily_fee, deposit_amount, max_borrow_days
  FROM item
 WHERE daily_fee <= 50.00
   AND item_condition IN ('NEW', 'GOOD')
   AND listing_status = 'ACTIVE';

SELECT '--- Q5: join of two tables (item + owner) ---' AS step;
SELECT i.item_id, i.title, i.daily_fee, u.full_name AS owner_name, u.hostel_or_dept
  FROM item i
  INNER JOIN app_user u ON u.user_id = i.owner_id;

SELECT '--- Q6: sub-query across two tables ---' AS step;
SELECT item_id, title, daily_fee, deposit_amount
  FROM item
 WHERE owner_id IN (SELECT user_id FROM app_user
                     WHERE hostel_or_dept = 'Bhabha Bhavan' AND is_verified = 1);

SELECT '--- Q7: correlated sub-query across two tables ---' AS step;
SELECT u.user_id, u.roll_number, u.full_name, u.hostel_or_dept
  FROM app_user u
 WHERE EXISTS (SELECT 1 FROM item i
                WHERE i.owner_id = u.user_id AND i.deposit_amount >= 300.00);

SELECT '--- Q8: update one table ---' AS step;
UPDATE item SET daily_fee = 25.00 WHERE title = 'CASIO FX-991CW SCIENTIFIC CALCULATOR';

SELECT '=== Execution times BEFORE the reporting indexes ===' AS measurement;
SHOW PROFILES;

-- ---------------------------------------------------------------------
-- SECTION 2 - SUPPORTING INDEXES
-- ---------------------------------------------------------------------
-- ix_item_fee_condition      : covers the Q4 predicate
--                              (daily_fee, item_condition, listing_status)
-- ix_user_hostel_verified    : covers the Q6 sub-query
--                              (hostel_or_dept, is_verified)
-- ix_item_owner_deposit      : covers the Q7 correlated sub-query
--                              (owner_id, deposit_amount)
-- ix_request_dates_status    : availability / overlap lookups
--                              (item_id, status, start_date, end_date)
--
-- The first three are created by database/schema.sql; they are re-declared
-- here in a guarded way so the file is safe to run on an existing install.
SET @sql := (SELECT IF(COUNT(*) = 0,
    'CREATE INDEX ix_item_fee_condition ON item (daily_fee, item_condition, listing_status)',
    'SELECT "ix_item_fee_condition already present" AS note')
  FROM information_schema.statistics
 WHERE table_schema = 'borrowhub' AND table_name = 'item'
   AND index_name = 'ix_item_fee_condition');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := (SELECT IF(COUNT(*) = 0,
    'CREATE INDEX ix_user_hostel_verified ON app_user (hostel_or_dept, is_verified)',
    'SELECT "ix_user_hostel_verified already present" AS note')
  FROM information_schema.statistics
 WHERE table_schema = 'borrowhub' AND table_name = 'app_user'
   AND index_name = 'ix_user_hostel_verified');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := (SELECT IF(COUNT(*) = 0,
    'CREATE INDEX ix_item_owner_deposit ON item (owner_id, deposit_amount)',
    'SELECT "ix_item_owner_deposit already present" AS note')
  FROM information_schema.statistics
 WHERE table_schema = 'borrowhub' AND table_name = 'item'
   AND index_name = 'ix_item_owner_deposit');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------
-- SECTION 3 - RE-MEASURE THE SAME STATEMENTS (after indexing)
-- ---------------------------------------------------------------------
SELECT '--- Q1 (after indexes) ---' AS step;
SELECT * FROM item;

SELECT '--- Q3 (after indexes) ---' AS step;
SELECT COUNT(*), ROUND(AVG(daily_fee), 2), MAX(deposit_amount), MIN(daily_fee), SUM(deposit_amount) FROM item;

SELECT '--- Q4 (after indexes) ---' AS step;
SELECT item_id, title, item_condition, daily_fee, deposit_amount
  FROM item
 WHERE daily_fee <= 50.00 AND item_condition IN ('NEW', 'GOOD') AND listing_status = 'ACTIVE';

SELECT '--- Q5 (after indexes) ---' AS step;
SELECT i.item_id, i.title, u.full_name
  FROM item i INNER JOIN app_user u ON u.user_id = i.owner_id;

SELECT '--- Q6 (after indexes) ---' AS step;
SELECT item_id, title, daily_fee FROM item
 WHERE owner_id IN (SELECT user_id FROM app_user
                     WHERE hostel_or_dept = 'Bhabha Bhavan' AND is_verified = 1);

SELECT '--- Q7 (after indexes) ---' AS step;
SELECT u.user_id, u.full_name FROM app_user u
 WHERE EXISTS (SELECT 1 FROM item i
                WHERE i.owner_id = u.user_id AND i.deposit_amount >= 300.00);

SELECT '=== Execution times AFTER the reporting indexes ===' AS measurement;
SHOW PROFILES;

-- Query plans for the three indexed predicates
SELECT '--- EXPLAIN Q4 ---' AS step;
EXPLAIN SELECT item_id FROM item
 WHERE daily_fee <= 50.00 AND item_condition IN ('NEW','GOOD') AND listing_status = 'ACTIVE';

SELECT '--- EXPLAIN Q6 ---' AS step;
EXPLAIN SELECT user_id FROM app_user
 WHERE hostel_or_dept = 'Bhabha Bhavan' AND is_verified = 1;

SELECT '--- EXPLAIN Q7 ---' AS step;
EXPLAIN SELECT 1 FROM item WHERE owner_id = 1 AND deposit_amount >= 300.00;

-- ---------------------------------------------------------------------
-- SECTION 4 - REPORTING VIEW, STORED PROCEDURE AND TRIGGER ON THE VIEW
-- ---------------------------------------------------------------------
SELECT '--- Report view: items of one hostel (item + owner) ---' AS step;
SELECT * FROM vw_bhabha_bhavan_items;

SELECT '--- Insert through the stored procedure, then read the view ---' AS step;
CALL sp_view_operations('INSERT', 1, 2, 1, 'Digital Multimeter Fluke', 30.00, 400.00);

SELECT '--- Accepted update through the view (audit trigger writes a row) ---' AS step;
UPDATE vw_active_items SET daily_fee = 35.00 WHERE item_id = 1;
SELECT log_id, action, entity_type, entity_id, old_value, new_value, created_at
  FROM application_audit_log
 WHERE entity_type = 'item'
 ORDER BY log_id DESC LIMIT 1;

SELECT '--- Rejected update through the view (BEFORE trigger blocks it) ---' AS step;
-- A damaged item may not stay ACTIVE, so the statement below raises
-- SQLSTATE 45000. Run it on its own to see the error message:
--
--   UPDATE vw_active_items SET item_condition = 'DAMAGED', listing_status = 'ACTIVE'
--    WHERE item_id = 1;
--
-- Expected: ERROR 1644 (45000): Cannot set listing_status to ACTIVE while
--           item_condition is DAMAGED.

-- ---------------------------------------------------------------------
-- SECTION 5 - APPLICATION STATISTICS (dashboard source)
-- ---------------------------------------------------------------------
SELECT '--- Row count of every table ---' AS step;
CALL sp_application_statistics();

SET profiling = 0;
