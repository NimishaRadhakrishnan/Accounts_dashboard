"""Bill / expense / invoice attachments. Stored outside any web root and served only to signed-in users."""
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import Actor, get_actor, require
from app.core.errors import DomainError, NotFound
from app.models import Attachment, Expense, PurchaseBill, SalesInvoice
from app.services import audit

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

ALLOWED = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAGIC = {".pdf": b"%PDF", ".jpg": b"\xff\xd8\xff", ".png": b"\x89PNG", ".webp": b"RIFF"}
ENTITIES = {"purchase_bill": (PurchaseBill, "purchases"), "expense": (Expense, "expenses"),
            "sales_invoice": (SalesInvoice, "sales")}


def _check_access(actor: Actor, entity: str, action: str) -> None:
    if entity not in ENTITIES:
        raise DomainError("Unknown record type.")
    perm = f"{ENTITIES[entity][1]}.{action}"
    if not actor.can(perm):
        raise DomainError("You don't have access to this action.", 403)


@router.get("")
def list_attachments(entity: str, entity_id: int, db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    _check_access(actor, entity, "view")
    rows = db.scalars(select(Attachment).where(Attachment.entity == entity, Attachment.entity_id == entity_id)
                      .order_by(Attachment.id))
    return [{"id": a.id, "name": a.original_name, "content_type": a.content_type, "size": a.size_bytes,
             "uploaded_at": a.uploaded_at} for a in rows]


@router.post("")
async def upload(entity: str = Form(...), entity_id: int = Form(...), file: UploadFile = File(...),
                 db: Session = Depends(get_db), actor: Actor = Depends(require("dashboard.view"))):
    _check_access(actor, entity, "create")
    model = ENTITIES[entity][0]
    if not db.get(model, entity_id):
        raise NotFound("Record")
    ext = ALLOWED.get(file.content_type or "")
    if not ext:
        raise DomainError("Only PDF, JPG, PNG or WEBP files can be attached.")
    s = get_settings()
    data = await file.read(s.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise DomainError(f"File is larger than {s.max_upload_mb} MB.")
    if not data.startswith(MAGIC[ext]):
        raise DomainError("The file content doesn't match its type.")
    os.makedirs(s.upload_dir, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(s.upload_dir, stored), "wb") as f:
        f.write(data)
    a = Attachment(entity=entity, entity_id=entity_id, original_name=os.path.basename(file.filename or "file")[:200],
                   stored_name=stored, content_type=file.content_type, size_bytes=len(data), uploaded_by_id=actor.id)
    db.add(a)
    db.flush()
    audit.record(db, actor, "attach", entity, entity_id, f"Attached {a.original_name}")
    db.commit()
    return {"id": a.id, "name": a.original_name}


@router.get("/{att_id}")
def download(att_id: int, db: Session = Depends(get_db), actor: Actor = Depends(get_actor)):
    a = db.get(Attachment, att_id)
    if not a:
        raise NotFound("Attachment")
    _check_access(actor, a.entity, "view")
    path = os.path.join(get_settings().upload_dir, a.stored_name)
    if not os.path.exists(path):
        raise NotFound("File")
    return FileResponse(path, media_type=a.content_type, filename=a.original_name)
