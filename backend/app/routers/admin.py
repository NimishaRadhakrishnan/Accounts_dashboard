"""Settings, master data, users, roles, audit log."""
from datetime import date

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import Actor, require
from app.core.errors import DomainError, NotFound
from app.models import (Account, AppSetting, AuditLog, BankAccount, Company, ExpenseCategory, FinancialYear, Party,
                        PaymentTerm, PeriodLock, Permission, Product, Role, User)
from app.routers.common import done
from app.schemas import (BankAccountIn, CompanyIn, ExpenseCategoryIn, FinancialYearIn, NumberSeriesIn, PartyIn,
                         PaymentTermIn, PeriodLockIn, ProductIn, ResetPasswordIn, RolePermissionsIn, SettingIn,
                         TallyMapIn, UserIn, UserUpdateIn)
from app.services import audit, ledger, masters, serialize
from app.services import users as user_svc
from app.services.common import snapshot

router = APIRouter(prefix="/api", tags=["settings & masters"])


# ---------- Company ----------
@router.get("/company")
def get_company(db: Session = Depends(get_db), _: Actor = Depends(require("dashboard.view"))):
    c = db.scalar(select(Company).limit(1))
    return snapshot(c) if c else None


@router.put("/company")
def put_company(body: CompanyIn, db: Session = Depends(get_db), actor: Actor = Depends(require("settings.manage"))):
    return done(db, snapshot(masters.save_company(db, actor, body)))


@router.post("/company/logo")
async def upload_logo(file: UploadFile = File(...), db: Session = Depends(get_db),
                      actor: Actor = Depends(require("settings.manage"))):
    import os
    import uuid
    if file.content_type not in ("image/png", "image/jpeg"):
        raise DomainError("Logo must be a PNG or JPG image.")
    data = await file.read()
    if len(data) > 2 * 1024 * 1024:
        raise DomainError("Logo must be under 2 MB.")
    s = get_settings()
    os.makedirs(s.upload_dir, exist_ok=True)
    path = os.path.join(s.upload_dir, f"logo-{uuid.uuid4().hex}{'.png' if 'png' in file.content_type else '.jpg'}")
    with open(path, "wb") as f:
        f.write(data)
    c = db.scalar(select(Company).limit(1))
    c.logo_path = path
    audit.record(db, actor, "update", "company", c.id, "Logo uploaded")
    return done(db, {"ok": True})


@router.get("/company/logo")
def get_logo(db: Session = Depends(get_db), _: Actor = Depends(require("dashboard.view"))):
    import os

    from fastapi.responses import FileResponse
    c = db.scalar(select(Company).limit(1))
    if not c or not c.logo_path or not os.path.exists(c.logo_path):
        raise NotFound("Logo")
    return FileResponse(c.logo_path)


# ---------- Parties ----------
@router.get("/parties")
def list_parties(kind: str | None = Query(None, pattern="^(customer|supplier)$"), q: str | None = None,
                 active: bool | None = None, db: Session = Depends(get_db),
                 _: Actor = Depends(require("masters.view"))):
    stmt = select(Party)
    if kind == "customer":
        stmt = stmt.where(Party.is_customer.is_(True))
    elif kind == "supplier":
        stmt = stmt.where(Party.is_supplier.is_(True))
    if active is not None:
        stmt = stmt.where(Party.is_active.is_(active))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Party.name.ilike(like), Party.code.ilike(like), Party.gstin.ilike(like),
                              Party.city.ilike(like)))
    parties = db.scalars(stmt.order_by(Party.name)).all()
    debt = {pid: amt for pid, amt in db.execute(
        select(ledger.JournalLine.party_id, func.sum(ledger.JournalLine.debit - ledger.JournalLine.credit))
        .where(ledger.JournalLine.party_id.isnot(None)).group_by(ledger.JournalLine.party_id))}
    return [{**serialize.party(p), "balance": debt.get(p.id, 0)} for p in parties]


@router.get("/parties/{party_id}")
def get_party(party_id: int, db: Session = Depends(get_db), _: Actor = Depends(require("masters.view"))):
    p = db.get(Party, party_id)
    if not p:
        raise NotFound("Party")
    return serialize.party(p)


@router.post("/parties")
def create_party(body: PartyIn, db: Session = Depends(get_db), actor: Actor = Depends(require("masters.manage"))):
    return done(db, serialize.party(masters.save_party(db, actor, body)))


@router.put("/parties/{party_id}")
def update_party(party_id: int, body: PartyIn, db: Session = Depends(get_db),
                 actor: Actor = Depends(require("masters.manage"))):
    return done(db, serialize.party(masters.save_party(db, actor, body, party_id)))


# ---------- Products ----------
@router.get("/products")
def list_products(q: str | None = None, active: bool | None = None, db: Session = Depends(get_db),
                  _: Actor = Depends(require("masters.view"))):
    stmt = select(Product)
    if active is not None:
        stmt = stmt.where(Product.is_active.is_(active))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.code.ilike(like), Product.hsn_code.ilike(like)))
    return [serialize.product(p) for p in db.scalars(stmt.order_by(Product.name))]


