"""Tally connector endpoints (key-authenticated) and the manager overview (user-authenticated)."""
import io
import json
import zipfile
import zlib
from pathlib import Path

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import Actor, require
from app.core.errors import DomainError
from app.models import AppSetting, ConnectorKey
from app.routers.common import done
from app.services import audit, overview, tally_sync
from app.services.tally_sync import CATEGORY_LABELS, MAX_BODY

router = APIRouter(prefix="/api", tags=["tally & overview"])


async def _json_body(request: Request) -> dict:
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise DomainError("Upload too large.", 413)
    if request.headers.get("content-encoding", "").lower() == "gzip":
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        raw = d.decompress(raw, MAX_BODY + 1)
        if len(raw) > MAX_BODY or d.unconsumed_tail:
            raise DomainError("Upload too large.", 413)
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        raise DomainError("Upload is not valid JSON.") from None
    if not isinstance(data, dict):
        raise DomainError("Upload is not valid.")
    return data


# ---------- connector ----------
@router.post("/tally/ping")
def ping(request: Request, authorization: str | None = Header(None), db: Session = Depends(get_db)):
    key = tally_sync.check_key(db, authorization)
    db.commit()
    return {"message": f"Connected. Key '{key.label}' is valid."}


@router.post("/tally/sync")
async def sync(request: Request, authorization: str | None = Header(None), db: Session = Depends(get_db)):
    tally_sync.check_key(db, authorization)
    payload = await _json_body(request)
    try:
        res = tally_sync.ingest(db, payload)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return res


@router.post("/tally/sync/error")
async def sync_error(request: Request, authorization: str | None = Header(None), db: Session = Depends(get_db)):
    tally_sync.check_key(db, authorization)
    tally_sync.record_error(db, await _json_body(request))
    db.commit()
    return {"ok": True}


# ---------- manager ----------
@router.get("/overview")
def get_overview(period: str = Query("month", pattern="^(month|last_month|year)$"), db: Session = Depends(get_db),
                 _: Actor = Depends(require("dashboard.view"))):
    return overview.overview(db, period)


@router.get("/overview/{kind}")
def get_detail(kind: str, period: str = Query("month", pattern="^(month|last_month|year)$"),
               db: Session = Depends(get_db), _: Actor = Depends(require("dashboard.view"))):
    return overview.detail(db, kind, period)


@router.get("/freshness")
def get_freshness(db: Session = Depends(get_db), _: Actor = Depends(require("dashboard.view"))):
    try:
        return overview.freshness(overview.current_company(db))
    except DomainError:
        return {"minutes_ago": None, "stale": True, "error": "No data from Tally yet."}


# ---------- administrator ----------
class KeyIn(BaseModel):
    label: str = Field(min_length=2, max_length=100)


class GroupMapIn(BaseModel):
    mapping: dict[str, str]


@router.get("/tally/status")
def get_status(db: Session = Depends(get_db), _: Actor = Depends(require("settings.manage"))):
    keys = [{"id": k.id, "label": k.label, "hint": k.hint, "created_at": k.created_at, "last_used_at": k.last_used_at}
            for k in db.scalars(select(ConnectorKey).where(ConnectorKey.revoked.is_(False)).order_by(ConnectorKey.id))]
    return {**overview.status(db), "keys": keys, "category_labels": CATEGORY_LABELS}


@router.post("/tally/keys")
def new_key(body: KeyIn, db: Session = Depends(get_db), actor: Actor = Depends(require("settings.manage"))):
    key = tally_sync.create_key(db, body.label, actor.id)
    audit.record(db, actor, "create", "connector_key", None, f"Connector key '{body.label}' created")
    return done(db, {"key": key, "message": "Copy this key now. It will not be shown again."})


@router.delete("/tally/keys/{key_id}")
def revoke_key(key_id: int, db: Session = Depends(get_db), actor: Actor = Depends(require("settings.manage"))):
    k = db.get(ConnectorKey, key_id)
    if not k:
        raise DomainError("Key not found.", 404)
    k.revoked = True
    audit.record(db, actor, "revoke", "connector_key", k.id, f"Connector key '{k.label}' turned off")
    return done(db, {"ok": True})


@router.get("/tally/groups")
def groups(db: Session = Depends(get_db), _: Actor = Depends(require("settings.manage"))):
    from app.models import TallyGroup
    c = overview.current_company(db)
    rows = db.scalars(select(TallyGroup).where(TallyGroup.company_id == c.id).order_by(TallyGroup.name)).all()
    return {"groups": [{"name": g.name, "parent": g.parent, "category": g.category} for g in rows],
            "overrides": tally_sync.group_overrides(db), "labels": CATEGORY_LABELS}


@router.put("/tally/group-map")
def set_group_map(body: GroupMapIn, db: Session = Depends(get_db), actor: Actor = Depends(require("settings.manage"))):
    bad = [v for v in body.mapping.values() if v not in CATEGORY_LABELS]
    if bad:
        raise DomainError(f"Unknown category: {bad[0]}")
    row = db.get(AppSetting, "tally_group_map") or AppSetting(key="tally_group_map", value="{}",
                                                              description="Tally group -> dashboard category overrides")
    row.value = json.dumps(body.mapping)
    db.add(row)
    db.flush()
    c = overview.current_company(db)
    tally_sync.reclassify(db, c.id)
    audit.record(db, actor, "update", "tally_group_map", None, f"{len(body.mapping)} group mappings saved")
    return done(db, {"ok": True})



CONNECTOR_FILES = ["vbt_tally_connector.py", "connector.ini", "1-test-connection.bat", "2-install-auto-update.bat",
                   "3-stop-auto-update.bat", "run-connector.bat", "SETUP-GUIDE.txt"]


def _connector_dir() -> Path:
    configured = get_settings().connector_dir
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "tally-connector"


@router.get("/tally/connector.zip")
def connector_zip(request: Request, db: Session = Depends(get_db), actor: Actor = Depends(require("settings.manage"))):
    folder = _connector_dir()
    if not (folder / "vbt_tally_connector.py").exists():
        raise DomainError("Connector files are not on the server.", 404)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    proto = request.headers.get("x-forwarded-proto") or ("https" if get_settings().is_production else request.url.scheme)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in CONNECTOR_FILES:
            path = folder / name
            if not path.exists():
                continue
            data = path.read_text(encoding="utf-8")
            if name == "connector.ini" and host:
                data = data.replace("url = https://accounts.example.com", f"url = {proto}://{host}")
            z.writestr(f"VishakanConnector/{name}", data)
    audit.record(db, actor, "export", "connector", None, "Connector downloaded")
    db.commit()
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="vishakan-tally-connector.zip"'})

