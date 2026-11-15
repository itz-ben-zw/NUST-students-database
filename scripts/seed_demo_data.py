"""Insert a small, fictional dataset for the NUST Student Accounts demo.

This script is deliberately opt-in and additive. It never deletes or overwrites
existing records. Run only against a demo database.
"""
from __future__ import annotations

import os
import sys
from datetime import date

import psycopg
from psycopg.rows import dict_row


FACULTIES = [
    "Faculty of Computing (Demo)",
    "Faculty of Engineering (Demo)",
    "Faculty of Applied Sciences (Demo)",
]
PROGRAMMES = [
    ("BSc Information Systems (Demo)", "Faculty of Computing (Demo)"),
    ("BSc Software Engineering (Demo)", "Faculty of Computing (Demo)"),
    ("BEng Engineering Systems (Demo)", "Faculty of Engineering (Demo)"),
    ("BSc Applied Mathematics (Demo)", "Faculty of Applied Sciences (Demo)"),
]
SPONSORS = [
    ("Family support (Demo)", "Family"),
    ("Self-funded (Demo)", "Self-funded"),
    ("Merit scholarship (Demo)", "Scholarship"),
]
STUDENTS = [
    ("DEMO26-0001", "Tariro", "Moyo", "BSc Information Systems (Demo)", "Family support (Demo)"),
    ("DEMO26-0002", "Tawanda", "Dube", "BSc Software Engineering (Demo)", "Self-funded (Demo)"),
    ("DEMO26-0003", "Nyasha", "Ndlovu", "BEng Engineering Systems (Demo)", "Merit scholarship (Demo)"),
    ("DEMO26-0004", "Kudzai", "Sibanda", "BSc Applied Mathematics (Demo)", "Family support (Demo)"),
    ("DEMO26-0005", "Rudo", "Mupfumi", "BSc Information Systems (Demo)", "Self-funded (Demo)"),
    ("DEMO26-0006", "Tinashe", "Moyo", "BSc Software Engineering (Demo)", "Family support (Demo)"),
    ("DEMO26-0007", "Rutendo", "Ncube", "BEng Engineering Systems (Demo)", "Merit scholarship (Demo)"),
    ("DEMO26-0008", "Blessing", "Dube", "BSc Applied Mathematics (Demo)", "Self-funded (Demo)"),
    ("DEMO26-0009", "Farai", "Moyo", "BSc Information Systems (Demo)", "Family support (Demo)"),
    ("DEMO26-0010", "Anesu", "Ndlovu", "BSc Software Engineering (Demo)", "Merit scholarship (Demo)"),
    ("DEMO26-0011", "Tapiwa", "Sibanda", "BEng Engineering Systems (Demo)", "Self-funded (Demo)"),
    ("DEMO26-0012", "Chipo", "Ncube", "BSc Applied Mathematics (Demo)", "Family support (Demo)"),
]
FEE_TYPES = [
    ("Tuition (Demo)", "Fictional semester tuition charge"),
    ("Registration (Demo)", "Fictional registration charge"),
    ("Technology levy (Demo)", "Fictional technology charge"),
]
FEES_BY_FACULTY = {
    "Faculty of Computing (Demo)": (95000, 8000, 5000),
    "Faculty of Engineering (Demo)": (112000, 8000, 5000),
    "Faculty of Applied Sciences (Demo)": (88000, 8000, 5000),
}


