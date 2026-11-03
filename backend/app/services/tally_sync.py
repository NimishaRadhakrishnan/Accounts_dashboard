"""Receives data from the Tally connector and keeps an exact read-only copy.

Rules
* Masters (groups, ledgers, voucher types) are replaced in full on every data sync.
* mode=full     -> every voucher dated inside the window is replaced (this is how deletions in Tally disappear here).
* mode=changes  -> vouchers are added or replaced by their Tally GUID.
* Cancelled, optional/post-dated and unbalanced vouchers are kept but marked counted=False, so they never affect figures.
"""
import hashlib
import json
import secrets
import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models import (AppSetting, ConnectorKey, TallyCompany, TallyGroup, TallyLedger, TallyLine, TallyStockLine,
                        TallyStockValue, TallySyncRun, TallyVoucher, TallyVoucherType)

# Tally's reserved groups (TallyPrime and Tally.ERP 9 names) -> what they mean for the dashboard.
RESERVED = {
    "sales accounts": "sales", "purchase accounts": "purchase",
    "direct expenses": "direct_exp", "expenses (direct)": "direct_exp",
    "indirect expenses": "indirect_exp", "expenses (indirect)": "indirect_exp",
    "direct incomes": "direct_inc", "income (direct)": "direct_inc",
    "indirect incomes": "indirect_inc", "income (indirect)": "indirect_inc",
    "sundry debtors": "debtors", "sundry creditors": "creditors",
    "bank accounts": "bank", "bank od a/c": "bank", "bank occ a/c": "bank",
    "cash-in-hand": "cash", "duties & taxes": "tax", "stock-in-hand": "stock",
    "fixed assets": "fixed", "capital account": "capital",
    "loans (liability)": "loans", "secured loans": "loans", "unsecured loans": "loans",
}
CATEGORY_LABELS = {
    "sales": "Sales", "purchase": "Purchases", "direct_exp": "Direct expenses", "indirect_exp": "Indirect expenses",
    "direct_inc": "Other income", "indirect_inc": "Other income", "debtors": "Dealers (Sundry Debtors)",
    "creditors": "Suppliers (Sundry Creditors)", "bank": "Bank", "cash": "Cash", "tax": "GST & taxes",
    "stock": "Stock", "fixed": "Fixed assets", "capital": "Capital", "loans": "Loans", "other": "Other",
}
MAX_BODY = 200 * 1024 * 1024  # decompressed


# ---------------------------------------------------------------------------------------------------------------
# Connector keys
# ---------------------------------------------------------------------------------------------------------------
def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create_key(db: Session, label: str, user_id: int | None) -> str:
    key = "vbt_" + secrets.token_urlsafe(32)
    db.add(ConnectorKey(label=label[:100], key_hash=_hash(key), hint=key[-6:], created_by_id=user_id))
    db.flush()
    return key


def check_key(db: Session, authorization: str | None) -> ConnectorKey:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise DomainError("Connector key missing.", 401)
    row = db.scalar(select(ConnectorKey).where(ConnectorKey.key_hash == _hash(authorization[7:].strip()),
                                               ConnectorKey.revoked.is_(False)))
    if not row:
        raise DomainError("Connector key not recognised.", 401)
    row.last_used_at = datetime.now(timezone.utc)
    return row


# ---------------------------------------------------------------------------------------------------------------
# Group classification
# ---------------------------------------------------------------------------------------------------------------
def group_overrides(db: Session) -> dict[str, str]:
    row = db.get(AppSetting, "tally_group_map")
    if not row:
        return {}
    try:
        return {k.lower(): v for k, v in json.loads(row.value).items()}
    except ValueError:
        return {}


def classify(groups: dict[str, str | None], overrides: dict[str, str]) -> dict[str, str]:
    """For every group, walk up its parents until a known group is found."""
    out = {}
    for g in groups:
        seen, cur, cat = set(), g, "other"
        while cur and cur.lower() not in seen:
            low = cur.lower()
            seen.add(low)
            if low in overrides:
                cat = overrides[low]
                break
            if low in RESERVED:
                cat = RESERVED[low]
                break
            cur = groups.get(cur) or ""
        out[g] = cat
    return out


