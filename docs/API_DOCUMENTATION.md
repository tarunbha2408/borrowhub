# BorrowHub — REST API Documentation

**Platform:** BorrowHub (SVNIT Surat Campus Resource Sharing Platform)  
**Tagline:** Share · Borrow · Grow  
**Base URL:** `http://localhost:8000/api`  
**Interactive Swagger Docs:** `http://localhost:8000/api/docs`  
**ReDoc Specifications:** `http://localhost:8000/api/redoc`

---

## 1. Authentication & Security Headers

All protected endpoints require a standard Bearer token in the `Authorization` HTTP header:

```http
Authorization: Bearer <JWT_ACCESS_TOKEN>
```

Tokens are signed using `HS256` with a configurable secret key (`JWT_SECRET_KEY`) and expire after 24 hours (1440 minutes).

### Standard Error Response Format
All error responses return standard JSON:
```json
{
  "detail": "Descriptive error message explaining the failure."
}
```

---

## 2. Authentication Endpoints (`/api/auth`)

### 2.1 Register New Student
* **Endpoint:** `POST /api/auth/register`
* **Access:** Public (Rate-limited to 10 requests / 15 minutes)
* **Description:** Registers a new SVNIT student account. Only official domains `@svnit.ac.in` and `@coed.svnit.ac.in` are permitted.
* **Request Body:**
  ```json
  {
    "svnit_email": "student@coed.svnit.ac.in",
    "password": "StrongPassword@2026!",
    "full_name": "Rohan Mehta",
    "roll_number": "U22CS042",
    "phone_number": "9876543210",
    "hostel": "Bhabha Bhavan",
    "room_no": "B-312"
  }
  ```
* **Success Response (201 Created):**
  ```json
  {
    "message": "Registration successful. Please verify your SVNIT email address with the verification code.",
    "email": "student@coed.svnit.ac.in",
    "verification_token_or_otp": "481920",
    "requires_verification": true
  }
  ```

### 2.2 Verify Student Email
* **Endpoint:** `POST /api/auth/verify-email`
* **Access:** Public
* **Description:** Verifies student email ownership using the 6-digit OTP code or registration token.
* **Request Body:**
  ```json
  {
    "email": "student@coed.svnit.ac.in",
    "otp": "481920"
  }
  ```
* **Success Response (200 OK):**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "user": {
      "user_id": 5,
      "svnit_email": "student@coed.svnit.ac.in",
      "full_name": "Rohan Mehta",
      "roll_number": "U22CS042",
      "role": "STUDENT",
      "is_active": 1,
      "email_verified": 1,
      "trust_score": 100.0,
      "created_at": "2026-10-31T15:30:00Z"
    }
  }
  ```

### 2.3 Student Sign In
* **Endpoint:** `POST /api/auth/login`
* **Access:** Public (Rate-limited to 10 requests / 15 minutes)
* **Description:** Authenticates with email and password, returning JWT access token.
* **Request Body:**
  ```json
  {
    "svnit_email": "priya@coed.svnit.ac.in",
    "password": "Svnit@2026!"
  }
  ```
* **Success Response (200 OK):**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "user": {
      "user_id": 1,
      "svnit_email": "priya@coed.svnit.ac.in",
      "full_name": "Priya Sharma",
      "roll_number": "U22CS001",
      "role": "STUDENT",
      "is_active": 1,
      "email_verified": 1,
      "trust_score": 100.0,
      "created_at": "2026-10-31T10:00:00Z"
    }
  }
  ```

### 2.4 Get Current Profile
* **Endpoint:** `GET /api/auth/me`
* **Access:** Authenticated
* **Success Response (200 OK):**
  ```json
  {
    "user_id": 14,
    "svnit_email": "priya@coed.svnit.ac.in",
    "full_name": "Priya Sharma",
    "roll_number": "U22CS001",
    "phone": "+919876543210",
    "hostel_or_dept": "Bhabha Bhavan",
    "role": "STUDENT",
    "is_verified": 1,
    "is_active": 1
  }
  ```

### 2.5 My Login Record
* **Endpoint:** `GET /api/auth/login-data`
* **Access:** Authenticated
* **Backed by:** stored procedure `sp_user_login_data`
* **Success Response (200 OK):**
  ```json
  {
    "user_id": 14,
    "roll_number": "U22CS001",
    "full_name": "Priya Sharma",
    "svnit_email": "priya@coed.svnit.ac.in",
    "role": "STUDENT",
    "is_verified": 1,
    "is_active": 1,
    "last_login_at": "2026-11-02T10:12:01",
    "failed_login_count": 0,
    "active_sessions": 0
  }
  ```

