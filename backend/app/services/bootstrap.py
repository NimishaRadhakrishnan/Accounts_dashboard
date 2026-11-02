"""Idempotent setup of reference data: permissions, roles, system ledger accounts, settings."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import PERMISSIONS, ROLES
from app.core.security import hash_password
from app.models import Account, AppSetting, FinancialYear, Permission, Role, User
from app.services.common import DEFAULT_SETTINGS
from app.services.ledger import SYSTEM_ACCOUNTS


def fy_label(start_year: int) -> str:
    return f"{start_year % 100:02d}-{(start_year + 1) % 100:02d}"


def ensure_fy(db: Session, start_year: int, make_current: bool = False) -> FinancialYear:
    label = fy_label(start_year)
    fy = db.scalar(select(FinancialYear).where(FinancialYear.label == label))
    if not fy:
        fy = FinancialYear(label=label, start_date=date(start_year, 4, 1), end_date=date(start_year + 1, 3, 31))
        db.add(fy)
    if make_current:
        for other in db.scalars(select(FinancialYear)):
            other.is_current = False
        fy.is_current = True
    db.flush()
    return fy


def ensure_reference_data(db: Session) -> None:
    existing = {p.code: p for p in db.scalars(select(Permission))}
    for code, label, group in PERMISSIONS:
        if code not in existing:
            existing[code] = Permission(code=code, label=label, group=group)
            db.add(existing[code])
        else:
            existing[code].label, existing[code].group = label, group
    db.flush()
    for code, spec in ROLES.items():
        role = db.scalar(select(Role).where(Role.code == code))
        if not role:
            role = Role(code=code, name=spec["name"], description=spec["description"])
            role.permissions = [existing[p] for p in dict.fromkeys(spec["permissions"])]
            db.add(role)
        elif code == "super_admin":  # super admin always keeps everything
            role.permissions = list(existing.values())
    for code, name, typ, tally in SYSTEM_ACCOUNTS:
        if not db.scalar(select(Account).where(Account.code == code)):
            db.add(Account(code=code, name=name, type=typ, is_system=True, tally_ledger_name=tally))
    for key, (value, desc) in DEFAULT_SETTINGS.items():
        if not db.get(AppSetting, key):
            db.add(AppSetting(key=key, value=value, description=desc))
    db.flush()


def ensure_admin(db: Session, username: str, password: str, full_name: str = "System Administrator") -> User:
    user = db.scalar(select(User).where(User.username == username))
    if user:
        return user
    role = db.scalar(select(Role).where(Role.code == "super_admin"))
    user = User(full_name=full_name, username=username, password_hash=hash_password(password), role_id=role.id,
                must_change_password=True)
    db.add(user)
    db.flush()
    return user
