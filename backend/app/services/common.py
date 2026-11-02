"""Shared helpers: financial year lookup, period locks, document numbering, app settings, snapshots."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models import AppSetting, Company, FinancialYear, NumberSeries, PeriodLock

DOC_PREFIX = {
    "sales_invoice": "VBT", "credit_note": "CN", "purchase_bill": "PB", "debit_note": "DN",
    "receipt": "RC", "payment": "PY", "expense": "EX", "contra": "CT",
}
GST_MAX_INVOICE_NO_LEN = 16


def company(db: Session) -> Company:
    c = db.scalar(select(Company).limit(1))
    if not c:
        raise DomainError("Company profile is not set up yet.")
    return c


def fy_for(db: Session, d: date) -> FinancialYear:
    fy = db.scalar(select(FinancialYear).where(FinancialYear.start_date <= d, FinancialYear.end_date >= d))
    if not fy:
        raise DomainError(f"No financial year is set up for {d:%d-%m-%Y}. Add it in Settings.")
    return fy


def current_fy(db: Session) -> FinancialYear:
    fy = db.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
    if not fy:
        fy = db.scalar(select(FinancialYear).order_by(FinancialYear.start_date.desc()))
    if not fy:
        raise DomainError("No financial year is set up.")
    return fy


def ensure_open_period(db: Session, d: date) -> FinancialYear:
    """Raises if the date falls in a locked month or a closed financial year."""
    fy = fy_for(db, d)
    if fy.is_closed:
        raise DomainError(f"Financial year {fy.label} is closed.")
    lock = db.scalar(select(PeriodLock).where(PeriodLock.year == d.year, PeriodLock.month == d.month))
    if lock:
        raise DomainError(f"{d:%B %Y} is locked. Ask the Accounts Manager to unlock it first.")
    return fy


def next_number(db: Session, doc_type: str, fy_label: str) -> str:
    """Gap-free sequential number per document type per financial year. Row-locked."""
    series = db.scalar(
        select(NumberSeries).where(NumberSeries.doc_type == doc_type, NumberSeries.fy_label == fy_label)
        .with_for_update())
    if not series:
        series = NumberSeries(doc_type=doc_type, fy_label=fy_label, prefix=DOC_PREFIX[doc_type],
                              padding=4, next_number=1)
        db.add(series)
        db.flush()
        series = db.scalar(select(NumberSeries).where(NumberSeries.id == series.id).with_for_update())
    number = f"{series.prefix}/{fy_label}/{series.next_number:0{series.padding}d}"
    if len(number) > GST_MAX_INVOICE_NO_LEN:
        raise DomainError(f"Number '{number}' is longer than 16 characters (GST rule). Shorten the prefix.")
    series.next_number += 1
    return number


DEFAULT_SETTINGS = {
    "expense_approval_limit": ("5000", "Expenses above this amount (₹, incl. GST) need approval."),
    "payment_approval_limit": ("100000", "Supplier payments above this amount (₹) need approval."),
    "purchase_maker_checker": ("true", "Purchase bills must be verified by a different user before posting."),
    "invoice_prefix_note": ("SAMPLE", "Replace sample prefixes once the company confirms its numbering format."),
}


def get_setting(db: Session, key: str) -> str:
    row = db.get(AppSetting, key)
    if row:
        return row.value
    return DEFAULT_SETTINGS[key][0]


def setting_decimal(db: Session, key: str) -> Decimal:
    return Decimal(get_setting(db, key))


def setting_bool(db: Session, key: str) -> bool:
    return get_setting(db, key).lower() in ("1", "true", "yes")


def snapshot(obj, fields: list[str] | None = None) -> dict:
    """JSON-safe dict of an ORM object's column values (for audit logs)."""
    cols = fields or [c.key for c in obj.__table__.columns]
    out = {}
    for k in cols:
        v = getattr(obj, k, None)
        if isinstance(v, Decimal):
            v = str(v)
        elif isinstance(v, (date, datetime)):
            v = v.isoformat()
        out[k] = v
    return out
