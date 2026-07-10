#!/usr/bin/env python3
"""
One-off, idempotent site-wide nav propagation (2026-07-10).

Problem: only ~21 root pages carry the current header + mobile burger/overlay.
All 1,200+ company/*.html pages have a desktop-only header and load NO JS, so
on a phone they render with no menu at all; several root content pages are in
the same state. Result: mobile visitors can't reach Workspace / new features.

What this does, per target page (pages that have `<header class="site-header"`
but NO `nav__mobile` overlay):
  1. Replaces the whole <header class="site-header">…</header> with the
     canonical nav (root-absolute clean URLs, so it works from any directory).
  2. Inserts the canonical mobile overlay right after the header (replacing an
     existing overlay if one is somehow present).
  3. Appends a tiny self-contained burger-toggle script — ONLY if the page has
     no script that already wires #nav-burger (company pages load no JS).
  4. Normalizes style.css to ?v=6 (company pages pin ?v=3 — a stale Cloudflare
     cache key that may predate the mobile-nav CSS; assets are 30d immutable).

On EVERY page (root + company + posts), also:
  5. Cache-busts the rebranded logo + favicons (?v=2) — /assets/ is served
     `Cache-Control: immutable, max-age=30d`, so the logo v2 swap never reaches
     returning visitors without a new URL.

Bespoke-nav pages (pricing/login/booking/marketplace/admin/…) keep their own
navs — only the asset version bumps apply there.

  python tools/propagate_mobile_nav.py            # apply
  python tools/propagate_mobile_nav.py --dry-run  # preview only
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

CANONICAL_HEADER = '''<header class="site-header" id="site-header">
  <nav class="nav container">
    <a href="/" class="nav__logo">
      <img class="logo-mark" src="/assets/img/logo-nav.png?v=2" alt="Green Curve" />
      <span class="nav__logo-text">Green <span class="nav__logo-accent">Curve</span> <span class="nav__logo-sol">Solutions</span></span>
    </a>
    <ul class="nav__links" role="list">
      <li><a href="/">Insights</a></li>
      <li class="nav__has-dropdown">
        <a class="nav__dropdown-toggle">BRSR <span class="nav__caret"></span></a>
        <ul class="nav__dropdown">
          <li><a href="/brsr-generator">BRSR Report Builder</a></li>
          <li><a href="/brsr-simple">Quick BRSR</a></li>
          <li><a href="/assurance">Core Assurance Checker</a></li>
          <li><a href="/ccts">CCTS Compliance Tracker</a></li>
          <li><a href="/tcfd">TCFD Report</a></li>
        </ul>
      </li>
      <li class="nav__has-dropdown">
        <a class="nav__dropdown-toggle">Carbon &amp; GHG <span class="nav__caret"></span></a>
        <ul class="nav__dropdown">
          <li><a href="/calculator">GHG Calculator</a></li>
          <li><a href="/data-baseline">Data Baseline Wizard <span class="nav-new">NEW</span></a></li>
          <li><a href="/value-chain">Value Chain / Scope 3</a></li>
          <li><a href="/learn">Carbon Literacy</a></li>
          <li><a href="/compliance-calendar">Compliance Calendar <span class="nav-new">NEW</span></a></li>
        </ul>
      </li>
      <li class="nav__has-dropdown">
        <a class="nav__dropdown-toggle" href="/epr-market">EPR Market <span class="nav__caret"></span></a>
        <ul class="nav__dropdown">
          <li><a href="/epr-market">Overview</a></li>
          <li><a href="/epr-market#calculator">Obligation Calculator <span class="nav-new">NEW</span></a></li>
          <li><a href="/epr-market#prices">Live Price Tracker <span class="nav-new">NEW</span></a></li>
          <li><a href="/epr-market#dashboard">CPCB Dashboard <span class="nav-new">NEW</span></a></li>
          <li><a href="/epr-registration">Registration Guide</a></li>
        </ul>
      </li>
      <li class="nav__has-dropdown">
        <a class="nav__dropdown-toggle" href="/esg-intelligence">ESG Quotient <span class="nav__caret"></span></a>
        <ul class="nav__dropdown">
          <li><a href="/esg-intelligence">Overview &amp; Screener</a></li>
          <li><a href="/esg-health-check">ESG Health Check <span class="nav-new">NEW</span></a></li>
          <li><a href="/esg-intelligence#aiquery">AI Query <span class="nav-new">NEW</span></a></li>
          <li><a href="/esg-intelligence#controversy">Controversy Feed <span class="nav-new">NEW</span></a></li>
          <li><a href="/esg-intelligence#climaterisk">Climate Risk <span class="nav-new">NEW</span></a></li>
          <li><a href="/esg-intelligence#cap">Improvement Plan <span class="nav-new">NEW</span></a></li>
          <li><a href="/esg-intelligence#supplier">Supplier ESG <span class="nav-new">NEW</span></a></li>
          <li><a href="/esg-intelligence#badge">BRSR Recognition <span class="nav-new">NEW</span></a></li>
          <li><a href="/benchmark">Peer Benchmarking <span class="nav-new">NEW</span></a></li>
          <li><a href="/search">Semantic Search <span class="nav-new">NEW</span></a></li>
        </ul>
      </li>
      <li class="nav__has-dropdown">
        <a class="nav__dropdown-toggle" href="/data-room">Workspace <span class="nav__caret"></span></a>
        <ul class="nav__dropdown">
          <li><a href="/data-room">ESG Data Room <span class="nav-new">NEW</span></a></li>
          <li><a href="/brsr-workspace">BRSR Workspace <span class="nav-new">NEW</span></a></li>
          <li><a href="/team">Team &amp; Collaboration <span class="nav-new">NEW</span></a></li>
          <li><a href="/alerts">ESG Alerts <span class="nav-new">NEW</span></a></li>
        </ul>
      </li>
      <li><a href="/pricing">Pricing</a></li>
      <li><a href="/login">Sign in</a></li>
    </ul>
    <a href="/login#register" class="nav__cta">Start free &rarr;</a>
    <button class="nav__burger" id="nav-burger" aria-label="Toggle menu" aria-expanded="false">
      <span></span><span></span><span></span>
    </button>
  </nav>
</header>'''

CANONICAL_MOBILE = '''<!-- Mobile nav overlay -->
<div class="nav__mobile" id="nav-mobile" role="navigation" aria-label="Mobile navigation">
  <a href="/">Insights</a>
  <div class="nav__mobile-group">
    <div class="nav__mobile-label">BRSR</div>
    <a href="/brsr-generator">BRSR Report Builder</a>
    <a href="/brsr-simple">Quick BRSR</a>
    <a href="/assurance">Assurance Checker</a>
    <a href="/ccts">CCTS Tracker</a>
    <a href="/tcfd">TCFD Report</a>
  </div>
  <div class="nav__mobile-group">
    <div class="nav__mobile-label">Carbon &amp; GHG</div>
    <a href="/calculator">GHG Calculator</a>
    <a href="/data-baseline">Data Baseline Wizard</a>
    <a href="/value-chain">Value Chain / Scope 3</a>
    <a href="/learn">Carbon Literacy</a>
    <a href="/compliance-calendar">Compliance Calendar</a>
  </div>
  <div class="nav__mobile-group">
    <div class="nav__mobile-label">EPR Market</div>
    <a href="/epr-market">Overview</a>
    <a href="/epr-market#calculator">Obligation Calculator</a>
    <a href="/epr-market#prices">Live Price Tracker</a>
    <a href="/epr-market#dashboard">CPCB Dashboard</a>
    <a href="/epr-registration">Registration Guide</a>
  </div>
  <div class="nav__mobile-group">
    <div class="nav__mobile-label">ESG Quotient</div>
    <a href="/esg-intelligence">Overview &amp; Screener</a>
    <a href="/esg-health-check">ESG Health Check</a>
    <a href="/esg-intelligence#aiquery">AI Query</a>
    <a href="/esg-intelligence#controversy">Controversy Feed</a>
    <a href="/esg-intelligence#climaterisk">Climate Risk</a>
    <a href="/esg-intelligence#cap">Improvement Plan</a>
    <a href="/esg-intelligence#supplier">Supplier ESG</a>
    <a href="/esg-intelligence#badge">BRSR Recognition</a>
    <a href="/benchmark">Peer Benchmarking</a>
    <a href="/search">Semantic Search</a>
  </div>
  <div class="nav__mobile-group">
    <div class="nav__mobile-label">Workspace</div>
    <a href="/data-room">ESG Data Room</a>
    <a href="/brsr-workspace">BRSR Workspace</a>
    <a href="/team">Team &amp; Collaboration</a>
    <a href="/alerts">ESG Alerts</a>
  </div>
  <a href="/pricing">Pricing</a>
  <a href="/login">Sign in</a>
  <a href="/login#register" style="color:#34d399;font-weight:700">Start free &rarr;</a>
</div>'''

# Self-contained burger toggle for pages that load no JS (e.g. company pages).
# Mirrors the app.js wiring; data-gc-wired guards against double-binding if a
# page ever gains app.js later.
WIRING_SCRIPT = '''<script>(function(){var b=document.getElementById('nav-burger'),m=document.getElementById('nav-mobile');if(!b||!m||b.dataset.gcWired)return;b.dataset.gcWired='1';b.addEventListener('click',function(){var o=b.classList.toggle('open');m.classList.toggle('open',o);b.setAttribute('aria-expanded',o?'true':'false');document.body.style.overflow=o?'hidden':'';});m.querySelectorAll('a').forEach(function(a){a.addEventListener('click',function(){b.classList.remove('open');m.classList.remove('open');b.setAttribute('aria-expanded','false');document.body.style.overflow='';});});})();</script>'''

HEADER_START = re.compile(r'<header class="site-header"[^>]*>')

# Pages whose navs are deliberately bespoke (auth, booking product surface,
# marketplace, admin/internal, legal) — never replace their header.
SKIP_HEADER_SWAP = {
    "login.html", "pricing.html", "book.html", "bookings.html",
    "booking-admin.html", "booking-legal.html", "marketplace.html",
    "marketplace-admin.html", "seller-dashboard.html", "admin.html",
    "analytics.html", "supplier-form.html", "offline.html", "app.html",
    "terms-of-use.html", "privacy-policy.html",
}


def find_block(text: str, start_pat: str, open_tag: str, close_tag: str) -> tuple[int, int] | None:
    """Return (start, end) of the element starting at start_pat, matching nested tags."""
    m = re.search(start_pat, text)
    if not m:
        return None
    depth = 0
    pos = m.start()
    for tag in re.finditer(rf'<{open_tag}\b|</{open_tag}>', text[m.start():]):
        if tag.group(0).startswith(f'</'):
            depth -= 1
        else:
            depth += 1
        if depth == 0:
            return m.start(), m.start() + tag.end()
    return None


def bump_assets(text: str) -> tuple[str, bool]:
    """Cache-bust rebranded logo + favicons; normalize style.css to v6."""
    orig = text
    # logo-nav.png (nav) and logo.png / logo-transparent.png (footers, og excluded)
    text = re.sub(r'((?:src|href)="[./]*assets/img/(?:logo-nav|logo|logo-transparent)\.png)(\?v=\d+)?"',
                  r'\1?v=2"', text)
    text = re.sub(r'(href="[./]*assets/img/(?:favicon(?:-16|-32)?\.(?:png|ico|svg)|apple-touch-icon\.png))(\?v=\d+)?"',
                  r'\1?v=2"', text)
    text = re.sub(r'(href="[./]*assets/css/style\.css)(\?v=\d+)?"', r'\1?v=6"', text)
    return text, text != orig


def patch_page(path: Path, text: str) -> tuple[str, list[str]]:
    changes: list[str] = []
    is_bespoke = path.name in SKIP_HEADER_SWAP and path.parent == BASE

    if not is_bespoke and 'class="site-header"' in text and 'nav__mobile' not in text:
        hdr = find_block(text, r'<header class="site-header"[^>]*>', 'header', 'header')
        if hdr:
            text = text[:hdr[0]] + CANONICAL_HEADER + '\n\n' + CANONICAL_MOBILE + text[hdr[1]:]
            changes.append("header+overlay")
            if "getElementById('nav-burger')" not in text and 'app.js' not in text:
                if '</body>' in text:
                    text = text.replace('</body>', WIRING_SCRIPT + '\n</body>', 1)
                else:
                    text += '\n' + WIRING_SCRIPT + '\n'
                changes.append("wiring")

    text, bumped = bump_assets(text)
    if bumped:
        changes.append("assets-v")
    return text, changes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    targets = sorted(BASE.glob("*.html")) + sorted(BASE.glob("company/*.html")) + sorted(BASE.glob("posts/*.html"))
    total = 0
    summary: dict[str, int] = {}
    for html in targets:
        original = html.read_text(encoding="utf-8")
        patched, changes = patch_page(html, original)
        if changes:
            total += 1
            for c in changes:
                summary[c] = summary.get(c, 0) + 1
            if total <= 40 or "header+overlay" in changes and summary.get("header+overlay", 0) <= 45:
                print(f"{'[dry] ' if args.dry_run else ''}{str(html.relative_to(BASE)):48} -> {'+'.join(changes)}")
            if not args.dry_run:
                html.write_text(patched, encoding="utf-8")
    print(f"\n{total} page(s) {'would be ' if args.dry_run else ''}updated. Breakdown: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
