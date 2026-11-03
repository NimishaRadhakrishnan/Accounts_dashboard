"""
Vishakan Bio Tech — Tally Connector
===================================

Runs on the office computer where Tally is open. Every few minutes it asks Tally for
new or changed entries and sends them to the manager dashboard over HTTPS.

* READ-ONLY: it only sends "Export" requests to Tally. It never creates, changes or deletes anything in Tally.
* Only needs Python 3.9+ (no extra packages).
* Settings are in connector.ini next to this file.

Usage
    python vbt_tally_connector.py --test      check Tally and the dashboard can both be reached
    python vbt_tally_connector.py             one sync (Windows Task Scheduler runs this every 10 minutes)
    python vbt_tally_connector.py --full      force a full re-read of this year and last year
    python vbt_tally_connector.py --loop      keep running, syncing every N minutes (alternative to Task Scheduler)
    python vbt_tally_connector.py --file daybook.xml masters.xml   send exported Tally XML files instead of live Tally
"""
from __future__ import annotations

import argparse
import configparser
import datetime as dt
import gzip
import json
import logging
import logging.handlers
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

VERSION = "1.0.0"
HERE = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
log = logging.getLogger("vbt-tally")


# ---------------------------------------------------------------------------------------------------------------
# Settings and saved state
# ---------------------------------------------------------------------------------------------------------------
DEFAULT_INI = """[tally]
; Tally must have: F1 Help > Settings > Connectivity > "TallyPrime acts as" = Both (or Server), Port = 9000
url = http://localhost:9000
; Leave empty to use the only company that is open in Tally
company =
; Seconds to wait for Tally to answer (big months can take a while)
timeout = 180

[dashboard]
url = https://accounts.example.com
; Paste the connector key shown in the dashboard: Settings > Tally link > Create connector key
token =

[sync]
minutes = 10
; Read all entries again once a day (catches deleted entries). Hour of day, 24h clock.
full_refresh_hour = 9
; How many past financial years to keep (1 = this year and last year)
past_years = 1
"""


def load_config(path: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_INI)
        log.info("Created %s — please fill in the dashboard url and token.", path)
    cfg.read(path, encoding="utf-8")
    return cfg


class State:
    """Remembers what was already sent, so only changes are sent next time."""

    def __init__(self, path: str):
        self.path = path
        self.data: dict = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.data = json.load(f)
            except (OSError, ValueError):
                self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, **kw):
        self.data.update(kw)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)


# ---------------------------------------------------------------------------------------------------------------
# Talking to Tally
# ---------------------------------------------------------------------------------------------------------------
class TallyError(Exception):
    pass


