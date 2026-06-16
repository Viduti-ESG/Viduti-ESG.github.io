#!/usr/bin/env bash
# Green Curve — DNS & Cloudflare verification script
# Run after migrating nameservers to Cloudflare or changing IP.
# Usage: bash deploy/check_dns.sh [expected_ip]
set -euo pipefail

DOMAIN="greencurve.solutions"
EXPECTED_IP="${1:-161.118.174.87}"
CF_NS_1="abel.ns.cloudflare.com"
CF_NS_2="kate.ns.cloudflare.com"   # update with your actual assigned NS

PASS="✓"
FAIL="✗"
WARN="⚠"
OK=0
ERRORS=0

_check() {
  local label="$1" result="$2" expected="$3"
  if [ "$result" = "$expected" ]; then
    echo "  $PASS $label: $result"
  else
    echo "  $FAIL $label: got '$result', expected '$expected'"
    ERRORS=$((ERRORS+1))
  fi
}

echo ""
echo "=== Green Curve DNS Health Check ==="
echo "Domain:      $DOMAIN"
echo "Expected IP: $EXPECTED_IP"
echo ""

# 1. Nameservers
echo "[ 1 ] Nameservers"
NS=$(dig +short NS "$DOMAIN" | sort | tr '\n' ' ' | xargs)
echo "  NS records: $NS"
if echo "$NS" | grep -q "cloudflare"; then
  echo "  $PASS Cloudflare nameservers detected"
else
  echo "  $WARN Cloudflare NS not found — migration may not be complete yet"
  echo "       Expected: $CF_NS_1 + $CF_NS_2"
  ERRORS=$((ERRORS+1))
fi

# 2. A record
echo ""
echo "[ 2 ] A Record (root domain)"
A=$(dig +short A "$DOMAIN" | head -1)
_check "A record" "$A" "$EXPECTED_IP"

# 3. www A record
echo ""
echo "[ 3 ] A Record (www)"
WWW=$(dig +short A "www.$DOMAIN" | head -1)
_check "www A record" "$WWW" "$EXPECTED_IP"

# 4. HTTP → HTTPS redirect
echo ""
echo "[ 4 ] HTTP → HTTPS redirect"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "http://$DOMAIN" || echo "ERR")
if [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
  echo "  $PASS HTTP redirects ($HTTP_CODE)"
else
  echo "  $FAIL HTTP redirect returned $HTTP_CODE (expected 301 or 302)"
  ERRORS=$((ERRORS+1))
fi

# 5. HTTPS response
echo ""
echo "[ 5 ] HTTPS reachability"
HTTPS_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "https://$DOMAIN" || echo "ERR")
if [ "$HTTPS_CODE" = "200" ]; then
  echo "  $PASS HTTPS 200 OK"
else
  echo "  $FAIL HTTPS returned $HTTPS_CODE"
  ERRORS=$((ERRORS+1))
fi

# 6. /health endpoint
echo ""
echo "[ 6 ] API /health endpoint"
HEALTH=$(curl -sf --max-time 10 "https://$DOMAIN/health" 2>/dev/null || echo "ERR")
if echo "$HEALTH" | grep -q '"status"'; then
  echo "  $PASS /health OK: $HEALTH"
else
  echo "  $FAIL /health did not return expected JSON: $HEALTH"
  ERRORS=$((ERRORS+1))
fi

# 7. TLS cert validity
echo ""
echo "[ 7 ] TLS certificate"
CERT_EXPIRY=$(echo | openssl s_client -servername "$DOMAIN" -connect "$DOMAIN:443" 2>/dev/null \
  | openssl x509 -noout -dates 2>/dev/null | grep "notAfter" | cut -d= -f2 || echo "ERR")
if [ "$CERT_EXPIRY" = "ERR" ]; then
  echo "  $FAIL Could not read TLS cert"
  ERRORS=$((ERRORS+1))
else
  # Check if cert expires in < 14 days
  EXPIRY_EPOCH=$(date -d "$CERT_EXPIRY" +%s 2>/dev/null || date -j -f "%b %d %T %Y %Z" "$CERT_EXPIRY" +%s 2>/dev/null || echo "0")
  NOW_EPOCH=$(date +%s)
  DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
  if [ "$DAYS_LEFT" -gt 14 ]; then
    echo "  $PASS TLS cert valid for $DAYS_LEFT more days (expires: $CERT_EXPIRY)"
  else
    echo "  $WARN TLS cert expires in $DAYS_LEFT days — renew soon: sudo certbot renew"
    ERRORS=$((ERRORS+1))
  fi
fi

# 8. Cloudflare cache header
echo ""
echo "[ 8 ] Cloudflare CDN cache headers"
CF_RAY=$(curl -sI --max-time 10 "https://$DOMAIN/assets/css/style.css" 2>/dev/null | grep -i "cf-ray" | head -1 || echo "")
if [ -n "$CF_RAY" ]; then
  echo "  $PASS Cloudflare CF-Ray header present: $CF_RAY"
else
  echo "  $WARN CF-Ray header not found — traffic may not be proxied through Cloudflare"
fi

# Summary
echo ""
echo "=== Summary ==="
if [ "$ERRORS" -eq 0 ]; then
  echo "  $PASS All checks passed. DNS looks healthy."
else
  echo "  $FAIL $ERRORS check(s) failed. See above for details."
  exit 1
fi