### 2.6 Change Password / Login E-mail
* **Endpoint:** `POST /api/auth/change-password`
* **Access:** Authenticated
* **Backed by:** stored procedure `sp_update_user_login`
* **Request Body:**
  ```json
  {
    "current_password": "Svnit@2026!",
    "new_password": "NewSecret@2026!",
    "new_email": "u22cs001@coed.svnit.ac.in"
  }
  ```
* **Behaviour:** the current password is verified first, the e-mail must stay in
  the `@svnit.ac.in` / `@coed.svnit.ac.in` domain, and a successful change
  **invalidates every open session** of the account — sign in again afterwards.
* **Errors:** `401` wrong current password · `400` non-SVNIT or already used e-mail.

---

## 3. Catalog & Item Listings (`/api/items`)

### 3.1 Get All Categories
* **Endpoint:** `GET /api/items/categories`
* **Access:** Public
* **Success Response (200 OK):**
  ```json
  [
    { "category_id": 1, "category_name": "Electronics", "category_description": "Calculators, lab meters, cables, adapters" },
    { "category_id": 2, "category_name": "Books", "category_description": "Engineering textbooks, reference manuals, notes" },
    { "category_id": 3, "category_name": "Lab Equipment", "category_description": "Aprons, safety goggles, breadboards, kits" },
    { "category_id": 4, "category_name": "Sports", "category_description": "Badminton rackets, footballs, cricket gear" },
    { "category_id": 5, "category_name": "Tools", "category_description": "Screwdrivers, soldering irons, wire strippers" },
    { "category_id": 6, "category_name": "Stationery", "category_description": "Drafters, drawing boards, geometry sets" },
    { "category_id": 7, "category_name": "Musical Instruments", "category_description": "Guitars, keyboards, flutes" },
    { "category_id": 8, "category_name": "Others", "category_description": "Daily essentials, umbrella, cycle pump" }
  ]
  ```

### 3.2 Get Pickup Locations
* **Endpoint:** `GET /api/items/locations`
* **Access:** Public
* **Success Response (200 OK):**
  ```json
  [
    { "location_id": 1, "name": "Central Library - Ground Floor Foyer", "description": "Near library turnstiles" },
    { "location_id": 2, "name": "Student Activity Centre (SAC)", "description": "Near sports desk" },
    { "location_id": 3, "name": "DoECC / Computer Engineering Dept", "description": "Department lobby" },
    { "location_id": 4, "name": "Bhabha Bhavan Main Entrance", "description": "Hostel reception" },
    { "location_id": 5, "name": "Mother Teresa Bhavan Foyer", "description": "Girls hostel security" },
    { "location_id": 6, "name": "Canteen / Nescafe Point", "description": "Open seating area" },
    { "location_id": 7, "name": "Main Gate Security Post", "description": "Campus main entrance" }
  ]
  ```

### 3.3 Search & Filter Marketplace
* **Endpoint:** `GET /api/items`
* **Access:** Public (Optional auth to include `is_favorite` flag)
* **Query Parameters:**
  - `q` (string): Keyword in title or description.
  - `category_id` (int): Filter by category ID.
  - `location_id` (int): Filter by pickup location.
  - `min_fee` (decimal), `max_fee` (decimal): Daily fee range.
  - `sort_by` (`newest`, `price_asc`, `price_desc`).
  - `page` (int, default: 1), `page_size` (int, default: 20).
* **Success Response (200 OK):**
  ```json
  {
    "items": [
      {
        "item_id": 1,
        "owner_id": 1,
        "owner_name": "Priya Sharma",
        "owner_email": "priya@coed.svnit.ac.in",
        "owner_hostel": "Mother Teresa Bhavan",
        "category_id": 1,
        "category_name": "Electronics",
        "location_id": 1,
        "location_name": "Central Library - Ground Floor Foyer",
        "title": "Scientific Calculator Casio fx-991EX ClassWiz",
        "description": "552 functions, perfect for semester exams and lab calculations.",
        "item_condition": "GOOD",
        "deposit_amount": "200.00",
        "daily_fee": "10.00",
        "max_borrow_days": 7,
        "listing_status": "ACTIVE",
        "primary_image_url": "https://images.unsplash.com/photo-1594980596870-8aa52a78d8cd?w=600",
        "is_favorite": false,
        "created_at": "2026-10-31T10:00:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
  ```

### 3.4 Create Item Listing
* **Endpoint:** `POST /api/items`
* **Access:** Authenticated
* **Request Body:**
  ```json
  {
    "title": "Engineering Drafter with Mini Scale",
    "category_id": 6,
    "location_id": 4,
    "custom_location": null,
    "description": "Omega mini drafter in original bag with clamp and scales.",
    "item_condition": "GOOD",
    "deposit_amount": 300.00,
    "daily_fee": 15.00,
    "max_borrow_days": 14,
    "image_urls": [
      "https://images.unsplash.com/photo-1581291518857-4e27b48ff24e?w=600"
    ]
  }
  ```
