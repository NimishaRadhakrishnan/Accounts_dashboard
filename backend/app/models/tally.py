"""Copy of Tally data, refreshed by the Tally connector. The dashboard only reads from these tables."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
                        func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

Money = Numeric(16, 2)


class TallyCompany(Base):
    __tablename__ = "tally_companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    guid: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    books_from: Mapped[date | None] = mapped_column(Date)
    alt_vch_id: Mapped[int] = mapped_column(Integer, default=0)
    alt_mst_id: Mapped[int] = mapped_column(Integer, default=0)
    closing_as_of: Mapped[date | None] = mapped_column(Date)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_data_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_full_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    agent_version: Mapped[str | None] = mapped_column(String(20))


class TallyGroup(Base):
    __tablename__ = "tally_groups"
    __table_args__ = (UniqueConstraint("company_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("tally_companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    parent: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20))


class TallyLedger(Base):
    __tablename__ = "tally_ledgers"
    __table_args__ = (UniqueConstraint("company_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("tally_companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    parent: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20), index=True)
    opening_dr: Mapped[Decimal] = mapped_column(Money, default=0)
    tally_closing_dr: Mapped[Decimal | None] = mapped_column(Money)  # as reported by Tally, for cross-checking
    credit_days: Mapped[int] = mapped_column(Integer, default=0)
    gstin: Mapped[str | None] = mapped_column(String(20))
    state: Mapped[str | None] = mapped_column(String(60))


class TallyVoucherType(Base):
    __tablename__ = "tally_voucher_types"
    __table_args__ = (UniqueConstraint("company_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("tally_companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    parent: Mapped[str | None] = mapped_column(String(100))


class TallyVoucher(Base):
    __tablename__ = "tally_vouchers"
    __table_args__ = (UniqueConstraint("company_id", "guid"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("tally_companies.id", ondelete="CASCADE"), index=True)
    guid: Mapped[str] = mapped_column(String(80))
    alter_id: Mapped[int] = mapped_column(Integer, default=0)
    date: Mapped[date] = mapped_column(Date, index=True)
    vtype: Mapped[str] = mapped_column(String(100))
    number: Mapped[str | None] = mapped_column(String(60))
    party: Mapped[str | None] = mapped_column(String(200))
    narration: Mapped[str | None] = mapped_column(String(300))
    counted: Mapped[bool] = mapped_column(Boolean, default=True)  # False for cancelled / optional / unbalanced
    lines: Mapped[list["TallyLine"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    stock: Mapped[list["TallyStockLine"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class TallyLine(Base):
    __tablename__ = "tally_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    voucher_id: Mapped[int] = mapped_column(ForeignKey("tally_vouchers.id", ondelete="CASCADE"), index=True)
    ledger: Mapped[str] = mapped_column(String(200), index=True)
    dr: Mapped[Decimal] = mapped_column(Money)  # + debit, - credit
    bills: Mapped[list | None] = mapped_column(JSON)


class TallyStockLine(Base):
    __tablename__ = "tally_stock_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    voucher_id: Mapped[int] = mapped_column(ForeignKey("tally_vouchers.id", ondelete="CASCADE"), index=True)
    item: Mapped[str] = mapped_column(String(200), index=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    unit: Mapped[str | None] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Money)
    inward: Mapped[bool] = mapped_column(Boolean, default=False)


class TallyStockValue(Base):
    __tablename__ = "tally_stock_values"
    __table_args__ = (UniqueConstraint("company_id", "as_of"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("tally_companies.id", ondelete="CASCADE"), index=True)
    as_of: Mapped[date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Money)


class TallySyncRun(Base):
    __tablename__ = "tally_sync_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("tally_companies.id", ondelete="CASCADE"))
    mode: Mapped[str] = mapped_column(String(20))
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    vouchers: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    seconds: Mapped[float | None] = mapped_column(Numeric(8, 2))
    message: Mapped[str | None] = mapped_column(Text)


class ConnectorKey(Base):
    """Key the connector on the Tally computer uses. Only a hash is stored."""
    __tablename__ = "tally_connector_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(100))
    key_hash: Mapped[str] = mapped_column(String(128), unique=True)
    hint: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
