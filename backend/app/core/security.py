from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from jose import JWTError, jwt

from app.core.config import get_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < 10:
        problems.append("at least 10 characters")
    if not any(c.isdigit() for c in password):
        problems.append("a number")
    if not any(c.isalpha() for c in password):
        problems.append("a letter")
    return problems


def _token(user_id: int, token_version: int, kind: str, minutes: int) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "tv": token_version, "typ": kind,
               "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=minutes)).timestamp())}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def create_access_token(user_id: int, token_version: int) -> str:
    return _token(user_id, token_version, "access", get_settings().access_token_minutes)


def create_refresh_token(user_id: int, token_version: int) -> str:
    return _token(user_id, token_version, "refresh", get_settings().session_idle_minutes)


def decode_token(token: str, expected_kind: str) -> dict | None:
    s = get_settings()
    try:
        data = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except JWTError:
        return None
    if data.get("typ") != expected_kind:
        return None
    return data
