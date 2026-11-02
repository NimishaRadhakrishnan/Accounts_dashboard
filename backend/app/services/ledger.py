"""Double-entry ledger. Every posted voucher creates one balanced journal entry; cancelling or
editing creates a reversing entry. All dashboard and report balances come from journal_lines."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.money import ZERO, D
from app.models import Account, JournalEntry, JournalLine

# System account codes
DEBTORS = "DEBTORS"
CREDITORS = "CREDITORS"
SALES = "SALES"
SALES_RETURNS = "SALES_RETURNS"
PURCHASES = "PURCHASES"
PURCHASE_RETURNS = "PURCHASE_RETURNS"
OUT_CGST, OUT_SGST, OUT_IGST = "OUT_CGST", "OUT_SGST", "OUT_IGST"
IN_CGST, IN_SGST, IN_IGST = "IN_CGST", "IN_SGST", "IN_IGST"
ROUND_OFF = "ROUND_OFF"
CASH_BANK = "CASH_BANK"
OPENING_EQUITY = "OPENING_EQUITY"

SYSTEM_ACCOUNTS = [
    (DEBTORS, "Sundry Debtors (Dealers)", "asset", "Sundry Debtors"),
    (CREDITORS, "Sundry Creditors (Suppliers)", "liability", "Sundry Creditors"),
    (SALES, "Sales", "income", "Sales Account"),
    (SALES_RETURNS, "Sales Returns", "income", "Sales Returns"),
    (PURCHASES, "Purchases", "expense", "Purchase Account"),
    (PURCHASE_RETURNS, "Purchase Returns", "expense", "Purchase Returns"),
    (OUT_CGST, "Output CGST", "liability", "Output CGST"),
    (OUT_SGST, "Output SGST", "liability", "Output SGST"),
    (OUT_IGST, "Output IGST", "liability", "Output IGST"),
    (IN_CGST, "Input CGST", "asset", "Input CGST"),
    (IN_SGST, "Input SGST", "asset", "Input SGST"),
    (IN_IGST, "Input IGST", "asset", "Input IGST"),
    (ROUND_OFF, "Round Off", "expense", "Round Off"),
    (CASH_BANK, "Cash & Bank", "asset", None),
    (OPENING_EQUITY, "Opening Balance Adjustment", "equity", "Opening Balance Difference"),
]


@dataclass
class Leg:
    account_code: str
    amount: Decimal  # positive = debit, negative = credit
    party_id: int | None = None
    bank_account_id: int | None = None


def dr(code: str, amount, **kw) -> Leg:
    return Leg(code, D(amount), **kw)


def cr(code: str, amount, **kw) -> Leg:
    return Leg(code, -D(amount), **kw)


def _account_ids(db: Session) -> dict[str, int]:
    cache = db.info.get("_account_ids")
    if cache is None:
        cache = {a.code: a.id for a in db.scalars(select(Account))}
        db.info["_account_ids"] = cache
    return cache


def account_id(db: Session, code: str) -> int:
    ids = _account_ids(db)
    if code not in ids:
        db.info.pop("_account_ids", None)
        ids = _account_ids(db)
    if code not in ids:
        raise DomainError(f"Ledger account {code} is missing. Run setup.")
    return ids[code]


def post(db: Session, *, on: date, fy_label: str, source_type: str, source_id: int, narration: str,
         legs: list[Leg]) -> JournalEntry:
    legs = [lg for lg in legs if lg.amount != 0]
    total = sum((lg.amount for lg in legs), ZERO)
    if total != 0:
        raise DomainError(f"Internal error: journal for {source_type} #{source_id} does not balance ({total}).")
    if not legs:
        raise DomainError("Nothing to post — the amount is zero.")
    entry = JournalEntry(date=on, fy_label=fy_label, source_type=source_type, source_id=source_id,
                         narration=narration[:300])
    for lg in legs:
        entry.lines.append(JournalLine(
            account_id=account_id(db, lg.account_code), party_id=lg.party_id, bank_account_id=lg.bank_account_id,
            debit=lg.amount if lg.amount > 0 else ZERO, credit=-lg.amount if lg.amount < 0 else ZERO))
    db.add(entry)
    db.flush()
    return entry


def active_entry(db: Session, source_type: str, source_id: int) -> JournalEntry | None:
    """The latest original (non-reversal) entry for a source that has not been reversed yet."""
    entries = db.scalars(select(JournalEntry).where(
        JournalEntry.source_type == source_type, JournalEntry.source_id == source_id).order_by(JournalEntry.id)).all()
    reversed_ids = {e.reversed_entry_id for e in entries if e.is_reversal}
    live = [e for e in entries if not e.is_reversal and e.id not in reversed_ids]
    return live[-1] if live else None


def reverse(db: Session, *, source_type: str, source_id: int, on: date, fy_label: str, narration: str) -> JournalEntry:
    original = active_entry(db, source_type, source_id)
    if not original:
        raise DomainError("Nothing to reverse for this record.")
    rev = JournalEntry(date=on, fy_label=fy_label, source_type=source_type, source_id=source_id,
                       narration=narration[:300], is_reversal=True, reversed_entry_id=original.id)
    for ln in original.lines:
        rev.lines.append(JournalLine(account_id=ln.account_id, party_id=ln.party_id,
                                     bank_account_id=ln.bank_account_id, debit=ln.credit, credit=ln.debit))
    db.add(rev)
    db.flush()
    return rev


# ---------- Balance queries ----------
def _net(db: Session, *filters) -> Decimal:
    q = select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).join(JournalEntry)
    for f in filters:
        q = q.where(f)
    return D(db.scalar(q)).quantize(Decimal("0.01"))


def balance(db: Session, code: str, *, party_id: int | None = None, bank_account_id: int | None = None,
            as_of: date | None = None, from_date: date | None = None) -> Decimal:
    """Net debit balance (debit - credit). Liabilities/income come back negative."""
    filters = [JournalLine.account_id == account_id(db, code)]
    if party_id is not None:
        filters.append(JournalLine.party_id == party_id)
    if bank_account_id is not None:
        filters.append(JournalLine.bank_account_id == bank_account_id)
    if as_of is not None:
        filters.append(JournalEntry.date <= as_of)
    if from_date is not None:
        filters.append(JournalEntry.date >= from_date)
    return _net(db, *filters)


def trial_balance(db: Session, start: date, end: date) -> list[dict]:
    """Per account: opening (before start), period debit, period credit, closing."""
    rows = db.execute(
        select(Account.code, Account.name, Account.type,
               func.coalesce(func.sum(case((JournalEntry.date < start, JournalLine.debit - JournalLine.credit),
                                           else_=0)), 0),
               func.coalesce(func.sum(case((JournalEntry.date >= start, JournalLine.debit), else_=0)), 0),
               func.coalesce(func.sum(case((JournalEntry.date >= start, JournalLine.credit), else_=0)), 0))
        .select_from(Account)
        .join(JournalLine, JournalLine.account_id == Account.id, isouter=True)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id, isouter=True)
        .where((JournalEntry.date <= end) | (JournalEntry.id.is_(None)))
        .group_by(Account.id).order_by(Account.type, Account.name)).all()
    out = []
    for code, name, typ, opening, debit, credit in rows:
        opening, debit, credit = D(opening), D(debit), D(credit)
        closing = opening + debit - credit
        if opening == 0 and debit == 0 and credit == 0:
            continue
        out.append({"code": code, "name": name, "type": typ, "opening": opening,
                    "debit": debit, "credit": credit, "closing": closing})
    return out
