from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models import User


class Actor:
    """Who is doing something, passed into services for audit and permission checks."""

    def __init__(self, user: User, ip: str | None = None):
        self.user = user
        self.ip = ip

    @property
    def id(self) -> int:
        return self.user.id

    def can(self, perm: str) -> bool:
        return perm in self.user.permission_codes


def _token_from(request: Request) -> str | None:
    token = request.cookies.get("access_token")
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _token_from(request)
    data = decode_token(token, "access") if token else None
    if not data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in again.")
    user = db.get(User, int(data["sub"]))
    if not user or not user.is_active or user.token_version != data.get("tv"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in again.")
    return user


def get_actor(request: Request, user: User = Depends(get_current_user)) -> Actor:
    ip = request.headers.get("CF-Connecting-IP") or (request.client.host if request.client else None)
    return Actor(user, ip)


def require(*perms: str) -> Callable[..., Actor]:
    """Dependency: the user must have ALL listed permissions."""

    def checker(actor: Actor = Depends(get_actor)) -> Actor:
        if actor.user.must_change_password:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Please change your password first.")
        missing = [p for p in perms if not actor.can(p)]
        if missing:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this action.")
        return actor

    return checker
