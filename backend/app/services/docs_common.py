"""Helpers shared by sales and purchase documents."""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFound
from app.core.money import ZERO, D
from app.models import (Allocation, CreditNote, DebitNote, Party, Payment, Product, PurchaseBill, Receipt,
                        SalesInvoice)
from app.schemas import LineIn
from app.services import gst
from app.services.common import company


def load_party(db: Session, party_id: int, *, customer: bool = False, supplier: bool = False) -> Party:
    p = db.get(Party, party_id)
    if not p:
        raise NotFound("Party")
    if not p.is_active:
        raise DomainError(f"{p.name} is marked inactive.")
    if customer and not p.is_customer:
        raise DomainError(f"{p.name} is not set up as a dealer/customer.")
    if supplier and not p.is_supplier:
        raise DomainError(f"{p.name} is not set up as a supplier.")
    return p


def due_date_for(party: Party, doc_date: date, given: date | None) -> date:
    if given:
        if given < doc_date:
            raise DomainError("Due date cannot be before the document date.")
        return given
    return doc_date + timedelta(days=party.credit_days)


def build_totals(db: Session, party: Party, lines: list[LineIn]) -> tuple[str, gst.DocTotals]:
    supply = gst.supply_type_for(company(db).state_code, party.state_code)
    inputs = []
    for ln in lines:
        hsn, unit = ln.hsn_code, ln.unit
        if ln.product_id:
            prod = db.get(Product, ln.product_id)
            if not prod:
                raise NotFound("Product")
            hsn = hsn or prod.hsn_code
            unit = unit or prod.unit
        inputs.append(gst.LineInput(description=ln.description, qty=ln.qty, rate=ln.rate, gst_rate=ln.gst_rate,
                                    discount_pct=ln.discount_pct, hsn_code=hsn, unit=unit, product_id=ln.product_id))
    return supply, gst.compute_document(inputs, supply)


def apply_totals(doc, line_cls, supply: str, place: str, t: gst.DocTotals) -> None:
    doc.supply_type = supply
    doc.place_of_supply = place
    doc.taxable_total = t.taxable_total
    doc.discount_total = t.discount_total
    doc.cgst_total, doc.sgst_total, doc.igst_total = t.cgst_total, t.sgst_total, t.igst_total
    doc.round_off = t.round_off
    doc.grand_total = t.grand_total
    doc.lines.clear()
    for r in t.lines:
        doc.lines.append(line_cls(
            line_no=r.line_no, product_id=r.product_id, description=r.description, hsn_code=r.hsn_code,
            qty=r.qty, unit=r.unit, rate=r.rate, discount_pct=r.discount_pct, discount_amount=r.discount_amount,
            taxable=r.taxable, gst_rate=r.gst_rate, cgst=r.cgst, sgst=r.sgst, igst=r.igst, total=r.total))


# ---------- Settlement ----------
def sales_settled(db: Session, invoice_ids: list[int]) -> dict[int, Decimal]:
    """Amount settled per invoice = posted receipt allocations + posted credit notes."""
    if not invoice_ids:
        return {}
    out = {i: ZERO for i in invoice_ids}
    for inv_id, amt in db.execute(
            select(Allocation.sales_invoice_id, func.sum(Allocation.amount))
            .join(Receipt, Receipt.id == Allocation.receipt_id)
            .where(Allocation.sales_invoice_id.in_(invoice_ids), Receipt.status == "posted")
            .group_by(Allocation.sales_invoice_id)):
        out[inv_id] += D(amt)
    for inv_id, amt in db.execute(
            select(CreditNote.sales_invoice_id, func.sum(CreditNote.grand_total))
            .where(CreditNote.sales_invoice_id.in_(invoice_ids), CreditNote.status == "posted")
            .group_by(CreditNote.sales_invoice_id)):
        out[inv_id] += D(amt)
    return out


def purchase_settled(db: Session, bill_ids: list[int], include_pending: bool = False) -> dict[int, Decimal]:
    """Amount settled per bill. include_pending=True also reserves payments awaiting approval
    (used when validating new allocations so a bill can't be paid twice)."""
    if not bill_ids:
        return {}
    statuses = ("posted", "pending_approval") if include_pending else ("posted",)
    out = {i: ZERO for i in bill_ids}
    for bill_id, amt in db.execute(
            select(Allocation.purchase_bill_id, func.sum(Allocation.amount))
            .join(Payment, Payment.id == Allocation.payment_id)
            .where(Allocation.purchase_bill_id.in_(bill_ids), Payment.status.in_(statuses))
            .group_by(Allocation.purchase_bill_id)):
        out[bill_id] += D(amt)
    for bill_id, amt in db.execute(
            select(DebitNote.purchase_bill_id, func.sum(DebitNote.grand_total))
            .where(DebitNote.purchase_bill_id.in_(bill_ids), DebitNote.status == "posted")
            .group_by(DebitNote.purchase_bill_id)):
        out[bill_id] += D(amt)
    return out


def payment_state(total: Decimal, settled: Decimal, due: date, status: str, today: date | None = None) -> dict:
    today = today or date.today()
    balance = total - settled
    if status != "posted":
        state = status
    elif balance <= 0:
        state = "paid"
    elif settled > 0:
        state = "partial"
    else:
        state = "unpaid"
    overdue_days = (today - due).days if status == "posted" and balance > 0 else 0
    return {"settled": settled, "balance": balance, "payment_status": state,
            "overdue_days": max(overdue_days, 0), "is_overdue": overdue_days > 0}


def has_allocations(db: Session, *, sales_invoice_id: int | None = None, purchase_bill_id: int | None = None) -> bool:
    q = select(func.count(Allocation.id))
    if sales_invoice_id:
        q = q.join(Receipt, Receipt.id == Allocation.receipt_id).where(
            Allocation.sales_invoice_id == sales_invoice_id, Receipt.status != "cancelled")
    else:
        q = q.join(Payment, Payment.id == Allocation.payment_id).where(
            Allocation.purchase_bill_id == purchase_bill_id, Payment.status.notin_(("cancelled", "rejected")))
    return (db.scalar(q) or 0) > 0


def has_notes(db: Session, *, sales_invoice_id: int | None = None, purchase_bill_id: int | None = None) -> bool:
    if sales_invoice_id:
        q = select(func.count(CreditNote.id)).where(CreditNote.sales_invoice_id == sales_invoice_id,
                                                     CreditNote.status == "posted")
    else:
        q = select(func.count(DebitNote.id)).where(DebitNote.purchase_bill_id == purchase_bill_id,
                                                    DebitNote.status == "posted")
    return (db.scalar(q) or 0) > 0


def get_or_404(db: Session, model, id_: int, what: str):
    obj = db.get(model, id_)
    if not obj:
        raise NotFound(what)
    return obj


_ = (SalesInvoice, PurchaseBill)
