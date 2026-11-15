from __future__ import annotations

import os
import json
import uuid
import psycopg
from psycopg.rows import dict_row
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import requests

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect

from security import (AuthenticationUnavailable, create_web_session, current_employee,
                      delete_web_session, invite_employee, list_employee_profiles, set_employee_active,
                      login_required, roles_required, sign_in_with_password)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("Set SECRET_KEY before starting the application.")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=__import__("datetime").timedelta(minutes=30),
)
csrf = CSRFProtect(app)

@app.get("/healthz")
def healthz():
    try:
        get_db().execute("SELECT 1").fetchone()
        return {"status": "ok"}, 200
    except Exception:
        app.logger.exception("Database health check failed.")
        return {"status": "unavailable"}, 503


@app.context_processor
def inject_employee():
    return {"current_employee": current_employee()}

@app.get("/preview")
def public_preview():
    """Public, read-only showcase populated only with fictional static examples."""
    return render_template("preview.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_employee():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        try:
            result = sign_in_with_password(email, password)
            session.clear()
            session.permanent = True
            session["web_session_id"] = create_web_session(result["token"], result["profile"]["user_id"])
            target = request.args.get("next", "")
            if not target.startswith("/") or target.startswith("//"):
                target = url_for("dashboard")
            return redirect(target)
        except ValueError as exc:
            flash(str(exc), "error")
        except (AuthenticationUnavailable, requests.RequestException) as exc:
            app.logger.warning("Employee sign-in unavailable: %s", exc)
            flash("Sign-in is temporarily unavailable. Please try again later.", "error")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    try:
        delete_web_session(session.get("web_session_id"))
    except requests.RequestException:
        app.logger.warning("Could not remove server-side employee session during sign-out.")
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))

