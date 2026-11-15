from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect

from security import (AuthenticationUnavailable, current_employee, invite_employee,
                      list_employee_profiles, login_required, roles_required, sign_in_with_password)

BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("NUST_FEES_DB", BASE_DIR / "nust_students.db"))
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

@app.context_processor
def inject_employee():
    return {"current_employee": current_employee()}

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
            session["supabase_access_token"] = result["token"]
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
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))

@app.route("/admin/employees", methods=["GET", "POST"])
@roles_required("system_admin")
def employee_admin():
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
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def get_db():
    if "db" not in g:
        g.db = connect_db()
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS faculties (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS programmes (
    id INTEGER PRIMARY KEY,
    faculty_id INTEGER NOT NULL REFERENCES faculties(id),
    name TEXT NOT NULL UNIQUE,
    award_level TEXT NOT NULL DEFAULT 'Undergraduate'
);
CREATE TABLE IF NOT EXISTS sponsors (
    id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    sponsor_type TEXT NOT NULL CHECK(sponsor_type IN ('Family','Self-funded','Scholarship'))
);
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY,
    student_no TEXT NOT NULL UNIQUE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    programme_id INTEGER NOT NULL REFERENCES programmes(id),
    status TEXT NOT NULL DEFAULT 'Registered' CHECK(status IN ('Registered','On attachment','Deferred'))
);
CREATE TABLE IF NOT EXISTS student_sponsors (
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    sponsor_id INTEGER NOT NULL REFERENCES sponsors(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    PRIMARY KEY(student_id, sponsor_id)
);
CREATE TABLE IF NOT EXISTS academic_semesters (
    id INTEGER PRIMARY KEY,
    academic_year TEXT NOT NULL,
    semester_number INTEGER NOT NULL CHECK(semester_number IN (1,2)),
    starts_on TEXT NOT NULL,
    ends_on TEXT NOT NULL,
    UNIQUE(academic_year, semester_number)
);
CREATE TABLE IF NOT EXISTS fee_types (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT
);
CREATE TABLE IF NOT EXISTS semester_fees (
    id INTEGER PRIMARY KEY,
    semester_id INTEGER NOT NULL REFERENCES academic_semesters(id),
    faculty_id INTEGER NOT NULL REFERENCES faculties(id),
    fee_type_id INTEGER NOT NULL REFERENCES fee_types(id),
    amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
    currency TEXT NOT NULL CHECK(currency IN ('USD','ZWG')),
    UNIQUE(semester_id, faculty_id, fee_type_id)
);
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY,
    invoice_no TEXT NOT NULL UNIQUE,
    student_id INTEGER NOT NULL REFERENCES students(id),
    semester_id INTEGER NOT NULL REFERENCES academic_semesters(id),
    issued_on TEXT NOT NULL,
    due_on TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Open' CHECK(status IN ('Open','Paid','Void')),
    UNIQUE(student_id, semester_id)
);
CREATE TABLE IF NOT EXISTS invoice_lines (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    fee_type_id INTEGER NOT NULL REFERENCES fee_types(id),
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
    currency TEXT NOT NULL CHECK(currency IN ('USD','ZWG'))
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY,
    receipt_no TEXT NOT NULL UNIQUE,
    student_id INTEGER NOT NULL REFERENCES students(id),
    paid_on TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    currency TEXT NOT NULL CHECK(currency IN ('USD','ZWG')),
    method TEXT NOT NULL CHECK(method IN ('EcoCash','Bank transfer','RTGS')),
    reference TEXT,
    recorded_by TEXT NOT NULL DEFAULT 'Student accounts demo'
);
CREATE TABLE IF NOT EXISTS payment_allocations (
    payment_id INTEGER NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    PRIMARY KEY(payment_id, invoice_id)
);
"""


def seed_database():
    db = connect_db()
    db.executescript(SCHEMA)
    if db.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
        db.executescript("""
        INSERT INTO faculties(name) VALUES
          ('Faculty of Applied Science'),
          ('Faculty of Engineering'),
          ('Faculty of Business & Economic Sciences');
        INSERT INTO programmes(faculty_id,name,award_level) VALUES
          (1,'Computer Science','Undergraduate'),
          (1,'Applied Biology and Biochemistry','Undergraduate'),
          (2,'Civil and Water Engineering','Undergraduate'),
          (3,'Accounting Sciences','Undergraduate');
        INSERT INTO sponsors(display_name,sponsor_type) VALUES
          ('Family sponsor 01','Family'),('Family sponsor 02','Family'),
          ('Student self-funded 01','Self-funded'),('Demo scholarship 01','Scholarship');
        INSERT INTO students(student_no,first_name,last_name,programme_id,status) VALUES
          ('NUST-DEMO-26041','Kundai','Moyo',1,'Registered'),
          ('NUST-DEMO-26042','Tariro','Chikwanha',4,'Registered'),
          ('NUST-DEMO-26043','Tafadzwa','Dube',3,'On attachment'),
          ('NUST-DEMO-26044','Simbarashe','Ndlovu',2,'Registered'),
          ('NUST-DEMO-26045','Rutendo','Moyo',1,'Registered'),
          ('NUST-DEMO-26046','Chipo','Muchengeti',4,'Registered');
        INSERT INTO student_sponsors VALUES
          (1,1,'Family'),(2,2,'Family'),(3,3,'Self-funded'),
          (4,4,'Scholarship'),(5,1,'Family'),(6,3,'Self-funded');
        INSERT INTO academic_semesters(academic_year,semester_number,starts_on,ends_on) VALUES
          ('2026',1,'2026-02-02','2026-06-26'),('2026',2,'2026-08-03','2026-12-18');
        INSERT INTO fee_types(name,description) VALUES
          ('Tuition','Demonstration tuition charge'),
          ('Student levy','Demonstration student services levy'),
          ('Registration','Demonstration registration charge'),
          ('Industrial attachment','Demonstration attachment administration charge');
        INSERT INTO semester_fees(semester_id,faculty_id,fee_type_id,amount_cents,currency) VALUES
          (2,1,1,42000,'USD'),(2,1,2,5000,'USD'),(2,1,3,3000,'USD'),
          (2,2,1,45000,'USD'),(2,2,2,5000,'USD'),(2,2,3,3000,'USD'),
          (2,3,1,38000,'USD'),(2,3,2,5000,'USD'),(2,3,3,3000,'USD'),
          (2,2,4,2500,'USD');
        INSERT INTO invoices(invoice_no,student_id,semester_id,issued_on,due_on,status) VALUES
          ('NUST-INV-DEMO-041',1,2,'2026-08-03','2026-08-31','Open'),
          ('NUST-INV-DEMO-042',2,2,'2026-08-03','2026-08-31','Open'),
          ('NUST-INV-DEMO-043',3,2,'2026-08-03','2026-08-31','Open'),
          ('NUST-INV-DEMO-044',4,2,'2026-08-03','2026-08-31','Open'),
          ('NUST-INV-DEMO-045',5,2,'2026-08-03','2026-08-31','Open'),
          ('NUST-INV-DEMO-046',6,2,'2026-08-03','2026-08-31','Open');
        INSERT INTO invoice_lines(invoice_id,fee_type_id,description,amount_cents,currency)
          SELECT i.id, sf.fee_type_id, ft.name, sf.amount_cents, sf.currency
          FROM invoices i JOIN students s ON s.id=i.student_id
          JOIN programmes p ON p.id=s.programme_id
          JOIN semester_fees sf ON sf.semester_id=i.semester_id AND sf.faculty_id=p.faculty_id
          JOIN fee_types ft ON ft.id=sf.fee_type_id
          WHERE NOT (p.name='Civil and Water Engineering' AND ft.name='Registration');
        INSERT INTO payments(receipt_no,student_id,paid_on,amount_cents,currency,method,reference) VALUES
          ('NUST-RCP-DEMO-081',1,'2026-09-02',20000,'USD','Bank transfer','DEMO-TRANSFER-01'),
          ('NUST-RCP-DEMO-082',2,'2026-09-04',28000,'USD','EcoCash','DEMO-ECOCASH-01'),
          ('NUST-RCP-DEMO-083',3,'2026-09-07',20000,'USD','RTGS','DEMO-RTGS-01'),
          ('NUST-RCP-DEMO-084',5,'2026-09-10',12000,'USD','Bank transfer','DEMO-TRANSFER-02');
        INSERT INTO payment_allocations(payment_id,invoice_id,amount_cents) VALUES
          (1,1,20000),(2,2,28000),(3,3,20000),(4,5,12000);
        """)
        db.commit()
    db.close()


def money(cents, currency="USD"):
    return f"{currency} {cents / 100:,.2f}"


app.jinja_env.filters["money"] = money


def invoice_rows(where="", params=()):
    return get_db().execute(f"""
      SELECT i.id, i.invoice_no, i.issued_on, i.due_on, i.status,
             s.student_no, s.first_name, s.last_name, s.status AS student_status,
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
@roles_required("system_admin", "finance", "student_records", "auditor")
def dashboard():
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
        sql += " WHERE s.student_no LIKE ? OR s.first_name LIKE ? OR s.last_name LIKE ? OR p.name LIKE ? OR f.name LIKE ?"
        params = (f"%{q}%",) * 5
    rows = get_db().execute(sql + " ORDER BY s.last_name,s.first_name", params).fetchall()
    balances = {row["student_no"]: row["balance"] for row in decorate_invoices(
        invoice_rows("WHERE i.semester_id=(SELECT id FROM academic_semesters WHERE academic_year='2026' AND semester_number=2)"))}
    return render_template("students.html", students=rows, balances=balances, q=q)


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
        current = decorate_invoices(invoice_rows("WHERE i.student_id=? AND i.status!='Void'", (student_id,)))
        invoice = next((row for row in sorted(current, key=lambda item: (item["due_on"], item["id"]))
                        if row["balance"] > 0 and row["currency"] == currency), None)
        if not invoice:
            flash("This student has no outstanding invoice in that currency.", "error")
            return redirect(url_for("payments"))
        if cents > invoice["balance"]:
            flash("Payment is higher than this invoice’s remaining balance.", "error")
            return redirect(url_for("payments"))
        try:
            receipt_no = f"NUST-RCP-DEMO-{datetime.now().strftime('%y%m%d%H%M%S')}"
            cur = db.execute("INSERT INTO payments(receipt_no,student_id,paid_on,amount_cents,currency,method,reference) VALUES(?,?,?,?,?,?,?)",
                             (receipt_no, student_id, paid_on, cents, currency, method, reference))
            db.execute("INSERT INTO payment_allocations(payment_id,invoice_id,amount_cents) VALUES(?,?,?)",
                       (cur.lastrowid, invoice["id"], cents))
            if cents == invoice["balance"]:
                db.execute("UPDATE invoices SET status='Paid' WHERE id=?", (invoice["id"],))
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            flash("Could not save the payment. Please try again.", "error")
            return redirect(url_for("payments"))
        flash(f"Demo payment recorded. Receipt {receipt_no} is ready.", "success")
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
                           today=date.today().isoformat())


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
      WHERE p.receipt_no=?
    """, (receipt_no,)).fetchone()
    if row is None:
        abort(404)
    return render_template("receipt.html", receipt=row)


if __name__ == "__main__":
    seed_database()
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
