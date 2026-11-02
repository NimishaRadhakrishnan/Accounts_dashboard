"""Financial reports. Each returns a Report that the screen, Excel and PDF exporters all share."""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.money import ZERO, D
from app.models import (Account, BankAccount, CreditNote, DebitNote, Expense, ExpenseCategory, Party, PurchaseBill,
                        SalesInvoice)
from app.services import ledger
from app.services.dashboard import period_figures
from app.services.outstanding import BUCKETS, ageing, bank_book, party_statement


@dataclass
class Column:
    key: str
    label: str
    kind: str = "text"  # text | money | date | number | pct
    width: int = 14


@dataclass
class Report:
    key: str
    title: str
    subtitle: str
    columns: list[Column]
    rows: list[dict]
    totals: dict | None = None
    notes: list[str] = field(default_factory=list)
    landscape: bool = False


def _period(start: date, end: date) -> str:
    if end < start:
        raise DomainError("End date is before start date.")
    return f"{start:%d %b %Y} to {end:%d %b %Y}"


def _sum(rows, *keys) -> dict:
    return {k: sum((D(r.get(k)) for r in rows), ZERO) for k in keys}


MONEY_TAX_COLS = [Column("taxable", "Taxable", "money"), Column("cgst", "CGST", "money", 12),
                  Column("sgst", "SGST", "money", 12), Column("igst", "IGST", "money", 12),
                  Column("round_off", "Round off", "money", 10), Column("total", "Total", "money")]


def sales_register(db: Session, start: date, end: date) -> Report:
    rows = []
    for inv in db.scalars(select(SalesInvoice).where(SalesInvoice.status == "posted", SalesInvoice.is_opening.is_(False),
                                                     SalesInvoice.date >= start, SalesInvoice.date <= end)
                          .order_by(SalesInvoice.date, SalesInvoice.number)):
        rows.append({"date": inv.date, "number": inv.number, "party": inv.party.name, "gstin": inv.party.gstin or "",
                     "state": inv.party.state_name, "taxable": inv.taxable_total, "cgst": inv.cgst_total,
                     "sgst": inv.sgst_total, "igst": inv.igst_total, "round_off": inv.round_off,
                     "total": inv.grand_total})
    for cn in db.scalars(select(CreditNote).where(CreditNote.status == "posted", CreditNote.date >= start,
                                                  CreditNote.date <= end).order_by(CreditNote.date)):
        rows.append({"date": cn.date, "number": cn.number, "party": cn.party.name + " (credit note)",
                     "gstin": cn.party.gstin or "", "state": cn.party.state_name, "taxable": -cn.taxable_total,
                     "cgst": -cn.cgst_total, "sgst": -cn.sgst_total, "igst": -cn.igst_total,
                     "round_off": -cn.round_off, "total": -cn.grand_total})
    rows.sort(key=lambda r: (r["date"], r["number"]))
    return Report("sales-register", "Sales Register", _period(start, end),
                  [Column("date", "Date", "date", 11), Column("number", "Invoice No", width=15),
                   Column("party", "Dealer", width=30), Column("gstin", "GSTIN", width=17),
                   Column("state", "State", width=12), *MONEY_TAX_COLS],
                  rows, _sum(rows, "taxable", "cgst", "sgst", "igst", "round_off", "total"),
                  ["Credit notes are shown as negative rows. Cancelled invoices are excluded."], landscape=True)


