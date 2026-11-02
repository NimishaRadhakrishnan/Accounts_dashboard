"""Request bodies. Responses are plain dicts built in app/services/serialize.py."""
import re
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")

Amount = Decimal


class StrictModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


def _gstin(v: str | None) -> str | None:
    if v in (None, ""):
        return None
    v = v.upper()
    if not GSTIN_RE.match(v):
        raise ValueError("GSTIN format looks wrong (15 characters, e.g. 33ABCDE1234F1Z5).")
    return v


# ---------- Auth ----------
class LoginIn(StrictModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


class ChangePasswordIn(StrictModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


# ---------- Users ----------
class UserIn(StrictModel):
    full_name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9._-]+$")
    email: str | None = None
    role_code: str
    temp_password: str = Field(min_length=10, max_length=200)


class UserUpdateIn(StrictModel):
    full_name: str | None = None
    email: str | None = None
    role_code: str | None = None
    is_active: bool | None = None


class ResetPasswordIn(StrictModel):
    temp_password: str = Field(min_length=10, max_length=200)


class RolePermissionsIn(StrictModel):
    permissions: list[str]


# ---------- Masters ----------
class CompanyIn(StrictModel):
    legal_name: str = Field(min_length=2)
    trade_name: str | None = None
    gstin: str | None = None
    pan: str | None = None
    cin: str | None = None
    address: str | None = None
    city: str | None = None
    state_code: str = Field(pattern=r"^\d{2}$")
    state_name: str
    pincode: str | None = Field(default=None, pattern=r"^\d{6}$")
    phone: str | None = None
    email: str | None = None
    bank_details_for_invoice: str | None = None
    signatory_name: str | None = None
    signatory_designation: str | None = None
    invoice_terms: str | None = None
    _v_gstin = field_validator("gstin")(classmethod(lambda cls, v: _gstin(v)))


class PartyIn(StrictModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=2, max_length=200)
    is_customer: bool = False
    is_supplier: bool = False
    gstin: str | None = None
    pan: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    district: str | None = None
    state_code: str = Field(pattern=r"^\d{2}$")
    state_name: str
    pincode: str | None = Field(default=None, pattern=r"^\d{6}$")
    payment_term_id: int | None = None
    credit_limit: Amount = Decimal("0")
    tally_ledger_name: str | None = None
    is_active: bool = True
    notes: str | None = None
    _v_gstin = field_validator("gstin")(classmethod(lambda cls, v: _gstin(v)))

    @field_validator("credit_limit")
    @classmethod
    def _non_negative(cls, v):
        if v < 0:
            raise ValueError("Credit limit cannot be negative.")
        return v


class ProductIn(StrictModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=2, max_length=200)
    category: str | None = None
    hsn_code: str | None = Field(default=None, pattern=r"^\d{4,8}$")
    unit: str = "Nos"
    gst_rate: Decimal = Decimal("0")
    sale_price: Amount = Decimal("0")
    purchase_price: Amount = Decimal("0")
    is_active: bool = True


class BankAccountIn(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    kind: Literal["bank", "cash"]
    bank_name: str | None = None
    last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    ifsc: str | None = Field(default=None, pattern=r"^[A-Z]{4}0[A-Z0-9]{6}$")
    opening_balance: Amount = Decimal("0")
    opening_date: date | None = None
    tally_ledger_name: str | None = None
    is_active: bool = True


class ExpenseCategoryIn(StrictModel):
    name: str = Field(min_length=2, max_length=80)
    tally_ledger_name: str | None = None
    is_active: bool = True


class PaymentTermIn(StrictModel):
    name: str = Field(min_length=2, max_length=60)
    days: int = Field(ge=0, le=365)
    is_active: bool = True


class FinancialYearIn(StrictModel):
    start_year: int = Field(ge=2000, le=2100)  # 2026 -> FY 26-27
    make_current: bool = False


class SettingIn(StrictModel):
    value: str


class NumberSeriesIn(StrictModel):
    prefix: str = Field(min_length=1, max_length=6, pattern=r"^[A-Z0-9-]+$")
    next_number: int = Field(ge=1)


class PeriodLockIn(StrictModel):
    year: int
    month: int = Field(ge=1, le=12)


class TallyMapIn(StrictModel):
    account_code: str
    tally_ledger_name: str


# ---------- Vouchers ----------
class LineIn(StrictModel):
    product_id: int | None = None
    description: str = Field(min_length=1, max_length=300)
    hsn_code: str | None = None
    qty: Decimal = Field(gt=0)
    unit: str = "Nos"
    rate: Amount = Field(ge=0)
    discount_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    gst_rate: Decimal = Decimal("0")


class InvoiceIn(StrictModel):
    party_id: int
    date: date
    due_date: date | None = None
    reference: str | None = None
    notes: str | None = None
    lines: list[LineIn] = Field(min_length=1, max_length=200)


class CreditNoteIn(StrictModel):
    sales_invoice_id: int
    date: date
    reason: str = Field(min_length=3, max_length=200)
    notes: str | None = None
    lines: list[LineIn] = Field(min_length=1, max_length=200)


class BillIn(StrictModel):
    party_id: int
    supplier_bill_no: str = Field(min_length=1, max_length=40)
    date: date
    due_date: date | None = None
    notes: str | None = None
    lines: list[LineIn] = Field(min_length=1, max_length=200)


class DebitNoteIn(StrictModel):
    purchase_bill_id: int
    date: date
    reason: str = Field(min_length=3, max_length=200)
    notes: str | None = None
    lines: list[LineIn] = Field(min_length=1, max_length=200)


class OpeningDocIn(StrictModel):
    """Outstanding invoice/bill carried forward from Tally/Excel at go-live."""
    party_id: int
    ref_no: str = Field(min_length=1, max_length=40)
    date: date
    due_date: date | None = None
    amount: Amount = Field(gt=0)
    notes: str | None = None


class AllocationIn(StrictModel):
    doc_id: int
    amount: Amount = Field(gt=0)


Mode = Literal["cash", "neft", "rtgs", "imps", "upi", "cheque"]


class ReceiptIn(StrictModel):
    party_id: int
    date: date
    bank_account_id: int
    amount: Amount = Field(gt=0)
    mode: Mode
    reference: str | None = None
    notes: str | None = None
    allocations: list[AllocationIn] | None = None  # None = auto (oldest first)


class PaymentIn(ReceiptIn):
    pass


class ExpenseIn(StrictModel):
    date: date
    category_id: int
    bank_account_id: int
    payee: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=2, max_length=300)
    mode: Mode = "cash"
    bill_no: str | None = None
    supplier_gstin: str | None = None
    supply_type: Literal["intra", "inter"] = "intra"
    amount: Amount = Field(gt=0)
    gst_rate: Decimal = Decimal("0")
    gst_claimable: bool = False
    notes: str | None = None
    _v_gstin = field_validator("supplier_gstin")(classmethod(lambda cls, v: _gstin(v)))


class ContraIn(StrictModel):
    date: date
    from_account_id: int
    to_account_id: int
    amount: Amount = Field(gt=0)
    reference: str | None = None
    notes: str | None = None


class CancelIn(StrictModel):
    reason: str = Field(min_length=3, max_length=300)


class RejectIn(CancelIn):
    pass
