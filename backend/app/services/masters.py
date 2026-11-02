"""Master data: company, parties, products, banks, categories, terms, settings, numbering, periods."""
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.core.errors import DomainError, NotFound
from app.models import (Account, AppSetting, BankAccount, Company, ExpenseCategory, FinancialYear, JournalLine,
                        NumberSeries, Party, PaymentTerm, PeriodLock, Product)
from app.schemas import (BankAccountIn, CompanyIn, ExpenseCategoryIn, NumberSeriesIn, PartyIn, PaymentTermIn,
                         PeriodLockIn, ProductIn, TallyMapIn)
from app.services import audit
from app.services.bootstrap import ensure_fy
from app.services.cash import post_bank_opening
from app.services.common import DEFAULT_SETTINGS, current_fy, fy_for, snapshot
from app.services.gst import VALID_RATES


def _apply(obj, data) -> None:
    for k, v in data.model_dump().items():
        setattr(obj, k, v)


def save_company(db: Session, actor: Actor, data: CompanyIn) -> Company:
    c = db.scalar(select(Company).limit(1))
    old = snapshot(c) if c else None
    if not c:
        c = Company()
        db.add(c)
    _apply(c, data)
    c.is_sample_data = False
    db.flush()
    audit.record(db, actor, "update", "company", c.id, "Company profile updated", old=old, new=snapshot(c))
    return c


# ---------- Parties ----------
def _party_checks(db: Session, data: PartyIn, party_id: int | None) -> None:
    if not (data.is_customer or data.is_supplier):
        raise DomainError("Tick at least one: Dealer/Customer or Supplier.")
    if data.gstin and data.gstin[:2] != data.state_code:
        raise DomainError(f"GSTIN starts with {data.gstin[:2]} but the state code is {data.state_code}.")
    dup = db.scalar(select(Party).where(func.lower(Party.code) == data.code.lower(), Party.id != (party_id or 0)))
    if dup:
        raise DomainError(f"Code {data.code} is already used by {dup.name}.")
    if data.gstin:
        dup = db.scalar(select(Party).where(Party.gstin == data.gstin, Party.id != (party_id or 0)))
        if dup:
            raise DomainError(f"GSTIN {data.gstin} is already used by {dup.name}.")
    if data.payment_term_id and not db.get(PaymentTerm, data.payment_term_id):
        raise NotFound("Payment term")


def save_party(db: Session, actor: Actor, data: PartyIn, party_id: int | None = None) -> Party:
    _party_checks(db, data, party_id)
    if party_id:
        p = db.get(Party, party_id)
        if not p:
            raise NotFound("Party")
        old = snapshot(p)
        has_entries = db.scalar(select(func.count(JournalLine.id)).where(JournalLine.party_id == p.id)) or 0
        if has_entries and p.state_code != data.state_code:
            raise DomainError("State can't be changed after transactions exist (it decides GST type). "
                              "Create a new party instead.")
    else:
        p, old = Party(), None
        db.add(p)
    _apply(p, data)
    db.flush()
    audit.record(db, actor, "update" if old else "create", "party", p.id, f"{p.code} {p.name}", old=old,
                 new=snapshot(p))
    return p


# ---------- Products ----------
def save_product(db: Session, actor: Actor, data: ProductIn, product_id: int | None = None) -> Product:
    if data.gst_rate not in VALID_RATES:
        raise DomainError(f"{data.gst_rate}% is not a valid GST rate.")
    dup = db.scalar(select(Product).where(func.lower(Product.code) == data.code.lower(),
                                          Product.id != (product_id or 0)))
    if dup:
        raise DomainError(f"Code {data.code} is already used by {dup.name}.")
    if product_id:
        p = db.get(Product, product_id)
        if not p:
            raise NotFound("Product")
        old = snapshot(p)
    else:
        p, old = Product(), None
        db.add(p)
    _apply(p, data)
    db.flush()
    audit.record(db, actor, "update" if old else "create", "product", p.id, f"{p.code} {p.name}", old=old,
                 new=snapshot(p))
    return p


# ---------- Banks ----------
def save_bank(db: Session, actor: Actor, data: BankAccountIn, bank_id: int | None = None) -> BankAccount:
    dup = db.scalar(select(BankAccount).where(func.lower(BankAccount.name) == data.name.lower(),
                                              BankAccount.id != (bank_id or 0)))
    if dup:
        raise DomainError(f"An account named {data.name} already exists.")
    if bank_id:
        b = db.get(BankAccount, bank_id)
        if not b:
            raise NotFound("Bank / cash account")
        old = snapshot(b)
    else:
        b, old = BankAccount(), None
        db.add(b)
    opening_changed = old is None or old["opening_balance"] != str(data.opening_balance) or \
        old["opening_date"] != (data.opening_date.isoformat() if data.opening_date else None)
    _apply(b, data)
    db.flush()
    if opening_changed and (b.opening_balance or old):
        if not b.opening_date:
            raise DomainError("Enter the date of the opening balance.")
        fy = fy_for(db, b.opening_date)
        post_bank_opening(db, b, fy.label)
    audit.record(db, actor, "update" if old else "create", "bank_account", b.id, b.name, old=old, new=snapshot(b))
    return b