def purchase_register(db: Session, start: date, end: date) -> Report:
    rows = []
    for b in db.scalars(select(PurchaseBill).where(PurchaseBill.status == "posted", PurchaseBill.is_opening.is_(False),
                                                   PurchaseBill.date >= start, PurchaseBill.date <= end)):
        rows.append({"date": b.date, "number": b.number, "supplier_bill_no": b.supplier_bill_no, "party": b.party.name,
                     "gstin": b.party.gstin or "", "taxable": b.taxable_total, "cgst": b.cgst_total,
                     "sgst": b.sgst_total, "igst": b.igst_total, "round_off": b.round_off, "total": b.grand_total})
    for dn in db.scalars(select(DebitNote).where(DebitNote.status == "posted", DebitNote.date >= start,
                                                 DebitNote.date <= end)):
        rows.append({"date": dn.date, "number": dn.number, "supplier_bill_no": dn.bill.supplier_bill_no,
                     "party": dn.party.name + " (debit note)", "gstin": dn.party.gstin or "",
                     "taxable": -dn.taxable_total, "cgst": -dn.cgst_total, "sgst": -dn.sgst_total,
                     "igst": -dn.igst_total, "round_off": -dn.round_off, "total": -dn.grand_total})
    rows.sort(key=lambda r: (r["date"], r["number"]))
    return Report("purchase-register", "Purchase Register", _period(start, end),
                  [Column("date", "Date", "date", 11), Column("number", "Our Ref", width=15),
                   Column("supplier_bill_no", "Supplier Bill", width=15), Column("party", "Supplier", width=28),
                   Column("gstin", "GSTIN", width=17), *MONEY_TAX_COLS],
                  rows, _sum(rows, "taxable", "cgst", "sgst", "igst", "round_off", "total"),
                  ["Debit notes are shown as negative rows."], landscape=True)


def gst_summary(db: Session, start: date, end: date) -> Report:
    out = defaultdict(lambda: {"taxable": ZERO, "cgst": ZERO, "sgst": ZERO, "igst": ZERO})
    inp = defaultdict(lambda: {"taxable": ZERO, "cgst": ZERO, "sgst": ZERO, "igst": ZERO})

    def add(bucket, lines, sign):
        for ln in lines:
            b = bucket[D(ln.gst_rate)]
            b["taxable"] += sign * ln.taxable
            b["cgst"] += sign * ln.cgst
            b["sgst"] += sign * ln.sgst
            b["igst"] += sign * ln.igst

    for inv in db.scalars(select(SalesInvoice).where(SalesInvoice.status == "posted", SalesInvoice.is_opening.is_(False),
                                                     SalesInvoice.date >= start, SalesInvoice.date <= end)):
        add(out, inv.lines, 1)
    for cn in db.scalars(select(CreditNote).where(CreditNote.status == "posted", CreditNote.date >= start,
                                                  CreditNote.date <= end)):
        add(out, cn.lines, -1)
    for b in db.scalars(select(PurchaseBill).where(PurchaseBill.status == "posted", PurchaseBill.is_opening.is_(False),
                                                   PurchaseBill.date >= start, PurchaseBill.date <= end)):
        add(inp, b.lines, 1)
    for dn in db.scalars(select(DebitNote).where(DebitNote.status == "posted", DebitNote.date >= start,
                                                 DebitNote.date <= end)):
        add(inp, dn.lines, -1)
    for ex in db.scalars(select(Expense).where(Expense.status == "posted", Expense.gst_claimable.is_(True),
                                               Expense.date >= start, Expense.date <= end)):
        b = inp[D(ex.gst_rate)]
        b["taxable"] += ex.amount
        b["cgst"] += ex.cgst
        b["sgst"] += ex.sgst
        b["igst"] += ex.igst

    rows = []
    for section, data in (("Output tax (sales)", out), ("Input tax credit (purchases + expenses)", inp)):
        for rate in sorted(data):
            v = data[rate]
            rows.append({"section": section, "rate": rate, **v, "tax": v["cgst"] + v["sgst"] + v["igst"]})
    o = _sum([r for r in rows if r["section"].startswith("Output")], "taxable", "cgst", "sgst", "igst", "tax")
    i = _sum([r for r in rows if r["section"].startswith("Input")], "taxable", "cgst", "sgst", "igst", "tax")
    rows.append({"section": "Total output tax", "rate": None, **o})
    rows.append({"section": "Total input tax credit", "rate": None, **i})
    net = {k: o[k] - i[k] for k in ("cgst", "sgst", "igst", "tax")}
    rows.append({"section": "Net (output − input)", "rate": None, "taxable": None, **net})
    return Report("gst-summary", "GST Summary", _period(start, end),
                  [Column("section", "Section", width=36), Column("rate", "GST %", "pct", 8),
                   Column("taxable", "Taxable", "money"), Column("cgst", "CGST", "money"),
                   Column("sgst", "SGST", "money"), Column("igst", "IGST", "money"),
                   Column("tax", "Total tax", "money")], rows, None,
                  ["For working only. Final GSTR-1 / GSTR-3B filing stays in Tally / with the CA.",
                   "Cross-utilisation of IGST/CGST/SGST credit is not applied here — the net row is a simple difference.",
                   "Input credit eligibility (e.g. blocked credits) must be confirmed by the CA."])


