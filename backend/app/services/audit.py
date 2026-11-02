from sqlalchemy.orm import Session

from app.core.deps import Actor
from app.models import AuditLog


def record(db: Session, actor: Actor | None, action: str, entity: str, entity_id=None,
           summary: str | None = None, old: dict | None = None, new: dict | None = None) -> None:
    db.add(AuditLog(
        user_id=actor.id if actor else None,
        username=actor.user.username if actor else None,
        action=action, entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        summary=(summary or "")[:300] or None,
        old_value=old, new_value=new,
        ip=actor.ip if actor else None,
    ))