@app.route("/admin/employees", methods=["GET", "POST"])
@roles_required("system_admin")
def employee_admin():
    if request.method == "POST" and request.form.get("action") == "toggle_active":
        target_user_id = request.form.get("user_id", "")
        active = request.form.get("active") == "true"
        actor = current_employee()
        if target_user_id == actor["user_id"] and not active:
            flash("You cannot deactivate your own administrator account.", "error")
            return redirect(url_for("employee_admin"))
        try:
            set_employee_active(target_user_id, active, actor["user_id"])
            flash("Employee access updated.", "success")
        except (ValueError, AuthenticationUnavailable, requests.RequestException) as exc:
            app.logger.error("Employee access update failed: %s", exc)
            flash("Could not update employee access. Review the employee record and audit log.", "error")
        return redirect(url_for("employee_admin"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "").strip()
        actor = current_employee()
        try:
            invite_employee(email, full_name, role, actor["user_id"])
            flash(f"Invitation sent to {email}. Access activates after the employee accepts and signs in.", "success")
            return redirect(url_for("employee_admin"))
        except ValueError as exc:
            flash(str(exc), "error")
        except (AuthenticationUnavailable, requests.RequestException) as exc:
            app.logger.error("Employee invitation failed: %s", exc)
            flash("Could not complete the invitation. Check Supabase Auth and employee_profiles before retrying.", "error")
    try:
        employees = list_employee_profiles()
    except (AuthenticationUnavailable, requests.RequestException) as exc:
        app.logger.error("Could not load employee list: %s", exc)
        employees = []
        flash("Employee directory is temporarily unavailable.", "error")
    return render_template("employees.html", employees=employees)


def connect_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL must point to the Supabase PostgreSQL database.")
    if "sslmode=" not in DATABASE_URL:
        raise RuntimeError("DATABASE_URL must specify sslmode=require or a stronger SSL mode.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row,
                           prepare_threshold=None, connect_timeout=10)


def get_db():
    if "db" not in g:
        g.db = connect_db()
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def money(cents, currency="USD"):
    return f"{currency} {cents / 100:,.2f}"


app.jinja_env.filters["money"] = money


def invoice_rows(where="", params=()):
    return get_db().execute(f"""
      SELECT i.id, i.invoice_no, i.issued_on, i.due_on, i.status,
             s.id AS student_id, s.student_no, s.first_name, s.last_name, s.status AS student_status,
             p.name AS programme_name, f.name AS faculty_name,
             a.academic_year, a.semester_number,
             COALESCE((SELECT SUM(amount_cents) FROM invoice_lines il WHERE il.invoice_id=i.id),0) AS billed,
             COALESCE((SELECT SUM(pa.amount_cents) FROM payment_allocations pa WHERE pa.invoice_id=i.id),0) AS paid,
             COALESCE((SELECT currency FROM invoice_lines il WHERE il.invoice_id=i.id LIMIT 1),'USD') AS currency
      FROM invoices i JOIN students s ON s.id=i.student_id
      JOIN programmes p ON p.id=s.programme_id JOIN faculties f ON f.id=p.faculty_id
      JOIN academic_semesters a ON a.id=i.semester_id
      {where} ORDER BY s.last_name, s.first_name
    """, params).fetchall()


def decorate_invoices(rows):
    return [dict(row) | {"balance": max(0, row["billed"] - row["paid"])} for row in rows]


@app.route("/")
def dashboard():
    employee = current_employee()
    if employee is None:
        return redirect(url_for("public_preview"))
    if employee.get("role") not in {"system_admin", "finance", "student_records", "auditor"}:
        abort(403)
    invoices = decorate_invoices(invoice_rows("WHERE i.semester_id=(SELECT id FROM academic_semesters WHERE academic_year='2026' AND semester_number=2)"))
    total_billed = sum(row["billed"] for row in invoices)
    total_collected = sum(row["paid"] for row in invoices)
    total_due = sum(row["balance"] for row in invoices)
    db = get_db()
    recent = db.execute("""
      SELECT p.*, s.first_name, s.last_name, s.student_no
      FROM payments p JOIN students s ON s.id=p.student_id ORDER BY p.paid_on DESC,p.id DESC LIMIT 5
    """).fetchall()
    all_due = sorted([row for row in invoices if row["balance"] > 0], key=lambda row: row["balance"], reverse=True)
    faculty_rows = []
    for faculty_name in dict.fromkeys(row["faculty_name"] for row in invoices):
        group = [row for row in invoices if row["faculty_name"] == faculty_name]
        billed = sum(row["billed"] for row in group)
        paid = sum(row["paid"] for row in group)
        faculty_rows.append({"name": faculty_name, "students": len(group), "billed": billed,
                             "paid": paid, "balance": sum(row["balance"] for row in group),
                             "rate": round(paid / billed * 100) if billed else 0,
                             "currency": group[0]["currency"]})
    return render_template("dashboard.html", invoices=invoices, recent=recent, due=all_due[:4],
                           due_count=len(all_due), faculties=faculty_rows, total_billed=total_billed,
                           total_collected=total_collected, total_due=total_due,
                           collection_rate=round(total_collected / total_billed * 100) if total_billed else 0)


@app.route("/students")
@roles_required("system_admin", "student_records", "auditor")
def students():
    q = request.args.get("q", "").strip()
    sql = """
      SELECT s.*, p.name AS programme_name, f.name AS faculty_name,
        (SELECT sp.display_name FROM student_sponsors ss JOIN sponsors sp ON sp.id=ss.sponsor_id WHERE ss.student_id=s.id LIMIT 1) AS sponsor_name
      FROM students s JOIN programmes p ON p.id=s.programme_id JOIN faculties f ON f.id=p.faculty_id
    """
    params = ()
    if q:
        sql += " WHERE s.student_no ILIKE %s OR s.first_name ILIKE %s OR s.last_name ILIKE %s OR p.name ILIKE %s OR f.name ILIKE %s"
        params = (f"%{q}%",) * 5
    rows = get_db().execute(sql + " ORDER BY s.last_name,s.first_name", params).fetchall()
    account_invoices = decorate_invoices(invoice_rows("WHERE i.semester_id=(SELECT id FROM academic_semesters WHERE academic_year='2026' AND semester_number=2)"))
    balances = {row["student_no"]: row["balance"] for row in account_invoices}
    account_states = {}
    for row in account_invoices:
        if row["balance"] <= 0:
            account_states[row["student_no"]] = "Paid"
        elif row["paid"] > 0:
            account_states[row["student_no"]] = "Partial"
        else:
            account_states[row["student_no"]] = "Owing"
    return render_template("students.html", students=rows, balances=balances, account_states=account_states, q=q)


@app.route("/invoices")
@roles_required("system_admin", "finance", "auditor")
def invoices_page():
    invoices = decorate_invoices(invoice_rows())
    return render_template("invoices.html", invoices=invoices,
                           outstanding=sum(row["balance"] for row in invoices))


@app.route("/payments", methods=["GET", "POST"])
@roles_required("system_admin", "finance")
def payments():
    db = get_db()
    if request.method == "POST":
        student_id = request.form.get("student_id", type=int)
        raw_amount = request.form.get("amount", "").strip()
        paid_on = request.form.get("paid_on", "").strip()
        currency = request.form.get("currency", "USD")
        method = request.form.get("method", "")
        reference = request.form.get("reference", "").strip() or None
        try:
            amount = Decimal(raw_amount).quantize(Decimal("0.01"))
            if amount <= 0:
                raise ValueError
            cents = int(amount * 100)
            datetime.strptime(paid_on, "%Y-%m-%d")
        except (InvalidOperation, ValueError, TypeError):
            flash("Enter a valid payment amount and date.", "error")
            return redirect(url_for("payments"))
        if currency not in ("USD", "ZWG") or method not in ("EcoCash", "Bank transfer", "RTGS"):
            flash("Choose a listed currency and payment method.", "error")
            return redirect(url_for("payments"))
        current = decorate_invoices(invoice_rows("WHERE i.student_id=%s AND i.status!='Void'", (student_id,)))
        invoice = next((row for row in sorted(current, key=lambda item: (item["due_on"], item["id"]))
                        if row["balance"] > 0 and row["currency"] == currency), None)
        if not invoice:
            flash("This student has no outstanding invoice in that currency.", "error")
            return redirect(url_for("payments"))
        try:
            # Lock the chosen invoice and re-read its balance inside this transaction.
            db.execute("SELECT id FROM invoices WHERE id=%s FOR UPDATE", (invoice["id"],)).fetchone()
            refreshed = decorate_invoices(invoice_rows("WHERE i.id=%s AND i.status!='Void'", (invoice["id"],)))
            invoice = refreshed[0] if refreshed else None
            if not invoice or invoice["balance"] <= 0 or invoice["currency"] != currency:
                db.rollback()
                flash("That invoice is no longer available for payment. Refresh and try again.", "error")
                return redirect(url_for("payments"))
            if cents > invoice["balance"]:
                db.rollback()
                flash("Payment is higher than this invoice’s remaining balance.", "error")
                return redirect(url_for("payments"))
            receipt_no = f"NUST-RCP-SAMPLE-{datetime.now().strftime('%y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
            actor = current_employee()
            recorded_by = actor.get("full_name") or actor["email"]
            cur = db.execute("INSERT INTO payments(receipt_no,student_id,paid_on,amount_cents,currency,method,reference,recorded_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                             (receipt_no, student_id, paid_on, cents, currency, method, reference, recorded_by))
            payment_id = cur.fetchone()["id"]
            db.execute("INSERT INTO payment_allocations(payment_id,invoice_id,amount_cents) VALUES(%s,%s,%s)",
                       (payment_id, invoice["id"], cents))
            if cents == invoice["balance"]:
                db.execute("UPDATE invoices SET status='Paid' WHERE id=%s", (invoice["id"],))
            db.execute(
                "INSERT INTO audit_logs(actor_user_id,action,entity_type,entity_id,details) VALUES(%s,%s,%s,%s,%s::jsonb)",
                (actor["user_id"], "payment.recorded", "payment", str(payment_id),
                 json.dumps({"receipt_no": receipt_no, "student_id": student_id,
                             "amount_cents": cents, "currency": currency,
                             "invoice_id": invoice["id"]})),
            )
            db.commit()
        except psycopg.IntegrityError:
            db.rollback()
            flash("Could not save the payment. Please try again.", "error")
            return redirect(url_for("payments"))
        flash(f"Payment recorded. Receipt {receipt_no} is ready.", "success")
        return redirect(url_for("payments", receipt=receipt_no))
    rows = db.execute("""
      SELECT s.id,s.student_no,s.first_name,s.last_name,p.name AS programme_name,
        COALESCE((SELECT SUM(il.amount_cents) FROM invoices i JOIN invoice_lines il ON il.invoice_id=i.id WHERE i.student_id=s.id),0)-
        COALESCE((SELECT SUM(pa.amount_cents) FROM invoices i JOIN payment_allocations pa ON pa.invoice_id=i.id WHERE i.student_id=s.id),0) AS balance,
        COALESCE((SELECT currency FROM invoices i JOIN invoice_lines il ON il.invoice_id=i.id WHERE i.student_id=s.id LIMIT 1),'USD') AS currency
      FROM students s JOIN programmes p ON p.id=s.programme_id WHERE s.status!='Deferred' ORDER BY s.last_name
    """).fetchall()
    recent = db.execute("""
      SELECT p.*,s.first_name,s.last_name,s.student_no
      FROM payments p JOIN students s ON s.id=p.student_id ORDER BY p.paid_on DESC,p.id DESC
    """).fetchall()
    selected = request.args.get("receipt")
    receipt = next((row for row in recent if row["receipt_no"] == selected), None)
    return render_template("payments.html", students=rows, payments=recent, receipt=receipt,
                           today=date.today().isoformat(), selected_student_id=request.args.get("student_id", type=int))


@app.route("/reports")
@roles_required("system_admin", "finance", "auditor")
def reports():
    rows = decorate_invoices(invoice_rows())
    totals = {}
    for row in rows:
        item = totals.setdefault(row["currency"], {"billed": 0, "paid": 0, "balance": 0})
        item["billed"] += row["billed"]
        item["paid"] += row["paid"]
        item["balance"] += row["balance"]
    faculty_rows = []
    for faculty in get_db().execute("SELECT id,name FROM faculties ORDER BY name"):
        group = [row for row in rows if row["faculty_name"] == faculty["name"]]
        faculty_rows.append({"name": faculty["name"], "students": len(group),
                             "billed": sum(row["billed"] for row in group),
                             "paid": sum(row["paid"] for row in group),
                             "balance": sum(row["balance"] for row in group)})
    return render_template("reports.html", totals=totals, faculties=faculty_rows, invoices=rows)


@app.route("/receipt/<receipt_no>")
@roles_required("system_admin", "finance", "auditor")
def receipt_page(receipt_no):
    row = get_db().execute("""
      SELECT p.*,s.first_name,s.last_name,s.student_no,pr.name AS programme_name,f.name AS faculty_name
      FROM payments p JOIN students s ON s.id=p.student_id
      JOIN programmes pr ON pr.id=s.programme_id JOIN faculties f ON f.id=pr.faculty_id
      WHERE p.receipt_no=%s
    """, (receipt_no,)).fetchone()
    if row is None:
        abort(404)
    return render_template("receipt.html", receipt=row)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
