# Vishakan Bio Tech — Accounts Department Dashboard (v1)

A simple, professional accounts app for the Vishakan Bio Tech accounts team: GST invoices to dealers, supplier
bills, receipts and payments, expenses, outstanding/ageing, reports (Excel/PDF), Tally export, and user/role
management with a permanent audit log.

**Agreed scope for v1** (from the approved roadmap): separate app on the same VPS as VBT Connect; **Tally stays the
statutory books** — this app is for daily entry, tracking and reporting, and exports vouchers to Tally.

---

## 1. What is in the box

| Module | What it does |
|---|---|
| Dashboard | Sales / expenses this month (vs last month), receivables, payables, cash & bank; sales-vs-spending chart for the FY; receivables ageing; top overdue dealers; supplier bills due in 7 days; approvals waiting; recent entries |
| Sales & Invoices | Draft → post GST tax invoices (number given at posting, gap-free per FY, ≤16 chars). CGST+SGST or IGST chosen automatically from the dealer's state. Credit notes (returns). Cancel with reason (number never reused). Edit posted invoice (Accounts Manager only, before period lock). Invoice PDF with amount in words. Credit-limit warning |
| Purchase Bills | Enter supplier bills with attachments; **maker-checker** — a different person verifies before the bill hits the books. Duplicate supplier bill no. blocked. Debit notes |
| Payments & Receipts | Receipts from dealers and payments to suppliers, auto-adjusted oldest-first (or by hand), part payments and advances. Payments above a limit need approval. Cash ↔ bank transfers. Cash can never go negative |
| Expenses | Category-wise expenses from cash/bank, optional GST input credit, receipt photo upload, approval above a limit |
| Outstanding | Receivables / payables ageing (not due, 1–30, 31–60, 61–90, 90+), advances, credit-limit flags, party statement (PDF/Excel) |
| Reports | Sales register, purchase register, GST summary, HSN summary, expense report, expenses by category, receivables/payables ageing, party ledger, cash/bank book, P&L summary, trial balance — each to **Excel and PDF**. **Tally XML** voucher export |
| Settings | Company profile & logo, dealers/suppliers, products (HSN, GST), bank & cash accounts, expense categories, payment terms, opening balances, numbering, approval limits, month locking, users & roles (editable permission matrix), audit log, Tally ledger names |

### Made for people new to computers (no training or tour needed)
* **Home screen asks "What would you like to do?"** with large buttons: make an invoice, money received, pay a supplier,
  enter a supplier bill, add an expense, who owes us, get a report.
* **Plain words everywhere**: "Dealers owe us" instead of receivables, "Goods returned" instead of credit note,
  "Waiting to be checked" instead of unverified, "Late by 12 days" instead of overdue 12d. Every menu item has a
  one-line description under it.
* **Big and clear**: nothing smaller than 14 px, 44 px buttons and boxes, strong contrast, no ALL-CAPS headings.
  A **Text size A / A+ / A++** switch at the top enlarges the whole screen and is remembered on that computer.
* **Forms guide you**: invoices are 3 numbered steps; the Save button always works and, if something is missing,
  says exactly what ("Choose the dealer", "Type the quantity on line 2") and marks the box in red.
* **Payments fill themselves in**: money received is linked to the oldest unpaid invoices automatically; the account is
  picked automatically when there is only one; "How was it paid?" is four big buttons.
* **Nothing hidden**: every row has a visible "Open" button, "See details →" is always shown, windows only close with
  their Close button (a stray click outside never loses typed work), and messages appear large at the top of the
  screen for 7–12 seconds with a close button.
* **Safe**: every delete, cancel, approve or sign-out asks "Are you sure?" in plain words; "Cancel this invoice" is
  never confused with closing a window. Password box has Show/Hide and a Caps Lock warning.

### How the numbers stay right
* **Double-entry ledger underneath.** Every posted document creates one balanced journal entry; cancel/edit adds a
  reversing entry. Dashboard, outstanding and reports all read the same ledger, so they always agree.
* The database itself refuses unbalanced entries and refuses any UPDATE/DELETE on the journal or audit log (triggers).
* Money is `NUMERIC(14,2)` end to end and travels over the API as exact strings — never floats.
* GST maths (one place: `backend/app/services/gst.py`): taxable = qty × rate − discount; CGST = SGST = taxable × rate/2
  (each rounded to paise) or IGST = taxable × rate; invoice total rounded to the rupee with a visible round-off line.

### Security
Argon2 password hashing (passwords can only be reset, never viewed) · httpOnly SameSite=Strict cookies + CSRF header ·
30-minute idle sign-out · lockout after 5 wrong passwords · forced password change on first sign-in · role-based
permissions checked on every API call · append-only audit log of every create/edit/post/cancel/approve/export/sign-in ·
attachments stored outside the web root with type checks · locked months · production refuses to start with a weak
secret. Full bank account numbers are never stored (last 4 digits only).

---

## 2. Run it locally

Needs Python 3.12+, Node 22, PostgreSQL 16.

