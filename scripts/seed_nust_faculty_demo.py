"""Additive seed for the expanded fictional NUST faculty/student demo dataset."""
from __future__ import annotations
import os
import sys
import psycopg
from psycopg.rows import dict_row

FACULTIES = {
    "Faculty of Agricultural Science & Technology": ["BSc Agricultural Technology", "BSc Agribusiness Management"],
    "Faculty of Applied Science": ["BSc Applied Mathematics", "BSc Computer Science"],
    "Faculty of The Built Environment": ["BSc Architecture", "BSc Quantity Surveying"],
    "Faculty of Business & Economic Sciences": ["BCom Accounting Sciences", "BSc Actuarial Science"],
    "Faculty of Comm & Information Science": ["BSc Journalism and Media Studies", "BSc Library and Information Science"],
    "Faculty of Engineering": ["BEng Civil and Water Engineering", "BEng Electronic Engineering"],
    "Faculty of Environmental Science": ["BSc Environmental Science", "BSc Geospatial Science"],
    "Faculty of Medicine": ["Bachelor of Medicine and Bachelor of Surgery", "BSc Nursing Science"],
    "Faculty of Science & Technology Education": ["BEd Science Education", "BEd Technology Education"],
}
FIRST = ["Tariro","Tawanda","Nyasha","Kudzai","Rudo","Tinashe","Rutendo","Blessing","Farai","Anesu","Tapiwa","Chipo","Luyanda","Sibusiso","Thandeka","Munashe","Tanaka","Nokuthula","Simbarashe","Vimbai","Mthokozisi","Precious","Lerato","Tatenda","Nothando","Kundai","Bongani","Tsitsi","Makanaka","Lwazi","Nqobile","Shingirai","Zanele","Melusi","Rumbidzai","Sihle","Thabani","Fadzai","Nkosana","Yolanda","Lindani","Chiedza","Mandla","Sibongile","Tendai","Nomsa","Panashe","Buhle","Nqobizitha","Sithandazile","Vusumuzi","Ruvimbo","Lethukuthula","Anotida","Mthandazo","Nyarai","Tafadzwa","Nobuhle","Khethiwe","Takudzwa","Zibusiso","Lungile","Tariro","Nobuhle","Sihle","Rumbidzai","Tinashe","Nokuthula","Kudzai","Vimbai","Mandla","Chipo"]
LAST = ["Moyo","Dube","Ndlovu","Sibanda","Mupfumi","Ncube","Mpofu","Mhlanga","Moyo","Dube","Ndlovu","Sibanda","Moyo","Nkomo","Dube","Moyo","Ncube","Mpofu","Sibanda","Dube","Ndlovu","Moyo","Ncube","Dube","Mhlanga","Ndlovu","Mpofu","Sibanda","Moyo","Dube","Ncube","Ndlovu","Moyo","Sibanda","Dube","Ncube","Mhlanga","Moyo","Ndlovu","Mpofu","Dube","Ncube","Sibanda","Moyo","Ndlovu","Dube","Mpofu","Mhlanga","Sibanda","Moyo","Dube","Ncube","Ndlovu","Moyo","Sibanda","Dube","Ncube","Mpofu","Mhlanga","Ndlovu","Moyo","Dube","Sibanda","Ncube","Moyo","Ndlovu","Dube","Mpofu","Sibanda","Mhlanga","Ncube"]
COHORTS = [("N020", "Y"), ("N021", "M"), ("N025", "T"), ("N026", "Z")]
SPONSORS = ["Family support (Demo)", "Self-funded (Demo)", "Merit scholarship (Demo)"]

