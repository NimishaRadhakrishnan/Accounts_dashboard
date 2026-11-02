"""Receipts, payments, allocations, expenses, contra (cash/bank transfers)."""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.core.errors import DomainError
from app.core.money import ZERO, D
from app.models import (Allocation, BankAccount, ContraEntry, Expense, ExpenseCategory, Payment, PurchaseBill,
                        Receipt, SalesInvoice)
from app.schemas import AllocationIn, CancelIn, ContraIn, ExpenseIn, PaymentIn, ReceiptIn, RejectIn
from app.services import audit, gst, ledger
from app.services.common import ensure_open_period, next_number, setting_decimal
from app.services.docs_common import get_or_404, load_party, purchase_settled, sales_settled
from app.services.ledger import cr, dr

SRC_RC, SRC_PY, SRC_EX, SRC_CT = "receipt", "payment", "expense", "contra"


def _now():
    return datetime.now(timezone.utc)


def _bank(db: Session, bank_id: int) -> BankAccount:
    b = get_or_404(db, BankAccount, bank_id, "Bank / cash account")
    if not b.is_active:
        raise DomainError(f"{b.name} is marked inactive.")
    return b


def bank_balance(db: Session, bank_id: int, as_of: date | None = None) -> Decimal:
    return ledger.balance(db, ledger.CASH_BANK, bank_account_id=bank_id, as_of=as_of)


def _ensure_cash_available(db: Session, bank: BankAccount, amount: Decimal, on: date) -> None:
    if bank.kind != "cash":
        return
    available = bank_balance(db, bank.id, as_of=on)
    if amount > available:
        raise DomainError(f"Not enough cash in {bank.name} on {on:%d-%m-%Y} (available ₹{available}).")


# ---------- Allocation helpers ----------
def _open_invoices(db: Session, party_id: int) -> list[tuple[SalesInvoice, Decimal]]:
    invs = db.scalars(select(SalesInvoice).where(SalesInvoice.party_id == party_id, SalesInvoice.status == "posted")
                      .order_by(SalesInvoice.due_date, SalesInvoice.date, SalesInvoice.id)).all()
    settled = sales_settled(db, [i.id for i in invs])
    return [(i, i.grand_total - settled[i.id]) for i in invs if i.grand_total - settled[i.id] > 0]


def _open_bills(db: Session, party_id: int) -> list[tuple[PurchaseBill, Decimal]]:
    bills = db.scalars(select(PurchaseBill).where(PurchaseBill.party_id == party_id, PurchaseBill.status == "posted")
                       .order_by(PurchaseBill.due_date, PurchaseBill.date, PurchaseBill.id)).all()
    settled = purchase_settled(db, [b.id for b in bills], include_pending=True)
    return [(b, b.grand_total - settled[b.id]) for b in bills if b.grand_total - settled[b.id] > 0]


def _plan_allocations(open_docs, available: Decimal, requested: list[AllocationIn] | None, what: str):
    """Returns [(doc, amount)]. Auto mode pays oldest due first."""
    plan = []
    if requested is None:
        left = available
        for doc, bal in open_docs:
            if left <= 0:
                break
            take = min(bal, left)
            plan.append((doc, take))
            left -= take
        return plan
    by_id = {doc.id: (doc, bal) for doc, bal in open_docs}
    total = ZERO
    seen = set()
    for a in requested:
        if a.doc_id in seen:
            raise DomainError(f"The same {what} is listed twice.")
        seen.add(a.doc_id)
        if a.doc_id not in by_id:
            raise DomainError(f"{what.capitalize()} #{a.doc_id} is not open for this party.")
        doc, bal = by_id[a.doc_id]
        if a.amount > bal:
            raise DomainError(f"₹{a.amount} is more than the balance ₹{bal} on {doc.number}.")
        plan.append((doc, D(a.amount)))
        total += D(a.amount)
    if total > available:
        raise DomainError(f"Allocated ₹{total} is more than the available ₹{available}.")
    return plan


