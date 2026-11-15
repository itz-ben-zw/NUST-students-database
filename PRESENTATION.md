# Five-minute presentation

## 1. Introduce the problem

Student accounts involve students, programmes, semester charges, receipts, and balances. If those records are disconnected, it becomes harder to answer whether a payment was received and which account it reduced.

## 2. Show the database structure

Start with the relationships: faculties contain programmes; students are enrolled in programmes; semester invoices contain fee lines; payments are linked to students and allocated to invoices. Sponsors use a linking table because a student may have more than one sponsor.

## 3. Walk through the app

1. Overview: compare fictional amounts invoiced, collected, and outstanding.
2. Students: search by number, name, programme, or faculty.
3. Invoices: inspect each semester account and its balance.
4. Payments: enter a fictional amount, date, currency, and payment method.
5. Receipt and reports: show the linked receipt and faculty summary.

## 4. Explain a database choice

Money is stored in integer cents to avoid floating-point rounding. Payment allocations connect a payment to an invoice, so a balance can be calculated as invoice lines minus allocated payments. Currency stays explicit and is not silently converted.

## 5. State the scope honestly

This is an independent class demo, not an official NUST system. Student details, payment references, dates, and fee values are fictional; the fees do not represent an official schedule. The app demonstrates core database relationships and a user workflow, not live payment processing or secure production operations.
