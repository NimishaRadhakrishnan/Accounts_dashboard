"""End-to-end accounting rules through the service layer."""
from datetime import date
from decimal import Decimal as D

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.errors import DomainError
from app.models import JournalEntry
from app.schemas import (AllocationIn, BillIn, CancelIn, ContraIn, CreditNoteIn, DebitNoteIn, ExpenseIn, InvoiceIn,
                         LineIn, OpeningDocIn, PaymentIn, PeriodLockIn, ReceiptIn, RejectIn)
from app.services import cash, ledger, masters, purchases, sales, tally
from app.services.dashboard import overview
from app.services.outstanding import ageing
from app.services.reports import gst_summary, profit_and_loss, sales_register, trial_balance_report

APR10 = date(2026, 4, 10)


def line(w, qty="10", rate="320", gst="5"):
    return LineIn(product_id=w.prod.id, description="Azospirillum", qty=D(qty), rate=D(rate), gst_rate=D(gst))


def invoice(w, party=None, on=APR10, **kw):
    inv, _ = sales.create_invoice(w.db, w.acct, InvoiceIn(party_id=(party or w.tn).id, date=on,
                                                          lines=[line(w, **kw)]), post_now=True)
    return inv


def assert_books_balance(db):
    total = db.execute(text("select coalesce(sum(debit),0), coalesce(sum(credit),0) from journal_lines")).one()
    assert total[0] == total[1]


# ---------- Sales ----------
def test_invoice_numbering_and_posting(w):
    a = invoice(w)
    b = invoice(w, party=w.kl)
    assert a.number == "VBT/26-27/0001" and b.number == "VBT/26-27/0002"
    assert a.supply_type == "intra" and b.supply_type == "inter"
    assert a.due_date == date(2026, 5, 10)
    assert ledger.balance(w.db, ledger.DEBTORS, party_id=w.tn.id) == D("3360.00")
    assert ledger.balance(w.db, ledger.OUT_IGST) == D("-160.00")
    assert_books_balance(w.db)


def test_draft_gets_number_only_when_posted(w):
    inv, _ = sales.create_invoice(w.db, w.acct, InvoiceIn(party_id=w.tn.id, date=APR10, lines=[line(w)]))
    assert inv.number is None and inv.status == "draft"
    assert ledger.balance(w.db, ledger.DEBTORS) == 0
    sales.post_invoice(w.db, w.acct, inv.id)
    assert inv.number == "VBT/26-27/0001"


def test_credit_limit_warning(w):
    _, warn = sales.create_invoice(w.db, w.acct, InvoiceIn(party_id=w.tn.id, date=APR10,
                                                           lines=[line(w, qty="400")]), post_now=True)
    assert warn and "over their credit limit" in warn


def test_cancel_reverses_and_keeps_number(w):
    inv = invoice(w)
    sales.cancel_invoice(w.db, w.mgr, inv.id, CancelIn(reason="Wrong dealer"))
    assert inv.status == "cancelled" and inv.number == "VBT/26-27/0001"
    assert ledger.balance(w.db, ledger.DEBTORS) == 0
    assert invoice(w).number == "VBT/26-27/0002"  # never reused


def test_edit_posted_invoice_requires_manager_and_reposts(w):
    inv = invoice(w)
    data = InvoiceIn(party_id=w.tn.id, date=APR10, lines=[line(w, qty="20")])
    with pytest.raises(DomainError):
        sales.update_invoice(w.db, w.acct, inv.id, data)
    sales.update_invoice(w.db, w.mgr, inv.id, data)
    assert ledger.balance(w.db, ledger.DEBTORS) == D("6720.00")
    assert inv.number == "VBT/26-27/0001"


def test_credit_note_limited_to_balance(w):
    inv = invoice(w)
    cn = sales.create_credit_note(w.db, w.acct, CreditNoteIn(sales_invoice_id=inv.id, date=date(2026, 4, 12),
                                                             reason="Damaged", lines=[line(w, qty="2")]))
    assert cn.grand_total == D("672.00") and cn.number == "CN/26-27/0001"
    assert ledger.balance(w.db, ledger.DEBTORS) == D("2688.00")
    with pytest.raises(DomainError, match="more than the invoice balance"):
        sales.create_credit_note(w.db, w.acct, CreditNoteIn(sales_invoice_id=inv.id, date=date(2026, 4, 12),
                                                            reason="Again", lines=[line(w, qty="9")]))


