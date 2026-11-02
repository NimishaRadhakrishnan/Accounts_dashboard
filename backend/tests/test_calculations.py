"""Pure calculation tests — GST, rounding, Indian formatting."""
from decimal import Decimal as D

import pytest

from app.core.errors import DomainError
from app.core.money import amount_in_words, inr
from app.services.gst import LineInput, compute_document, compute_simple_tax


def L(qty, rate, gst, disc="0"):
    return LineInput(description="x", qty=D(qty), rate=D(rate), gst_rate=D(gst), discount_pct=D(disc))


def test_intra_state_splits_cgst_sgst():
    t = compute_document([L(10, "320", 5)], "intra")
    assert t.taxable_total == D("3200.00")
    assert t.cgst_total == D("80.00") and t.sgst_total == D("80.00") and t.igst_total == 0
    assert t.grand_total == D("3360.00") and t.round_off == 0


def test_inter_state_uses_igst():
    t = compute_document([L(10, "320", 5)], "inter")
    assert t.igst_total == D("160.00") and t.cgst_total == 0 and t.sgst_total == 0
    assert t.grand_total == D("3360.00")


def test_discount_and_round_off():
    # 7 x 333.33 = 2333.31; 2% disc = 46.67 -> 2286.64; 18% -> 9% each = 205.80 / 205.80
    t = compute_document([L(7, "333.33", 18, "2")], "intra")
    ln = t.lines[0]
    assert ln.discount_amount == D("46.67")
    assert ln.taxable == D("2286.64")
    assert ln.cgst == D("205.80") and ln.sgst == D("205.80")
    assert t.grand_total == D("2698.00")
    assert t.round_off == D("-0.24")
    assert t.taxable_total + t.tax_total + t.round_off == t.grand_total


def test_round_half_up_to_rupee():
    t = compute_document([L(1, "100.48", 0)], "intra")
    assert t.grand_total == D("100.00") and t.round_off == D("-0.48")
    t = compute_document([L(1, "100.50", 0)], "intra")
    assert t.grand_total == D("101.00") and t.round_off == D("0.50")


def test_mixed_rates_sum():
    t = compute_document([L(10, "320", 5), L(4, "450", 18)], "inter")
    assert t.taxable_total == D("5000.00")
    assert t.igst_total == D("160.00") + D("324.00")


@pytest.mark.parametrize("bad", [L(0, 10, 5), L(1, -1, 5), L(1, 10, 7), L(1, 10, 5, "101")])
def test_invalid_lines_rejected(bad):
    with pytest.raises(DomainError):
        compute_document([bad], "intra")


def test_simple_tax():
    assert compute_simple_tax(D("1000"), D("18"), "intra") == (D("90.00"), D("90.00"), D("0"))
    assert compute_simple_tax(D("1000"), D("18"), "inter") == (D("0"), D("0"), D("180.00"))


def test_indian_number_format():
    assert inr(D("1234567.5")) == "12,34,567.50"
    assert inr(D("999")) == "999.00"
    assert inr(D("-100000")) == "-1,00,000.00"
    assert inr(D("123456789.01")) == "12,34,56,789.01"


def test_amount_in_words():
    assert amount_in_words(D("3360")) == "Rupees Three Thousand Three Hundred Sixty Only"
    assert amount_in_words(D("1234567.50")) == \
        "Rupees Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven and Fifty Paise Only"
    assert amount_in_words(D("10000000")) == "Rupees One Crore Only"
