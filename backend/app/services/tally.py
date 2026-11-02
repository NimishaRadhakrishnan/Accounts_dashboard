"""Export posted vouchers as Tally import XML (Gateway of Tally > Import > Vouchers).

Tally convention: debit amounts are negative with ISDEEMEDPOSITIVE=Yes, credits positive with No.
Ledger names must exist in Tally exactly as written — map them in Settings > Tally ledger names.
This must be tested on a copy of the company's Tally data before use (see README, 'Tally export').
"""
from datetime import date
from xml.etree.ElementTree import Element, SubElement, tostring

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import ZERO
from app.models import Account, BankAccount, JournalEntry, Party
from app.services.outstanding import _numbers

VOUCHER_TYPE = {
    "sales_invoice": "Sales", "credit_note": "Credit Note", "purchase_bill": "Purchase", "debit_note": "Debit Note",
    "receipt": "Receipt", "payment": "Payment", "expense": "Payment", "contra": "Contra",
}


def _ledger_names(db: Session) -> tuple[dict, dict, dict]:
    accounts = {a.id: (a.tally_ledger_name or a.name) for a in db.scalars(select(Account))}
    parties = {p.id: (p.tally_ledger_name or p.name) for p in db.scalars(select(Party))}
    banks = {b.id: (b.tally_ledger_name or b.name) for b in db.scalars(select(BankAccount))}
    return accounts, parties, banks


def export_vouchers(db: Session, start: date, end: date) -> tuple[bytes, int]:
    accounts, parties, banks = _ledger_names(db)
    entries = db.scalars(select(JournalEntry).where(
        JournalEntry.date >= start, JournalEntry.date <= end, JournalEntry.source_type.in_(VOUCHER_TYPE.keys()),
        JournalEntry.is_reversal.is_(False)).order_by(JournalEntry.date, JournalEntry.id)).all()
    # Skip entries that were later reversed (cancelled/edited) — Tally gets only live vouchers.
    reversed_ids = set(db.scalars(select(JournalEntry.reversed_entry_id).where(JournalEntry.is_reversal.is_(True))))
    entries = [e for e in entries if e.id not in reversed_ids and not _is_opening(db, e)]
    nums = _numbers(db, entries)

    env = Element("ENVELOPE")
    hdr = SubElement(env, "HEADER")
    SubElement(hdr, "TALLYREQUEST").text = "Import Data"
    body = SubElement(SubElement(env, "BODY"), "IMPORTDATA")
    rd = SubElement(body, "REQUESTDESC")
    SubElement(rd, "REPORTNAME").text = "Vouchers"
    data = SubElement(body, "REQUESTDATA")
    for e in entries:
        msg = SubElement(data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
        vtype = VOUCHER_TYPE[e.source_type]
        v = SubElement(msg, "VOUCHER", {"VCHTYPE": vtype, "ACTION": "Create"})
        SubElement(v, "DATE").text = e.date.strftime("%Y%m%d")
        SubElement(v, "VOUCHERTYPENAME").text = vtype
        SubElement(v, "VOUCHERNUMBER").text = nums.get((e.source_type, e.source_id), str(e.source_id))
        SubElement(v, "NARRATION").text = e.narration
        party_line = next((ln for ln in e.lines if ln.party_id), None)
        if party_line:
            SubElement(v, "PARTYLEDGERNAME").text = parties[party_line.party_id]
        for ln in e.lines:
            name = parties[ln.party_id] if ln.party_id else banks[ln.bank_account_id] if ln.bank_account_id \
                else accounts[ln.account_id]
            le = SubElement(v, "ALLLEDGERENTRIES.LIST")
            SubElement(le, "LEDGERNAME").text = name
            is_debit = ln.debit > ZERO
            SubElement(le, "ISDEEMEDPOSITIVE").text = "Yes" if is_debit else "No"
            amt = ln.debit if is_debit else ln.credit
            SubElement(le, "AMOUNT").text = f"{-amt if is_debit else amt:.2f}"
    xml = b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(env, encoding="utf-8")
    return xml, len(entries)


def _is_opening(db: Session, e: JournalEntry) -> bool:
    """Opening-balance documents are already in Tally — never re-export them."""
    from app.models import PurchaseBill, SalesInvoice
    if e.source_type == "sales_invoice":
        inv = db.get(SalesInvoice, e.source_id)
        return bool(inv and inv.is_opening)
    if e.source_type == "purchase_bill":
        b = db.get(PurchaseBill, e.source_id)
        return bool(b and b.is_opening)
    return False