# ---------- Receipts & allocation ----------
def test_receipt_auto_allocates_oldest_first_and_tracks_advance(w):
    i1 = invoice(w, on=date(2026, 4, 5))
    i2 = invoice(w, on=date(2026, 4, 20))
    rc = cash.create_receipt(w.db, w.acct, ReceiptIn(party_id=w.tn.id, date=date(2026, 5, 1),
                                                     bank_account_id=w.bank.id, amount=D("5000"), mode="neft"))
    assert [(a.sales_invoice_id, a.amount) for a in rc.allocations] == [(i1.id, D("3360.00")), (i2.id, D("1640.00"))]
    rc2 = cash.create_receipt(w.db, w.acct, ReceiptIn(party_id=w.tn.id, date=date(2026, 5, 2),
                                                      bank_account_id=w.bank.id, amount=D("3000"), mode="upi"))
    assert cash.unallocated(w.db, rc2) == D("1280.00")  # 1720 settles i2, rest is advance
    a = ageing(w.db, "receivable", date(2026, 5, 2))
    assert a["gross"] == 0 and a["advances"] == D("1280.00") and a["net"] == D("-1280.00")
    assert a["net"] == ledger.balance(w.db, ledger.DEBTORS)


def test_manual_allocation_validation(w):
    inv = invoice(w)
    with pytest.raises(DomainError, match="more than the balance"):
        cash.create_receipt(w.db, w.acct, ReceiptIn(party_id=w.tn.id, date=APR10, bank_account_id=w.bank.id,
                                                    amount=D("5000"), mode="neft",
                                                    allocations=[AllocationIn(doc_id=inv.id, amount=D("4000"))]))
    other = invoice(w, party=w.kl)
    with pytest.raises(DomainError, match="not open for this party"):
        cash.create_receipt(w.db, w.acct, ReceiptIn(party_id=w.tn.id, date=APR10, bank_account_id=w.bank.id,
                                                    amount=D("100"), mode="neft",
                                                    allocations=[AllocationIn(doc_id=other.id, amount=D("100"))]))


def test_cannot_cancel_invoice_with_receipt(w):
    inv = invoice(w)
    rc = cash.create_receipt(w.db, w.acct, ReceiptIn(party_id=w.tn.id, date=APR10, bank_account_id=w.bank.id,
                                                     amount=D("1000"), mode="neft"))
    with pytest.raises(DomainError, match="Cancel the receipts"):
        sales.cancel_invoice(w.db, w.mgr, inv.id, CancelIn(reason="test"))
    cash.cancel_receipt(w.db, w.mgr, rc.id, CancelIn(reason="bounced cheque"))
    sales.cancel_invoice(w.db, w.mgr, inv.id, CancelIn(reason="test"))
    assert ledger.balance(w.db, ledger.DEBTORS) == 0
    assert ledger.balance(w.db, ledger.CASH_BANK, bank_account_id=w.bank.id) == D("100000.00")


def test_cash_receipt_must_use_cash_account(w):
    invoice(w)
    with pytest.raises(DomainError, match="cash account"):
        cash.create_receipt(w.db, w.acct, ReceiptIn(party_id=w.tn.id, date=APR10, bank_account_id=w.bank.id,
                                                    amount=D("100"), mode="cash"))


# ---------- Purchases (maker-checker) ----------
def bill(w, no="B-1", on=APR10, qty="100", rate="50", gst="18"):
    return purchases.create_bill(w.db, w.acct, BillIn(party_id=w.sup.id, supplier_bill_no=no, date=on, lines=[
        LineIn(description="Bottles", qty=D(qty), rate=D(rate), gst_rate=D(gst))]))


def test_purchase_needs_second_person(w):
    b = bill(w)
    assert b.status == "draft" and b.number is None
    with pytest.raises(DomainError):
        purchases.verify_bill(w.db, w.acct, b.id)  # accountant has no verify permission
    w.mgr.user.id  # noqa: B018
    purchases.verify_bill(w.db, w.mgr, b.id)
    assert b.status == "posted" and b.number == "PB/26-27/0001"
    assert ledger.balance(w.db, ledger.CREDITORS, party_id=w.sup.id) == D("-5900.00")
    assert ledger.balance(w.db, ledger.IN_CGST) == D("450.00")


