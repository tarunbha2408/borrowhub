import uuid
import pytest


def test_login_success(client):
    res = client.post("/api/auth/login", json={
        "email": "u23cs001@svnit.ac.in",
        "password": "Svnit@2026!"
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["svnit_email"] == "u23cs001@svnit.ac.in"


def test_login_wrong_password(client):
    res = client.post("/api/auth/login", json={
        "email": "u23cs001@svnit.ac.in",
        "password": "WrongPassword123!"
    })
    assert res.status_code == 401
    assert "Invalid SVNIT email or password" in res.json()["detail"]


def test_register_invalid_domain(client):
    res = client.post("/api/auth/register", json={
        "roll_number": "U24TEST99",
        "full_name": "Test Student",
        "svnit_email": "test@gmail.com",
        "password": "Password123!"
    })
    assert res.status_code == 422  # Pydantic validation error


def test_register_duplicate_email(client):
    res = client.post("/api/auth/register", json={
        "roll_number": "U24DIFF01",
        "full_name": "Duplicate Student",
        "svnit_email": "u23cs001@svnit.ac.in",
        "password": "Password123!"
    })
    assert res.status_code == 400
    assert "already registered" in res.json()["detail"]


def test_register_and_verify_success(client, monkeypatch):
    monkeypatch.setattr("backend.app.services.email_service.send_email_otp", lambda **kwargs: (False, "Test mode"))
    unique_id = uuid.uuid4().hex[:6]
    email = f"u24cs{unique_id}@coed.svnit.ac.in"
    roll = f"U24CS{unique_id.upper()}"

    # Register
    res = client.post("/api/auth/register", json={
        "roll_number": roll,
        "full_name": f"Student {unique_id}",
        "svnit_email": email,
        "password": "SecurePassword@123",
        "hostel_or_dept": "Bhabha Bhavan"
    })
    assert res.status_code == 200
    token = res.json()["access_token"]

    # Request OTP resend for testing verification
    res_otp = client.post("/api/auth/resend-otp", json={"email": email})
    assert res_otp.status_code == 200
    otp = res_otp.json()["otp_debug"]
    assert otp is not None

    # Verify email
    res_verify = client.post("/api/auth/verify-email", json={
        "email": email,
        "otp": otp
    })
    assert res_verify.status_code == 200
    assert res_verify.json()["is_verified"] is True


def test_unauthorized_access(client):
    res = client.get("/api/items/my-listings")
    assert res.status_code == 401


def test_forgot_password_two_step_reset_flow(client, monkeypatch):
    monkeypatch.setattr("backend.app.services.email_service.send_email_otp", lambda **kwargs: (False, "Test mode"))
    unique_id = uuid.uuid4().hex[:6]
    email = f"u24fp{unique_id}@coed.svnit.ac.in"
    roll = f"U24FP{unique_id.upper()}"

    # Register student
    res_reg = client.post("/api/auth/register", json={
        "roll_number": roll,
        "full_name": f"FP Student {unique_id}",
        "svnit_email": email,
        "password": "InitialPassword@123",
        "hostel_or_dept": "Bhabha Bhavan"
    })
    assert res_reg.status_code == 200

    # Step 1: Request reset code
    res_forgot = client.post("/api/auth/forgot-password", json={"email": email})
    assert res_forgot.status_code == 200
    otp = res_forgot.json().get("otp_debug")
    assert otp is not None
    assert len(otp) == 6

    # Step 2: Verify reset OTP (Screen 2: verify OTP only without consuming)
    res_verify = client.post("/api/auth/verify-reset-otp", json={
        "email": email,
        "otp": otp
    })
    assert res_verify.status_code == 200
    assert res_verify.json()["verified"] is True

    # Step 2b: Test invalid OTP gives 400
    res_bad_otp = client.post("/api/auth/verify-reset-otp", json={
        "email": email,
        "otp": "000000"
    })
    assert res_bad_otp.status_code == 400

    # Step 3: Set new password (Screen 3: sets new password using the verified OTP)
    new_password = "BrandNewPassword2026!"
    res_reset = client.post("/api/auth/reset-password", json={
        "email": email,
        "otp_or_token": otp,
        "new_password": new_password
    })
    assert res_reset.status_code == 200

    # Step 4: Login with new password
    res_login = client.post("/api/auth/login", json={
        "email": email,
        "password": new_password
    })
    assert res_login.status_code == 200
    assert "access_token" in res_login.json()

