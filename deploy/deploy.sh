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

echo "==> [2/8] Cloning / updating repository"
if [ -d "$SITE_DIR/.git" ]; then
    echo "    Repo exists — resetting to latest origin/main"
    # Hard reset (not pull --ff-only) so the in-place asset minification done in
    # step [4/8] is discarded cleanly every deploy. .env, venv/, *.db and build/
    # are gitignored, so they survive the reset untouched.
    git -C "$SITE_DIR" fetch --quiet origin
    git -C "$SITE_DIR" reset --hard --quiet origin/main
else
    echo "    Fresh clone"
    mkdir -p "$SITE_DIR"
    git clone "$REPO_URL" "$SITE_DIR"
fi

echo "==> [3/8] Setting up Python virtual environment"
if [ ! -d "$SITE_DIR/venv" ]; then
    python3 -m venv "$SITE_DIR/venv"
fi
"$SITE_DIR/venv/bin/pip" install --quiet --upgrade pip
"$SITE_DIR/venv/bin/pip" install --quiet -r "$SITE_DIR/requirements.txt"

echo "==> [4/8] Minifying CSS/JS assets (serve minified, keep sources readable)"
# Pure-Python minifiers (rjsmin/rcssmin); never breaks the build if absent.
"$SITE_DIR/venv/bin/pip" install --quiet -r "$SITE_DIR/requirements-build.txt"
( cd "$SITE_DIR" && "$SITE_DIR/venv/bin/python" build_assets.py )
# Overwrite the served assets with their minified equivalents (same filenames,
# so no HTML <link>/<script> reference needs to change). The hard reset in
# step [2/8] restores the readable sources before the next deploy.
cp -f "$SITE_DIR"/build/assets/css/*.css "$SITE_DIR"/assets/css/
cp -f "$SITE_DIR"/build/assets/js/*.js   "$SITE_DIR"/assets/js/

echo "==> [5/8] Checking .env file"
if [ ! -f "$SITE_DIR/.env" ]; then
    cp "$SITE_DIR/.env.example" "$SITE_DIR/.env"
    echo ""
    echo "  !! ACTION REQUIRED: Edit /var/www/greencurve/.env and add your ANTHROPIC_API_KEY"
    echo "  !! Run:  nano /var/www/greencurve/.env"
    echo ""
fi

echo "==> [6/8] Configuring Nginx"
cp "$SITE_DIR/deploy/nginx.conf" /etc/nginx/sites-available/greencurve
ln -sf /etc/nginx/sites-available/greencurve /etc/nginx/sites-enabled/greencurve
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> [7/8] Installing and starting API service"
chown -R www-data:www-data "$SITE_DIR"
cp "$SITE_DIR/deploy/greencurve-api.service" /etc/systemd/system/greencurve-api.service
systemctl daemon-reload
systemctl enable greencurve-api
systemctl restart greencurve-api

echo "==> [8/8] Opening firewall ports (Oracle Cloud)"
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