def hsn_summary(db: Session, start: date, end: date) -> Report:
    agg = defaultdict(lambda: {"qty": ZERO, "taxable": ZERO, "cgst": ZERO, "sgst": ZERO, "igst": ZERO})
    for inv in db.scalars(select(SalesInvoice).where(SalesInvoice.status == "posted", SalesInvoice.is_opening.is_(False),
                                                     SalesInvoice.date >= start, SalesInvoice.date <= end)):
        for ln in inv.lines:
            a = agg[(ln.hsn_code or "-", ln.unit, D(ln.gst_rate))]
            a["qty"] += ln.qty
            for k in ("taxable", "cgst", "sgst", "igst"):
                a[k] += getattr(ln, k)
    for cn in db.scalars(select(CreditNote).where(CreditNote.status == "posted", CreditNote.date >= start,
                                                  CreditNote.date <= end)):
        for ln in cn.lines:
            a = agg[(ln.hsn_code or "-", ln.unit, D(ln.gst_rate))]
            a["qty"] -= ln.qty
            for k in ("taxable", "cgst", "sgst", "igst"):
                a[k] -= getattr(ln, k)
    rows = [{"hsn": h, "unit": u, "rate": r, **v, "total": v["taxable"] + v["cgst"] + v["sgst"] + v["igst"]}
            for (h, u, r), v in sorted(agg.items())]
    return Report("hsn-summary", "HSN-wise Sales Summary", _period(start, end),
                  [Column("hsn", "HSN", width=10), Column("unit", "Unit", width=8), Column("rate", "GST %", "pct", 8),
                   Column("qty", "Quantity", "number"), Column("taxable", "Taxable", "money"),
                   Column("cgst", "CGST", "money"), Column("sgst", "SGST", "money"), Column("igst", "IGST", "money"),
                   Column("total", "Total", "money")],
                  rows, _sum(rows, "taxable", "cgst", "sgst", "igst", "total"))


def expense_report(db: Session, start: date, end: date) -> Report:
    rows = []
    for ex in db.scalars(select(Expense).where(Expense.status == "posted", Expense.date >= start, Expense.date <= end)
                         .order_by(Expense.date, Expense.number)):
        rows.append({"date": ex.date, "number": ex.number, "category": ex.category.name, "payee": ex.payee,
                     "description": ex.description, "paid_from": ex.bank_account.name, "amount": ex.amount,
                     "gst": ex.cgst + ex.sgst + ex.igst, "total": ex.total})
    by_cat = defaultdict(lambda: ZERO)
    for r in rows:
        by_cat[r["category"]] += r["total"]
    notes = ["Category totals: " + "; ".join(f"{k} ₹{v:,.2f}" for k, v in sorted(by_cat.items(), key=lambda x: -x[1]))] \
        if by_cat else []
    return Report("expense-report", "Expense Report", _period(start, end),
                  [Column("date", "Date", "date", 11), Column("number", "No", width=14),
                   Column("category", "Category", width=18), Column("payee", "Paid to", width=22),
                   Column("description", "Description", width=30), Column("paid_from", "Paid from", width=16),
                   Column("amount", "Amount", "money"), Column("gst", "GST", "money", 11),
                   Column("total", "Total", "money")],
                  rows, _sum(rows, "amount", "gst", "total"), notes, landscape=True)


def expense_by_category(db: Session, start: date, end: date) -> Report:
    rows = []
    for cat in db.scalars(select(ExpenseCategory).order_by(ExpenseCategory.name)):
        amt = ledger.balance(db, cat.account.code, from_date=start, as_of=end)
        if amt:
            rows.append({"category": cat.name, "amount": amt})
    rows.sort(key=lambda r: -r["amount"])
    total = sum((r["amount"] for r in rows), ZERO)
    for r in rows:
        r["share"] = (r["amount"] / total * 100).quantize(D("0.1")) if total else ZERO
    return Report("expense-by-category", "Expenses by Category", _period(start, end),
                  [Column("category", "Category", width=30), Column("amount", "Amount", "money"),
                   Column("share", "Share %", "pct", 10)], rows, {"amount": total})