* **Success Response (201 Created):**
  Returns complete `ItemDetailOut` object.

### 3.5 Check Availability Calendar
* **Endpoint:** `GET /api/items/{item_id}/availability`
* **Access:** Public
* **Success Response (200 OK):**
  ```json
  {
    "item_id": 1,
    "status": "ACTIVE",
    "booked_dates": ["2026-11-02", "2026-11-03", "2026-11-04"],
    "booked_ranges": [
      {
        "start_date": "2026-11-02",
        "end_date": "2026-11-04",
        "status": "APPROVED",
        "reason": "Existing approved booking"
      }
    ]
  }
  ```

---

## 4. Borrowing & Approval Workflow (`/api/borrow-requests`)

### 4.1 Submit Borrow Request
* **Endpoint:** `POST /api/borrow-requests`
* **Access:** Authenticated (Student)
* **Validation:** Prevents self-borrowing, invalid dates, duration exceeding item limits, and conflicting bookings. Backend independently calculates all fees.
* **Request Body:**
  ```json
  {
    "item_id": 1,
    "start_date": "2026-11-05",
    "end_date": "2026-11-07",
    "borrower_note": "Need for physics practical exam."
  }
  ```
* **Success Response (201 Created):**
  ```json
  {
    "request_id": 12,
    "item_id": 1,
    "item_title": "Scientific Calculator Casio fx-991EX ClassWiz",
    "borrower_id": 2,
    "borrower_name": "Aarav Patel",
    "start_date": "2026-11-05",
    "end_date": "2026-11-07",
    "days_count": 3,
    "daily_fee": "10.00",
    "deposit_amount": "200.00",
    "total_fee": "30.00",
    "total_payable": "230.00",
    "status": "PENDING"
  }
  ```

### 4.2 Owner Approves Request
* **Endpoint:** `POST /api/borrow-requests/{request_id}/approve`
* **Access:** Authenticated (Item Owner)
* **Description:** Atomically reserves dates, generates cryptographic OTP hashes, sets trigger session variables, creates scheduled loan, and automatically rejects overlapping pending requests.
* **Success Response (200 OK):**
  Returns `LoanOut` object with status `SCHEDULED`.

### 4.3 Owner Declines Request
* **Endpoint:** `POST /api/borrow-requests/{request_id}/reject`
* **Access:** Authenticated (Item Owner)
* **Request Body:**
  ```json
  { "decision_note": "Item currently in use." }
  ```

---

## 5. Loan Management & Two-Party OTP Handshake (`/api/loans`)

### 5.1 Get My Loans
* **Endpoint:** `GET /api/loans`
* **Access:** Authenticated
* **Success Response (200 OK):**
  ```json
  {
    "borrowed": [
      {
        "loan_id": 8,
        "item_title": "Digital Multimeter",
        "status": "SCHEDULED",
        "agreed_total_fee": "60.00",
        "agreed_deposit": "250.00",
        "deposit_status": "HELD",
        "handover_otp": "729401"
      }
    ],
    "lent": []
  }
  ```

### 5.2 Verify Handover (Physical Item Exchange)
* **Endpoint:** `POST /api/loans/{loan_id}/verify-handover`
* **Access:** Authenticated (Item Owner)
* **Description:** Owner enters borrower's 6-digit Handover OTP. The backend executes `sp_confirm_inspection` which triggers database verification. Once verified, loan transitions to `ACTIVE`.
* **Request Body:**
  ```json
  {
    "handover_otp": "729401",
    "inspected_condition": "GOOD",
    "notes": "Multimeter delivered with test probes."
  }
  ```

### 5.3 Verify Return & Settle Deposit
* **Endpoint:** `POST /api/loans/{loan_id}/verify-return`
* **Access:** Authenticated (Item Owner)
* **Description:** Owner enters borrower's 6-digit Return OTP. Once verified, loan status transitions to `RETURNED`.
* **Request Body:**
  ```json
  {
    "return_otp": "834192",
    "inspected_condition": "GOOD",
    "notes": "Returned on time."
  }
  ```

### 5.4 Settle Deposit
* **Endpoint:** `POST /api/loans/{loan_id}/settle-deposit`
* **Access:** Authenticated (Item Owner)
* **Request Body:**
  ```json
  {
    "damage_fee_deduction": 0.00,
    "late_fee_deduction": 0.00,
    "settlement_reason": "Full deposit refund"
  }
  ```

---

