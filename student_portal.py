"""Student-only portal routes.

Every query is scoped by the student_id resolved from the verified Supabase
Auth identity. No student number or email supplied by the browser is trusted
as an authorization input.
"""
from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
import requests

from security import (
    AuthenticationUnavailable,
    clear_student_session,
    create_student_web_session,
    current_student,
    sign_in_student_with_password,
    student_login_required,
)

student_portal = Blueprint("student_portal", __name__)


@student_portal.route("/student/login", methods=["GET", "POST"])
def student_login():
    if current_student():
        return redirect(url_for("student_portal.student_dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        try:
            result = sign_in_student_with_password(email, password)
            # Establish a clean student-only browser session.
            session.clear()
            session.permanent = True
            session["student_web_session_id"] = create_student_web_session(
                result["token"], result["user_id"], result["student_id"]
            )
            return redirect(url_for("student_portal.student_dashboard"))
        except ValueError as exc:
            flash(str(exc), "error")
        except (AuthenticationUnavailable, requests.RequestException):
            flash("Student sign-in is temporarily unavailable. Please try again.", "error")
    return render_template("student_login.html")


@student_portal.post("/student/logout")
@student_login_required
def student_logout():
    clear_student_session()
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("student_portal.student_login"))


@student_portal.get("/student/dashboard")
@student_login_required
def student_dashboard():
    from app import get_db
    db = get_db()
    student = current_student()
    student_id = student["student_id"]
    profile = db.execute(
        """
        SELECT s.id, s.student_no, s.first_name, s.last_name, s.status,
               p.name AS programme_name, p.award_level,
               f.name AS faculty_name
        FROM students s
        JOIN programmes p ON p.id = s.programme_id
        JOIN faculties f ON f.id = p.faculty_id
        WHERE s.id = %s
        """,
        (student_id,),
    ).fetchone()
    if not profile:
        abort(404)

    invoices = db.execute(
        """
        SELECT i.id, i.invoice_no, i.issued_on, i.due_on, i.status,
               a.academic_year, a.semester_number, il.currency,
               SUM(il.amount_cents) AS billed,
               COALESCE((
                   SELECT SUM(pa.amount_cents)
                   FROM payment_allocations pa
                   JOIN payments pay ON pay.id = pa.payment_id
                   WHERE pa.invoice_id = i.id AND pay.currency = il.currency
               ), 0) AS paid
        FROM invoices i
        JOIN invoice_lines il ON il.invoice_id = i.id
        JOIN academic_semesters a ON a.id = i.semester_id
        WHERE i.student_id = %s AND i.status <> 'Void'
        GROUP BY i.id, i.invoice_no, i.issued_on, i.due_on, i.status,
                 a.academic_year, a.semester_number, il.currency
        ORDER BY a.academic_year DESC, a.semester_number DESC, i.due_on DESC
        """,
        (student_id,),
    ).fetchall()
    invoice_rows = [
        dict(row) | {"balance": max(0, row["billed"] - row["paid"])}
        for row in invoices
    ]

    payments = db.execute(
        """
        SELECT p.receipt_no, p.paid_on, p.amount_cents, p.currency, p.method,
               COALESCE(string_agg(DISTINCT i.invoice_no, ', '), '') AS invoices
        FROM payments p
        LEFT JOIN payment_allocations pa ON pa.payment_id = p.id
        LEFT JOIN invoices i ON i.id = pa.invoice_id
        WHERE p.student_id = %s
        GROUP BY p.id
        ORDER BY p.paid_on DESC, p.id DESC
        LIMIT 12
        """,
        (student_id,),
    ).fetchall()

    totals = {}
    for row in invoice_rows:
        item = totals.setdefault(row["currency"], {"currency": row["currency"], "billed": 0, "paid": 0, "balance": 0})
        item["billed"] += row["billed"]
        item["paid"] += row["paid"]
        item["balance"] += row["balance"]

    return render_template(
        "student_dashboard.html",
        student_profile=profile,
        invoices=invoice_rows,
        payments=payments,
        totals=list(totals.values()),
    )
