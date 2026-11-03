"""Figures for the manager's overview, computed from the copy of Tally.

Everything here is read-only. Money is Decimal throughout and returned as strings.

How each figure is worked out (kept in plain words because the manager sees these explanations too):
* Sales          = net credits to ledgers under "Sales Accounts" (before GST, after returns).
* Money collected= amounts credited to dealers (Sundry Debtors) in entries that put money into cash or bank.
* Expenses       = net debits to ledgers under Direct + Indirect Expenses (salaries, rent, fuel, …). Purchases separate.
* Profit (est.)  = sales + other income − purchases − expenses ± change in stock value (when stock is kept in Tally).
* Cash & bank    = balances of ledgers under Cash-in-Hand and Bank Accounts.
* Dealers owe us = balances of ledgers under Sundry Debtors. How late: payments are matched to the oldest bills
                   first; a bill is late after the dealer's credit days (Tally's "Default credit period", else 30).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models import (TallyCompany, TallyLedger, TallyLine, TallyStockLine, TallyStockValue, TallySyncRun,
                        TallyVoucher)

IST = ZoneInfo("Asia/Kolkata")
ZERO = Decimal(0)
EXP = ("direct_exp", "indirect_exp")
INC = ("direct_inc", "indirect_inc")
BALANCE_SHEET = ("bank", "cash", "debtors", "creditors", "tax", "stock", "fixed", "capital", "loans", "other")
DEFAULT_CREDIT_DAYS = 30


def today_ist() -> date:
    return datetime.now(IST).date()


# ---------------------------------------------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class Span:
    start: date
    end: date

    def label(self) -> str:
        if self.start.day == 1 and (self.end + timedelta(days=1)).day == 1 and self.start.month == self.end.month:
            return f"{self.start:%B %Y}"
        if self.start.year == self.end.year and self.start.month == self.end.month:
            return f"{self.start.day}–{self.end.day} {self.end:%b %Y}"
        return f"{self.start.day} {self.start:%b %Y} – {self.end.day} {self.end:%b %Y}"


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    import calendar
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def month_end(d: date) -> date:
    return add_months(month_start(d), 1) - timedelta(days=1)


def fy_start(d: date) -> date:
    return date(d.year if d.month >= 4 else d.year - 1, 4, 1)


def shift_year(s: Span, years: int = -1) -> Span:
    def sh(d: date) -> date:
        try:
            return d.replace(year=d.year + years)
        except ValueError:  # 29 Feb
            return d.replace(year=d.year + years, day=28)
    return Span(sh(s.start), sh(s.end))


@dataclass
class Period:
    key: str
    title: str
    cur: Span
    cmp: Span          # main comparison shown on tiles
    cmp_label: str     # "1–3 Oct" / "last October"
    ly: Span           # same period last year (for the story)


def make_period(key: str, today: date) -> Period:
    if key == "month":
        cur = Span(month_start(today), today)
        pm = add_months(month_start(today), -1)
        cmp = Span(pm, min(pm + (today - cur.start), month_end(pm)))
        return Period(key, "This month", cur, cmp, f"same days last month ({cmp.label()})", shift_year(cur))
    if key == "last_month":
        s = add_months(month_start(today), -1)
        cur = Span(s, month_end(s))
        ps = add_months(s, -1)
        return Period(key, f"{s:%B}", cur, Span(ps, month_end(ps)), f"{ps:%B}", shift_year(cur))
    if key == "year":
        cur = Span(fy_start(today), today)
        ly = shift_year(cur)
        return Period(key, f"This year (from April {cur.start.year})", cur, ly,
                      f"same time last year ({ly.label()})", ly)
    raise DomainError("Unknown period.", 404)


# ---------------------------------------------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------------------------------------------
class Books:
    """Read helpers over the Tally copy for one company."""

    def __init__(self, db: Session, company: TallyCompany):
        self.db = db
        self.c = company
        self.ledgers = {lg.name: lg for lg in db.scalars(select(TallyLedger).where(TallyLedger.company_id == company.id))}
        self.as_of = company.closing_as_of or today_ist()

    def names(self, *cats: str) -> list[str]:
        return [n for n, lg in self.ledgers.items() if lg.category in cats]

    def _lines(self):
        return (select(TallyLine.ledger, TallyLine.dr, TallyVoucher.date, TallyVoucher.id)
                .join(TallyVoucher, TallyVoucher.id == TallyLine.voucher_id)
                .where(TallyVoucher.company_id == self.c.id, TallyVoucher.counted.is_(True)))

    def flow(self, cats: tuple[str, ...], s: Span, by_ledger: bool = False):
        names = self.names(*cats)
        if not names:
            return {} if by_ledger else ZERO
        q = select(TallyLine.ledger, func.sum(TallyLine.dr)).join(TallyVoucher).where(
            TallyVoucher.company_id == self.c.id, TallyVoucher.counted.is_(True), TallyLine.ledger.in_(names),
            TallyVoucher.date >= s.start, TallyVoucher.date <= s.end).group_by(TallyLine.ledger)
        rows = {n: Decimal(v or 0) for n, v in self.db.execute(q)}
        return rows if by_ledger else sum(rows.values(), ZERO)

    def monthly(self, cats: tuple[str, ...], start: date, end: date) -> dict[date, Decimal]:
        names = self.names(*cats)
        out: dict[date, Decimal] = defaultdict(lambda: ZERO)
        if not names:
            return out
        m = func.date_trunc("month", TallyVoucher.date)
        q = (select(m, func.sum(TallyLine.dr)).join(TallyVoucher)
             .where(TallyVoucher.company_id == self.c.id, TallyVoucher.counted.is_(True), TallyLine.ledger.in_(names),
                    TallyVoucher.date >= start, TallyVoucher.date <= end).group_by(m))
        for k, v in self.db.execute(q):
            out[k.date() if isinstance(k, datetime) else k] = Decimal(v or 0)
        return out

    def balances(self, cats: tuple[str, ...], on: date) -> dict[str, Decimal]:
        """Balance (debit +) of each ledger at the end of `on`.
        Anchored on Tally's own closing balance, so it is exact even if older years were not copied."""
        names = self.names(*cats)
        if not names:
            return {}
        after = {n: Decimal(v or 0) for n, v in self.db.execute(
            select(TallyLine.ledger, func.sum(TallyLine.dr)).join(TallyVoucher).where(
                TallyVoucher.company_id == self.c.id, TallyVoucher.counted.is_(True), TallyLine.ledger.in_(names),
                TallyVoucher.date > on, TallyVoucher.date <= self.as_of).group_by(TallyLine.ledger))}
        upto = None
        out = {}
        for n in names:
            lg = self.ledgers[n]
            if lg.tally_closing_dr is not None:
                out[n] = lg.tally_closing_dr - after.get(n, ZERO)
            else:  # file import without closing balances: opening + everything up to the date
                if upto is None:
                    upto = {k: Decimal(v or 0) for k, v in self.db.execute(
                        select(TallyLine.ledger, func.sum(TallyLine.dr)).join(TallyVoucher).where(
                            TallyVoucher.company_id == self.c.id, TallyVoucher.counted.is_(True),
                            TallyLine.ledger.in_(names), TallyVoucher.date <= on).group_by(TallyLine.ledger))}
                out[n] = lg.opening_dr + upto.get(n, ZERO)
        return out

    def balance(self, cats: tuple[str, ...], on: date) -> Decimal:
        return sum(self.balances(cats, on).values(), ZERO)

    def voucher_lines(self, s: Span, having_cats: tuple[str, ...]) -> dict[int, list[tuple[str, Decimal, date]]]:
        """All lines of vouchers in the span that touch any ledger in having_cats."""
        names = self.names(*having_cats)
        if not names:
            return {}
        ids = (select(TallyLine.voucher_id).join(TallyVoucher).where(
            TallyVoucher.company_id == self.c.id, TallyVoucher.counted.is_(True), TallyVoucher.date >= s.start,
            TallyVoucher.date <= s.end, TallyLine.ledger.in_(names)).distinct())
        out: dict[int, list] = defaultdict(list)
        for ledger, dr, d, vid in self.db.execute(self._lines().where(TallyVoucher.id.in_(ids))):
            out[vid].append((ledger, Decimal(dr), d))
        return out

    def cat(self, ledger: str) -> str:
        lg = self.ledgers.get(ledger)
        return lg.category if lg else "other"

    def stock_value(self, on: date) -> Decimal | None:
        row = self.db.scalar(select(TallyStockValue).where(TallyStockValue.company_id == self.c.id,
                                                            TallyStockValue.as_of <= on)
                             .order_by(TallyStockValue.as_of.desc()).limit(1))
        return row.value if row else None