## 6. Payments & Razorpay (`/api/payments`)

### 6.1 Create Razorpay Order
* **Endpoint:** `POST /api/payments/create-order`
* **Access:** Authenticated (Borrower)
* **Request Body:**
  ```json
  {
    "loan_id": 8,
    "payment_type": "RENTAL_FEE"
  }
  ```
* **Success Response (200 OK):**
  ```json
  {
    "order_id": "order_test_98124",
    "payment_id": 14,
    "amount": "60.00",
    "amount_subunits": 6000,
    "currency": "INR",
    "key_id": "rzp_test_borrowhub_dummy",
    "payment_type": "RENTAL_FEE"
  }
  ```

### 6.2 Verify Razorpay Signature
* **Endpoint:** `POST /api/payments/verify`
* **Access:** Authenticated
* **Request Body:**
  ```json
  {
    "loan_id": 8,
    "razorpay_order_id": "order_test_98124",
    "razorpay_payment_id": "pay_test_58190",
    "razorpay_signature": "signature_hash...",
    "payment_type": "RENTAL_FEE"
  }
  ```

---

## 7. Reviews, Disputes & Administration

* `POST /api/reviews`: Submit star rating (1-5) and comment after loan is `RETURNED`.
* `POST /api/disputes`: Submit dispute claim (`ITEM_DAMAGED`, `ITEM_NOT_RETURNED`, etc.).
* `GET /api/admin/stats`: Platform statistics (users, listings, active loans, platform volume).
* `POST /api/upload`: Upload image file via multipart form data to Cloudinary or local storage.
* `GET /api/admin/office-hours`: Current office-hours guard state (day + window + enabled flag).
* `PUT /api/admin/office-hours?enabled=true|false`: Switches the `borrow_request` office-hours trigger through `sp_set_office_hours_guard`.

---

## 8. Database Explorer / Data Studio (`/api/explorer`)

Every read endpoint accepts `?fmt=xml` to return the same payload serialised as XML.

| Endpoint | Purpose |
|---|---|
| `GET /api/explorer/dashboard` | Row count of every table (`sp_application_statistics`) + headline KPIs + message |
| `GET /api/explorer/options` | Tables, columns, views, filter fields, join pairs, aggregate functions |
| `GET /api/explorer/table/{table}` | Full table data as an HTML-table payload (or XML) |
| `GET /api/explorer/aggregate` | `COUNT/SUM/AVG/MIN/MAX` on a whitelisted column, optional `group_by` |
| `GET /api/explorer/filter` | Column + operator + value conditional read |
| `GET /api/explorer/multi-table` | `mode=subquery` or `mode=correlated` across two tables |
| `GET /api/explorer/join` | Two chosen tables + chosen join type |
| `GET /api/explorer/view/{view}` | Read one of the 7 reporting views |
| `POST /api/explorer/view/{view}/insert` | Insert through `sp_view_operations` and re-read the view |
| `POST /api/explorer/view/{view}/trigger-demo` | Update through the view; the trigger either accepts or rejects it |
| `GET /api/explorer/update-options` · `POST /api/explorer/update` | Administrator-only whitelisted column update |

---

## 9. Query Lab (`/api/query-lab`)

Read-only SQL console. **Administrator (or moderator) session required.**

### 9.1 Run a statement
* **Endpoint:** `POST /api/query-lab/run`
* **Query params:** `sql` (the statement), `include_plan` (default `true`)
* **Success Response (200 OK):**
  ```json
  {
    "sql": "SELECT item_id, title FROM item",
    "statement_type": "SELECT",
    "columns": ["item_id", "title"],
    "rows": [[1, "CASIO FX-991EX CLASSWIZ SCIENTIFIC CALCULATOR"]],
    "row_count": 1,
    "truncated": false,
    "row_cap": 500,
    "execution_ms": 0.621,
    "message": "1 row(s) in 0.6 ms",
    "plan": {"columns": ["id", "select_type", "table", "key", "rows", "Extra"], "rows": [], "row_count": 1},
    "indexes_used": ["ix_item_owner"]
  }
  ```
* **Allowed statements:** anything starting with `SELECT`, `WITH`, `SHOW`, `DESCRIBE`/`DESC`, `EXPLAIN`.
* **Errors:**
  * `400` — write/DDL keyword, stacked statements, confidential column, blocked system schema, or the SQL error itself (returned as one readable line with the elapsed time).
  * `403` — the caller is not an administrator.
  * `401` — no session.

### 9.2 Curated examples
* **Endpoint:** `GET /api/query-lab/examples`
* Returns 16 statements in three groups (`Statement set`, `Schema & performance`, `Views & reporting`); every one of them is executed by the test suite, so a broken example cannot ship.

