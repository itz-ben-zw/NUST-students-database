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