# ---------------------------------------------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------------------------------------------
def sales(b: Books, s: Span) -> Decimal:
    return -b.flow(("sales",), s)


def expenses(b: Books, s: Span) -> Decimal:
    return b.flow(EXP, s)


def purchases(b: Books, s: Span) -> Decimal:
    return b.flow(("purchase",), s)


def other_income(b: Books, s: Span) -> Decimal:
    return -b.flow(INC, s)


def profit(b: Books, s: Span) -> tuple[Decimal, Decimal | None]:
    stock_change = None
    end_v, start_v = b.stock_value(s.end), b.stock_value(s.start - timedelta(days=1))
    if end_v is not None and start_v is not None:
        stock_change = end_v - start_v
    p = sales(b, s) + other_income(b, s) - purchases(b, s) - expenses(b, s) + (stock_change or ZERO)
    return p, stock_change


def collections(b: Books, s: Span, by_party: bool = False):
    per: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for lines in b.voucher_lines(s, ("cash", "bank")).values():
        if not any(b.cat(n) in ("cash", "bank") and dr > 0 for n, dr, _ in lines):
            continue
        for n, dr, _ in lines:
            if dr < 0 and b.cat(n) == "debtors":
                per[n] += -dr
    return dict(per) if by_party else sum(per.values(), ZERO)


