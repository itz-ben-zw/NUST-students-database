"""Fast, database-free regression tests for the demo's access boundaries."""
import os

os.environ.setdefault("SECRET_KEY", "ci-only-test-secret")

import app as web_app
import security


def employee(role):
    return {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "email": "test@nust.ac.zw",
        "full_name": "Test Employee",
        "role": role,
        "is_active": True,
    }


def test_anonymous_users_are_redirected_to_sign_in():
    client = web_app.app.test_client()
    response = client.get("/students")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_finance_role_cannot_open_student_records(monkeypatch):
    monkeypatch.setattr(security, "current_employee", lambda: employee("finance"))
    response = web_app.app.test_client().get("/students")
    assert response.status_code == 403


def test_student_records_role_cannot_record_payments(monkeypatch):
    monkeypatch.setattr(security, "current_employee", lambda: employee("student_records"))
    response = web_app.app.test_client().get("/payments")
    assert response.status_code == 403


def test_auditor_role_cannot_record_payments(monkeypatch):
    monkeypatch.setattr(security, "current_employee", lambda: employee("auditor"))
    response = web_app.app.test_client().get("/payments")
    assert response.status_code == 403


def test_login_page_renders_csrf_protection():
    response = web_app.app.test_client().get("/login")
    assert response.status_code == 200
    assert b'name="csrf_token"' in response.data


def test_login_post_without_csrf_token_is_rejected():
    response = web_app.app.test_client().post(
        "/login",
        data={"email": "test@nust.ac.zw", "password": "not-a-real-password"},
    )
    assert response.status_code == 400


def test_public_preview_is_available_without_database_or_login():
    response = web_app.app.test_client().get("/preview")
    assert response.status_code == 200
    assert b"PUBLIC PREVIEW" in response.data
    assert b"fictional" in response.data.lower()


def test_homepage_opens_public_preview_for_visitors():
    response = web_app.app.test_client().get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/preview")