def test_manager_cannot_verify_own_bill(w):
    b = purchases.create_bill(w.db, w.mgr, BillIn(party_id=w.sup.id, supplier_bill_no="X", date=APR10, lines=[
        LineIn(description="Bottles", qty=D(1), rate=D(100), gst_rate=D(0))]))
    with pytest.raises(DomainError, match="different person"):
        purchases.verify_bill(w.db, w.mgr, b.id)


def test_duplicate_supplier_bill_blocked(w):
    bill(w, no="INV-55")
    with pytest.raises(DomainError, match="already entered"):
        bill(w, no="INV-55")


def test_debit_note_and_payment(w):
    b = bill(w)
    purchases.verify_bill(w.db, w.mgr, b.id)
    purchases.create_debit_note(w.db, w.acct, DebitNoteIn(purchase_bill_id=b.id, date=date(2026, 4, 15),
                                                          reason="Short supply", lines=[
        LineIn(description="Bottles", qty=D(10), rate=D(50), gst_rate=D(18))]))
    py = cash.create_payment(w.db, w.acct, PaymentIn(party_id=w.sup.id, date=date(2026, 4, 20),
                                                     bank_account_id=w.bank.id, amount=D("5310"), mode="neft"))
    assert py.status == "posted" and py.allocations[0].amount == D("5310.00")
    assert ageing(w.db, "payable", date(2026, 4, 20))["net"] == 0
    assert ledger.balance(w.db, ledger.CREDITORS) == 0


def test_large_payment_needs_approval(w):
    b = bill(w, qty="3000")  # 1,77,000
    purchases.verify_bill(w.db, w.mgr, b.id)
    small = cash.create_payment(w.db, w.acct, PaymentIn(party_id=w.sup.id, date=APR10, bank_account_id=w.bank.id,
                                                        amount=D("20000"), mode="neft"))
    assert small.status == "posted"  # under the ₹1,00,000 limit
    py = cash.create_payment(w.db, w.acct, PaymentIn(party_id=w.sup.id, date=APR10, bank_account_id=w.bank.id,
                                                     amount=D("150000"), mode="neft"))
    assert py.status == "pending_approval" and py.number is None
    assert ledger.balance(w.db, ledger.CASH_BANK, bank_account_id=w.bank.id) == D("80000.00")
    # the pending payment reserves the bill, so a second one can only take what is left
    py2 = cash.create_payment(w.db, w.acct, PaymentIn(party_id=w.sup.id, date=APR10, bank_account_id=w.bank.id,
                                                      amount=D("120000"), mode="neft"))
    assert sum(a.amount for a in py2.allocations) == D("7000.00")
    cash.reject_payment(w.db, w.ceo, py2.id, RejectIn(reason="Pay in two parts"))
    cash.approve_payment(w.db, w.ceo, py.id)
    assert py.status == "posted" and py.number == "PY/26-27/0002"
    assert ledger.balance(w.db, ledger.CASH_BANK, bank_account_id=w.bank.id) == D("-70000.00")
    assert ageing(w.db, "payable", APR10)["gross"] == D("7000.00")


# ---------- Expenses, cash, contra ----------
def test_expense_with_gst_credit_and_approval(w):
    small = cash.create_expense(w.db, w.acct, ExpenseIn(date=APR10, category_id=w.cat.id, bank_account_id=w.cash.id,
                                                        payee="Auto", description="Local travel", amount=D("400")))
    assert small.status == "posted"
    big = cash.create_expense(w.db, w.acct, ExpenseIn(
        date=APR10, category_id=w.cat.id, bank_account_id=w.bank.id, payee="Hotel", description="Stay",
        mode="neft", amount=D("10000"), gst_rate=D("18"), gst_claimable=True, supplier_gstin="33AAAFZ9999Z1Z9"))
    assert big.status == "pending_approval"
    with pytest.raises(DomainError, match="different person"):
        cash.approve_expense(w.db, w.acct, big.id)
    cash.approve_expense(w.db, w.mgr, big.id)
    assert big.total == D("11800.00")
    assert ledger.balance(w.db, w.cat.account.code) == D("10400.00")
    assert ledger.balance(w.db, ledger.IN_SGST) == D("900.00")


