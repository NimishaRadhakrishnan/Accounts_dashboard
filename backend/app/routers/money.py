"""Receipts, payments, transfers, expenses."""
from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Actor, require
from app.core.errors import NotFound
from app.models import ContraEntry, Expense, Payment, Receipt
from app.routers.common import ListParams, done, filtered, paginate
from app.schemas import AllocationIn, CancelIn, ContraIn, ExpenseIn, PaymentIn, ReceiptIn, RejectIn
from app.services import cash as svc
from app.services import serialize
from app.services.outstanding import party_items

router = APIRouter(prefix="/api", tags=["payments, receipts & expenses"])


# ---------- Receipts ----------
@router.get("/receipts")
def list_receipts(p: ListParams = Depends(), db: Session = Depends(get_db), _: Actor = Depends(require("receipts.view"))):
    items, meta = paginate(db, filtered(Receipt, p, search_cols=(Receipt.reference,)), p,
                           (Receipt.date.desc(), Receipt.id.desc()))
    return {"items": [serialize.receipt(r) for r in items], **meta}


@router.get("/receipts/{rc_id}")
def get_receipt(rc_id: int, db: Session = Depends(get_db), _: Actor = Depends(require("receipts.view"))):
    r = db.get(Receipt, rc_id)
    if not r:
        raise NotFound("Receipt")
    return serialize.receipt(r)


@router.get("/parties/{party_id}/open-invoices")
def open_invoices(party_id: int, db: Session = Depends(get_db), _: Actor = Depends(require("receipts.view"))):
    return party_items(db, party_id, "receivable")


@router.post("/receipts")
def create_receipt(body: ReceiptIn, db: Session = Depends(get_db), actor: Actor = Depends(require("receipts.create"))):
    return done(db, serialize.receipt(svc.create_receipt(db, actor, body)))


@router.post("/receipts/{rc_id}/allocate")
def allocate_receipt(rc_id: int, allocations: list[AllocationIn] | None = Body(None, embed=True),
                     db: Session = Depends(get_db), actor: Actor = Depends(require("receipts.create"))):
    return done(db, serialize.receipt(svc.allocate_receipt(db, actor, rc_id, allocations)))


@router.post("/receipts/{rc_id}/cancel")
def cancel_receipt(rc_id: int, body: CancelIn, db: Session = Depends(get_db),
                   actor: Actor = Depends(require("receipts.cancel"))):
    return done(db, serialize.receipt(svc.cancel_receipt(db, actor, rc_id, body)))


# ---------- Payments ----------
@router.get("/payments")
def list_payments(p: ListParams = Depends(), db: Session = Depends(get_db), _: Actor = Depends(require("payments.view"))):
    items, meta = paginate(db, filtered(Payment, p, search_cols=(Payment.reference,)), p,
                           (Payment.date.desc(), Payment.id.desc()))
    return {"items": [serialize.payment(x) for x in items], **meta}


@router.get("/payments/{py_id}")
def get_payment(py_id: int, db: Session = Depends(get_db), _: Actor = Depends(require("payments.view"))):
    x = db.get(Payment, py_id)
    if not x:
        raise NotFound("Payment")
    return serialize.payment(x)


@router.get("/parties/{party_id}/open-bills")
def open_bills(party_id: int, db: Session = Depends(get_db), _: Actor = Depends(require("payments.view"))):
    return party_items(db, party_id, "payable")


@router.post("/payments")
def create_payment(body: PaymentIn, db: Session = Depends(get_db), actor: Actor = Depends(require("payments.create"))):
    return done(db, serialize.payment(svc.create_payment(db, actor, body)))


@router.post("/payments/{py_id}/approve")
def approve_payment(py_id: int, db: Session = Depends(get_db), actor: Actor = Depends(require("payments.approve"))):
    return done(db, serialize.payment(svc.approve_payment(db, actor, py_id)))


@router.post("/payments/{py_id}/reject")
def reject_payment(py_id: int, body: RejectIn, db: Session = Depends(get_db),
                   actor: Actor = Depends(require("payments.approve"))):
    return done(db, serialize.payment(svc.reject_payment(db, actor, py_id, body)))


@router.post("/payments/{py_id}/allocate")
def allocate_payment(py_id: int, allocations: list[AllocationIn] | None = Body(None, embed=True),
                     db: Session = Depends(get_db), actor: Actor = Depends(require("payments.create"))):
    return done(db, serialize.payment(svc.allocate_payment(db, actor, py_id, allocations)))


@router.post("/payments/{py_id}/cancel")
def cancel_payment(py_id: int, body: CancelIn, db: Session = Depends(get_db),
                   actor: Actor = Depends(require("payments.cancel"))):
    return done(db, serialize.payment(svc.cancel_payment(db, actor, py_id, body)))


# ---------- Transfers ----------
@router.get("/contra")
def list_contra(p: ListParams = Depends(), db: Session = Depends(get_db), _: Actor = Depends(require("receipts.view"))):
    items, meta = paginate(db, filtered(ContraEntry, p, search_cols=(ContraEntry.reference,)), p,
                           (ContraEntry.date.desc(), ContraEntry.id.desc()))
    return {"items": [serialize.contra(c) for c in items], **meta}


@router.post("/contra")
def create_contra(body: ContraIn, db: Session = Depends(get_db), actor: Actor = Depends(require("contra.create"))):
    return done(db, serialize.contra(svc.create_contra(db, actor, body)))


@router.post("/contra/{ct_id}/cancel")
def cancel_contra(ct_id: int, body: CancelIn, db: Session = Depends(get_db),
                  actor: Actor = Depends(require("payments.cancel"))):
    return done(db, serialize.contra(svc.cancel_contra(db, actor, ct_id, body)))


# ---------- Expenses ----------
@router.get("/expenses")
def list_expenses(p: ListParams = Depends(), category_id: int | None = None, db: Session = Depends(get_db),
                  _: Actor = Depends(require("expenses.view"))):
    q = filtered(Expense, p, search_cols=(Expense.payee, Expense.description, Expense.bill_no))
    if category_id:
        q = q.where(Expense.category_id == category_id)
    items, meta = paginate(db, q, p, (Expense.date.desc(), Expense.id.desc()))
    return {"items": [serialize.expense(e) for e in items], **meta}


@router.post("/expenses")
def create_expense(body: ExpenseIn, db: Session = Depends(get_db), actor: Actor = Depends(require("expenses.create"))):
    return done(db, serialize.expense(svc.create_expense(db, actor, body)))


@router.post("/expenses/{ex_id}/approve")
def approve_expense(ex_id: int, db: Session = Depends(get_db), actor: Actor = Depends(require("expenses.approve"))):
    return done(db, serialize.expense(svc.approve_expense(db, actor, ex_id)))


@router.post("/expenses/{ex_id}/reject")
def reject_expense(ex_id: int, body: RejectIn, db: Session = Depends(get_db),
                   actor: Actor = Depends(require("expenses.approve"))):
    return done(db, serialize.expense(svc.reject_expense(db, actor, ex_id, body)))


@router.post("/expenses/{ex_id}/cancel")
def cancel_expense(ex_id: int, body: CancelIn, db: Session = Depends(get_db),
                   actor: Actor = Depends(require("expenses.cancel"))):
    return done(db, serialize.expense(svc.cancel_expense(db, actor, ex_id, body)))
