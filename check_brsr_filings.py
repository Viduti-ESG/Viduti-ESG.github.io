#!/usr/bin/env python3
"""
BRSR Filing Tracker for Green Curve
Checks BSE corporate announcements for recent BRSR submissions and writes
assets/data/filing_tracker.json which the dashboard reads.

Usage:
  python check_brsr_filings.py            # check last 30 days (default)
  python check_brsr_filings.py --days 7   # check last 7 days

Requires: pip install requests
Recommended: schedule weekly via Task Scheduler or cron.
"""

import json
import re
import sys
import time
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run:  pip install requests", file=sys.stderr)
    sys.exit(1)

from db import get_conn, init_db

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR    = Path(__file__).parent
DATA_DIR    = BASE_DIR / "assets" / "data"
TRACKER_OUT = DATA_DIR / "filing_tracker.json"

init_db()

# ── BSE API ───────────────────────────────────────────────────────────────────
# BSE corporate announcements endpoint (public, no auth required).
# Returns announcements in a date range; we filter by BRSR keywords.

BSE_URL = (
    "https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w"
    "?strCat=-1"
    "&strPrevDate={from_d}"
    "&strScrip="
    "&strSearch="
    "&strToDate={to_d}"
    "&strType=C"
    "&subcatid=0"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bseindia.com/",
    "Accept":   "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Headline keywords that identify a BRSR-type filing
BRSR_KEYWORDS = [
    "BUSINESS RESPONSIBILITY",
    "BRSR",
    "SUSTAINABILITY REPORT",
    "INTEGRATED ANNUAL REPORT",
]

# ── Company name normalisation ─────────────────────────────────────────────────

_STRIP_WORDS = re.compile(
    r"\b(LIMITED|LTD\.?|PRIVATE|PVT\.?|CORPORATION|CORP\.?|"
    r"INDUSTRIES|INDUSTRY|INDIA|HOLDINGS|HOLDING|VENTURES|VENTURE)\b",
    re.IGNORECASE,
)


def _norm(name: str) -> str:
    n = re.sub(r"\s+", " ", name.upper().strip())
    n = _STRIP_WORDS.sub("", n)
    n = re.sub(r"[^A-Z0-9 ]", "", n).strip()
    return n


def build_index(companies: list) -> dict:
    """Build normalised-name → company dict."""
    idx = {}
    for c in companies:
        key = _norm(c.get("company_name", ""))
        if key:
            idx[key] = c
    return idx


def match_company(bse_name: str, idx: dict):
    """
    Match a BSE company name to our database.
    Tries exact normalised match first, then substring match.
    Returns the matched company dict or None.
    """
    key = _norm(bse_name)
    if not key:
        return None
    if key in idx:
        return idx[key]
    # Substring: our key starts/contains BSE key (or vice versa) — min 8 chars
    for k, c in idx.items():
        if len(key) >= 8 and len(k) >= 8 and (key in k or k in key):
            return c
    return None


# ── BSE fetcher ────────────────────────────────────────────────────────────────

def fetch_bse(from_date: datetime, to_date: datetime, session: requests.Session,
              retries: int = 3, backoff: int = 5) -> list:
    """Fetch BSE announcements with up to `retries` attempts and linear backoff.
    Returns empty list only after all attempts fail, so the tracker is not
    falsely zeroed on a transient BSE outage."""
    url = BSE_URL.format(
        from_d=from_date.strftime("%Y%m%d"),
        to_d=to_date.strftime("%Y%m%d"),
    )
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=25)
            r.raise_for_status()
            payload = r.json()
            # BSE returns {"Table": [...]} or {"Table1": [...]}
            return payload.get("Table") or payload.get("Table1") or []
        except requests.Timeout:
            print(f"  [BSE] Timeout after 25 s (attempt {attempt}/{retries})", file=sys.stderr)
        except requests.HTTPError as e:
            print(f"  [BSE] HTTP error: {e} (attempt {attempt}/{retries})", file=sys.stderr)
        except Exception as e:
            print(f"  [BSE] Unexpected error: {e} (attempt {attempt}/{retries})", file=sys.stderr)
        if attempt < retries:
            time.sleep(backoff * attempt)
    print("  [BSE] All attempts exhausted — returning empty list", file=sys.stderr)
    return []