def main() -> int:
    if os.getenv("ALLOW_DEMO_SEED") != "true":
        print("Refusing to seed: set ALLOW_DEMO_SEED=true for a demo database.", file=sys.stderr)
        return 2
    url = os.getenv("DATABASE_URL", "")
    if not url or "sslmode=" not in url:
        print("DATABASE_URL with sslmode=require (or stronger) is required.", file=sys.stderr)
        return 2
    with psycopg.connect(url, row_factory=dict_row, prepare_threshold=None, connect_timeout=10) as db:
        with db.cursor() as cur:
            faculty_ids = {}
            programme_ids = {}
            for faculty, programmes in FACULTIES.items():
                cur.execute("INSERT INTO faculties(name) VALUES(%s) ON CONFLICT(name) DO NOTHING", (faculty,))
                cur.execute("SELECT id FROM faculties WHERE name=%s", (faculty,))
                faculty_ids[faculty] = cur.fetchone()["id"]
                for programme in programmes:
                    name = programme + " (Demo)"
                    cur.execute("INSERT INTO programmes(name,faculty_id,award_level) VALUES(%s,%s,'Undergraduate') ON CONFLICT(name) DO NOTHING", (name, faculty_ids[faculty]))
                    cur.execute("SELECT id FROM programmes WHERE name=%s", (name,))
                    programme_ids[(faculty, name)] = cur.fetchone()["id"]
            sponsor_ids = {}
            for sponsor, kind in zip(SPONSORS, ["Family", "Self-funded", "Scholarship"]):
                cur.execute("INSERT INTO sponsors(display_name,sponsor_type) SELECT %s,%s WHERE NOT EXISTS(SELECT 1 FROM sponsors WHERE display_name=%s)", (sponsor, kind, sponsor))
                cur.execute("SELECT id FROM sponsors WHERE display_name=%s ORDER BY id LIMIT 1", (sponsor,))
                sponsor_ids[sponsor] = cur.fetchone()["id"]
            cur.execute("SELECT id FROM academic_semesters WHERE academic_year='2026' AND semester_number=2")
            semester = cur.fetchone()
            if not semester:
                raise RuntimeError("The 2026 semester 2 record is required before seeding.")
            cur.execute("SELECT id,name FROM fee_types WHERE name IN ('Tuition (Demo)','Registration (Demo)','Technology levy (Demo)')")
            fee_ids = {row["name"]: row["id"] for row in cur.fetchall()}
            if len(fee_ids) != 3:
                raise RuntimeError("Run scripts/seed_demo_data.py first to create demo fee types.")
            for faculty, fid in faculty_ids.items():
                for fee_name, amount in [("Tuition (Demo)", 100000 + (fid % 5)*5000), ("Registration (Demo)", 8000), ("Technology levy (Demo)", 5000)]:
                    cur.execute("""INSERT INTO semester_fees(semester_id,faculty_id,fee_type_id,amount_cents,currency)
                        VALUES(%s,%s,%s,%s,'USD') ON CONFLICT(semester_id,faculty_id,fee_type_id) DO NOTHING""",
                        (semester["id"], fid, fee_ids[fee_name], amount))
            inserted = 0
            for i in range(72):
                faculty = list(FACULTIES)[i // 8]
                programme = FACULTIES[faculty][i % 2] + " (Demo)"
                cohort, suffix = COHORTS[i // 18]
                student_no = f"{cohort}{i % 18 + 1:04d}{suffix}"
                sponsor = SPONSORS[i % 3]
                status = "On attachment" if i % 13 == 0 else "Registered"
                cur.execute("""INSERT INTO students(student_no,first_name,last_name,programme_id,status)
                    VALUES(%s,%s,%s,%s,%s) ON CONFLICT(student_no) DO NOTHING RETURNING id""",
                    (student_no, FIRST[i], LAST[i], programme_ids[(faculty, programme)], status))
                row = cur.fetchone()
                cur.execute("SELECT id FROM students WHERE student_no=%s", (student_no,))
                student_id = cur.fetchone()["id"]
                cur.execute("""INSERT INTO student_sponsors(student_id,sponsor_id,relationship)
                    VALUES(%s,%s,'Demo sponsor') ON CONFLICT(student_id,sponsor_id) DO NOTHING""",
                    (student_id, sponsor_ids[sponsor]))
                invoice_no = f"DEMO-INV-2026-{i+13:04d}"
                cur.execute("""INSERT INTO invoices(invoice_no,student_id,semester_id,issued_on,due_on,status)
                    VALUES(%s,%s,%s,'2026-08-01','2026-09-15','Open') ON CONFLICT(invoice_no) DO NOTHING""",
                    (invoice_no, student_id, semester["id"]))
                cur.execute("SELECT id FROM invoices WHERE invoice_no=%s", (invoice_no,))
                invoice_id = cur.fetchone()["id"]
                cur.execute("""SELECT ft.id,ft.name,sf.amount_cents FROM semester_fees sf
                    JOIN fee_types ft ON ft.id=sf.fee_type_id
                    WHERE sf.semester_id=%s AND sf.faculty_id=%s""", (semester["id"], faculty_ids[faculty]))
                for fee in cur.fetchall():
                    cur.execute("""INSERT INTO invoice_lines(invoice_id,fee_type_id,description,amount_cents,currency)
                        SELECT %s,%s,%s,%s,'USD' WHERE NOT EXISTS
                        (SELECT 1 FROM invoice_lines WHERE invoice_id=%s AND fee_type_id=%s)""",
                        (invoice_id, fee["id"], fee["name"], fee["amount_cents"], invoice_id, fee["id"]))
                inserted += bool(row)
        db.commit()
    print(f"Expanded NUST demo seed complete: 9 faculties and 72 patterned student records (up to 84 total with original demo students).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