_BAD_XML_CHARS = re.compile(r"&#(?:x0*[0-8bcef]|x0*1[0-9a-f]|0*[0-8]|0*1[1-9]|0*2[0-9]|0*3[01]);", re.I)
_RAW_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_xml(raw: bytes) -> str:
    """Tally sometimes sends UTF-16 and control characters that are not valid XML."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-16") if raw[:1] == b"<" and raw[1:2] == b"\x00" else raw.decode("latin-1")
    text = text.lstrip("﻿")
    text = _BAD_XML_CHARS.sub("", text)
    return _RAW_CTRL.sub("", text)


def xesc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def tdate(d: dt.date) -> str:
    """Date for Tally formulas, e.g. 1-Apr-2026."""
    return f"{d.day}-{d:%b}-{d.year}"


class Tally:
    def __init__(self, url: str, company: str = "", timeout: int = 180):
        self.url = url.rstrip("/")
        self.company = company
        self.timeout = timeout

    def _post(self, xml: str) -> ET.Element:
        req = urllib.request.Request(self.url, data=xml.encode("utf-8"), method="POST",
                                     headers={"Content-Type": "text/xml; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
        except urllib.error.URLError as e:
            raise TallyError(f"Cannot reach Tally at {self.url}. Is Tally open, with a company loaded, "
                             f"and is the connection port turned on? ({e.reason})") from None
        except TimeoutError:
            raise TallyError("Tally took too long to answer. Try again when Tally is not busy.") from None
        text = clean_xml(raw)
        try:
            root = ET.fromstring(text)
        except ET.ParseError as e:
            raise TallyError(f"Tally sent an answer that could not be read ({e}).") from None
        err = root.find(".//LINEERROR")
        if err is not None and (err.text or "").strip():
            raise TallyError(f"Tally said: {err.text.strip()}")
        return root

    def collection(self, cid: str, body: str, static: dict | None = None, formulas: dict | None = None) -> ET.Element:
        sv = {"SVEXPORTFORMAT": "$$SysName:XML"}
        if self.company:
            sv["SVCURRENTCOMPANY"] = self.company
        sv.update(static or {})
        svx = "".join(f"<{k}>{xesc(v) if k != 'SVEXPORTFORMAT' else v}</{k}>" for k, v in sv.items())
        fx = "".join(f'<SYSTEM TYPE="Formulae" NAME="{n}">{xesc(f)}</SYSTEM>' for n, f in (formulas or {}).items())
        xml = (f"<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE>"
               f"<ID>{cid}</ID></HEADER><BODY><DESC><STATICVARIABLES>{svx}</STATICVARIABLES><TDL><TDLMESSAGE>"
               f'<COLLECTION NAME="{cid}" ISMODIFY="No">{body}</COLLECTION>{fx}'
               f"</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>")
        return self._post(xml)

    # --- what we ask for -----------------------------------------------------------------------------------
    def companies(self) -> list[dict]:
        root = self.collection("VBTCompanies", "<TYPE>Company</TYPE>" + _methods(
            "Name", "GUID", "StartingFrom", "BooksFrom", "AltVchID", "AltMstID", "StateName"))
        out = []
        for c in root.iter("COMPANY"):
            out.append({"name": _name(c), "guid": _t(c, "GUID"), "starting_from": _date(_t(c, "STARTINGFROM")),
                        "books_from": _date(_t(c, "BOOKSFROM")), "alt_vch_id": _int(_t(c, "ALTVCHID")),
                        "alt_mst_id": _int(_t(c, "ALTMSTID")), "state": _t(c, "STATENAME")})
        return out

    def groups(self) -> list[dict]:
        root = self.collection("VBTGroups", "<TYPE>Group</TYPE>" + _methods("Name", "Parent", "GUID"))
        return [{"name": _name(g), "parent": _t(g, "PARENT")} for g in root.iter("GROUP")]

    def ledgers(self, as_of: dt.date) -> list[dict]:
        root = self.collection(
            "VBTLedgers", "<TYPE>Ledger</TYPE>" + _methods(
                "Name", "Parent", "GUID", "AlterID", "OpeningBalance", "ClosingBalance", "BillCreditPeriod",
                "PartyGSTIN", "LedStateName", "StateName", "IsBillWiseOn", "Email", "LedgerPhone", "LedgerMobile"),
            static={"SVTODATE": f"{as_of:%Y%m%d}"})
        return [parse_ledger(lg) for lg in root.iter("LEDGER")]

    def voucher_types(self) -> list[dict]:
        root = self.collection("VBTVchTypes", "<TYPE>VoucherType</TYPE>" + _methods("Name", "Parent"))
        return [{"name": _name(v), "parent": _t(v, "PARENT")} for v in root.iter("VOUCHERTYPE")]

    VCH_FETCH = ("<FETCH>Date, VoucherTypeName, VoucherNumber, PartyLedgerName, Narration, Reference, GUID, AlterID, "
                 "MasterID, IsCancelled, IsOptional, IsPostDated, IsDeleted, IsInvoice, AllLedgerEntries, LedgerEntries, "
                 "AllInventoryEntries, InventoryEntries</FETCH>")

    def vouchers_between(self, start: dt.date, end: dt.date) -> list[dict]:
        root = self.collection(
            "VBTVouchers", "<TYPE>Voucher</TYPE>" + self.VCH_FETCH + "<FILTER>VBTInRange</FILTER>",
            static={"SVFROMDATE": f"{start:%Y%m%d}", "SVTODATE": f"{end:%Y%m%d}"},
            formulas={"VBTInRange": f'$Date >= $$Date:"{tdate(start)}" AND $Date <= $$Date:"{tdate(end)}"'})
        return [parse_voucher(v) for v in root.iter("VOUCHER")]

    def vouchers_changed_since(self, alter_id: int, start: dt.date, end: dt.date) -> list[dict]:
        root = self.collection(
            "VBTChanged", "<TYPE>Voucher</TYPE>" + self.VCH_FETCH + "<FILTER>VBTChangedOnly</FILTER>",
            static={"SVFROMDATE": f"{start:%Y%m%d}", "SVTODATE": f"{end:%Y%m%d}"},
            formulas={"VBTChangedOnly": f"$AlterID > {int(alter_id)}"})
        return [parse_voucher(v) for v in root.iter("VOUCHER")]

    def stock_value(self, as_of: dt.date) -> tuple[Decimal, int]:
        """Total closing stock value on a date (only if stock items are kept in Tally)."""
        root = self.collection("VBTStock", "<TYPE>StockItem</TYPE>" + _methods("Name", "ClosingValue"),
                               static={"SVTODATE": f"{as_of:%Y%m%d}"})
        total, n = Decimal(0), 0
        for s in root.iter("STOCKITEM"):
            n += 1
            total += abs(_amount(_t(s, "CLOSINGVALUE")))
        return total, n


def _methods(*names: str) -> str:
    return "".join(f"<NATIVEMETHOD>{n}</NATIVEMETHOD>" for n in names)


# ---------------------------------------------------------------------------------------------------------------
# Reading Tally XML (works for live answers AND for files exported from Tally with Alt+E)
# ---------------------------------------------------------------------------------------------------------------
def _t(el: ET.Element, tag: str) -> str:
    x = el.find(tag)
    if x is None:
        return ""
    return (x.text or "").strip()


def _name(el: ET.Element) -> str:
    return (el.get("NAME") or _t(el, "NAME") or (el.findtext("NAME.LIST/NAME") or "")).strip()


_NUM = re.compile(r"-?\(?[\d,]*\.?\d+\)?")


def _amount(s: str) -> Decimal:
    """'-1234.50' / '1,234.50 Dr' / '₹ 1,234' / '(1234)' -> Decimal. Tally: negative = Debit."""
    if not s:
        return Decimal(0)
    s = s.strip()
    neg = s.startswith("-") or s.startswith("(")
    m = _NUM.search(s.replace("₹", ""))
    if not m:
        return Decimal(0)
    try:
        v = Decimal(m.group(0).strip("()-").replace(",", ""))
    except InvalidOperation:
        return Decimal(0)
    if s.endswith("Dr") and not neg:
        neg = True
    return -v if neg else v


def _qty(s: str) -> tuple[Decimal, str]:
    """'20 Nos' -> (20, 'Nos'); '-5.000 Kg' -> (-5, 'Kg')."""
    if not s:
        return Decimal(0), ""
    m = re.match(r"\s*(-?[\d,]*\.?\d+)\s*(.*)", s)
    if not m:
        return Decimal(0), ""
    try:
        return Decimal(m.group(1).replace(",", "")), m.group(2).split("=")[0].strip()
    except InvalidOperation:
        return Decimal(0), ""


def _date(s: str) -> str | None:
    s = (s or "").strip()
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _int(s: str) -> int:
    try:
        return int(re.sub(r"[^\d-]", "", s or "") or 0)
    except ValueError:
        return 0


def _yes(s: str) -> bool:
    return (s or "").strip().lower() == "yes"


def _dr(amount_text: str) -> str:
    """Convert Tally's signed amount (negative = Debit) to debit-positive, as a string for JSON."""
    return str(-_amount(amount_text))


