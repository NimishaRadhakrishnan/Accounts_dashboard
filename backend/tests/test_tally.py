"""Tally connector -> server -> overview, using the pretend Tally."""
import datetime as dt
import gzip
import json
import os
import sys
import threading
from decimal import Decimal as D
from http.server import ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tally-connector"))
import tally_simulator as sim  # noqa: E402
import vbt_tally_connector as conn  # noqa: E402

from app.main import app  # noqa: E402
from app.models import TallyCompany, TallyVoucher  # noqa: E402
from app.services import overview, tally_sync  # noqa: E402
from tests.conftest import PASSWORD, _user  # noqa: E402

TODAY = dt.date(2026, 11, 3)
H = {"X-Requested-With": "vbt-accounts"}


@pytest.fixture(scope="module")
def book():
    return sim.Book(TODAY)


@pytest.fixture(scope="module")
def tally_url(book):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), sim.make_handler(book))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def full_payload(tally_url) -> dict:
    t = conn.Tally(tally_url)
    comp = t.companies()[0]
    vs = []
    for a, b in conn.month_chunks(dt.date(2025, 4, 1), TODAY):
        vs += t.vouchers_between(a, b)
    return {"mode": "full", "company": comp, "tally_today": TODAY.isoformat(), "groups": t.groups(),
            "ledgers": t.ledgers(TODAY), "voucher_types": t.voucher_types(), "vouchers": vs,
            "window": {"from": "2025-04-01", "to": TODAY.isoformat()},
            "stock_values": [{"date": d.isoformat(), "value": str(t.stock_value(d)[0])}
                             for d in conn.month_ends(dt.date(2025, 4, 1), TODAY)]}


@pytest.fixture()
def loaded(db, tally_url):
    tally_sync.ingest(db, full_payload(tally_url))
    db.commit()
    return db


# ---------- parsing ----------
def test_parser_handles_invoice_style_and_bad_characters(tally_url):
    vs = conn.Tally(tally_url).vouchers_between(dt.date(2026, 10, 1), dt.date(2026, 10, 31))
    assert vs and all(conn._balanced(v["lines"]) for v in vs)
    inv = next(v for v in vs if v["stock"])
    assert any(line["ledger"].startswith("Sales GST") for line in inv["lines"])  # came from ACCOUNTINGALLOCATIONS
    assert inv["narration"] and "\x04" not in inv["narration"]


def test_amount_and_date_formats():
    assert conn._amount("-1,23,456.50") == D("-123456.50")
    assert conn._amount("1234.00 Dr") == D("-1234.00")
    assert conn._amount("(500)") == D("-500")
    assert conn._amount("₹ 1,000") == D("1000")
    assert conn._qty(" 20 Nos") == (D(20), "Nos")
    assert conn._date("20261103") == "2026-11-03" and conn._date("3-Nov-2026") == "2026-11-03"


def test_classify_walks_up_to_tally_groups():
    groups = {"Dealers - Kerala": "Sundry Debtors", "Sundry Debtors": "Current Assets", "Current Assets": None,
              "Selling Expenses": "Indirect Expenses", "Indirect Expenses": None, "Odd Group": "Odd Parent"}
    cats = tally_sync.classify(groups, {})
    assert cats["Dealers - Kerala"] == "debtors" and cats["Selling Expenses"] == "indirect_exp"
    assert cats["Odd Group"] == "other"
    assert tally_sync.classify(groups, {"odd group": "indirect_exp"})["Odd Group"] == "indirect_exp"


# ---------- ingest ----------
def test_full_sync_matches_tally_balances(loaded, book):
    st = overview.status(loaded)
    assert st["check_possible"] and all(c["match"] for c in st["check"])
    assert st["not_counted"] == 2  # one cancelled, one optional
    b = overview.Books(loaded, overview.current_company(loaded))
    for name in ("HDFC Bank - Current A/c", "Kongu Farm Inputs", "Cash"):
        ours = b.balances(("bank", "cash", "debtors"), dt.date(2026, 6, 30))[name]
        assert ours == book.balance(name, dt.date(2026, 6, 30))  # past dates exact too


def test_sales_and_expense_figures_match_source(loaded, book):
    b = overview.Books(loaded, overview.current_company(loaded))
    oct_ = overview.Span(dt.date(2026, 10, 1), dt.date(2026, 10, 31))
    expected_sales = sum(-dr for v in book.vouchers if not v["cancelled"] and not v["optional"]
                         and oct_.start <= v["date"] <= oct_.end
                         for n, dr, *_ in v["lines"] if n.startswith("Sales"))
    assert overview.sales(b, oct_) == expected_sales
    exp_ledgers = {e[0] for e in sim.EXPENSES} | {"Round Off"}
    expected_exp = sum(dr for v in book.vouchers if not v["cancelled"] and not v["optional"]
                       and oct_.start <= v["date"] <= oct_.end for n, dr, *_ in v["lines"] if n in exp_ledgers)
    assert overview.expenses(b, oct_) == expected_exp


def test_changes_mode_replaces_by_guid_and_full_mode_removes_deleted(loaded, tally_url):
    db = loaded
    comp = db.scalar(select(TallyCompany))
    v = db.scalar(select(TallyVoucher).where(TallyVoucher.counted.is_(True)).limit(1))
    payload = {"mode": "changes", "company": {"guid": comp.guid, "name": comp.name},
               "vouchers": [{"guid": v.guid, "date": v.date.isoformat(), "type": "Journal", "number": "X",
                             "lines": [{"ledger": "Cash", "dr": "10"}, {"ledger": "Rent", "dr": "-10"}]}]}
    tally_sync.ingest(db, payload)
    db.commit()
    assert db.scalar(select(TallyVoucher).where(TallyVoucher.guid == v.guid)).number == "X"
    count_before = db.query(TallyVoucher).count()
    # a full re-read without that voucher removes it
    p = full_payload(tally_url)
    p["vouchers"] = [x for x in p["vouchers"] if x["guid"] != v.guid]
    tally_sync.ingest(db, p)
    db.commit()
    assert db.query(TallyVoucher).count() == count_before - 1