# ---------- Expense categories ----------
def save_category(db: Session, actor: Actor, data: ExpenseCategoryIn, cat_id: int | None = None) -> ExpenseCategory:
    dup = db.scalar(select(ExpenseCategory).where(func.lower(ExpenseCategory.name) == data.name.lower(),
                                                  ExpenseCategory.id != (cat_id or 0)))
    if dup:
        raise DomainError(f"Category {data.name} already exists.")
    if cat_id:
        c = db.get(ExpenseCategory, cat_id)
        if not c:
            raise NotFound("Category")
        old = snapshot(c)
        c.name, c.is_active = data.name, data.is_active
        c.account.name = data.name
        c.account.tally_ledger_name = data.tally_ledger_name or c.account.tally_ledger_name
    else:
        slug = re.sub(r"[^A-Z0-9]+", "_", data.name.upper()).strip("_")[:20]
        code = f"EXP_{slug}"
        n = 1
        while db.scalar(select(Account).where(Account.code == code)):
            n += 1
            code = f"EXP_{slug}_{n}"
        acc = Account(code=code, name=data.name, type="expense", is_system=False,
                      tally_ledger_name=data.tally_ledger_name or data.name)
        db.add(acc)
        db.flush()
        c, old = ExpenseCategory(name=data.name, account_id=acc.id, is_active=data.is_active), None
        db.add(c)
    db.flush()
    audit.record(db, actor, "update" if old else "create", "expense_category", c.id, c.name, old=old,
                 new=snapshot(c))
    return c


def save_term(db: Session, actor: Actor, data: PaymentTermIn, term_id: int | None = None) -> PaymentTerm:
    if term_id:
        t = db.get(PaymentTerm, term_id)
        if not t:
            raise NotFound("Payment term")
        old = snapshot(t)
    else:
        t, old = PaymentTerm(), None
        db.add(t)
    _apply(t, data)
    db.flush()
    audit.record(db, actor, "update" if old else "create", "payment_term", t.id, f"{t.name} ({t.days} days)",
                 old=old, new=snapshot(t))
    return t


# ---------- Settings ----------
def set_setting(db: Session, actor: Actor, key: str, value: str) -> AppSetting:
    if key not in DEFAULT_SETTINGS:
        raise DomainError("Unknown setting.", 404)
    if key.endswith("_limit"):
        try:
            if float(value) < 0:
                raise ValueError
        except ValueError:
            raise DomainError("Enter a valid amount.")
    if key == "purchase_maker_checker" and value.lower() not in ("true", "false"):
        raise DomainError("Use true or false.")
    row = db.get(AppSetting, key) or AppSetting(key=key, value="", description=DEFAULT_SETTINGS[key][1])
    old = row.value
    row.value = value
    db.add(row)
    db.flush()
    audit.record(db, actor, "update", "setting", key, f"{key}: {old} → {value}")
    return row


def update_series(db: Session, actor: Actor, series_id: int, data: NumberSeriesIn) -> NumberSeries:
    s = db.get(NumberSeries, series_id)
    if not s:
        raise NotFound("Number series")
    old = snapshot(s)
    if s.next_number > 1 and data.prefix != s.prefix:
        raise DomainError("Prefix can't change after numbers have been used this year.")
    if data.next_number < s.next_number:
        raise DomainError("Next number can't go backwards (numbers must stay unique and in order).")
    sample = f"{data.prefix}/{s.fy_label}/{data.next_number:0{s.padding}d}"
    if len(sample) > 16:
        raise DomainError(f"'{sample}' is longer than 16 characters (GST rule).")
    s.prefix, s.next_number = data.prefix, data.next_number
    audit.record(db, actor, "update", "number_series", s.id, f"{s.doc_type} {s.fy_label} → {sample}",
                 old=old, new=snapshot(s))
    return s


def ensure_series(db: Session) -> list[NumberSeries]:
    """Make sure every document type has a series for the current year (so Settings can show/edit them)."""
    from app.services.common import DOC_PREFIX
    fy = current_fy(db)
    have = {s.doc_type for s in db.scalars(select(NumberSeries).where(NumberSeries.fy_label == fy.label))}
    for doc_type, prefix in DOC_PREFIX.items():
        if doc_type not in have:
            db.add(NumberSeries(doc_type=doc_type, fy_label=fy.label, prefix=prefix, padding=4, next_number=1))
    db.flush()
    return list(db.scalars(select(NumberSeries).where(NumberSeries.fy_label == fy.label).order_by(NumberSeries.id)))


def lock_period(db: Session, actor: Actor, data: PeriodLockIn) -> PeriodLock:
    if db.scalar(select(PeriodLock).where(PeriodLock.year == data.year, PeriodLock.month == data.month)):
        raise DomainError("That month is already locked.")
    lock = PeriodLock(year=data.year, month=data.month, locked_by_id=actor.id)
    db.add(lock)
    db.flush()
    audit.record(db, actor, "lock", "period", f"{data.year}-{data.month:02d}", f"Locked {data.month:02d}/{data.year}")
    return lock


def unlock_period(db: Session, actor: Actor, lock_id: int) -> None:
    lock = db.get(PeriodLock, lock_id)
    if not lock:
        raise NotFound("Lock")
    audit.record(db, actor, "unlock", "period", f"{lock.year}-{lock.month:02d}",
                 f"Unlocked {lock.month:02d}/{lock.year}")
    db.delete(lock)


def add_fy(db: Session, actor: Actor, start_year: int, make_current: bool) -> FinancialYear:
    fy = ensure_fy(db, start_year, make_current)
    audit.record(db, actor, "create", "financial_year", fy.id, f"FY {fy.label}{' (current)' if make_current else ''}")
    return fy


def map_tally(db: Session, actor: Actor, data: TallyMapIn) -> Account:
    acc = db.scalar(select(Account).where(Account.code == data.account_code))
    if not acc:
        raise NotFound("Account")
    old = acc.tally_ledger_name
    acc.tally_ledger_name = data.tally_ledger_name
    audit.record(db, actor, "update", "tally_map", acc.code, f"{acc.name}: {old} → {data.tally_ledger_name}")
    return acc