def supplier_payments(b: Books, s: Span) -> Decimal:
    total = ZERO
    for lines in b.voucher_lines(s, ("cash", "bank")).values():
        if not any(b.cat(n) in ("cash", "bank") and dr < 0 for n, dr, _ in lines):
            continue
        total += sum((dr for n, dr, _ in lines if dr > 0 and b.cat(n) == "creditors"), ZERO)
    return total


def sales_by_party(b: Books, s: Span) -> dict[str, Decimal]:
    per: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for lines in b.voucher_lines(s, ("sales",)).values():
        amount = -sum((dr for n, dr, _ in lines if b.cat(n) == "sales"), ZERO)
        debtors = [(abs(dr), n) for n, dr, _ in lines if b.cat(n) == "debtors"]
        party = max(debtors)[1] if debtors else "Cash / counter sales"
        per[party] += amount
    return dict(per)


def sales_by_product(b: Books, s: Span) -> list[dict]:
    sales_ids = (select(TallyLine.voucher_id).join(TallyVoucher).where(
        TallyVoucher.company_id == b.c.id, TallyVoucher.counted.is_(True), TallyVoucher.date >= s.start,
        TallyVoucher.date <= s.end, TallyLine.ledger.in_(b.names("sales") or ["-"]), TallyLine.dr < 0).distinct())
    rows = b.db.execute(
        select(TallyStockLine.item, func.sum(TallyStockLine.amount), func.sum(TallyStockLine.qty),
               func.min(TallyStockLine.unit))
        .where(TallyStockLine.voucher_id.in_(sales_ids), TallyStockLine.inward.is_(False))
        .group_by(TallyStockLine.item).order_by(func.sum(TallyStockLine.amount).desc())).all()
    return [{"item": i, "amount": Decimal(a or 0), "qty": Decimal(q or 0), "unit": u or ""} for i, a, q, u in rows]


def receivable_ageing(b: Books, on: date) -> list[dict]:
    """Per dealer: what they owe and how late. Payments are matched to the oldest bills first."""
    bal = b.balances(("debtors",), on)
    names = [n for n, v in bal.items() if v != 0]
    if not names:
        return []
    debits: dict[str, list[tuple[date, Decimal]]] = defaultdict(list)
    q = (select(TallyLine.ledger, TallyVoucher.date, TallyLine.dr).join(TallyVoucher)
         .where(TallyVoucher.company_id == b.c.id, TallyVoucher.counted.is_(True), TallyLine.ledger.in_(names),
                TallyLine.dr > 0, TallyVoucher.date <= on).order_by(TallyVoucher.date.desc(), TallyVoucher.id.desc()))
    for n, d, dr in b.db.execute(q):
        debits[n].append((d, Decimal(dr)))
    oldest = b.db.scalar(select(func.min(TallyVoucher.date)).where(TallyVoucher.company_id == b.c.id)) or on
    out = []
    for n in names:
        owed = bal[n]
        lg = b.ledgers[n]
        days = lg.credit_days or DEFAULT_CREDIT_DAYS
        row = {"party": n, "owed": owed, "credit_days": days, "not_due": ZERO, "late_30": ZERO, "late_60": ZERO,
               "late_90": ZERO, "late_90_plus": ZERO, "oldest_late_days": 0, "advance": ZERO, "state": lg.state}
        if owed < 0:
            row["advance"] = -owed
            out.append(row)
            continue
        left = owed
        for d, amt in debits[n] + [(oldest - timedelta(days=1), left)]:  # last item = anything older than the copy
            if left <= 0:
                break
            take = min(amt, left)
            left -= take
            late = (on - d).days - days
            key = ("not_due" if late <= 0 else "late_30" if late <= 30 else "late_60" if late <= 60
                   else "late_90" if late <= 90 else "late_90_plus")
            row[key] += take
            if late > 0:
                row["oldest_late_days"] = max(row["oldest_late_days"], late)
        out.append(row)
    out.sort(key=lambda r: (-r["owed"]))
    return out


