import random
from datetime import date, timedelta


def test_self_borrowing_prevention(client, db, auth_headers_student_a):
    """A student must not be able to borrow a listing they own."""
    from backend.app.models.catalog import Item
    from backend.app.models.user import AppUser

    owner = db.query(AppUser).filter(AppUser.svnit_email == "u23cs001@svnit.ac.in").one()
    own_item = db.query(Item).filter(
        Item.owner_id == owner.user_id,
        Item.listing_status == "ACTIVE",
        Item.deleted_at.is_(None),
    ).order_by(Item.item_id).first()
    assert own_item is not None, "seed data must give this student at least one active listing"

    today = date.today()
    offset = random.randint(300, 500)
    start = today + timedelta(days=offset)
    end = today + timedelta(days=offset + 2)

    res = client.post("/api/borrow-requests", json={
        "item_id": own_item.item_id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "request_message": "Trying to borrow my own calculator"
    }, headers=auth_headers_student_a)

    assert res.status_code == 400
    assert "cannot borrow your own listing" in res.json()["detail"].lower()


def test_complete_borrow_loan_and_return_lifecycle(
    client, auth_headers_student_a, auth_headers_student_b
):
    # 0. Student A creates a dedicated test item so dates are 100% fresh
    item_res = client.post("/api/items", json={
        "title": f"Lifecycle Test Multi-meter {random.randint(1000, 9999)}",
        "category_id": 3,
        "location_id": 1,
        "description": "Digital multimeter for circuit testing.",
        "item_condition": "GOOD",
        "deposit_amount": 250.00,
        "daily_fee": 20.00,
        "max_borrow_days": 7,
        "image_urls": ["https://images.unsplash.com/photo-1581092335397-9583fe92d232"]
    }, headers=auth_headers_student_a)
    assert item_res.status_code == 201
    test_item = item_res.json()
    test_item_id = test_item["item_id"]

    today = date.today()
    start = today
    end = today + timedelta(days=2)  # 3 days starting today: start <= today, so handover is valid

    # 1. Student B submits borrow request
    req_res = client.post("/api/borrow-requests", json={
        "item_id": test_item_id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "request_message": "Need multimeter for testing power supply."
    }, headers=auth_headers_student_b)

    assert req_res.status_code == 201
    req_data = req_res.json()
    req_id = req_data["request_id"]
    assert req_data["status"] == "PENDING"
    assert req_data["days_count"] == 3
    assert req_data["total_fee"] == "60.00"
    assert req_data["total_payable"] == "310.00"

    # 2. Student A (owner) approves request
    app_res = client.post(f"/api/borrow-requests/{req_id}/approve", json={
        "decision_note": "Approved! Collect at Bhabha Bhavan reception."
    }, headers=auth_headers_student_a)

    assert app_res.status_code == 200
    loan_data = app_res.json()
    loan_id = loan_data["loan_id"]
    assert loan_data["status"] == "SCHEDULED"
    assert loan_data["agreed_daily_fee"] == "20.00"
    assert loan_data["agreed_deposit"] == "250.00"
    assert loan_data["agreed_total_fee"] == "60.00"

    # 2b. Borrower completes rental fee and deposit payments before handover
    # Pay rental fee (₹60)
    res_rent = client.post("/api/payments/create-order", json={"loan_id": loan_id, "payment_type": "RENTAL_FEE"}, headers=auth_headers_student_b)
    assert res_rent.status_code == 200
    pay_rent_id = res_rent.json()["payment_id"]
    client.post("/api/payments/verify", json={
        "payment_id": pay_rent_id,
        "razorpay_order_id": res_rent.json()["order_id"],
        "razorpay_payment_id": f"pay_rent_{pay_rent_id}",
        "razorpay_signature": "dummy_sig"
    }, headers=auth_headers_student_b)

    # Pay security deposit (₹250)
    res_dep = client.post("/api/payments/create-order", json={"loan_id": loan_id, "payment_type": "DEPOSIT"}, headers=auth_headers_student_b)
    assert res_dep.status_code == 200
    pay_dep_id = res_dep.json()["payment_id"]
    client.post("/api/payments/verify", json={
        "payment_id": pay_dep_id,
        "razorpay_order_id": res_dep.json()["order_id"],
        "razorpay_payment_id": f"pay_dep_{pay_dep_id}",
        "razorpay_signature": "dummy_sig"
    }, headers=auth_headers_student_b)

    # 3. Test overlapping request rejection: another student tries same dates
    overlap_res = client.post("/api/borrow-requests", json={
        "item_id": test_item_id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }, headers=auth_headers_student_b)
    assert overlap_res.status_code == 409

    # 4. Confidentiality test: Owner asks for handover OTP -> 403 Forbidden!
    h_hack = client.get(f"/api/loans/{loan_id}/handover-otp", headers=auth_headers_student_a)
    assert h_hack.status_code == 403

    # 5. Borrower fetches their secure handover OTP
    h_res = client.get(f"/api/loans/{loan_id}/handover-otp", headers=auth_headers_student_b)
    assert h_res.status_code == 200
    handover_otp = h_res.json()["handover_otp"]
    assert len(handover_otp) == 6

    # 6. Wrong handover OTP verification test
    wrong_res = client.post(f"/api/loans/{loan_id}/verify-handover", json={
        "handover_otp": "000000",
        "condition_found": "GOOD"
    }, headers=auth_headers_student_a)
    assert wrong_res.status_code == 400
    assert "invalid handover otp" in wrong_res.json()["detail"].lower()

    # 7. Owner enters correct handover OTP at meetup -> Loan transitions to ACTIVE
    valid_res = client.post(f"/api/loans/{loan_id}/verify-handover", json={
        "handover_otp": handover_otp,
        "condition_found": "NEW",
        "notes": "Handed over multimeter with test probes."
    }, headers=auth_headers_student_a)
    assert valid_res.status_code == 200
    active_loan = valid_res.json()
    assert active_loan["status"] == "ACTIVE"
    assert active_loan["issued_at"] is not None

    # 8. Return flow: Borrower retrieves return OTP
    r_res = client.get(f"/api/loans/{loan_id}/return-otp", headers=auth_headers_student_b)
    assert r_res.status_code == 200
    return_otp = r_res.json()["return_otp"]
    assert len(return_otp) == 6

    # 9. Owner verifies return using borrower's OTP -> Loan transitions to RETURNED
    ret_res = client.post(f"/api/loans/{loan_id}/verify-return", json={
        "return_otp": return_otp,
        "counterparty_notes": "Returned on time in perfect condition."
    }, headers=auth_headers_student_a)
    assert ret_res.status_code == 200
    returned_loan = ret_res.json()
    assert returned_loan["status"] == "RETURNED"
    assert returned_loan["returned_at"] is not None

    # 10. Deposit settlement: Owner settles deposit (full refund ₹250)
    settle_res = client.post(f"/api/loans/{loan_id}/settle-deposit", json={
        "deduct_amount": 0.00,
        "refund_method": "UPI"
    }, headers=auth_headers_student_a)
    assert settle_res.status_code == 200

    # 11. Review: Borrower submits a 5-star review for the owner
    rev_res = client.post("/api/reviews", json={
        "loan_id": loan_id,
        "rating": 5,
        "review_text": "Smooth handover, multimeter worked flawlessly for my lab. Highly recommended!"
    }, headers=auth_headers_student_b)
    assert rev_res.status_code == 201
    assert rev_res.json()["rating"] == 5

    # 12. Verify incoming and outgoing requests endpoints
    in_res = client.get("/api/borrow-requests/incoming", headers=auth_headers_student_a)
    assert in_res.status_code == 200
    assert isinstance(in_res.json(), list)

    out_res = client.get("/api/borrow-requests/outgoing", headers=auth_headers_student_b)
    assert out_res.status_code == 200
    assert isinstance(out_res.json(), list)
