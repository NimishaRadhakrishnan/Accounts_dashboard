"""Set up reference data, and optionally load SAMPLE data for demos and training.

    python seed.py                       # reference data + admin user only (production)
    python seed.py --sample              # also loads sample company, dealers, products and ~7 months of entries

Production admin: set ADMIN_USERNAME / ADMIN_PASSWORD env vars; the admin must change the password on first login.
Everything created with --sample is clearly marked SAMPLE and must be wiped before go-live (see README).
"""
import argparse
import os
import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.deps import Actor
from app.core.security import hash_password
from app.models import Company, ExpenseCategory, Party, PaymentTerm, Product, Role, User
from app.schemas import (AllocationIn, BankAccountIn, BillIn, CompanyIn, ContraIn, CreditNoteIn, ExpenseCategoryIn,
                         ExpenseIn, InvoiceIn, LineIn, OpeningDocIn, PartyIn, PaymentIn, PaymentTermIn, PeriodLockIn,
                         ProductIn, ReceiptIn)
from app.services import cash, masters, purchases, sales
from app.services.bootstrap import ensure_admin, ensure_fy, ensure_reference_data

DEMO_PASSWORD = "Vbt@Demo2026"

DEALERS = [
    # code, name, city, district, state_code, state_name, gstin, term_days, credit_limit
    ("D001", "Sri Murugan Agro Centre", "Pollachi", "Coimbatore", "33", "Tamil Nadu", "33AAPFM1234K1Z2", 30, 500000),
    ("D002", "Kongu Farm Inputs", "Gobichettipalayam", "Erode", "33", "Tamil Nadu", "33AAKFK2234L1Z8", 45, 400000),
    ("D003", "Green Valley Agri Traders", "Udumalpet", "Tiruppur", "33", "Tamil Nadu", "33AAGFG3234M1Z1", 30, 300000),
    ("D004", "Cauvery Krishi Kendra", "Mettur", "Salem", "33", "Tamil Nadu", "33AACFC4234N1Z4", 60, 600000),
    ("D005", "Palani Hills Agro Agencies", "Oddanchatram", "Dindigul", "33", "Tamil Nadu", "33AAPFP5234P1Z7", 30, 250000),
    ("D006", "Theni Organic Supplies", "Cumbum", "Theni", "33", "Tamil Nadu", "33AATFT6234Q1Z3", 45, 350000),
    ("D007", "Vaigai Fertilisers & Seeds", "Melur", "Madurai", "33", "Tamil Nadu", "33AAVFV7234R1Z6", 30, 300000),
    ("D008", "Nilgiri Plantation Stores", "Gudalur", "Nilgiris", "33", "Tamil Nadu", "33AANFN8234S1Z9", 30, 200000),
    ("D009", "Palakkad Agri Mart", "Chittur", "Palakkad", "32", "Kerala", "32AAPFP9234T1Z5", 45, 400000),
    ("D010", "Thrissur Krishi Bhavan Traders", "Chalakudy", "Thrissur", "32", "Kerala", "32AATFT1034U1Z1", 45, 300000),
    ("D011", "Idukki Spice Growers Supply", "Kattappana", "Idukki", "32", "Kerala", "32AAIFI1134V1Z4", 60, 350000),
    ("D012", "Bhavani Agro Services", "Bhavani", "Erode", "33", "Tamil Nadu", None, 0, 0),
]

SUPPLIERS = [
    ("S001", "Lignite Carrier Materials Co.", "Neyveli", "Cuddalore", "33", "Tamil Nadu", "33AALCL2134W1Z8", 30),
    ("S002", "Coimbatore Poly Packaging", "Coimbatore", "Coimbatore", "33", "Tamil Nadu", "33AACFC2234X1Z2", 45),
    ("S003", "BioCulture Labs Pvt Ltd", "Bengaluru", "Bengaluru Urban", "29", "Karnataka", "29AABCB2334Y1Z5", 30),
    ("S004", "Western Ghats Logistics", "Coimbatore", "Coimbatore", "33", "Tamil Nadu", "33AAWFW2434Z1Z9", 15),
    ("S005", "Agro Chem Raw Materials", "Kochi", "Ernakulam", "32", "Kerala", "32AAAFA2534A1Z3", 30),
]

