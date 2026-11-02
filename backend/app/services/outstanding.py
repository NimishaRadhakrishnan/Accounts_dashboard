"""Receivables / payables, ageing, party statements, bank books."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import ZERO, D
from app.models import (BankAccount, ContraEntry, CreditNote, DebitNote, Expense, JournalEntry, JournalLine, Party,
                        Payment, PurchaseBill, Receipt, SalesInvoice)
from app.services import ledger
from app.services.docs_common import purchase_settled, sales_settled

BUCKETS = [("not_due", "Not yet due"), ("d0_30", "1–30 days"), ("d31_60", "31–60 days"),
           ("d61_90", "61–90 days"), ("d90_plus", "Over 90 days")]


def bucket_for(overdue_days: int) -> str:
    if overdue_days <= 0:
        return "not_due"
    if overdue_days <= 30:
        return "d0_30"
    if overdue_days <= 60:
        return "d31_60"
    if overdue_days <= 90:
        return "d61_90"
    return "d90_plus"


def _open_items(db: Session, kind: str, today: date, party_id: int | None = None) -> list[dict]:
    model = SalesInvoice if kind == "receivable" else PurchaseBill
    q = select(model).where(model.status == "posted")
    if party_id:
        q = q.where(model.party_id == party_id)
    docs = db.scalars(q).all()
    settled = (sales_settled if kind == "receivable" else purchase_settled)(db, [d.id for d in docs])
    rows = []
    for d in docs:
        bal = d.grand_total - settled[d.id]
        if bal <= 0:
            continue
        overdue = (today - d.due_date).days
        rows.append({
            "id": d.id, "number": d.number, "date": d.date, "due_date": d.due_date,
            "supplier_bill_no": getattr(d, "supplier_bill_no", None),
            "party_id": d.party_id, "party_name": d.party.name, "party_code": d.party.code,
            "total": d.grand_total, "settled": settled[d.id], "balance": bal,
            "overdue_days": max(overdue, 0), "bucket": bucket_for(overdue), "is_opening": d.is_opening,
        })
    rows.sort(key=lambda r: (r["due_date"], r["number"]))
    return rows


def _advances(db: Session, kind: str) -> dict[int, Decimal]:
    """Unallocated money per party (receipts not matched to invoices, payments not matched to bills)."""
    model = Receipt if kind == "receivable" else Payment
    out: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for v in db.scalars(select(model).where(model.status == "posted")):
        free = v.amount - sum((a.amount for a in v.allocations), ZERO)
        if free > 0:
            out[v.party_id] += free
    return out


def ageing(db: Session, kind: str, today: date | None = None) -> dict:
    today = today or date.today()
    items = _open_items(db, kind, today)
    advances = _advances(db, kind)
    parties: dict[int, dict] = {}
    totals = {k: ZERO for k, _ in BUCKETS}
    for it in items:
        p = parties.setdefault(it["party_id"], {
            "party_id": it["party_id"], "party_name": it["party_name"], "party_code": it["party_code"],
            **{k: ZERO for k, _ in BUCKETS}, "gross": ZERO, "advance": ZERO, "net": ZERO,
            "oldest_overdue_days": 0, "open_count": 0})
        p[it["bucket"]] += it["balance"]
        p["gross"] += it["balance"]
        p["open_count"] += 1
        p["oldest_overdue_days"] = max(p["oldest_overdue_days"], it["overdue_days"])
        totals[it["bucket"]] += it["balance"]
    for pid, adv in advances.items():
        if pid not in parties:
            party = db.get(Party, pid)
            parties[pid] = {"party_id": pid, "party_name": party.name, "party_code": party.code,
                            **{k: ZERO for k, _ in BUCKETS}, "gross": ZERO, "advance": ZERO, "net": ZERO,
                            "oldest_overdue_days": 0, "open_count": 0}
        parties[pid]["advance"] = adv
    for p in parties.values():
        p["net"] = p["gross"] - p["advance"]
        party = db.get(Party, p["party_id"])
        p["credit_limit"] = party.credit_limit
        p["over_limit"] = bool(party.credit_limit and p["net"] > party.credit_limit)
    gross = sum(totals.values(), ZERO)
    adv_total = sum(advances.values(), ZERO)
    return {
        "kind": kind, "as_of": today, "buckets": [{"key": k, "label": lbl, "amount": totals[k]} for k, lbl in BUCKETS],
        "gross": gross, "advances": adv_total, "net": gross - adv_total,
        "parties": sorted(parties.values(), key=lambda p: (-p["oldest_overdue_days"], -p["net"])),
        "items": items,
    }


def party_items(db: Session, party_id: int, kind: str, today: date | None = None) -> list[dict]:
    return _open_items(db, kind, today or date.today(), party_id)


# ---------- Statements ----------
_SOURCE_MODELS = {
    "sales_invoice": SalesInvoice, "credit_note": CreditNote, "purchase_bill": PurchaseBill,
    "debit_note": DebitNote, "receipt": Receipt, "payment": Payment, "expense": Expense, "contra": ContraEntry,
}
_SOURCE_LABEL = {
    "sales_invoice": "Sales Invoice", "credit_note": "Credit Note", "purchase_bill": "Purchase Bill",
    "debit_note": "Debit Note", "receipt": "Receipt", "payment": "Payment", "expense": "Expense",
    "contra": "Transfer", "bank_opening": "Opening Balance",
}


def _numbers(db: Session, entries: list[JournalEntry]) -> dict[tuple[str, int], str]:
    want: dict[str, set[int]] = defaultdict(set)
    for e in entries:
        if e.source_type in _SOURCE_MODELS:
            want[e.source_type].add(e.source_id)
    out = {}
    for st, ids in want.items():
        m = _SOURCE_MODELS[st]
        for i, n in db.execute(select(m.id, m.number).where(m.id.in_(ids))):
            out[(st, i)] = n or "(draft)"
    return out


def _statement(db: Session, account_code: str, start: date, end: date, *, party_id=None, bank_account_id=None,
               sign: int = 1) -> dict:
    opening = ledger.balance(db, account_code, party_id=party_id, bank_account_id=bank_account_id,
                             as_of=date.fromordinal(start.toordinal() - 1)) * sign
    q = (select(JournalLine, JournalEntry).join(JournalEntry)
         .where(JournalLine.account_id == ledger.account_id(db, account_code),
                JournalEntry.date >= start, JournalEntry.date <= end)
         .order_by(JournalEntry.date, JournalEntry.id))
    if party_id is not None:
        q = q.where(JournalLine.party_id == party_id)
    if bank_account_id is not None:
        q = q.where(JournalLine.bank_account_id == bank_account_id)
    pairs = db.execute(q).all()
    nums = _numbers(db, [e for _, e in pairs])
    running = opening
    rows = []
    for ln, e in pairs:
        running += (ln.debit - ln.credit) * sign
        rows.append({"date": e.date, "type": _SOURCE_LABEL.get(e.source_type, e.source_type)
                     + (" (reversal)" if e.is_reversal else ""),
                     "number": nums.get((e.source_type, e.source_id), ""), "narration": e.narration,
                     "debit": D(ln.debit), "credit": D(ln.credit), "balance": running})
    return {"opening": opening, "rows": rows, "closing": running,
            "total_debit": sum((r["debit"] for r in rows), ZERO),
            "total_credit": sum((r["credit"] for r in rows), ZERO)}


def party_statement(db: Session, party_id: int, start: date, end: date) -> dict:
    party = db.get(Party, party_id)
    out = {"party": party}
    if party.is_customer:
        out["receivable"] = _statement(db, ledger.DEBTORS, start, end, party_id=party_id, sign=1)
    if party.is_supplier:
        out["payable"] = _statement(db, ledger.CREDITORS, start, end, party_id=party_id, sign=-1)
    return out


def bank_book(db: Session, bank_id: int, start: date, end: date) -> dict:
    bank = db.get(BankAccount, bank_id)
    return {"bank": bank, **_statement(db, ledger.CASH_BANK, start, end, bank_account_id=bank_id, sign=1)}