def test_cash_cannot_go_negative(w):
    with pytest.raises(DomainError, match="Not enough cash"):
        cash.create_expense(w.db, w.mgr, ExpenseIn(date=APR10, category_id=w.cat.id, bank_account_id=w.cash.id,
                                                   payee="Xyz", description="Too much", amount=D("6000")))
    cash.create_contra(w.db, w.acct, ContraIn(date=APR10, from_account_id=w.bank.id, to_account_id=w.cash.id,
                                              amount=D("10000")))
    cash.create_expense(w.db, w.mgr, ExpenseIn(date=APR10, category_id=w.cat.id, bank_account_id=w.cash.id,
                                               payee="Xyz", description="Now fine", amount=D("6000")))
    assert ledger.balance(w.db, ledger.CASH_BANK, bank_account_id=w.cash.id) == D("9000.00")


# ---------- Controls ----------
def test_locked_period_blocks_entries(w):
    masters.lock_period(w.db, w.mgr, PeriodLockIn(year=2026, month=4))
    with pytest.raises(DomainError, match="locked"):
        invoice(w)
    invoice(w, on=date(2026, 5, 1))


def test_opening_balance_invoice(w):
    ob = sales.create_opening_invoice(w.db, w.admin, OpeningDocIn(party_id=w.tn.id, ref_no="25-812",
                                                                  date=date(2026, 3, 1), amount=D("50000")))
    assert ob.number == "OB-25-812" and ob.fy_label == "25-26"
    assert ledger.balance(w.db, ledger.OPENING_EQUITY) == D("-155000.00")  # 1,05,000 bank/cash + 50,000
    a = ageing(w.db, "receivable", date(2026, 6, 1))
    assert a["items"][0]["bucket"] == "d61_90"


def test_journal_is_append_only_and_balanced(w):
    invoice(w)
    w.db.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        w.db.execute(text("UPDATE journal_lines SET debit = debit + 1"))
    w.db.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        w.db.execute(text("DELETE FROM audit_logs"))
    w.db.rollback()
    entry = w.db.scalar(select(JournalEntry).limit(1))
    w.db.execute(text("INSERT INTO journal_lines (entry_id, account_id, debit, credit) "
                      "VALUES (:e, :a, 5, 0)"), {"e": entry.id, "a": ledger.account_id(w.db, ledger.SALES)})
    with pytest.raises(DBAPIError, match="does not balance"):
        w.db.commit()
    w.db.rollback()


# ---------- Reports & exports ----------
def test_reports_reconcile(w):
    invoice(w)
    invoice(w, party=w.kl, gst="18", rate="450", qty="4")
    b = bill(w)
    purchases.verify_bill(w.db, w.mgr, b.id)
    end = date(2026, 4, 30)
    reg = sales_register(w.db, date(2026, 4, 1), end)
    assert reg.totals["total"] == D("3360.00") + D("2124.00")
    g = gst_summary(w.db, date(2026, 4, 1), end)
    net = next(r for r in g.rows if r["section"].startswith("Net"))
    assert net["tax"] == D("160.00") + D("324.00") - D("900.00")
    tb = trial_balance_report(w.db, date(2026, 4, 1), end)
    assert tb.totals["closing_dr"] == tb.totals["closing_cr"]
    pl = profit_and_loss(w.db, date(2026, 4, 1), end)
    assert pl.rows[-1]["amount"] == D("3200.00") + D("1800.00") - D("5000.00")
    o = overview(w.db, date(2026, 4, 30))
    assert o["kpis"]["receivables"] == D("5484.00") and o["kpis"]["payables"] == D("5900.00")
    assert o["kpis"]["cash_bank"] == D("105000.00")


def test_tally_export_skips_cancelled_and_opening(w):
    sales.create_opening_invoice(w.db, w.admin, OpeningDocIn(party_id=w.tn.id, ref_no="1", date=date(2026, 4, 1),
                                                             amount=D("100")))
    keep = invoice(w)
    gone = invoice(w)
    sales.cancel_invoice(w.db, w.mgr, gone.id, CancelIn(reason="dup"))
    xml, count = tally.export_vouchers(w.db, date(2026, 4, 1), date(2026, 4, 30))
    assert count == 1
    assert keep.number.encode() in xml and gone.number.encode() not in xml
    assert b"<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>" in xml and b"<AMOUNT>-3360.00</AMOUNT>" in xml
