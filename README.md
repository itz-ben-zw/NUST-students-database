# NUST Student Accounts Demo by Group 5 Informatic

A one-day academic database project: a small Flask and SQLite app for exploring student records, programmes, semester invoices, payments, balances, and printable receipts. It is designed to be easy to present and demonstrates a practical university accounts workflow in Zimbabwe.

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

The 12 related tables are `faculties`, `programmes`, `sponsors`, `students`, `student_sponsors`, `academic_semesters`, `fee_types`, `semester_fees`, `invoices`, `invoice_lines`, `payments`, and `payment_allocations`. See [`schema.sql`](schema.sql).

## Safety and scope

- `.env`, local databases, Python environments, and logs are excluded by `.gitignore`.
- The app uses a temporary random session key when `SECRET_KEY` is unset. For a persistent private deployment, set a strong secret in the environment.
- This classroom demo has no authentication, real payment integration, exchange-rate conversion, or production safeguards. Keep it on fictional records for presentations.

## Presentation notes

See [`PRESENTATION.md`](PRESENTATION.md) for a short walkthrough and [`DESIGN.md`](DESIGN.md) for the screen and database rationale.
