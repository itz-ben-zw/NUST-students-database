# NUST Student Accounts Demo by Group 5 Informatic

An academic database project: a Flask app with Supabase employee identity and a student accounts demonstration for exploring student records, programmes, semester invoices, payments, balances, and printable receipts. It is designed to be easy to present and demonstrates a practical university accounts workflow in Zimbabwe.

> This is an independent academic demo. It is not built, approved, or operated by the National University of Science and Technology (NUST). All people, student numbers, invoices, payment references, dates, and fee amounts are fictional. The fee schedule is not NUST's official schedule. Do not use it for real student or payment data.

## What it demonstrates

- Browse and search students by student number, name, programme, or faculty.
- View semester invoices and fee line totals.
- Record USD or ZWG demo payments using EcoCash, bank transfer, or RTGS labels.
- Allocate a payment oldest-due-first across the student's open invoices in the same currency.
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

## Public preview and fictional demo data

Open the site homepage (or `/preview`) to view a public, read-only presentation page that works without an employee account or database connection. It contains static fictional examples only. The employee application remains protected by Supabase Auth and role checks.

To populate a dedicated demo database with relational sample data, run this from the project root:

```bash
ALLOW_DEMO_SEED=true DATABASE_URL="postgresql://...?...sslmode=require" python scripts/seed_demo_data.py
```

The seeder is opt-in, additive, and idempotent. It creates 12 fictional students, 12 invoices, and 4 sample receipts using `DEMO`-prefixed identifiers. It does not delete records or overwrite existing rows. Run it only against a database reserved for this academic demo, and remove `ALLOW_DEMO_SEED` immediately after use. Never run it against a real university or production student database.

## Render deployment

For a single Render Web Service linked to this repository:

- Runtime: Python 3
- Python version: 3.12
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`
- Recommended region: Frankfurt, close to the existing Supabase project region (`eu-central-1`)

Set these environment variables in Render's private Environment settings:

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Strong, unique random Flask session secret |
| `FLASK_ENV` | Set to `production` |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase publishable/anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only Supabase service role key |
| `DATABASE_URL` | Supabase PostgreSQL connection string with `sslmode=require` or stronger |

Never place the service-role key or database connection string in browser code, GitHub, or chat. The public `/preview` page is viewable before database credentials are configured; employee sign-in and database-backed pages require all private variables and an authorised employee profile.

## AI Assistant v1 (in development)

The AI Assistant uses the Google Gemini API through the official `google-genai`
Python SDK. It is a read-only feature: Gemini may request only server-defined,
parameterized SELECT tools. The application does not accept SQL from the model,
does not expose database credentials to the browser, and runs each assistant
request in a read-only PostgreSQL transaction.

Configure `GEMINI_API_KEY` as a private server environment variable. Optionally
set `GEMINI_MODEL`; the default is `gemini-2.5-flash`. Never commit the key or
place it in frontend JavaScript.

Current employee access follows the existing employee role model. Finance
summaries are limited to finance-authorized roles; student searches are limited
to student-records-authorized roles. Demo access remains scoped to DEMO-prefixed
student numbers.

**Student self-service is not enabled yet.** The current application has no
student sign-in or verified link between a Supabase Auth user and a student
record. A migration is included as identity-linking groundwork, but it must be
reviewed and applied only with an approved student identity onboarding process.
Do not infer identity from a typed student number or an email address supplied
in chat. Until that workflow is implemented, student access to the AI assistant
must remain disabled.

The project contains fictional academic demonstration records and is not an
official NUST system. Do not enter real student, identity, or payment data.
