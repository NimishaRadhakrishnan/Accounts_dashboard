#!/usr/bin/env bash
# DEVELOPMENT ONLY: wipes the database. Default: users for the Tally dashboard demo.
#   ./reset_dev_db.sh              -> --tally-demo (then run the simulator + connector)
#   ./reset_dev_db.sh --sample     -> old manual-entry sample data
set -euo pipefail
cd "$(dirname "$0")"
if [ -x "../.venv/bin/python" ]; then
    PYTHON="../.venv/bin/python"
    ALEMBIC="../.venv/bin/alembic"
else
    PYTHON="${PYTHON:-python3}"
    ALEMBIC="${ALEMBIC:-alembic}"
fi
"$PYTHON" - <<'PY'
from sqlalchemy import text
from app.core.config import get_settings
from app.core.database import engine
assert not get_settings().is_production, "Refusing to reset a production database."
with engine.begin() as c:
    c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
PY
"$ALEMBIC" upgrade head
if [ $# -eq 0 ]; then "$PYTHON" seed.py --tally-demo; else "$PYTHON" seed.py "$@"; fi
