"""Fast, database-free regression tests for the application's access boundaries."""
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
    assert b"Student accounts" in response.data
    assert b"Illustrative records" in response.data


def test_homepage_opens_public_preview_for_visitors():
    response = web_app.app.test_client().get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/preview")


def test_dashboard_financial_totals_are_separated_by_currency():
    rows = [
        {"currency": "USD", "billed": 10000, "paid": 2500, "balance": 7500},
        {"currency": "USD", "billed": 5000, "paid": 5000, "balance": 0},
        {"currency": "ZWG", "billed": 90000, "paid": 30000, "balance": 60000},
    ]

    totals = {item["currency"]: item for item in web_app.summarize_financials(rows)}

    assert totals["USD"] == {
        "currency": "USD", "billed": 15000, "paid": 7500,
        "balance": 7500, "rate": 50,
    }
    assert totals["ZWG"] == {
        "currency": "ZWG", "billed": 90000, "paid": 30000,
        "balance": 60000, "rate": 33,
    }


def test_dashboard_financial_totals_handle_empty_and_zero_billed_rows():
    assert web_app.summarize_financials([]) == []
    assert web_app.summarize_financials([
        {"currency": "USD", "billed": 0, "paid": 0, "balance": 0}
    ]) == [{
        "currency": "USD", "billed": 0, "paid": 0,
        "balance": 0, "rate": 0,
    }]
