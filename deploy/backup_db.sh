#!/usr/bin/env bash
# Green Curve — SQLite Hot Backup
# Runs daily at 03:00 UTC via /etc/cron.d/greencurve
# Keeps 7 daily backups; rotates older ones automatically.
set -euo pipefail

SITE_DIR="/var/www/greencurve"
DB="$SITE_DIR/greencurve.db"
BACKUP_DIR="$SITE_DIR/backups"
KEEP=7

mkdir -p "$BACKUP_DIR"

STAMP="$(date -u +%Y%m%d)"
DEST="$BACKUP_DIR/greencurve_${STAMP}.db"

# SQLite online backup via .backup command (safe while WAL mode is active)
sqlite3 "$DB" ".backup '$DEST'"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)  Backup written: $DEST ($(du -sh "$DEST" | cut -f1))"

# Rotate: keep only the $KEEP most recent .db files
cd "$BACKUP_DIR"
ls -1t greencurve_*.db 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm --
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)  Rotation done (keeping $KEEP copies)"
