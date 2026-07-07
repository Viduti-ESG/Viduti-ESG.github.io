#!/usr/bin/env bash
# Green Curve — Oracle Cloud ARM VM deployment script
# Run once as: sudo bash deploy.sh
# Re-run anytime to pull latest code and restart services.
set -euo pipefail

REPO_URL="https://github.com/Viduti-ESG/Viduti-ESG.github.io.git"
SITE_DIR="/var/www/greencurve"
DOMAIN="greencurve.solutions"

echo "==> [1/7] Installing system dependencies"
apt-get update -qq
apt-get install -y nginx python3 python3-pip python3-venv git curl

echo "==> [2/7] Cloning / updating repository"
if [ -d "$SITE_DIR/.git" ]; then
    echo "    Repo exists — pulling latest"
    git -C "$SITE_DIR" pull --ff-only
else
    echo "    Fresh clone"
    mkdir -p "$SITE_DIR"
    git clone "$REPO_URL" "$SITE_DIR"
fi

echo "==> [3/7] Setting up Python virtual environment"
if [ ! -d "$SITE_DIR/venv" ]; then
    python3 -m venv "$SITE_DIR/venv"
fi
"$SITE_DIR/venv/bin/pip" install --quiet --upgrade pip
"$SITE_DIR/venv/bin/pip" install --quiet -r "$SITE_DIR/requirements.txt"

echo "==> [3b/7] Minifying JS/CSS assets"
# Overwrites the checked-out sources with minified copies (same filenames, so
# no HTML changes needed). A later git pull/reset restores the readable
# sources; this step re-minifies on every deploy. Run this step by hand after
# any quick deploy that bypasses this script (git reset --hard flow):
#   cd /var/www/greencurve && venv/bin/python build_assets.py \
#     && cp -r build/assets/js/. assets/js/ && cp -r build/assets/css/. assets/css/
"$SITE_DIR/venv/bin/pip" install --quiet -r "$SITE_DIR/requirements-build.txt"
(cd "$SITE_DIR" && ./venv/bin/python build_assets.py)
cp -r "$SITE_DIR/build/assets/js/."  "$SITE_DIR/assets/js/"
cp -r "$SITE_DIR/build/assets/css/." "$SITE_DIR/assets/css/"

echo "==> [4/7] Checking .env file"
if [ ! -f "$SITE_DIR/.env" ]; then
    cp "$SITE_DIR/.env.example" "$SITE_DIR/.env"
    echo ""
    echo "  !! ACTION REQUIRED: Edit /var/www/greencurve/.env and add your ANTHROPIC_API_KEY"
    echo "  !! Run:  nano /var/www/greencurve/.env"
    echo ""
fi

echo "==> [5/7] Configuring Nginx"
cp "$SITE_DIR/deploy/nginx.conf" /etc/nginx/sites-available/greencurve
ln -sf /etc/nginx/sites-available/greencurve /etc/nginx/sites-enabled/greencurve
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> [6/7] Installing and starting API service"
chown -R www-data:www-data "$SITE_DIR"
cp "$SITE_DIR/deploy/greencurve-api.service" /etc/systemd/system/greencurve-api.service
systemctl daemon-reload
systemctl enable greencurve-api
systemctl restart greencurve-api

echo "==> [7/7] Opening firewall ports (Oracle Cloud)"
# Allow HTTP and HTTPS through iptables (Oracle Cloud blocks by default)
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
# Persist iptables rules across reboots
apt-get install -y iptables-persistent -qq
netfilter-persistent save

echo ""
echo "============================================"
echo " Green Curve deployment complete!"
echo "============================================"
echo " Site dir  : $SITE_DIR"
echo " API status: $(systemctl is-active greencurve-api)"
echo " Nginx     : $(systemctl is-active nginx)"
echo ""
echo " NEXT STEPS (manual):"
echo " 1. Edit .env:        nano $SITE_DIR/.env"
echo " 2. Restart API:      sudo systemctl restart greencurve-api"
echo " 3. Check API logs:   sudo journalctl -u greencurve-api -f"
echo " 4. Point DNS:        Add A record @ -> $(curl -s ifconfig.me) in Cloudflare"
echo " 5. Uptime monitoring: Sign up at uptimerobot.com (free)"
echo "    Create HTTP(S) monitor: https://greencurve.solutions/health"
echo "    Alert interval: 5 minutes | Alert email: kneha2381@gmail.com"
echo " 6. Run scheduled jobs: sudo bash deploy/setup_cron.sh"
echo "============================================"