def unallocated(db: Session, voucher) -> Decimal:
    used = sum((a.amount for a in voucher.allocations), ZERO)
    return voucher.amount - used


# ---------- Receipts ----------
def create_receipt(db: Session, actor: Actor, data: ReceiptIn) -> Receipt:
    party = load_party(db, data.party_id, customer=True)
    bank = _bank(db, data.bank_account_id)
    if data.mode == "cash" and bank.kind != "cash":
        raise DomainError("Cash receipts must go to a cash account.")
    fy = ensure_open_period(db, data.date)
    rc = Receipt(status="posted", created_by_id=actor.id, posted_by_id=actor.id, posted_at=_now(),
                 number=next_number(db, SRC_RC, fy.label), fy_label=fy.label, date=data.date, party_id=party.id,
                 party=party, bank_account_id=bank.id, bank_account=bank, amount=data.amount, mode=data.mode,
                 reference=data.reference, notes=data.notes)
    db.add(rc)
    db.flush()
    for inv, amt in _plan_allocations(_open_invoices(db, party.id), rc.amount, data.allocations, "invoice"):
        rc.allocations.append(Allocation(sales_invoice_id=inv.id, amount=amt))
    ledger.post(db, on=rc.date, fy_label=fy.label, source_type=SRC_RC, source_id=rc.id,
                narration=f"Receipt {rc.number} from {party.name} ({rc.mode} {rc.reference or ''})".strip(),
                legs=[dr(ledger.CASH_BANK, rc.amount, bank_account_id=bank.id),
                      cr(ledger.DEBTORS, rc.amount, party_id=party.id)])
    db.flush()
    audit.record(db, actor, "post", SRC_RC, rc.id, f"Receipt {rc.number} from {party.name} ₹{rc.amount}, "
                 f"allocated ₹{rc.amount - unallocated(db, rc)}")
    return rc


def allocate_receipt(db: Session, actor: Actor, rc_id: int, allocations: list[AllocationIn] | None) -> Receipt:
    rc = get_or_404(db, Receipt, rc_id, "Receipt")
    if rc.status != "posted":
        raise DomainError("Only posted receipts can be allocated.")
    free = unallocated(db, rc)
    if free <= 0:
        raise DomainError("This receipt is fully allocated already.")
    for inv, amt in _plan_allocations(_open_invoices(db, rc.party_id), free, allocations, "invoice"):
        rc.allocations.append(Allocation(sales_invoice_id=inv.id, amount=amt))
    db.flush()
    audit.record(db, actor, "allocate", SRC_RC, rc.id, f"Allocated advance on {rc.number}")
    return rc


def cancel_receipt(db: Session, actor: Actor, rc_id: int, body: CancelIn) -> Receipt:
    rc = get_or_404(db, Receipt, rc_id, "Receipt")
    if rc.status != "posted":
        raise DomainError("Only posted receipts can be cancelled.")
    ensure_open_period(db, rc.date)
    ledger.reverse(db, source_type=SRC_RC, source_id=rc.id, on=rc.date, fy_label=rc.fy_label,
                   narration=f"Cancellation of {rc.number}: {body.reason}")
    rc.status, rc.cancel_reason, rc.cancelled_by_id, rc.cancelled_at = "cancelled", body.reason, actor.id, _now()
    audit.record(db, actor, "cancel", SRC_RC, rc.id, f"Cancelled {rc.number}: {body.reason}")
    return rc


# ---------- Payments ----------
def _post_payment(db: Session, actor: Actor, py: Payment) -> None:
    fy = ensure_open_period(db, py.date)
    _ensure_cash_available(db, py.bank_account, py.amount, py.date)
    py.number = next_number(db, SRC_PY, fy.label)
    py.status, py.posted_by_id, py.posted_at = "posted", actor.id, _now()
    db.flush()
    ledger.post(db, on=py.date, fy_label=fy.label, source_type=SRC_PY, source_id=py.id,
                narration=f"Payment {py.number} to {py.party.name} ({py.mode} {py.reference or ''})".strip(),
                legs=[dr(ledger.CREDITORS, py.amount, party_id=py.party_id),
                      cr(ledger.CASH_BANK, py.amount, bank_account_id=py.bank_account_id)])