# ---------------------------------------------------------------------------------------------------------------
# Story: plain sentences about what went up and down
# ---------------------------------------------------------------------------------------------------------------
def pct(now: Decimal, before: Decimal) -> float | None:
    if before == 0:
        return None
    return float((now - before) / abs(before) * 100)


def rupees(v: Decimal) -> str:
    v = Decimal(v).quantize(Decimal("1"))
    neg = v < 0
    v = abs(v)
    if v >= 10_000_000:
        s = f"₹{v / 10_000_000:.2f} crore"
    elif v >= 100_000:
        s = f"₹{v / 100_000:.2f} lakh"
    else:
        s = "₹" + _indian(int(v))
    return ("minus " if neg else "") + s


def _indian(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def story(b: Books, p: Period, fig: dict, ageing: list[dict]) -> list[dict]:
    items: list[dict] = []
    s_now, s_cmp, s_ly = fig["sales"]["value"], fig["sales"]["compare"], fig["sales"]["last_year"]
    ch = pct(s_now, s_cmp)
    ch_ly = pct(s_now, s_ly)
    if s_now:
        bits = []
        if ch is not None:
            bits.append(f"{'up' if ch >= 0 else 'down'} {abs(ch):.0f}% compared with {p.cmp_label}")
        if ch_ly is not None and p.key != "year":
            bits.append(f"{'up' if ch_ly >= 0 else 'down'} {abs(ch_ly):.0f}% on the same time last year")
        tone = "up" if (ch or 0) >= 0 else "down"
        items.append({"tone": tone, "kind": "sales",
                      "text": f"Sales were {rupees(s_now)}" + (" — " + ", and ".join(bits) if bits else "") + "."})
    coll = fig["collections"]["value"]
    if s_now and coll:
        ratio = float(coll / s_now * 100) if s_now else 0
        tone = "good" if ratio >= 90 else "warn" if ratio < 70 else "neutral"
        items.append({"tone": tone, "kind": "collections",
                      "text": f"Dealers paid {rupees(coll)}. For every ₹100 of sales, ₹{ratio:.0f} came in"
                              + (" — collections are falling behind sales." if ratio < 70 else ".")})
    # dealers who moved most (skipped in the first week of a month: too few days to judge)
    short = (p.cur.end - p.cur.start).days < 7
    now_p, cmp_p = ({}, {}) if short else (sales_by_party(b, p.cur), sales_by_party(b, p.cmp))
    moves = []
    for party in set(now_p) | set(cmp_p):
        a, c = now_p.get(party, ZERO), cmp_p.get(party, ZERO)
        if max(a, c) >= Decimal(50000):
            moves.append((a - c, party, a, c))
    if moves:
        up = max(moves)
        down = min(moves)
        if up[0] > 0:
            items.append({"tone": "up", "kind": "sales",
                          "text": f"{up[1]} bought the most extra: {rupees(up[2])} against {rupees(up[3])}."})
        if down[0] < 0:
            items.append({"tone": "down", "kind": "sales",
                          "text": f"{down[1]} bought less: {rupees(down[2])} against {rupees(down[3])}. Worth a call."})
    # expense spikes against the 3 periods before
    now_e = b.flow(EXP, p.cur, by_ledger=True)
    span_days = (p.cur.end - p.cur.start).days + 1
    prev = [Span(add_months(p.cur.start, -k), add_months(p.cur.start, -k) + timedelta(days=span_days - 1)) for k in (1, 2, 3)] \
        if p.key != "year" else []
    if prev and not short:
        hist = [b.flow(EXP, sp, by_ledger=True) for sp in prev]
        spikes = []
        for led, v in now_e.items():
            avg = sum((h.get(led, ZERO) for h in hist), ZERO) / 3
            if v >= Decimal(10000) and avg > 0 and v > avg * Decimal("1.5"):
                spikes.append((v / avg, led, v, avg))
        if spikes:
            r, led, v, avg = max(spikes)
            items.append({"tone": "warn", "kind": "expenses",
                          "text": f"{led} was {rupees(v)} — about {r:.1f} times the usual {rupees(avg)}."})
    # late money
    very_late = [a for a in ageing if a["late_90_plus"] > 0]
    if very_late:
        total = sum((a["late_90_plus"] for a in very_late), ZERO)
        worst = max(very_late, key=lambda a: a["late_90_plus"])
        items.append({"tone": "warn", "kind": "receivables",
                      "text": f"{rupees(total)} is more than 3 months late, from {len(very_late)} dealer"
                              f"{'s' if len(very_late) > 1 else ''}. Biggest: {worst['party']} ({rupees(worst['late_90_plus'])})."})
    # cash position against the last 12 month-ends
    cash_now = fig["cash"]["value"]
    hist = fig["cash"]["spark"][:-1]
    if len(hist) >= 6:
        if cash_now <= min(hist):
            items.append({"tone": "warn", "kind": "cash", "text": f"Cash and bank ({rupees(cash_now)}) is the lowest in a year."})
        elif cash_now >= max(hist):
            items.append({"tone": "good", "kind": "cash", "text": f"Cash and bank ({rupees(cash_now)}) is the highest in a year."})
    # first-time dealers this year
    year_span = Span(fy_start(p.cur.end), p.cur.end)
    before = set(sales_by_party(b, Span(date(2000, 1, 1), year_span.start - timedelta(days=1))))
    new = [n for n, v in sales_by_party(b, year_span).items() if n not in before and v > 0 and n != "Cash / counter sales"]
    has_history = b.db.scalar(select(func.count(TallyVoucher.id)).where(
        TallyVoucher.company_id == b.c.id, TallyVoucher.date < year_span.start)) or 0
    if new and has_history:
        items.append({"tone": "good", "kind": "sales",
                      "text": f"New dealer{'s' if len(new) > 1 else ''} this year: {', '.join(sorted(new)[:3])}"
                              + (f" and {len(new) - 3} more" if len(new) > 3 else "") + "."})
    order = {"warn": 0, "down": 1, "up": 2, "good": 3, "neutral": 4}
    head = items[:1]
    rest = sorted(items[1:], key=lambda i: order.get(i["tone"], 9))
    return (head + rest)[:6]


# ---------------------------------------------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------------------------------------------
def current_company(db: Session) -> TallyCompany:
    c = db.scalar(select(TallyCompany).where(TallyCompany.last_data_at.isnot(None))
                  .order_by(TallyCompany.last_data_at.desc()).limit(1))
    if not c:
        raise DomainError("No data from Tally yet. Ask the administrator to set up the Tally connector.", 409)
    return c


def freshness(c: TallyCompany) -> dict:
    now = datetime.now(timezone.utc)
    seen = c.last_seen_at or c.last_data_at
    mins = int((now - seen).total_seconds() // 60) if seen else None
    local = datetime.now(IST)
    office_hours = local.weekday() < 6 and 9 <= local.hour < 19
    stale = mins is None or (mins > 60 if office_hours else mins > 60 * 18)
    return {"last_seen_at": seen, "minutes_ago": mins, "stale": stale, "error": c.last_error,
            "company": c.name, "as_of": c.closing_as_of}


def _months_back(end: date, n: int) -> list[date]:
    first = month_start(end)
    return [add_months(first, -k) for k in range(n - 1, -1, -1)]


def overview(db: Session, period_key: str = "month", today: date | None = None) -> dict:
    c = current_company(db)
    b = Books(db, c)
    today = min(today or today_ist(), b.as_of) if b.as_of else (today or today_ist())
    p = make_period(period_key, today)

    # Trend lines use whole months only: a half-finished month would look like a sudden drop.
    spark_end = p.cur.end if p.cur.end == month_end(p.cur.end) else month_start(p.cur.end) - timedelta(days=1)
    months = _months_back(spark_end, 12)
    m_from = months[0]
    m_sales = b.monthly(("sales",), m_from, spark_end)
    m_exp = b.monthly(EXP, m_from, spark_end)
    m_pur = b.monthly(("purchase",), m_from, spark_end)
    m_inc = b.monthly(INC, m_from, spark_end)
    m_coll = [collections(b, Span(m, month_end(m))) for m in months]
    # balances: month-ends, with today as the last point
    bal_points = [month_end(m) for m in _months_back(p.cur.end, 12)][:-1] + [p.cur.end]
    m_cash = [b.balance(("cash", "bank"), d) for d in bal_points]
    m_recv = [b.balance(("debtors",), d) for d in bal_points]

    def tile(value, compare, last_year, spark, good_when_up=True, extra=None):
        return {"value": value, "compare": compare, "last_year": last_year, "change_pct": pct(value, compare),
                "good_when_up": good_when_up, "spark": spark, **(extra or {})}

    s_cur, s_cmp, s_ly = sales(b, p.cur), sales(b, p.cmp), sales(b, p.ly)
    pr_cur, stock_chg = profit(b, p.cur)
    cash_now = b.balance(("cash", "bank"), p.cur.end)
    cash_before = b.balance(("cash", "bank"), p.cur.start - timedelta(days=1))
    recv_now = b.balance(("debtors",), p.cur.end)
    recv_before = b.balance(("debtors",), p.cur.start - timedelta(days=1))
    ageing = receivable_ageing(b, p.cur.end)
    late = sum((a["owed"] - a["not_due"] - a["advance"] for a in ageing if a["owed"] > 0), ZERO)
    payables = -b.balance(("creditors",), p.cur.end)

    fig = {
        "sales": tile(s_cur, s_cmp, s_ly, [-m_sales.get(m, ZERO) for m in months]),
        "collections": tile(collections(b, p.cur), collections(b, p.cmp), collections(b, p.ly), m_coll),
        "expenses": tile(expenses(b, p.cur), expenses(b, p.cmp), expenses(b, p.ly),
                         [m_exp.get(m, ZERO) for m in months], good_when_up=False,
                         extra={"purchases": purchases(b, p.cur)}),
        "profit": tile(pr_cur, profit(b, p.cmp)[0], profit(b, p.ly)[0],
                       [-m_sales.get(m, ZERO) - m_inc.get(m, ZERO) - m_exp.get(m, ZERO) - m_pur.get(m, ZERO) for m in months],
                       extra={"stock_included": stock_chg is not None}),
        "cash": tile(cash_now, cash_before, None, m_cash, extra={"payables": payables, "since": "start of the period"}),
        "receivables": tile(recv_now, recv_before, None, m_recv, good_when_up=False,
                            extra={"late": late, "since": "start of the period"}),
    }

    # sales by month: this financial year against last
    fy = fy_start(p.cur.end)
    this_fy = b.monthly(("sales",), fy, p.cur.end)
    last_fy = b.monthly(("sales",), add_months(fy, -12), fy - timedelta(days=1))
    chart = []
    for k in range(12):
        m = add_months(fy, k)
        lm = add_months(m, -12)
        chart.append({"month": f"{m:%b}", "this_year": (-this_fy.get(m, ZERO)) if m <= p.cur.end else None,
                      "last_year": (-last_fy[lm]) if lm in last_fy else None})

    by_party = sales_by_party(b, p.cur)
    by_party_cmp = sales_by_party(b, p.cmp)
    top_dealers = sorted(by_party.items(), key=lambda x: -x[1])[:6]
    exp_ledgers = sorted(b.flow(EXP, p.cur, by_ledger=True).items(), key=lambda x: -x[1])
    exp_cmp = b.flow(EXP, p.cmp, by_ledger=True)
    products = sales_by_product(b, p.cur)[:6]

    return {
        "period": {"key": p.key, "title": p.title, "days": (p.cur.end - p.cur.start).days + 1, "from": p.cur.start, "to": p.cur.end, "label": p.cur.label(),
                   "compare_label": p.cmp_label, "last_year_label": p.ly.label()},
        "freshness": freshness(c),
        "story": story(b, p, fig, ageing),
        "tiles": fig,
        "sales_chart": {"this_year_label": f"{fy.year}–{str(fy.year + 1)[2:]}",
                        "last_year_label": f"{fy.year - 1}–{str(fy.year)[2:]}", "months": chart},
        "owe_us": [{"party": a["party"], "owed": a["owed"], "late": a["owed"] - a["not_due"],
                    "oldest_late_days": a["oldest_late_days"]} for a in ageing if a["owed"] > 0][:6],
        "top_dealers": [{"party": n, "amount": v, "change_pct": pct(v, by_party_cmp.get(n, ZERO))} for n, v in top_dealers],
        "spending": [{"name": n, "amount": v, "change_pct": pct(v, exp_cmp.get(n, ZERO))} for n, v in exp_ledgers[:7]],
        "spending_other": sum((v for _, v in exp_ledgers[7:]), ZERO),
        "products": [{"item": x["item"], "amount": x["amount"], "qty": x["qty"], "unit": x["unit"]} for x in products],
        "month_labels": [f"{m:%b}" for m in months],
    }


def detail(db: Session, kind: str, period_key: str = "month", today: date | None = None) -> dict:
    c = current_company(db)
    b = Books(db, c)
    today = min(today or today_ist(), b.as_of)
    p = make_period(period_key, today)

    if kind == "sales":
        now, before = sales_by_party(b, p.cur), sales_by_party(b, p.cmp)
        total = sum(now.values(), ZERO)
        rows = [{"label": n, "value": v, "share": float(v / total * 100) if total else 0,
                 "change_pct": pct(v, before.get(n, ZERO))} for n, v in sorted(now.items(), key=lambda x: -x[1])]
        gone = [{"label": n, "value": ZERO, "share": 0, "change_pct": -100.0, "note": f"bought {rupees(v)} in {p.cmp_label}"}
                for n, v in before.items() if n not in now and v > 0]
        return {"title": "Sales", "explain": "Sales before GST, after goods returned. Taken from the Sales Accounts in Tally.",
                "sections": [{"title": "By dealer", "kind": "bars", "rows": rows + gone},
                             {"title": "By product", "kind": "bars", "rows": [
                                 {"label": x["item"], "value": x["amount"], "sub": f"{x['qty'].normalize():f} {x['unit']}"}
                                 for x in sales_by_product(b, p.cur)]}]}
    if kind == "collections":
        now = collections(b, p.cur, by_party=True)
        return {"title": "Money collected", "explain": "Money received from dealers into cash or bank.",
                "sections": [{"title": "By dealer", "kind": "bars",
                              "rows": [{"label": n, "value": v} for n, v in sorted(now.items(), key=lambda x: -x[1])]}]}
    if kind == "expenses":
        now, before = b.flow(EXP, p.cur, by_ledger=True), b.flow(EXP, p.cmp, by_ledger=True)
        return {"title": "Expenses", "explain": "Direct and indirect expenses in Tally (salaries, rent, fuel and so on). "
                                                f"Purchases of materials ({rupees(purchases(b, p.cur))}) are not included here.",
                "sections": [{"title": "Where the money went", "kind": "bars", "rows": [
                    {"label": n, "value": v, "change_pct": pct(v, before.get(n, ZERO))}
                    for n, v in sorted(now.items(), key=lambda x: -x[1]) if v]}]}
    if kind == "profit":
        pr, stock_chg = profit(b, p.cur)
        rows = [("Sales", sales(b, p.cur)), ("Other income", other_income(b, p.cur)),
                ("Purchases of materials", -purchases(b, p.cur)), ("Expenses", -expenses(b, p.cur))]
        if stock_chg is not None:
            rows.append(("Change in stock value", stock_chg))
        rows.append(("Profit (estimate)", pr))
        return {"title": "Profit (estimate)",
                "explain": "A quick estimate from Tally figures. It does not include depreciation, tax or year-end "
                           "adjustments made by the auditor." + ("" if stock_chg is not None else
                                                                 " Stock value is not kept in Tally, so stock changes are not included."),
                "sections": [{"title": "How it adds up", "kind": "sum", "rows": [{"label": k, "value": v} for k, v in rows]}]}
    if kind == "cash":
        bal = b.balances(("cash", "bank"), p.cur.end)
        cred = b.balances(("creditors",), p.cur.end)
        owe = sorted(((n, -v) for n, v in cred.items() if v < 0), key=lambda x: -x[1])
        return {"title": "Cash and bank",
                "explain": f"Balances on {p.cur.end:%d %b %Y}, from the Cash-in-Hand and Bank Accounts in Tally.",
                "sections": [{"title": "Accounts", "kind": "bars",
                              "rows": [{"label": n, "value": v} for n, v in sorted(bal.items(), key=lambda x: -x[1])]},
                             {"title": f"We owe suppliers {rupees(sum((v for _, v in owe), ZERO))}", "kind": "bars",
                              "rows": [{"label": n, "value": v} for n, v in owe]}]}
    if kind == "receivables":
        rows = receivable_ageing(b, p.cur.end)
        return {"title": "Dealers owe us",
                "explain": "Money dealers still have to pay. Payments are matched to their oldest bills first. "
                           "A bill becomes late after the dealer's credit days.",
                "sections": [{"title": "By dealer", "kind": "ageing", "rows": [
                    {"label": r["party"], "value": r["owed"], "not_due": r["not_due"], "late_30": r["late_30"],
                     "late_60": r["late_60"], "late_90": r["late_90"], "late_90_plus": r["late_90_plus"],
                     "oldest_late_days": r["oldest_late_days"], "credit_days": r["credit_days"], "advance": r["advance"]}
                    for r in rows]}]}
    raise DomainError("Unknown detail.", 404)


# ---------------------------------------------------------------------------------------------------------------
# For the administrator: is the copy healthy and does it match Tally?
# ---------------------------------------------------------------------------------------------------------------
def status(db: Session) -> dict:
    c = db.scalar(select(TallyCompany).order_by(TallyCompany.last_seen_at.desc().nullslast()).limit(1))
    runs = db.scalars(select(TallySyncRun).order_by(TallySyncRun.id.desc()).limit(15)).all()
    out = {"connected": c is not None, "runs": [{"at": r.at, "mode": r.mode, "ok": r.ok, "vouchers": r.vouchers,
                                                 "skipped": r.skipped, "message": r.message} for r in runs]}
    if not c:
        return out
    b = Books(db, c)
    counts = db.execute(select(func.count(TallyVoucher.id), func.min(TallyVoucher.date), func.max(TallyVoucher.date))
                        .where(TallyVoucher.company_id == c.id)).one()
    not_counted = db.scalar(select(func.count(TallyVoucher.id)).where(TallyVoucher.company_id == c.id,
                                                                       TallyVoucher.counted.is_(False))) or 0
    # Check: opening balance + every entry we hold should equal Tally's own closing balance (only possible
    # when we hold every entry since the books began).
    check = []
    holds_all = c.books_from and counts[1] and counts[1] <= c.books_from + timedelta(days=31)
    if holds_all:
        sums = {n: Decimal(v or 0) for n, v in db.execute(
            select(TallyLine.ledger, func.sum(TallyLine.dr)).join(TallyVoucher).where(
                TallyVoucher.company_id == c.id, TallyVoucher.counted.is_(True), TallyVoucher.date <= b.as_of)
            .group_by(TallyLine.ledger))}
        for cat in ("bank", "cash", "debtors", "creditors", "tax"):
            ours = sum((b.ledgers[n].opening_dr + sums.get(n, ZERO) for n in b.names(cat)), ZERO)
            theirs = sum((b.ledgers[n].tally_closing_dr or ZERO for n in b.names(cat)), ZERO)
            check.append({"what": cat, "ours": ours, "tally": theirs, "match": abs(ours - theirs) < Decimal("1")})
    unmapped = sorted({lg.parent for lg in b.ledgers.values() if lg.category == "other" and lg.parent})
    out.update({
        "company": c.name, "books_from": c.books_from, "agent_version": c.agent_version,
        "last_seen_at": c.last_seen_at, "last_data_at": c.last_data_at, "last_full_at": c.last_full_at,
        "last_error": c.last_error, "last_error_at": c.last_error_at, "freshness": freshness(c),
        "vouchers": counts[0], "from": counts[1], "to": counts[2], "not_counted": not_counted,
        "ledgers": len(b.ledgers), "check": check, "check_possible": bool(holds_all),
        "categories": {cat: len(b.names(cat)) for cat in ("sales", "purchase", "direct_exp", "indirect_exp", "debtors",
                                                          "creditors", "bank", "cash")},
        "groups_not_used": unmapped,
    })
    return out

