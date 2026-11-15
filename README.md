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

The academic model has 12 related tables: `faculties`, `programmes`, `sponsors`, `students`, `student_sponsors`, `academic_semesters`, `fee_types`, `semester_fees`, `invoices`, `invoice_lines`, `payments`, and `payment_allocations`. The PostgreSQL schema adds `employee_profiles`, `employee_web_sessions`, and `audit_logs` for employee access and auditing. See [`db/schema.postgres.sql`](db/schema.postgres.sql).

## Safety and scope

- `.env`, local databases, Python environments, and logs are excluded by `.gitignore`.
- The app refuses to start unless a strong `SECRET_KEY` is configured. Set `FLASK_ENV=production` in hosted environments so session cookies use the Secure flag.
- Employee sign-in uses Supabase Auth. There is no public registration route; only invited users with an active employee_profiles record and an assigned role can access protected pages.
- The Flask server verifies Supabase JWT signatures and reads employee roles server-side using the service-role key. Never expose SUPABASE_SERVICE_ROLE_KEY to a browser or commit it.
- Set SECRET_KEY, SUPABASE_URL, SUPABASE_ANON_KEY, and SUPABASE_SERVICE_ROLE_KEY as server environment variables before enabling employee sign-in.
- The Flask business-data routes connect to Supabase PostgreSQL through DATABASE_URL. The PostgreSQL schema has been created and is protected by RLS; the server uses a database connection string that must remain private. Do not deploy this as a live university system or enter real records until the remaining security, audit and operational controls are reviewed.
- No real payment integration or exchange-rate conversion is provided. Keep all records fictional.

## Presentation notes

See [`PRESENTATION.md`](PRESENTATION.md) for a short walkthrough and [`DESIGN.md`](DESIGN.md) for the screen and database rationale.


## Employee access bootstrap

The first system administrator must be provisioned manually by an authorised project owner:

1. In the Supabase Dashboard for the DBS project, disable public user sign-ups in the Auth settings. Keep invitations enabled.
2. Verify the first administrator's employment and authority through an independent university channel.
3. Use Supabase Auth's dashboard invitation flow to invite that exact work email.
4. After the Auth user exists, run this SQL in the Supabase SQL Editor, replacing the email and name with the verified administrator's details:

```sql
insert into public.employee_profiles (user_id, email, full_name, role, is_active)
select id, email, 'Verified System Administrator', 'system_admin', true
from auth.users
where lower(email) = lower('verified.admin@nust.ac.zw')
on conflict (user_id) do update
set role = excluded.role,
    is_active = true,
    email = excluded.email,
    full_name = excluded.full_name;
```

5. Set `SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY` in the hosting provider's secret environment settings. The service-role key is server-only.
6. The administrator can then sign in and use the Employee access page to invite individually verified staff.

The application checks the employee profile on each protected request. Setting `is_active = false` blocks further application access on the next request. This does not replace revoking sessions in Supabase Auth when immediate token invalidation is required.

**Important current limitation:** the Flask business routes now use Supabase PostgreSQL and payment writes are transactional with invoice row locking and audit entries. The database is still empty, and no demo seeding script has been run. Real operational use still requires university authorisation, formal data governance, backups, MFA policy, session revocation procedures, testing and review of the finance workflow.
