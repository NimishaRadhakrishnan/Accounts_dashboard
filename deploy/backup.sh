#!/usr/bin/env bash
# Nightly encrypted backup of the accounts database and attachments.
# Cron (as root):  15 1 * * *  /opt/vbt-accounts/deploy/backup.sh >> /var/log/vbt-accounts-backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a

: "${BACKUP_DIR:?}" "${BACKUP_PASSPHRASE:?}"
KEEP="${BACKUP_KEEP_DAYS:-30}"
STAMP="$(date +%Y%m%d-%H%M)"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

DB_FILE="$BACKUP_DIR/db-$STAMP.sql.gz.gpg"
UP_FILE="$BACKUP_DIR/uploads-$STAMP.tar.gz.gpg"

docker compose exec -T db pg_dump -U vbt_accounts -d vbt_accounts --no-owner \
  | gzip -9 \
  | gpg --batch --yes --pinentry-mode loopback --passphrase "$BACKUP_PASSPHRASE" --symmetric --cipher-algo AES256 -o "$DB_FILE"

docker compose exec -T api tar -C /data -czf - uploads \
  | gpg --batch --yes --pinentry-mode loopback --passphrase "$BACKUP_PASSPHRASE" --symmetric --cipher-algo AES256 -o "$UP_FILE"

# Sanity check: the dump must not be tiny
if [ "$(stat -c%s "$DB_FILE")" -lt 2000 ]; then
  echo "$(date) BACKUP LOOKS EMPTY: $DB_FILE" >&2
  exit 1
fi

find "$BACKUP_DIR" -name '*.gpg' -mtime +"$KEEP" -delete

if [ -n "${BACKUP_REMOTE:-}" ] && command -v rclone >/dev/null; then
  rclone copy "$DB_FILE" "$BACKUP_REMOTE/"
  rclone copy "$UP_FILE" "$BACKUP_REMOTE/"
fi
echo "$(date) backup ok: $DB_FILE"