PRODUCTS = [
    # code, name, category, hsn, unit, gst, sale, purchase
    ("BF-AZO-1L", "Azospirillum Liquid 1 L", "Bio-fertilizer", "3101", "Ltr", "5", "320", "0"),
    ("BF-PSB-1L", "Phosphobacteria Liquid 1 L", "Bio-fertilizer", "3101", "Ltr", "5", "320", "0"),
    ("BF-KMB-1L", "Potash Mobilising Bacteria 1 L", "Bio-fertilizer", "3101", "Ltr", "5", "340", "0"),
    ("BF-RHZ-1KG", "Rhizobium Carrier 1 kg", "Bio-fertilizer", "3101", "Kg", "5", "120", "0"),
    ("BC-TRI-1KG", "Trichoderma viride 1 kg", "Bio-fungicide", "3808", "Kg", "5", "260", "0"),
    ("BC-PSF-1KG", "Pseudomonas fluorescens 1 kg", "Bio-fungicide", "3808", "Kg", "5", "240", "0"),
    ("BP-BEA-1KG", "Beauveria bassiana 1 kg", "Bio-pesticide", "3808", "Kg", "5", "380", "0"),
    ("BP-MET-1KG", "Metarhizium anisopliae 1 kg", "Bio-pesticide", "3808", "Kg", "5", "380", "0"),
    ("BS-SWE-1L", "Seaweed Extract 1 L", "Bio-stimulant", "3101", "Ltr", "18", "450", "0"),
    ("BS-HUM-1KG", "Humic Acid Granules 1 kg", "Bio-stimulant", "3101", "Kg", "18", "180", "0"),
]

PURCHASE_ITEMS = [
    # supplier code, description, hsn, unit, gst, rate range
    # supplier, description, hsn, unit, gst, rate range, qty choices
    ("S001", "Lignite carrier powder", "2702", "Kg", "5", (12, 16), (5000, 8000, 12000, 20000)),
    ("S002", "HDPE bottles 1 L with caps", "3923", "Nos", "18", (9, 12), (5000, 10000, 15000)),
    ("S002", "Printed laminated pouches 1 kg", "3923", "Nos", "18", (4, 6), (10000, 20000, 30000)),
    ("S003", "Mother cultures (assorted strains)", "3002", "Nos", "12", (1800, 2600), (5, 8, 12)),
    ("S004", "Freight — dealer dispatches", "9965", "Trip", "5", (2500, 6500), (3, 5, 8)),
    ("S005", "Molasses / media ingredients", "1703", "Kg", "5", (28, 40), (2000, 4000, 6000)),
]

EXPENSES = [
    ("Travel & Conveyance", (300, 4500), "0"), ("Fuel", (1500, 6500), "0"), ("Electricity", (8000, 18000), "18"),
    ("Telephone & Internet", (1200, 3500), "18"), ("Printing & Stationery", (400, 3000), "18"),
    ("Repairs & Maintenance", (1500, 12000), "18"), ("Office Expenses", (300, 2500), "0"),
    ("Staff Welfare", (500, 4000), "0"), ("Bank Charges", (100, 900), "18"), ("Rent", (25000, 25000), "18"),
    ("Professional Fees", (10000, 15000), "18"), ("Advertising & Promotion", (3000, 20000), "18"),
    ("Salaries & Wages", (380000, 420000), "0"),
]


def _users(db) -> dict[str, User]:
    roles = {r.code: r for r in db.scalars(select(Role))}
    spec = [("admin", "Admin (Sample)", "super_admin"), ("manager", "Accounts Manager (Sample)", "accounts_manager"),
            ("accountant", "Accountant (Sample)", "accountant"), ("ceo", "Management View (Sample)", "management"),
            ("auditor", "Auditor (Sample)", "auditor")]
    out = {}
    for username, name, role in spec:
        u = db.scalar(select(User).where(User.username == username))
        if not u:
            u = User(full_name=name, username=username, password_hash=hash_password(DEMO_PASSWORD),
                     role_id=roles[role].id, must_change_password=False)
            db.add(u)
            db.flush()
        out[username] = u
    return out