def _ageing_report(db: Session, kind: str, today: date) -> Report:
    a = ageing(db, kind, today)
    rows = [{"party": p["party_name"], **{k: p[k] for k, _ in BUCKETS}, "gross": p["gross"],
             "advance": p["advance"], "net": p["net"]} for p in a["parties"]]
    who = "Dealer" if kind == "receivable" else "Supplier"
    title = "Receivables Ageing" if kind == "receivable" else "Payables Ageing"
    return Report(f"{kind}-ageing", title, f"As on {today:%d %b %Y} (days past due date)",
                  [Column("party", who, width=30), *[Column(k, lbl, "money") for k, lbl in BUCKETS],
                   Column("gross", "Outstanding", "money"), Column("advance", "Advance", "money", 12),
                   Column("net", "Net", "money")],
                  rows, _sum(rows, *[k for k, _ in BUCKETS], "gross", "advance", "net"), landscape=True)


def receivables_ageing(db: Session, today: date) -> Report:
    return _ageing_report(db, "receivable", today)


def payables_ageing(db: Session, today: date) -> Report:
    return _ageing_report(db, "payable", today)


STATEMENT_COLS = [Column("date", "Date", "date", 11), Column("type", "Type", width=16),
                  Column("number", "No", width=15), Column("narration", "Particulars", width=44),
                  Column("debit", "Debit", "money"), Column("credit", "Credit", "money"),
                  Column("balance", "Balance", "money")]


def party_ledger(db: Session, party_id: int, start: date, end: date) -> Report:
    party = db.get(Party, party_id)
    if not party:
        raise DomainError("Party not found.")
    st = party_statement(db, party_id, start, end)
    rows, notes = [], []
    for kind, label in (("receivable", "Receivable (positive = they owe us)"),
                        ("payable", "Payable (positive = we owe them)")):
        if kind not in st:
            continue
        s = st[kind]
        rows.append({"date": start, "type": "Opening", "number": "", "narration": label, "debit": None,
                     "credit": None, "balance": s["opening"]})
        rows.extend(s["rows"])
        rows.append({"date": end, "type": "Closing", "number": "", "narration": "", "debit": s["total_debit"],
                     "credit": s["total_credit"], "balance": s["closing"]})
    return Report("party-ledger", f"Ledger — {party.name}", _period(start, end), STATEMENT_COLS, rows, None,
                  notes, landscape=True)


def bank_book_report(db: Session, bank_id: int, start: date, end: date) -> Report:
    bank = db.get(BankAccount, bank_id)
    if not bank:
        raise DomainError("Bank / cash account not found.")
    s = bank_book(db, bank_id, start, end)
    rows = [{"date": start, "type": "Opening", "number": "", "narration": "", "debit": None, "credit": None,
             "balance": s["opening"]}, *s["rows"],
            {"date": end, "type": "Closing", "number": "", "narration": "", "debit": s["total_debit"],
             "credit": s["total_credit"], "balance": s["closing"]}]
    cols = [c if c.key not in ("debit", "credit") else Column(c.key, "Money in" if c.key == "debit" else "Money out",
                                                               "money") for c in STATEMENT_COLS]
    return Report("bank-book", f"{'Cash' if bank.kind == 'cash' else 'Bank'} Book — {bank.name}",
                  _period(start, end), cols, rows, None, landscape=True)


def profit_and_loss(db: Session, start: date, end: date) -> Report:
    f = period_figures(db, start, end)
    rows = [{"particular": "Sales (net of returns, excl. GST)", "amount": f["sales"]},
            {"particular": "Less: Purchases (net of returns, excl. GST)", "amount": -f["purchases"]}]
    gross = f["sales"] - f["purchases"]
    rows.append({"particular": "Gross margin (before stock adjustment)", "amount": gross, "bold": True})
    exp_total = ZERO
    for cat in db.scalars(select(ExpenseCategory).order_by(ExpenseCategory.name)):
        amt = ledger.balance(db, cat.account.code, from_date=start, as_of=end)
        if amt:
            rows.append({"particular": f"Less: {cat.name}", "amount": -amt})
            exp_total += amt
    ro = ledger.balance(db, ledger.ROUND_OFF, from_date=start, as_of=end)
    if ro:
        rows.append({"particular": "Less: Round off (net)", "amount": -ro})
    net = gross - exp_total - ro
    rows.append({"particular": "Net result (before stock, depreciation & tax)", "amount": net, "bold": True})
    return Report("profit-loss", "Profit & Loss Summary", _period(start, end),
                  [Column("particular", "Particulars", width=50), Column("amount", "Amount (₹)", "money", 18)], rows,
                  None, ["Management summary only. Opening/closing stock, depreciation, provisions and income tax "
                         "are not included — final accounts stay in Tally with the CA."])


