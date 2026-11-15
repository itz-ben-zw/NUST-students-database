# Project design

## Problem

University accounts work with linked information: each student belongs to a programme and faculty, receives charges for an academic period, and may make more than one payment. A single spreadsheet can make it hard to follow how a payment changes an invoice balance or which receipt belongs to a student.

## Proposed demo

The app models that workflow with a relational database. The overview summarizes semester charges, collections, and balances; the student register supports search; the invoice ledger shows the billed and paid amounts; the payment form allocates a payment; and reports summarize activity by faculty.

## Main relationships

- A faculty has many programmes; a programme has many students.
- Students and sponsors have a many-to-many relationship through `student_sponsors`.
- A student can have an invoice for each academic semester. An invoice has multiple fee lines.
- A payment belongs to a student and can be allocated against an invoice through `payment_allocations`.
- Semester fees are illustrative defaults by faculty and fee type.

## Design choices

- SQLite keeps setup simple for a one-day classroom presentation.
- Amounts are integer cents. Currency is recorded with each amount; the demo does not exchange currencies.
- The interface uses a ledger-inspired layout with concise totals, searchable records, and printable receipts.
- Seed data is fictional and carries a visible disclaimer. Faculty and programme labels are examples based on public NUST pages; fee amounts and semester dates are invented for the demo.

## Limits

The demo has no authentication, roles, live payment gateway, official NUST fees, student import process, or production audit controls. It must not be used to process real student information or payments.
