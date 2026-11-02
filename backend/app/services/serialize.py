"""Turn ORM objects into JSON-ready dicts for the API."""
from datetime import date

from sqlalchemy.orm import Session

from app.models import (BankAccount, ContraEntry, CreditNote, DebitNote, Expense, Party, Payment, Product,
                        PurchaseBill, Receipt, SalesInvoice, User)
from app.services.docs_common import payment_state, purchase_settled, sales_settled


def user(u: User) -> dict:
    return {"id": u.id, "full_name": u.full_name, "username": u.username, "email": u.email,
            "role": {"code": u.role.code, "name": u.role.name}, "is_active": u.is_active,
            "must_change_password": u.must_change_password, "last_login_at": u.last_login_at,
            "locked": bool(u.locked_until and u.locked_until.timestamp() > __import__("time").time()),
            "permissions": sorted(u.permission_codes)}


def party(p: Party) -> dict:
    return {"id": p.id, "code": p.code, "name": p.name, "is_customer": p.is_customer, "is_supplier": p.is_supplier,
            "gstin": p.gstin, "pan": p.pan, "contact_person": p.contact_person, "phone": p.phone, "email": p.email,
            "address": p.address, "city": p.city, "district": p.district, "state_code": p.state_code,
            "state_name": p.state_name, "pincode": p.pincode, "payment_term_id": p.payment_term_id,
            "payment_term": p.payment_term.name if p.payment_term else None, "credit_days": p.credit_days,
            "credit_limit": p.credit_limit, "tally_ledger_name": p.tally_ledger_name, "is_active": p.is_active,
            "notes": p.notes}


def product(p: Product) -> dict:
    return {k: getattr(p, k) for k in ("id", "code", "name", "category", "hsn_code", "unit", "gst_rate",
                                       "sale_price", "purchase_price", "is_active")}


def bank(b: BankAccount, balance=None) -> dict:
    d = {k: getattr(b, k) for k in ("id", "name", "kind", "bank_name", "last4", "ifsc", "opening_balance",
                                    "opening_date", "tally_ledger_name", "is_active")}
    if balance is not None:
        d["balance"] = balance
    return d


def _lines(lines) -> list[dict]:
    return [{k: getattr(ln, k) for k in ("line_no", "product_id", "description", "hsn_code", "qty", "unit", "rate",
                                         "discount_pct", "discount_amount", "taxable", "gst_rate", "cgst", "sgst",
                                         "igst", "total")} for ln in lines]


def _header(doc) -> dict:
    return {"id": doc.id, "number": doc.number, "fy_label": doc.fy_label, "date": doc.date, "status": doc.status,
            "notes": doc.notes, "created_at": doc.created_at, "posted_at": doc.posted_at,
            "cancelled_at": doc.cancelled_at, "cancel_reason": doc.cancel_reason,
            "created_by_id": doc.created_by_id}


def _tax(doc) -> dict:
    return {k: getattr(doc, k) for k in ("supply_type", "place_of_supply", "taxable_total", "discount_total",
                                         "cgst_total", "sgst_total", "igst_total", "round_off", "grand_total")}


def _party_brief(p: Party) -> dict:
    return {"id": p.id, "code": p.code, "name": p.name, "gstin": p.gstin, "state_name": p.state_name,
            "state_code": p.state_code}


def invoice_list(db: Session, invs: list[SalesInvoice], today: date | None = None) -> list[dict]:
    settled = sales_settled(db, [i.id for i in invs])
    return [{**_header(i), **_tax(i), "party": _party_brief(i.party), "due_date": i.due_date,
             "reference": i.reference, "is_opening": i.is_opening,
             **payment_state(i.grand_total, settled[i.id], i.due_date, i.status, today)} for i in invs]


def invoice(db: Session, i: SalesInvoice) -> dict:
    d = invoice_list(db, [i])[0]
    d["lines"] = _lines(i.lines)
    return d


def bill_list(db: Session, bills: list[PurchaseBill], today: date | None = None) -> list[dict]:
    settled = purchase_settled(db, [b.id for b in bills])
    return [{**_header(b), **_tax(b), "party": _party_brief(b.party), "due_date": b.due_date,
             "supplier_bill_no": b.supplier_bill_no, "is_opening": b.is_opening, "verified_by_id": b.verified_by_id,
             **payment_state(b.grand_total, settled[b.id], b.due_date, b.status, today)} for b in bills]


def bill(db: Session, b: PurchaseBill) -> dict:
    d = bill_list(db, [b])[0]
    d["lines"] = _lines(b.lines)
    return d


def credit_note(cn: CreditNote) -> dict:
    return {**_header(cn), **_tax(cn), "party": _party_brief(cn.party), "reason": cn.reason,
            "sales_invoice_id": cn.sales_invoice_id, "invoice_number": cn.invoice.number, "lines": _lines(cn.lines)}


def debit_note(dn: DebitNote) -> dict:
    return {**_header(dn), **_tax(dn), "party": _party_brief(dn.party), "reason": dn.reason,
            "purchase_bill_id": dn.purchase_bill_id, "bill_number": dn.bill.number, "lines": _lines(dn.lines)}


def _money_voucher(v, doc_attr: str) -> dict:
    allocs = []
    for a in v.allocations:
        doc = getattr(a, doc_attr)
        allocs.append({"doc_id": doc.id, "number": doc.number, "date": doc.date, "amount": a.amount})
    used = sum((a.amount for a in v.allocations), 0)
    return {**_header(v), "party": _party_brief(v.party), "bank_account": {"id": v.bank_account.id,
                                                                            "name": v.bank_account.name},
            "amount": v.amount, "mode": v.mode, "reference": v.reference, "allocations": allocs,
            "allocated": used, "unallocated": v.amount - used}


def receipt(r: Receipt) -> dict:
    return _money_voucher(r, "sales_invoice")


def payment(p: Payment) -> dict:
    return {**_money_voucher(p, "purchase_bill"), "approved_by_id": p.approved_by_id}


def expense(e: Expense) -> dict:
    return {**_header(e), "category": {"id": e.category.id, "name": e.category.name},
            "bank_account": {"id": e.bank_account.id, "name": e.bank_account.name}, "payee": e.payee,
            "description": e.description, "mode": e.mode, "bill_no": e.bill_no, "supplier_gstin": e.supplier_gstin,
            "supply_type": e.supply_type, "amount": e.amount, "gst_rate": e.gst_rate, "gst_claimable": e.gst_claimable,
            "cgst": e.cgst, "sgst": e.sgst, "igst": e.igst, "total": e.total, "approved_by_id": e.approved_by_id,
            "reject_reason": e.reject_reason}


def contra(c: ContraEntry) -> dict:
    return {**_header(c), "from_account": {"id": c.from_account.id, "name": c.from_account.name},
            "to_account": {"id": c.to_account.id, "name": c.to_account.name}, "amount": c.amount,
            "reference": c.reference}
