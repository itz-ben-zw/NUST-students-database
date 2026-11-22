"""Safely rebuild only the explicitly tagged fictional demo dataset."""
from __future__ import annotations

import os
import subprocess
import sys

import psycopg


def main() -> int:
    if os.getenv("RESET_DEMO_DATA") != "true" or os.getenv("ALLOW_DEMO_SEED") != "true":
        print("Refusing reset: both RESET_DEMO_DATA=true and ALLOW_DEMO_SEED=true are required.", file=sys.stderr)
        return 2

    database_url = os.getenv("DEMO_DATABASE_URL", "")
    if not database_url or "sslmode=" not in database_url:
        print("DEMO_DATABASE_URL with sslmode=require (or stronger) is required.", file=sys.stderr)
        return 2

    # Every deletion is constrained to the seed script's explicit DEMO prefixes/names.
    # Foreign-key restrictions intentionally abort the transaction if non-demo data
    # has been attached to any demo record.
    with psycopg.connect(database_url, prepare_threshold=None, connect_timeout=10) as db:
        with db.cursor() as cur:
            cur.execute("DELETE FROM payments WHERE receipt_no LIKE 'DEMO-RCP-%'")
            cur.execute("DELETE FROM invoices WHERE invoice_no LIKE 'DEMO-INV-%'")
            cur.execute("""
                DELETE FROM student_sponsors ss USING students s
                WHERE ss.student_id=s.id AND s.student_no LIKE 'DEMO26-%'
            """)
            cur.execute("DELETE FROM students WHERE student_no LIKE 'DEMO26-%' OR student_no ~ '^N0(20[0-9]{4}Y|21[0-9]{4}M|25[0-9]{4}T|26[0-9]{4}Z)
            cur.execute("""
                DELETE FROM semester_fees sf USING faculties f
                WHERE sf.faculty_id=f.id AND f.name LIKE '%(Demo)'
            """)
            cur.execute("DELETE FROM programmes WHERE name LIKE '%(Demo)'")
            cur.execute("DELETE FROM faculties WHERE name LIKE '%(Demo)'")
            cur.execute("DELETE FROM sponsors WHERE display_name LIKE '%(Demo)'")
            cur.execute("DELETE FROM fee_types WHERE name LIKE '%(Demo)'")
        db.commit()

    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["ALLOW_DEMO_SEED"] = "true"
    subprocess.run([sys.executable, "scripts/seed_demo_data.py"], check=True, env=env)
    print("Fictional demo data reset and reseeded successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
")
            cur.execute("""
                DELETE FROM semester_fees sf USING faculties f
                WHERE sf.faculty_id=f.id AND f.name LIKE '%(Demo)'
            """)
            cur.execute("DELETE FROM programmes WHERE name LIKE '%(Demo)'")
            cur.execute("DELETE FROM faculties WHERE name LIKE '%(Demo)'")
            cur.execute("DELETE FROM sponsors WHERE display_name LIKE '%(Demo)'")
            cur.execute("DELETE FROM fee_types WHERE name LIKE '%(Demo)'")
        db.commit()

    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["ALLOW_DEMO_SEED"] = "true"
    subprocess.run([sys.executable, "scripts/seed_demo_data.py"], check=True, env=env)
    print("Fictional demo data reset and reseeded successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