def create_payment(db: Session, actor: Actor, data: PaymentIn) -> Payment:
    party = load_party(db, data.party_id, supplier=True)
    bank = _bank(db, data.bank_account_id)
    if data.mode == "cash" and bank.kind != "cash":
        raise DomainError("Cash payments must come from a cash account.")
    fy = ensure_open_period(db, data.date)
    py = Payment(status="pending_approval", created_by_id=actor.id, fy_label=fy.label, date=data.date,
                 party_id=party.id, party=party, bank_account_id=bank.id, bank_account=bank, amount=data.amount,
                 mode=data.mode, reference=data.reference, notes=data.notes)
    db.add(py)
    db.flush()
    for bill, amt in _plan_allocations(_open_bills(db, party.id), py.amount, data.allocations, "bill"):
        py.allocations.append(Allocation(purchase_bill_id=bill.id, amount=amt))
    needs_approval = py.amount > setting_decimal(db, "payment_approval_limit") and not actor.can("payments.approve")
    if needs_approval:
        audit.record(db, actor, "create", SRC_PY, py.id, f"Payment to {party.name} ₹{py.amount} sent for approval")
    else:
        _post_payment(db, actor, py)
        py.approved_by_id = actor.id
        audit.record(db, actor, "post", SRC_PY, py.id, f"Payment {py.number} to {party.name} ₹{py.amount}")
    db.flush()
    return py


def approve_payment(db: Session, actor: Actor, py_id: int) -> Payment:
    py = get_or_404(db, Payment, py_id, "Payment")
    if py.status != "pending_approval":
        raise DomainError("This payment is not waiting for approval.")
    if py.created_by_id == actor.id:
        raise DomainError("A different person must approve this payment.")
    py.approved_by_id = actor.id
    _post_payment(db, actor, py)
    audit.record(db, actor, "approve", SRC_PY, py.id, f"Approved payment {py.number} ₹{py.amount}")
    return py


def reject_payment(db: Session, actor: Actor, py_id: int, body: RejectIn) -> Payment:
    py = get_or_404(db, Payment, py_id, "Payment")
    if py.status != "pending_approval":
        raise DomainError("This payment is not waiting for approval.")
    py.status, py.cancel_reason, py.cancelled_by_id, py.cancelled_at = "rejected", body.reason, actor.id, _now()
    audit.record(db, actor, "reject", SRC_PY, py.id, f"Rejected payment to {py.party.name}: {body.reason}")
    return py


def allocate_payment(db: Session, actor: Actor, py_id: int, allocations: list[AllocationIn] | None) -> Payment:
    py = get_or_404(db, Payment, py_id, "Payment")
    if py.status != "posted":
        raise DomainError("Only posted payments can be allocated.")
    free = unallocated(db, py)
    if free <= 0:
        raise DomainError("This payment is fully allocated already.")
    for bill, amt in _plan_allocations(_open_bills(db, py.party_id), free, allocations, "bill"):
        py.allocations.append(Allocation(purchase_bill_id=bill.id, amount=amt))
    db.flush()
    audit.record(db, actor, "allocate", SRC_PY, py.id, f"Allocated advance on {py.number}")
    return py


def cancel_payment(db: Session, actor: Actor, py_id: int, body: CancelIn) -> Payment:
    py = get_or_404(db, Payment, py_id, "Payment")
    if py.status != "posted":
        raise DomainError("Only posted payments can be cancelled (reject pending ones instead).")
    ensure_open_period(db, py.date)
    ledger.reverse(db, source_type=SRC_PY, source_id=py.id, on=py.date, fy_label=py.fy_label,
                   narration=f"Cancellation of {py.number}: {body.reason}")
    py.status, py.cancel_reason, py.cancelled_by_id, py.cancelled_at = "cancelled", body.reason, actor.id, _now()
    audit.record(db, actor, "cancel", SRC_PY, py.id, f"Cancelled {py.number}: {body.reason}")
    return py


