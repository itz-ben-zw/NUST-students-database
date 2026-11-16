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


def clear_auth_session():
    """Clear authentication state without invalidating Flask-WTF's CSRF token."""
    csrf_token = session.get("_csrf_token")
    session.clear()
    if csrf_token:
        session["_csrf_token"] = csrf_token

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


@app.post("/try-demo")
def try_demo():
    """Start a short-lived, signed-cookie demo session without an employee account."""
    clear_auth_session()
    session.permanent = True
    session["demo_mode"] = True
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_employee():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        try:
            result = sign_in_with_password(email, password)
            clear_auth_session()
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
        if session.get("web_session_id"):
            delete_web_session(session.get("web_session_id"))
    except requests.RequestException:
        app.logger.warning("Could not remove server-side employee session during sign-out.")
    clear_auth_session()
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

    # Inspect only the query component without urlsplit(). Supabase passwords
    # may contain bracket characters that make urllib's authority parser fail.
    # libpq accepts sslmode as a separate keyword and preserves URI credentials.
    query_string = DATABASE_URL.partition("?")[2]
    query_items = [item.split("=", 1) for item in query_string.split("&") if item]
    sslmode = next(
        (pair[1] if len(pair) == 2 else "" for pair in query_items
         if pair[0].lower() == "sslmode"),
        None,
    )
    if sslmode is not None and sslmode.lower() in {"disable", "allow", "prefer"}:
        raise RuntimeError("DATABASE_URL must use sslmode=require, verify-ca or verify-full.")

    connect_options = {} if sslmode is not None else {"sslmode": "require"}
    return psycopg.connect(DATABASE_URL, row_factory=dict_row,
                           prepare_threshold=None, connect_timeout=10,
                           **connect_options)


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
             a.academic_year, a.semester_number, il.currency,
             SUM(il.amount_cents) AS billed,
             COALESCE((
               SELECT SUM(pa.amount_cents)
               FROM payment_allocations pa
               JOIN payments pay ON pay.id=pa.payment_id
               WHERE pa.invoice_id=i.id AND pay.currency=il.currency
             ),0) AS paid
      FROM invoices i JOIN students s ON s.id=i.student_id
      JOIN programmes p ON p.id=s.programme_id JOIN faculties f ON f.id=p.faculty_id
      JOIN academic_semesters a ON a.id=i.semester_id
      JOIN invoice_lines il ON il.invoice_id=i.id
      {where}
      GROUP BY i.id, i.invoice_no, i.issued_on, i.due_on, i.status,
               s.id, s.student_no, s.first_name, s.last_name, s.status,
               p.name, f.name, a.academic_year, a.semester_number, il.currency
      ORDER BY s.last_name, s.first_name, i.due_on, il.currency
    """, params).fetchall()


def decorate_invoices(rows):
    return [dict(row) | {"balance": max(0, row["billed"] - row["paid"])} for row in rows]


def allocate_payment(cents, invoices):
    """Allocate a payment oldest-due-first without crossing currency boundaries."""
    remaining = cents
    allocations = []
    for invoice in sorted(invoices, key=lambda row: (row["due_on"], row["id"])):
        available = max(0, invoice["balance"])
        allocated = min(remaining, available)
        if allocated:
            allocations.append((invoice["id"], allocated))
            remaining -= allocated
        if remaining == 0:
            break
    if remaining:
        raise ValueError("Payment exceeds the outstanding balance in this currency.")
    return allocations


def summarize_financials(rows):
    """Aggregate invoice totals independently for each currency."""
    totals_by_currency = {}
    for row in rows:
        currency = row["currency"]
        totals = totals_by_currency.setdefault(
            currency, {"currency": currency, "billed": 0, "paid": 0, "balance": 0}
        )
        totals["billed"] += row["billed"]
        totals["paid"] += row["paid"]
        totals["balance"] += row["balance"]
    for totals in totals_by_currency.values():
        totals["rate"] = round(totals["paid"] / totals["billed"] * 100) if totals["billed"] else 0
    return list(totals_by_currency.values())




@app.route("/")
def dashboard():
    employee = current_employee()
    if employee is None:
        return redirect(url_for("public_preview"))
    if employee.get("role") not in {"system_admin", "finance", "student_records", "auditor", "demo"}:
        abort(403)
    demo_mode = employee.get("role") == "demo"
    invoice_scope = "left(s.student_no, 7) = 'DEMO26-' AND " if demo_mode else ""
    invoices = decorate_invoices(invoice_rows(
        f"WHERE {invoice_scope}i.semester_id=(SELECT id FROM academic_semesters WHERE academic_year='2026' AND semester_number=2)"
    ))
    currency_totals = summarize_financials(invoices)
    db = get_db()
    recent_scope = "WHERE p.receipt_no LIKE 'DEMO-RCP-%'" if demo_mode else ""
    recent = db.execute(f"""
      SELECT p.*, s.first_name, s.last_name, s.student_no
      FROM payments p JOIN students s ON s.id=p.student_id
      {recent_scope}
      ORDER BY p.paid_on DESC,p.id DESC LIMIT 5
    """).fetchall()
    all_due = sorted([row for row in invoices if row["balance"] > 0], key=lambda row: row["balance"], reverse=True)
    faculty_rows = []
    faculty_keys = dict.fromkeys((row["faculty_name"], row["currency"]) for row in invoices)
    for faculty_name, currency in faculty_keys:
        group = [row for row in invoices if row["faculty_name"] == faculty_name and row["currency"] == currency]
        billed = sum(row["billed"] for row in group)
        paid = sum(row["paid"] for row in group)
        faculty_rows.append({"name": faculty_name, "students": len({row["student_id"] for row in group}), "billed": billed,
                             "paid": paid, "balance": sum(row["balance"] for row in group),
                             "rate": round(paid / billed * 100) if billed else 0,
                             "currency": currency})
    return render_template("dashboard.html", invoices=invoices, recent=recent, due=all_due[:4],
                           due_count=len(all_due), faculties=faculty_rows,
                           currency_totals=currency_totals)


@app.route("/students")
@roles_required("system_admin", "student_records", "auditor", "demo")
def students():
    q = request.args.get("q", "").strip()
    sql = """
      SELECT s.*, p.name AS programme_name, f.name AS faculty_name,
        (SELECT sp.display_name FROM student_sponsors ss JOIN sponsors sp ON sp.id=ss.sponsor_id WHERE ss.student_id=s.id LIMIT 1) AS sponsor_name
      FROM students s JOIN programmes p ON p.id=s.programme_id JOIN faculties f ON f.id=p.faculty_id
    """
    filters = []
    params = ()
    if current_employee().get("role") == "demo":
        filters.append("left(s.student_no, 7) = 'DEMO26-'")
    if q:
        filters.append("(s.student_no ILIKE %s OR s.first_name ILIKE %s OR s.last_name ILIKE %s OR p.name ILIKE %s OR f.name ILIKE %s)")
        params = (f"%{q}%",) * 5
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    rows = get_db().execute(sql + " ORDER BY s.last_name,s.first_name", params).fetchall()
    invoice_scope = "left(s.student_no, 7) = 'DEMO26-' AND " if current_employee().get("role") == "demo" else ""
    account_invoices = decorate_invoices(invoice_rows(
        f"WHERE {invoice_scope}i.semester_id=(SELECT id FROM academic_semesters WHERE academic_year='2026' AND semester_number=2)"
    ))
    balance_parts = {}
    account_totals = {}
    for row in account_invoices:
        balance_parts.setdefault(row["student_no"], []).append(money(row["balance"], row["currency"]))
        totals = account_totals.setdefault(row["student_no"], {"paid": 0, "balance": 0})
        totals["paid"] += row["paid"]
        totals["balance"] += row["balance"]
    account_states = {
        student_no: (
            "Paid" if totals["balance"] <= 0
            else "Partial" if totals["paid"] > 0
            else "Unpaid"
        )
        for student_no, totals in account_totals.items()
    }
    balances = {student_no: " · ".join(parts) for student_no, parts in balance_parts.items()}
    return render_template("students.html", students=rows, balances=balances, account_states=account_states, q=q)


@app.route("/invoices")
@roles_required("system_admin", "finance", "auditor", "demo")
def invoices_page():
    q = request.args.get("q", "").strip()
    demo_mode = current_employee().get("role") == "demo"
    where, params = ("WHERE left(s.student_no, 7) = 'DEMO26-'" if demo_mode else ""), ()
    if q:
        search_clause = "(s.student_no ILIKE %s OR s.first_name ILIKE %s OR s.last_name ILIKE %s)"
        where = (where + " AND " if where else "WHERE ") + search_clause
        params = (f"%{q}%",) * 3
    invoices = decorate_invoices(invoice_rows(where, params))
    outstanding_by_currency = {}
    for row in invoices:
        outstanding_by_currency[row["currency"]] = (
            outstanding_by_currency.get(row["currency"], 0) + row["balance"]
        )
    return render_template("invoices.html", invoices=invoices, q=q,
                           outstanding_by_currency=outstanding_by_currency)


@app.route("/payments", methods=["GET", "POST"])
@roles_required("system_admin", "finance", "demo")
def payments():
    if request.method == "POST" and current_employee().get("role") == "demo":
        abort(403)
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
        try:
            # Lock every candidate invoice in a stable order, then recalculate balances.
            db.execute(
                """SELECT id FROM invoices
                   WHERE student_id=%s AND status!='Void'
                     AND id IN (SELECT invoice_id FROM invoice_lines WHERE currency=%s)
                   ORDER BY due_on,id FOR UPDATE""",
                (student_id, currency),
            ).fetchall()
            current = decorate_invoices(invoice_rows(
                "WHERE i.student_id=%s AND i.status!='Void'", (student_id,)
            ))
            eligible = [row for row in current if row["currency"] == currency and row["balance"] > 0]
            if not eligible:
                db.rollback()
                flash("This student has no outstanding invoice in that currency.", "error")
                return redirect(url_for("payments", student_id=student_id))
            try:
                allocations = allocate_payment(cents, eligible)
            except ValueError:
                db.rollback()
                flash("Payment exceeds the student's total outstanding balance in this currency.", "error")
                return redirect(url_for("payments", student_id=student_id))
            receipt_no = f"SA-RCP-SAMPLE-{datetime.now().strftime('%y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
            actor = current_employee()
            recorded_by = actor.get("full_name") or actor["email"]
            cur = db.execute("INSERT INTO payments(receipt_no,student_id,paid_on,amount_cents,currency,method,reference,recorded_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                             (receipt_no, student_id, paid_on, cents, currency, method, reference, recorded_by))
            payment_id = cur.fetchone()["id"]
            for invoice_id, allocated_cents in allocations:
                db.execute(
                    "INSERT INTO payment_allocations(payment_id,invoice_id,amount_cents) VALUES(%s,%s,%s)",
                    (payment_id, invoice_id, allocated_cents),
                )
                invoice_row = next(row for row in eligible if row["id"] == invoice_id)
                db.execute(
                    """UPDATE invoices AS inv
                       SET status=CASE WHEN EXISTS (
                         SELECT 1
                         FROM invoice_lines il
                         WHERE il.invoice_id=inv.id
                         GROUP BY il.currency
                         HAVING SUM(il.amount_cents) > COALESCE((
                           SELECT SUM(pa.amount_cents)
                           FROM payment_allocations pa
                           JOIN payments pay ON pay.id=pa.payment_id
                           WHERE pa.invoice_id=inv.id AND pay.currency=il.currency
                         ),0)
                       ) THEN 'Open' ELSE 'Paid' END
                       WHERE inv.id=%s""",
                    (invoice_id,),
                )
            db.execute(
                "INSERT INTO audit_logs(actor_user_id,action,entity_type,entity_id,details) VALUES(%s,%s,%s,%s,%s::jsonb)",
                (actor["user_id"], "payment.recorded", "payment", str(payment_id),
                 json.dumps({"receipt_no": receipt_no, "student_id": student_id,
                             "amount_cents": cents, "currency": currency,
                             "invoice_ids": [invoice_id for invoice_id, _ in allocations]})),
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
        il.currency,
        SUM(il.amount_cents)-COALESCE((
          SELECT SUM(pa.amount_cents)
          FROM invoices pi
          JOIN payment_allocations pa ON pa.invoice_id=pi.id
          JOIN payments pay ON pay.id=pa.payment_id AND pay.currency=il.currency
          WHERE pi.student_id=s.id AND pi.status!='Void'
            AND EXISTS (
              SELECT 1 FROM invoice_lines pil
              WHERE pil.invoice_id=pi.id AND pil.currency=il.currency
            )
        ),0) AS balance
      FROM students s
      JOIN programmes p ON p.id=s.programme_id
      JOIN invoices i ON i.student_id=s.id AND i.status!='Void'
      JOIN invoice_lines il ON il.invoice_id=i.id
      WHERE s.status!='Deferred' AND (%s = false OR s.student_no LIKE %s)
      GROUP BY s.id,s.student_no,s.first_name,s.last_name,p.name,il.currency
      HAVING SUM(il.amount_cents)-COALESCE((
          SELECT SUM(pa.amount_cents)
          FROM invoices pi
          JOIN payment_allocations pa ON pa.invoice_id=pi.id
          JOIN payments pay ON pay.id=pa.payment_id AND pay.currency=il.currency
          WHERE pi.student_id=s.id AND pi.status!='Void'
            AND EXISTS (
              SELECT 1 FROM invoice_lines pil
              WHERE pil.invoice_id=pi.id AND pil.currency=il.currency
            )
        ),0) > 0
      ORDER BY s.last_name,s.first_name,il.currency
    """, (current_employee().get("role") == "demo",
           "DEMO26-%" if current_employee().get("role") == "demo" else "%")).fetchall()
    recent = db.execute("""
      SELECT p.*,s.first_name,s.last_name,s.student_no
      FROM payments p JOIN students s ON s.id=p.student_id
      WHERE (%s = false OR p.receipt_no LIKE %s)
      ORDER BY p.paid_on DESC,p.id DESC
    """, (current_employee().get("role") == "demo",
          "DEMO-RCP-%" if current_employee().get("role") == "demo" else "%")).fetchall()
    selected = request.args.get("receipt")
    receipt = next((row for row in recent if row["receipt_no"] == selected), None)
    selected_student_id = request.args.get("student_id", type=int)
    selected_currency = next((row["currency"] for row in rows if row["id"] == selected_student_id), "USD")
    return render_template("payments.html", students=rows, payments=recent, receipt=receipt,
                           today=date.today().isoformat(), selected_student_id=selected_student_id,
                           selected_currency=selected_currency)