def trial_balance_report(db: Session, start: date, end: date) -> Report:
    rows = []
    names = {a.code: a.name for a in db.scalars(select(Account))}
    for r in ledger.trial_balance(db, start, end):
        closing = r["closing"]
        rows.append({"account": names[r["code"]], "type": r["type"].capitalize(), "opening": r["opening"],
                     "debit": r["debit"], "credit": r["credit"],
                     "closing_dr": closing if closing > 0 else ZERO, "closing_cr": -closing if closing < 0 else ZERO})
    return Report("trial-balance", "Trial Balance", _period(start, end),
                  [Column("account", "Account", width=34), Column("type", "Type", width=10),
                   Column("opening", "Opening (Dr+)", "money"), Column("debit", "Debit", "money"),
                   Column("credit", "Credit", "money"), Column("closing_dr", "Closing Dr", "money"),
                   Column("closing_cr", "Closing Cr", "money")],
                  rows, _sum(rows, "debit", "credit", "closing_dr", "closing_cr"),
                  ["Use this to reconcile with Tally: totals of Closing Dr and Closing Cr must be equal."],
                  landscape=True)


CATALOGUE = [
    {"key": "sales-register", "title": "Sales Register", "group": "Sales & Purchases", "needs": "period"},
    {"key": "purchase-register", "title": "Purchase Register", "group": "Sales & Purchases", "needs": "period"},
    {"key": "gst-summary", "title": "GST Summary", "group": "GST", "needs": "period"},
    {"key": "hsn-summary", "title": "HSN-wise Sales Summary", "group": "GST", "needs": "period"},
    {"key": "expense-report", "title": "Expense Report", "group": "Expenses", "needs": "period"},
    {"key": "expense-by-category", "title": "Expenses by Category", "group": "Expenses", "needs": "period"},
    {"key": "receivable-ageing", "title": "Receivables Ageing", "group": "Outstanding", "needs": "as_of"},
    {"key": "payable-ageing", "title": "Payables Ageing", "group": "Outstanding", "needs": "as_of"},
    {"key": "party-ledger", "title": "Party Ledger / Statement", "group": "Ledgers", "needs": "party"},
    {"key": "bank-book", "title": "Cash / Bank Book", "group": "Ledgers", "needs": "bank"},
    {"key": "profit-loss", "title": "Profit & Loss Summary", "group": "Summary", "needs": "period"},
    {"key": "trial-balance", "title": "Trial Balance", "group": "Summary", "needs": "period"},
]


def build(db: Session, key: str, *, start: date | None, end: date | None, as_of: date | None,
          party_id: int | None, bank_id: int | None) -> Report:
    def need_period():
        if not start or not end:
            raise DomainError("Choose a From and To date.")
        return start, end

    if key == "sales-register":
        return sales_register(db, *need_period())
    if key == "purchase-register":
        return purchase_register(db, *need_period())
    if key == "gst-summary":
        return gst_summary(db, *need_period())
    if key == "hsn-summary":
        return hsn_summary(db, *need_period())
    if key == "expense-report":
        return expense_report(db, *need_period())
    if key == "expense-by-category":
        return expense_by_category(db, *need_period())
    if key == "receivable-ageing":
        return receivables_ageing(db, as_of or date.today())
    if key == "payable-ageing":
        return payables_ageing(db, as_of or date.today())
    if key == "party-ledger":
        if not party_id:
            raise DomainError("Choose a dealer or supplier.")
        return party_ledger(db, party_id, *need_period())
    if key == "bank-book":
        if not bank_id:
            raise DomainError("Choose a bank or cash account.")
        return bank_book_report(db, bank_id, *need_period())
    if key == "profit-loss":
        return profit_and_loss(db, *need_period())
    if key == "trial-balance":
        return trial_balance_report(db, *need_period())
    raise DomainError("Unknown report.", 404)


_ = Decimal