def parse_ledger(lg: ET.Element) -> dict:
    return {
        "name": _name(lg), "parent": _t(lg, "PARENT"), "guid": _t(lg, "GUID"),
        "opening_dr": _dr(_t(lg, "OPENINGBALANCE")), "closing_dr": _dr(_t(lg, "CLOSINGBALANCE")),
        "credit_days": _int(_t(lg, "BILLCREDITPERIOD")),
        "gstin": _t(lg, "PARTYGSTIN") or _t(lg, "GSTIN"),
        "state": _t(lg, "LEDSTATENAME") or _t(lg, "STATENAME"),
        "bill_wise": _yes(_t(lg, "ISBILLWISEON")),
    }


def _ledger_lines(container: ET.Element, tag: str) -> list[dict]:
    out = []
    for e in container.findall(tag):
        name = _t(e, "LEDGERNAME")
        if not name:
            continue
        bills = [{"name": _t(b, "NAME"), "type": _t(b, "BILLTYPE"), "dr": _dr(_t(b, "AMOUNT")),
                  "credit_days": _int(_t(b, "BILLCREDITPERIOD"))}
                 for b in e.findall("BILLALLOCATIONS.LIST") if _t(b, "NAME") or _t(b, "BILLTYPE")]
        out.append({"ledger": name, "dr": _dr(_t(e, "AMOUNT")), "bills": bills})
    return out


