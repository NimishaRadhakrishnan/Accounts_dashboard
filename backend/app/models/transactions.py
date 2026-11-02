"""Vouchers: sales invoices, credit notes, purchase bills, debit notes, receipts, payments,
allocations, expenses, contra entries, and the journal (ledger core)."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String,
                        Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from app.core.database import Base
from app.models.masters import BankAccount, ExpenseCategory, Party, Product

Money = Numeric(14, 2)
Qty = Numeric(14, 3)


class VoucherMixin:
    """Common header fields. status: draft | pending_approval | posted | cancelled | rejected"""
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str | None] = mapped_column(String(16), unique=True)
    fy_label: Mapped[str] = mapped_column(String(10), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))

    @declared_attr
    def created_by_id(cls) -> Mapped[int]:
        return mapped_column(ForeignKey("users.id"))

    @declared_attr
    def posted_by_id(cls) -> Mapped[int | None]:
        return mapped_column(ForeignKey("users.id"))

    @declared_attr
    def cancelled_by_id(cls) -> Mapped[int | None]:
        return mapped_column(ForeignKey("users.id"))


class TaxTotalsMixin:
    supply_type: Mapped[str] = mapped_column(String(5), default="intra")  # intra | inter
    place_of_supply: Mapped[str] = mapped_column(String(2), default="33")
    taxable_total: Mapped[Decimal] = mapped_column(Money, default=0)
    discount_total: Mapped[Decimal] = mapped_column(Money, default=0)
    cgst_total: Mapped[Decimal] = mapped_column(Money, default=0)
    sgst_total: Mapped[Decimal] = mapped_column(Money, default=0)
    igst_total: Mapped[Decimal] = mapped_column(Money, default=0)
    round_off: Mapped[Decimal] = mapped_column(Money, default=0)
    grand_total: Mapped[Decimal] = mapped_column(Money, default=0)


class LineMixin:
    id: Mapped[int] = mapped_column(primary_key=True)
    line_no: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(300))
    hsn_code: Mapped[str | None] = mapped_column(String(8))
    qty: Mapped[Decimal] = mapped_column(Qty)
    unit: Mapped[str] = mapped_column(String(20), default="Nos")
    rate: Mapped[Decimal] = mapped_column(Money)
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    taxable: Mapped[Decimal] = mapped_column(Money)
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    cgst: Mapped[Decimal] = mapped_column(Money, default=0)
    sgst: Mapped[Decimal] = mapped_column(Money, default=0)
    igst: Mapped[Decimal] = mapped_column(Money, default=0)
    total: Mapped[Decimal] = mapped_column(Money)

    @declared_attr
    def product_id(cls) -> Mapped[int | None]:
        return mapped_column(ForeignKey("products.id"))


# ---------- Sales ----------
class SalesInvoice(VoucherMixin, TaxTotalsMixin, Base):
    __tablename__ = "sales_invoices"
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"), index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    reference: Mapped[str | None] = mapped_column(String(60))  # dealer PO / order ref
    is_opening: Mapped[bool] = mapped_column(Boolean, default=False)  # migrated outstanding, no lines
    party: Mapped[Party] = relationship(lazy="joined")
    lines: Mapped[list["SalesInvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="SalesInvoiceLine.line_no")


class SalesInvoiceLine(LineMixin, Base):
    __tablename__ = "sales_invoice_lines"
    invoice_id: Mapped[int] = mapped_column(ForeignKey("sales_invoices.id", ondelete="CASCADE"), index=True)
    invoice: Mapped[SalesInvoice] = relationship(back_populates="lines")
    product: Mapped[Product | None] = relationship()


class CreditNote(VoucherMixin, TaxTotalsMixin, Base):
    """Sales return / price correction against a specific invoice."""
    __tablename__ = "credit_notes"
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"), index=True)
    sales_invoice_id: Mapped[int] = mapped_column(ForeignKey("sales_invoices.id"), index=True)
    reason: Mapped[str] = mapped_column(String(200))
    party: Mapped[Party] = relationship(lazy="joined")
    invoice: Mapped[SalesInvoice] = relationship()
    lines: Mapped[list["CreditNoteLine"]] = relationship(cascade="all, delete-orphan", order_by="CreditNoteLine.line_no")


class CreditNoteLine(LineMixin, Base):
    __tablename__ = "credit_note_lines"
    credit_note_id: Mapped[int] = mapped_column(ForeignKey("credit_notes.id", ondelete="CASCADE"), index=True)


# ---------- Purchases ----------
class PurchaseBill(VoucherMixin, TaxTotalsMixin, Base):
    __tablename__ = "purchase_bills"
    __table_args__ = (UniqueConstraint("party_id", "supplier_bill_no", "fy_label", name="uq_supplier_bill"),)
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"), index=True)
    supplier_bill_no: Mapped[str] = mapped_column(String(40))
    due_date: Mapped[date] = mapped_column(Date, index=True)
    is_opening: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    party: Mapped[Party] = relationship(lazy="joined")
    lines: Mapped[list["PurchaseBillLine"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan", order_by="PurchaseBillLine.line_no")


class PurchaseBillLine(LineMixin, Base):
    __tablename__ = "purchase_bill_lines"
    bill_id: Mapped[int] = mapped_column(ForeignKey("purchase_bills.id", ondelete="CASCADE"), index=True)
    bill: Mapped[PurchaseBill] = relationship(back_populates="lines")
    product: Mapped[Product | None] = relationship()


class DebitNote(VoucherMixin, TaxTotalsMixin, Base):
    """Purchase return / supplier price correction against a specific bill."""
    __tablename__ = "debit_notes"
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"), index=True)
    purchase_bill_id: Mapped[int] = mapped_column(ForeignKey("purchase_bills.id"), index=True)
    reason: Mapped[str] = mapped_column(String(200))
    party: Mapped[Party] = relationship(lazy="joined")
    bill: Mapped[PurchaseBill] = relationship()
    lines: Mapped[list["DebitNoteLine"]] = relationship(cascade="all, delete-orphan", order_by="DebitNoteLine.line_no")


class DebitNoteLine(LineMixin, Base):
    __tablename__ = "debit_note_lines"
    debit_note_id: Mapped[int] = mapped_column(ForeignKey("debit_notes.id", ondelete="CASCADE"), index=True)


# ---------- Money movement ----------
class Receipt(VoucherMixin, Base):
    __tablename__ = "receipts"
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"), index=True)
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"))
    amount: Mapped[Decimal] = mapped_column(Money)
    mode: Mapped[str] = mapped_column(String(10))  # cash | neft | rtgs | upi | cheque
    reference: Mapped[str | None] = mapped_column(String(60))
    party: Mapped[Party] = relationship(lazy="joined")
    bank_account: Mapped[BankAccount] = relationship(lazy="joined")
    allocations: Mapped[list["Allocation"]] = relationship(
        back_populates="receipt", foreign_keys="Allocation.receipt_id", cascade="all, delete-orphan")


class Payment(VoucherMixin, Base):
    __tablename__ = "payments"
    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"), index=True)
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"))
    amount: Mapped[Decimal] = mapped_column(Money)
    mode: Mapped[str] = mapped_column(String(10))
    reference: Mapped[str | None] = mapped_column(String(60))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    party: Mapped[Party] = relationship(lazy="joined")
    bank_account: Mapped[BankAccount] = relationship(lazy="joined")
    allocations: Mapped[list["Allocation"]] = relationship(
        back_populates="payment", foreign_keys="Allocation.payment_id", cascade="all, delete-orphan")


class Allocation(Base):
    """Links a receipt to sales invoices, or a payment to purchase bills (part payments allowed)."""
    __tablename__ = "allocations"
    __table_args__ = (
        CheckConstraint(
            "(receipt_id IS NOT NULL AND sales_invoice_id IS NOT NULL AND payment_id IS NULL AND purchase_bill_id IS NULL)"
            " OR (payment_id IS NOT NULL AND purchase_bill_id IS NOT NULL AND receipt_id IS NULL AND sales_invoice_id IS NULL)",
            name="ck_allocation_pair"),
        CheckConstraint("amount > 0", name="ck_allocation_positive"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int | None] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"), index=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), index=True)
    sales_invoice_id: Mapped[int | None] = mapped_column(ForeignKey("sales_invoices.id"), index=True)
    purchase_bill_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_bills.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    receipt: Mapped[Receipt | None] = relationship(back_populates="allocations", foreign_keys=[receipt_id])
    payment: Mapped[Payment | None] = relationship(back_populates="allocations", foreign_keys=[payment_id])
    sales_invoice: Mapped[SalesInvoice | None] = relationship()
    purchase_bill: Mapped[PurchaseBill | None] = relationship()


class Expense(VoucherMixin, Base):
    __tablename__ = "expenses"
    category_id: Mapped[int] = mapped_column(ForeignKey("expense_categories.id"), index=True)
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"))
    payee: Mapped[str] = mapped_column(String(200))
    bill_no: Mapped[str | None] = mapped_column(String(40))
    supplier_gstin: Mapped[str | None] = mapped_column(String(15))
    description: Mapped[str] = mapped_column(String(300))
    mode: Mapped[str] = mapped_column(String(10), default="cash")
    supply_type: Mapped[str] = mapped_column(String(5), default="intra")
    amount: Mapped[Decimal] = mapped_column(Money)  # before GST
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    gst_claimable: Mapped[bool] = mapped_column(Boolean, default=False)
    cgst: Mapped[Decimal] = mapped_column(Money, default=0)
    sgst: Mapped[Decimal] = mapped_column(Money, default=0)
    igst: Mapped[Decimal] = mapped_column(Money, default=0)
    total: Mapped[Decimal] = mapped_column(Money)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reject_reason: Mapped[str | None] = mapped_column(String(300))
    category: Mapped[ExpenseCategory] = relationship(lazy="joined")
    bank_account: Mapped[BankAccount] = relationship(lazy="joined")


class ContraEntry(VoucherMixin, Base):
    """Cash deposit, cash withdrawal, or bank-to-bank transfer."""
    __tablename__ = "contra_entries"
    __table_args__ = (CheckConstraint("from_account_id <> to_account_id", name="ck_contra_distinct"),)
    from_account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"))
    to_account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"))
    amount: Mapped[Decimal] = mapped_column(Money)
    reference: Mapped[str | None] = mapped_column(String(60))
    from_account: Mapped[BankAccount] = relationship(foreign_keys=[from_account_id], lazy="joined")
    to_account: Mapped[BankAccount] = relationship(foreign_keys=[to_account_id], lazy="joined")


# ---------- Ledger core ----------
class JournalEntry(Base):
    __tablename__ = "journal_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    fy_label: Mapped[str] = mapped_column(String(10), index=True)
    source_type: Mapped[str] = mapped_column(String(30), index=True)
    source_id: Mapped[int] = mapped_column(Integer, index=True)
    narration: Mapped[str] = mapped_column(String(300))
    is_reversal: Mapped[bool] = mapped_column(Boolean, default=False)
    reversed_entry_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lines: Mapped[list["JournalLine"]] = relationship(back_populates="entry", cascade="all, delete-orphan")


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint("debit >= 0 AND credit >= 0 AND NOT (debit > 0 AND credit > 0)", name="ck_line_side"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    party_id: Mapped[int | None] = mapped_column(ForeignKey("parties.id"), index=True)
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_accounts.id"), index=True)
    debit: Mapped[Decimal] = mapped_column(Money, default=0)
    credit: Mapped[Decimal] = mapped_column(Money, default=0)
    entry: Mapped[JournalEntry] = relationship(back_populates="lines")
