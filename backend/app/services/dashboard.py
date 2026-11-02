"""Dashboard overview numbers. Everything is derived from the ledger so it always matches reports."""
from datetime import date, timedelta

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.core.money import ZERO, D
from app.models import (Account, BankAccount, Expense, JournalEntry, JournalLine, Payment, PurchaseBill)
from app.services import ledger
from app.services.common import current_fy, fy_for
from app.services.outstanding import ageing


def _expense_account_ids(db: Session) -> list[int]:
    return list(db.scalars(select(Account.id).where(Account.type == "expense", Account.is_system.is_(False))))


def _net_for(db: Session, account_ids: list[int], start: date, end: date) -> D:
    if not account_ids:
        return ZERO
    v = db.scalar(select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).join(JournalEntry)
                  .where(JournalLine.account_id.in_(account_ids), JournalEntry.date >= start, JournalEntry.date <= end))
    return D(v).quantize(D("0.01"))


def period_figures(db: Session, start: date, end: date) -> dict:
    sales_ids = [ledger.account_id(db, ledger.SALES), ledger.account_id(db, ledger.SALES_RETURNS)]
    purchase_ids = [ledger.account_id(db, ledger.PURCHASES), ledger.account_id(db, ledger.PURCHASE_RETURNS)]
    return {
        "sales": -_net_for(db, sales_ids, start, end),
        "purchases": _net_for(db, purchase_ids, start, end),
        "expenses": _net_for(db, _expense_account_ids(db), start, end),
    }


def monthly_trend(db: Session, start: date, end: date) -> list[dict]:
    sales_ids = {ledger.account_id(db, ledger.SALES), ledger.account_id(db, ledger.SALES_RETURNS)}
    purchase_ids = {ledger.account_id(db, ledger.PURCHASES), ledger.account_id(db, ledger.PURCHASE_RETURNS)}
    expense_ids = set(_expense_account_ids(db))
    rows = db.execute(
        select(extract("year", JournalEntry.date), extract("month", JournalEntry.date), JournalLine.account_id,
               func.sum(JournalLine.debit - JournalLine.credit))
        .join(JournalEntry)
        .where(JournalEntry.date >= start, JournalEntry.date <= end,
               JournalLine.account_id.in_(sales_ids | purchase_ids | expense_ids))
        .group_by(extract("year", JournalEntry.date), extract("month", JournalEntry.date), JournalLine.account_id)
    ).all()
    months = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    data = {k: {"sales": ZERO, "purchases": ZERO, "expenses": ZERO} for k in months}
    for yy, mm, acc, net in rows:
        key = (int(yy), int(mm))
        if key not in data:
            continue
        net = D(net)
        if acc in sales_ids:
            data[key]["sales"] -= net
        elif acc in purchase_ids:
            data[key]["purchases"] += net
        else:
            data[key]["expenses"] += net
    return [{"month": f"{date(y, m, 1):%b %y}", "year": y, "month_no": m, **v} for (y, m), v in data.items()]


def overview(db: Session, on: date | None = None) -> dict:
    today = on or date.today()
    try:
        fy = fy_for(db, today)
    except Exception:
        fy = current_fy(db)
    month_start = today.replace(day=1)
    fy_end_or_today = min(fy.end_date, today)
    this_month = period_figures(db, month_start, today)
    prev_end = month_start - timedelta(days=1)
    prev_month = period_figures(db, prev_end.replace(day=1), prev_end)
    fy_figs = period_figures(db, fy.start_date, fy_end_or_today)

    banks = []
    for b in db.scalars(select(BankAccount).where(BankAccount.is_active.is_(True)).order_by(BankAccount.kind,
                                                                                           BankAccount.name)):
        banks.append({"id": b.id, "name": b.name, "kind": b.kind,
                      "balance": ledger.balance(db, ledger.CASH_BANK, bank_account_id=b.id, as_of=today)})

    rec = ageing(db, "receivable", today)
    pay = ageing(db, "payable", today)

    overdue_dealers = [p for p in rec["parties"] if p["oldest_overdue_days"] > 0][:5]
    upcoming = [i for i in pay["items"] if 0 <= (i["due_date"] - today).days <= 7][:8]
    overdue_payables = [i for i in pay["items"] if i["overdue_days"] > 0]

    recent = []
    for e in db.scalars(select(JournalEntry).where(JournalEntry.source_type != "bank_opening")
                        .order_by(JournalEntry.date.desc(), JournalEntry.id.desc()).limit(8)):
        amt = sum((ln.debit for ln in e.lines), ZERO)
        recent.append({"date": e.date, "type": e.source_type, "source_id": e.source_id, "narration": e.narration,
                       "amount": amt, "is_reversal": e.is_reversal})

    pending = {
        "payments": db.scalar(select(func.count(Payment.id)).where(Payment.status == "pending_approval")) or 0,
        "expenses": db.scalar(select(func.count(Expense.id)).where(Expense.status == "pending_approval")) or 0,
        "bills_to_verify": db.scalar(select(func.count(PurchaseBill.id)).where(PurchaseBill.status == "draft")) or 0,
    }

    return {
        "as_of": today, "fy": fy.label, "fy_start": fy.start_date, "fy_end": fy.end_date,
        "kpis": {
            "sales_month": this_month["sales"], "sales_prev_month": prev_month["sales"], "sales_fy": fy_figs["sales"],
            "expenses_month": this_month["expenses"], "expenses_prev_month": prev_month["expenses"],
            "expenses_fy": fy_figs["expenses"], "purchases_month": this_month["purchases"],
            "purchases_fy": fy_figs["purchases"],
            "receivables": rec["net"], "receivables_overdue": rec["gross"] - next(
                b["amount"] for b in rec["buckets"] if b["key"] == "not_due"),
            "payables": pay["net"], "payables_overdue": sum((i["balance"] for i in overdue_payables), ZERO),
            "cash_bank": sum((b["balance"] for b in banks), ZERO),
            "cash_only": sum((b["balance"] for b in banks if b["kind"] == "cash"), ZERO),
        },
        "banks": banks,
        "trend": [{**t, "future": date(t["year"], t["month_no"], 1) > today} for t in monthly_trend(db, fy.start_date, fy.end_date)],
        "receivable_ageing": rec["buckets"], "payable_ageing": pay["buckets"],
        "overdue_dealers": overdue_dealers, "upcoming_payments": upcoming,
        "recent": recent, "pending": pending,
    }