def reclassify(db: Session, company_id: int) -> None:
    groups = {g.name: g.parent for g in db.scalars(select(TallyGroup).where(TallyGroup.company_id == company_id))}
    cats = classify(groups, group_overrides(db))
    for g in db.scalars(select(TallyGroup).where(TallyGroup.company_id == company_id)):
        g.category = cats.get(g.name, "other")
    for lg in db.scalars(select(TallyLedger).where(TallyLedger.company_id == company_id)):
        lg.category = cats.get(lg.parent or "", RESERVED.get((lg.parent or "").lower(), "other"))


# ---------------------------------------------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------------------------------------------
def _dec(v, default="0") -> Decimal:
    try:
        return Decimal(str(v if v not in (None, "") else default))
    except InvalidOperation:
        return Decimal(default)


def _date(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _company(db: Session, c: dict) -> TallyCompany:
    guid = (c.get("guid") or c.get("name") or "unknown")[:64]
    comp = db.scalar(select(TallyCompany).where(TallyCompany.guid == guid))
    if not comp:
        comp = TallyCompany(guid=guid, name=(c.get("name") or "Company")[:200])
        db.add(comp)
        db.flush()
    comp.name = (c.get("name") or comp.name)[:200]
    comp.books_from = _date(c.get("books_from")) or comp.books_from
    return comp


def _voucher(company_id: int, v: dict) -> TallyVoucher | None:
    d = _date(v.get("date"))
    guid = (v.get("guid") or "").strip()
    if not d or not guid:
        return None
    lines = [(str(x.get("ledger", ""))[:200], _dec(x.get("dr")), x.get("bills") or None) for x in v.get("lines") or []]
    lines = [x for x in lines if x[0] and x[1] != 0]
    balanced = abs(sum((x[1] for x in lines), Decimal(0))) < Decimal("0.05")
    tv = TallyVoucher(company_id=company_id, guid=guid[:80], alter_id=int(v.get("alter_id") or 0), date=d,
                      vtype=str(v.get("type") or "")[:100], number=str(v.get("number") or "")[:60] or None,
                      party=str(v.get("party") or "")[:200] or None, narration=str(v.get("narration") or "")[:300] or None,
                      counted=bool(lines) and balanced and not v.get("cancelled") and not v.get("optional"))
    tv.lines = [TallyLine(ledger=n, dr=a, bills=b) for n, a, b in lines]
    tv.stock = [TallyStockLine(item=str(s.get("item"))[:200], qty=_dec(s.get("qty")), unit=str(s.get("unit") or "")[:20],
                               amount=_dec(s.get("amount")), inward=bool(s.get("inward")))
                for s in v.get("stock") or [] if s.get("item")]
    return tv


def ingest(db: Session, payload: dict) -> dict:
    t0 = time.time()
    mode = payload.get("mode") or "changes"
    if mode not in ("full", "changes", "heartbeat", "masters"):
        raise DomainError("Unknown sync mode.")
    comp = _company(db, payload.get("company") or {})
    now = datetime.now(timezone.utc)
    comp.last_seen_at = now
    comp.agent_version = str(payload.get("agent_version") or "")[:20] or None
    if mode == "heartbeat":
        comp.last_error = None
        db.add(TallySyncRun(company_id=comp.id, mode=mode, ok=True, seconds=round(time.time() - t0, 2),
                            message="No changes in Tally"))
        return {"message": "No changes", "vouchers": 0}

    # ---- masters
    if payload.get("groups") is not None:
        db.execute(delete(TallyGroup).where(TallyGroup.company_id == comp.id))
        seen = set()
        for g in payload["groups"]:
            name = str(g.get("name") or "").strip()[:200]
            if name and name not in seen:
                seen.add(name)
                db.add(TallyGroup(company_id=comp.id, name=name, parent=(g.get("parent") or None), category="other"))
    if payload.get("ledgers") is not None:
        existing = {lg.name: lg for lg in db.scalars(select(TallyLedger).where(TallyLedger.company_id == comp.id))}
        incoming = set()
        for raw in payload["ledgers"]:
            name = str(raw.get("name") or "").strip()[:200]
            if not name or name in incoming:
                continue
            incoming.add(name)
            lg = existing.get(name) or TallyLedger(company_id=comp.id, name=name, category="other")
            lg.parent = raw.get("parent") or None
            lg.opening_dr = _dec(raw.get("opening_dr"))
            lg.tally_closing_dr = _dec(raw.get("closing_dr")) if raw.get("closing_dr") not in (None, "") else None
            lg.credit_days = int(raw.get("credit_days") or 0)
            lg.gstin = (raw.get("gstin") or None) and str(raw["gstin"])[:20]
            lg.state = (raw.get("state") or None) and str(raw["state"])[:60]
            db.add(lg)
        if mode != "masters" or payload.get("ledgers"):
            for name, lg in existing.items():
                if name not in incoming:
                    db.delete(lg)
        comp.closing_as_of = _date(payload.get("tally_today")) or date.today()
    if payload.get("voucher_types") is not None:
        db.execute(delete(TallyVoucherType).where(TallyVoucherType.company_id == comp.id))
        seen = set()
        for vt in payload["voucher_types"]:
            name = str(vt.get("name") or "").strip()[:100]
            if name and name not in seen:
                seen.add(name)
                db.add(TallyVoucherType(company_id=comp.id, name=name, parent=vt.get("parent") or None))
    db.flush()
    reclassify(db, comp.id)

    # ---- vouchers
    vouchers = payload.get("vouchers") or []
    added = skipped = 0
    if mode == "full" and payload.get("window"):
        w_from, w_to = _date(payload["window"].get("from")), _date(payload["window"].get("to"))
        if not w_from or not w_to or w_to < w_from:
            raise DomainError("Sync window is not valid.")
        db.execute(delete(TallyVoucher).where(TallyVoucher.company_id == comp.id, TallyVoucher.date >= w_from,
                                              TallyVoucher.date <= w_to))
    else:
        guids = [str(v.get("guid"))[:80] for v in vouchers if v.get("guid")]
        for i in range(0, len(guids), 1000):
            db.execute(delete(TallyVoucher).where(TallyVoucher.company_id == comp.id,
                                                  TallyVoucher.guid.in_(guids[i:i + 1000])))
    db.flush()
    seen_guid = set()
    for v in vouchers:
        tv = _voucher(comp.id, v)
        if not tv or tv.guid in seen_guid:
            skipped += 1
            continue
        seen_guid.add(tv.guid)
        if not tv.counted:
            skipped += 1
        db.add(tv)
        added += 1
        if added % 2000 == 0:
            db.flush()

    for sv in payload.get("stock_values") or []:
        d = _date(sv.get("date"))
        if not d:
            continue
        row = db.scalar(select(TallyStockValue).where(TallyStockValue.company_id == comp.id, TallyStockValue.as_of == d))
        if not row:
            row = TallyStockValue(company_id=comp.id, as_of=d, value=0)
            db.add(row)
        row.value = _dec(sv.get("value"))

    c = payload.get("company") or {}
    comp.alt_vch_id = int(c.get("alt_vch_id") or comp.alt_vch_id or 0)
    comp.alt_mst_id = int(c.get("alt_mst_id") or comp.alt_mst_id or 0)
    comp.last_data_at = now
    if mode == "full":
        comp.last_full_at = now
    comp.last_error = None
    msg = f"{added} entries received" + (f" ({skipped} not counted: cancelled, optional or unbalanced)" if skipped else "")
    db.add(TallySyncRun(company_id=comp.id, mode=mode, ok=True, vouchers=added, skipped=skipped,
                        seconds=round(time.time() - t0, 2), message=msg))
    db.flush()
    return {"message": msg, "vouchers": added, "skipped": skipped}


def record_error(db: Session, payload: dict) -> None:
    comp = db.scalar(select(TallyCompany).order_by(TallyCompany.last_seen_at.desc().nullslast()).limit(1))
    msg = str(payload.get("message") or "Unknown problem")[:500]
    now = datetime.now(timezone.utc)
    if comp:
        comp.last_error, comp.last_error_at, comp.last_seen_at = msg, now, now
    db.add(TallySyncRun(company_id=comp.id if comp else None, mode="error", ok=False, message=msg))
