"""Basic route-level checks for the isolated student portal."""
from flask import Flask
import student_portal


def make_app():
    app = Flask(__name__)
    app.secret_key = "test-only-secret"
    app.register_blueprint(student_portal.student_portal)
    return app


def test_student_dashboard_requires_verified_student_session(monkeypatch):
    monkeypatch.setattr(student_portal, "current_student", lambda: None)
    response = make_app().test_client().get("/student/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/student/login")


def test_student_logout_is_not_available_without_student_session(monkeypatch):
    monkeypatch.setattr(student_portal, "current_student", lambda: None)
    response = make_app().test_client().post("/student/logout")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/student/login")

def test_student_assistant_page_requires_verified_student_session(monkeypatch):
    monkeypatch.setattr(student_portal, "current_student", lambda: None)
    response = make_app().test_client().get("/student/assistant")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/student/login")


def test_student_assistant_api_requires_verified_student_session(monkeypatch):
    monkeypatch.setattr(student_portal, "current_student", lambda: None)
    response = make_app().test_client().post(
        "/api/student/assistant/chat", json={"question": "Show me my balance"}
    )
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/student/login")
