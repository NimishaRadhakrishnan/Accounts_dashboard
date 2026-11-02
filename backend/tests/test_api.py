"""HTTP-level checks: auth, CSRF header, permissions, exports, money as strings."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import PASSWORD

H = {"X-Requested-With": "vbt-accounts"}


@pytest.fixture()
def client(w):
    return TestClient(app)


def login(c, username):
    r = c.post("/api/auth/login", json={"username": username, "password": PASSWORD}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def test_requires_login(client):
    assert client.get("/api/dashboard").status_code == 401


def test_csrf_header_required(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 403


def test_login_sets_httponly_cookie_and_returns_permissions(client):
    me = login(client, "accountant")
    assert "sales.create" in me["permissions"] and "users.manage" not in me["permissions"]
    cookie = client.cookies.jar
    assert any(c.name == "access_token" for c in cookie)
    assert client.get("/api/auth/me").json()["username"] == "accountant"


def test_lockout_after_failed_attempts(client):
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "ceo", "password": "wrong-password"}, headers=H)
    r = client.post("/api/auth/login", json={"username": "ceo", "password": PASSWORD}, headers=H)
    assert r.status_code == 429


def test_role_permissions_enforced(client, w):
    login(client, "accountant")
    assert client.get("/api/users").status_code == 403
    assert client.get("/api/audit-logs").status_code == 403
    login(client, "ceo")
    body = {"party_id": w.tn.id, "date": "2026-04-10",
            "lines": [{"description": "x", "qty": "1", "rate": "100", "gst_rate": "5"}]}
    assert client.post("/api/sales-invoices", json=body, headers=H).status_code == 403
    assert client.get("/api/dashboard").status_code == 200


def test_invoice_round_trip_money_as_strings(client, w):
    login(client, "accountant")
    body = {"party_id": w.tn.id, "date": "2026-04-10",
            "lines": [{"product_id": w.prod.id, "description": "Azo", "qty": "10", "rate": "320", "gst_rate": "5"}]}
    r = client.post("/api/sales-invoices?post=true", json=body, headers=H)
    assert r.status_code == 200, r.text
    inv = r.json()
    assert inv["number"] == "VBT/26-27/0001" and inv["grand_total"] == "3360.00"
    pdf = client.get(f"/api/sales-invoices/{inv['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    lst = client.get("/api/sales-invoices").json()
    assert lst["total"] == 1 and lst["items"][0]["payment_status"] == "unpaid"


def test_validation_messages_are_readable(client, w):
    login(client, "accountant")
    r = client.post("/api/sales-invoices", json={"party_id": w.tn.id, "date": "2026-04-10", "lines": []}, headers=H)
    assert r.status_code == 422 and "lines" in r.json()["detail"]
    r = client.post("/api/sales-invoices", headers=H, json={
        "party_id": w.tn.id, "date": "2030-04-10",
        "lines": [{"description": "x", "qty": "1", "rate": "1", "gst_rate": "5"}]})
    assert r.status_code == 400 and "financial year" in r.json()["detail"]


@pytest.mark.parametrize("key", ["sales-register", "purchase-register", "gst-summary", "hsn-summary",
                                 "expense-report", "expense-by-category", "profit-loss", "trial-balance"])
@pytest.mark.parametrize("fmt", ["xlsx", "pdf"])
def test_report_exports(client, w, key, fmt):
    login(client, "auditor")
    r = client.get(f"/api/reports/{key}/export", params={"fmt": fmt, "date_from": "2026-04-01",
                                                          "date_to": "2026-04-30"})
    assert r.status_code == 200, r.text
    assert r.content[:4] in (b"%PDF", b"PK\x03\x04")


def test_ageing_party_and_bank_reports(client, w):
    login(client, "manager")
    assert client.get("/api/reports/receivable-ageing", params={"as_of": str(date(2026, 5, 1))}).status_code == 200
    r = client.get("/api/reports/party-ledger", params={"party_id": w.tn.id, "date_from": "2026-04-01",
                                                        "date_to": "2026-04-30"})
    assert r.status_code == 200
    r = client.get("/api/reports/bank-book", params={"bank_id": w.bank.id, "date_from": "2026-04-01",
                                                     "date_to": "2026-04-30"})
    assert r.json()["rows"][-1]["balance"] == "100000.00"


def test_admin_cannot_view_passwords_only_reset(client, w):
    login(client, "admin")
    users = client.get("/api/users").json()
    assert all(k not in u for u in users for k in ("password", "password_hash"))
    r = client.post(f"/api/users/{w.acct.id}/reset-password", json={"temp_password": "short"}, headers=H)
    assert r.status_code == 422
    r = client.post(f"/api/users/{w.acct.id}/reset-password", json={"temp_password": "NewTemp12345"}, headers=H)
    assert r.status_code == 200 and r.json()["must_change_password"] is True


def test_last_super_admin_protected(client, w):
    login(client, "admin")
    r = client.put(f"/api/users/{w.admin.id}", json={"role_code": "accountant"}, headers=H)
    assert r.status_code == 400
