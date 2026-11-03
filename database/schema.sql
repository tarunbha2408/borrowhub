-- =====================================================================
-- BorrowHub - Master Production Schema (MySQL 8.0.16+ / InnoDB)
-- All 23 Triggers, 9 Workflow Procedures, 5 Views & E2E Test Suite
-- =====================================================================

DROP DATABASE IF EXISTS borrowhub;
CREATE DATABASE borrowhub
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
USE borrowhub;
SET NAMES utf8mb4;
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';

-- =====================================================================
-- 1. TABLES
-- =====================================================================

-- ---- Identity & Auth ------------------------------------------------
CREATE TABLE app_user (
    user_id        INT AUTO_INCREMENT PRIMARY KEY,
    roll_number    VARCHAR(30)  NOT NULL,
    full_name      VARCHAR(120) NOT NULL,
    svnit_email    VARCHAR(254) NOT NULL,
    phone          VARCHAR(20)  NULL,
    hostel_or_dept VARCHAR(100) NULL,
    password_hash  VARCHAR(255) NOT NULL,
    role           ENUM('STUDENT','MODERATOR','ADMIN') NOT NULL DEFAULT 'STUDENT',
    is_verified    TINYINT(1)   NOT NULL DEFAULT 0,
    is_active      TINYINT(1)   NOT NULL DEFAULT 1,
    created_at     DATETIME     NOT NULL DEFAULT (UTC_TIMESTAMP()),
    updated_at     DATETIME     NOT NULL DEFAULT (UTC_TIMESTAMP()),
    -- Set whenever the password changes. Any JWT issued before this moment is
    -- rejected, so a password change really does end every other session
    -- (the tokens themselves are stateless, so the check lives here).
    password_changed_at DATETIME NULL,
    deleted_at     DATETIME     NULL,
    CONSTRAINT uq_user_roll  UNIQUE (roll_number),
    CONSTRAINT uq_user_email UNIQUE (svnit_email),
    CONSTRAINT chk_user_verified CHECK (is_verified IN (0, 1)),
    CONSTRAINT chk_user_active   CHECK (is_active IN (0, 1)),
    CONSTRAINT chk_user_email_domain
        CHECK (svnit_email REGEXP '^[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\\.)*svnit\\.ac\\.in$')
) ENGINE=InnoDB;

CREATE TABLE auth_token (
    token_id   BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT         NOT NULL,
    token_type ENUM('EMAIL_OTP','PASSWORD_RESET','REFRESH') NOT NULL,
    token_hash CHAR(64)    NOT NULL,
    expires_at DATETIME    NOT NULL,
    used_at    DATETIME    NULL,
    created_at DATETIME    NOT NULL DEFAULT (UTC_TIMESTAMP()),
    CONSTRAINT fk_auth_token_user FOREIGN KEY (user_id) REFERENCES app_user(user_id)
      ON DELETE CASCADE,
    INDEX ix_auth_token_lookup (user_id, token_type, expires_at),
    INDEX ix_auth_token_hash   (token_hash)
) ENGINE=InnoDB;

CREATE TABLE device_token (
    device_id    INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT          NOT NULL,
    platform     ENUM('ANDROID','IOS','WEB') NOT NULL,
    push_token   VARCHAR(512) NOT NULL,
    is_active    TINYINT(1)   NOT NULL DEFAULT 1,
    last_seen_at DATETIME     NULL,
    created_at   DATETIME     NOT NULL DEFAULT (UTC_TIMESTAMP()),
    CONSTRAINT fk_device_user FOREIGN KEY (user_id) REFERENCES app_user(user_id)
      ON DELETE CASCADE,
    CONSTRAINT uq_device_push_token UNIQUE (push_token),
    CONSTRAINT chk_device_active CHECK (is_active IN (0, 1)),
    INDEX ix_device_user (user_id, is_active)
) ENGINE=InnoDB;

-- ---- Catalogue ------------------------------------------------------
CREATE TABLE category (
    category_id          INT AUTO_INCREMENT PRIMARY KEY,
    category_name        VARCHAR(80) NOT NULL,
    category_description TEXT        NULL,
    CONSTRAINT uq_category_name UNIQUE (category_name)
) ENGINE=InnoDB;

CREATE TABLE pickup_location (
    location_id INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    description VARCHAR(255) NULL,
    CONSTRAINT uq_pickup_location_name UNIQUE (name)
) ENGINE=InnoDB;

CREATE TABLE item (
    item_id         INT AUTO_INCREMENT PRIMARY KEY,
    owner_id        INT           NOT NULL,
    category_id     INT           NOT NULL,
    location_id     INT           NOT NULL,
    title           VARCHAR(160)  NOT NULL,
    description     TEXT          NULL,
    item_condition  ENUM('NEW','GOOD','FAIR','WORN','DAMAGED') NOT NULL DEFAULT 'GOOD',
    deposit_amount  DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    daily_fee       DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    max_borrow_days INT           NOT NULL DEFAULT 1,
    listing_status  ENUM('ACTIVE','PAUSED','ARCHIVED') NOT NULL DEFAULT 'ACTIVE',
    created_at      DATETIME      NOT NULL DEFAULT (UTC_TIMESTAMP()),
    updated_at      DATETIME      NOT NULL DEFAULT (UTC_TIMESTAMP()),
    deleted_at      DATETIME      NULL,
    CONSTRAINT fk_item_owner    FOREIGN KEY (owner_id)    REFERENCES app_user(user_id)            ON DELETE RESTRICT,
    CONSTRAINT fk_item_category FOREIGN KEY (category_id) REFERENCES category(category_id)        ON DELETE RESTRICT,
    CONSTRAINT fk_item_location FOREIGN KEY (location_id) REFERENCES pickup_location(location_id) ON DELETE RESTRICT,
    CONSTRAINT chk_item_deposit   CHECK (deposit_amount >= 0),
    CONSTRAINT chk_item_daily_fee CHECK (daily_fee >= 0),
    CONSTRAINT chk_item_max_days  CHECK (max_borrow_days BETWEEN 1 AND 365),
    INDEX ix_item_owner    (owner_id, listing_status),
    INDEX ix_item_category (category_id, listing_status),
    INDEX ix_item_location (location_id),
    FULLTEXT INDEX ft_item_search (title, description)
) ENGINE=InnoDB;

CREATE TABLE item_image (
    image_id    INT AUTO_INCREMENT PRIMARY KEY,
    item_id     INT               NOT NULL,
    image_url   VARCHAR(2048)     NOT NULL,
    sort_order  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    is_primary  TINYINT(1)        NOT NULL DEFAULT 0,
    uploaded_at DATETIME          NOT NULL DEFAULT (UTC_TIMESTAMP()),
    CONSTRAINT fk_item_image_item FOREIGN KEY (item_id) REFERENCES item(item_id)
      ON DELETE CASCADE,
    CONSTRAINT chk_item_image_primary CHECK (is_primary IN (0, 1)),
    INDEX ix_item_image_item (item_id, sort_order)
) ENGINE=InnoDB;

