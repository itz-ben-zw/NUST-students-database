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



def test_payment_allocation_spans_oldest_invoices_first():
    invoices = [
        {"id": 3, "due_on": "2026-10-01", "balance": 700},
        {"id": 2, "due_on": "2026-09-01", "balance": 400},
        {"id": 1, "due_on": "2026-08-01", "balance": 300},
    ]

    assert web_app.allocate_payment(900, invoices) == [(1, 300), (2, 400), (3, 200)]


def test_payment_allocation_rejects_amount_above_total_balance():
    invoices = [
        {"id": 1, "due_on": "2026-08-01", "balance": 300},
        {"id": 2, "due_on": "2026-09-01", "balance": 400},
    ]

    try:
        web_app.allocate_payment(701, invoices)
    except ValueError as exc:
        assert "outstanding balance" in str(exc)
    else:
        raise AssertionError("An overpayment should be rejected.")


def test_payment_allocation_handles_exact_total_balance():
    invoices = [
        {"id": 1, "due_on": "2026-08-01", "balance": 300},
        {"id": 2, "due_on": "2026-09-01", "balance": 400},
    ]

    assert web_app.allocate_payment(700, invoices) == [(1, 300), (2, 400)]



def test_mixed_currency_invoice_rows_keep_allocations_separate():
    # One invoice can have separate USD and ZWG balances.
    invoice_rows = [
        {"id": 41, "due_on": "2026-08-01", "currency": "USD", "balance": 12500},
        {"id": 41, "due_on": "2026-08-01", "currency": "ZWG", "balance": 900000},
    ]

    usd_rows = [row for row in invoice_rows if row["currency"] == "USD"]
    zwg_rows = [row for row in invoice_rows if row["currency"] == "ZWG"]

    assert web_app.allocate_payment(5000, usd_rows) == [(41, 5000)]
    assert web_app.allocate_payment(300000, zwg_rows) == [(41, 300000)]


def test_mixed_currency_invoice_rejects_overpayment_in_selected_currency():
    invoice_rows = [
        {"id": 41, "due_on": "2026-08-01", "currency": "USD", "balance": 12500},
        {"id": 41, "due_on": "2026-08-01", "currency": "ZWG", "balance": 900000},
    ]

    try:
        web_app.allocate_payment(12501, [row for row in invoice_rows if row["currency"] == "USD"])
    except ValueError as exc:
        assert "outstanding balance" in str(exc)
    else:
        raise AssertionError("USD payment must not consume the ZWG balance.")



def test_demo_session_is_a_distinct_read_only_identity():
    from flask import session

    with web_app.app.test_request_context("/"):
        session["demo_mode"] = True
        profile = security.current_employee()
        assert profile["role"] == "demo"
        assert profile["user_id"] == "read-only-demo"


def test_demo_session_cannot_post_a_payment():
    web_app.app.config["WTF_CSRF_ENABLED"] = False
    client = web_app.app.test_client()
    with client.session_transaction() as browser_session:
        browser_session["demo_mode"] = True
    response = client.post("/payments", data={"student_id": "1", "amount": "1.00"})
    assert response.status_code == 403


def test_try_demo_starts_without_employee_credentials():
    web_app.app.config["WTF_CSRF_ENABLED"] = False
    client = web_app.app.test_client()
    response = client.post("/try-demo")
    assert response.status_code == 302
    with client.session_transaction() as browser_session:
        assert browser_session.get("demo_mode") is True
        assert "web_session_id" not in browser_session
