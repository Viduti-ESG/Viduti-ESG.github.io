#!/usr/bin/env bash
# Green Curve — Cron + Scheduled-Job Setup
# Run once after deploy.sh:  sudo bash deploy/setup_cron.sh
set -euo pipefail

SITE_DIR="/var/www/greencurve"
VENV_PY="$SITE_DIR/venv/bin/python"
LOG_DIR="/var/log/greencurve"
mkdir -p "$LOG_DIR"
chown www-data:www-data "$LOG_DIR"

echo "==> Setting up Green Curve scheduled jobs"

# ── 1. BRSR Filing Tracker — every Monday at 07:00 UTC ────────────────────────
# Checks BSE corporate announcements for new BRSR filings, updates filing_tracker.json
BRSR_CRON="0 7 * * 1 www-data cd $SITE_DIR && $VENV_PY check_brsr_filings.py --days 30 >> $LOG_DIR/brsr_filings.log 2>&1"

# ── 2. GHG Estimator — every Sunday at 06:00 UTC ──────────────────────────────
# Re-estimates GHG for non-disclosers, updates ghg_estimates.json
GHG_CRON="0 6 * * 0 www-data cd $SITE_DIR && $VENV_PY predict_ghg.py >> $LOG_DIR/ghg_estimates.log 2>&1"

# ── 3. Anomaly Detection — every Sunday at 06:30 UTC ──────────────────────────
# Recomputes anomaly flags after GHG estimates are refreshed
ANOMALY_CRON="30 6 * * 0 www-data cd $SITE_DIR && $VENV_PY detect_anomalies.py >> $LOG_DIR/anomalies.log 2>&1"

# ── 4. ESG Events Scraper — daily at 05:00 UTC ────────────────────────────────
# Fetches SEBI/NGT RSS feeds for new ESG-material events
EVENTS_CRON="0 5 * * * www-data cd $SITE_DIR && $VENV_PY scrape_esg_events.py >> $LOG_DIR/esg_events.log 2>&1"

# ── 5. SQLite Backup — daily at 03:00 UTC ─────────────────────────────────────
# Backs up the database; keeps last 7 daily copies
BACKUP_CRON="0 3 * * * www-data bash $SITE_DIR/deploy/backup_db.sh >> $LOG_DIR/backup.log 2>&1"

# Write to /etc/cron.d/greencurve (root-owned, system crontab)
CRON_FILE="/etc/cron.d/greencurve"
cat > "$CRON_FILE" <<EOF
# Green Curve scheduled jobs — managed by setup_cron.sh
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

$BRSR_CRON
$GHG_CRON
$ANOMALY_CRON
$EVENTS_CRON
$BACKUP_CRON
EOF

chmod 644 "$CRON_FILE"
echo "    Written to $CRON_FILE"

echo ""
echo "==> Scheduled jobs installed:"
echo "    Mon 07:00 UTC  — BRSR filing tracker    (check_brsr_filings.py)"
echo "    Sun 06:00 UTC  — GHG estimator          (predict_ghg.py)"
echo "    Sun 06:30 UTC  — Anomaly detection       (detect_anomalies.py)"
echo "    Daily 05:00 UTC — ESG events scraper    (scrape_esg_events.py)"
echo "    Daily 03:00 UTC — DB backup             (deploy/backup_db.sh)"
echo ""
echo "    Logs: $LOG_DIR/"
echo "Done."