# ---------- Expenses ----------
def _post_expense(db: Session, actor: Actor, ex: Expense) -> None:
    fy = ensure_open_period(db, ex.date)
    _ensure_cash_available(db, ex.bank_account, ex.total, ex.date)
    ex.number = next_number(db, SRC_EX, fy.label)
    ex.status, ex.posted_by_id, ex.posted_at = "posted", actor.id, _now()
    db.flush()
    tax = ex.cgst + ex.sgst + ex.igst
    cat_code = ex.category.account.code
    if ex.gst_claimable:
        legs = [dr(cat_code, ex.amount), dr(ledger.IN_CGST, ex.cgst), dr(ledger.IN_SGST, ex.sgst),
                dr(ledger.IN_IGST, ex.igst)]
    else:
        legs = [dr(cat_code, ex.amount + tax)]
    legs.append(cr(ledger.CASH_BANK, ex.total, bank_account_id=ex.bank_account_id))
    ledger.post(db, on=ex.date, fy_label=fy.label, source_type=SRC_EX, source_id=ex.id,
                narration=f"Expense {ex.number}: {ex.category.name} — {ex.payee}", legs=legs)


def create_expense(db: Session, actor: Actor, data: ExpenseIn) -> Expense:
    cat = get_or_404(db, ExpenseCategory, data.category_id, "Expense category")
    if not cat.is_active:
        raise DomainError(f"Category {cat.name} is inactive.")
    bank = _bank(db, data.bank_account_id)
    if data.mode == "cash" and bank.kind != "cash":
        raise DomainError("Cash expenses must be paid from a cash account.")
    if data.gst_claimable and not data.supplier_gstin:
        raise DomainError("To claim GST input credit, enter the supplier's GSTIN.")
    fy = ensure_open_period(db, data.date)
    cgst, sgst, igst = gst.compute_simple_tax(data.amount, data.gst_rate, data.supply_type)
    ex = Expense(status="pending_approval", created_by_id=actor.id, fy_label=fy.label, date=data.date,
                 category_id=cat.id, category=cat, bank_account_id=bank.id, bank_account=bank, payee=data.payee,
                 description=data.description, mode=data.mode, bill_no=data.bill_no,
                 supplier_gstin=data.supplier_gstin, supply_type=data.supply_type, amount=data.amount,
                 gst_rate=data.gst_rate, gst_claimable=data.gst_claimable, cgst=cgst, sgst=sgst, igst=igst,
                 total=data.amount + cgst + sgst + igst, notes=data.notes)
    db.add(ex)
    db.flush()
    needs_approval = ex.total > setting_decimal(db, "expense_approval_limit") and not actor.can("expenses.approve")
    if needs_approval:
        audit.record(db, actor, "create", SRC_EX, ex.id, f"Expense ₹{ex.total} ({cat.name}) sent for approval")
    else:
        ex.approved_by_id = actor.id
        _post_expense(db, actor, ex)
        audit.record(db, actor, "post", SRC_EX, ex.id, f"Expense {ex.number} ₹{ex.total} ({cat.name})")
    return ex


def approve_expense(db: Session, actor: Actor, ex_id: int) -> Expense:
    ex = get_or_404(db, Expense, ex_id, "Expense")
    if ex.status != "pending_approval":
        raise DomainError("This expense is not waiting for approval.")
    if ex.created_by_id == actor.id:
        raise DomainError("A different person must approve this expense.")
    ex.approved_by_id = actor.id
    _post_expense(db, actor, ex)
    audit.record(db, actor, "approve", SRC_EX, ex.id, f"Approved expense {ex.number} ₹{ex.total}")
    return ex


def reject_expense(db: Session, actor: Actor, ex_id: int, body: RejectIn) -> Expense:
    ex = get_or_404(db, Expense, ex_id, "Expense")
    if ex.status != "pending_approval":
        raise DomainError("This expense is not waiting for approval.")
    ex.status, ex.reject_reason, ex.cancelled_by_id, ex.cancelled_at = "rejected", body.reason, actor.id, _now()
    audit.record(db, actor, "reject", SRC_EX, ex.id, f"Rejected expense ₹{ex.total}: {body.reason}")
    return ex


