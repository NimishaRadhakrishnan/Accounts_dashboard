"""Authentication and user management. Passwords are hashed (Argon2) and can never be viewed — only reset."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import Actor
from app.core.errors import DomainError, NotFound
from app.core.security import hash_password, password_problems, verify_password
from app.models import Permission, Role, User
from app.schemas import ChangePasswordIn, UserIn, UserUpdateIn
from app.services import audit


def _now():
    return datetime.now(timezone.utc)


def authenticate(db: Session, username: str, password: str, ip: str | None) -> User:
    s = get_settings()
    user = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    generic = DomainError("Wrong username or password.", 401)
    if not user:
        verify_password(password, "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$invalid")  # equalise timing
        audit.record(db, None, "login_failed", "user", None, f"Unknown username '{username[:40]}' from {ip}")
        raise generic
    if not user.is_active:
        raise DomainError("This account is turned off. Contact the administrator.", 403)
    if user.locked_until and user.locked_until > _now():
        mins = int((user.locked_until - _now()).total_seconds() // 60) + 1
        raise DomainError(f"Too many wrong attempts. Try again in {mins} minute(s).", 429)
    actor = Actor(user, ip)
    if not verify_password(password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= s.max_failed_logins:
            user.locked_until = _now() + timedelta(minutes=s.lockout_minutes)
            user.failed_logins = 0
            audit.record(db, actor, "locked", "user", user.id, f"{user.username} locked after repeated failures")
        else:
            audit.record(db, actor, "login_failed", "user", user.id, f"Wrong password for {user.username}")
        raise generic
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = _now()
    audit.record(db, actor, "login", "user", user.id, f"{user.username} signed in")
    return user


def _check_password(pw: str) -> None:
    problems = password_problems(pw)
    if problems:
        raise DomainError("Password needs " + ", ".join(problems) + ".")


def change_password(db: Session, actor: Actor, data: ChangePasswordIn) -> None:
    u = actor.user
    if not verify_password(data.current_password, u.password_hash):
        raise DomainError("Current password is wrong.")
    if data.current_password == data.new_password:
        raise DomainError("New password must be different.")
    _check_password(data.new_password)
    u.password_hash = hash_password(data.new_password)
    u.must_change_password = False
    u.token_version += 1  # signs out other sessions
    audit.record(db, actor, "password_change", "user", u.id, f"{u.username} changed password")


def _role(db: Session, code: str) -> Role:
    r = db.scalar(select(Role).where(Role.code == code))
    if not r:
        raise NotFound("Role")
    return r


def create_user(db: Session, actor: Actor, data: UserIn) -> User:
    if db.scalar(select(User).where(func.lower(User.username) == data.username.lower())):
        raise DomainError("That username is taken.")
    _check_password(data.temp_password)
    u = User(full_name=data.full_name, username=data.username, email=data.email, role_id=_role(db, data.role_code).id,
             password_hash=hash_password(data.temp_password), must_change_password=True)
    db.add(u)
    db.flush()
    audit.record(db, actor, "create", "user", u.id, f"Created {u.username} as {data.role_code}")
    return u


def _super_admin_count(db: Session) -> int:
    return db.scalar(select(func.count(User.id)).join(Role).where(Role.code == "super_admin",
                                                                 User.is_active.is_(True))) or 0


def update_user(db: Session, actor: Actor, user_id: int, data: UserUpdateIn) -> User:
    u = db.get(User, user_id)
    if not u:
        raise NotFound("User")
    old = {"full_name": u.full_name, "email": u.email, "role": u.role.code, "is_active": u.is_active}
    losing_admin = u.role.code == "super_admin" and (
        (data.role_code and data.role_code != "super_admin") or data.is_active is False)
    if losing_admin and _super_admin_count(db) <= 1:
        raise DomainError("There must be at least one active Super Admin.")
    if u.id == actor.id and data.is_active is False:
        raise DomainError("You can't turn off your own account.")
    if data.full_name is not None:
        u.full_name = data.full_name
    if data.email is not None:
        u.email = data.email
    if data.role_code is not None and data.role_code != u.role.code:
        u.role_id = _role(db, data.role_code).id
        u.token_version += 1
    if data.is_active is not None and data.is_active != u.is_active:
        u.is_active = data.is_active
        u.token_version += 1
    db.flush()
    db.refresh(u)
    audit.record(db, actor, "update", "user", u.id, f"Updated {u.username}", old=old,
                 new={"full_name": u.full_name, "email": u.email, "role": u.role.code, "is_active": u.is_active})
    return u


def reset_password(db: Session, actor: Actor, user_id: int, temp_password: str) -> User:
    u = db.get(User, user_id)
    if not u:
        raise NotFound("User")
    _check_password(temp_password)
    u.password_hash = hash_password(temp_password)
    u.must_change_password = True
    u.failed_logins, u.locked_until = 0, None
    u.token_version += 1
    audit.record(db, actor, "password_reset", "user", u.id, f"Reset password for {u.username}")
    return u


def set_role_permissions(db: Session, actor: Actor, role_code: str, codes: list[str]) -> Role:
    role = _role(db, role_code)
    if role.code == "super_admin":
        raise DomainError("Super Admin always has every permission.")
    perms = list(db.scalars(select(Permission).where(Permission.code.in_(codes))))
    if len(perms) != len(set(codes)):
        raise DomainError("Unknown permission in the list.")
    old = sorted(p.code for p in role.permissions)
    role.permissions = perms  # takes effect on the next request; permissions are read live
    audit.record(db, actor, "update", "role", role.code, f"Permissions changed for {role.name}",
                 old={"permissions": old}, new={"permissions": sorted(codes)})
    return role
