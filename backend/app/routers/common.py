from datetime import date

from fastapi import Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Party


class ListParams:
    def __init__(self, q: str | None = Query(None, max_length=100), status: str | None = None,
                 party_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
                 page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
        self.q, self.status, self.party_id = q, status, party_id
        self.date_from, self.date_to, self.page, self.page_size = date_from, date_to, page, page_size


def filtered(model, p: ListParams, *, search_cols=()):
    q = select(model)
    if p.status:
        q = q.where(model.status.in_(p.status.split(",")))
    if p.party_id and hasattr(model, "party_id"):
        q = q.where(model.party_id == p.party_id)
    if p.date_from:
        q = q.where(model.date >= p.date_from)
    if p.date_to:
        q = q.where(model.date <= p.date_to)
    if p.q:
        like = f"%{p.q.strip()}%"
        conds = [model.number.ilike(like)] + [c.ilike(like) for c in search_cols]
        if hasattr(model, "party_id"):
            conds.append(model.party_id.in_(select(Party.id).where(or_(Party.name.ilike(like),
                                                                       Party.code.ilike(like)))))
        q = q.where(or_(*conds))
    return q


def paginate(db: Session, q, p: ListParams, order):
    total = db.scalar(select(func.count()).select_from(q.order_by(None).subquery()))
    items = db.scalars(q.order_by(*order).offset((p.page - 1) * p.page_size).limit(p.page_size)).unique().all()
    return items, {"total": total, "page": p.page, "page_size": p.page_size}


def done(db: Session, value):
    db.commit()
    return value
