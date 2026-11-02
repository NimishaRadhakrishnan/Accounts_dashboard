"""GST calculation — pure functions, no database. The single source of truth for tax maths.

Rules
- taxable = qty x rate - discount  (discount = gross x discount% , rounded to paise)
- Intra-state (same state as company): CGST = SGST = taxable x (rate/2)%, each rounded to paise
- Inter-state: IGST = taxable x rate%, rounded to paise
- Document total is rounded to the nearest rupee; the difference is kept as round_off
"""
from dataclasses import dataclass, field
from decimal import Decimal

from app.core.errors import DomainError
from app.core.money import D, ZERO, r0, r2


@dataclass
class LineInput:
    description: str
    qty: Decimal
    rate: Decimal
    gst_rate: Decimal = ZERO
    discount_pct: Decimal = ZERO
    hsn_code: str | None = None
    unit: str = "Nos"
    product_id: int | None = None


@dataclass
class LineResult:
    line_no: int
    description: str
    hsn_code: str | None
    unit: str
    product_id: int | None
    qty: Decimal
    rate: Decimal
    discount_pct: Decimal
    discount_amount: Decimal
    taxable: Decimal
    gst_rate: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    total: Decimal


@dataclass
class DocTotals:
    lines: list[LineResult] = field(default_factory=list)
    discount_total: Decimal = ZERO
    taxable_total: Decimal = ZERO
    cgst_total: Decimal = ZERO
    sgst_total: Decimal = ZERO
    igst_total: Decimal = ZERO
    round_off: Decimal = ZERO
    grand_total: Decimal = ZERO

    @property
    def tax_total(self) -> Decimal:
        return self.cgst_total + self.sgst_total + self.igst_total


VALID_RATES = {D(x) for x in ("0", "0.1", "0.25", "1", "1.5", "3", "5", "6", "7.5", "12", "18", "28", "40")}


def supply_type_for(company_state: str, party_state: str) -> str:
    return "intra" if company_state == party_state else "inter"


def compute_line(no: int, li: LineInput, supply_type: str) -> LineResult:
    qty, rate, pct, gst_rate = D(li.qty), D(li.rate), D(li.discount_pct), D(li.gst_rate)
    if qty <= 0:
        raise DomainError(f"Line {no}: quantity must be more than zero.")
    if rate < 0:
        raise DomainError(f"Line {no}: rate cannot be negative.")
    if not (ZERO <= pct <= D(100)):
        raise DomainError(f"Line {no}: discount must be between 0 and 100%.")
    if gst_rate not in VALID_RATES:
        raise DomainError(f"Line {no}: {gst_rate}% is not a valid GST rate.")

    gross = r2(qty * rate)
    discount = r2(gross * pct / 100)
    taxable = gross - discount
    cgst = sgst = igst = ZERO
    if supply_type == "intra":
        cgst = r2(taxable * gst_rate / 2 / 100)
        sgst = r2(taxable * gst_rate / 2 / 100)
    else:
        igst = r2(taxable * gst_rate / 100)
    return LineResult(no, li.description.strip(), li.hsn_code, li.unit, li.product_id, qty, rate, pct, discount,
                      taxable, gst_rate, cgst, sgst, igst, taxable + cgst + sgst + igst)


def compute_document(lines: list[LineInput], supply_type: str) -> DocTotals:
    if supply_type not in ("intra", "inter"):
        raise DomainError("Supply type must be intra or inter.")
    if not lines:
        raise DomainError("Add at least one line.")
    t = DocTotals()
    for i, li in enumerate(lines, start=1):
        r = compute_line(i, li, supply_type)
        t.lines.append(r)
        t.discount_total += r.discount_amount
        t.taxable_total += r.taxable
        t.cgst_total += r.cgst
        t.sgst_total += r.sgst
        t.igst_total += r.igst
    before_round = t.taxable_total + t.tax_total
    t.grand_total = r0(before_round)
    t.round_off = t.grand_total - before_round
    return t


def compute_simple_tax(amount: Decimal, gst_rate: Decimal, supply_type: str) -> tuple[Decimal, Decimal, Decimal]:
    """For single-amount vouchers (expenses). Returns (cgst, sgst, igst)."""
    amount, gst_rate = D(amount), D(gst_rate)
    if gst_rate not in VALID_RATES:
        raise DomainError(f"{gst_rate}% is not a valid GST rate.")
    if supply_type == "intra":
        half = r2(amount * gst_rate / 2 / 100)
        return half, half, ZERO
    return ZERO, ZERO, r2(amount * gst_rate / 100)