def main() -> int:
    if os.getenv("ALLOW_DEMO_SEED") != "true":
        print("Refusing to seed: set ALLOW_DEMO_SEED=true explicitly for a demo database.", file=sys.stderr)
        return 2
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url or "sslmode=" not in database_url:
        print("DATABASE_URL with sslmode=require (or stronger) is required.", file=sys.stderr)
        return 2

    with psycopg.connect(database_url, row_factory=dict_row, prepare_threshold=None, connect_timeout=10) as db:
        with db.cursor() as cur:
            for name in FACULTIES:
                cur.execute("INSERT INTO faculties(name) VALUES(%s) ON CONFLICT(name) DO NOTHING", (name,))
            faculty_ids = {}
            for name in FACULTIES:
                cur.execute("SELECT id FROM faculties WHERE name=%s", (name,))
                faculty_ids[name] = cur.fetchone()["id"]

            for name, faculty in PROGRAMMES:
                cur.execute(
                    "INSERT INTO programmes(name,faculty_id,award_level) VALUES(%s,%s,'Undergraduate') ON CONFLICT(name) DO NOTHING",
                    (name, faculty_ids[faculty]),
                )
            programme_ids = {}
            programme_faculties = {}
            for name, faculty in PROGRAMMES:
                cur.execute("SELECT id FROM programmes WHERE name=%s", (name,))
                programme_ids[name] = cur.fetchone()["id"]
                programme_faculties[name] = faculty

            for name, sponsor_type in SPONSORS:
                cur.execute(
                    "INSERT INTO sponsors(display_name,sponsor_type) SELECT %s,%s WHERE NOT EXISTS (SELECT 1 FROM sponsors WHERE display_name=%s)",
                    (name, sponsor_type, name),
                )
            sponsor_ids = {}
            for name, _ in SPONSORS:
                cur.execute("SELECT id FROM sponsors WHERE display_name=%s ORDER BY id LIMIT 1", (name,))
                sponsor_ids[name] = cur.fetchone()["id"]

            cur.execute(
                """INSERT INTO academic_semesters(academic_year,semester_number,starts_on,ends_on)
                   VALUES('2026',2,'2026-08-01','2026-12-15')
                   ON CONFLICT(academic_year,semester_number) DO NOTHING"""
            )
            cur.execute("SELECT id FROM academic_semesters WHERE academic_year='2026' AND semester_number=2")
            semester_id = cur.fetchone()["id"]

            fee_type_ids = {}
            for name, description in FEE_TYPES:
                cur.execute(
                    "INSERT INTO fee_types(name,description) VALUES(%s,%s) ON CONFLICT(name) DO NOTHING",
                    (name, description),
                )
                cur.execute("SELECT id FROM fee_types WHERE name=%s", (name,))
                fee_type_ids[name] = cur.fetchone()["id"]

            for faculty, amounts in FEES_BY_FACULTY.items():
                for (fee_name, _), amount in zip(FEE_TYPES, amounts):
                    cur.execute(
                        """INSERT INTO semester_fees(semester_id,faculty_id,fee_type_id,amount_cents,currency)
                           VALUES(%s,%s,%s,%s,'USD')
                           ON CONFLICT(semester_id,faculty_id,fee_type_id) DO NOTHING""",
                        (semester_id, faculty_ids[faculty], fee_type_ids[fee_name], amount),
                    )

            invoice_ids = {}
            for index, (student_no, first, last, programme, sponsor) in enumerate(STUDENTS, start=1):
                cur.execute(
                    """INSERT INTO students(student_no,first_name,last_name,programme_id,status)
                       VALUES(%s,%s,%s,%s,%s) ON CONFLICT(student_no) DO NOTHING""",
                    (student_no, first, last, programme_ids[programme],
                     "On attachment" if index in (6, 10) else "Registered"),
                )
                cur.execute("SELECT id FROM students WHERE student_no=%s", (student_no,))
                student_id = cur.fetchone()["id"]
                cur.execute(
                    """INSERT INTO student_sponsors(student_id,sponsor_id,relationship)
                       VALUES(%s,%s,'Demo sponsor') ON CONFLICT(student_id,sponsor_id) DO NOTHING""",
                    (student_id, sponsor_ids[sponsor]),
                )
                invoice_no = f"DEMO-INV-2026-{index:04d}"
                cur.execute(
                    """INSERT INTO invoices(invoice_no,student_id,semester_id,issued_on,due_on,status)
                       VALUES(%s,%s,%s,'2026-08-01','2026-09-15','Open')
                       ON CONFLICT(invoice_no) DO NOTHING""",
                    (invoice_no, student_id, semester_id),
                )
                cur.execute("SELECT id FROM invoices WHERE invoice_no=%s", (invoice_no,))
                invoice_id = cur.fetchone()["id"]
                invoice_ids[index] = (invoice_id, student_id)
                faculty = programme_faculties[programme]
                for (fee_name, _), amount in zip(FEE_TYPES, FEES_BY_FACULTY[faculty]):
                    cur.execute(
                        """INSERT INTO invoice_lines(invoice_id,fee_type_id,description,amount_cents,currency)
                           SELECT %s,%s,%s,%s,'USD'
                           WHERE NOT EXISTS (SELECT 1 FROM invoice_lines WHERE invoice_id=%s AND fee_type_id=%s)""",
                        (invoice_id, fee_type_ids[fee_name], fee_name, amount, invoice_id, fee_type_ids[fee_name]),
                    )

            # A few illustrative receipts: partial, full, and mixed payment methods.
            demo_payments = [
                (1, "DEMO-RCP-2026-0001", date(2026, 10, 15), 25000, "EcoCash"),
                (2, "DEMO-RCP-2026-0002", date(2026, 10, 22), 108000, "Bank transfer"),
                (3, "DEMO-RCP-2026-0003", date(2026, 11, 2), 40000, "RTGS"),
                (5, "DEMO-RCP-2026-0004", date(2026, 11, 8), 20000, "EcoCash"),
            ]
            for index, receipt_no, paid_on, amount, method in demo_payments:
                invoice_id, student_id = invoice_ids[index]
                cur.execute(
                    """INSERT INTO payments(receipt_no,student_id,paid_on,amount_cents,currency,method,reference,recorded_by)
                       VALUES(%s,%s,%s,%s,'USD',%s,%s,'Demo seed script')
                       ON CONFLICT(receipt_no) DO NOTHING""",
                    (receipt_no, student_id, paid_on, amount, method, f"DEMO-REF-{index:04d}"),
                )
                cur.execute("SELECT id FROM payments WHERE receipt_no=%s", (receipt_no,))
                payment_id = cur.fetchone()["id"]
                cur.execute(
                    """INSERT INTO payment_allocations(payment_id,invoice_id,amount_cents)
                       VALUES(%s,%s,%s) ON CONFLICT(payment_id,invoice_id) DO NOTHING""",
                    (payment_id, invoice_id, amount),
                )
            # Student 2's demo receipt settles their fictional invoice.
            cur.execute(
                """UPDATE invoices SET status='Paid'
                   WHERE invoice_no='DEMO-INV-2026-0002'
                   AND (SELECT COALESCE(SUM(il.amount_cents),0) FROM invoice_lines il WHERE il.invoice_id=invoices.id)
                       <= (SELECT COALESCE(SUM(pa.amount_cents),0) FROM payment_allocations pa WHERE pa.invoice_id=invoices.id)"""
            )
        db.commit()

    print("Demo seed complete: 12 fictional students, 12 invoices and 4 fictional receipts.")
    print("All inserted student numbers and invoice/receipt references use DEMO prefixes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
