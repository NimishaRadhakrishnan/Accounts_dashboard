"""Money helpers. All amounts are Decimal, never float."""
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0.00")
PAISA = Decimal("0.01")
RUPEE = Decimal("1")


def D(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def r2(value) -> Decimal:
    """Round to paise, half-up (standard commercial rounding)."""
    return D(value).quantize(PAISA, rounding=ROUND_HALF_UP)


def r0(value) -> Decimal:
    """Round to the nearest rupee, half-up."""
    return D(value).quantize(RUPEE, rounding=ROUND_HALF_UP).quantize(PAISA)


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
         "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
         "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def _three(n: int) -> str:
    h, rest = divmod(n, 100)
    parts = []
    if h:
        parts.append(_ONES[h] + " Hundred")
    if rest:
        parts.append(_two(rest))
    return " ".join(parts)


def amount_in_words(amount) -> str:
    """Indian numbering: 1,23,45,678.50 -> 'Rupees One Crore Twenty Three Lakh ... and Fifty Paise Only'."""
    amount = r2(amount)
    rupees = int(amount)
    paise = int((amount - rupees) * 100)
    if rupees == 0 and paise == 0:
        return "Rupees Zero Only"
    parts = []
    crore, rupees = divmod(rupees, 10_000_000)
    lakh, rupees = divmod(rupees, 100_000)
    thousand, rupees = divmod(rupees, 1000)
    if crore:
        parts.append(_three(crore) + " Crore" if crore < 1000 else amount_in_words(crore).replace("Rupees ", "").replace(" Only", "") + " Crore")
    if lakh:
        parts.append(_two(lakh) + " Lakh")
    if thousand:
        parts.append(_two(thousand) + " Thousand")
    if rupees:
        parts.append(_three(rupees))
    words = "Rupees " + " ".join(parts) if parts else "Rupees Zero"
    if paise:
        words += f" and {_two(paise)} Paise"
    return words + " Only"


def inr(amount) -> str:
    """Format as Indian currency grouping: 1234567.5 -> '12,34,567.50'."""
    amount = r2(amount)
    neg = amount < 0
    s = f"{abs(amount):.2f}"
    whole, frac = s.split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return ("-" if neg else "") + whole + "." + frac
