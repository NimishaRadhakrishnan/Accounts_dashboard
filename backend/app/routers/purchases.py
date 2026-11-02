from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Actor, require
from app.core.errors import NotFound
from app.models import Allocation, DebitNote, Payment, PurchaseBill
from app.routers.common import ListParams, done, filtered, paginate
from app.schemas import BillIn, CancelIn, DebitNoteIn, OpeningDocIn
from app.services import purchases as svc
from app.services import serialize

router = APIRouter(prefix="/api", tags=["purchases"])


@router.get("/purchase-bills")
def list_bills(p: ListParams = Depends(), db: Session = Depends(get_db), _: Actor = Depends(require("purchases.view"))):
    q = filtered(PurchaseBill, p, search_cols=(PurchaseBill.supplier_bill_no,))
    items, meta = paginate(db, q, p, (PurchaseBill.date.desc(), PurchaseBill.id.desc()))
    return {"items": serialize.bill_list(db, items), **meta}


@router.get("/purchase-bills/{bill_id}")
def get_bill(bill_id: int, db: Session = Depends(get_db), _: Actor = Depends(require("purchases.view"))):
    b = db.get(PurchaseBill, bill_id)
    if not b:
        raise NotFound("Bill")
    d = serialize.bill(db, b)
    d["debit_notes"] = [{"id": n.id, "number": n.number, "date": n.date, "grand_total": n.grand_total,
                         "status": n.status, "reason": n.reason}
                        for n in db.scalars(select(DebitNote).where(DebitNote.purchase_bill_id == b.id))]
    d["payments"] = [{"id": py.id, "number": py.number, "date": py.date, "amount": a.amount, "status": py.status}
                     for a, py in db.execute(select(Allocation, Payment).join(Payment, Payment.id == Allocation.payment_id)
                                             .where(Allocation.purchase_bill_id == b.id))]
    return d


@router.post("/purchase-bills")
def create_bill(body: BillIn, db: Session = Depends(get_db), actor: Actor = Depends(require("purchases.create"))):
    return done(db, serialize.bill(db, svc.create_bill(db, actor, body)))


@router.put("/purchase-bills/{bill_id}")
def update_bill(bill_id: int, body: BillIn, db: Session = Depends(get_db),
                actor: Actor = Depends(require("purchases.create"))):
    return done(db, serialize.bill(db, svc.update_bill(db, actor, bill_id, body)))


@router.post("/purchase-bills/{bill_id}/verify")
def verify_bill(bill_id: int, db: Session = Depends(get_db), actor: Actor = Depends(require("purchases.verify"))):
    return done(db, serialize.bill(db, svc.verify_bill(db, actor, bill_id)))


@router.delete("/purchase-bills/{bill_id}")
def delete_draft(bill_id: int, db: Session = Depends(get_db), actor: Actor = Depends(require("purchases.create"))):
    svc.delete_draft(db, actor, bill_id)
    return done(db, {"ok": True})


@router.post("/purchase-bills/{bill_id}/cancel")
def cancel_bill(bill_id: int, body: CancelIn, db: Session = Depends(get_db),
                actor: Actor = Depends(require("purchases.cancel"))):
    return done(db, serialize.bill(db, svc.cancel_bill(db, actor, bill_id, body)))


@router.post("/purchase-bills/opening")
def create_opening(body: OpeningDocIn, db: Session = Depends(get_db), actor: Actor = Depends(require("masters.manage"))):
    return done(db, serialize.bill(db, svc.create_opening_bill(db, actor, body)))


@router.get("/debit-notes")
def list_debit_notes(p: ListParams = Depends(), db: Session = Depends(get_db),
                     _: Actor = Depends(require("purchases.view"))):
    items, meta = paginate(db, filtered(DebitNote, p, search_cols=(DebitNote.reason,)), p,
                           (DebitNote.date.desc(), DebitNote.id.desc()))
    return {"items": [serialize.debit_note(n) for n in items], **meta}


@router.post("/debit-notes")
def create_debit_note(body: DebitNoteIn, db: Session = Depends(get_db),
                      actor: Actor = Depends(require("purchases.create"))):
    return done(db, serialize.debit_note(svc.create_debit_note(db, actor, body)))


@router.post("/debit-notes/{dn_id}/cancel")
def cancel_debit_note(dn_id: int, body: CancelIn, db: Session = Depends(get_db),
                      actor: Actor = Depends(require("purchases.cancel"))):
    return done(db, serialize.debit_note(svc.cancel_debit_note(db, actor, dn_id, body)))