def load_sample(db, today: date) -> None:
    if db.scalar(select(Party).limit(1)):
        print("Sample data already present — skipping.")
        return
    rnd = random.Random(2026)
    ensure_fy(db, 2025)
    ensure_fy(db, 2026, make_current=True)
    users = _users(db)
    admin, mgr, acct = Actor(users["admin"]), Actor(users["manager"]), Actor(users["accountant"])

    masters.save_company(db, admin, CompanyIn(
        legal_name="Vishakan Biotech Pvt. Ltd.", trade_name="Vishakan Bio Tech", gstin="33AADCV1234F1Z6",
        pan="AADCV1234F", address="SAMPLE ADDRESS — to be replaced\nIndustrial Estate", city="Coimbatore",
        state_code="33", state_name="Tamil Nadu", pincode="641001", phone="+91 00000 00000",
        email="accounts@example.com",
        bank_details_for_invoice="SAMPLE — Bank name, A/c no., IFSC to be confirmed by Accounts",
        signatory_name="", signatory_designation="Authorised Signatory",
        invoice_terms="1. Goods once sold will not be taken back.\n2. Interest @18% p.a. on overdue bills.\n"
                      "3. Subject to Coimbatore jurisdiction.\n(SAMPLE terms — replace with company terms)"))
    db.scalar(select(Company)).is_sample_data = True

    terms = {}
    for name, days in [("Immediate", 0), ("15 days", 15), ("30 days", 30), ("45 days", 45), ("60 days", 60)]:
        terms[days] = masters.save_term(db, admin, PaymentTermIn(name=name, days=days))

    for name, _, _ in EXPENSES:
        masters.save_category(db, admin, ExpenseCategoryIn(name=name))
    cats = {c.name: c for c in db.scalars(select(ExpenseCategory))}

    opening = date(2026, 4, 1)
    main = masters.save_bank(db, admin, BankAccountIn(name="Main Current A/c (Sample)", kind="bank",
                                                      bank_name="SAMPLE BANK", last4="1234",
                                                      opening_balance=Decimal("1850000"), opening_date=opening))
    coll = masters.save_bank(db, admin, BankAccountIn(name="Collections A/c (Sample)", kind="bank",
                                                      bank_name="SAMPLE BANK", last4="5678",
                                                      opening_balance=Decimal("420000"), opening_date=opening))
    cash_acc = masters.save_bank(db, admin, BankAccountIn(name="Cash in Hand — Office", kind="cash",
                                                          opening_balance=Decimal("35000"), opening_date=opening))

    dealers = []
    for code, name, city, dist, sc, sn, gstin, days, limit in DEALERS:
        dealers.append(masters.save_party(db, admin, PartyIn(
            code=code, name=name, is_customer=True, gstin=gstin, city=city, district=dist, state_code=sc,
            state_name=sn, payment_term_id=terms[days].id, credit_limit=Decimal(limit),
            contact_person="Proprietor", phone="+91 00000 00000", address=f"Main Road, {city}",
            notes="SAMPLE dealer")))
    suppliers = {}
    for code, name, city, dist, sc, sn, gstin, days in SUPPLIERS:
        suppliers[code] = masters.save_party(db, admin, PartyIn(
            code=code, name=name, is_supplier=True, gstin=gstin, city=city, district=dist, state_code=sc,
            state_name=sn, payment_term_id=terms[days].id, address=f"{city}", notes="SAMPLE supplier"))

    products = []
    for code, name, cat, hsn, unit, gst_rate, sp, pp in PRODUCTS:
        products.append(masters.save_product(db, admin, ProductIn(
            code=code, name=name, category=cat, hsn_code=hsn, unit=unit, gst_rate=Decimal(gst_rate),
            sale_price=Decimal(sp), purchase_price=Decimal(pp))))

    # Opening outstanding carried over from Tally (dated last FY)
    for i, (dealer_idx, amt, d) in enumerate([(0, 84250, date(2026, 2, 18)), (3, 132400, date(2026, 1, 27)),
                                              (8, 56780, date(2026, 3, 9)), (5, 41200, date(2026, 3, 22))]):
        sales.create_opening_invoice(db, admin, OpeningDocIn(party_id=dealers[dealer_idx].id, ref_no=f"25-{812 + i}",
                                                             date=d, amount=Decimal(amt),
                                                             notes="Carried over from Tally (SAMPLE)"))
    purchases.create_opening_bill(db, admin, OpeningDocIn(party_id=suppliers["S001"].id, ref_no="LC/2526/447",
                                                          date=date(2026, 3, 15), amount=Decimal("68500")))

    # Month by month activity
    d = date(2026, 4, 1)
    seq = 0
    while d <= today:
        month_end = (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        last = min(month_end, today)
        days = (last - d).days + 1
        season = 1.35 if d.month in (6, 7, 9, 10) else 1.0  # sowing seasons
        if d + timedelta(days=1) <= today and cash.bank_balance(db, cash_acc.id, d) < 30000:  # petty cash top-up
            cash.create_contra(db, acct, ContraIn(date=d + timedelta(days=1), from_account_id=main.id,
                                                  to_account_id=cash_acc.id, amount=Decimal("30000"),
                                                  reference="Cash withdrawal for petty expenses"))

        # Sales
        # dates sorted so numbers run in date order, as they would in real use
        for inv_date in sorted(d + timedelta(days=rnd.randrange(days)) for _ in range(int(rnd.randint(9, 13) * season))):
            dealer = rnd.choice(dealers[:11]) if rnd.random() > 0.05 else dealers[11]
            lines = []
            for prod in rnd.sample(products, rnd.randint(2, 5)):
                qty = Decimal(rnd.choice([20, 25, 40, 50, 60, 80, 100, 120, 150, 200]))
                lines.append(LineIn(product_id=prod.id, description=prod.name, hsn_code=prod.hsn_code, qty=qty,
                                    unit=prod.unit, rate=prod.sale_price,
                                    discount_pct=Decimal(rnd.choice([0, 0, 0, 2, 5])), gst_rate=prod.gst_rate))
            seq += 1
            inv, _ = sales.create_invoice(db, acct, InvoiceIn(party_id=dealer.id, date=inv_date, lines=lines,
                                                              reference=f"PO-{seq:04d}"), post_now=True)
            if rnd.random() < 0.06:  # occasional sales return
                ln = inv.lines[0]
                sales.create_credit_note(db, mgr, CreditNoteIn(
                    sales_invoice_id=inv.id, date=min(inv_date + timedelta(days=rnd.randint(3, 12)), today),
                    reason="Damaged in transit",
                    lines=[LineIn(product_id=ln.product_id, description=ln.description, hsn_code=ln.hsn_code,
                                  qty=Decimal(5), unit=ln.unit, rate=ln.rate, discount_pct=ln.discount_pct,
                                  gst_rate=ln.gst_rate)]))

        # Purchases (entered by accountant, verified by manager)
        for bdate in sorted(d + timedelta(days=rnd.randrange(days)) for _ in range(rnd.randint(4, 7))):
            sup_code, desc, hsn, unit, gst_rate, (lo, hi), qtys = rnd.choice(PURCHASE_ITEMS)
            qty = Decimal(rnd.choice(qtys))
            bill = purchases.create_bill(db, acct, BillIn(
                party_id=suppliers[sup_code].id, supplier_bill_no=f"{sup_code}/{bdate:%y%m}/{rnd.randint(100, 999)}",
                date=bdate, lines=[LineIn(description=desc, hsn_code=hsn, qty=qty, unit=unit,
                                          rate=Decimal(rnd.randint(lo, hi)), gst_rate=Decimal(gst_rate))]))
            if (today - bdate).days > 2 or rnd.random() < 0.5:
                purchases.verify_bill(db, mgr, bill.id)

        # Expenses
        planned = []
        for name, (lo, hi), gst_rate in EXPENSES:
            if name == "Salaries & Wages" and d.replace(day=28) > today:
                continue  # salaries are paid at month end
            if name in ("Rent", "Electricity", "Telephone & Internet", "Salaries & Wages") or rnd.random() < 0.6:
                edate = d.replace(day=28) if name == "Salaries & Wages" else d + timedelta(days=rnd.randrange(days))
                planned.append((edate, name, Decimal(rnd.randint(lo, hi)), gst_rate))
        for edate, name, amt, gst_rate in sorted(planned):
            use_cash = amt < 5000 and name not in ("Rent", "Electricity", "Professional Fees", "Salaries & Wages")
            ex = cash.create_expense(db, acct, ExpenseIn(
                date=edate, category_id=cats[name].id,
                bank_account_id=(cash_acc.id if use_cash else main.id), payee=f"{name} vendor (Sample)",
                description=f"{name} — {edate:%B}", mode="cash" if use_cash else "neft",
                amount=amt, gst_rate=Decimal(gst_rate), gst_claimable=gst_rate != "0",
                supplier_gstin="33AAAFZ9999Z1Z9" if gst_rate != "0" else None))
            if ex.status == "pending_approval" and (today - edate).days > 4:
                cash.approve_expense(db, mgr, ex.id)
        d = month_end + timedelta(days=1)

    # Receipts: dealers pay most invoices roughly on terms
    receipts_plan = []
    for dealer in dealers:
        for item in sorted(cash._open_invoices(db, dealer.id), key=lambda x: x[0].date):
            inv, bal = item
            pay_on = inv.due_date + timedelta(days=rnd.randint(-10, 25))
            if pay_on > today or rnd.random() < 0.12:
                continue
            partial = rnd.random() < 0.15
            amount = (bal * Decimal("0.6")).quantize(Decimal("1")) if partial else bal
            bank = coll if rnd.random() < 0.7 else main
            receipts_plan.append(ReceiptIn(
                party_id=dealer.id, date=max(pay_on, inv.date), bank_account_id=bank.id, amount=amount,
                mode=rnd.choice(["neft", "neft", "rtgs", "upi", "cheque"]), reference=f"UTR{rnd.randint(10**9, 10**10)}",
                allocations=[AllocationIn(doc_id=inv.id, amount=amount)]))
    for r in sorted(receipts_plan, key=lambda x: x.date):
        cash.create_receipt(db, acct, r)
    # One advance received, not yet matched
    cash.create_receipt(db, acct, ReceiptIn(party_id=dealers[2].id, date=today - timedelta(days=2),
                                            bank_account_id=coll.id, amount=Decimal("25000"), mode="upi",
                                            reference="Advance for Rabi order", allocations=[]))

    # Supplier payments
    payments_plan = []
    for sup in suppliers.values():
        for bill, bal in sorted(cash._open_bills(db, sup.id), key=lambda x: x[0].date):
            pay_on = bill.due_date + timedelta(days=rnd.randint(-5, 10))
            if pay_on > today or rnd.random() < 0.1:
                continue
            payments_plan.append(PaymentIn(
                party_id=sup.id, date=max(pay_on, bill.date), bank_account_id=main.id, amount=bal, mode="neft",
                reference=f"NEFT{rnd.randint(10**8, 10**9)}", allocations=[AllocationIn(doc_id=bill.id, amount=bal)]))
    for pi in sorted(payments_plan, key=lambda x: x.date):
        py = cash.create_payment(db, acct, pi)
        if py.status == "pending_approval" and (today - py.date).days > 3:
            cash.approve_payment(db, mgr, py.id)

    # Monthly sweep from collections to main account
    for m in range(4, today.month + (1 if today.year == 2026 else 0)):
        sweep_day = date(2026, m, 25)
        if sweep_day > today:
            break
        bal = cash.bank_balance(db, coll.id, sweep_day)
        if bal > 100000:
            cash.create_contra(db, acct, ContraIn(date=sweep_day, from_account_id=coll.id, to_account_id=main.id,
                                                  amount=(bal - 50000).quantize(Decimal("1000")),
                                                  reference="Monthly sweep"))

    # Lock closed months (April to two months ago)
    for m in range(4, max(4, today.month - 1)):
        masters.lock_period(db, mgr, PeriodLockIn(year=2026, month=m))
    print(f"Sample data loaded up to {today}.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="load SAMPLE data for demos/training")
    ap.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = ap.parse_args()
    with SessionLocal() as db:
        ensure_reference_data(db)
        if args.sample:
            load_sample(db, args.today)
        else:
            ensure_fy(db, args.today.year if args.today.month >= 4 else args.today.year - 1, make_current=True)
            username = os.environ.get("ADMIN_USERNAME", "admin")
            password = os.environ.get("ADMIN_PASSWORD")
            if not password:
                raise SystemExit("Set ADMIN_PASSWORD (10+ chars, letters and numbers) for the first admin user.")
            ensure_admin(db, username, password)
            print(f"Admin user '{username}' ready — must change password at first login.")
        db.commit()


if __name__ == "__main__":
    main()
