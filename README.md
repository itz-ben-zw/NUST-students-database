# NUST Student Accounts Demo by Group 5 Informatic

An academic database project: a Flask app with Supabase employee identity and a student accounts demonstration for exploring student records, programmes, semester invoices, payments, balances, and printable receipts. It is designed to be easy to present and demonstrates a practical university accounts workflow in Zimbabwe.

> This is an independent academic demo. It is not built, approved, or operated by the National University of Science and Technology (NUST). All people, student numbers, invoices, payment references, dates, and fee amounts are fictional. The fee schedule is not NUST's official schedule. Do not use it for real student or payment data.

## What it demonstrates

- Browse and search students by student number, name, programme, or faculty.
- View semester invoices and fee line totals.
- Record USD or ZWG demo payments using EcoCash, bank transfer, or RTGS labels.
- Allocate a payment to the student's oldest open invoice in the same currency.
- Print a receipt and faculty collection report.
- Store financial values as integer cents, with no exchange-rate conversion.

The faculty and programme labels are examples based on publicly listed NUST academic areas. See [NUST Faculties](https://www.nust.ac.zw/index.php/faculties.html) and [Civil and Water Engineering](https://www.nust.ac.zw/engineering/index.php/departments/department-of-civil-and-water-engineering). The app uses no NUST logo or official fee information.

## Data model

The original SQLite prototype has 12 related tables. The Supabase PostgreSQL schema adds employee_profiles and audit_logs for controlled employee access and auditability. The academic tables are `faculties`, `programmes`, `sponsors`, `students`, `student_sponsors`, `academic_semesters`, `fee_types`, `semester_fees`, `invoices`, `invoice_lines`, `payments`, and `payment_allocations`. See [`schema.sql`](schema.sql).

## Safety and scope

- `.env`, local databases, Python environments, and logs are excluded by `.gitignore`.
- The app uses a temporary random session key when `SECRET_KEY` is unset. For a persistent private deployment, set a strong secret in the environment.
- Employee sign-in uses Supabase Auth. There is no public registration route; only invited users with an active employee_profiles record and an assigned role can access protected pages.
- The Flask server verifies Supabase JWT signatures and reads employee roles server-side using the service-role key. Never expose SUPABASE_SERVICE_ROLE_KEY to a browser or commit it.
- Set SECRET_KEY, SUPABASE_URL, SUPABASE_ANON_KEY, and SUPABASE_SERVICE_ROLE_KEY as server environment variables before enabling employee sign-in.
- The current Flask data layer is still the local SQLite prototype. Supabase PostgreSQL schema has been created, but business data routes have not yet been migrated to PostgreSQL. Do not deploy this as a live university system or enter real records.
- No real payment integration or exchange-rate conversion is provided. Keep all records fictional.

## Presentation notes

See [`PRESENTATION.md`](PRESENTATION.md) for a short walkthrough and [`DESIGN.md`](DESIGN.md) for the screen and database rationale.