def test_unbalanced_voucher_not_counted(db):
    tally_sync.ingest(db, {"mode": "changes", "company": {"guid": "g", "name": "C"}, "tally_today": "2026-11-03",
                           "groups": [], "ledgers": [], "vouchers": [
                               {"guid": "u1", "date": "2026-10-01", "lines": [{"ledger": "A", "dr": "10"}, {"ledger": "B", "dr": "-9"}]}]})
    db.commit()
    assert db.scalar(select(TallyVoucher).where(TallyVoucher.guid == "u1")).counted is False


# ---------- overview ----------
def test_overview_periods_and_story(loaded):
    for key in ("month", "last_month", "year"):
        o = overview.overview(loaded, key, today=TODAY)
        assert set(o["tiles"]) == {"sales", "collections", "expenses", "profit", "cash", "receivables"}
        assert o["story"] and o["story"][0]["kind"] == "sales"
        assert len(o["tiles"]["sales"]["spark"]) == 12
    o = overview.overview(loaded, "last_month", today=TODAY)
    assert o["period"]["label"] == "October 2026" and o["period"]["compare_label"] == "September"
    assert any("Repairs & Maintenance" in s["text"] for s in o["story"])  # spike planted in October
    chart = o["sales_chart"]["months"]
    assert chart[0]["month"] == "Apr" and chart[11]["this_year"] is None and chart[11]["last_year"] is not None


def test_ageing_adds_up_to_balance(loaded):
    b = overview.Books(loaded, overview.current_company(loaded))
    rows = overview.receivable_ageing(b, TODAY)
    for r in rows:
        if r["owed"] > 0:
            parts = r["not_due"] + r["late_30"] + r["late_60"] + r["late_90"] + r["late_90_plus"]
            assert parts == r["owed"]
    slow = {r["party"]: r for r in rows}
    assert slow["Idukki Spice Growers Supply"]["owed"] - slow["Idukki Spice Growers Supply"]["not_due"] > 0


def test_every_detail_view(loaded):
    for kind in ("sales", "collections", "expenses", "profit", "cash", "receivables"):
        d = overview.detail(loaded, kind, "last_month", today=TODAY)
        assert d["title"] and d["sections"]
    rows = overview.detail(loaded, "profit", "last_month", today=TODAY)["sections"][0]["rows"]
    assert rows[-1]["value"] == sum(r["value"] for r in rows[:-1])


# ---------- HTTP ----------
def test_connector_endpoints_need_key_and_accept_gzip(db, tally_url):
    key = tally_sync.create_key(db, "Office PC", None)
    db.commit()
    c = TestClient(app)
    assert c.post("/api/tally/sync", json={}, headers=H).status_code == 401
    assert c.post("/api/tally/sync", json={}, headers={**H, "Authorization": "Bearer nope"}).status_code == 401
    body = gzip.compress(json.dumps(full_payload(tally_url)).encode())
    r = c.post("/api/tally/sync", content=body, headers={**H, "Authorization": f"Bearer {key}",
                                                        "Content-Encoding": "gzip", "Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    assert r.json()["vouchers"] > 1000


def test_manager_sees_overview_but_not_admin(loaded):
    _user(loaded, "md", "management")
    loaded.commit()
    c = TestClient(app)
    c.post("/api/auth/login", json={"username": "md", "password": PASSWORD}, headers=H).raise_for_status()
    r = c.get("/api/overview?period=year")
    assert r.status_code == 200 and r.json()["tiles"]["sales"]["value"]
    assert c.get("/api/overview/receivables").status_code == 200
    assert c.get("/api/tally/status").status_code == 403
    assert c.post("/api/tally/keys", json={"label": "x"}, headers=H).status_code == 403


def test_connector_end_to_end_with_live_http(db, tally_url, tmp_path, monkeypatch):
    """The real connector script against the pretend Tally and the real API (in-process)."""
    key = tally_sync.create_key(db, "e2e", None)
    db.commit()
    client = TestClient(app)

    class Bridge(conn.Dashboard):
        def send(self, path, payload):
            r = client.post(path, content=gzip.compress(json.dumps(payload).encode()),
                            headers={**H, "Authorization": f"Bearer {self.token}", "Content-Encoding": "gzip",
                                     "Content-Type": "application/json"})
            assert r.status_code == 200, r.text
            return r.json()

    monkeypatch.setattr(conn, "Dashboard", Bridge)
    cfg = conn.configparser.ConfigParser()
    cfg.read_string(f"[tally]\nurl={tally_url}\n[dashboard]\nurl=http://x\ntoken={key}\n[sync]\nfull_refresh_hour=0\n")
    state = conn.State(str(tmp_path / "state.json"))
    assert conn.sync_once(cfg, state)["mode"] == "full"
    assert conn.sync_once(cfg, state)["mode"] == "heartbeat"
    assert overview.status(db)["check_possible"]


def test_connector_download_prefills_address(db):
    _user(db, "boss", "super_admin")
    db.commit()
    c = TestClient(app, base_url="https://accounts.example.in")
    c.post("/api/auth/login", json={"username": "boss", "password": PASSWORD}, headers=H).raise_for_status()
    r = c.get("/api/tally/connector.zip")
    assert r.status_code == 200
    import io
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert "VishakanConnector/vbt_tally_connector.py" in names and not any("simulator" in n for n in names)
    assert "url = https://accounts.example.in" in z.read("VishakanConnector/connector.ini").decode()
