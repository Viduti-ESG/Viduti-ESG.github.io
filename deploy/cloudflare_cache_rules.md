# Green Curve — Cloudflare Cache Rules

Configure these rules in the Cloudflare dashboard under:
**Domain → Rules → Cache Rules**

---

## Rule 1: Cache Static Assets (1 year)

**When**: URI path matches `*/assets/*`

**Cache settings**:
- Cache eligibility: **Eligible for cache**
- Edge TTL: **1 year** (31536000 seconds)
- Browser TTL: **1 day** (86400 seconds)
- Origin cache control: **Off** (Cloudflare controls TTL)

**Includes**: JS, CSS, images, fonts, data JSON files (esg_quotient.json, ghg_estimates.json, etc.)

> **Note**: When deploying JS/CSS updates, bump the `?v=YYYYMMDD` query string on `<script>` and `<link>` tags in esg-intelligence.html to bust the cache. Data JSON files update daily via cron — use `?v=` + timestamp to force refresh on the dashboard.

---

## Rule 2: Bypass Cache for API Endpoints

**When**: URI path matches `/api/*`

**Cache settings**:
- Cache eligibility: **Bypass cache**

This ensures all API calls reach the origin server (critical for auth, AI endpoints, and live ESG data).

---

## Rule 3: Cache HTML Pages (30 minutes)

**When**: URI path matches `/*.html` or the root `/`

**Cache settings**:
- Cache eligibility: **Eligible for cache**
- Edge TTL: **30 minutes** (1800 seconds)
- Browser TTL: **5 minutes** (300 seconds)

---

## Rule 4: Bypass Cache for /health

**When**: URI path equals `/health`

**Cache settings**:
- Cache eligibility: **Bypass cache**

Ensures Uptime Robot gets a live response.

---

## Setup Steps (Cloudflare Dashboard)

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com) → greencurve.solutions
2. Rules → Cache Rules → Create rule
3. Add the four rules above in order (they're evaluated top-to-bottom)
4. Enable "Always Online" to serve stale pages if origin is down

## Cloudflare Settings (recommended)

- **SSL/TLS**: Full (strict) — origin uses HTTPS
- **Always Use HTTPS**: On
- **HTTP/2**: On
- **Minify**: JS + CSS + HTML: On
- **Brotli**: On
- **Rocket Loader**: Off (breaks deferred JS loading)
