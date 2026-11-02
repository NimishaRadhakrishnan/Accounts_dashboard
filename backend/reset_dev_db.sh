#!/usr/bin/env bash
# DEVELOPMENT ONLY: wipes the database and reloads sample data.
set -euo pipefail
cd "$(dirname "$0")"
python3 - <<'PY'
from sqlalchemy import text
from app.core.config import get_settings
from app.core.database import engine
assert not get_settings().is_production, "Refusing to reset a production database."
with engine.begin() as c:
    c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
PY
alembic upgrade head
python3 seed.py --sample "$@"