def _balanced(lines: list[dict]) -> bool:
    return abs(sum(Decimal(x["dr"]) for x in lines)) < Decimal("0.05")


def parse_voucher(v: ET.Element) -> dict:
    # Accounting lines. In "invoice" style vouchers Tally keeps the party in LEDGERENTRIES and the
    # sales/purchase ledger inside each stock line (ACCOUNTINGALLOCATIONS); we combine whichever set balances.
    main = _ledger_lines(v, "ALLLEDGERENTRIES.LIST") or _ledger_lines(v, "LEDGERENTRIES.LIST")
    inv_tags = v.findall("ALLINVENTORYENTRIES.LIST") or v.findall("INVENTORYENTRIES.LIST")
    alloc = []
    stock = []
    for ie in inv_tags:
        q, unit = _qty(_t(ie, "BILLEDQTY") or _t(ie, "ACTUALQTY"))
        stock.append({"item": _t(ie, "STOCKITEMNAME"), "qty": str(abs(q)), "unit": unit,
                      "amount": str(abs(_amount(_t(ie, "AMOUNT")))),
                      "inward": _yes(_t(ie, "ISDEEMEDPOSITIVE"))})
        alloc += _ledger_lines(ie, "ACCOUNTINGALLOCATIONS.LIST")
    if alloc and not _balanced(main) and _balanced(main + alloc):
        lines = main + alloc
    else:
        lines = main
    return {
        "guid": _t(v, "GUID") or v.get("REMOTEID") or "",
        "alter_id": _int(_t(v, "ALTERID")),
        "date": _date(_t(v, "DATE")),
        "type": _t(v, "VOUCHERTYPENAME") or v.get("VCHTYPE") or "",
        "number": _t(v, "VOUCHERNUMBER"),
        "party": _t(v, "PARTYLEDGERNAME"),
        "narration": _t(v, "NARRATION")[:300],
        "cancelled": _yes(_t(v, "ISCANCELLED")) or _yes(_t(v, "ISDELETED")),
        "optional": _yes(_t(v, "ISOPTIONAL")) or _yes(_t(v, "ISPOSTDATED")),
        "lines": lines,
        "stock": [s for s in stock if s["item"]],
    }


def parse_file(path: str) -> dict:
    """Read a file exported from Tally (Day Book, List of Accounts...)."""
    with open(path, "rb") as f:
        root = ET.fromstring(clean_xml(f.read()))
    return {
        "groups": [{"name": _name(g), "parent": _t(g, "PARENT")} for g in root.iter("GROUP")],
        "ledgers": [parse_ledger(lg) for lg in root.iter("LEDGER")],
        "voucher_types": [{"name": _name(v), "parent": _t(v, "PARENT")} for v in root.iter("VOUCHERTYPE")],
        "vouchers": [parse_voucher(v) for v in root.iter("VOUCHER")],
    }


