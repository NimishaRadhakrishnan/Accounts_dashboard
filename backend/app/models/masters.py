"""Master data: company, financial years, parties, products, accounts, banks, settings."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

Money = Numeric(14, 2)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Company(TimestampMixin, Base):
    __tablename__ = "company"
    id: Mapped[int] = mapped_column(primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    trade_name: Mapped[str | None] = mapped_column(String(200))
    gstin: Mapped[str | None] = mapped_column(String(15))
    pan: Mapped[str | None] = mapped_column(String(10))
    cin: Mapped[str | None] = mapped_column(String(25))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(80))
    state_code: Mapped[str] = mapped_column(String(2), default="33")
    state_name: Mapped[str] = mapped_column(String(60), default="Tamil Nadu")
    pincode: Mapped[str | None] = mapped_column(String(6))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(120))
    logo_path: Mapped[str | None] = mapped_column(String(300))
    bank_details_for_invoice: Mapped[str | None] = mapped_column(Text)
    signatory_name: Mapped[str | None] = mapped_column(String(120))
    signatory_designation: Mapped[str | None] = mapped_column(String(120))
    invoice_terms: Mapped[str | None] = mapped_column(Text)
    is_sample_data: Mapped[bool] = mapped_column(Boolean, default=True)


class FinancialYear(Base):
    __tablename__ = "financial_years"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(10), unique=True)  # "26-27"
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)


class PeriodLock(Base):
    __tablename__ = "period_locks"
    __table_args__ = (UniqueConstraint("year", "month"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    locked_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaymentTerm(Base):
    __tablename__ = "payment_terms"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    days: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Party(TimestampMixin, Base):
    """Dealers/distributors (customers) and suppliers. A party can be both."""
    __tablename__ = "parties"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    is_customer: Mapped[bool] = mapped_column(Boolean, default=False)
    is_supplier: Mapped[bool] = mapped_column(Boolean, default=False)
    gstin: Mapped[str | None] = mapped_column(String(15))
    pan: Mapped[str | None] = mapped_column(String(10))
    contact_person: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(80))
    district: Mapped[str | None] = mapped_column(String(80))
    state_code: Mapped[str] = mapped_column(String(2))
    state_name: Mapped[str] = mapped_column(String(60))
    pincode: Mapped[str | None] = mapped_column(String(6))
    payment_term_id: Mapped[int | None] = mapped_column(ForeignKey("payment_terms.id"))
    credit_limit: Mapped[Decimal] = mapped_column(Money, default=0)
    tally_ledger_name: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    payment_term: Mapped[PaymentTerm | None] = relationship()

    @property
    def credit_days(self) -> int:
        return self.payment_term.days if self.payment_term else 0


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(80))
    hsn_code: Mapped[str | None] = mapped_column(String(8))
    unit: Mapped[str] = mapped_column(String(20), default="Nos")
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    sale_price: Mapped[Decimal] = mapped_column(Money, default=0)
    purchase_price: Mapped[Decimal] = mapped_column(Money, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Account(Base):
    """Chart of accounts. System accounts are fixed codes; expense categories each map to one account."""
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    # asset | liability | income | expense | equity
    type: Mapped[str] = mapped_column(String(20))
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)
    tally_ledger_name: Mapped[str | None] = mapped_column(String(200))


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    account: Mapped[Account] = relationship()


class BankAccount(TimestampMixin, Base):
    """Bank accounts and cash counters. Store a label and last 4 digits only, never full numbers."""
    __tablename__ = "bank_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    kind: Mapped[str] = mapped_column(String(10))  # bank | cash
    bank_name: Mapped[str | None] = mapped_column(String(120))
    last4: Mapped[str | None] = mapped_column(String(4))
    ifsc: Mapped[str | None] = mapped_column(String(11))
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=0)
    opening_date: Mapped[date | None] = mapped_column(Date)
    tally_ledger_name: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class NumberSeries(Base):
    __tablename__ = "number_series"
    __table_args__ = (UniqueConstraint("doc_type", "fy_label"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(20))  # sales_invoice, credit_note, purchase_bill, ...
    fy_label: Mapped[str] = mapped_column(String(10))
    prefix: Mapped[str] = mapped_column(String(10))
    padding: Mapped[int] = mapped_column(Integer, default=4)
    next_number: Mapped[int] = mapped_column(Integer, default=1)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(String(300))
