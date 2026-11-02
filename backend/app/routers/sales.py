from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Actor, require
from app.core.errors import NotFound
from app.models import CreditNote, SalesInvoice
from app.routers.common import ListParams, done, filtered, paginate
from app.schemas import CancelIn, CreditNoteIn, InvoiceIn, OpeningDocIn
from app.services import audit, serialize
from app.services import sales as svc
from app.services.common import company
from app.services.exports import invoice_pdf

router = APIRouter(prefix="/api", tags=["sales"])


@router.get("/sales-invoices")
def list_invoices(p: ListParams = Depends(), db: Session = Depends(get_db), _: Actor = Depends(require("sales.view"))):
    q = filtered(SalesInvoice, p, search_cols=(SalesInvoice.reference,))
    items, meta = paginate(db, q, p, (SalesInvoice.date.desc(), SalesInvoice.id.desc()))
    return {"items": serialize.invoice_list(db, items), **meta}


@router.get("/sales-invoices/{inv_id}")
def get_invoice(inv_id: int, db: Session = Depends(get_db), _: Actor = Depends(require("sales.view"))):
    inv = db.get(SalesInvoice, inv_id)
    if not inv:
        raise NotFound("Invoice")
    d = serialize.invoice(db, inv)
    d["credit_notes"] = [{"id": c.id, "number": c.number, "date": c.date, "grand_total": c.grand_total,
                          "status": c.status, "reason": c.reason}
                         for c in db.scalars(select(CreditNote).where(CreditNote.sales_invoice_id == inv.id))]
    from app.models import Allocation, Receipt
    d["receipts"] = [{"id": r.id, "number": r.number, "date": r.date, "amount": a.amount, "status": r.status}
                     for a, r in db.execute(select(Allocation, Receipt).join(Receipt, Receipt.id == Allocation.receipt_id)
                                            .where(Allocation.sales_invoice_id == inv.id))]
    return d


@router.post("/sales-invoices")
def create_invoice(body: InvoiceIn, post: bool = Query(False), db: Session = Depends(get_db),
                   actor: Actor = Depends(require("sales.create"))):
    inv, warning = svc.create_invoice(db, actor, body, post_now=post)
    return done(db, {**serialize.invoice(db, inv), "warning": warning})


@router.put("/sales-invoices/{inv_id}")
def update_invoice(inv_id: int, body: InvoiceIn, db: Session = Depends(get_db),
                   actor: Actor = Depends(require("sales.create"))):
    return done(db, serialize.invoice(db, svc.update_invoice(db, actor, inv_id, body)))


@router.post("/sales-invoices/{inv_id}/post")
def post_invoice(inv_id: int, db: Session = Depends(get_db), actor: Actor = Depends(require("sales.post"))):
    return done(db, serialize.invoice(db, svc.post_invoice(db, actor, inv_id)))


@router.delete("/sales-invoices/{inv_id}")
def delete_draft(inv_id: int, db: Session = Depends(get_db), actor: Actor = Depends(require("sales.create"))):
    svc.delete_draft(db, actor, inv_id)
    return done(db, {"ok": True})


@router.post("/sales-invoices/{inv_id}/cancel")
def cancel_invoice(inv_id: int, body: CancelIn, db: Session = Depends(get_db),
                   actor: Actor = Depends(require("sales.cancel"))):
    return done(db, serialize.invoice(db, svc.cancel_invoice(db, actor, inv_id, body)))


@router.post("/sales-invoices/opening")
def create_opening(body: OpeningDocIn, db: Session = Depends(get_db), actor: Actor = Depends(require("masters.manage"))):
    return done(db, serialize.invoice(db, svc.create_opening_invoice(db, actor, body)))


@router.get("/sales-invoices/{inv_id}/pdf")
def invoice_pdf_(inv_id: int, db: Session = Depends(get_db), actor: Actor = Depends(require("sales.view"))):
    inv = db.get(SalesInvoice, inv_id)
    if not inv:
        raise NotFound("Invoice")
    pdf = invoice_pdf(inv, company(db))
    audit.record(db, actor, "export", "sales_invoice", inv.id, f"Downloaded PDF of {inv.number or 'draft'}")
    db.commit()
    name = (inv.number or f"DRAFT-{inv.id}").replace("/", "-")
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


# ---------- Credit notes ----------
@router.get("/credit-notes")
def list_credit_notes(p: ListParams = Depends(), db: Session = Depends(get_db),
                      _: Actor = Depends(require("sales.view"))):
    items, meta = paginate(db, filtered(CreditNote, p, search_cols=(CreditNote.reason,)), p,
                           (CreditNote.date.desc(), CreditNote.id.desc()))
    return {"items": [serialize.credit_note(c) for c in items], **meta}


@router.post("/credit-notes")
def create_credit_note(body: CreditNoteIn, db: Session = Depends(get_db),
                       actor: Actor = Depends(require("sales.create"))):
    return done(db, serialize.credit_note(svc.create_credit_note(db, actor, body)))


@router.post("/credit-notes/{cn_id}/cancel")
def cancel_credit_note(cn_id: int, body: CancelIn, db: Session = Depends(get_db),
                       actor: Actor = Depends(require("sales.cancel"))):
    return done(db, serialize.credit_note(svc.cancel_credit_note(db, actor, cn_id, body)))