@router.post("/products")
def create_product(body: ProductIn, db: Session = Depends(get_db), actor: Actor = Depends(require("masters.manage"))):
    return done(db, serialize.product(masters.save_product(db, actor, body)))


@router.put("/products/{product_id}")
def update_product(product_id: int, body: ProductIn, db: Session = Depends(get_db),
                   actor: Actor = Depends(require("masters.manage"))):
    return done(db, serialize.product(masters.save_product(db, actor, body, product_id)))


# ---------- Banks ----------
@router.get("/bank-accounts")
def list_banks(db: Session = Depends(get_db), _: Actor = Depends(require("masters.view"))):
    return [serialize.bank(b, ledger.balance(db, ledger.CASH_BANK, bank_account_id=b.id))
            for b in db.scalars(select(BankAccount).order_by(BankAccount.kind, BankAccount.name))]


@router.post("/bank-accounts")
def create_bank(body: BankAccountIn, db: Session = Depends(get_db), actor: Actor = Depends(require("masters.manage"))):
    return done(db, serialize.bank(masters.save_bank(db, actor, body)))


@router.put("/bank-accounts/{bank_id}")
def update_bank(bank_id: int, body: BankAccountIn, db: Session = Depends(get_db),
                actor: Actor = Depends(require("masters.manage"))):
    return done(db, serialize.bank(masters.save_bank(db, actor, body, bank_id)))


# ---------- Expense categories & payment terms ----------
@router.get("/expense-categories")
def list_categories(db: Session = Depends(get_db), _: Actor = Depends(require("expenses.view"))):
    return [{"id": c.id, "name": c.name, "is_active": c.is_active, "account_code": c.account.code,
             "tally_ledger_name": c.account.tally_ledger_name}
            for c in db.scalars(select(ExpenseCategory).order_by(ExpenseCategory.name))]


@router.post("/expense-categories")
def create_category(body: ExpenseCategoryIn, db: Session = Depends(get_db),
                    actor: Actor = Depends(require("masters.manage"))):
    c = masters.save_category(db, actor, body)
    return done(db, {"id": c.id, "name": c.name, "is_active": c.is_active})


@router.put("/expense-categories/{cat_id}")
def update_category(cat_id: int, body: ExpenseCategoryIn, db: Session = Depends(get_db),
                    actor: Actor = Depends(require("masters.manage"))):
    c = masters.save_category(db, actor, body, cat_id)
    return done(db, {"id": c.id, "name": c.name, "is_active": c.is_active})


@router.get("/payment-terms")
def list_terms(db: Session = Depends(get_db), _: Actor = Depends(require("masters.view"))):
    return [{"id": t.id, "name": t.name, "days": t.days, "is_active": t.is_active}
            for t in db.scalars(select(PaymentTerm).order_by(PaymentTerm.days))]


@router.post("/payment-terms")
def create_term(body: PaymentTermIn, db: Session = Depends(get_db), actor: Actor = Depends(require("masters.manage"))):
    t = masters.save_term(db, actor, body)
    return done(db, {"id": t.id, "name": t.name, "days": t.days, "is_active": t.is_active})


@router.put("/payment-terms/{term_id}")
def update_term(term_id: int, body: PaymentTermIn, db: Session = Depends(get_db),
                actor: Actor = Depends(require("masters.manage"))):
    t = masters.save_term(db, actor, body, term_id)
    return done(db, {"id": t.id, "name": t.name, "days": t.days, "is_active": t.is_active})


# ---------- App settings, numbering, years, periods ----------
@router.get("/settings")
def get_settings_(db: Session = Depends(get_db), _: Actor = Depends(require("dashboard.view"))):
    return [{"key": s.key, "value": s.value, "description": s.description}
            for s in db.scalars(select(AppSetting).order_by(AppSetting.key))]


@router.put("/settings/{key}")
def put_setting(key: str, body: SettingIn, db: Session = Depends(get_db),
                actor: Actor = Depends(require("settings.manage"))):
    s = masters.set_setting(db, actor, key, body.value)
    return done(db, {"key": s.key, "value": s.value})


@router.get("/number-series")
def list_series(db: Session = Depends(get_db), _: Actor = Depends(require("settings.manage"))):
    rows = masters.ensure_series(db)
    out = [{"id": s.id, "doc_type": s.doc_type, "fy_label": s.fy_label, "prefix": s.prefix,
            "next_number": s.next_number, "preview": f"{s.prefix}/{s.fy_label}/{s.next_number:0{s.padding}d}"}
           for s in rows]
    return done(db, out)


@router.put("/number-series/{series_id}")
def update_series(series_id: int, body: NumberSeriesIn, db: Session = Depends(get_db),
                  actor: Actor = Depends(require("settings.manage"))):
    s = masters.update_series(db, actor, series_id, body)
    return done(db, {"id": s.id, "prefix": s.prefix, "next_number": s.next_number})


