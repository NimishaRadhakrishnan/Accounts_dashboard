"""
A pretend Tally for testing and demos. It answers the same XML requests the connector sends, in Tally's XML
format, with made-up data for a bio-fertilizer company (sales in "invoice" style with stock items, bank receipts
against bills, supplier payments, expenses, GST, a cancelled and an optional entry).

    python tally_simulator.py --port 9000 --today 2026-11-03

NOT used in production. Real Tally replaces it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import re
import uuid
from decimal import ROUND_HALF_UP, Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape

D = Decimal
P2 = D("0.01")
COMPANY = "Vishakan Biotech Pvt. Ltd. (SAMPLE)"
COMPANY_GUID = "c0ffee00-0000-4000-8000-000000000001"

# Tally's own groups plus a few the company might add
GROUPS = [
    ("Capital Account", ""), ("Current Assets", ""), ("Current Liabilities", ""), ("Fixed Assets", ""),
    ("Sales Accounts", ""), ("Purchase Accounts", ""), ("Direct Expenses", ""), ("Indirect Expenses", ""),
    ("Direct Incomes", ""), ("Indirect Incomes", ""), ("Loans (Liability)", ""), ("Suspense A/c", ""),
    ("Bank Accounts", "Current Assets"), ("Cash-in-Hand", "Current Assets"), ("Sundry Debtors", "Current Assets"),
    ("Stock-in-Hand", "Current Assets"), ("Deposits (Asset)", "Current Assets"),
    ("Sundry Creditors", "Current Liabilities"), ("Duties & Taxes", "Current Liabilities"),
    ("Provisions", "Current Liabilities"), ("Secured Loans", "Loans (Liability)"),
    # company's own sub-groups
    ("Dealers - Tamil Nadu", "Sundry Debtors"), ("Dealers - Kerala", "Sundry Debtors"),
    ("Raw Material Suppliers", "Sundry Creditors"), ("Office & Admin Expenses", "Indirect Expenses"),
    ("Selling Expenses", "Indirect Expenses"), ("Factory Expenses", "Direct Expenses"),
]

DEALERS = [
    ("Sri Murugan Agro Centre", "Dealers - Tamil Nadu", "Tamil Nadu", 30, 1.3),
    ("Kongu Farm Inputs", "Dealers - Tamil Nadu", "Tamil Nadu", 45, 1.6),
    ("Green Valley Agri Traders", "Dealers - Tamil Nadu", "Tamil Nadu", 30, 1.0),
    ("Cauvery Krishi Kendra", "Dealers - Tamil Nadu", "Tamil Nadu", 60, 1.4),
    ("Palani Hills Agro Agencies", "Dealers - Tamil Nadu", "Tamil Nadu", 30, 0.9),
    ("Theni Organic Supplies", "Dealers - Tamil Nadu", "Tamil Nadu", 45, 0.8),
    ("Vaigai Fertilisers & Seeds", "Dealers - Tamil Nadu", "Tamil Nadu", 30, 1.1),
    ("Nilgiri Plantation Stores", "Dealers - Tamil Nadu", "Tamil Nadu", 30, 0.7),
    ("Palakkad Agri Mart", "Dealers - Kerala", "Kerala", 45, 1.2),
    ("Thrissur Krishi Bhavan Traders", "Dealers - Kerala", "Kerala", 45, 0.9),
    ("Idukki Spice Growers Supply", "Dealers - Kerala", "Kerala", 60, 1.0),
    ("Bhavani Agro Services", "Dealers - Tamil Nadu", "Tamil Nadu", 15, 0.5),
    ("Erode Green Farms Depot", "Dealers - Tamil Nadu", "Tamil Nadu", 30, 0.6),
    ("Wayanad Coffee Growers Co-op", "Dealers - Kerala", "Kerala", 45, 0.7),
]
SLOW_PAYERS = {"Nilgiri Plantation Stores", "Idukki Spice Growers Supply"}
NEW_IN_FY27 = {"Erode Green Farms Depot", "Wayanad Coffee Growers Co-op"}

SUPPLIERS = [
    ("Lignite Carrier Materials Co.", "Raw Material Suppliers", ["Lignite carrier powder"]),
    ("Coimbatore Poly Packaging", "Raw Material Suppliers", ["HDPE bottles", "Printed pouches"]),
    ("BioCulture Labs Pvt Ltd", "Raw Material Suppliers", ["Mother cultures"]),
    ("Agro Chem Raw Materials", "Raw Material Suppliers", ["Molasses and media"]),
    ("Western Ghats Logistics", "Sundry Creditors", []),
]

PRODUCTS = [  # name, unit, rate, gst, popularity
    ("Azospirillum Liquid 1 L", "Ltr", 320, 5, 1.4), ("Phosphobacteria Liquid 1 L", "Ltr", 320, 5, 1.3),
    ("Potash Mobilising Bacteria 1 L", "Ltr", 340, 5, 0.9), ("Rhizobium Carrier 1 kg", "Kg", 120, 5, 0.6),
    ("Trichoderma viride 1 kg", "Kg", 260, 5, 1.2), ("Pseudomonas fluorescens 1 kg", "Kg", 240, 5, 1.0),
    ("Beauveria bassiana 1 kg", "Kg", 380, 5, 0.7), ("Metarhizium anisopliae 1 kg", "Kg", 380, 5, 0.5),
    ("Seaweed Extract 1 L", "Ltr", 450, 18, 0.8), ("Humic Acid Granules 1 kg", "Kg", 180, 18, 0.9),
]

EXPENSES = [  # ledger, group, monthly base, gst
    ("Salaries & Wages", "Indirect Expenses", 410000, 0), ("Factory Wages", "Factory Expenses", 180000, 0),
    ("Rent", "Office & Admin Expenses", 25000, 18), ("Electricity Charges", "Factory Expenses", 42000, 0),
    ("Telephone & Internet", "Office & Admin Expenses", 3500, 18), ("Printing & Stationery", "Office & Admin Expenses", 3000, 18),
    ("Travelling Expenses", "Selling Expenses", 38000, 0), ("Fuel - Vehicles", "Selling Expenses", 52000, 0),
    ("Advertisement & Field Demos", "Selling Expenses", 30000, 18), ("Freight Outward", "Selling Expenses", 36000, 5),
    ("Repairs & Maintenance", "Factory Expenses", 15000, 18), ("Bank Charges", "Indirect Expenses", 900, 18),
    ("Professional Fees", "Office & Admin Expenses", 15000, 18), ("Staff Welfare", "Office & Admin Expenses", 6000, 0),
]

BANKS = [("HDFC Bank - Current A/c", "Bank Accounts", 2400000), ("Indian Bank - Collections A/c", "Bank Accounts", 600000),
         ("Cash", "Cash-in-Hand", 45000)]

SEASON = {4: 0.8, 5: 0.75, 6: 1.25, 7: 1.4, 8: 1.1, 9: 1.3, 10: 1.35, 11: 1.0, 12: 0.85, 1: 0.8, 2: 0.75, 3: 1.05}


def r2(x) -> Decimal:
    return D(x).quantize(P2, rounding=ROUND_HALF_UP)


def amt(dr: Decimal) -> str:
    """Tally writes debits as negative numbers."""
    return f"{-dr:.2f}"


class Book:
    def __init__(self, today: dt.date, seed: int = 7):
        self.today = today
        self.rnd = random.Random(seed)
        self.books_from = dt.date(2025, 4, 1)
        self.vouchers: list[dict] = []
        self.alter = 1000
        self.ledgers: dict[str, dict] = {}
        self._masters()
        self._generate()

    # ---- masters --------------------------------------------------------------------------------
    def L(self, name, parent, opening_dr=D(0), **kw):
        self.ledgers[name] = {"name": name, "parent": parent, "opening_dr": D(opening_dr), "guid": str(uuid.uuid5(uuid.NAMESPACE_DNS, name)), **kw}

    def _masters(self):
        opening_debtors = {"Kongu Farm Inputs": 132400, "Cauvery Krishi Kendra": 98000, "Palakkad Agri Mart": 56780,
                           "Nilgiri Plantation Stores": 61200}
        for name, parent, state, days, _ in DEALERS:
            self.L(name, parent, opening_debtors.get(name, 0), state=state, credit_days=days, bill_wise=True,
                   gstin=("33" if state == "Tamil Nadu" else "32") + "AAAPZ" + str(abs(hash(name)) % 9000 + 1000) + "K1Z" + "5")
        for name, parent, _ in SUPPLIERS:
            self.L(name, parent, -68500 if name.startswith("Lignite") else 0, state="Tamil Nadu", credit_days=30, bill_wise=True)
        for rate in (5, 18):
            self.L(f"Sales GST {rate}%", "Sales Accounts")
            self.L(f"Purchase GST {rate}%", "Purchase Accounts")
        self.L("Sales Returns", "Sales Accounts")
        for t in ("Output CGST", "Output SGST", "Output IGST", "Input CGST", "Input SGST", "Input IGST"):
            self.L(t, "Duties & Taxes")
        self.L("Round Off", "Indirect Expenses")
        self.L("Interest Received", "Indirect Incomes")
        self.L("Scrap Sales", "Direct Incomes")
        for name, parent, base, _ in EXPENSES:
            self.L(name, parent)
        for name, parent, opening in BANKS:
            self.L(name, parent, opening)
        self.L("Plant & Machinery", "Fixed Assets", 3800000)
        self.L("Opening Stock", "Stock-in-Hand", 0)
        self.L("Term Loan - HDFC", "Secured Loans", -1500000)
        total = sum(l["opening_dr"] for l in self.ledgers.values())
        self.L("Capital Account - Partners", "Capital Account", -total)

    # ---- vouchers -------------------------------------------------------------------------------
    def V(self, date, vtype, number, party, lines, stock=None, invoice=False, narration="", cancelled=False, optional=False):
        assert abs(sum(l[1] for l in lines)) < D("0.01"), (vtype, number, lines)
        self.alter += 1
        self.vouchers.append({"date": date, "type": vtype, "number": number, "party": party, "lines": lines,
                              "stock": stock or [], "invoice": invoice, "narration": narration, "cancelled": cancelled,
                              "optional": optional, "alter": self.alter, "guid": str(uuid.uuid4())})

    def _generate(self):
        rnd = self.rnd
        open_bills: dict[str, list] = {d[0]: [] for d in DEALERS}  # [number, date, balance]
        for name, amt0 in [("Kongu Farm Inputs", 132400), ("Cauvery Krishi Kendra", 98000), ("Palakkad Agri Mart", 56780),
                           ("Nilgiri Plantation Stores", 61200)]:
            open_bills[name].append([f"24-25/OB-{name[:3].upper()}", dt.date(2025, 3, 10), D(amt0), None])
        sup_bills: dict[str, list] = {s[0]: [] for s in SUPPLIERS}
        sup_bills["Lignite Carrier Materials Co."].append(["LC/2425/447", dt.date(2025, 3, 15), D(68500)])
        inv_no = {"25-26": 0, "26-27": 0}
        cn_no = {"25-26": 0, "26-27": 0}
        rec_no = {"25-26": 0, "26-27": 0}

        d = self.books_from
        while d <= self.today:
            fy = "25-26" if d < dt.date(2026, 4, 1) else "26-27"
            growth = D("1.0") if fy == "25-26" else D("1.12")
            m_end = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
            last = min(m_end, self.today)
            days = (last - d).days + 1
            # ---- sales invoices
            n_inv = int(rnd.randint(28, 36) * SEASON[d.month] * days / 30)
            for inv_date in sorted(d + dt.timedelta(days=rnd.randrange(days)) for _ in range(n_inv)):
                pool = [x for x in DEALERS if not (fy == "25-26" and x[0] in NEW_IN_FY27)]
                dealer = rnd.choices(pool, weights=[x[4] for x in pool])[0]
                name, _, state, cdays, _ = dealer
                inter = state != "Tamil Nadu"
                stock, sales_by_rate = [], {}
                for p in rnd.choices(PRODUCTS, weights=[x[4] for x in PRODUCTS], k=rnd.randint(2, 4)):
                    qty = D(rnd.choice([20, 25, 40, 50, 60, 80, 100, 120])) * growth
                    qty = qty.quantize(D("1"))
                    value = r2(qty * p[2])
                    stock.append((p[0], qty, p[1], D(p[2]), value, f"Sales GST {p[3]}%"))
                    sales_by_rate[p[3]] = sales_by_rate.get(p[3], D(0)) + value
                tax_lines = []
                for rate, base in sales_by_rate.items():
                    if inter:
                        tax_lines.append(("Output IGST", -r2(base * rate / 100)))
                    else:
                        half = r2(base * rate / 200)
                        tax_lines += [("Output CGST", -half), ("Output SGST", -half)]
                taxable = sum(sales_by_rate.values())
                tax = -sum(t[1] for t in tax_lines)
                gross = taxable + tax
                total = gross.quantize(D("1"), rounding=ROUND_HALF_UP)
                ro = total - gross
                inv_no[fy] += 1
                num = f"VBT/{fy}/{inv_no[fy]:04d}"
                lines = [(name, total, [(num, "New Ref", total, cdays)])] + [(t, a, []) for t, a in self._merge(tax_lines)]
                lines += [(f"Sales GST {r}%", -b, []) for r, b in sales_by_rate.items()]
                if ro:
                    lines.append(("Round Off", -ro, []))
                self.V(inv_date, "Sales GST", num, name, lines, stock, invoice=True, narration=f"Dealer order PO-{rnd.randint(1000, 9999)}")
                open_bills[name].append([num, inv_date, total, None])
                # occasional sales return
                if rnd.random() < 0.04 and inv_date + dt.timedelta(days=7) <= self.today:
                    cn_no[fy] += 1
                    base = r2(taxable * D("0.1"))
                    rate = next(iter(sales_by_rate))
                    t = r2(base * rate / 100)
                    ret = (base + t).quantize(D("1"), rounding=ROUND_HALF_UP)
                    ro2 = ret - base - t
                    cl = [("Sales Returns", base, []), (name, -ret, [(num, "Agst Ref", -ret, 0)])]
                    cl += [("Output IGST", t, [])] if inter else [("Output CGST", t / 2, []), ("Output SGST", t / 2, [])]
                    if ro2:
                        cl.append(("Round Off", ro2, []))
                    self.V(inv_date + dt.timedelta(days=7), "Credit Note", f"CN/{fy}/{cn_no[fy]:03d}", name, cl,
                           narration="Damaged packs returned")
                    open_bills[name][-1][2] -= ret
            # ---- receipts against older bills
            for name, bills in open_bills.items():
                for b in bills:
                    if b[2] <= 0:
                        continue
                    if b[3] is None:  # decide once when this bill will be paid
                        cdays = next(x[3] for x in DEALERS if x[0] == name)
                        delay = cdays + rnd.randint(-12, 20) + (75 if name in SLOW_PAYERS else 0)
                        b[3] = max(b[1] + dt.timedelta(days=delay), d)
                    pay_on = b[3]
                    if not (d <= pay_on <= last):
                        continue
                    partial = rnd.random() < 0.15
                    amount = r2(b[2] * D("0.6")).quantize(D("1")) if partial else b[2]
                    b[3] = pay_on + dt.timedelta(days=30) if partial else None
                    rec_no[fy] += 1
                    bank = "Indian Bank - Collections A/c" if rnd.random() < 0.7 else "HDFC Bank - Current A/c"
                    self.V(pay_on, "Bank Receipt", f"R/{fy}/{rec_no[fy]:04d}", name,
                           [(bank, amount, []), (name, -amount, [(b[0], "Agst Ref", -amount, 0)])],
                           narration=f"NEFT UTR{rnd.randint(10**9, 10**10)}")
                    b[2] -= amount
            # ---- purchases
            for _ in range(int(rnd.randint(6, 9) * SEASON[d.month])):
                sup = rnd.choice(SUPPLIERS[:4])
                bd = d + dt.timedelta(days=rnd.randrange(days))
                base = r2(D(rnd.randint(40000, 180000)) * growth)
                rate = 18 if "Packaging" in sup[0] else 5
                half = r2(base * rate / 200)
                total = (base + 2 * half).quantize(D("1"), rounding=ROUND_HALF_UP)
                ro = total - base - 2 * half
                bill_no = f"{sup[0][:3].upper()}/{bd:%y%m}/{rnd.randint(100, 999)}"
                lines = [(f"Purchase GST {rate}%", base, []), ("Input CGST", half, []), ("Input SGST", half, []),
                         (sup[0], -total, [(bill_no, "New Ref", -total, 30)])]
                if ro:
                    lines.append(("Round Off", ro, []))
                self.V(bd, "Purchase", bill_no, sup[0], lines, narration=", ".join(sup[2]))
                sup_bills[sup[0]].append([bill_no, bd, total])
            # ---- supplier payments
            for sname, bills in sup_bills.items():
                for b in bills:
                    pay_on = b[1] + dt.timedelta(days=30 + rnd.randint(-5, 15))
                    if b[2] > 0 and d <= pay_on <= last:
                        self.V(pay_on, "Payment", "", sname, [(sname, b[2], [(b[0], "Agst Ref", b[2], 0)]),
                                                              ("HDFC Bank - Current A/c", -b[2], [])], narration="NEFT")
                        b[2] = D(0)
            # ---- expenses
            for name, group, base, gst in EXPENSES:
                if name in ("Salaries & Wages", "Factory Wages") and m_end > self.today:
                    continue
                ed = m_end if name in ("Salaries & Wages", "Factory Wages") else d + dt.timedelta(days=rnd.randrange(days))
                spike = D("2.6") if (name == "Repairs & Maintenance" and d.month == 10 and d.year == 2026) else D(1)
                a = r2(D(base) * D(str(round(rnd.uniform(0.75, 1.25), 3))) * spike * (D(days) / 30 if name not in ("Salaries & Wages", "Factory Wages", "Rent") else 1))
                src = "Cash" if a < 8000 else "HDFC Bank - Current A/c"
                lines = [(name, a, [])]
                total = a
                if gst:
                    half = r2(a * gst / 200)
                    lines += [("Input CGST", half, []), ("Input SGST", half, [])]
                    total += 2 * half
                lines.append((src, -total, []))
                self.V(ed, "Payment", "", "", lines, narration=f"{name} - {ed:%B}")
            # ---- cash top up, GST payment, interest
            if d + dt.timedelta(days=2) <= self.today:
                self.V(d + dt.timedelta(days=2), "Contra", "", "", [("Cash", D(20000), []), ("HDFC Bank - Current A/c", D(-20000), [])],
                       narration="Cash withdrawn for petty expenses")
            sweep_day = d + dt.timedelta(days=4)
            if sweep_day <= self.today:
                coll = self.balance("Indian Bank - Collections A/c", sweep_day) - 300000
                if coll > 0:
                    coll = coll.quantize(D("1000"))
                    self.V(sweep_day, "Contra", "", "", [("HDFC Bank - Current A/c", coll, []),
                                                         ("Indian Bank - Collections A/c", -coll, [])],
                           narration="Transfer from collections account")
            if d.month in (6, 9, 12, 3) and m_end <= self.today:
                self.V(m_end, "Receipt", "", "", [("HDFC Bank - Current A/c", D(4200), []), ("Interest Received", D(-4200), [])],
                       narration="FD interest")
            d = m_end + dt.timedelta(days=1)

        # one cancelled and one optional voucher — must be ignored by the dashboard
        self.V(self.today - dt.timedelta(days=3), "Sales GST", "VBT/26-27/CXL", "Kongu Farm Inputs",
               [("Kongu Farm Inputs", D(99999), []), ("Sales GST 5%", D(-99999), [])], cancelled=True)
        self.V(self.today, "Sales GST", "", "Kongu Farm Inputs",
               [("Kongu Farm Inputs", D(50000), []), ("Sales GST 5%", D(-50000), [])], optional=True)

    @staticmethod
    def _merge(lines):
        out: dict[str, Decimal] = {}
        for k, v in lines:
            out[k] = out.get(k, D(0)) + v
        return list(out.items())

    # ---- answers -----------------------------------------------------------------------------
    def balance(self, ledger: str, upto: dt.date) -> Decimal:
        b = self.ledgers[ledger]["opening_dr"]
        for v in self.vouchers:
            if v["cancelled"] or v["optional"] or v["date"] > upto:
                continue
            for name, dr, *_ in v["lines"]:
                if name == ledger:
                    b += dr
        return b

    def stock_value(self, on: dt.date) -> Decimal:
        months = (on.year - 2025) * 12 + on.month - 4
        return r2(D(1850000) + D(months * 21000) + D(180000) * (D(str(SEASON[on.month])) - 1))


def xml_voucher(v: dict) -> str:
    parts = [f'<VOUCHER REMOTEID="{v["guid"]}" VCHTYPE="{escape(v["type"])}" ACTION="Create">',
             f"<DATE>{v['date']:%Y%m%d}</DATE><GUID>{v['guid']}</GUID><ALTERID> {v['alter']}</ALTERID>",
             f"<VOUCHERTYPENAME>{escape(v['type'])}</VOUCHERTYPENAME><VOUCHERNUMBER>{escape(v['number'])}</VOUCHERNUMBER>",
             f"<PARTYLEDGERNAME>{escape(v['party'])}</PARTYLEDGERNAME>",
             f"<NARRATION>{escape(v['narration'])}&#4;</NARRATION>",  # Tally really does send odd characters
             f"<ISCANCELLED>{'Yes' if v['cancelled'] else 'No'}</ISCANCELLED><ISOPTIONAL>{'Yes' if v['optional'] else 'No'}</ISOPTIONAL>",
             f"<ISINVOICE>{'Yes' if v['invoice'] else 'No'}</ISINVOICE>"]
    in_stock = {s[5] for s in v["stock"]}

    def ledger_xml(tag, name, dr, bills):
        bx = "".join(f"<BILLALLOCATIONS.LIST><NAME>{escape(b[0])}</NAME><BILLTYPE>{b[1]}</BILLTYPE>"
                     f"<BILLCREDITPERIOD>{b[3]} Days</BILLCREDITPERIOD><AMOUNT>{amt(b[2])}</AMOUNT></BILLALLOCATIONS.LIST>"
                     for b in bills)
        return (f"<{tag}><LEDGERNAME>{escape(name)}</LEDGERNAME><ISDEEMEDPOSITIVE>{'Yes' if dr > 0 else 'No'}</ISDEEMEDPOSITIVE>"
                f"<AMOUNT>{amt(dr)}</AMOUNT>{bx}</{tag}>")

    if v["invoice"]:
        # invoice style: party + taxes in LEDGERENTRIES, sales ledger inside each stock line
        for name, dr, bills in v["lines"]:
            if name not in in_stock:
                parts.append(ledger_xml("LEDGERENTRIES.LIST", name, dr, bills))
        for item, qty, unit, rate, value, ledger in v["stock"]:
            parts.append(f"<ALLINVENTORYENTRIES.LIST><STOCKITEMNAME>{escape(item)}</STOCKITEMNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>"
                         f"<RATE>{rate:.2f}/{unit}</RATE><AMOUNT>{value:.2f}</AMOUNT><ACTUALQTY> {qty} {unit}</ACTUALQTY>"
                         f"<BILLEDQTY> {qty} {unit}</BILLEDQTY>"
                         f"<ACCOUNTINGALLOCATIONS.LIST><LEDGERNAME>{escape(ledger)}</LEDGERNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>"
                         f"<AMOUNT>{value:.2f}</AMOUNT></ACCOUNTINGALLOCATIONS.LIST></ALLINVENTORYENTRIES.LIST>")
    else:
        for name, dr, bills in v["lines"]:
            parts.append(ledger_xml("ALLLEDGERENTRIES.LIST", name, dr, bills))
    parts.append("</VOUCHER>")
    return "".join(parts)


def envelope(body: str) -> str:
    return f'<ENVELOPE><BODY><DATA><COLLECTION>{body}</COLLECTION></DATA></BODY></ENVELOPE>'


def make_handler(book: Book):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):  # noqa: N802
            req = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
            typ = (re.search(r"<TYPE>(\w+)</TYPE>\s*(?:<NATIVEMETHOD|<FETCH)", req) or re.search(r'<COLLECTION[^>]*><TYPE>(\w+)</TYPE>', req)).group(1)
            to = re.search(r"<SVTODATE>(\d{8})</SVTODATE>", req)
            upto = dt.datetime.strptime(to.group(1), "%Y%m%d").date() if to else book.today
            if typ == "Company":
                body = (f'<COMPANY NAME="{escape(COMPANY)}"><GUID>{COMPANY_GUID}</GUID><STARTINGFROM>20250401</STARTINGFROM>'
                        f"<BOOKSFROM>20250401</BOOKSFROM><ALTVCHID>{book.alter}</ALTVCHID><ALTMSTID>412</ALTMSTID>"
                        f"<STATENAME>Tamil Nadu</STATENAME></COMPANY>")
            elif typ == "Group":
                body = "".join(f'<GROUP NAME="{escape(n)}"><PARENT>{escape(p)}</PARENT></GROUP>' for n, p in GROUPS)
            elif typ == "VoucherType":
                vt = [("Sales", ""), ("Sales GST", "Sales"), ("Purchase", ""), ("Receipt", ""), ("Bank Receipt", "Receipt"),
                      ("Payment", ""), ("Contra", ""), ("Journal", ""), ("Credit Note", ""), ("Debit Note", "")]
                body = "".join(f'<VOUCHERTYPE NAME="{n}"><PARENT>{p}</PARENT></VOUCHERTYPE>' for n, p in vt)
            elif typ == "Ledger":
                body = "".join(
                    f'<LEDGER NAME="{escape(l["name"])}"><PARENT>{escape(l["parent"])}</PARENT><GUID>{l["guid"]}</GUID>'
                    f'<OPENINGBALANCE>{amt(l["opening_dr"])}</OPENINGBALANCE><CLOSINGBALANCE>{amt(book.balance(l["name"], upto))}</CLOSINGBALANCE>'
                    f'<BILLCREDITPERIOD>{l.get("credit_days", 0)} Days</BILLCREDITPERIOD><PARTYGSTIN>{l.get("gstin", "")}</PARTYGSTIN>'
                    f'<LEDSTATENAME>{escape(l.get("state", ""))}</LEDSTATENAME><ISBILLWISEON>{"Yes" if l.get("bill_wise") else "No"}</ISBILLWISEON></LEDGER>'
                    for l in book.ledgers.values())
            elif typ == "StockItem":
                body = (f'<STOCKITEM NAME="All stock"><CLOSINGVALUE>{amt(book.stock_value(upto))}</CLOSINGVALUE></STOCKITEM>')
            elif typ == "Voucher":
                vs = book.vouchers
                m = re.search(r"\$AlterID &gt; (\d+)", req) or re.search(r"\$AlterID > (\d+)", req)
                if m:
                    vs = [v for v in vs if v["alter"] > int(m.group(1))]
                m = re.search(r'\$Date &gt;= \$\$Date:&quot;([\w-]+)&quot; AND \$Date &lt;= \$\$Date:&quot;([\w-]+)&quot;', req)
                if m:
                    a, b = (dt.datetime.strptime(x, "%d-%b-%Y").date() for x in m.groups())
                    vs = [v for v in vs if a <= v["date"] <= b]
                body = "".join(xml_voucher(v) for v in vs)
            else:
                body = ""
            out = envelope(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today())
    a = ap.parse_args()
    book = Book(a.today)
    print(f"Pretend Tally on http://localhost:{a.port} — {len(book.vouchers)} entries, {len(book.ledgers)} ledgers")
    ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(book)).serve_forever()


if __name__ == "__main__":
    main()
