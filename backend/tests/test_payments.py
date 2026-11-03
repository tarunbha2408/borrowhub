import random
from datetime import date, timedelta


def test_payment_flow(client, auth_headers_student_a, auth_headers_student_b):
    # Student A creates a dedicated item
    item_res = client.post("/api/items", json={
        "title": f"Payment Test Breadboard {random.randint(1000, 9999)}",
        "category_id": 2,
        "location_id": 1,
        "description": "Electronics breadboard for circuit prototyping.",
        "item_condition": "NEW",
        "deposit_amount": 150.00,
        "daily_fee": 10.00,
        "max_borrow_days": 7,
        "image_urls": ["https://images.unsplash.com/photo-1518770660439-4636190af475"]
    }, headers=auth_headers_student_a)
    assert item_res.status_code == 201
    item_id = item_res.json()["item_id"]

    today = date.today()
    offset = random.randint(20, 300)
    start = today + timedelta(days=offset)
    end = today + timedelta(days=offset + 2)

    # Student B requests Item
    req_res = client.post("/api/borrow-requests", json={
        "item_id": item_id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "request_message": "Need for microprocessors project"
    }, headers=auth_headers_student_b)
    assert req_res.status_code == 201
    req_id = req_res.json()["request_id"]

    # Student A approves
    app_res = client.post(f"/api/borrow-requests/{req_id}/approve", headers=auth_headers_student_a)
    assert app_res.status_code == 200
    loan_id = app_res.json()["loan_id"]

    # Student B creates a payment order
    order_res = client.post("/api/payments/create-order", json={
        "loan_id": loan_id,
        "payment_type": "RENTAL_FEE"
    }, headers=auth_headers_student_b)
    assert order_res.status_code == 200
    order_data = order_res.json()
    assert "order_id" in order_data
    payment_id = order_data["payment_id"]

    # Student B submits verification
    verify_res = client.post("/api/payments/verify", json={
        "payment_id": payment_id,
        "razorpay_order_id": order_data["order_id"],
        "razorpay_payment_id": f"pay_test_{payment_id}",
        "razorpay_signature": "dummy_valid_test_signature"
    }, headers=auth_headers_student_b)
    assert verify_res.status_code == 200
    assert verify_res.json()["payment_status"] == "COMPLETED"

    # Check payment history
    history_res = client.get("/api/payments/history", headers=auth_headers_student_b)
    assert history_res.status_code == 200
    history = history_res.json()
    assert any(p["payment_id"] == payment_id for p in history)
