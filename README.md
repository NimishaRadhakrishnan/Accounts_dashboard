# Vishakan Bio Tech — Business Overview (reads from Tally)

A simple screen for the manager that shows how the business is doing: sales, money collected, expenses,
profit (estimate), cash & bank, and what dealers owe. It works on a phone or a computer. It **updates itself from
Tally** every 10 minutes. Nobody types anything twice, and nothing here ever changes Tally.

```
 Office computer (Tally open)                    VPS (same server as VBT Connect)
 ┌────────────────────────────┐   HTTPS, every   ┌───────────────────────────────────┐
 │ Tally  ◄── read-only XML ──┤   10 minutes     │ API (FastAPI) ─ PostgreSQL copy   │
 │ (port 9000, localhost)     │ ───────────────► │       │                           │
 │ Tally Connector (Python)   │  only changes;   │ Web (Next.js) ◄── Manager: phone / │
 └────────────────────────────┘  full re-read    │                   computer         │
                                  once a day     └───────────────────────────────────┘
```

## What the manager sees (one page)
* **"In short"**: 4–6 plain sentences about what went up or down. Examples: "Sales were ₹26.80 lakh — down 6% on
  September, up 10% on last October", "Repairs & Maintenance was 3.2 times the usual", "Vaigai Fertilisers bought
  less — worth a call", "₹4.7 lakh is more than 3 months late".
* **Six boxes**, each with a green/red arrow and a 12-month trend line: Sales · Money collected · Expenses ·
  Profit (estimate) · Cash and bank · Dealers owe us. Tap any box for the details behind it.
* **Sales month by month**: this year against last year.
* **Who owes us the most** (and how late), **best dealers**, **where the money went**, **best-selling products**.
* Three period buttons: *This month so far* · *last month* · *This year*. In the first week of a month it opens on
  last month, because a few days are too little to judge.
* "Updated from Tally 8 minutes ago". If the Tally computer stops sending, this turns amber and explains why.
* Large text, plain words, an A / A+ / A++ text-size switch, and no menus to learn.

## How figures are worked out (from Tally's own groups)
| Figure | From |
|---|---|
| Sales | net credits to ledgers under **Sales Accounts** (before GST, after returns) |
| Money collected | dealer (Sundry Debtors) credits in entries that put money into Cash/Bank |
| Expenses | ledgers under **Direct + Indirect Expenses**. Purchases are shown separately. |
| Profit (estimate) | sales + other income − purchases − expenses ± change in stock value (if stock is kept in Tally) |
| Cash and bank | balances under **Cash-in-Hand** and **Bank Accounts / Bank OD** |
| Dealers owe us | balances under **Sundry Debtors**. Lateness is worked out by matching payments to the oldest bills first, using each dealer's credit period (default 30 days). |

Custom groups (for example "Dealers - Kerala" under Sundry Debtors) are followed up to Tally's main groups
automatically. The admin can change the mapping in **Settings → Tally link → Check group mapping**.
Cancelled, optional and post-dated vouchers are ignored. Balances come from **Tally's own closing balances**, so
they match Tally exactly. The admin page has a "Do the figures match Tally?" table.

## The Tally connector (`tally-connector/`)
* `vbt_tally_connector.py`: one Python file with no extra packages. It only sends *Export* requests to Tally.
* Every 10 minutes it checks Tally's change counters (AltVchID/AltMstID). If nothing changed it sends only a
  heartbeat. If entries changed it sends just the changed ones. Once a day it re-reads the current and previous
  financial year month by month, which also clears out entries deleted in Tally.
* It handles both "invoice" and "voucher" style entries, Tally's UTF-16 output, and the odd control characters
  Tally emits.
* Windows helpers: `1-test-connection.bat`, `2-install-auto-update.bat` (Task Scheduler), `3-stop-auto-update.bat`.
  Plain-language steps are in `SETUP-GUIDE.txt`. The admin downloads all of this from **Settings → Tally link**,
  with the website address already filled in.
* `--file DayBook.xml Masters.xml` sends Tally XML exports instead of a live connection. This is useful for a
  first trial with real data.
* `tally_simulator.py`: a pretend Tally used for tests and demos. It is not used in production.

## Run locally (demo with the pretend Tally)
```bash
cd backend && pip install -r requirements-dev.txt && ./reset_dev_db.sh      # users: admin / manager, password Vbt@Demo2026
uvicorn app.main:app --port 8100 &
cd ../tally-connector && python tally_simulator.py --port 9000 &
#   connector.ini: dashboard url = http://127.0.0.1:8100, token = vbt_demo_key_for_local_testing_only
python vbt_tally_connector.py --test && python vbt_tally_connector.py
cd ../frontend && npm install && npm run build && npx next start -p 3100     # open http://localhost:3100
```
Tests: `cd backend && pytest -q` (74 tests). They include the whole chain: pretend Tally → real connector →
API → figures, checked against the source to the rupee.

## Deploy (Hostinger VPS, next to VBT Connect)
```bash
cp .env.example .env    # set DB_PASSWORD, JWT_SECRET, BACKUP_PASSPHRASE
docker compose up -d --build
docker compose exec -e ADMIN_PASSWORD='…' api python seed.py   # first admin (must change password)
```
Nginx + Cloudflare: `deploy/nginx-accounts.conf`. Backups: `deploy/backup.sh` (nightly, encrypted) and
`deploy/restore.sh` (test restores). Then:
1. Sign in as admin → **Settings → Users** → add the manager with role **Management (View)**.
2. **Settings → Tally link** → *Download connector* → *Create connector key* → follow the 6 steps on the Tally PC.

## Still to confirm with Vishakan's real Tally
* Version (TallyPrime or ERP 9) and that port 9000 can be turned on.
* Real group names. The mapping is automatic, but a quick look in "Check group mapping" after the first sync is wise.
* Whether stock is maintained in Tally (this affects the profit estimate) and whether bills are tracked bill-by-bill.
* Send a **Day Book (one month) + List of Accounts** export, and the admin page's match table will confirm the
  figures before the manager sees them.

## Older manual-entry module
The earlier screens for typing invoices, bills and payments are switched off, since Tally is where entries are made.
The code is kept (`ENABLE_MANUAL_ENTRY=true` turns its API back on) but it is not shown to anyone.
