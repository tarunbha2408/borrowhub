def test_admin_endpoints_access_control(client, auth_headers_student_a, auth_headers_admin):
    # Ordinary student denied admin access
    res_denied = client.get("/api/admin/stats", headers=auth_headers_student_a)
    assert res_denied.status_code == 403

    # Admin granted access
    res_ok = client.get("/api/admin/stats", headers=auth_headers_admin)
    assert res_ok.status_code == 200
    stats = res_ok.json()
    assert "total_students" in stats
    assert "active_listings" in stats
    assert stats["total_students"] >= 1


def test_admin_user_moderation(client, auth_headers_admin):
    # Fetch users
    res_users = client.get("/api/admin/users", headers=auth_headers_admin)
    assert res_users.status_code == 200
    users = res_users.json()
    assert len(users) >= 1

    # Suspend user 3 (Rohan Mehta)
    res_suspend = client.put("/api/admin/users/3/status", json={"is_active": False}, headers=auth_headers_admin)
    assert res_suspend.status_code == 200

    # User 3 attempts to login -> Forbidden
    res_login = client.post("/api/auth/login", json={
        "email": "u23cs003@svnit.ac.in",
        "password": "Svnit@2026!"
    })
    assert res_login.status_code == 403

    # Reactivate user 3
    res_reactivate = client.put("/api/admin/users/3/status", json={"is_active": True}, headers=auth_headers_admin)
    assert res_reactivate.status_code == 200
