"""Sales invoices and credit notes."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.core.errors import DomainError
from app.core.money import ZERO
from app.models import CreditNote, CreditNoteLine, SalesInvoice, SalesInvoiceLine
from app.schemas import CancelIn, CreditNoteIn, InvoiceIn, OpeningDocIn
from app.services import audit, ledger
from app.services.common import ensure_open_period, next_number, snapshot
from app.services.docs_common import (apply_totals, build_totals, due_date_for, get_or_404, has_allocations,
                                      has_notes, load_party, sales_settled)
from app.services.ledger import cr, dr

SRC_INV = "sales_invoice"
SRC_CN = "credit_note"


def _now():
    return datetime.now(timezone.utc)


def _invoice_legs(inv: SalesInvoice) -> list[ledger.Leg]:
    if inv.is_opening:
        return [dr(ledger.DEBTORS, inv.grand_total, party_id=inv.party_id),
                cr(ledger.OPENING_EQUITY, inv.grand_total)]
    legs = [dr(ledger.DEBTORS, inv.grand_total, party_id=inv.party_id),
            cr(ledger.SALES, inv.taxable_total),
            cr(ledger.OUT_CGST, inv.cgst_total), cr(ledger.OUT_SGST, inv.sgst_total),
            cr(ledger.OUT_IGST, inv.igst_total)]
    if inv.round_off:
        legs.append(cr(ledger.ROUND_OFF, inv.round_off))  # +ve round off is a small gain
    return legs


def _post_journal(db: Session, inv: SalesInvoice) -> None:
    ledger.post(db, on=inv.date, fy_label=inv.fy_label, source_type=SRC_INV, source_id=inv.id,
                narration=f"Sales invoice {inv.number} — {inv.party.name}", legs=_invoice_legs(inv))


def _fill(db: Session, inv: SalesInvoice, data: InvoiceIn) -> None:
    party = load_party(db, data.party_id, customer=True)
    fy = ensure_open_period(db, data.date)
    supply, totals = build_totals(db, party, data.lines)
    inv.party_id, inv.party = party.id, party
    inv.date = data.date
    inv.fy_label = fy.label
    inv.due_date = due_date_for(party, data.date, data.due_date)
    inv.reference, inv.notes = data.reference, data.notes
    apply_totals(inv, SalesInvoiceLine, supply, party.state_code, totals)


def _check_credit_limit(db: Session, inv: SalesInvoice) -> str | None:
    """Returns a warning (not an error) when the dealer would exceed their credit limit."""
    party = inv.party
    if not party.credit_limit or party.credit_limit <= 0:
        return None
    outstanding = ledger.balance(db, ledger.DEBTORS, party_id=party.id)
    after = outstanding + inv.grand_total
    if after > party.credit_limit:
        return f"{party.name} will be ₹{after - party.credit_limit:,.2f} over their credit limit."
    return None


def create_invoice(db: Session, actor: Actor, data: InvoiceIn, *, post_now: bool = False) -> tuple[SalesInvoice, str | None]:
    inv = SalesInvoice(status="draft", created_by_id=actor.id)
    _fill(db, inv, data)
    db.add(inv)
    db.flush()
    audit.record(db, actor, "create", SRC_INV, inv.id, f"Draft invoice for {inv.party.name}, ₹{inv.grand_total}")
    warning = _check_credit_limit(db, inv)
    if post_now:
        post_invoice(db, actor, inv.id)
    return inv, warning


def update_invoice(db: Session, actor: Actor, inv_id: int, data: InvoiceIn) -> SalesInvoice:
    inv = get_or_404(db, SalesInvoice, inv_id, "Invoice")
    if inv.is_opening:
        raise DomainError("Opening balances can't be edited here. Cancel and re-enter instead.")
    old = snapshot(inv)
    if inv.status == "cancelled":
        raise DomainError("This invoice is cancelled.")
    if inv.status == "posted":
        if not actor.can("sales.edit_posted"):
            raise DomainError("Only the Accounts Manager can edit a posted invoice.", 403)
        if has_allocations(db, sales_invoice_id=inv.id) or has_notes(db, sales_invoice_id=inv.id):
            raise DomainError("This invoice already has receipts or credit notes. Remove those first, "
                              "or raise a credit note instead.")
        ensure_open_period(db, inv.date)
        old_fy = inv.fy_label
        _fill(db, inv, data)
        if inv.fy_label != old_fy:
            raise DomainError("A posted invoice can't be moved to a different financial year.")
        ledger.reverse(db, source_type=SRC_INV, source_id=inv.id, on=inv.date, fy_label=inv.fy_label,
                       narration=f"Edit of {inv.number}: reverse previous posting")
        db.flush()
        _post_journal(db, inv)
    else:
        _fill(db, inv, data)
    db.flush()
    audit.record(db, actor, "update", SRC_INV, inv.id, f"Edited invoice {inv.number or '(draft)'}",
                 old=old, new=snapshot(inv))
    return inv


def post_invoice(db: Session, actor: Actor, inv_id: int) -> SalesInvoice:
    inv = get_or_404(db, SalesInvoice, inv_id, "Invoice")
    if inv.status != "draft":
        raise DomainError(f"Only draft invoices can be posted (this one is {inv.status}).")
    if not actor.can("sales.post"):
        raise DomainError("You don't have permission to post invoices.", 403)
    fy = ensure_open_period(db, inv.date)
    inv.number = next_number(db, SRC_INV, fy.label)
    inv.status, inv.posted_by_id, inv.posted_at = "posted", actor.id, _now()
    db.flush()
    _post_journal(db, inv)
    audit.record(db, actor, "post", SRC_INV, inv.id, f"Posted {inv.number} — {inv.party.name} ₹{inv.grand_total}")
    return inv


def delete_draft(db: Session, actor: Actor, inv_id: int) -> None:
    inv = get_or_404(db, SalesInvoice, inv_id, "Invoice")
    if inv.status != "draft":
        raise DomainError("Only drafts can be deleted. Posted invoices must be cancelled.")
    audit.record(db, actor, "delete_draft", SRC_INV, inv.id, f"Deleted draft for {inv.party.name}", old=snapshot(inv))
    db.delete(inv)


def cancel_invoice(db: Session, actor: Actor, inv_id: int, body: CancelIn) -> SalesInvoice:
    inv = get_or_404(db, SalesInvoice, inv_id, "Invoice")
    if inv.status != "posted":
        raise DomainError("Only posted invoices can be cancelled (delete drafts instead).")
    if has_allocations(db, sales_invoice_id=inv.id) or has_notes(db, sales_invoice_id=inv.id):
        raise DomainError("Cancel the receipts / credit notes linked to this invoice first.")
    ensure_open_period(db, inv.date)
    ledger.reverse(db, source_type=SRC_INV, source_id=inv.id, on=inv.date, fy_label=inv.fy_label,
                   narration=f"Cancellation of {inv.number}: {body.reason}")
    inv.status, inv.cancel_reason, inv.cancelled_by_id, inv.cancelled_at = "cancelled", body.reason, actor.id, _now()
    audit.record(db, actor, "cancel", SRC_INV, inv.id, f"Cancelled {inv.number}: {body.reason}")
    return inv


def create_opening_invoice(db: Session, actor: Actor, data: OpeningDocIn) -> SalesInvoice:
    """Outstanding dealer invoice carried over from Tally/Excel. Keeps the original invoice number."""
    party = load_party(db, data.party_id, customer=True)
    fy = ensure_open_period(db, data.date)
    inv = SalesInvoice(
        status="posted", is_opening=True, created_by_id=actor.id, posted_by_id=actor.id, posted_at=_now(),
        number=f"OB-{data.ref_no}"[:16], party_id=party.id, party=party, date=data.date, fy_label=fy.label,
        due_date=due_date_for(party, data.date, data.due_date), notes=data.notes, supply_type="intra",
        place_of_supply=party.state_code, taxable_total=ZERO, grand_total=data.amount)
    db.add(inv)
    db.flush()
    _post_journal(db, inv)
    audit.record(db, actor, "create", SRC_INV, inv.id, f"Opening balance {inv.number} for {party.name} ₹{data.amount}")
    return inv


# ---------- Credit notes ----------
def create_credit_note(db: Session, actor: Actor, data: CreditNoteIn) -> CreditNote:
    inv = get_or_404(db, SalesInvoice, data.sales_invoice_id, "Invoice")
    if inv.status != "posted":
        raise DomainError("Credit notes can only be raised against posted invoices.")
    if inv.is_opening:
        raise DomainError("For opening balances, record a receipt or adjust with your CA instead.")
    if data.date < inv.date:
        raise DomainError("Credit note date cannot be before the invoice date.")
    fy = ensure_open_period(db, data.date)
    supply, totals = build_totals(db, inv.party, data.lines)
    if supply != inv.supply_type:
        raise DomainError("Tax type does not match the original invoice.")
    balance = inv.grand_total - sales_settled(db, [inv.id])[inv.id]
    if totals.grand_total > balance:
        raise DomainError(f"Credit note (₹{totals.grand_total}) is more than the invoice balance (₹{balance}).")
    cn = CreditNote(status="posted", created_by_id=actor.id, posted_by_id=actor.id, posted_at=_now(),
                    party_id=inv.party_id, party=inv.party, sales_invoice_id=inv.id, invoice=inv,
                    date=data.date, fy_label=fy.label, reason=data.reason, notes=data.notes)
    apply_totals(cn, CreditNoteLine, supply, inv.place_of_supply, totals)
    cn.number = next_number(db, SRC_CN, fy.label)
    db.add(cn)
    db.flush()
    legs = [dr(ledger.SALES_RETURNS, cn.taxable_total),
            dr(ledger.OUT_CGST, cn.cgst_total), dr(ledger.OUT_SGST, cn.sgst_total), dr(ledger.OUT_IGST, cn.igst_total),
            cr(ledger.DEBTORS, cn.grand_total, party_id=cn.party_id)]
    if cn.round_off:
        legs.append(dr(ledger.ROUND_OFF, cn.round_off))
    ledger.post(db, on=cn.date, fy_label=fy.label, source_type=SRC_CN, source_id=cn.id,
                narration=f"Credit note {cn.number} against {inv.number}: {cn.reason}", legs=legs)
    audit.record(db, actor, "post", SRC_CN, cn.id, f"Credit note {cn.number} against {inv.number} ₹{cn.grand_total}")
    return cn


def cancel_credit_note(db: Session, actor: Actor, cn_id: int, body: CancelIn) -> CreditNote:
    cn = get_or_404(db, CreditNote, cn_id, "Credit note")
    if cn.status != "posted":
        raise DomainError("Only posted credit notes can be cancelled.")
    ensure_open_period(db, cn.date)
    ledger.reverse(db, source_type=SRC_CN, source_id=cn.id, on=cn.date, fy_label=cn.fy_label,
                   narration=f"Cancellation of {cn.number}: {body.reason}")
    cn.status, cn.cancel_reason, cn.cancelled_by_id, cn.cancelled_at = "cancelled", body.reason, actor.id, _now()
    audit.record(db, actor, "cancel", SRC_CN, cn.id, f"Cancelled {cn.number}: {body.reason}")
    return cn
