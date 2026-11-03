# BorrowHub — Security Assessment & Threat Model Report

**Platform:** BorrowHub (SVNIT Surat Campus Resource Sharing Platform)  
**Security Architecture Status:** Production-Grade / Hardened  
**Audit Scope:** Authentication, Authorization, Database Triggers, Concurrency, Financial Calculations, Media Uploads, Rate Limiting

---

## 1. Executive Summary

BorrowHub implements defense-in-depth across the presentation, application, and database tiers. In accordance with zero-trust architectural guidelines, the backend never trusts client-side inputs or totals. Business rules, financial calculations, date availability checks, and physical exchange verifications are validated independently by Python FastAPI services and enforced at the lowest level by MySQL InnoDB triggers and constraints.

---

## 2. Security Controls & Implementations

### 2.1 Campus Email Domain Verification
* **Threat:** Unauthorized public users registering fake accounts or spamming the campus network.
* **Control:**
  - Dual-layer validation: Pydantic email schema regex and MySQL `chk_user_email` constraint.
  - Allowed domains: `@svnit.ac.in` and `@coed.svnit.ac.in`.
  - Non-campus emails receive an immediate `400 Bad Request` rejection.
  - Mandatory 6-digit OTP email verification before account activation.

### 2.2 Password Security & Credential Storage
* **Threat:** Credential theft via database leaks or brute force.
* **Control:**
  - Standard `bcrypt` password hashing with automatically salted rounds.
  - Plain-text passwords are never logged, echoed, or stored in session storage.
  - Minimum 8-character password policy enforced during registration.

### 2.3 Stateless JWT Authentication & Session Management
* **Threat:** Session hijacking or unauthorized route access.
* **Control:**
  - Cryptographically signed JSON Web Tokens (`HS256`) containing `sub` (user_id), `email`, and `role`.
  - Expiration timestamp (`exp`) set to 24 hours (1440 minutes).
  - Protected endpoints extract user identity via FastAPI dependency injection (`get_current_user`).

### 2.4 Rate Limiting & Denial-of-Service (DoS) Mitigation
* **Threat:** Brute-force attacks against authentication endpoints (`/api/auth/login`, `/api/auth/register`).
* **Control:**
  - In-memory sliding window rate limiter (`backend/app/core/rate_limit.py`).
  - Limits registration and login requests to 10 attempts per 15-minute window per client IP.
  - Excess requests immediately return `HTTP 429 Too Many Requests`.

### 2.5 Independent Financial Calculation (Anti-Tampering)
* **Threat:** Malicious students modifying frontend JavaScript variables to change rental fees or deposits.
* **Control:**
  - Total fees, rental sums, and deposits are computed exclusively on the backend:
    $$\text{Total Fee} = \text{daily\_fee} \times (\text{end\_date} - \text{start\_date} + 1)$$
    $$\text{Total Payable} = \text{Total Fee} + \text{deposit\_amount}$$
  - Pricing snapshots are stored on the `BORROW_REQUEST` row upon creation. Any future price changes by the owner cannot tamper with an ongoing booking.
  - MySQL database trigger `trg_payment_bi` aborts payments if the submitted amount does not match `loan.agreed_total_fee` or `loan.agreed_deposit`.

### 2.6 Concurrency Protection & Anti-Double-Booking
* **Threat:** Race conditions where two students simultaneously book the same resource for overlapping dates.
* **Control:**
  - Database table `BOOKED_DATE` with composite unique constraint `(item_id, booked_date)`.
  - Database trigger `trg_booked_date_bi` rejects any date insertion if `item_id` is already reserved on that day.
  - Automatic cancellation: when an owner approves a borrow request, all other overlapping pending requests for that item are automatically declined with notification.

### 2.7 Two-Party Cryptographic Handshake (OTPs)
* **Threat:** Fraudulent claims that an item was delivered or returned when no physical meeting occurred.
* **Control:**
  - Separate 6-digit OTPs generated for Handover and Return using Python's `secrets.randbelow(1000000)` (CSPRNG).
  - Plaintext OTPs are confidential to the borrower.
  - MySQL stores only the SHA-256 cryptographic digest of the OTP (`handover_otp_hash` and `return_otp_hash`).
  - Verification calls the database stored procedure `sp_confirm_inspection`, which calculates `SHA2(input_otp, 256)` and compares hashes in constant time.
  - Direct updates to `LOAN.status` without a verified inspection record are rejected by `trg_loan_bu`.

### 2.8 Secure Media Uploads
* **Threat:** Unrestricted file uploads leading to Remote Code Execution (RCE) or SVG XSS attacks.
* **Control:**
  - Enforces strict whitelist of image MIME types: `image/jpeg`, `image/png`, `image/webp`.
  - Extension whitelist: `.jpg`, `.jpeg`, `.png`, `.webp`.
  - Maximum upload size capped at 5 MB per image.
  - Images uploaded to Cloudinary or stored locally in isolated static folders without script execution permissions.
  - Cloudinary API secret is kept exclusively on the server and never exposed to frontend code.

### 2.9 Role-Based Access Control (RBAC)
* **Roles:** `STUDENT`, `FACULTY`, `MODERATOR`, `ADMIN`.
* **Enforcement:**
  - Dependency `get_current_admin` restricts administrative moderation and metrics to users with role `ADMIN`.
  - Item ownership authorization ensures students can only edit or archive their own listings.
  - Self-borrowing is strictly forbidden by API validation and database trigger `trg_borrow_request_bi`.

### 2.10 SQL Injection Defense
* **Control:**
  - 100% of database interactions are conducted through SQLAlchemy 2.x ORM or parameterized SQL queries using named parameters (`:param`).
  - No raw string concatenations or unescaped user inputs are passed to SQL execution.

---

## 3. Automated Security Verification Results

All 13 automated security, flow, and authorization tests pass in `backend/tests/`:
- `test_admin_endpoints_access_control`: PASSED (403 Forbidden for non-admin)
- `test_login_wrong_password`: PASSED (401 Unauthorized)
- `test_register_invalid_domain`: PASSED (400 Bad Request for non-SVNIT emails)
- `test_register_duplicate_email`: PASSED (400 Bad Request)
- `test_unauthorized_access`: PASSED (401 Unauthorized for missing bearer token)
- `test_self_borrowing_prevention`: PASSED (400 Bad Request when owner requests own item)
- `test_complete_borrow_loan_and_return_lifecycle`: PASSED (End-to-end OTP cryptographic verification)
- `test_payment_flow`: PASSED (Order creation, verification, and cash settlement)

---

## 10. Media-upload hardening (latest)

`POST /api/upload` no longer trusts the browser-supplied `Content-Type`.

* The **magic bytes** of the file body are checked (`sniff_image_type`): JPEG, PNG,
  GIF and WebP only. A file renamed to `photo.jpg` but containing HTML/SVG is
  rejected with `400`, which closes a stored-XSS path (the file used to be written
  to `backend/static/uploads/` and served back from the same origin).
* The stored **extension comes from the sniffed bytes**, not from the filename.
* Empty uploads and files over 5 MB are refused before anything is written.
* Cloudinary (when configured) receives only files that already passed the sniff.
* Covered by `test_upload_rejects_non_image_payload` and `test_upload_accepts_a_real_png`.

### Query Lab surface

The new SQL console is an administrative tool and is protected in five layers
(admin-only session, statement allow-list, single-statement enforcement,
confidential-column/schema blocklist, 8 s timeout + 500-row cap). It never opens a
separate database connection with elevated privileges — it reuses the application
session, so MySQL grants still apply. Details in the README, §9.