@router.get("/financial-years")
def list_fys(db: Session = Depends(get_db), _: Actor = Depends(require("dashboard.view"))):
    return [{"id": f.id, "label": f.label, "start_date": f.start_date, "end_date": f.end_date,
             "is_current": f.is_current, "is_closed": f.is_closed}
            for f in db.scalars(select(FinancialYear).order_by(FinancialYear.start_date.desc()))]


@router.post("/financial-years")
def create_fy(body: FinancialYearIn, db: Session = Depends(get_db), actor: Actor = Depends(require("settings.manage"))):
    fy = masters.add_fy(db, actor, body.start_year, body.make_current)
    return done(db, {"id": fy.id, "label": fy.label})


@router.get("/period-locks")
def list_locks(db: Session = Depends(get_db), _: Actor = Depends(require("dashboard.view"))):
    return [{"id": lk.id, "year": lk.year, "month": lk.month, "locked_at": lk.locked_at}
            for lk in db.scalars(select(PeriodLock).order_by(PeriodLock.year.desc(), PeriodLock.month.desc()))]


@router.post("/period-locks")
def lock(body: PeriodLockIn, db: Session = Depends(get_db), actor: Actor = Depends(require("periods.lock"))):
    lk = masters.lock_period(db, actor, body)
    return done(db, {"id": lk.id})


@router.delete("/period-locks/{lock_id}")
def unlock(lock_id: int, db: Session = Depends(get_db), actor: Actor = Depends(require("periods.lock"))):
    masters.unlock_period(db, actor, lock_id)
    return done(db, {"ok": True})


@router.get("/tally-ledgers")
def tally_map(db: Session = Depends(get_db), _: Actor = Depends(require("settings.manage"))):
    return [{"code": a.code, "name": a.name, "type": a.type, "tally_ledger_name": a.tally_ledger_name}
            for a in db.scalars(select(Account).where(Account.code != ledger.CASH_BANK).order_by(Account.type,
                                                                                                Account.name))]


@router.put("/tally-ledgers")
def put_tally_map(body: TallyMapIn, db: Session = Depends(get_db), actor: Actor = Depends(require("settings.manage"))):
    a = masters.map_tally(db, actor, body)
    return done(db, {"code": a.code, "tally_ledger_name": a.tally_ledger_name})


# ---------- Users & roles ----------
@router.get("/users")
def list_users(db: Session = Depends(get_db), _: Actor = Depends(require("users.manage"))):
    return [serialize.user(u) for u in db.scalars(select(User).order_by(User.full_name))]


@router.post("/users")
def create_user(body: UserIn, db: Session = Depends(get_db), actor: Actor = Depends(require("users.manage"))):
    return done(db, serialize.user(user_svc.create_user(db, actor, body)))


@router.put("/users/{user_id}")
def update_user(user_id: int, body: UserUpdateIn, db: Session = Depends(get_db),
                actor: Actor = Depends(require("users.manage"))):
    return done(db, serialize.user(user_svc.update_user(db, actor, user_id, body)))


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, body: ResetPasswordIn, db: Session = Depends(get_db),
                   actor: Actor = Depends(require("users.manage"))):
    return done(db, serialize.user(user_svc.reset_password(db, actor, user_id, body.temp_password)))


@router.get("/roles")
def list_roles(db: Session = Depends(get_db), _: Actor = Depends(require("users.manage"))):
    perms = db.scalars(select(Permission).order_by(Permission.id)).all()
    counts = dict(db.execute(select(User.role_id, func.count(User.id)).group_by(User.role_id)).all())
    return {
        "permissions": [{"code": p.code, "label": p.label, "group": p.group} for p in perms],
        "roles": [{"code": r.code, "name": r.name, "description": r.description, "users": counts.get(r.id, 0),
                   "permissions": sorted(p.code for p in r.permissions)}
                  for r in db.scalars(select(Role).order_by(Role.id))],
    }


@router.put("/roles/{role_code}")
def update_role(role_code: str, body: RolePermissionsIn, db: Session = Depends(get_db),
                actor: Actor = Depends(require("users.manage"))):
    r = user_svc.set_role_permissions(db, actor, role_code, body.permissions)
    return done(db, {"code": r.code, "permissions": sorted(p.code for p in r.permissions)})


# ---------- Audit ----------
@router.get("/audit-logs")
def audit_logs(entity: str | None = None, action: str | None = None, user_id: int | None = None,
               date_from: date | None = None, date_to: date | None = None, q: str | None = None,
               page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
               db: Session = Depends(get_db), _: Actor = Depends(require("audit.view"))):
    stmt = select(AuditLog)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if date_from:
        stmt = stmt.where(func.date(AuditLog.at) >= date_from)
    if date_to:
        stmt = stmt.where(func.date(AuditLog.at) <= date_to)
    if q:
        stmt = stmt.where(AuditLog.summary.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [{"id": a.id, "at": a.at, "username": a.username, "action": a.action, "entity": a.entity,
                       "entity_id": a.entity_id, "summary": a.summary, "old_value": a.old_value,
                       "new_value": a.new_value, "ip": a.ip} for a in rows],
            "total": total, "page": page, "page_size": page_size}
