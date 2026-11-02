from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.encoders import ENCODERS_BY_TYPE
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import DomainError
from app.routers import admin, attachments, auth, money, purchases, reports, sales

# Money goes over the wire as exact strings ("1234.50"), never floats.
ENCODERS_BY_TYPE[Decimal] = str

settings = get_settings()
if settings.is_production and (settings.jwt_secret.startswith("change-me") or len(settings.jwt_secret) < 32):
    raise RuntimeError("Set a long random JWT_SECRET in .env before running in production.")
if settings.is_production and not settings.cookie_secure:
    raise RuntimeError("COOKIE_SECURE must be true in production (HTTPS).")

app = FastAPI(title=settings.app_name, version="1.0.0",
              docs_url=None if settings.is_production else "/api/docs",
              openapi_url=None if settings.is_production else "/api/openapi.json")


@app.middleware("http")
async def security_headers_and_csrf(request: Request, call_next):
    # CSRF: cookies are SameSite=Strict, and every state-changing call must also carry this header,
    # which a cross-site form cannot set.
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/") \
            and request.headers.get("X-Requested-With") != "vbt-accounts":
        return JSONResponse({"detail": "Missing request header."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(DomainError)
async def domain_error(_: Request, exc: DomainError):
    return JSONResponse({"detail": exc.message}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    msgs = []
    for e in exc.errors():
        loc = [str(x) for x in e.get("loc", []) if x not in ("body", "query")]
        field = " → ".join(loc)
        msg = str(e.get("msg", "")).replace("Value error, ", "")
        msgs.append(f"{field}: {msg}" if field else msg)
    return JSONResponse({"detail": "; ".join(msgs) or "Please check the form.", "errors": exc.errors()},
                        status_code=422)


for r in (auth, admin, sales, purchases, money, reports, attachments):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "database unavailable"}, status_code=503)
    return {"status": "ready"}