def is_brsr_filing(row: dict) -> bool:
    headline = (row.get("HEADLINE") or row.get("NEWSSUB") or "").upper()
    return any(kw in headline for kw in BRSR_KEYWORDS)


def parse_bse_date(row: dict):
    raw = row.get("NEWS_DT") or row.get("DT_TM") or ""
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:len(fmt)], fmt)
        except (ValueError, TypeError):
            continue
    return None


def build_filing_url(row: dict) -> str:
    attach = row.get("ATTACHMENTNAME") or row.get("attachement") or ""
    scrip  = str(row.get("SCRIP_CD") or row.get("scCode") or "")
    if attach:
        return f"https://www.bseindia.com/xml-data/corpfiling/AttachHis/{attach}"
    if scrip:
        return f"https://www.bseindia.com/corporates/ann.html?scrip={scrip}"
    return "https://www.bseindia.com/corporates/ann.html"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Green Curve BRSR Filing Tracker — checks BSE for new BRSR submissions"
    )
    parser.add_argument(
        "--days", type=int, default=30,
        help="Number of days to look back (default: 30)",
    )
    args = parser.parse_args()

    now       = datetime.now(timezone.utc)
    from_date = now - timedelta(days=args.days)

    print("=" * 60)
    print("Green Curve — BRSR Filing Tracker")
    print(f"  Period : {from_date.strftime('%Y-%m-%d')} → {now.strftime('%Y-%m-%d')}")
    print("=" * 60)

    # ── Load company database from SQLite ─────────────────────────────────────
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT company_name, cin, sector, esg_risk_score, risk_tier FROM companies"
        ).fetchall()
    companies = [dict(r) for r in rows]
    idx = build_index(companies)
    print(f"  DB: {len(companies)} companies indexed from greencurve.db")

    # ── Fetch from BSE ─────────────────────────────────────────────────────────
    session = requests.Session()
    session.headers.update(HEADERS)

    print("  Querying BSE corporate announcements…")
    rows = fetch_bse(from_date, now, session)
    print(f"  Got   : {len(rows)} total BSE announcements")

    # ── Filter and match ───────────────────────────────────────────────────────
    matched = []
    for row in rows:
        if not is_brsr_filing(row):
            continue

        bse_name = (
            row.get("COMPANY_NAME")
            or row.get("Scrip_Cd_Name")
            or row.get("companyname")
            or ""
        )
        company = match_company(bse_name, idx)
        if not company:
            continue

        dt          = parse_bse_date(row)
        filing_date = dt.strftime("%Y-%m-%d") if dt else "Unknown"
        days_ago    = (now.date() - dt.date()).days if dt else None
        scrip       = str(row.get("SCRIP_CD") or row.get("scCode") or "")
        headline    = (row.get("HEADLINE") or row.get("NEWSSUB") or "")[:150]

        matched.append({
            "company_name":   company["company_name"],
            "cin":            company.get("cin", ""),
            "sector":         company.get("sector", ""),
            "esg_risk_score": company.get("esg_risk_score"),
            "risk_tier":      company.get("risk_tier", ""),
            "filing_date":    filing_date,
            "days_ago":       days_ago,
            "source":         "BSE",
            "scrip_code":     scrip,
            "headline":       headline,
            "url":            build_filing_url(row),
        })

    # Deduplicate by company + date
    seen, unique = set(), []
    for m in matched:
        key = f"{m['company_name']}|{m['filing_date']}"
        if key not in seen:
            seen.add(key)
            unique.append(m)

    unique.sort(key=lambda x: x["filing_date"], reverse=True)

    print(f"  Matched: {len(unique)} BRSR filings linked to database companies")

    # ── Write output ───────────────────────────────────────────────────────────
    output = {
        "last_checked":      now.isoformat(),
        "check_period_days": args.days,
        "total_found":       len(unique),
        "recent_filings":    unique[:100],   # cap at 100 entries
    }

    TRACKER_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_OUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"  Output : {TRACKER_OUT}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