CREATE TABLE favorite (
    user_id    INT      NOT NULL,
    item_id    INT      NOT NULL,
    created_at DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
    PRIMARY KEY (user_id, item_id),
    CONSTRAINT fk_favorite_user FOREIGN KEY (user_id) REFERENCES app_user(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_favorite_item FOREIGN KEY (item_id) REFERENCES item(item_id)     ON DELETE CASCADE,
    INDEX ix_favorite_item (item_id)
) ENGINE=InnoDB;

-- ---- Requests, Bookings & Loans -------------------------------------
CREATE TABLE borrow_request (
    request_id      INT AUTO_INCREMENT PRIMARY KEY,
    item_id         INT      NOT NULL,
    borrower_id     INT      NOT NULL,
    start_date      DATE     NOT NULL,
    end_date        DATE     NOT NULL,
    request_message TEXT     NULL,
    status          ENUM('PENDING','APPROVED','REJECTED','CANCELLED') NOT NULL DEFAULT 'PENDING',
    requested_at    DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
    decided_at      DATETIME NULL,
    decision_note   TEXT     NULL,
    CONSTRAINT fk_request_item     FOREIGN KEY (item_id)     REFERENCES item(item_id)     ON DELETE RESTRICT,
    CONSTRAINT fk_request_borrower FOREIGN KEY (borrower_id) REFERENCES app_user(user_id) ON DELETE RESTRICT,
    CONSTRAINT chk_request_dates CHECK (end_date >= start_date),
    INDEX ix_request_item_status   (item_id, status),
    INDEX ix_request_item_dates    (item_id, start_date, end_date),
    INDEX ix_request_borrower_time (borrower_id, requested_at)
) ENGINE=InnoDB;

CREATE TABLE booked_date (
    item_id     INT  NOT NULL,
    booked_date DATE NOT NULL,
    request_id  INT  NOT NULL,
    PRIMARY KEY (item_id, booked_date),
    CONSTRAINT fk_booked_item    FOREIGN KEY (item_id)    REFERENCES item(item_id)              ON DELETE RESTRICT,
    CONSTRAINT fk_booked_request FOREIGN KEY (request_id) REFERENCES borrow_request(request_id) ON DELETE CASCADE,
    INDEX ix_booked_request (request_id)
) ENGINE=InnoDB;

CREATE TABLE loan (
    loan_id            INT AUTO_INCREMENT PRIMARY KEY,
    request_id         INT           NOT NULL,
    status             ENUM('SCHEDULED','ACTIVE','OVERDUE','RETURNED','CANCELLED') NOT NULL DEFAULT 'SCHEDULED',
    issued_at          DATETIME      NULL,
    due_at             DATETIME      NOT NULL,
    returned_at        DATETIME      NULL,
    agreed_daily_fee   DECIMAL(10,2) NOT NULL,
    agreed_deposit     DECIMAL(10,2) NOT NULL,
    agreed_total_fee   DECIMAL(10,2) NOT NULL,
    late_fee           DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    deposit_status     ENUM('NOT_PAID','HELD','RELEASED','FORFEITED','PARTIAL') NOT NULL DEFAULT 'NOT_PAID',
    deposit_deducted   DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    handover_otp_hash  CHAR(64)      NOT NULL,
    return_otp_hash    CHAR(64)      NOT NULL,
    created_at         DATETIME      NOT NULL DEFAULT (UTC_TIMESTAMP()),
    CONSTRAINT fk_loan_request   FOREIGN KEY (request_id) REFERENCES borrow_request(request_id) ON DELETE RESTRICT,
    CONSTRAINT uq_loan_request   UNIQUE (request_id),
    CONSTRAINT chk_loan_amounts  CHECK (agreed_daily_fee >= 0 AND agreed_deposit >= 0 AND agreed_total_fee >= 0
                                        AND late_fee >= 0 AND deposit_deducted >= 0),
    CONSTRAINT chk_loan_deducted CHECK (deposit_deducted <= agreed_deposit),
    CONSTRAINT chk_loan_times    CHECK (returned_at IS NULL OR issued_at IS NULL OR returned_at >= issued_at),
    INDEX ix_loan_status_due (status, due_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS temporary_otp (
    otp_id     INT AUTO_INCREMENT PRIMARY KEY,
    loan_id    INT         NOT NULL,
    stage      VARCHAR(20) NOT NULL,
    otp_code   VARCHAR(10) NOT NULL,
    expires_at DATETIME    NOT NULL,
    created_at DATETIME    NOT NULL DEFAULT (UTC_TIMESTAMP()),
    CONSTRAINT fk_temp_otp_loan FOREIGN KEY (loan_id) REFERENCES loan(loan_id) ON DELETE CASCADE,
    INDEX ix_temp_otp_loan_stage (loan_id, stage)
) ENGINE=InnoDB;

-- ---- Payments & Provider Webhooks -----------------------------------
CREATE TABLE payment (
    payment_id            INT AUTO_INCREMENT PRIMARY KEY,
    loan_id               INT           NOT NULL,
    payer_id              INT           NOT NULL,
    payee_id              INT           NOT NULL,
    payment_type          ENUM('RENTAL_FEE','DEPOSIT','LATE_FEE','DAMAGE_CHARGE','DAMAGE_DEDUCTION','REFUND') NOT NULL,
    method                ENUM('UPI','CARD','CASH') NOT NULL,
    payment_status        ENUM('PENDING','COMPLETED','FAILED') NOT NULL DEFAULT 'PENDING',
    amount                DECIMAL(10,2) NOT NULL,
    refund_for_payment_id INT           NULL,
    refund_reason         ENUM('CANCELLED_LOAN','DEPOSIT_SETTLEMENT','DISPUTE_AWARD','OVERPAYMENT') NULL,
    confirmed_by_user_id  INT           NULL,
    gateway_order_id      VARCHAR(100)  NULL,
    transaction_reference VARCHAR(160)  NULL,
    idempotency_key       VARCHAR(100)  NULL,
    created_at            DATETIME      NOT NULL DEFAULT (UTC_TIMESTAMP()),
    paid_at               DATETIME      NULL,
    CONSTRAINT fk_payment_loan      FOREIGN KEY (loan_id)              REFERENCES loan(loan_id)     ON DELETE RESTRICT,
    CONSTRAINT fk_payment_payer     FOREIGN KEY (payer_id)             REFERENCES app_user(user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_payment_payee     FOREIGN KEY (payee_id)             REFERENCES app_user(user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_payment_confirmer FOREIGN KEY (confirmed_by_user_id) REFERENCES app_user(user_id) ON DELETE RESTRICT,
    CONSTRAINT chk_payment_amount   CHECK (amount > 0),
    CONSTRAINT chk_payment_parties  CHECK (payer_id <> payee_id),
    CONSTRAINT chk_payment_refund_link CHECK (
        (payment_type = 'REFUND' AND refund_for_payment_id IS NOT NULL AND refund_reason IS NOT NULL)
        OR (payment_type <> 'REFUND' AND refund_for_payment_id IS NULL AND refund_reason IS NULL)
    ),
    CONSTRAINT uq_payment_txn  UNIQUE (transaction_reference),
    CONSTRAINT uq_payment_idem UNIQUE (idempotency_key),
    INDEX ix_payment_loan_status   (loan_id, payment_status),
    INDEX ix_payment_refund_source (refund_for_payment_id, payment_status),
    INDEX ix_payment_gateway_order (gateway_order_id)
) ENGINE=InnoDB;

ALTER TABLE payment
  ADD CONSTRAINT fk_payment_refund_src
  FOREIGN KEY (refund_for_payment_id) REFERENCES payment(payment_id)
  ON DELETE RESTRICT;

CREATE TABLE payment_webhook_event (
    event_id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    payment_id            INT           NOT NULL,
    gateway_event_id      VARCHAR(160)  NOT NULL,
    event_type            ENUM('PAYMENT_CAPTURED','PAYMENT_FAILED','REFUND_PROCESSED') NOT NULL,
    amount_reported       DECIMAL(10,2) NOT NULL,
    transaction_reference VARCHAR(160)  NOT NULL,
    signature_verified    TINYINT(1)    NOT NULL DEFAULT 0,
    event_status          ENUM('RECEIVED','VERIFIED','REJECTED') NOT NULL DEFAULT 'RECEIVED',
    payload               JSON          NOT NULL,
    received_at           DATETIME      NOT NULL DEFAULT (UTC_TIMESTAMP()),
    processed_at          DATETIME      NULL,
    CONSTRAINT fk_webhook_payment FOREIGN KEY (payment_id) REFERENCES payment(payment_id) ON DELETE RESTRICT,
    CONSTRAINT uq_webhook_event   UNIQUE (gateway_event_id),
    CONSTRAINT chk_webhook_sig    CHECK (signature_verified IN (0, 1)),
    CONSTRAINT chk_webhook_amt    CHECK (amount_reported > 0),
    INDEX ix_webhook_payment_verified (payment_id, event_status, signature_verified)
) ENGINE=InnoDB;

-- ---- Trust: Reviews & Two-Party Independent Inspections -------------
CREATE TABLE review (
    review_id   INT AUTO_INCREMENT PRIMARY KEY,
    loan_id     INT              NOT NULL,
    reviewer_id INT              NOT NULL,
    reviewee_id INT              NOT NULL,
    rating      TINYINT UNSIGNED NOT NULL,
    review_text TEXT             NULL,
    created_at  DATETIME         NOT NULL DEFAULT (UTC_TIMESTAMP()),
    CONSTRAINT fk_review_loan     FOREIGN KEY (loan_id)     REFERENCES loan(loan_id)     ON DELETE RESTRICT,
    CONSTRAINT fk_review_reviewer FOREIGN KEY (reviewer_id) REFERENCES app_user(user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_review_reviewee FOREIGN KEY (reviewee_id) REFERENCES app_user(user_id) ON DELETE RESTRICT,
    CONSTRAINT chk_review_rating   CHECK (rating BETWEEN 1 AND 5),
    CONSTRAINT chk_review_not_self CHECK (reviewer_id <> reviewee_id),
    CONSTRAINT uq_review_one_per_reviewer_per_loan UNIQUE (loan_id, reviewer_id),
    INDEX ix_review_reviewee (reviewee_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE loan_inspection (
    inspection_id      INT AUTO_INCREMENT PRIMARY KEY,
    loan_id            INT         NOT NULL,
    stage              ENUM('HANDOVER','RETURN') NOT NULL,
    inspected_by       INT         NOT NULL,
    confirmed_by       INT         NULL,
    condition_found    ENUM('NEW','GOOD','FAIR','WORN','DAMAGED') NOT NULL,
    notes              TEXT        NULL,
    counterparty_notes TEXT        NULL,
    owner_agreed       TINYINT(1)  NOT NULL DEFAULT 0,
    owner_agreed_at    DATETIME    NULL,
    borrower_agreed    TINYINT(1)  NOT NULL DEFAULT 0,
    borrower_agreed_at DATETIME    NULL,
    provided_otp_hash  CHAR(64)    NULL,
    otp_verified       TINYINT(1)  NOT NULL DEFAULT 0,
    inspection_status  ENUM('PENDING_COUNTERPARTY','VERIFIED','DISPUTED') NOT NULL DEFAULT 'PENDING_COUNTERPARTY',
    inspected_at       DATETIME    NOT NULL DEFAULT (UTC_TIMESTAMP()),
    verified_at        DATETIME    NULL,
    CONSTRAINT fk_inspection_loan      FOREIGN KEY (loan_id)      REFERENCES loan(loan_id)     ON DELETE RESTRICT,
    CONSTRAINT fk_inspection_inspector FOREIGN KEY (inspected_by) REFERENCES app_user(user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_inspection_confirmer FOREIGN KEY (confirmed_by) REFERENCES app_user(user_id) ON DELETE RESTRICT,
    CONSTRAINT uq_inspection_stage_per_loan UNIQUE (loan_id, stage),
    CONSTRAINT chk_inspection_flags CHECK (owner_agreed IN (0, 1) AND borrower_agreed IN (0, 1) AND otp_verified IN (0, 1)),
    CONSTRAINT chk_inspection_two_party_state CHECK (
        (inspection_status = 'PENDING_COUNTERPARTY'
            AND confirmed_by IS NULL
            AND otp_verified = 0
            AND (owner_agreed + borrower_agreed = 1))
        OR
        (inspection_status = 'VERIFIED'
            AND confirmed_by IS NOT NULL
            AND confirmed_by <> inspected_by
            AND owner_agreed = 1
            AND borrower_agreed = 1
            AND otp_verified = 1
            AND provided_otp_hash IS NOT NULL)
        OR
        (inspection_status = 'DISPUTED'
            AND confirmed_by IS NOT NULL
            AND confirmed_by <> inspected_by)
    ),
    INDEX ix_inspection_inspector (inspected_by),
    INDEX ix_inspection_confirmer (confirmed_by)
) ENGINE=InnoDB;

CREATE TABLE inspection_photo (
    photo_id      INT AUTO_INCREMENT PRIMARY KEY,
    inspection_id INT           NOT NULL,
    image_url     VARCHAR(2048) NOT NULL,
    uploaded_at   DATETIME      NOT NULL DEFAULT (UTC_TIMESTAMP()),
    CONSTRAINT fk_inspection_photo_inspection FOREIGN KEY (inspection_id) REFERENCES loan_inspection(inspection_id)
      ON DELETE CASCADE,
    INDEX ix_inspection_photo_parent (inspection_id)
) ENGINE=InnoDB;

-- ---- In-App Chat ----------------------------------------------------
CREATE TABLE conversation (
    conversation_id INT AUTO_INCREMENT PRIMARY KEY,
    item_id         INT      NOT NULL,
    borrower_id     INT      NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
    last_message_at DATETIME NULL,
    CONSTRAINT fk_conversation_item     FOREIGN KEY (item_id)     REFERENCES item(item_id)     ON DELETE RESTRICT,
    CONSTRAINT fk_conversation_borrower FOREIGN KEY (borrower_id) REFERENCES app_user(user_id) ON DELETE RESTRICT,
    CONSTRAINT uq_conversation_item_borrower UNIQUE (item_id, borrower_id),
    INDEX ix_conversation_borrower (borrower_id, last_message_at)
) ENGINE=InnoDB;

CREATE TABLE message (
    message_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id INT      NOT NULL,
    sender_id       INT      NOT NULL,
    body            TEXT     NOT NULL,
    sent_at         DATETIME NOT NULL DEFAULT (UTC_TIMESTAMP()),
    read_at         DATETIME NULL,
    CONSTRAINT fk_message_conversation FOREIGN KEY (conversation_id) REFERENCES conversation(conversation_id) ON DELETE CASCADE,
    CONSTRAINT fk_message_sender       FOREIGN KEY (sender_id)       REFERENCES app_user(user_id)             ON DELETE RESTRICT,
    INDEX ix_message_conversation (conversation_id, sent_at)
) ENGINE=InnoDB;

-- ---- Disputes -------------------------------------------------------
CREATE TABLE dispute (
    dispute_id      INT AUTO_INCREMENT PRIMARY KEY,
    loan_id         INT           NOT NULL,
    raised_by       INT           NOT NULL,
    against_user_id INT           NOT NULL,
    inspection_id   INT           NULL,
    resolved_by     INT           NULL,
    dispute_type    ENUM('DAMAGE','NO_SHOW','LATE_RETURN','NON_PAYMENT','OTHER') NOT NULL,
    description     TEXT          NOT NULL,
    status          ENUM('OPEN','UNDER_REVIEW','RESOLVED','REJECTED') NOT NULL DEFAULT 'OPEN',
    amount_claimed  DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    amount_awarded  DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    resolution_note TEXT          NULL,
    created_at      DATETIME      NOT NULL DEFAULT (UTC_TIMESTAMP()),
    resolved_at     DATETIME      NULL,
    CONSTRAINT fk_dispute_loan       FOREIGN KEY (loan_id)         REFERENCES loan(loan_id)                   ON DELETE RESTRICT,
    CONSTRAINT fk_dispute_raised_by  FOREIGN KEY (raised_by)       REFERENCES app_user(user_id)               ON DELETE RESTRICT,
    CONSTRAINT fk_dispute_against    FOREIGN KEY (against_user_id) REFERENCES app_user(user_id)               ON DELETE RESTRICT,
    CONSTRAINT fk_dispute_inspection FOREIGN KEY (inspection_id)   REFERENCES loan_inspection(inspection_id) ON DELETE RESTRICT,
    CONSTRAINT fk_dispute_resolver   FOREIGN KEY (resolved_by)     REFERENCES app_user(user_id)               ON DELETE RESTRICT,
    CONSTRAINT chk_dispute_parties CHECK (raised_by <> against_user_id),
    CONSTRAINT chk_dispute_amounts CHECK (amount_claimed >= 0 AND amount_awarded >= 0 AND amount_awarded <= amount_claimed),
    INDEX ix_dispute_loan   (loan_id),
    INDEX ix_dispute_status (status, created_at)
) ENGINE=InnoDB;

CREATE TABLE dispute_evidence (
    evidence_id INT AUTO_INCREMENT PRIMARY KEY,
    dispute_id  INT           NOT NULL,
    image_url   VARCHAR(2048) NOT NULL,
    uploaded_at DATETIME      NOT NULL DEFAULT (UTC_TIMESTAMP()),
    CONSTRAINT fk_evidence_dispute FOREIGN KEY (dispute_id) REFERENCES dispute(dispute_id) ON DELETE CASCADE,
    INDEX ix_evidence_dispute (dispute_id)
) ENGINE=InnoDB;

-- ---- Notifications, Audit & Job Execution Logs ----------------------
CREATE TABLE notification (
    notif_id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id            INT          NOT NULL,
    related_request_id INT          NULL,
    related_loan_id    INT          NULL,
    reference_type     ENUM('REQUEST','loan','payment','review','dispute','SYSTEM') NOT NULL DEFAULT 'SYSTEM',
    reference_id       BIGINT       NULL,
    type               ENUM('REQUEST_RECEIVED','REQUEST_APPROVED','REQUEST_REJECTED','REQUEST_CANCELLED',
                            'LOAN_STARTED','LOAN_OVERDUE','LOAN_RETURNED','PAYMENT_UPDATE',
                            'REVIEW_RECEIVED','DISPUTE_UPDATE','SYSTEM') NOT NULL,
    title              VARCHAR(150) NOT NULL,
    message            TEXT         NOT NULL,
    is_read            TINYINT(1)   NOT NULL DEFAULT 0,
    created_at         DATETIME     NOT NULL DEFAULT (UTC_TIMESTAMP()),
    CONSTRAINT fk_notification_user    FOREIGN KEY (user_id)            REFERENCES app_user(user_id)           ON DELETE CASCADE,
    CONSTRAINT fk_notification_request FOREIGN KEY (related_request_id) REFERENCES borrow_request(request_id) ON DELETE SET NULL,
    CONSTRAINT fk_notification_loan    FOREIGN KEY (related_loan_id)    REFERENCES loan(loan_id)               ON DELETE SET NULL,
    CONSTRAINT chk_notif_read CHECK (is_read IN (0, 1)),
    INDEX ix_notification_unread (user_id, is_read, created_at),
    INDEX ix_notification_ref    (reference_type, reference_id)
) ENGINE=InnoDB;

CREATE TABLE application_audit_log (
    log_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
    actor_id    INT         NULL,
    action      VARCHAR(60) NOT NULL,
    entity_type VARCHAR(40) NOT NULL,
    entity_id   BIGINT      NOT NULL,
    old_value   JSON        NULL,
    new_value   JSON        NULL,
    created_at  DATETIME    NOT NULL DEFAULT (UTC_TIMESTAMP()),
    CONSTRAINT fk_audit_actor FOREIGN KEY (actor_id) REFERENCES app_user(user_id) ON DELETE SET NULL,
    INDEX ix_audit_entity  (entity_type, entity_id),
    INDEX ix_audit_actor   (actor_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE system_job_log (
    job_run_id        BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_name          VARCHAR(60) NOT NULL,
    triggered_by      ENUM('EVENT_SCHEDULER','ON_DEMAND','CRON') NOT NULL DEFAULT 'ON_DEMAND',
    overdue_marked    INT         NOT NULL DEFAULT 0,
    requests_expired  INT         NOT NULL DEFAULT 0,
    no_shows_expired  INT         NOT NULL DEFAULT 0,
    tokens_purged     INT         NOT NULL DEFAULT 0,
    ran_at            DATETIME    NOT NULL DEFAULT (UTC_TIMESTAMP()),
    INDEX ix_job_name_time (job_name, ran_at)
) ENGINE=InnoDB;

-- =====================================================================
-- 2. HELPER FUNCTIONS
-- =====================================================================
DELIMITER $$

DROP FUNCTION IF EXISTS fn_campus_today$$
CREATE FUNCTION fn_campus_today() RETURNS DATE
NOT DETERMINISTIC READS SQL DATA
BEGIN
    RETURN DATE(UTC_TIMESTAMP() + INTERVAL 330 MINUTE);
END$$

DROP FUNCTION IF EXISTS fn_campus_day_end_utc$$
CREATE FUNCTION fn_campus_day_end_utc(p_date DATE) RETURNS DATETIME
DETERMINISTIC NO SQL
BEGIN
    RETURN TIMESTAMP(p_date, '23:59:59') - INTERVAL 330 MINUTE;
END$$

DROP FUNCTION IF EXISTS fn_item_is_available$$
CREATE FUNCTION fn_item_is_available(p_item_id INT, p_start DATE, p_end DATE) RETURNS TINYINT(1)
NOT DETERMINISTIC READS SQL DATA
BEGIN
    DECLARE v_ok TINYINT(1);
    SELECT (i.listing_status = 'ACTIVE'
            AND i.deleted_at IS NULL
            AND i.item_condition <> 'DAMAGED'
            AND NOT EXISTS (
                SELECT 1 FROM borrow_request br
                JOIN loan l ON l.request_id = br.request_id
                WHERE br.item_id = i.item_id
                  AND (l.status = 'OVERDUE'
                       OR (l.status = 'ACTIVE' AND l.due_at < UTC_TIMESTAMP())
                       OR (l.status = 'ACTIVE' AND p_start <= fn_campus_today()))
            )
            AND NOT EXISTS (
                SELECT 1 FROM booked_date bd
                WHERE bd.item_id = i.item_id
                  AND bd.booked_date BETWEEN p_start AND p_end
            ))
      INTO v_ok
      FROM item i
     WHERE i.item_id = p_item_id;
    RETURN IFNULL(v_ok, 0);
END$$

-- =====================================================================
-- 3. COMPLETE TRIGGERS (All 23 Triggers Included)
-- =====================================================================

-- ---------------------------- app_user -------------------------------
DROP TRIGGER IF EXISTS trg_app_user_bu$$
CREATE TRIGGER trg_app_user_bu
BEFORE UPDATE ON app_user
FOR EACH ROW
BEGIN
    DECLARE v_open INT DEFAULT 0;
    SET NEW.updated_at = UTC_TIMESTAMP();

    IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
        SELECT COUNT(*) INTO v_open
          FROM loan l
          JOIN borrow_request br ON br.request_id = l.request_id
          JOIN item i ON i.item_id = br.item_id
         WHERE l.status IN ('SCHEDULED','ACTIVE','OVERDUE')
           AND (br.borrower_id = OLD.user_id OR i.owner_id = OLD.user_id);
        IF v_open > 0 THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot delete a user who has unfinished loans.';
        END IF;
    END IF;
END$$

DROP TRIGGER IF EXISTS trg_app_user_au$$
CREATE TRIGGER trg_app_user_au
AFTER UPDATE ON app_user
FOR EACH ROW
BEGIN
    IF (OLD.is_active = 1 AND NEW.is_active = 0)
       OR (OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL) THEN
        UPDATE item
           SET listing_status = 'PAUSED'
         WHERE owner_id = NEW.user_id AND listing_status = 'ACTIVE';
    END IF;

    IF NOT (OLD.role <=> NEW.role) OR NOT (OLD.is_active <=> NEW.is_active)
       OR NOT (OLD.is_verified <=> NEW.is_verified) OR NOT (OLD.deleted_at <=> NEW.deleted_at) THEN
        INSERT INTO application_audit_log (actor_id, action, entity_type, entity_id, old_value, new_value)
        VALUES (@current_user_id, 'USER_CHANGED', 'app_user', NEW.user_id,
                JSON_OBJECT('role', OLD.role, 'is_active', OLD.is_active, 'is_verified', OLD.is_verified,
                            'deleted', OLD.deleted_at IS NOT NULL),
                JSON_OBJECT('role', NEW.role, 'is_active', NEW.is_active, 'is_verified', NEW.is_verified,
                            'deleted', NEW.deleted_at IS NOT NULL));
    END IF;
END$$

-- ------------------------------ item ---------------------------------
DROP TRIGGER IF EXISTS trg_item_bi$$
CREATE TRIGGER trg_item_bi
BEFORE INSERT ON item
FOR EACH ROW
BEGIN
    DECLARE v_ok INT DEFAULT 0;
    SELECT COUNT(*) INTO v_ok FROM app_user
     WHERE user_id = NEW.owner_id AND is_verified = 1 AND is_active = 1 AND deleted_at IS NULL;
    IF v_ok = 0 THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Only verified, active users can list items.';
    END IF;
    IF NEW.item_condition = 'DAMAGED' AND NEW.listing_status = 'ACTIVE' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'A DAMAGED item cannot be listed as ACTIVE.';
    END IF;
END$$

DROP TRIGGER IF EXISTS trg_item_bu$$
CREATE TRIGGER trg_item_bu
BEFORE UPDATE ON item
FOR EACH ROW
BEGIN
    DECLARE v_open INT DEFAULT 0;
    SET NEW.updated_at = UTC_TIMESTAMP();

    IF NEW.owner_id <> OLD.owner_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Item ownership cannot be changed.';
    END IF;

    IF NEW.item_condition = 'DAMAGED' AND NEW.listing_status = 'ACTIVE' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Cannot set listing_status to ACTIVE while item_condition is DAMAGED.';
    END IF;

    IF (NEW.listing_status = 'ARCHIVED' AND OLD.listing_status <> 'ARCHIVED')
       OR (NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL) THEN
        SELECT COUNT(*) INTO v_open
          FROM loan l
          JOIN borrow_request br ON br.request_id = l.request_id
         WHERE br.item_id = OLD.item_id AND l.status IN ('SCHEDULED','ACTIVE','OVERDUE');
        IF v_open > 0 THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot archive or delete an item that has unfinished loans.';
        END IF;
    END IF;
END$$

DROP TRIGGER IF EXISTS trg_item_au$$
CREATE TRIGGER trg_item_au
AFTER UPDATE ON item
FOR EACH ROW
BEGIN
    IF NOT (OLD.daily_fee <=> NEW.daily_fee) OR NOT (OLD.deposit_amount <=> NEW.deposit_amount)
       OR NOT (OLD.listing_status <=> NEW.listing_status) OR NOT (OLD.item_condition <=> NEW.item_condition) THEN
        INSERT INTO application_audit_log (actor_id, action, entity_type, entity_id, old_value, new_value)
        VALUES (@current_user_id, 'ITEM_CHANGED', 'item', NEW.item_id,
                JSON_OBJECT('daily_fee', OLD.daily_fee, 'deposit_amount', OLD.deposit_amount,
                            'listing_status', OLD.listing_status, 'item_condition', OLD.item_condition),
                JSON_OBJECT('daily_fee', NEW.daily_fee, 'deposit_amount', NEW.deposit_amount,
                            'listing_status', NEW.listing_status, 'item_condition', NEW.item_condition));
    END IF;
END$$

-- -------------------------- borrow_request ---------------------------
DROP TRIGGER IF EXISTS trg_request_bi$$
CREATE TRIGGER trg_request_bi
BEFORE INSERT ON borrow_request
FOR EACH ROW
BEGIN
    DECLARE v_owner     INT;
    DECLARE v_listing   VARCHAR(20);
    DECLARE v_condition VARCHAR(20);
    DECLARE v_deleted   DATETIME;
    DECLARE v_max_days  INT;
    DECLARE v_ok        INT DEFAULT 0;

    SELECT owner_id, listing_status, item_condition, deleted_at, max_borrow_days
      INTO v_owner, v_listing, v_condition, v_deleted, v_max_days
      FROM item WHERE item_id = NEW.item_id FOR UPDATE;

    IF v_owner IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Item not found.';
    END IF;
    IF v_listing <> 'ACTIVE' OR v_deleted IS NOT NULL OR v_condition = 'DAMAGED' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'This item is not available for borrowing requests.';
    END IF;
    IF v_owner = NEW.borrower_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Users cannot request to borrow their own items.';
    END IF;

    SELECT COUNT(*) INTO v_ok FROM app_user
     WHERE user_id = NEW.borrower_id AND is_verified = 1 AND is_active = 1 AND deleted_at IS NULL;
    IF v_ok = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only verified, active users can borrow items.';
    END IF;

    IF NEW.start_date < fn_campus_today() THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Start date cannot be in the past.';
    END IF;
    IF DATEDIFF(NEW.end_date, NEW.start_date) + 1 > v_max_days THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Requested period exceeds the item max_borrow_days.';
    END IF;

    IF fn_item_is_available(NEW.item_id, NEW.start_date, NEW.end_date) = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'The item is unavailable or already booked for part of this period.';
    END IF;

    SET NEW.status = 'PENDING';
    SET NEW.decided_at = NULL;
END$$

DROP TRIGGER IF EXISTS trg_request_ai$$
CREATE TRIGGER trg_request_ai
AFTER INSERT ON borrow_request
FOR EACH ROW
BEGIN
    DECLARE v_owner INT;
    DECLARE v_title VARCHAR(160);
    SELECT owner_id, title INTO v_owner, v_title FROM item WHERE item_id = NEW.item_id;
    INSERT INTO notification (user_id, related_request_id, reference_type, reference_id, type, title, message)
    VALUES (v_owner, NEW.request_id, 'REQUEST', NEW.request_id, 'REQUEST_RECEIVED', 'New borrow request',
            CONCAT('Someone wants to borrow "', v_title, '" from ', NEW.start_date, ' to ', NEW.end_date, '.'));
END$$

DROP TRIGGER IF EXISTS trg_request_bu$$
CREATE TRIGGER trg_request_bu
BEFORE UPDATE ON borrow_request
FOR EACH ROW
BEGIN
    DECLARE v_loan_id      INT;
    DECLARE v_loan_status  VARCHAR(20);
    DECLARE v_listing      VARCHAR(20);
    DECLARE v_condition    VARCHAR(20);
    DECLARE v_deleted      DATETIME;
    DECLARE v_locked_owner INT;
    DECLARE v_open_dispute INT DEFAULT 0;

    IF NEW.item_id <> OLD.item_id OR NEW.borrower_id <> OLD.borrower_id
       OR NEW.start_date <> OLD.start_date OR NEW.end_date <> OLD.end_date THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Item, borrower and dates of a request cannot be changed.';
    END IF;

    IF NEW.status <> OLD.status THEN
        IF NOT ((OLD.status = 'PENDING'  AND NEW.status IN ('APPROVED','REJECTED','CANCELLED'))
             OR (OLD.status = 'APPROVED' AND NEW.status = 'CANCELLED')) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid request status transition.';
        END IF;

        IF NEW.status = 'APPROVED' THEN
            IF @pending_handover_otp_hash IS NULL OR @pending_return_otp_hash IS NULL THEN
                SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Requests must be approved via sp_approve_request so handover/return OTPs are issued.';
            END IF;

            SELECT owner_id, listing_status, item_condition, deleted_at
              INTO v_locked_owner, v_listing, v_condition, v_deleted
              FROM item WHERE item_id = NEW.item_id FOR UPDATE;

            IF NEW.end_date < fn_campus_today() THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cannot approve a request whose period has already ended.';
            END IF;
            IF v_listing <> 'ACTIVE' OR v_deleted IS NOT NULL OR v_condition = 'DAMAGED' THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cannot approve request: item is paused, archived, deleted, or damaged.';
            END IF;
            IF fn_item_is_available(NEW.item_id, NEW.start_date, NEW.end_date) = 0 THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Approval rejected: requested dates overlap an existing reservation or active loan.';
            END IF;
        END IF;

        IF OLD.status = 'APPROVED' AND NEW.status = 'CANCELLED' THEN
            SELECT loan_id, status INTO v_loan_id, v_loan_status
              FROM loan WHERE request_id = OLD.request_id;
            IF v_loan_status IS NOT NULL AND v_loan_status <> 'SCHEDULED' THEN
                SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'An approved request cannot be cancelled after handover.';
            END IF;
            IF v_loan_id IS NOT NULL THEN
                SELECT COUNT(*) INTO v_open_dispute FROM dispute
                 WHERE loan_id = v_loan_id AND status IN ('OPEN','UNDER_REVIEW');
                IF v_open_dispute > 0 THEN
                    SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'Cannot cancel a request while an open dispute exists.';
                END IF;
            END IF;
        END IF;

        SET NEW.decided_at = IFNULL(NEW.decided_at, UTC_TIMESTAMP());
    END IF;
END$$

DROP TRIGGER IF EXISTS trg_request_au$$
CREATE TRIGGER trg_request_au
AFTER UPDATE ON borrow_request
FOR EACH ROW
BEGIN
    DECLARE v_owner   INT;
    DECLARE v_title   VARCHAR(160);
    DECLARE v_daily   DECIMAL(10,2);
    DECLARE v_deposit DECIMAL(10,2);
    DECLARE v_days    INT;
    DECLARE v_d       DATE;
    DECLARE v_loan_id INT;

    IF NEW.status <> OLD.status THEN
        SELECT owner_id, title, daily_fee, deposit_amount
          INTO v_owner, v_title, v_daily, v_deposit
          FROM item WHERE item_id = NEW.item_id;

        IF NEW.status = 'APPROVED' THEN
            SET v_days = DATEDIFF(NEW.end_date, NEW.start_date) + 1;

            INSERT INTO loan (
                request_id, status, due_at,
                agreed_daily_fee, agreed_deposit, agreed_total_fee,
                handover_otp_hash, return_otp_hash
            )
            VALUES (
                NEW.request_id, 'SCHEDULED', fn_campus_day_end_utc(NEW.end_date),
                v_daily, v_deposit, v_daily * v_days,
                @pending_handover_otp_hash,
                @pending_return_otp_hash
            );
            SET v_loan_id = LAST_INSERT_ID();

            SET v_d = NEW.start_date;
            WHILE v_d <= NEW.end_date DO
                INSERT INTO booked_date (item_id, booked_date, request_id)
                VALUES (NEW.item_id, v_d, NEW.request_id);
                SET v_d = v_d + INTERVAL 1 DAY;
            END WHILE;

            INSERT INTO notification (user_id, related_request_id, related_loan_id, reference_type, reference_id, type, title, message)
            VALUES (NEW.borrower_id, NEW.request_id, v_loan_id, 'loan', v_loan_id, 'REQUEST_APPROVED', 'Request approved',
                    CONCAT('Your request for "', v_title, '" was approved. Fee: ', v_daily * v_days,
                           ', deposit: ', v_deposit, '.'));

        ELSEIF NEW.status = 'REJECTED' THEN
            INSERT INTO notification (user_id, related_request_id, reference_type, reference_id, type, title, message)
            VALUES (NEW.borrower_id, NEW.request_id, 'REQUEST', NEW.request_id, 'REQUEST_REJECTED', 'Request declined',
                    CONCAT('Your request for "', v_title, '" was declined.'));

        ELSEIF NEW.status = 'CANCELLED' THEN
            DELETE FROM booked_date WHERE request_id = NEW.request_id;
            UPDATE loan SET status = 'CANCELLED'
             WHERE request_id = NEW.request_id AND status = 'SCHEDULED';

            IF NEW.decision_note LIKE 'Expired:%' THEN
                INSERT INTO notification (user_id, related_request_id, reference_type, reference_id, type, title, message)
                VALUES (NEW.borrower_id, NEW.request_id, 'REQUEST', NEW.request_id, 'REQUEST_CANCELLED', 'Request expired',
                        CONCAT('Your request for "', v_title, '" expired because the start date passed.'));
            ELSE
                INSERT INTO notification (user_id, related_request_id, reference_type, reference_id, type, title, message)
                VALUES (v_owner, NEW.request_id, 'REQUEST', NEW.request_id, 'REQUEST_CANCELLED', 'Request cancelled',
                        CONCAT('A request for "', v_title, '" was cancelled by the borrower.'));
            END IF;
        END IF;

        INSERT INTO application_audit_log (actor_id, action, entity_type, entity_id, old_value, new_value)
        VALUES (@current_user_id, 'REQUEST_STATUS_CHANGED', 'borrow_request', NEW.request_id,
                JSON_OBJECT('status', OLD.status), JSON_OBJECT('status', NEW.status));
    END IF;
END$$

-- ------------------------------ loan ---------------------------------
DROP TRIGGER IF EXISTS trg_loan_bi$$
CREATE TRIGGER trg_loan_bi
BEFORE INSERT ON loan
FOR EACH ROW
BEGIN
    SET NEW.status = 'SCHEDULED';
    SET NEW.issued_at = NULL;
    SET NEW.returned_at = NULL;
    SET NEW.late_fee = 0.00;
    SET NEW.deposit_status = 'NOT_PAID';
    SET NEW.deposit_deducted = 0.00;
END$$

DROP TRIGGER IF EXISTS trg_loan_bu$$
CREATE TRIGGER trg_loan_bu
BEFORE UPDATE ON loan
FOR EACH ROW
BEGIN
    DECLARE v_ref DATETIME;

    IF NEW.request_id <> OLD.request_id OR NEW.due_at <> OLD.due_at
       OR NEW.agreed_daily_fee <> OLD.agreed_daily_fee
       OR NEW.agreed_deposit   <> OLD.agreed_deposit
       OR NEW.agreed_total_fee <> OLD.agreed_total_fee THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Agreed loan terms cannot be changed.';
    END IF;

    IF NEW.status <> OLD.status THEN
        IF NOT ((OLD.status = 'SCHEDULED' AND NEW.status IN ('ACTIVE','CANCELLED'))
             OR (OLD.status = 'ACTIVE'    AND NEW.status IN ('OVERDUE','RETURNED'))
             OR (OLD.status = 'OVERDUE'   AND NEW.status = 'RETURNED')) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid loan status transition.';
        END IF;

        IF NEW.status = 'ACTIVE' THEN
            IF NOT EXISTS (
                SELECT 1 FROM loan_inspection li
                 WHERE li.loan_id = OLD.loan_id
                   AND li.stage = 'HANDOVER'
                   AND li.inspection_status = 'VERIFIED'
                   AND li.owner_agreed = 1
                   AND li.borrower_agreed = 1
                   AND li.otp_verified = 1
            ) THEN
                SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Loan cannot become ACTIVE without a VERIFIED two-party HANDOVER inspection.';
            END IF;
            SET NEW.issued_at = IFNULL(NEW.issued_at, UTC_TIMESTAMP());
        END IF;

        IF NEW.status = 'RETURNED' THEN
            IF NOT EXISTS (
                SELECT 1 FROM loan_inspection li
                 WHERE li.loan_id = OLD.loan_id
                   AND li.stage = 'RETURN'
                   AND li.inspection_status = 'VERIFIED'
                   AND li.owner_agreed = 1
                   AND li.borrower_agreed = 1
                   AND li.otp_verified = 1
            ) THEN
                SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Loan cannot become RETURNED without a VERIFIED two-party RETURN inspection.';
            END IF;
            SET NEW.returned_at = IFNULL(NEW.returned_at, UTC_TIMESTAMP());
        END IF;
    END IF;

    IF NEW.status IN ('OVERDUE','RETURNED') AND OLD.status IN ('ACTIVE','OVERDUE') THEN
        SET v_ref = IF(NEW.status = 'RETURNED', NEW.returned_at, UTC_TIMESTAMP());
        IF v_ref > NEW.due_at THEN
            SET NEW.late_fee = CEIL(TIMESTAMPDIFF(SECOND, NEW.due_at, v_ref) / 86400) * NEW.agreed_daily_fee;
        ELSE
            SET NEW.late_fee = 0.00;
        END IF;
    END IF;

    IF NEW.deposit_status <> OLD.deposit_status THEN
        IF NOT ((OLD.deposit_status = 'NOT_PAID' AND NEW.deposit_status = 'HELD')
             OR (OLD.deposit_status = 'HELD' AND NEW.deposit_status IN ('RELEASED','FORFEITED','PARTIAL'))) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid deposit status transition.';
        END IF;
        IF NEW.deposit_status IN ('RELEASED','FORFEITED','PARTIAL') AND NEW.status NOT IN ('RETURNED','CANCELLED') THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Deposit can only be settled after return or cancellation.';
        END IF;
    END IF;
END$$

DROP TRIGGER IF EXISTS trg_loan_au$$
CREATE TRIGGER trg_loan_au
AFTER UPDATE ON loan
FOR EACH ROW
BEGIN
    DECLARE v_borrower INT;
    DECLARE v_owner    INT;
    DECLARE v_title    VARCHAR(160);

    IF NEW.status <> OLD.status THEN
        IF NEW.status IN ('ACTIVE','OVERDUE','RETURNED') THEN
            SELECT br.borrower_id, i.owner_id, i.title
              INTO v_borrower, v_owner, v_title
              FROM borrow_request br JOIN item i ON i.item_id = br.item_id
             WHERE br.request_id = NEW.request_id;
        END IF;

        IF NEW.status = 'ACTIVE' THEN
            INSERT INTO notification (user_id, related_request_id, related_loan_id, reference_type, reference_id, type, title, message)
            VALUES (v_borrower, NEW.request_id, NEW.loan_id, 'loan', NEW.loan_id, 'LOAN_STARTED', 'Loan started',
                    CONCAT('"', v_title, '" is now on loan to you. Due: ', NEW.due_at, ' UTC.'));
        ELSEIF NEW.status = 'OVERDUE' THEN
            INSERT INTO notification (user_id, related_request_id, related_loan_id, reference_type, reference_id, type, title, message)
            VALUES (v_borrower, NEW.request_id, NEW.loan_id, 'loan', NEW.loan_id, 'LOAN_OVERDUE', 'Loan overdue',
                    CONCAT('"', v_title, '" is overdue. Please return it - late fees apply.')),
                   (v_owner, NEW.request_id, NEW.loan_id, 'loan', NEW.loan_id, 'LOAN_OVERDUE', 'Loan overdue',
                    CONCAT('"', v_title, '" has not been returned on time.'));
        ELSEIF NEW.status = 'RETURNED' THEN
            DELETE FROM booked_date
             WHERE request_id = NEW.request_id AND booked_date > fn_campus_today();
            INSERT INTO notification (user_id, related_request_id, related_loan_id, reference_type, reference_id, type, title, message)
            VALUES (v_owner, NEW.request_id, NEW.loan_id, 'loan', NEW.loan_id, 'LOAN_RETURNED', 'Item returned',
                    CONCAT('"', v_title, '" was returned.'));
        END IF;

        INSERT INTO application_audit_log (actor_id, action, entity_type, entity_id, old_value, new_value)
        VALUES (@current_user_id, 'LOAN_STATUS_CHANGED', 'loan', NEW.loan_id,
                JSON_OBJECT('status', OLD.status), JSON_OBJECT('status', NEW.status));
    END IF;

    IF NEW.deposit_status <> OLD.deposit_status THEN
        INSERT INTO application_audit_log (actor_id, action, entity_type, entity_id, old_value, new_value)
        VALUES (@current_user_id, 'DEPOSIT_STATUS_CHANGED', 'loan', NEW.loan_id,
                JSON_OBJECT('deposit_status', OLD.deposit_status, 'deducted', OLD.deposit_deducted),
                JSON_OBJECT('deposit_status', NEW.deposit_status, 'deducted', NEW.deposit_deducted));
    END IF;
END$$

-- -------------------------- loan_inspection --------------------------
DROP TRIGGER IF EXISTS trg_inspection_bi$$
CREATE TRIGGER trg_inspection_bi
BEFORE INSERT ON loan_inspection
FOR EACH ROW
BEGIN
    DECLARE v_loan_status VARCHAR(20);
    DECLARE v_borrower    INT;
    DECLARE v_owner       INT;
    DECLARE v_start       DATE;
    DECLARE v_deposit     DECIMAL(10,2);
    DECLARE v_dep_status  VARCHAR(20);
    DECLARE v_rental_fee  DECIMAL(10,2);
    DECLARE v_rental_paid INT DEFAULT 0;

    SELECT l.status, br.borrower_id, i.owner_id, br.start_date,
           l.agreed_deposit, l.deposit_status, l.agreed_total_fee
      INTO v_loan_status, v_borrower, v_owner, v_start,
           v_deposit, v_dep_status, v_rental_fee
      FROM loan l
      JOIN borrow_request br ON br.request_id = l.request_id
      JOIN item i ON i.item_id = br.item_id
     WHERE l.loan_id = NEW.loan_id
     FOR UPDATE;

    IF v_loan_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Loan not found.';
    END IF;
    IF NEW.inspected_by NOT IN (v_borrower, v_owner) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only the loan owner or borrower can submit an inspection.';
    END IF;

    IF NEW.stage = 'HANDOVER' THEN
        IF v_loan_status <> 'SCHEDULED' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Handover inspection requires a SCHEDULED loan.';
        END IF;
        IF v_deposit > 0 AND v_dep_status <> 'HELD' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Required deposit must be paid and HELD before handover.';
        END IF;
        IF v_rental_fee > 0 THEN
            SELECT COUNT(*) INTO v_rental_paid FROM payment
             WHERE loan_id = NEW.loan_id AND payment_type = 'RENTAL_FEE' AND payment_status = 'COMPLETED';
            IF v_rental_paid = 0 THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Agreed rental fee must be COMPLETED before handover.';
            END IF;
        END IF;
        IF NEW.condition_found = 'DAMAGED' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cannot hand over an item in DAMAGED condition.';
        END IF;
    ELSE
        IF v_loan_status NOT IN ('ACTIVE','OVERDUE') THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Return inspection requires an ACTIVE or OVERDUE loan.';
        END IF;
    END IF;

    SET NEW.confirmed_by      = NULL;
    SET NEW.otp_verified      = 0;
    SET NEW.provided_otp_hash = NULL;
    SET NEW.verified_at       = NULL;
    SET NEW.inspection_status = 'PENDING_COUNTERPARTY';

    IF NEW.inspected_by = v_owner THEN
        SET NEW.owner_agreed       = 1;
        SET NEW.owner_agreed_at    = UTC_TIMESTAMP();
        SET NEW.borrower_agreed    = 0;
        SET NEW.borrower_agreed_at = NULL;
    ELSE
        SET NEW.owner_agreed       = 0;
        SET NEW.owner_agreed_at    = NULL;
        SET NEW.borrower_agreed    = 1;
        SET NEW.borrower_agreed_at = UTC_TIMESTAMP();
    END IF;
END$$

DROP TRIGGER IF EXISTS trg_inspection_bu$$
CREATE TRIGGER trg_inspection_bu
BEFORE UPDATE ON loan_inspection
FOR EACH ROW
BEGIN
    DECLARE v_borrower      INT;
    DECLARE v_owner         INT;
    DECLARE v_expected_hash CHAR(64);

    IF OLD.inspection_status <> 'PENDING_COUNTERPARTY' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Finalized inspections (VERIFIED or DISPUTED) are immutable.';
    END IF;

    IF NEW.loan_id <> OLD.loan_id OR NEW.stage <> OLD.stage
       OR NEW.inspected_by <> OLD.inspected_by
       OR NEW.condition_found <> OLD.condition_found
       OR NOT (NEW.notes <=> OLD.notes) THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Inspection loan, stage, inspector, condition_found and original notes cannot be altered.';
    END IF;

    SELECT br.borrower_id, i.owner_id,
           IF(OLD.stage = 'HANDOVER', l.handover_otp_hash, l.return_otp_hash)
      INTO v_borrower, v_owner, v_expected_hash
      FROM loan l
      JOIN borrow_request br ON br.request_id = l.request_id
      JOIN item i ON i.item_id = br.item_id
     WHERE l.loan_id = OLD.loan_id
     FOR UPDATE;

    IF NEW.confirmed_by IS NULL OR NEW.confirmed_by NOT IN (v_borrower, v_owner)
       OR NEW.confirmed_by = OLD.inspected_by THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Inspection must be confirmed by the counterparty (the other party to the loan).';
    END IF;

    IF NEW.inspection_status = 'VERIFIED' THEN
        IF NEW.provided_otp_hash IS NULL OR NEW.provided_otp_hash <> v_expected_hash THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid handover/return OTP hash.';
        END IF;

        IF NEW.confirmed_by = v_owner THEN
            SET NEW.owner_agreed    = 1;
            SET NEW.owner_agreed_at = UTC_TIMESTAMP();
            SET NEW.borrower_agreed = OLD.borrower_agreed;
        ELSE
            SET NEW.borrower_agreed    = 1;
            SET NEW.borrower_agreed_at = UTC_TIMESTAMP();
            SET NEW.owner_agreed       = OLD.owner_agreed;
        END IF;

        SET NEW.otp_verified = 1;
        SET NEW.verified_at  = UTC_TIMESTAMP();
    ELSEIF NEW.inspection_status = 'DISPUTED' THEN
        SET NEW.otp_verified = 0;
        SET NEW.verified_at  = UTC_TIMESTAMP();
    ELSE
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Counterparty update must transition status to VERIFIED or DISPUTED.';
    END IF;
END$$

DROP TRIGGER IF EXISTS trg_inspection_au$$
CREATE TRIGGER trg_inspection_au
AFTER UPDATE ON loan_inspection
FOR EACH ROW
BEGIN
    DECLARE v_item_id INT;

    IF OLD.inspection_status = 'PENDING_COUNTERPARTY' AND NEW.inspection_status = 'VERIFIED' THEN
        SELECT br.item_id INTO v_item_id
          FROM loan l
          JOIN borrow_request br ON br.request_id = l.request_id
         WHERE l.loan_id = NEW.loan_id;

        IF NEW.stage = 'HANDOVER' THEN
            UPDATE loan SET status = 'ACTIVE' WHERE loan_id = NEW.loan_id;
            UPDATE item SET item_condition = NEW.condition_found WHERE item_id = v_item_id;
        ELSE
            UPDATE loan SET status = 'RETURNED' WHERE loan_id = NEW.loan_id;
            UPDATE item
               SET item_condition = NEW.condition_found,
                   listing_status = IF(NEW.condition_found = 'DAMAGED' AND listing_status = 'ACTIVE', 'PAUSED', listing_status)
             WHERE item_id = v_item_id;
        END IF;
    END IF;
END$$

DROP TRIGGER IF EXISTS trg_inspection_bd$$
CREATE TRIGGER trg_inspection_bd
BEFORE DELETE ON loan_inspection
FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Inspections are immutable evidence and cannot be deleted.';
END$$

-- ------------------------------ review -------------------------------
DROP TRIGGER IF EXISTS trg_review_bi$$
CREATE TRIGGER trg_review_bi
BEFORE INSERT ON review
FOR EACH ROW
BEGIN
    DECLARE v_status   VARCHAR(20);
    DECLARE v_borrower INT;
    DECLARE v_owner    INT;

    SELECT l.status, br.borrower_id, i.owner_id
      INTO v_status, v_borrower, v_owner
      FROM loan l
      JOIN borrow_request br ON br.request_id = l.request_id
      JOIN item i ON i.item_id = br.item_id
     WHERE l.loan_id = NEW.loan_id
     FOR UPDATE;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Loan not found.';
    END IF;
    IF v_status <> 'RETURNED' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Reviews can only be submitted after the loan is RETURNED.';
    END IF;
    IF NOT ((NEW.reviewer_id = v_borrower AND NEW.reviewee_id = v_owner)
         OR (NEW.reviewer_id = v_owner    AND NEW.reviewee_id = v_borrower)) THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Reviewer and reviewee must be the owner and borrower of this loan.';
    END IF;
END$$

DROP TRIGGER IF EXISTS trg_review_ai$$
CREATE TRIGGER trg_review_ai
AFTER INSERT ON review
FOR EACH ROW
BEGIN
    INSERT INTO notification (user_id, related_loan_id, reference_type, reference_id, type, title, message)
    VALUES (NEW.reviewee_id, NEW.loan_id, 'review', NEW.review_id, 'REVIEW_RECEIVED', 'New review',
            CONCAT('You received a ', NEW.rating, '-star review.'));
END$$

-- ----------------------------- payment -------------------------------
DROP TRIGGER IF EXISTS trg_payment_bi$$
CREATE TRIGGER trg_payment_bi
BEFORE INSERT ON payment
FOR EACH ROW
BEGIN
    DECLARE v_status           VARCHAR(20);
    DECLARE v_borrower         INT;
    DECLARE v_owner            INT;
    DECLARE v_deposit          DECIMAL(10,2);
    DECLARE v_fee              DECIMAL(10,2);
    DECLARE v_late_fee         DECIMAL(10,2);
    DECLARE v_deducted         DECIMAL(10,2);
    DECLARE v_dup              INT DEFAULT 0;
    DECLARE v_paid_total       DECIMAL(12,2) DEFAULT 0.00;
    DECLARE v_awarded_total    DECIMAL(12,2) DEFAULT 0.00;
    DECLARE v_src_loan_id      INT;
    DECLARE v_src_type         VARCHAR(30);
    DECLARE v_src_status       VARCHAR(20);
    DECLARE v_src_amount       DECIMAL(10,2);
    DECLARE v_src_refunded     DECIMAL(12,2) DEFAULT 0.00;
    DECLARE v_borrower_awarded DECIMAL(12,2) DEFAULT 0.00;

    SELECT l.status, br.borrower_id, i.owner_id,
           l.agreed_deposit, l.agreed_total_fee, l.late_fee, l.deposit_deducted
      INTO v_status, v_borrower, v_owner,
           v_deposit, v_fee, v_late_fee, v_deducted
      FROM loan l
      JOIN borrow_request br ON br.request_id = l.request_id
      JOIN item i ON i.item_id = br.item_id
     WHERE l.loan_id = NEW.loan_id
     FOR UPDATE;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Loan not found.';
    END IF;
    IF v_status = 'CANCELLED' AND NEW.payment_type <> 'REFUND' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only refunds are allowed on a cancelled loan.';
    END IF;

    IF NEW.payment_type = 'REFUND' THEN
        IF NEW.payer_id <> v_owner OR NEW.payee_id <> v_borrower THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Refunds must go from the owner to the borrower.';
        END IF;

        SELECT loan_id, payment_type, payment_status, amount
          INTO v_src_loan_id, v_src_type, v_src_status, v_src_amount
          FROM payment
         WHERE payment_id = NEW.refund_for_payment_id;

        IF v_src_loan_id IS NULL OR v_src_loan_id <> NEW.loan_id THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Refund must reference a valid payment on the same loan.';
        END IF;
        IF v_src_status <> 'COMPLETED' OR v_src_type = 'REFUND' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Refunds can only be issued against COMPLETED non-refund payments.';
        END IF;

        SELECT COALESCE(SUM(amount), 0) INTO v_src_refunded
          FROM payment
         WHERE refund_for_payment_id = NEW.refund_for_payment_id
           AND payment_status IN ('PENDING','COMPLETED');

        IF v_src_refunded + NEW.amount > v_src_amount THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cumulative refunds for this charge cannot exceed the original payment amount.';
        END IF;

        IF v_src_type = 'DEPOSIT' THEN
            IF v_src_refunded + NEW.amount > (v_src_amount - v_deducted) THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Deposit refund cannot exceed paid deposit minus deposit_deducted.';
            END IF;
            IF v_status NOT IN ('RETURNED','CANCELLED') THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Deposit can only be refunded on a RETURNED or CANCELLED loan.';
            END IF;
        ELSEIF v_src_type = 'RENTAL_FEE' THEN
            IF v_status <> 'CANCELLED' THEN
                IF NEW.refund_reason <> 'DISPUTE_AWARD' THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'After handover, rental fees can only be refunded via a RESOLVED dispute award.';
                END IF;
                SELECT COALESCE(SUM(amount_awarded), 0) INTO v_borrower_awarded
                  FROM dispute
                 WHERE loan_id = NEW.loan_id AND raised_by = v_borrower AND status = 'RESOLVED';
                IF v_src_refunded + NEW.amount > v_borrower_awarded THEN
                    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Rental fee dispute refund exceeds resolved dispute award to borrower.';
                END IF;
            END IF;
        END IF;

    ELSE
        IF NEW.payer_id <> v_borrower OR NEW.payee_id <> v_owner THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Charges must go from the borrower to the owner.';
        END IF;

        IF NEW.payment_type = 'DEPOSIT' AND NEW.amount <> v_deposit THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Deposit payment must equal the agreed deposit.';
        END IF;
        IF NEW.payment_type = 'RENTAL_FEE' AND NEW.amount <> v_fee THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Rental fee payment must equal the agreed total fee.';
        END IF;
        IF NEW.payment_type = 'LATE_FEE' AND (v_late_fee <= 0 OR NEW.amount > v_late_fee) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Late fee payment cannot exceed the accrued late fee on the loan.';
        END IF;

        IF NEW.payment_type IN ('DEPOSIT','RENTAL_FEE') THEN
            SELECT COUNT(*) INTO v_dup FROM payment
             WHERE loan_id = NEW.loan_id AND payment_type = NEW.payment_type
               AND payment_status IN ('PENDING','COMPLETED');
            IF v_dup > 0 THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A pending or completed payment of this type already exists.';
            END IF;
        END IF;

        IF NEW.payment_type = 'LATE_FEE' THEN
            SELECT COALESCE(SUM(amount), 0) INTO v_paid_total FROM payment
             WHERE loan_id = NEW.loan_id AND payment_type = 'LATE_FEE'
               AND payment_status IN ('PENDING','COMPLETED');
            IF v_paid_total + NEW.amount > v_late_fee THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cumulative late-fee payments cannot exceed the accrued late fee.';
            END IF;
        ELSEIF NEW.payment_type = 'DAMAGE_DEDUCTION' THEN
            IF v_status NOT IN ('ACTIVE','OVERDUE','RETURNED') THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Damage deductions require a started or returned loan.';
            END IF;
            SELECT COALESCE(SUM(amount), 0) INTO v_paid_total FROM payment
             WHERE loan_id = NEW.loan_id AND payment_type = 'DAMAGE_DEDUCTION'
               AND payment_status IN ('PENDING','COMPLETED');
            IF v_paid_total + NEW.amount > v_deposit THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cumulative damage deductions cannot exceed the agreed deposit.';
            END IF;
        ELSEIF NEW.payment_type = 'DAMAGE_CHARGE' THEN
            IF v_status NOT IN ('ACTIVE','OVERDUE','RETURNED') THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Damage charges require a started or returned loan.';
            END IF;
            SELECT COALESCE(SUM(amount_awarded), 0) INTO v_awarded_total FROM dispute
             WHERE loan_id = NEW.loan_id AND dispute_type = 'DAMAGE' AND status = 'RESOLVED';
            SELECT COALESCE(SUM(amount), 0) INTO v_paid_total FROM payment
             WHERE loan_id = NEW.loan_id AND payment_type = 'DAMAGE_CHARGE'
               AND payment_status IN ('PENDING','COMPLETED');
            IF v_awarded_total <= 0 OR v_paid_total + NEW.amount > v_awarded_total THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cumulative damage charges cannot exceed resolved dispute awards.';
            END IF;
        END IF;
    END IF;

    SET NEW.payment_status       = 'PENDING';
    SET NEW.paid_at              = NULL;
    SET NEW.confirmed_by_user_id = NULL;
END$$

DROP TRIGGER IF EXISTS trg_payment_bu$$
CREATE TRIGGER trg_payment_bu
BEFORE UPDATE ON payment
FOR EACH ROW
BEGIN
    DECLARE v_webhook_ok INT DEFAULT 0;

    IF NEW.loan_id <> OLD.loan_id OR NEW.payer_id <> OLD.payer_id OR NEW.payee_id <> OLD.payee_id
       OR NEW.amount <> OLD.amount OR NEW.payment_type <> OLD.payment_type
       OR NOT (NEW.refund_for_payment_id <=> OLD.refund_for_payment_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Payment loan, parties, type, amount and refund source cannot be changed.';
    END IF;

    IF NEW.payment_status <> OLD.payment_status THEN
        IF OLD.payment_status <> 'PENDING' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only PENDING payments can change status.';
        END IF;

        IF NEW.payment_status = 'COMPLETED' THEN
            IF NEW.method IN ('UPI','CARD') THEN
                IF NEW.transaction_reference IS NULL OR NEW.gateway_order_id IS NULL THEN
                    SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'UPI/CARD completion requires gateway_order_id and transaction_reference.';
                END IF;
                SELECT COUNT(*) INTO v_webhook_ok
                  FROM payment_webhook_event w
                 WHERE w.payment_id = NEW.payment_id
                   AND w.signature_verified = 1
                   AND w.event_status = 'VERIFIED'
                   AND w.amount_reported = NEW.amount
                   AND w.transaction_reference = NEW.transaction_reference;
                IF v_webhook_ok = 0 THEN
                    SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'UPI/CARD payment cannot be marked COMPLETED without a signature-verified webhook event.';
                END IF;
            ELSEIF NEW.method = 'CASH' THEN
                IF NEW.confirmed_by_user_id IS NULL OR NEW.confirmed_by_user_id <> OLD.payee_id THEN
                    SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'CASH payment completion requires explicit confirmation by the payee.';
                END IF;
            END IF;
            SET NEW.paid_at = IFNULL(NEW.paid_at, UTC_TIMESTAMP());
        END IF;
    END IF;
END$$

DROP TRIGGER IF EXISTS trg_payment_au$$
CREATE TRIGGER trg_payment_au
AFTER UPDATE ON payment
FOR EACH ROW
BEGIN
    IF NEW.payment_status <> OLD.payment_status THEN
        IF NEW.payment_status = 'COMPLETED' AND NEW.payment_type = 'DEPOSIT' THEN
            UPDATE loan SET deposit_status = 'HELD'
             WHERE loan_id = NEW.loan_id AND deposit_status = 'NOT_PAID';
        END IF;

        INSERT INTO notification (user_id, related_loan_id, reference_type, reference_id, type, title, message)
        VALUES (NEW.payee_id, NEW.loan_id, 'payment', NEW.payment_id, 'PAYMENT_UPDATE', 'Payment update',
                CONCAT(NEW.payment_type, ' of ', NEW.amount, ' is now ', NEW.payment_status, '.'));

        INSERT INTO application_audit_log (actor_id, action, entity_type, entity_id, old_value, new_value)
        VALUES (@current_user_id, 'PAYMENT_STATUS_CHANGED', 'payment', NEW.payment_id,
                JSON_OBJECT('status', OLD.payment_status), JSON_OBJECT('status', NEW.payment_status));
    END IF;
END$$

-- ----------------------------- dispute -------------------------------
DROP TRIGGER IF EXISTS trg_dispute_bi$$
CREATE TRIGGER trg_dispute_bi
BEFORE INSERT ON dispute
FOR EACH ROW
BEGIN
    DECLARE v_status   VARCHAR(20);
    DECLARE v_borrower INT;
    DECLARE v_owner    INT;
    DECLARE v_ok       INT DEFAULT 0;

    SELECT l.status, br.borrower_id, i.owner_id
      INTO v_status, v_borrower, v_owner
      FROM loan l
      JOIN borrow_request br ON br.request_id = l.request_id
      JOIN item i ON i.item_id = br.item_id
     WHERE l.loan_id = NEW.loan_id;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Loan not found.';
    END IF;
    IF v_status NOT IN ('SCHEDULED','ACTIVE','OVERDUE','RETURNED') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Disputes cannot be raised on a cancelled loan.';
    END IF;
    IF v_status = 'SCHEDULED' AND NEW.dispute_type <> 'NO_SHOW' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only NO_SHOW disputes can be raised on a SCHEDULED loan.';
    END IF;
    IF NEW.raised_by NOT IN (v_borrower, v_owner) OR NEW.against_user_id NOT IN (v_borrower, v_owner) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Both parties of a dispute must be the loan owner and borrower.';
    END IF;
    IF NEW.inspection_id IS NOT NULL THEN
        SELECT COUNT(*) INTO v_ok FROM loan_inspection
         WHERE inspection_id = NEW.inspection_id AND loan_id = NEW.loan_id;
        IF v_ok = 0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'The linked inspection does not belong to this loan.';
        END IF;
    END IF;

    SET NEW.status = 'OPEN';
    SET NEW.resolved_by = NULL;
    SET NEW.resolved_at = NULL;
    SET NEW.amount_awarded = 0.00;
END$$

DROP TRIGGER IF EXISTS trg_dispute_bu$$
CREATE TRIGGER trg_dispute_bu
BEFORE UPDATE ON dispute
FOR EACH ROW
BEGIN
    DECLARE v_ok INT DEFAULT 0;

    IF NEW.loan_id <> OLD.loan_id OR NEW.raised_by <> OLD.raised_by
       OR NEW.against_user_id <> OLD.against_user_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Dispute loan and parties cannot be changed.';
    END IF;

    IF NEW.resolved_by IS NOT NULL AND NOT (NEW.resolved_by <=> OLD.resolved_by) THEN
        SELECT COUNT(*) INTO v_ok FROM app_user
         WHERE user_id = NEW.resolved_by AND role IN ('MODERATOR','ADMIN')
           AND is_active = 1 AND deleted_at IS NULL;
        IF v_ok = 0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only an active moderator or admin can handle disputes.';
        END IF;
        IF NEW.resolved_by IN (NEW.raised_by, NEW.against_user_id) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A party to the dispute cannot resolve it.';
        END IF;
    END IF;

    IF NEW.status <> OLD.status THEN
        IF NOT ((OLD.status = 'OPEN'         AND NEW.status IN ('UNDER_REVIEW','RESOLVED','REJECTED'))
             OR (OLD.status = 'UNDER_REVIEW' AND NEW.status IN ('RESOLVED','REJECTED'))) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid dispute status transition.';
        END IF;
        IF NEW.status IN ('RESOLVED','REJECTED') THEN
            IF NEW.resolved_by IS NULL THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A resolver (moderator/admin) is required to close a dispute.';
            END IF;
            SET NEW.resolved_at = IFNULL(NEW.resolved_at, UTC_TIMESTAMP());
            IF NEW.status = 'REJECTED' THEN
                SET NEW.amount_awarded = 0.00;
            END IF;
        END IF;
    END IF;
END$$

DROP TRIGGER IF EXISTS trg_dispute_au$$
CREATE TRIGGER trg_dispute_au
AFTER UPDATE ON dispute
FOR EACH ROW
BEGIN
    IF NEW.status <> OLD.status THEN
        INSERT INTO notification (user_id, related_loan_id, reference_type, reference_id, type, title, message)
        VALUES (NEW.raised_by, NEW.loan_id, 'dispute', NEW.dispute_id, 'DISPUTE_UPDATE', 'Dispute update',
                CONCAT('Your dispute is now ', NEW.status, '.')),
               (NEW.against_user_id, NEW.loan_id, 'dispute', NEW.dispute_id, 'DISPUTE_UPDATE', 'Dispute update',
                CONCAT('A dispute against you is now ', NEW.status, '.'));

        INSERT INTO application_audit_log (actor_id, action, entity_type, entity_id, old_value, new_value)
        VALUES (@current_user_id, 'DISPUTE_STATUS_CHANGED', 'dispute', NEW.dispute_id,
                JSON_OBJECT('status', OLD.status), JSON_OBJECT('status', NEW.status, 'awarded', NEW.amount_awarded));
    END IF;
END$$

-- ------------------------ conversation / message ---------------------
DROP TRIGGER IF EXISTS trg_conversation_bi$$
CREATE TRIGGER trg_conversation_bi
BEFORE INSERT ON conversation
FOR EACH ROW
BEGIN
    DECLARE v_owner INT;
    DECLARE v_ok    INT DEFAULT 0;
    SELECT owner_id INTO v_owner FROM item WHERE item_id = NEW.item_id AND deleted_at IS NULL;
    IF v_owner IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Item not found.';
    END IF;
    IF v_owner = NEW.borrower_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'You cannot start a conversation about your own item.';
    END IF;
    SELECT COUNT(*) INTO v_ok FROM app_user
     WHERE user_id = NEW.borrower_id AND is_active = 1 AND deleted_at IS NULL;
    IF v_ok = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only active users can start conversations.';
    END IF;
END$$

DROP TRIGGER IF EXISTS trg_message_bi$$
CREATE TRIGGER trg_message_bi
BEFORE INSERT ON message
FOR EACH ROW
BEGIN
    DECLARE v_borrower INT;
    DECLARE v_owner    INT;
    DECLARE v_ok       INT DEFAULT 0;
    SELECT c.borrower_id, i.owner_id INTO v_borrower, v_owner
      FROM conversation c JOIN item i ON i.item_id = c.item_id
     WHERE c.conversation_id = NEW.conversation_id;
    IF v_borrower IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Conversation not found.';
    END IF;
    IF NEW.sender_id NOT IN (v_borrower, v_owner) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only the two participants can send messages here.';
    END IF;
    SELECT COUNT(*) INTO v_ok FROM app_user
     WHERE user_id = NEW.sender_id AND is_active = 1 AND deleted_at IS NULL;
    IF v_ok = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Suspended users cannot send messages.';
    END IF;
END$$

DROP TRIGGER IF EXISTS trg_message_ai$$
CREATE TRIGGER trg_message_ai
AFTER INSERT ON message
FOR EACH ROW
BEGIN
    UPDATE conversation SET last_message_at = NEW.sent_at
     WHERE conversation_id = NEW.conversation_id;
END$$

-- =====================================================================
-- 4. STORED PROCEDURES (Transactional Workflows)
-- =====================================================================

DROP PROCEDURE IF EXISTS sp_run_system_maintenance$$
CREATE PROCEDURE sp_run_system_maintenance(IN p_source VARCHAR(20))
BEGIN
    DECLARE v_done       TINYINT(1) DEFAULT 0;
    DECLARE v_req_id     INT;
    DECLARE v_overdue    INT DEFAULT 0;
    DECLARE v_expired    INT DEFAULT 0;
    DECLARE v_noshows    INT DEFAULT 0;
    DECLARE v_purged     INT DEFAULT 0;

    DECLARE cur_expired_scheduled CURSOR FOR
        SELECT br.request_id
          FROM borrow_request br
          JOIN loan l ON l.request_id = br.request_id
         WHERE br.status = 'APPROVED'
           AND l.status = 'SCHEDULED'
           AND br.start_date < fn_campus_today()
           AND NOT EXISTS (
               SELECT 1 FROM dispute d
                WHERE d.loan_id = l.loan_id AND d.status IN ('OPEN','UNDER_REVIEW')
           );
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_done = 1;

    UPDATE loan SET status = 'OVERDUE'
     WHERE status = 'ACTIVE' AND due_at < UTC_TIMESTAMP();
    SET v_overdue = ROW_COUNT();

    UPDATE loan
       SET late_fee = CEIL(TIMESTAMPDIFF(SECOND, due_at, UTC_TIMESTAMP()) / 86400) * agreed_daily_fee
     WHERE status = 'OVERDUE';

    UPDATE borrow_request
       SET status = 'CANCELLED', decision_note = 'Expired: start date passed without a decision.'
     WHERE status = 'PENDING' AND start_date < fn_campus_today();
    SET v_expired = ROW_COUNT();

    OPEN cur_expired_scheduled;
    read_loop: LOOP
        FETCH cur_expired_scheduled INTO v_req_id;
        IF v_done = 1 THEN
            LEAVE read_loop;
        END IF;
        UPDATE borrow_request
           SET status = 'CANCELLED',
               decision_note = 'Expired: approved loan was never handed over.'
         WHERE request_id = v_req_id
           AND status = 'APPROVED';
        SET v_noshows = v_noshows + ROW_COUNT();
    END LOOP;
    CLOSE cur_expired_scheduled;

    DELETE FROM auth_token WHERE expires_at < UTC_TIMESTAMP() - INTERVAL 7 DAY;
    SET v_purged = ROW_COUNT();

    INSERT INTO system_job_log (
        job_name, triggered_by, overdue_marked, requests_expired, no_shows_expired, tokens_purged
    )
    VALUES (
        'sp_run_system_maintenance',
        IF(p_source IN ('EVENT_SCHEDULER','ON_DEMAND','CRON'), p_source, 'ON_DEMAND'),
        v_overdue, v_expired, v_noshows, v_purged
    );
END$$

DROP PROCEDURE IF EXISTS sp_approve_request$$
CREATE PROCEDURE sp_approve_request(
    IN  p_request_id   INT,
    IN  p_owner_id     INT,
    IN  p_note         TEXT,
    OUT p_handover_otp CHAR(6),
    OUT p_return_otp   CHAR(6)
)
BEGIN
    DECLARE v_item    INT;
    DECLARE v_start   DATE;
    DECLARE v_end     DATE;
    DECLARE v_status  VARCHAR(20);
    DECLARE v_owner   INT;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        SET @pending_handover_otp_hash = NULL;
        SET @pending_return_otp_hash   = NULL;
        ROLLBACK;
        RESIGNAL;
    END;

    CALL sp_run_system_maintenance('ON_DEMAND');

    START TRANSACTION;
    SET @current_user_id = p_owner_id;

    SELECT item_id, start_date, end_date INTO v_item, v_start, v_end
      FROM borrow_request WHERE request_id = p_request_id;
    IF v_item IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Request not found.';
    END IF;

    SELECT owner_id INTO v_owner FROM item WHERE item_id = v_item FOR UPDATE;
    SELECT status INTO v_status FROM borrow_request WHERE request_id = p_request_id FOR UPDATE;

    IF v_owner <> p_owner_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only the item owner can approve a request.';
    END IF;
    IF v_status <> 'PENDING' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only PENDING requests can be approved.';
    END IF;
    IF fn_item_is_available(v_item, v_start, v_end) = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Item is unavailable or dates are already booked.';
    END IF;

    SET p_handover_otp = LPAD(FLOOR(RAND() * 1000000), 6, '0');
    SET p_return_otp   = LPAD(FLOOR(RAND() * 1000000), 6, '0');
    SET @pending_handover_otp_hash = SHA2(p_handover_otp, 256);
    SET @pending_return_otp_hash   = SHA2(p_return_otp, 256);

    UPDATE borrow_request SET status = 'APPROVED', decision_note = p_note
     WHERE request_id = p_request_id;

    SET @pending_handover_otp_hash = NULL;
    SET @pending_return_otp_hash   = NULL;

    UPDATE borrow_request
       SET status = 'REJECTED', decision_note = 'Dates no longer available.'
     WHERE item_id = v_item AND status = 'PENDING' AND request_id <> p_request_id
       AND start_date <= v_end AND end_date >= v_start;

    COMMIT;
END$$

DROP PROCEDURE IF EXISTS sp_reject_request$$
CREATE PROCEDURE sp_reject_request(IN p_request_id INT, IN p_owner_id INT, IN p_note TEXT)
BEGIN
    DECLARE v_item   INT;
    DECLARE v_status VARCHAR(20);
    DECLARE v_owner  INT;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;
    SET @current_user_id = p_owner_id;

    SELECT item_id INTO v_item FROM borrow_request WHERE request_id = p_request_id;
    IF v_item IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Request not found.';
    END IF;

    SELECT owner_id INTO v_owner FROM item WHERE item_id = v_item FOR UPDATE;
    SELECT status INTO v_status FROM borrow_request WHERE request_id = p_request_id FOR UPDATE;

    IF v_owner <> p_owner_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only the item owner can reject a request.';
    END IF;
    IF v_status <> 'PENDING' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only PENDING requests can be rejected.';
    END IF;

    UPDATE borrow_request SET status = 'REJECTED', decision_note = p_note
     WHERE request_id = p_request_id;
    COMMIT;
END$$

DROP PROCEDURE IF EXISTS sp_cancel_request$$
CREATE PROCEDURE sp_cancel_request(IN p_request_id INT, IN p_borrower_id INT, IN p_note TEXT)
BEGIN
    DECLARE v_item     INT;
    DECLARE v_status   VARCHAR(20);
    DECLARE v_borrower INT;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;
    SET @current_user_id = p_borrower_id;

    SELECT item_id INTO v_item FROM borrow_request WHERE request_id = p_request_id;
    IF v_item IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Request not found.';
    END IF;

    SELECT item_id INTO v_item FROM item WHERE item_id = v_item FOR UPDATE;
    SELECT status, borrower_id INTO v_status, v_borrower
      FROM borrow_request WHERE request_id = p_request_id FOR UPDATE;

    IF v_borrower <> p_borrower_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only the borrower can cancel this request.';
    END IF;
    IF v_status NOT IN ('PENDING','APPROVED') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'This request can no longer be cancelled.';
    END IF;

    UPDATE borrow_request SET status = 'CANCELLED', decision_note = p_note
     WHERE request_id = p_request_id;
    COMMIT;
END$$

DROP PROCEDURE IF EXISTS sp_process_payment_webhook$$
CREATE PROCEDURE sp_process_payment_webhook(
    IN p_payment_id            INT,
    IN p_gateway_event_id      VARCHAR(160),
    IN p_event_type            VARCHAR(30),
    IN p_amount_reported       DECIMAL(10,2),
    IN p_gateway_order_id      VARCHAR(100),
    IN p_transaction_reference VARCHAR(160),
    IN p_signature_verified    TINYINT(1),
    IN p_payload               JSON
)
BEGIN
    DECLARE v_loan_id  INT;
    DECLARE v_expected DECIMAL(10,2);
    DECLARE v_status   VARCHAR(20);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    SELECT loan_id, amount, payment_status
      INTO v_loan_id, v_expected, v_status
      FROM payment WHERE payment_id = p_payment_id FOR UPDATE;

    IF v_loan_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Payment not found.';
    END IF;
    IF p_signature_verified <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Webhook signature verification failed.';
    END IF;
    IF p_amount_reported <> v_expected THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Webhook reported amount does not match payment amount.';
    END IF;

    INSERT INTO payment_webhook_event (
        payment_id, gateway_event_id, event_type, amount_reported,
        transaction_reference, signature_verified, event_status, payload, processed_at
    )
    VALUES (
        p_payment_id, p_gateway_event_id, p_event_type, p_amount_reported,
        p_transaction_reference, 1, 'VERIFIED', p_payload, UTC_TIMESTAMP()
    );

    IF v_status = 'PENDING' THEN
        IF p_event_type IN ('PAYMENT_CAPTURED','REFUND_PROCESSED') THEN
            UPDATE payment
               SET gateway_order_id      = p_gateway_order_id,
                   transaction_reference = p_transaction_reference,
                   payment_status        = 'COMPLETED',
                   paid_at               = UTC_TIMESTAMP()
             WHERE payment_id = p_payment_id;
        ELSEIF p_event_type = 'PAYMENT_FAILED' THEN
            UPDATE payment
               SET gateway_order_id      = p_gateway_order_id,
                   transaction_reference = p_transaction_reference,
                   payment_status        = 'FAILED'
             WHERE payment_id = p_payment_id;
        END IF;
    END IF;

    COMMIT;
END$$

DROP PROCEDURE IF EXISTS sp_confirm_cash_payment$$
CREATE PROCEDURE sp_confirm_cash_payment(
    IN p_payment_id INT,
    IN p_payee_id   INT,
    IN p_receipt_no VARCHAR(160)
)
BEGIN
    DECLARE v_payee  INT;
    DECLARE v_method VARCHAR(10);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;
    SET @current_user_id = p_payee_id;

    SELECT payee_id, method INTO v_payee, v_method
      FROM payment WHERE payment_id = p_payment_id FOR UPDATE;

    IF v_payee IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Payment not found.';
    END IF;
    IF v_method <> 'CASH' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only CASH payments can be confirmed with sp_confirm_cash_payment.';
    END IF;
    IF v_payee <> p_payee_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only the payee can confirm receipt of a CASH payment.';
    END IF;

    UPDATE payment
       SET confirmed_by_user_id  = p_payee_id,
           transaction_reference = p_receipt_no,
           payment_status        = 'COMPLETED',
           paid_at               = UTC_TIMESTAMP()
     WHERE payment_id = p_payment_id;

    COMMIT;
END$$

DROP PROCEDURE IF EXISTS sp_submit_inspection$$
CREATE PROCEDURE sp_submit_inspection(
    IN  p_loan_id       INT,
    IN  p_inspector_id  INT,
    IN  p_stage         VARCHAR(10),
    IN  p_condition     VARCHAR(20),
    IN  p_notes         TEXT,
    OUT p_inspection_id INT
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;
    SET @current_user_id = p_inspector_id;

    INSERT INTO loan_inspection (loan_id, stage, inspected_by, condition_found, notes)
    VALUES (p_loan_id, p_stage, p_inspector_id, p_condition, p_notes);

    SET p_inspection_id = LAST_INSERT_ID();
    COMMIT;
END$$

DROP PROCEDURE IF EXISTS sp_confirm_inspection$$
CREATE PROCEDURE sp_confirm_inspection(
    IN p_inspection_id      INT,
    IN p_confirming_user_id INT,
    IN p_agree              TINYINT(1),
    IN p_otp                CHAR(6),
    IN p_counterparty_notes TEXT
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;
    SET @current_user_id = p_confirming_user_id;

    IF p_agree = 1 THEN
        UPDATE loan_inspection
           SET confirmed_by       = p_confirming_user_id,
               provided_otp_hash  = SHA2(p_otp, 256),
               counterparty_notes = p_counterparty_notes,
               inspection_status  = 'VERIFIED'
         WHERE inspection_id = p_inspection_id;
    ELSE
        UPDATE loan_inspection
           SET confirmed_by       = p_confirming_user_id,
               counterparty_notes = p_counterparty_notes,
               inspection_status  = 'DISPUTED'
         WHERE inspection_id = p_inspection_id;
    END IF;

    COMMIT;
END$$

DROP PROCEDURE IF EXISTS sp_settle_deposit$$
CREATE PROCEDURE sp_settle_deposit(
    IN p_loan_id       INT,
    IN p_deduct        DECIMAL(10,2),
    IN p_actor_id      INT,
    IN p_refund_method VARCHAR(10)
)
BEGIN
    DECLARE v_status         VARCHAR(20);
    DECLARE v_dep_state      VARCHAR(20);
    DECLARE v_deposit        DECIMAL(10,2);
    DECLARE v_borrower       INT;
    DECLARE v_owner          INT;
    DECLARE v_is_mod         INT DEFAULT 0;
    DECLARE v_open_dispute   INT DEFAULT 0;
    DECLARE v_dep_payment_id INT;
    DECLARE v_ded_payment_id INT;
    DECLARE v_new_state      VARCHAR(20);
    DECLARE v_refund         DECIMAL(10,2);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;
    SET @current_user_id = p_actor_id;

    SELECT l.status, l.deposit_status, l.agreed_deposit, br.borrower_id, i.owner_id
      INTO v_status, v_dep_state, v_deposit, v_borrower, v_owner
      FROM loan l
      JOIN borrow_request br ON br.request_id = l.request_id
      JOIN item i ON i.item_id = br.item_id
     WHERE l.loan_id = p_loan_id
       FOR UPDATE;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Loan not found.';
    END IF;

    SELECT COUNT(*) INTO v_is_mod FROM app_user
     WHERE user_id = p_actor_id AND role IN ('MODERATOR','ADMIN') AND is_active = 1;
    IF p_actor_id <> v_owner AND v_is_mod = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only the item owner or a moderator can settle a deposit.';
    END IF;

    SELECT COUNT(*) INTO v_open_dispute FROM dispute
     WHERE loan_id = p_loan_id AND status IN ('OPEN','UNDER_REVIEW');
    IF v_open_dispute > 0 AND v_is_mod = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cannot settle deposit while an open dispute exists unless resolved by a moderator.';
    END IF;

    IF v_dep_state <> 'HELD' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'There is no held deposit to settle.';
    END IF;
    IF v_status NOT IN ('RETURNED','CANCELLED') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Deposit can only be settled after return or cancellation.';
    END IF;
    IF p_deduct < 0 OR p_deduct > v_deposit THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Deduction must be between 0 and the deposit amount.';
    END IF;
    IF v_status = 'CANCELLED' AND p_deduct > 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No deduction is allowed on a cancelled loan.';
    END IF;

    SELECT payment_id INTO v_dep_payment_id
      FROM payment
     WHERE loan_id = p_loan_id AND payment_type = 'DEPOSIT' AND payment_status = 'COMPLETED'
     LIMIT 1;

    IF v_dep_payment_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Original completed deposit payment record not found.';
    END IF;

    SET v_refund = v_deposit - p_deduct;
    SET v_new_state = CASE WHEN p_deduct = 0 THEN 'RELEASED'
                           WHEN p_deduct = v_deposit THEN 'FORFEITED'
                           ELSE 'PARTIAL' END;

    UPDATE loan SET deposit_status = v_new_state, deposit_deducted = p_deduct
     WHERE loan_id = p_loan_id;

    -- Record the deduction in payment so vw_loan_financial_ledger is 100% balanced
    IF p_deduct > 0 THEN
        INSERT INTO payment (loan_id, payer_id, payee_id, payment_type, method, amount)
        VALUES (p_loan_id, v_borrower, v_owner, 'DAMAGE_DEDUCTION', 'CASH', p_deduct);
        SET v_ded_payment_id = LAST_INSERT_ID();

        UPDATE payment
           SET confirmed_by_user_id  = v_owner,
               transaction_reference = CONCAT('DEP_DEDUCT_LOAN_', p_loan_id, '_', v_ded_payment_id),
               payment_status        = 'COMPLETED',
               paid_at               = UTC_TIMESTAMP()
         WHERE payment_id = v_ded_payment_id;
    END IF;

    IF v_refund > 0 THEN
        INSERT INTO payment (
            loan_id, payer_id, payee_id, payment_type, method, amount,
            refund_for_payment_id, refund_reason
        )
        VALUES (
            p_loan_id, v_owner, v_borrower, 'REFUND', p_refund_method, v_refund,
            v_dep_payment_id, IF(v_status = 'CANCELLED', 'CANCELLED_LOAN', 'DEPOSIT_SETTLEMENT')
        );
    END IF;

    COMMIT;
END$$

-- =====================================================================
-- 5. SCHEDULED EVENTS
-- =====================================================================

DROP EVENT IF EXISTS ev_loan_maintenance$$
CREATE EVENT ev_loan_maintenance
ON SCHEDULE EVERY 15 MINUTE
DO
BEGIN
    CALL sp_run_system_maintenance('EVENT_SCHEDULER');
END$$

DROP EVENT IF EXISTS ev_purge_old_tokens$$
CREATE EVENT ev_purge_old_tokens
ON SCHEDULE EVERY 1 DAY
DO
BEGIN
    DELETE FROM auth_token WHERE expires_at < UTC_TIMESTAMP() - INTERVAL 7 DAY;
END$$

-- =====================================================================
-- 6. AUTOMATED END-TO-END VERIFICATION SUITE
-- =====================================================================

DROP PROCEDURE IF EXISTS sp_verify_all_workflows$$
CREATE PROCEDURE sp_verify_all_workflows()
BEGIN
    DECLARE v_owner_id    INT;
    DECLARE v_borrower_id INT;
    DECLARE v_other_id    INT;
    DECLARE v_cat_id      INT;
    DECLARE v_loc_id      INT;
    DECLARE v_item_id     INT;
    DECLARE v_req1_id     INT;
    DECLARE v_req2_id     INT;
    DECLARE v_loan_id     INT;
    DECLARE v_dep_pay_id  INT;
    DECLARE v_fee_pay_id  INT;
    DECLARE v_ref_pay_id  INT;
    DECLARE v_insp_ho_id  INT;
    DECLARE v_insp_ret_id INT;
    DECLARE v_ho_otp      CHAR(6);
    DECLARE v_ret_otp     CHAR(6);
    DECLARE v_loan_state  VARCHAR(20);
    DECLARE v_req2_state  VARCHAR(20);

    INSERT INTO app_user (roll_number, full_name, svnit_email, hostel_or_dept, password_hash, is_verified, is_active)
    VALUES ('U23CS001', 'Aarav Patel', 'u23cs001@svnit.ac.in', 'Bhabha Bhavan', 'hash_owner', 1, 1);
    SET v_owner_id = LAST_INSERT_ID();

    INSERT INTO app_user (roll_number, full_name, svnit_email, hostel_or_dept, password_hash, is_verified, is_active)
    VALUES ('U23CS002', 'Priya Shah',  'u23cs002@svnit.ac.in', 'Mother Teresa Bhavan', 'hash_borrower', 1, 1);
    SET v_borrower_id = LAST_INSERT_ID();

    INSERT INTO app_user (roll_number, full_name, svnit_email, hostel_or_dept, password_hash, is_verified, is_active)
    VALUES ('U23CS003', 'Rohan Mehta', 'u23cs003@svnit.ac.in', 'Gajjar Bhavan', 'hash_other', 1, 1);
    SET v_other_id = LAST_INSERT_ID();

    SELECT category_id INTO v_cat_id FROM category WHERE category_name = 'Electronics' LIMIT 1;
    SELECT location_id INTO v_loc_id FROM pickup_location WHERE name = 'Bhabha Bhavan' LIMIT 1;

    INSERT INTO item (owner_id, category_id, location_id, title, description, item_condition, deposit_amount, daily_fee, max_borrow_days)
    VALUES (v_owner_id, v_cat_id, v_loc_id, 'Arduino Uno R4 WiFi Kit', 'Complete sensor kit with breadboard', 'GOOD', 500.00, 50.00, 7);
    SET v_item_id = LAST_INSERT_ID();

    INSERT INTO borrow_request (item_id, borrower_id, start_date, end_date, request_message)
    VALUES (v_item_id, v_borrower_id, fn_campus_today(), fn_campus_today() + INTERVAL 2 DAY, 'Need for embedded lab');
    SET v_req1_id = LAST_INSERT_ID();

    INSERT INTO borrow_request (item_id, borrower_id, start_date, end_date, request_message)
    VALUES (v_item_id, v_other_id, fn_campus_today() + INTERVAL 1 DAY, fn_campus_today() + INTERVAL 3 DAY, 'Need for mini project');
    SET v_req2_id = LAST_INSERT_ID();

    CALL sp_approve_request(v_req1_id, v_owner_id, 'Meet at Bhabha reception at 6 PM', v_ho_otp, v_ret_otp);

    SELECT status INTO v_req2_state FROM borrow_request WHERE request_id = v_req2_id;
    IF v_req2_state <> 'REJECTED' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Verification failed: Overlapping request was not auto-rejected.';
    END IF;

    SELECT loan_id INTO v_loan_id FROM loan WHERE request_id = v_req1_id;

    INSERT INTO payment (loan_id, payer_id, payee_id, payment_type, method, amount)
    VALUES (v_loan_id, v_borrower_id, v_owner_id, 'DEPOSIT', 'UPI', 500.00);
    SET v_dep_pay_id = LAST_INSERT_ID();

    CALL sp_process_payment_webhook(
        v_dep_pay_id, 'evt_verify_dep_001', 'PAYMENT_CAPTURED', 500.00,
        'order_dep_001', 'txn_dep_001', 1, JSON_OBJECT('verified', true)
    );

    INSERT INTO payment (loan_id, payer_id, payee_id, payment_type, method, amount)
    VALUES (v_loan_id, v_borrower_id, v_owner_id, 'RENTAL_FEE', 'UPI', 150.00);
    SET v_fee_pay_id = LAST_INSERT_ID();

    CALL sp_process_payment_webhook(
        v_fee_pay_id, 'evt_verify_fee_001', 'PAYMENT_CAPTURED', 150.00,
        'order_fee_001', 'txn_fee_001', 1, JSON_OBJECT('verified', true)
    );

    CALL sp_submit_inspection(v_loan_id, v_owner_id, 'HANDOVER', 'GOOD', 'All jumper wires and board tested', v_insp_ho_id);
    SELECT status INTO v_loan_state FROM loan WHERE loan_id = v_loan_id;
    IF v_loan_state <> 'SCHEDULED' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Verification failed: Loan became ACTIVE before counterparty confirmed.';
    END IF;

    CALL sp_confirm_inspection(v_insp_ho_id, v_borrower_id, 1, v_ho_otp, 'Checked and received in good condition');
    SELECT status INTO v_loan_state FROM loan WHERE loan_id = v_loan_id;
    IF v_loan_state <> 'ACTIVE' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Verification failed: Loan did not transition to ACTIVE after 2-party verification.';
    END IF;

    CALL sp_submit_inspection(v_loan_id, v_borrower_id, 'RETURN', 'GOOD', 'Returning kit intact', v_insp_ret_id);
    CALL sp_confirm_inspection(v_insp_ret_id, v_owner_id, 1, v_ret_otp, 'Verified kit returned in good order');
    SELECT status INTO v_loan_state FROM loan WHERE loan_id = v_loan_id;
    IF v_loan_state <> 'RETURNED' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Verification failed: Loan did not transition to RETURNED after 2-party verification.';
    END IF;

    CALL sp_settle_deposit(v_loan_id, 50.00, v_owner_id, 'UPI');
    SELECT payment_id INTO v_ref_pay_id FROM payment
     WHERE loan_id = v_loan_id AND payment_type = 'REFUND' LIMIT 1;

    CALL sp_process_payment_webhook(
        v_ref_pay_id, 'evt_verify_ref_001', 'REFUND_PROCESSED', 450.00,
        'order_ref_001', 'txn_ref_001', 1, JSON_OBJECT('verified', true)
    );

    INSERT INTO review (loan_id, reviewer_id, reviewee_id, rating, review_text)
    VALUES (v_loan_id, v_owner_id, v_borrower_id, 5, 'Took great care of the Arduino kit!'),
           (v_loan_id, v_borrower_id, v_owner_id, 5, 'Smooth pickup and helpful owner.');
END$$

DELIMITER ;

-- =====================================================================
-- 7. VIEWS (Trust Score, Real-Time Availability, Ledger & Scheduler Health)
-- =====================================================================

CREATE OR REPLACE VIEW vw_user_trust_score AS
SELECT
    u.user_id,
    ROUND(AVG(r.rating), 2) AS trust_score,
    COUNT(r.review_id)      AS review_count
FROM app_user AS u
LEFT JOIN review AS r ON r.reviewee_id = u.user_id
GROUP BY u.user_id;

CREATE OR REPLACE VIEW vw_item_availability AS
SELECT
    i.item_id,
    i.owner_id,
    i.title,
    i.item_condition,
    i.listing_status,
    EXISTS (SELECT 1
              FROM borrow_request br
              JOIN loan l ON l.request_id = br.request_id
             WHERE br.item_id = i.item_id AND l.status IN ('ACTIVE','OVERDUE')) AS is_on_loan_now,
    EXISTS (SELECT 1 FROM booked_date bd
             WHERE bd.item_id = i.item_id AND bd.booked_date = fn_campus_today()) AS is_booked_today,
    (SELECT MIN(bd.booked_date) FROM booked_date bd
      WHERE bd.item_id = i.item_id AND bd.booked_date >= fn_campus_today())       AS next_booked_date,
    fn_item_is_available(i.item_id, fn_campus_today(), fn_campus_today())         AS is_available_today
FROM item AS i;

CREATE OR REPLACE VIEW vw_loan_details AS
SELECT
    l.loan_id, l.status AS loan_status, l.issued_at, l.due_at, l.returned_at,
    l.agreed_daily_fee, l.agreed_deposit, l.agreed_total_fee, l.late_fee,
    l.deposit_status, l.deposit_deducted,
    br.request_id, br.start_date, br.end_date,
    i.item_id, i.title AS item_title,
    i.owner_id,     ou.full_name AS owner_name,
    br.borrower_id, bu.full_name AS borrower_name
FROM loan l
JOIN borrow_request br ON br.request_id = l.request_id
JOIN item i            ON i.item_id = br.item_id
JOIN app_user ou       ON ou.user_id = i.owner_id
JOIN app_user bu       ON bu.user_id = br.borrower_id;

CREATE OR REPLACE VIEW vw_loan_financial_ledger AS
SELECT
    l.loan_id,
    l.status AS loan_status,
    l.agreed_deposit,
    l.agreed_total_fee,
    l.late_fee AS late_fee_accrued,
    l.deposit_status,
    l.deposit_deducted,
    COALESCE(SUM(CASE WHEN p.payment_type = 'DEPOSIT'    AND p.payment_status = 'COMPLETED' THEN p.amount ELSE 0 END), 0.00) AS deposit_paid,
    COALESCE(SUM(CASE WHEN p.payment_type = 'RENTAL_FEE' AND p.payment_status = 'COMPLETED' THEN p.amount ELSE 0 END), 0.00) AS rental_fee_paid,
    COALESCE(SUM(CASE WHEN p.payment_type = 'LATE_FEE'   AND p.payment_status = 'COMPLETED' THEN p.amount ELSE 0 END), 0.00) AS late_fee_paid,
    COALESCE(SUM(CASE WHEN p.payment_type IN ('DAMAGE_CHARGE','DAMAGE_DEDUCTION') AND p.payment_status = 'COMPLETED' THEN p.amount ELSE 0 END), 0.00) AS damage_paid,
    COALESCE(SUM(CASE WHEN p.payment_type = 'REFUND'     AND p.payment_status = 'COMPLETED' THEN p.amount ELSE 0 END), 0.00) AS total_refunded
FROM loan l
LEFT JOIN payment p ON p.loan_id = l.loan_id
GROUP BY l.loan_id;

CREATE OR REPLACE VIEW vw_scheduler_health AS
SELECT
    j.job_name,
    COUNT(*) AS total_runs,
    MAX(j.ran_at) AS last_maintenance_run_utc,
    TIMESTAMPDIFF(MINUTE, MAX(j.ran_at), UTC_TIMESTAMP()) AS minutes_since_last_run,
    SUM(j.overdue_marked) AS total_overdue_marked,
    SUM(j.requests_expired) AS total_requests_expired,
    SUM(j.no_shows_expired) AS total_no_shows_expired
FROM system_job_log AS j
GROUP BY j.job_name;

-- =====================================================================
-- 8. SEED DATA (SVNIT Campus Defaults)
-- =====================================================================
INSERT IGNORE INTO category (category_name, category_description) VALUES
 ('Books',               'Textbooks, reference books and novels'),
 ('Electronics',         'Calculators, Arduino kits, chargers, cables and gadgets'),
 ('Lab Equipment',       'Lab coats, drafters, multimeters, kits and instruments'),
 ('Sports',              'Bats, rackets, balls and fitness gear'),
 ('Tools',               'Hand tools, soldering irons and hardware'),
 ('Stationery',          'Pens, drawing sheets and project supplies'),
 ('Musical Instruments', 'Guitars, keyboards and accessories'),
 ('Others',              'Miscellaneous campus utility items');

INSERT IGNORE INTO pickup_location (name, description) VALUES
 ('Bhabha Bhavan',            'Bhabha Bhavan Hostel Main Gate / Reception'),
 ('Gajjar Bhavan',            'Gajjar Bhavan Hostel Main Gate / Reception'),
 ('Swami Vivekanand Bhavan',  'SVB Hostel Main Entrance'),
 ('Mother Teresa Bhavan',     'MTB Hostel Main Entrance'),
 ('CSE Department',           'Computer Science & Engineering Ground Floor Lobby'),
 ('Central Library',          'SVNIT Central Library Entrance'),
 ('Main Gate / SAC',          'Student Activity Centre / Main Gate Security Cabin');

-- =====================================================================
-- 9. LEAST-PRIVILEGE DATABASE ROLE (Security Boundary)
-- =====================================================================
CREATE ROLE IF NOT EXISTS 'borrowhub_app_role';
GRANT SELECT ON borrowhub.* TO 'borrowhub_app_role';
GRANT INSERT, UPDATE ON borrowhub.app_user TO 'borrowhub_app_role';
GRANT INSERT, UPDATE, DELETE ON borrowhub.auth_token TO 'borrowhub_app_role';
GRANT INSERT, UPDATE, DELETE ON borrowhub.device_token TO 'borrowhub_app_role';
GRANT INSERT, UPDATE ON borrowhub.item TO 'borrowhub_app_role';
GRANT INSERT, UPDATE, DELETE ON borrowhub.item_image TO 'borrowhub_app_role';
GRANT INSERT, DELETE ON borrowhub.favorite TO 'borrowhub_app_role';
GRANT INSERT ON borrowhub.borrow_request TO 'borrowhub_app_role';
GRANT INSERT ON borrowhub.payment TO 'borrowhub_app_role';
GRANT INSERT ON borrowhub.review TO 'borrowhub_app_role';
GRANT INSERT ON borrowhub.inspection_photo TO 'borrowhub_app_role';
GRANT INSERT ON borrowhub.conversation TO 'borrowhub_app_role';
GRANT INSERT, UPDATE ON borrowhub.message TO 'borrowhub_app_role';
GRANT INSERT, UPDATE ON borrowhub.dispute TO 'borrowhub_app_role';
GRANT INSERT ON borrowhub.dispute_evidence TO 'borrowhub_app_role';
GRANT UPDATE ON borrowhub.notification TO 'borrowhub_app_role';

GRANT EXECUTE ON PROCEDURE borrowhub.sp_run_system_maintenance  TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_approve_request         TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_reject_request          TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_cancel_request          TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_process_payment_webhook TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_confirm_cash_payment    TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_submit_inspection       TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_confirm_inspection      TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_settle_deposit          TO 'borrowhub_app_role';


-- =====================================================================
-- 10. RUNTIME CONFIGURATION (guards that must persist across sessions)
-- =====================================================================
-- Stored in a table (not in a session variable) so that the rule is
-- enforced identically for every client connection, including pooled
-- connections opened by the web application.

CREATE TABLE IF NOT EXISTS app_config (
    config_key   VARCHAR(60)  PRIMARY KEY,
    config_value VARCHAR(255) NOT NULL,
    description  VARCHAR(255) NULL,
    updated_at   DATETIME     NOT NULL DEFAULT (UTC_TIMESTAMP())
) ENGINE=InnoDB;

INSERT INTO app_config (config_key, config_value, description) VALUES
    ('enforce_office_hours', '0', 'Set to 1 to block borrow_request changes outside the office-hours window below'),
    ('office_hours_window',  '14:00-16:00', 'Allowed modification window on the working day'),
    ('office_hours_day',     'Monday',      'Allowed modification day')
ON DUPLICATE KEY UPDATE description = VALUES(description);


-- =====================================================================
-- 11. DATABASE ROLES (naive user / application developer / DBA)
-- =====================================================================

-- Naive end user: may only read the read-only availability catalogue.
CREATE ROLE IF NOT EXISTS 'borrowhub_naive_role';
GRANT SELECT ON borrowhub.vw_item_availability TO 'borrowhub_naive_role';

-- Application developer: full CRUD on application data + routine execution.
CREATE ROLE IF NOT EXISTS 'borrowhub_developer_role';
GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON borrowhub.* TO 'borrowhub_developer_role';

-- DBA: complete control of the schema.
CREATE ROLE IF NOT EXISTS 'borrowhub_dba_role';
GRANT ALL PRIVILEGES ON borrowhub.* TO 'borrowhub_dba_role';

DELIMITER $$

-- Helper used by the demo accounts below: create a login with a password.
DROP PROCEDURE IF EXISTS sp_create_role_user$$
CREATE PROCEDURE sp_create_role_user(IN p_user VARCHAR(80), IN p_password VARCHAR(120), IN p_role VARCHAR(80))
BEGIN
    DECLARE v_host VARCHAR(80) DEFAULT 'localhost';
    SET @ddl = CONCAT("CREATE USER IF NOT EXISTS '", p_user, "'@'", v_host, "' IDENTIFIED BY '", p_password, "'");
    PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    SET @ddl = CONCAT("GRANT '", p_role, "' TO '", p_user, "'@'", v_host, "'");
    PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    SET @ddl = CONCAT("SET DEFAULT ROLE '", p_role, "' FOR '", p_user, "'@'", v_host, "'");
    PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
END$$


-- =====================================================================
-- 12. STORED PROCEDURES FOR APPLICATION DATA MANIPULATION
--     (individual INSERT / UPDATE / DELETE routines)
-- =====================================================================

DROP PROCEDURE IF EXISTS sp_insert_item$$
CREATE PROCEDURE sp_insert_item(
    IN  p_owner_id  INT,
    IN  p_cat_id    INT,
    IN  p_loc_id    INT,
    IN  p_title     VARCHAR(160),
    IN  p_desc      TEXT,
    IN  p_cond      VARCHAR(20),
    IN  p_deposit   DECIMAL(10,2),
    IN  p_fee       DECIMAL(10,2),
    IN  p_max_days  INT,
    OUT p_new_item_id INT
)
BEGIN
    INSERT INTO item (owner_id, category_id, location_id, title, description,
                      item_condition, deposit_amount, daily_fee, max_borrow_days)
    VALUES (p_owner_id, p_cat_id, p_loc_id, p_title, p_desc, p_cond,
            p_deposit, p_fee, p_max_days);
    SET p_new_item_id = LAST_INSERT_ID();
END$$

DROP PROCEDURE IF EXISTS sp_update_item_fee$$
CREATE PROCEDURE sp_update_item_fee(IN p_item_id INT, IN p_new_fee DECIMAL(10,2))
BEGIN
    UPDATE item
       SET daily_fee = p_new_fee,
           updated_at = UTC_TIMESTAMP()
     WHERE item_id = p_item_id
       AND deleted_at IS NULL;
END$$

DROP PROCEDURE IF EXISTS sp_soft_delete_item$$
CREATE PROCEDURE sp_soft_delete_item(IN p_item_id INT)
BEGIN
    UPDATE item
       SET deleted_at = UTC_TIMESTAMP(),
           listing_status = 'ARCHIVED',
           updated_at = UTC_TIMESTAMP()
     WHERE item_id = p_item_id
       AND deleted_at IS NULL;
END$$


-- =====================================================================
-- 13. USER LOGIN DATA MANAGEMENT ROUTINES
-- =====================================================================

DROP PROCEDURE IF EXISTS sp_create_user$$
CREATE PROCEDURE sp_create_user(
    IN  p_roll       VARCHAR(30),
    IN  p_name       VARCHAR(120),
    IN  p_email      VARCHAR(254),
    IN  p_phone      VARCHAR(20),
    IN  p_hostel     VARCHAR(100),
    IN  p_pw_hash    VARCHAR(255),
    IN  p_role       VARCHAR(20),
    OUT p_user_id    INT
)
BEGIN
    INSERT INTO app_user (roll_number, full_name, svnit_email, phone, hostel_or_dept,
                          password_hash, role, is_verified, is_active)
    VALUES (UPPER(p_roll), p_name, LOWER(p_email), p_phone, p_hostel,
            p_pw_hash, p_role, 0, 1);
    SET p_user_id = LAST_INSERT_ID();
END$$

DROP PROCEDURE IF EXISTS sp_set_user_password$$
CREATE PROCEDURE sp_set_user_password(IN p_user_id INT, IN p_pw_hash VARCHAR(255))
BEGIN
    UPDATE app_user
       SET password_hash = p_pw_hash,
           updated_at = UTC_TIMESTAMP()
     WHERE user_id = p_user_id
       AND deleted_at IS NULL;
END$$

-- Reports the login / account data of one user: identity, role, verification
-- state, last successful sign-in, failed attempts and open sessions.
DROP PROCEDURE IF EXISTS sp_user_login_data$$
CREATE PROCEDURE sp_user_login_data(IN p_user_id INT)
BEGIN
    SELECT u.user_id,
           u.roll_number,
           u.full_name,
           u.svnit_email,
           u.role,
           u.is_verified,
           u.is_active,
           (SELECT MAX(a.created_at)
              FROM application_audit_log a
             WHERE a.entity_type = 'app_user'
               AND a.entity_id   = u.user_id
               AND a.action      = 'LOGIN_SUCCESS')                       AS last_login_at,
           (SELECT COUNT(*)
              FROM application_audit_log a
             WHERE a.entity_type = 'app_user'
               AND a.entity_id   = u.user_id
               AND a.action      = 'LOGIN_FAILED')                        AS failed_login_count,
           (SELECT COUNT(*)
              FROM auth_token t
             WHERE t.user_id    = u.user_id
               AND t.used_at   IS NULL
               AND t.expires_at > UTC_TIMESTAMP())                        AS active_sessions
      FROM app_user u
     WHERE u.user_id = p_user_id
       AND u.deleted_at IS NULL;
END$$

-- Single entry point for changing a login record: e-mail address, password
-- hash, or both. Any change revokes the user's existing sessions, because a
-- credential change must invalidate tokens issued under the old credential.
DROP PROCEDURE IF EXISTS sp_update_user_login$$
CREATE PROCEDURE sp_update_user_login(
    IN p_user_id     INT,
    IN p_email       VARCHAR(254),
    IN p_pw_hash     VARCHAR(255)
)
BEGIN
    DECLARE v_exists   INT DEFAULT 0;
    DECLARE v_taken    INT DEFAULT 0;
    DECLARE v_email    VARCHAR(254) DEFAULT NULL;
    DECLARE v_changed  INT DEFAULT 0;

    SELECT COUNT(*) INTO v_exists
      FROM app_user
     WHERE user_id = p_user_id AND deleted_at IS NULL;

    IF v_exists = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unknown or deleted user.';
    END IF;

    IF p_email IS NOT NULL AND TRIM(p_email) <> '' THEN
        SET v_email = LOWER(TRIM(p_email));

        IF v_email NOT LIKE '%@svnit.ac.in' AND v_email NOT LIKE '%@coed.svnit.ac.in' THEN
            SIGNAL SQLSTATE '45000'
               SET MESSAGE_TEXT = 'Login e-mail must be an official SVNIT address.';
        END IF;

        SELECT COUNT(*) INTO v_taken
          FROM app_user
         WHERE svnit_email = v_email AND user_id <> p_user_id;

        IF v_taken > 0 THEN
            SIGNAL SQLSTATE '45000'
               SET MESSAGE_TEXT = 'This e-mail is already used by another account.';
        END IF;

        SET v_changed = 1;
    END IF;

    IF p_pw_hash IS NOT NULL AND p_pw_hash <> '' THEN
        SET v_changed = 1;
    END IF;

    IF v_changed = 0 THEN
        SIGNAL SQLSTATE '45000'
           SET MESSAGE_TEXT = 'No login field supplied to update.';
    END IF;

    UPDATE app_user
       SET svnit_email        = COALESCE(v_email, svnit_email),
           password_hash      = COALESCE(NULLIF(p_pw_hash, ''), password_hash),
           password_changed_at = IF(p_pw_hash IS NOT NULL AND p_pw_hash <> '',
                                    UTC_TIMESTAMP(), password_changed_at),
           updated_at         = UTC_TIMESTAMP()
     WHERE user_id = p_user_id;

    -- Credential change invalidates every open session of that user: the
    -- outstanding one-time tokens are marked used and their life is expired.
    UPDATE auth_token
       SET used_at    = COALESCE(used_at, UTC_TIMESTAMP()),
           expires_at = UTC_TIMESTAMP()
     WHERE user_id = p_user_id
       AND expires_at > UTC_TIMESTAMP();

    INSERT INTO application_audit_log (actor_id, action, entity_type, entity_id, new_value)
    VALUES (p_user_id, 'LOGIN_DATA_UPDATED', 'app_user', p_user_id,
            JSON_OBJECT('email_changed', v_email IS NOT NULL,
                        'password_changed', (p_pw_hash IS NOT NULL AND p_pw_hash <> ''),
                        'sessions_revoked', 1));
END$$

-- Records every sign-in attempt (success or failure) into the audit trail.
DROP PROCEDURE IF EXISTS sp_record_login_attempt$$
CREATE PROCEDURE sp_record_login_attempt(
    IN p_user_id INT,
    IN p_email   VARCHAR(254),
    IN p_status  VARCHAR(20)
)
BEGIN
    INSERT INTO application_audit_log (actor_id, action, entity_type, entity_id, new_value)
    VALUES (p_user_id, CONCAT('LOGIN_', UPPER(p_status)), 'app_user', COALESCE(p_user_id, 0),
            JSON_OBJECT('email', p_email, 'status', p_status, 'at', UTC_TIMESTAMP()));
END$$


-- =====================================================================
-- 14. EXPLICIT CURSORS
-- =====================================================================

-- 14-A: explicit cursor WITHOUT a limit (iterates the whole table)
--       (a second unlimited cursor lives inside sp_run_system_maintenance)
DROP PROCEDURE IF EXISTS sp_cursor_items_unlimited$$
CREATE PROCEDURE sp_cursor_items_unlimited()
BEGIN
    DECLARE v_done  TINYINT(1) DEFAULT 0;
    DECLARE v_id    INT;
    DECLARE v_title VARCHAR(160);
    DECLARE v_fee   DECIMAL(10,2);

    DECLARE cur_items CURSOR FOR
        SELECT item_id, title, daily_fee
          FROM item
         WHERE deleted_at IS NULL
         ORDER BY item_id;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_done = 1;

    DROP TEMPORARY TABLE IF EXISTS tmp_cursor_items;
    CREATE TEMPORARY TABLE tmp_cursor_items (
        item_id   INT,
        title     VARCHAR(160),
        daily_fee DECIMAL(10,2),
        INDEX ix_tmp_cursor (item_id)
    );

    OPEN cur_items;
    read_loop: LOOP
        FETCH cur_items INTO v_id, v_title, v_fee;
        IF v_done = 1 THEN
            LEAVE read_loop;
        END IF;
        INSERT INTO tmp_cursor_items VALUES (v_id, v_title, v_fee);
    END LOOP;
    CLOSE cur_items;

    SELECT * FROM tmp_cursor_items;
    DROP TEMPORARY TABLE IF EXISTS tmp_cursor_items;
END$$

-- 14-B: explicit cursor WITH a limit
DROP PROCEDURE IF EXISTS sp_cursor_items_with_limit$$
CREATE PROCEDURE sp_cursor_items_with_limit(IN p_limit INT)
BEGIN
    DECLARE v_done  TINYINT(1) DEFAULT 0;
    DECLARE v_id    INT;
    DECLARE v_title VARCHAR(160);
    DECLARE v_fee   DECIMAL(10,2);
    DECLARE v_max   INT DEFAULT 5;

    IF p_limit IS NOT NULL AND p_limit > 0 THEN
        SET v_max = p_limit;
    END IF;

    DROP TEMPORARY TABLE IF EXISTS tmp_cursor_items;
    CREATE TEMPORARY TABLE tmp_cursor_items (
        item_id   INT,
        title     VARCHAR(160),
        daily_fee DECIMAL(10,2)
    );

    BEGIN
        DECLARE cur_items CURSOR FOR
            SELECT item_id, title, daily_fee
              FROM item
             WHERE deleted_at IS NULL
             ORDER BY item_id
             LIMIT v_max;
        DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_done = 1;

        OPEN cur_items;
        read_loop: LOOP
            FETCH cur_items INTO v_id, v_title, v_fee;
            IF v_done = 1 THEN
                LEAVE read_loop;
            END IF;
            INSERT INTO tmp_cursor_items VALUES (v_id, v_title, v_fee);
        END LOOP;
        CLOSE cur_items;
    END;

    SELECT * FROM tmp_cursor_items;
    DROP TEMPORARY TABLE IF EXISTS tmp_cursor_items;
END$$

-- =====================================================================
-- 15. PAGINATED SEARCH (function + procedure, with and without filters)
-- =====================================================================

DROP FUNCTION IF EXISTS fn_search_items_count$$
CREATE FUNCTION fn_search_items_count(p_keyword VARCHAR(100), p_category_id INT) RETURNS INT
DETERMINISTIC READS SQL DATA
BEGIN
    DECLARE v_cnt INT;
    SELECT COUNT(*) INTO v_cnt
      FROM item
     WHERE listing_status = 'ACTIVE'
       AND deleted_at IS NULL
       AND (p_keyword IS NULL OR p_keyword = ''
            OR title LIKE CONCAT('%', p_keyword, '%')
            OR description LIKE CONCAT('%', p_keyword, '%'))
       AND (p_category_id IS NULL OR category_id = p_category_id);
    RETURN v_cnt;
END$$

DROP PROCEDURE IF EXISTS sp_search_items_paginated$$
CREATE PROCEDURE sp_search_items_paginated(
    IN p_keyword     VARCHAR(100),
    IN p_category_id INT,
    IN p_limit       INT,
    IN p_offset      INT
)
BEGIN
    DECLARE v_limit  INT DEFAULT 10;
    DECLARE v_offset INT DEFAULT 0;

    SET v_limit  = IF(p_limit IS NULL OR p_limit <= 0, 10, p_limit);
    SET v_offset = IF(p_offset IS NULL OR p_offset < 0, 0, p_offset);

    SELECT i.item_id, i.title, i.item_condition, i.daily_fee, i.deposit_amount,
           i.max_borrow_days, c.category_name, pl.name AS pickup_location,
           fn_search_items_count(p_keyword, p_category_id) AS total_matches
      FROM item i
      JOIN category c        ON c.category_id = i.category_id
      LEFT JOIN pickup_location pl ON pl.location_id = i.location_id
     WHERE i.listing_status = 'ACTIVE'
       AND i.deleted_at IS NULL
       AND (p_keyword IS NULL OR p_keyword = ''
            OR i.title LIKE CONCAT('%', p_keyword, '%')
            OR i.description LIKE CONCAT('%', p_keyword, '%'))
       AND (p_category_id IS NULL OR i.category_id = p_category_id)
     ORDER BY i.created_at DESC
     LIMIT v_limit OFFSET v_offset;
END$$


-- =====================================================================
-- 16. NUMERIC COLUMN AGGREGATION (without grouping / with grouping)
-- =====================================================================

-- 16-A: without grouping (single aggregate over the whole table)
DROP FUNCTION IF EXISTS fn_sum_column_total$$
CREATE FUNCTION fn_sum_column_total(p_column VARCHAR(40)) RETURNS DECIMAL(14,2)
DETERMINISTIC READS SQL DATA
BEGIN
    DECLARE v_sum DECIMAL(14,2) DEFAULT 0.00;
    -- Whitelisted numeric columns only: the identifier cannot be user-injected.
    IF p_column = 'daily_fee' THEN
        SELECT COALESCE(SUM(daily_fee), 0) INTO v_sum FROM item WHERE deleted_at IS NULL;
    ELSEIF p_column = 'deposit_amount' THEN
        SELECT COALESCE(SUM(deposit_amount), 0) INTO v_sum FROM item WHERE deleted_at IS NULL;
    ELSEIF p_column = 'max_borrow_days' THEN
        SELECT COALESCE(SUM(max_borrow_days), 0) INTO v_sum FROM item WHERE deleted_at IS NULL;
    ELSEIF p_column = 'agreed_deposit' THEN
        SELECT COALESCE(SUM(agreed_deposit), 0) INTO v_sum FROM loan;
    ELSEIF p_column = 'agreed_total_fee' THEN
        SELECT COALESCE(SUM(agreed_total_fee), 0) INTO v_sum FROM loan;
    ELSEIF p_column = 'late_fee' THEN
        SELECT COALESCE(SUM(late_fee), 0) INTO v_sum FROM loan;
    ELSE
        SIGNAL SQLSTATE '45000'
           SET MESSAGE_TEXT = 'Unsupported column for aggregation.';
    END IF;
    RETURN v_sum;
END$$

-- 16-B: with grouping (one aggregate value per group)
DROP FUNCTION IF EXISTS fn_sum_deposits_by_category$$
CREATE FUNCTION fn_sum_deposits_by_category(p_cat_id INT) RETURNS DECIMAL(14,2)
DETERMINISTIC READS SQL DATA
BEGIN
    DECLARE v_sum DECIMAL(14,2) DEFAULT 0.00;
    SELECT COALESCE(SUM(l.agreed_deposit), 0) INTO v_sum
      FROM loan l
      JOIN borrow_request br ON br.request_id = l.request_id
      JOIN item i            ON i.item_id = br.item_id
     WHERE i.category_id = p_cat_id
     GROUP BY i.category_id;
    RETURN COALESCE(v_sum, 0.00);
END$$

-- Grouped aggregate result set (used by the reporting dashboard)
DROP PROCEDURE IF EXISTS sp_deposit_totals_by_category$$
CREATE PROCEDURE sp_deposit_totals_by_category(IN p_column VARCHAR(40))
BEGIN
    IF p_column NOT IN ('agreed_deposit', 'agreed_total_fee', 'late_fee') THEN
        SIGNAL SQLSTATE '45000'
           SET MESSAGE_TEXT = 'Unsupported grouped column. Use agreed_deposit, agreed_total_fee or late_fee.';
    END IF;

    SET @sql_group = CONCAT(
        'SELECT c.category_id, c.category_name, ',
        '       COUNT(l.loan_id) AS loans, ',
        '       COALESCE(SUM(l.', p_column, '), 0) AS group_total ',
        '  FROM category c ',
        '  LEFT JOIN item i           ON i.category_id = c.category_id ',
        '  LEFT JOIN borrow_request br ON br.item_id = i.item_id ',
        '  LEFT JOIN loan l            ON l.request_id = br.request_id ',
        ' GROUP BY c.category_id, c.category_name ',
        ' ORDER BY group_total DESC');
    PREPARE stmt FROM @sql_group; EXECUTE stmt; DEALLOCATE PREPARE stmt;
END$$


-- =====================================================================
-- 17. TEXT NORMALISATION (upper-casing character data)
-- =====================================================================
-- MySQL/MariaDB only implement row-level triggers (FOR EACH ROW); a real
-- statement-level trigger does not exist in this engine. The row trigger
-- below keeps every row consistent, and sp_normalize_item_titles() gives
-- the same result for bulk/batch loading in a single statement.

DROP TRIGGER IF EXISTS trg_item_uppercase_title$$
CREATE TRIGGER trg_item_uppercase_title
BEFORE INSERT ON item
FOR EACH ROW
BEGIN
    SET NEW.title = UPPER(NEW.title);
END$$

DROP TRIGGER IF EXISTS trg_item_uppercase_title_bu$$
CREATE TRIGGER trg_item_uppercase_title_bu
BEFORE UPDATE ON item
FOR EACH ROW
BEGIN
    SET NEW.title = UPPER(NEW.title);
END$$

DROP PROCEDURE IF EXISTS sp_normalize_item_titles$$
CREATE PROCEDURE sp_normalize_item_titles()
BEGIN
    UPDATE item
       SET title = UPPER(title)
     WHERE CAST(title AS BINARY) <> CAST(UPPER(title) AS BINARY);
    SELECT ROW_COUNT() AS titles_normalised;
END$$


-- =====================================================================
-- 18. OFFICE-HOURS MODIFICATION GUARD
-- =====================================================================
-- Reads its switch from app_config, so it behaves identically for every
-- connection. Enable it with: CALL sp_set_office_hours_guard(1);
-- It is shipped disabled so that ordinary day-to-day use of the portal is
-- not blocked, and can be switched on for a live demonstration of the rule.

DROP TRIGGER IF EXISTS trg_restrict_office_hours$$
CREATE TRIGGER trg_restrict_office_hours
BEFORE UPDATE ON borrow_request
FOR EACH ROW
BEGIN
    DECLARE v_enabled   VARCHAR(10);
    DECLARE v_now_ist   DATETIME;
    DECLARE v_day       VARCHAR(15);
    DECLARE v_time      TIME;
    DECLARE v_open_day  VARCHAR(15);
    DECLARE v_window    VARCHAR(30);
    DECLARE v_from      TIME;
    DECLARE v_to        TIME;

    SELECT config_value INTO v_enabled
      FROM app_config WHERE config_key = 'enforce_office_hours';

    IF COALESCE(v_enabled, '0') = '1' THEN
        SET v_now_ist  = UTC_TIMESTAMP() + INTERVAL 330 MINUTE;
        SET v_day      = DAYNAME(v_now_ist);
        SET v_time     = TIME(v_now_ist);

        -- The permitted day and window are configuration, not hard-coded, so
        -- the campus office can move them without touching the trigger.
        SET v_open_day = COALESCE((SELECT config_value FROM app_config
                                    WHERE config_key = 'office_hours_day'), 'Monday');
        SET v_window   = COALESCE((SELECT config_value FROM app_config
                                    WHERE config_key = 'office_hours_window'), '14:00-16:00');
        SET v_from     = SUBSTRING_INDEX(v_window, '-', 1);
        SET v_to       = SUBSTRING_INDEX(v_window, '-', -1);

        IF v_day <> v_open_day OR v_time < v_from OR v_time > v_to THEN
            SIGNAL SQLSTATE '45000'
               SET MESSAGE_TEXT = 'Modifications are restricted outside standard office hours (see app_config.office_hours_day / office_hours_window).';
        END IF;
    END IF;
END$$

DROP PROCEDURE IF EXISTS sp_set_office_hours_guard$$
CREATE PROCEDURE sp_set_office_hours_guard(IN p_enable TINYINT)
BEGIN
    UPDATE app_config
       SET config_value = IF(p_enable = 1, '1', '0'),
           updated_at   = UTC_TIMESTAMP()
     WHERE config_key = 'enforce_office_hours';

    SELECT config_key, config_value FROM app_config WHERE config_key = 'enforce_office_hours';
END$$


-- =====================================================================
-- 19. REPORTING VIEWS AND VIEW OPERATIONS
-- =====================================================================

-- Two-table view restricted to one campus location (conditional view).
CREATE OR REPLACE VIEW vw_bhabha_bhavan_items AS
SELECT i.item_id,
       i.owner_id,
       i.category_id,
       i.location_id,
       i.title,
       i.item_condition,
       i.daily_fee,
       i.deposit_amount,
       i.listing_status,
       u.roll_number AS owner_roll,
       u.full_name   AS owner_name,
       u.hostel_or_dept
  FROM item i
  JOIN app_user u ON u.user_id = i.owner_id
 WHERE u.hostel_or_dept = 'Bhabha Bhavan';

-- Single-table (directly updatable) view used for the trigger demonstration.
CREATE OR REPLACE VIEW vw_active_items AS
SELECT item_id, owner_id, category_id, location_id, title, description,
       item_condition, daily_fee, deposit_amount, max_borrow_days, listing_status
  FROM item
 WHERE deleted_at IS NULL;

-- Inserts through the application routine and then displays the view.
DROP PROCEDURE IF EXISTS sp_view_operations$$
CREATE PROCEDURE sp_view_operations(
    IN p_action    VARCHAR(10),
    IN p_owner_id  INT,
    IN p_cat_id    INT,
    IN p_loc_id    INT,
    IN p_title     VARCHAR(160),
    IN p_fee       DECIMAL(10,2),
    IN p_deposit   DECIMAL(10,2)
)
BEGIN
    IF UPPER(p_action) = 'INSERT' THEN
        INSERT INTO item (owner_id, category_id, location_id, title, item_condition,
                          deposit_amount, daily_fee, max_borrow_days)
        VALUES (p_owner_id, p_cat_id, p_loc_id, p_title, 'GOOD',
                p_deposit, p_fee, 7);
    END IF;

    SELECT * FROM vw_bhabha_bhavan_items ORDER BY item_id;
END$$

-- One call = every table statistic used by the reporting dashboard.
DROP PROCEDURE IF EXISTS sp_application_statistics$$
CREATE PROCEDURE sp_application_statistics()
BEGIN
    SELECT 'app_user'         AS table_name, COUNT(*) AS row_count FROM app_user
    UNION ALL SELECT 'item',              COUNT(*) FROM item
    UNION ALL SELECT 'item_image',        COUNT(*) FROM item_image
    UNION ALL SELECT 'category',          COUNT(*) FROM category
    UNION ALL SELECT 'pickup_location',   COUNT(*) FROM pickup_location
    UNION ALL SELECT 'favorite',          COUNT(*) FROM favorite
    UNION ALL SELECT 'borrow_request',    COUNT(*) FROM borrow_request
    UNION ALL SELECT 'booked_date',       COUNT(*) FROM booked_date
    UNION ALL SELECT 'loan',              COUNT(*) FROM loan
    UNION ALL SELECT 'temporary_otp',     COUNT(*) FROM temporary_otp
    UNION ALL SELECT 'payment',           COUNT(*) FROM payment
    UNION ALL SELECT 'payment_webhook_event', COUNT(*) FROM payment_webhook_event
    UNION ALL SELECT 'review',            COUNT(*) FROM review
    UNION ALL SELECT 'loan_inspection',   COUNT(*) FROM loan_inspection
    UNION ALL SELECT 'inspection_photo',  COUNT(*) FROM inspection_photo
    UNION ALL SELECT 'conversation',      COUNT(*) FROM conversation
    UNION ALL SELECT 'message',           COUNT(*) FROM message
    UNION ALL SELECT 'dispute',           COUNT(*) FROM dispute
    UNION ALL SELECT 'dispute_evidence',  COUNT(*) FROM dispute_evidence
    UNION ALL SELECT 'notification',      COUNT(*) FROM notification
    UNION ALL SELECT 'auth_token',        COUNT(*) FROM auth_token
    UNION ALL SELECT 'device_token',      COUNT(*) FROM device_token
    UNION ALL SELECT 'application_audit_log', COUNT(*) FROM application_audit_log
    UNION ALL SELECT 'system_job_log',    COUNT(*) FROM system_job_log
    UNION ALL SELECT 'app_config',        COUNT(*) FROM app_config;
END$$

DELIMITER ;

-- Grants for the routines introduced in this section
GRANT EXECUTE ON PROCEDURE borrowhub.sp_insert_item               TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_update_item_fee           TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_soft_delete_item          TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_create_user               TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_set_user_password         TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_user_login_data         TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_update_user_login       TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_record_login_attempt      TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_search_items_paginated    TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_deposit_totals_by_category TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_normalize_item_titles     TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_view_operations           TO 'borrowhub_app_role';
GRANT EXECUTE ON PROCEDURE borrowhub.sp_application_statistics    TO 'borrowhub_app_role';
GRANT SELECT ON borrowhub.vw_bhabha_bhavan_items TO 'borrowhub_naive_role';
GRANT SELECT ON borrowhub.vw_active_items       TO 'borrowhub_naive_role';
GRANT EXECUTE ON FUNCTION  borrowhub.fn_search_items_count        TO 'borrowhub_app_role';
GRANT EXECUTE ON FUNCTION  borrowhub.fn_sum_column_total          TO 'borrowhub_app_role';
GRANT EXECUTE ON FUNCTION  borrowhub.fn_sum_deposits_by_category  TO 'borrowhub_app_role';


-- =====================================================================
-- 19-b. DEMO LOGINS FOR THE THREE DATABASE ROLES
-- =====================================================================
-- Each role gets one real MySQL account so the privilege separation can be
-- demonstrated (the naive user only sees one read-only view, the developer
-- has DML on application data, the DBA owns everything).

CALL sp_create_role_user('borrowhub_naive', 'Naive@2026!',     'borrowhub_naive_role');
CALL sp_create_role_user('borrowhub_dev',   'Developer@2026!', 'borrowhub_developer_role');
CALL sp_create_role_user('borrowhub_dba',   'Dba@2026!',       'borrowhub_dba_role');

-- =====================================================================
-- 20. PERFORMANCE INDEXES
-- =====================================================================
-- Supporting indexes for the reporting queries (fee/condition filters,
-- hostel based lookups and owner/deposit aggregations).

CREATE INDEX ix_item_fee_condition      ON item (daily_fee, item_condition, listing_status);
CREATE INDEX ix_user_hostel_verified    ON app_user (hostel_or_dept, is_verified);
CREATE INDEX ix_item_owner_deposit      ON item (owner_id, deposit_amount);
CREATE INDEX ix_request_dates_status    ON borrow_request (item_id, status, start_date, end_date);

-- =====================================================================
-- END OF SCHEMA
-- (sample queries, execution-time measurements and index-impact analysis
--  live in database/demo_queries.sql so that this file stays pure DDL)
-- =====================================================================
