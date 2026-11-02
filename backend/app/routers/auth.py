from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import Actor, get_actor
from app.core.errors import DomainError
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models import User
from app.schemas import ChangePasswordIn, LoginIn
from app.services import audit, serialize
from app.services import users as svc

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookies(resp: Response, user: User) -> None:
    s = get_settings()
    common = {"httponly": True, "secure": s.cookie_secure, "samesite": "strict", "path": "/"}
    resp.set_cookie("access_token", create_access_token(user.id, user.token_version),
                    max_age=s.access_token_minutes * 60, **common)
    resp.set_cookie("refresh_token", create_refresh_token(user.id, user.token_version),
                    max_age=s.session_idle_minutes * 60, **{**common, "path": "/api/auth"})


def _clear(resp: Response) -> None:
    resp.delete_cookie("access_token", path="/")
    resp.delete_cookie("refresh_token", path="/api/auth")


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.headers.get("CF-Connecting-IP") or (request.client.host if request.client else None)
    try:
        user = svc.authenticate(db, body.username, body.password, ip)
    except DomainError:
        db.commit()  # keep failed-attempt counters and audit rows
        raise
    db.commit()
    _set_cookies(response, user)
    return serialize.user(user)


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get("refresh_token")
    data = decode_token(token, "refresh") if token else None
    user = db.get(User, int(data["sub"])) if data else None
    if not user or not user.is_active or user.token_version != data.get("tv"):
        _clear(response)
        raise HTTPException(401, "Session ended. Please sign in again.")
    _set_cookies(response, user)
    return serialize.user(user)


@router.post("/logout")
def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    data = decode_token(token, "access") if token else None
    if data:
        user = db.get(User, int(data["sub"]))
        if user:
            audit.record(db, Actor(user), "logout", "user", user.id, f"{user.username} signed out")
            db.commit()
    _clear(response)
    return {"ok": True}


@router.get("/me")
def me(actor: Actor = Depends(get_actor)):
    return serialize.user(actor.user)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, response: Response, actor: Actor = Depends(get_actor),
                    db: Session = Depends(get_db)):
    user = db.merge(actor.user)
    svc.change_password(db, Actor(user, actor.ip), body)
    db.commit()
    _set_cookies(response, user)
    return serialize.user(user)
