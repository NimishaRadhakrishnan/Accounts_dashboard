"""Purchase bills (maker-checker) and debit notes."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.core.errors import DomainError
from app.core.money import ZERO
from app.models import DebitNote, DebitNoteLine, PurchaseBill, PurchaseBillLine
from app.schemas import BillIn, CancelIn, DebitNoteIn, OpeningDocIn
from app.services import audit, ledger
from app.services.common import ensure_open_period, next_number, setting_bool, snapshot
from app.services.docs_common import (apply_totals, build_totals, due_date_for, get_or_404, has_allocations,
                                      has_notes, load_party, purchase_settled)
from app.services.ledger import cr, dr

SRC_BILL = "purchase_bill"
SRC_DN = "debit_note"


def _now():
    return datetime.now(timezone.utc)


def _bill_legs(b: PurchaseBill) -> list[ledger.Leg]:
    if b.is_opening:
        return [dr(ledger.OPENING_EQUITY, b.grand_total), cr(ledger.CREDITORS, b.grand_total, party_id=b.party_id)]
    legs = [dr(ledger.PURCHASES, b.taxable_total),
            dr(ledger.IN_CGST, b.cgst_total), dr(ledger.IN_SGST, b.sgst_total), dr(ledger.IN_IGST, b.igst_total),
            cr(ledger.CREDITORS, b.grand_total, party_id=b.party_id)]
    if b.round_off:
        legs.append(dr(ledger.ROUND_OFF, b.round_off))
    return legs


def _post_journal(db: Session, b: PurchaseBill) -> None:
    ledger.post(db, on=b.date, fy_label=b.fy_label, source_type=SRC_BILL, source_id=b.id,
                narration=f"Purchase bill {b.number} (supplier bill {b.supplier_bill_no}) — {b.party.name}",
                legs=_bill_legs(b))


def _check_duplicate(db: Session, b: PurchaseBill) -> None:
    dup = db.scalar(select(PurchaseBill).where(
        PurchaseBill.party_id == b.party_id, PurchaseBill.supplier_bill_no == b.supplier_bill_no,
        PurchaseBill.fy_label == b.fy_label, PurchaseBill.status != "cancelled", PurchaseBill.id != (b.id or 0)))
    if dup:
        raise DomainError(f"Supplier bill {b.supplier_bill_no} from {b.party.name} is already entered "
                          f"({dup.number or 'draft'}).")


def _fill(db: Session, b: PurchaseBill, data: BillIn) -> None:
    party = load_party(db, data.party_id, supplier=True)
    fy = ensure_open_period(db, data.date)
    supply, totals = build_totals(db, party, data.lines)
    b.party_id, b.party = party.id, party
    b.supplier_bill_no = data.supplier_bill_no.strip()
    b.date, b.fy_label = data.date, fy.label
    b.due_date = due_date_for(party, data.date, data.due_date)
    b.notes = data.notes
    apply_totals(b, PurchaseBillLine, supply, party.state_code, totals)
    _check_duplicate(db, b)


def create_bill(db: Session, actor: Actor, data: BillIn) -> PurchaseBill:
    b = PurchaseBill(status="draft", created_by_id=actor.id)
    _fill(db, b, data)
    db.add(b)
    db.flush()
    audit.record(db, actor, "create", SRC_BILL, b.id,
                 f"Bill {b.supplier_bill_no} from {b.party.name} ₹{b.grand_total} (awaiting verification)")
    if not setting_bool(db, "purchase_maker_checker") and actor.can("purchases.verify"):
        verify_bill(db, actor, b.id)
    return b


def update_bill(db: Session, actor: Actor, bill_id: int, data: BillIn) -> PurchaseBill:
    b = get_or_404(db, PurchaseBill, bill_id, "Bill")
    if b.is_opening:
        raise DomainError("Opening balances can't be edited here. Cancel and re-enter instead.")
    old = snapshot(b)
    if b.status == "cancelled":
        raise DomainError("This bill is cancelled.")
    if b.status == "posted":
        if not actor.can("purchases.edit_posted"):
            raise DomainError("Only the Accounts Manager can edit a posted bill.", 403)
        if has_allocations(db, purchase_bill_id=b.id) or has_notes(db, purchase_bill_id=b.id):
            raise DomainError("This bill already has payments or debit notes. Remove those first.")
        ensure_open_period(db, b.date)
        old_fy = b.fy_label
        _fill(db, b, data)
        if b.fy_label != old_fy:
            raise DomainError("A posted bill can't be moved to a different financial year.")
        ledger.reverse(db, source_type=SRC_BILL, source_id=b.id, on=b.date, fy_label=b.fy_label,
                       narration=f"Edit of {b.number}: reverse previous posting")
        db.flush()
        _post_journal(db, b)
    else:
        _fill(db, b, data)
    db.flush()
    audit.record(db, actor, "update", SRC_BILL, b.id, f"Edited bill {b.number or b.supplier_bill_no}",
                 old=old, new=snapshot(b))
    return b


def verify_bill(db: Session, actor: Actor, bill_id: int) -> PurchaseBill:
    b = get_or_404(db, PurchaseBill, bill_id, "Bill")
    if b.status != "draft":
        raise DomainError(f"Only bills awaiting verification can be verified (this one is {b.status}).")
    if not actor.can("purchases.verify"):
        raise DomainError("You don't have permission to verify bills.", 403)
    if setting_bool(db, "purchase_maker_checker") and b.created_by_id == actor.id:
        raise DomainError("A different person must verify this bill (maker-checker is on).")
    fy = ensure_open_period(db, b.date)
    b.number = next_number(db, SRC_BILL, fy.label)
    b.status, b.verified_by_id, b.posted_by_id, b.posted_at = "posted", actor.id, actor.id, _now()
    db.flush()
    _post_journal(db, b)
    audit.record(db, actor, "post", SRC_BILL, b.id, f"Verified and posted {b.number} — {b.party.name} ₹{b.grand_total}")
    return b


def delete_draft(db: Session, actor: Actor, bill_id: int) -> None:
    b = get_or_404(db, PurchaseBill, bill_id, "Bill")
    if b.status != "draft":
        raise DomainError("Only unverified bills can be deleted. Posted bills must be cancelled.")
    audit.record(db, actor, "delete_draft", SRC_BILL, b.id, f"Deleted unverified bill {b.supplier_bill_no}",
                 old=snapshot(b))
    db.delete(b)


def cancel_bill(db: Session, actor: Actor, bill_id: int, body: CancelIn) -> PurchaseBill:
    b = get_or_404(db, PurchaseBill, bill_id, "Bill")
    if b.status != "posted":
        raise DomainError("Only posted bills can be cancelled.")
    if has_allocations(db, purchase_bill_id=b.id) or has_notes(db, purchase_bill_id=b.id):
        raise DomainError("Cancel the payments / debit notes linked to this bill first.")
    ensure_open_period(db, b.date)
    ledger.reverse(db, source_type=SRC_BILL, source_id=b.id, on=b.date, fy_label=b.fy_label,
                   narration=f"Cancellation of {b.number}: {body.reason}")
    b.status, b.cancel_reason, b.cancelled_by_id, b.cancelled_at = "cancelled", body.reason, actor.id, _now()
    audit.record(db, actor, "cancel", SRC_BILL, b.id, f"Cancelled {b.number}: {body.reason}")
    return b


def create_opening_bill(db: Session, actor: Actor, data: OpeningDocIn) -> PurchaseBill:
    party = load_party(db, data.party_id, supplier=True)
    fy = ensure_open_period(db, data.date)
    b = PurchaseBill(
        status="posted", is_opening=True, created_by_id=actor.id, posted_by_id=actor.id, verified_by_id=actor.id,
        posted_at=_now(), number=f"OB-{data.ref_no}"[:16], supplier_bill_no=data.ref_no, party_id=party.id,
        party=party, date=data.date, fy_label=fy.label, due_date=due_date_for(party, data.date, data.due_date),
        notes=data.notes, supply_type="intra", place_of_supply=party.state_code, taxable_total=ZERO,
        grand_total=data.amount)
    _check_duplicate(db, b)
    db.add(b)
    db.flush()
    _post_journal(db, b)
    audit.record(db, actor, "create", SRC_BILL, b.id, f"Opening balance {b.number} for {party.name} ₹{data.amount}")
    return b


# ---------- Debit notes ----------
def create_debit_note(db: Session, actor: Actor, data: DebitNoteIn) -> DebitNote:
    b = get_or_404(db, PurchaseBill, data.purchase_bill_id, "Bill")
    if b.status != "posted":
        raise DomainError("Debit notes can only be raised against posted bills.")
    if b.is_opening:
        raise DomainError("For opening balances, record a payment or adjust with your CA instead.")
    if data.date < b.date:
        raise DomainError("Debit note date cannot be before the bill date.")
    fy = ensure_open_period(db, data.date)
    supply, totals = build_totals(db, b.party, data.lines)
    balance = b.grand_total - purchase_settled(db, [b.id], include_pending=True)[b.id]
    if totals.grand_total > balance:
        raise DomainError(f"Debit note (₹{totals.grand_total}) is more than the bill balance (₹{balance}).")
    dn = DebitNote(status="posted", created_by_id=actor.id, posted_by_id=actor.id, posted_at=_now(),
                   party_id=b.party_id, party=b.party, purchase_bill_id=b.id, bill=b,
                   date=data.date, fy_label=fy.label, reason=data.reason, notes=data.notes)
    apply_totals(dn, DebitNoteLine, supply, b.place_of_supply, totals)
    dn.number = next_number(db, SRC_DN, fy.label)
    db.add(dn)
    db.flush()
    legs = [dr(ledger.CREDITORS, dn.grand_total, party_id=dn.party_id),
            cr(ledger.PURCHASE_RETURNS, dn.taxable_total),
            cr(ledger.IN_CGST, dn.cgst_total), cr(ledger.IN_SGST, dn.sgst_total), cr(ledger.IN_IGST, dn.igst_total)]
    if dn.round_off:
        legs.append(cr(ledger.ROUND_OFF, dn.round_off))
    ledger.post(db, on=dn.date, fy_label=fy.label, source_type=SRC_DN, source_id=dn.id,
                narration=f"Debit note {dn.number} against {b.number}: {dn.reason}", legs=legs)
    audit.record(db, actor, "post", SRC_DN, dn.id, f"Debit note {dn.number} against {b.number} ₹{dn.grand_total}")
    return dn


def cancel_debit_note(db: Session, actor: Actor, dn_id: int, body: CancelIn) -> DebitNote:
    dn = get_or_404(db, DebitNote, dn_id, "Debit note")
    if dn.status != "posted":
        raise DomainError("Only posted debit notes can be cancelled.")
    ensure_open_period(db, dn.date)
    ledger.reverse(db, source_type=SRC_DN, source_id=dn.id, on=dn.date, fy_label=dn.fy_label,
                   narration=f"Cancellation of {dn.number}: {body.reason}")
    dn.status, dn.cancel_reason, dn.cancelled_by_id, dn.cancelled_at = "cancelled", body.reason, actor.id, _now()
    audit.record(db, actor, "cancel", SRC_DN, dn.id, f"Cancelled {dn.number}: {body.reason}")
    return dn
