"""Dashboard, outstanding, reports and exports."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Actor, require
from app.core.errors import DomainError
from app.services import audit, reports, tally
from app.services.common import company
from app.services.dashboard import overview
from app.services.exports import report_pdf, report_xlsx
from app.services.outstanding import ageing

router = APIRouter(prefix="/api", tags=["dashboard & reports"])


@router.get("/dashboard")
def dashboard(on: date | None = None, db: Session = Depends(get_db), _: Actor = Depends(require("dashboard.view"))):
    return overview(db, on)


@router.get("/outstanding/{kind}")
def outstanding(kind: str, as_of: date | None = None, db: Session = Depends(get_db),
                _: Actor = Depends(require("outstanding.view"))):
    if kind not in ("receivable", "payable"):
        raise DomainError("Use receivable or payable.", 404)
    return ageing(db, kind, as_of)


@router.get("/reports")
def catalogue(_: Actor = Depends(require("reports.view"))):
    return reports.CATALOGUE


def _build(db, key, date_from, date_to, as_of, party_id, bank_id):
    return reports.build(db, key, start=date_from, end=date_to, as_of=as_of, party_id=party_id, bank_id=bank_id)


@router.get("/reports/{key}")
def run_report(key: str, date_from: date | None = None, date_to: date | None = None, as_of: date | None = None,
               party_id: int | None = None, bank_id: int | None = None, db: Session = Depends(get_db),
               _: Actor = Depends(require("reports.view"))):
    r = _build(db, key, date_from, date_to, as_of, party_id, bank_id)
    return {"key": r.key, "title": r.title, "subtitle": r.subtitle, "notes": r.notes,
            "columns": [{"key": c.key, "label": c.label, "kind": c.kind} for c in r.columns],
            "rows": r.rows, "totals": r.totals}


@router.get("/reports/{key}/export")
def export_report(key: str, fmt: str = Query("xlsx", pattern="^(xlsx|pdf)$"), date_from: date | None = None,
                  date_to: date | None = None, as_of: date | None = None, party_id: int | None = None,
                  bank_id: int | None = None, db: Session = Depends(get_db),
                  actor: Actor = Depends(require("reports.export"))):
    r = _build(db, key, date_from, date_to, as_of, party_id, bank_id)
    comp = company(db)
    if fmt == "xlsx":
        content = report_xlsx(r, comp)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = report_pdf(r, comp)
        media = "application/pdf"
    audit.record(db, actor, "export", "report", key, f"{r.title} ({r.subtitle}) as {fmt.upper()}")
    db.commit()
    stamp = (date_to or as_of or date.today()).isoformat()
    return Response(content, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{key}-{stamp}.{fmt}"'})


@router.get("/exports/tally")
def export_tally(date_from: date, date_to: date, db: Session = Depends(get_db),
                 actor: Actor = Depends(require("reports.export"))):
    if date_to < date_from:
        raise DomainError("End date is before start date.")
    xml, count = tally.export_vouchers(db, date_from, date_to)
    audit.record(db, actor, "export", "tally", None, f"Tally XML {date_from}..{date_to}, {count} vouchers")
    db.commit()
    return Response(xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="tally-vouchers-{date_from}-{date_to}.xml"',
                             "X-Voucher-Count": str(count)})
