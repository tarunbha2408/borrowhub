"""Tests for the Query Lab (read-only SQL console)."""


def test_query_lab_runs_a_select(client, auth_headers_admin):
    res = client.post(
        "/api/query-lab/run",
        params={"sql": "SELECT item_id, title FROM item ORDER BY item_id"},
        headers=auth_headers_admin,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["columns"] == ["item_id", "title"]
    assert body["row_count"] >= 1
    assert body["statement_type"] == "SELECT"
    assert body["execution_ms"] >= 0
    assert "plan" in body, "the optimiser plan should be returned for a SELECT"


def test_query_lab_rejects_non_admin(client, auth_headers_student_a):
    res = client.post(
        "/api/query-lab/run",
        params={"sql": "SELECT 1"},
        headers=auth_headers_student_a,
    )
    assert res.status_code == 403


def test_query_lab_requires_a_session(client):
    res = client.post("/api/query-lab/run", params={"sql": "SELECT 1"})
    assert res.status_code == 401


def test_query_lab_blocks_writes(client, auth_headers_admin):
    for sql in (
        "DELETE FROM item",
        "UPDATE item SET daily_fee = 0",
        "DROP TABLE item",
        "INSERT INTO category (category_name) VALUES ('x')",
        "ALTER TABLE item ADD COLUMN hacked INT",
        "TRUNCATE TABLE item",
        "CALL sp_run_system_maintenance()",
    ):
        res = client.post("/api/query-lab/run", params={"sql": sql}, headers=auth_headers_admin)
        assert res.status_code == 400, f"{sql} should have been refused, got {res.status_code}"
        assert "read-only" in res.json()["detail"].lower() or "not allowed" in res.json()["detail"].lower()


def test_query_lab_blocks_stacked_statements(client, auth_headers_admin):
    for sql in (
        "SELECT 1; DROP TABLE item",
        "SELECT 1 /* x */ ; DELETE FROM item",
        "SELECT 1 -- \n; DELETE FROM item",
    ):
        res = client.post("/api/query-lab/run", params={"sql": sql}, headers=auth_headers_admin)
        assert res.status_code == 400
        assert "one statement" in res.json()["detail"].lower()


def test_query_lab_blocks_confidential_columns(client, auth_headers_admin):
    for sql in ("SELECT password_hash FROM app_user",
                "SELECT token_hash FROM auth_token"):
        res = client.post("/api/query-lab/run", params={"sql": sql}, headers=auth_headers_admin)
        assert res.status_code == 400
        assert "confidential" in res.json()["detail"].lower()


def test_query_lab_blocks_system_schemas(client, auth_headers_admin):
    res = client.post(
        "/api/query-lab/run",
        params={"sql": "SELECT user, authentication_string FROM mysql.user"},
        headers=auth_headers_admin,
    )
    assert res.status_code == 400


def test_query_lab_caps_result_rows(client, auth_headers_admin):
    res = client.post(
        "/api/query-lab/run",
        params={"sql": "SELECT * FROM information_schema.columns"},
        headers=auth_headers_admin,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["row_count"] == body["row_cap"]
    assert body["truncated"] is True


def test_query_lab_reports_sql_errors_readably(client, auth_headers_admin):
    res = client.post(
        "/api/query-lab/run",
        params={"sql": "SELECT * FROM table_that_does_not_exist"},
        headers=auth_headers_admin,
    )
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "doesn't exist" in detail
    assert "Background on this error" not in detail


def test_query_lab_examples_are_valid_sql(client, auth_headers_admin):
    """Every curated example must actually run - they are shown as one-click demos."""
    groups = client.get("/api/query-lab/examples", headers=auth_headers_admin).json()["groups"]
    total = 0
    for group in groups:
        for item in group["items"]:
            total += 1
            res = client.post("/api/query-lab/run", params={"sql": item["sql"]},
                              headers=auth_headers_admin)
            assert res.status_code == 200, f"{item['title']} failed: {res.text}"
    assert total >= 15


def test_demo_reset_endpoint_is_disabled_without_token(client):
    """The operational endpoint must be invisible unless a token is configured."""
    res = client.post("/api/internal/reset-demo", headers={"X-Demo-Reset-Token": "anything"})
    assert res.status_code == 404


def test_demo_reset_requires_matching_token(client, monkeypatch):
    from backend.app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "DEMO_RESET_TOKEN", "expected-token")
    from backend.app.routes import internal as internal_module

    monkeypatch.setattr(internal_module, "_last_reset_at", 0.0)

    bad = client.post("/api/internal/reset-demo", headers={"X-Demo-Reset-Token": "wrong"})
    assert bad.status_code == 401

    none = client.post("/api/internal/reset-demo")
    assert none.status_code == 401


def test_demo_reset_rebuilds_the_database(client, monkeypatch):
    """A full reset must restore the exact seeded state."""
    from backend.app.core import config as config_module
    from backend.app.routes import internal as internal_module
    from backend.app.core.db_bootstrap import reset_demo_database

    monkeypatch.setattr(config_module.settings, "DEMO_RESET_TOKEN", "expected-token")
    monkeypatch.setattr(internal_module, "_last_reset_at", 0.0)

    # Dirty the database first.
    client.post("/api/query-lab/run", params={"sql": "SELECT 1"})
    from backend.app.models.user import AppUser
    from backend.app.core.database import SessionLocal

    session = SessionLocal()
    try:
        session.execute(__import__("sqlalchemy").text(
            "UPDATE item SET title = 'JUNK ROW' WHERE item_id = 1"))
        session.commit()
    finally:
        session.close()

    res = client.post("/api/internal/reset-demo",
                      headers={"X-Demo-Reset-Token": "expected-token"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tables"] >= 30
    assert body["accounts"] == 7
    assert body["items"] == 6
    assert body["triggers"] == 30

    session = SessionLocal()
    try:
        junk = session.execute(__import__("sqlalchemy").text(
            "SELECT COUNT(*) FROM item WHERE title = 'JUNK ROW'")).scalar()
        assert junk == 0
    finally:
        session.close()