@app.route("/reports")
@roles_required("system_admin", "finance", "auditor", "demo")
def reports():
    demo_scope = "WHERE left(s.student_no, 7) = 'DEMO26-'" if current_employee().get("role") == "demo" else ""
    rows = decorate_invoices(invoice_rows(demo_scope))
    totals = {}
    for row in rows:
        item = totals.setdefault(row["currency"], {"billed": 0, "paid": 0, "balance": 0})
        item["billed"] += row["billed"]
        item["paid"] += row["paid"]
        item["balance"] += row["balance"]
    faculty_rows = []
    faculty_filter = "WHERE name LIKE '%(Demo)'" if current_employee().get("role") == "demo" else ""
    for faculty in get_db().execute(f"SELECT id,name FROM faculties {faculty_filter} ORDER BY name"):
        group = [row for row in rows if row["faculty_name"] == faculty["name"]]
        faculty_rows.append({"name": faculty["name"], "students": len(group),
                             "billed": sum(row["billed"] for row in group),
                             "paid": sum(row["paid"] for row in group),
                             "balance": sum(row["balance"] for row in group)})
    return render_template("reports.html", totals=totals, faculties=faculty_rows, invoices=rows)


@app.route("/receipt/<receipt_no>")
@roles_required("system_admin", "finance", "auditor", "demo")
def receipt_page(receipt_no):
    row = get_db().execute("""
      SELECT p.*,s.first_name,s.last_name,s.student_no,pr.name AS programme_name,f.name AS faculty_name
      FROM payments p JOIN students s ON s.id=p.student_id
      JOIN programmes pr ON pr.id=s.programme_id JOIN faculties f ON f.id=pr.faculty_id
      WHERE p.receipt_no=%s
        AND (%s = false OR p.receipt_no LIKE %s)
    """, (receipt_no, current_employee().get("role") == "demo",
          "DEMO-RCP-%" if current_employee().get("role") == "demo" else "%")).fetchone()
    if row is None:
        abort(404)
    return render_template("receipt.html", receipt=row)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