```bash
# database
createuser -P vbt          # password: vbt_dev  (or set DATABASE_URL)
createdb -O vbt vbt_accounts

# backend
cd backend
pip install -r requirements-dev.txt
alembic upgrade head
python seed.py --sample            # SAMPLE data: ~7 months of entries for training/demo
uvicorn app.main:app --port 8100   # API docs at http://localhost:8100/api/docs

# frontend (new terminal)
cd frontend
npm install
npm run build && npx next start -p 3100     # or: npm run dev -- -p 3100
```
Open http://localhost:3100.

**Sample logins** (password `Vbt@Demo2026` for all): `admin` (Super Admin), `manager` (Accounts Manager),
`accountant`, `ceo` (Management view + approvals), `auditor` (read-only + audit log).

`backend/reset_dev_db.sh` wipes and reloads sample data (refuses to run in production).

### Tests
```bash
cd backend && createdb -O vbt vbt_accounts_test && pytest -q     # 60 tests
```
Covers GST/rounding/amount-in-words, numbering, posting & reversal, credit/debit notes, allocation & advances,
maker-checker, approval limits, cash limits, period locks, opening balances, DB triggers, report reconciliation
(trial balance, GST net, P&L, dashboard), Tally export, auth/CSRF/lockout/permissions, and every Excel/PDF export.

---

## 3. Deploy on the Hostinger VPS (next to VBT Connect)

The app has its own database, network and port, and publishes only `127.0.0.1:3100`.

```bash
sudo mkdir -p /opt/vbt-accounts && cd /opt/vbt-accounts     # copy this folder here
cp .env.example .env && nano .env                            # set DB_PASSWORD, JWT_SECRET, BACKUP_PASSPHRASE
docker compose up -d --build
docker compose exec -e ADMIN_PASSWORD='choose-a-strong-one' api python seed.py   # reference data + first admin
```
Then:
1. Nginx: copy `deploy/nginx-accounts.conf`, set the sub-domain (e.g. `accounts.<company-domain>`), Cloudflare
   origin certificate, `nginx -t && systemctl reload nginx`. Cloudflare DNS → proxied, SSL "Full (strict)".
2. Backups: `crontab -e` → `15 1 * * * /opt/vbt-accounts/deploy/backup.sh >> /var/log/vbt-accounts-backup.log 2>&1`
   (encrypted DB + attachments, 30-day retention, optional rclone copy off-server).
3. Test a restore: `deploy/restore.sh /var/backups/vbt-accounts/db-<stamp>.sql.gz.gpg` (restores into a test DB).
4. UFW: only 22/80/443 open; nothing from this app needs another port.

---

## 4. Go-live checklist (needs the company's inputs)

Everything company-specific is **SAMPLE** until confirmed. The app runs fully without it, but these must be
replaced before real invoices go out:

| # | Item | Where it goes |
|---|---|---|
| C1–C3 | Legal name, address, GSTIN, PAN, logo, signatory, bank details on invoice, invoice terms | Settings → Company |
| C4–C5 | Sample invoice to match layout; current numbering format and last number used in Tally | Settings → Numbering (prefix + next number) |
| C6–C8 | Dealer list, supplier list, product list with **HSN and GST rates confirmed by the CA** | Settings → Dealers & suppliers / Products |
| C10–C11 | Opening bank/cash balances and every unpaid invoice/bill on the go-live date | Settings → Bank & cash; Dealers & suppliers → Opening balance |
| C12–C13 | Credit days per dealer, credit limits, expense categories, approval limits | Settings |
| C15 | Staff list and who approves what | Settings → Users & roles |
| C16 | Tally ledger names (exact spelling) — then **test the XML import on a copy of the Tally company** | Settings → Tally ledgers |
| C17–C18 | Turnover (decides e-invoicing), TDS/TCS applicability | Not built in v1 — see limitations |
| C20, C22 | Sub-domain, backup location | Deploy steps above |

Production starts empty (no `--sample`). Recommended: run alongside Tally for the first month and check that the
trial balance, receivables and GST summary match before relying on it.

---

## 5. Known limitations of v1 (deliberate, per agreed scope)
* **Not the statutory books**: no GSTR-1/3B filing, e-invoice (IRN/QR) or e-way bill generation, TDS/TCS, depreciation,
  stock valuation or year-end closing. P&L is a management summary only. These stay in Tally / with the CA.
* No inventory/stock tracking; no payroll (salary totals can be booked as an expense).
* No bank statement import / reconciliation screen yet.
* Tally XML follows Tally's standard voucher import format but has **not been tested against Vishakan's Tally** —
  needs one trial import (C16).
* No email/WhatsApp sending of invoices or reminders.
* Sample GST rates/HSN codes are placeholders, not tax advice.

## 6. Layout
```
backend/   FastAPI + SQLAlchemy 2 + Alembic (Clean layering: models → services → routers)
  app/services/gst.py      GST maths          app/services/ledger.py   double-entry posting
  app/services/sales.py    invoices, CNs      app/services/purchases.py bills, DNs (maker-checker)
  app/services/cash.py     receipts, payments, allocation, expenses, transfers
  app/services/reports.py  all reports        app/services/exports.py  Excel/PDF/invoice PDF
  app/services/tally.py    Tally XML          migrations/              schema + DB safety triggers
frontend/  Next.js 16 + Tailwind 4 + Recharts (palette tokens in app/globals.css)
deploy/    backup.sh, restore.sh, nginx-accounts.conf
```
