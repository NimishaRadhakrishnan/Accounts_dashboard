#!/usr/bin/env bash
# Restore a backup made by backup.sh.
#   deploy/restore.sh /var/backups/vbt-accounts/db-20270105-0115.sql.gz.gpg            -> into a TEST database (safe)
#   deploy/restore.sh <file> --replace-live                                             -> over the live database
# Do a test restore every month (roadmap Phase 7 / go-live checklist).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
FILE="${1:?backup file}"
TARGET="vbt_accounts_restore_test"
[ "${2:-}" = "--replace-live" ] && TARGET="vbt_accounts"

if [ "$TARGET" = "vbt_accounts" ]; then
  read -r -p "This REPLACES the live accounts database. Type RESTORE to continue: " ok
  [ "$ok" = "RESTORE" ] || exit 1
  docker compose stop api web
fi

docker compose exec -T db psql -U vbt_accounts -d postgres -c "DROP DATABASE IF EXISTS $TARGET WITH (FORCE);"
docker compose exec -T db psql -U vbt_accounts -d postgres -c "CREATE DATABASE $TARGET OWNER vbt_accounts;"
gpg --batch --pinentry-mode loopback --passphrase "$BACKUP_PASSPHRASE" -d "$FILE" | gunzip \
  | docker compose exec -T db psql -q -U vbt_accounts -d "$TARGET" -v ON_ERROR_STOP=1

echo "Restored into $TARGET. Row counts:"
docker compose exec -T db psql -U vbt_accounts -d "$TARGET" -c \
  "select 'invoices' t, count(*) from sales_invoices union all select 'bills', count(*) from purchase_bills union all select 'journal lines', count(*) from journal_lines;"

if [ "$TARGET" = "vbt_accounts" ]; then docker compose start api web; fi