# ---------------------------------------------------------------------------------------------------------------
# Sending to the dashboard
# ---------------------------------------------------------------------------------------------------------------
class Dashboard:
    def __init__(self, url: str, token: str, timeout: int = 120):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def send(self, path: str, payload: dict) -> dict:
        body = gzip.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        req = urllib.request.Request(self.url + path, data=body, method="POST", headers={
            "Content-Type": "application/json", "Content-Encoding": "gzip",
            "Authorization": f"Bearer {self.token}", "X-Requested-With": "vbt-accounts",
            "User-Agent": f"vbt-tally-connector/{VERSION}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code == 401:
                raise RuntimeError("The dashboard did not accept the connector key. Create a new key in "
                                   "Settings > Tally link and paste it into connector.ini.") from None
            raise RuntimeError(f"Dashboard answered {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"Cannot reach the dashboard at {self.url} ({e.reason}). Check the internet.") from None

    def report_error(self, message: str) -> None:
        try:
            self.send("/api/tally/sync/error", {"message": message[:500], "agent_version": VERSION})
        except Exception:  # noqa: BLE001 - best effort only
            pass


# ---------------------------------------------------------------------------------------------------------------
# The sync itself
# ---------------------------------------------------------------------------------------------------------------
def fy_start(d: dt.date) -> dt.date:
    return dt.date(d.year if d.month >= 4 else d.year - 1, 4, 1)


def month_chunks(start: dt.date, end: dt.date):
    cur = start
    while cur <= end:
        nxt = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        yield cur, min(end, nxt - dt.timedelta(days=1))
        cur = nxt


def month_ends(start: dt.date, end: dt.date) -> list[dt.date]:
    out = [s - dt.timedelta(days=1) for s, _ in month_chunks(start, end)]
    out.append(end)
    return out


def sync_once(cfg: configparser.ConfigParser, state: State, force_full: bool = False) -> dict:
    t0 = time.time()
    tally = Tally(cfg.get("tally", "url"), cfg.get("tally", "company", fallback="").strip(),
                  cfg.getint("tally", "timeout", fallback=180))
    dash = Dashboard(cfg.get("dashboard", "url"), cfg.get("dashboard", "token"))

    companies = tally.companies()
    if not companies:
        raise TallyError("No company is open in Tally. Please open the company in Tally.")
    if tally.company:
        match = [c for c in companies if c["name"].lower() == tally.company.lower()]
        if not match:
            raise TallyError(f"Company '{tally.company}' is not open in Tally. Open companies: "
                             + ", ".join(c["name"] for c in companies))
        comp = match[0]
    else:
        if len(companies) > 1:
            raise TallyError("More than one company is open in Tally. Write the company name in connector.ini "
                             "(company = ...). Open companies: " + ", ".join(c["name"] for c in companies))
        comp = companies[0]
        tally.company = comp["name"]

    today = dt.date.today()
    keep_from = dt.date(fy_start(today).year - cfg.getint("sync", "past_years", fallback=1), 4, 1)
    books_from = dt.date.fromisoformat(comp["books_from"]) if comp.get("books_from") else keep_from
    window_from = max(keep_from, books_from)

    same_company = state.get("company_guid") == comp["guid"]
    last_full = state.get("last_full_date")
    full_hour = cfg.getint("sync", "full_refresh_hour", fallback=9)
    need_full = (force_full or not same_company or not last_full
                 or (last_full != today.isoformat() and dt.datetime.now().hour >= full_hour))
    masters_changed = not same_company or comp["alt_mst_id"] != state.get("alt_mst_id")
    vouchers_changed = not same_company or comp["alt_vch_id"] != state.get("alt_vch_id")

    if not (need_full or masters_changed or vouchers_changed):
        dash.send("/api/tally/sync", {"mode": "heartbeat", "company": comp, "agent_version": VERSION})
        log.info("No changes in Tally since last time.")
        return {"mode": "heartbeat", "vouchers": 0}

    payload: dict = {"company": comp, "agent_version": VERSION, "tally_today": today.isoformat()}
    # Masters are small: always send all of them together with today's closing balances (used to double-check figures).
    payload["groups"] = tally.groups()
    payload["ledgers"] = tally.ledgers(today)
    payload["voucher_types"] = tally.voucher_types()

    if need_full:
        payload["mode"] = "full"
        payload["window"] = {"from": window_from.isoformat(), "to": today.isoformat()}
        vouchers = []
        for a, b in month_chunks(window_from, today):  # month by month keeps Tally responsive
            got = tally.vouchers_between(a, b)
            log.info("Read %s: %d entries", f"{a:%b %Y}", len(got))
            vouchers += got
        payload["vouchers"] = vouchers
        value, items = tally.stock_value(today)
        if items:
            payload["stock_values"] = [{"date": d.isoformat(), "value": str(tally.stock_value(d)[0])}
                                       for d in month_ends(window_from, today)]
    else:
        payload["mode"] = "changes"
        changed = tally.vouchers_changed_since(state.get("alt_vch_id", 0), window_from, today)
        payload["vouchers"] = [v for v in changed if v["date"] and v["date"] >= window_from.isoformat()]
        value, items = tally.stock_value(today)
        if items:
            payload["stock_values"] = [{"date": today.isoformat(), "value": str(value)}]

    res = dash.send("/api/tally/sync", payload)
    state.set(company_guid=comp["guid"], alt_vch_id=comp["alt_vch_id"], alt_mst_id=comp["alt_mst_id"],
              last_sync=dt.datetime.now().isoformat(timespec="seconds"),
              **({"last_full_date": today.isoformat()} if need_full else {}))
    log.info("Sent %d entries (%s) in %.1fs. Dashboard says: %s", len(payload["vouchers"]), payload["mode"],
             time.time() - t0, res.get("message", "ok"))
    return {"mode": payload["mode"], "vouchers": len(payload["vouchers"])}


def send_files(cfg, files: list[str]) -> None:
    dash = Dashboard(cfg.get("dashboard", "url"), cfg.get("dashboard", "token"))
    merged = {"groups": [], "ledgers": [], "voucher_types": [], "vouchers": []}
    for f in files:
        part = parse_file(f)
        for k in merged:
            merged[k] += part[k]
        log.info("%s: %d groups, %d ledgers, %d entries", os.path.basename(f), len(part["groups"]),
                 len(part["ledgers"]), len(part["vouchers"]))
    dates = sorted(v["date"] for v in merged["vouchers"] if v["date"])
    company = {"name": cfg.get("tally", "company", fallback="").strip() or "Imported from file", "guid": "file-import",
               "alt_vch_id": 0, "alt_mst_id": 0}
    payload = {"mode": "full" if dates else "masters", "company": company, "agent_version": VERSION,
               "tally_today": dt.date.today().isoformat(), **merged}
    if dates:
        payload["window"] = {"from": dates[0], "to": dates[-1]}
    print(json.dumps(dash.send("/api/tally/sync", payload), indent=2))


def self_test(cfg) -> int:
    ok = True
    print(f"Vishakan Tally Connector {VERSION}\n")
    tally = Tally(cfg.get("tally", "url"), cfg.get("tally", "company", fallback="").strip(), 60)
    try:
        comps = tally.companies()
        print("✓ Tally answered. Open companies:", ", ".join(c["name"] for c in comps) or "(none!)")
        if not comps:
            ok = False
    except TallyError as e:
        print("✗", e)
        ok = False
    url, token = cfg.get("dashboard", "url"), cfg.get("dashboard", "token")
    if not token:
        print("✗ No connector key in connector.ini (dashboard > token).")
        ok = False
    else:
        try:
            r = Dashboard(url, token, 30).send("/api/tally/ping", {"agent_version": VERSION})
            print("✓ Dashboard answered:", r.get("message", "ok"))
        except RuntimeError as e:
            print("✗", e)
            ok = False
    print("\nAll good — you can schedule the connector." if ok else "\nPlease fix the ✗ items above.")
    return 0 if ok else 1


def setup_logging() -> None:
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.handlers.RotatingFileHandler(os.path.join(HERE, "connector.log"), maxBytes=1_000_000, backupCount=3,
                                              encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(sh)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Send Tally data to the Vishakan manager dashboard (read-only).")
    ap.add_argument("--config", default=os.path.join(HERE, "connector.ini"))
    ap.add_argument("--test", action="store_true", help="check connections and stop")
    ap.add_argument("--full", action="store_true", help="re-read everything now")
    ap.add_argument("--loop", action="store_true", help="keep running")
    ap.add_argument("--file", nargs="+", help="send exported Tally XML files instead of live Tally")
    a = ap.parse_args(argv)
    setup_logging()
    cfg = load_config(a.config)
    if a.test:
        return self_test(cfg)
    if a.file:
        send_files(cfg, a.file)
        return 0
    state = State(os.path.join(HERE, "connector-state.json"))
    while True:
        try:
            sync_once(cfg, state, force_full=a.full)
            code = 0
        except (TallyError, RuntimeError) as e:
            log.error("%s", e)
            Dashboard(cfg.get("dashboard", "url"), cfg.get("dashboard", "token"), 20).report_error(str(e))
            code = 1
        except Exception as e:  # noqa: BLE001 - keep the loop alive, but record it
            log.exception("Unexpected problem")
            Dashboard(cfg.get("dashboard", "url"), cfg.get("dashboard", "token"), 20).report_error(repr(e))
            code = 2
        if not a.loop:
            return code
        a.full = False
        time.sleep(max(1, cfg.getint("sync", "minutes", fallback=10)) * 60)


if __name__ == "__main__":
    sys.exit(main())