def cancel_expense(db: Session, actor: Actor, ex_id: int, body: CancelIn) -> Expense:
    ex = get_or_404(db, Expense, ex_id, "Expense")
    if ex.status != "posted":
        raise DomainError("Only posted expenses can be cancelled.")
    ensure_open_period(db, ex.date)
    ledger.reverse(db, source_type=SRC_EX, source_id=ex.id, on=ex.date, fy_label=ex.fy_label,
                   narration=f"Cancellation of {ex.number}: {body.reason}")
    ex.status, ex.cancel_reason, ex.cancelled_by_id, ex.cancelled_at = "cancelled", body.reason, actor.id, _now()
    audit.record(db, actor, "cancel", SRC_EX, ex.id, f"Cancelled {ex.number}: {body.reason}")
    return ex


# ---------- Contra ----------
def create_contra(db: Session, actor: Actor, data: ContraIn) -> ContraEntry:
    if data.from_account_id == data.to_account_id:
        raise DomainError("From and To accounts must be different.")
    src, dst = _bank(db, data.from_account_id), _bank(db, data.to_account_id)
    fy = ensure_open_period(db, data.date)
    _ensure_cash_available(db, src, data.amount, data.date)
    ct = ContraEntry(status="posted", created_by_id=actor.id, posted_by_id=actor.id, posted_at=_now(),
                     number=next_number(db, SRC_CT, fy.label), fy_label=fy.label, date=data.date,
                     from_account_id=src.id, to_account_id=dst.id, amount=data.amount, reference=data.reference,
                     notes=data.notes)
    db.add(ct)
    db.flush()
    ledger.post(db, on=ct.date, fy_label=fy.label, source_type=SRC_CT, source_id=ct.id,
                narration=f"Transfer {ct.number}: {src.name} → {dst.name}",
                legs=[dr(ledger.CASH_BANK, ct.amount, bank_account_id=dst.id),
                      cr(ledger.CASH_BANK, ct.amount, bank_account_id=src.id)])
    audit.record(db, actor, "post", SRC_CT, ct.id, f"Transfer {ct.number} ₹{ct.amount} {src.name} → {dst.name}")
    return ct


def cancel_contra(db: Session, actor: Actor, ct_id: int, body: CancelIn) -> ContraEntry:
    ct = get_or_404(db, ContraEntry, ct_id, "Transfer")
    if ct.status != "posted":
        raise DomainError("Only posted transfers can be cancelled.")
    ensure_open_period(db, ct.date)
    ledger.reverse(db, source_type=SRC_CT, source_id=ct.id, on=ct.date, fy_label=ct.fy_label,
                   narration=f"Cancellation of {ct.number}: {body.reason}")
    ct.status, ct.cancel_reason, ct.cancelled_by_id, ct.cancelled_at = "cancelled", body.reason, actor.id, _now()
    audit.record(db, actor, "cancel", SRC_CT, ct.id, f"Cancelled {ct.number}: {body.reason}")
    return ct


def post_bank_opening(db: Session, bank: BankAccount, fy_label: str) -> None:
    """Opening balance journal for a bank/cash account (called from masters)."""
    if ledger.active_entry(db, "bank_opening", bank.id):
        ledger.reverse(db, source_type="bank_opening", source_id=bank.id, on=bank.opening_date or date.today(),
                       fy_label=fy_label, narration=f"Opening balance change — {bank.name}")
    if bank.opening_balance:
        ledger.post(db, on=bank.opening_date or date.today(), fy_label=fy_label, source_type="bank_opening",
                    source_id=bank.id, narration=f"Opening balance — {bank.name}",
                    legs=[dr(ledger.CASH_BANK, bank.opening_balance, bank_account_id=bank.id),
                          cr(ledger.OPENING_EQUITY, bank.opening_balance)])


_ = func
