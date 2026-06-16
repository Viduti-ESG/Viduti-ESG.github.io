"""
Green Curve — ESG Event Feed Scraper
Fetches regulatory circulars and enforcement notices from SEBI, BSE,
NGT, and MoEFCC RSS feeds, filters for ESG relevance, and writes
assets/data/esg_events.json consumed by the dashboard's Event Feed tab.

Run: python scrape_esg_events.py
Cron: Daily at 05:00 UTC (see deploy/setup_cron.sh)
"""

import json
import re
import ssl
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent
OUT_FILE   = ROOT / "assets" / "data" / "esg_events.json"
CACHE_FILE = ROOT / "assets" / "data" / ".esg_events_cache.json"

# ── RSS sources ───────────────────────────────────────────────────────────────
SOURCES = [
    {
        "name": "SEBI",
        "urls": [
            "https://www.sebi.gov.in/sebi_data/rss/pressreleases.xml",
            "https://www.sebi.gov.in/sebi_data/rss/circulars.xml",
        ],
        "default_category": "Regulatory",
    },
    {
        "name": "BSE",
        "urls": [
            "https://www.bseindia.com/markets/MarketInfo/RssFeed.aspx?id=4",  # corporate actions
            "https://www.bseindia.com/markets/MarketInfo/RssFeed.aspx?id=12", # circulars
        ],
        "default_category": "Regulatory",
    },
    {
        "name": "NGT",
        "urls": [
            "https://www.greentribunal.gov.in/Rss/RssFeed.aspx",
        ],
        "default_category": "Environmental",
    },
    {
        "name": "MoEFCC",
        "urls": [
            "https://moef.gov.in/rss/latest-news.xml",
            "https://moef.gov.in/rss/what-new.xml",
        ],
        "default_category": "Environmental",
    },
    {
        "name": "NSE",
        "urls": [
            "https://www.nseindia.com/rss/circular.xml",
        ],
        "default_category": "Regulatory",
    },
]

# ── ESG keyword classifier ────────────────────────────────────────────────────
_CRITICAL_KW = [
    "penalty", "enforcement action", "prosecution", "criminal",
    "show cause", "adjudication order", "insider trading",
    "market manipulation", "fraud",
]
_HIGH_KW = [
    "suspension", "debarment", "fine", "suo motu", "contempt",
    "directive", "mandatory", "compulsory", "violation", "non-compliance",
    "default", "injunction", "prohibit",
]
_MEDIUM_KW = [
    "circular", "guideline", "amendment", "notification", "regulation",
    "disclosure requirement", "reporting", "brsr", "sebi esg", "climate risk",
    "sustainability report", "esg rating", "carbon", "ghg", "scope 1", "scope 2",
    "renewable energy", "green", "epr", "extended producer", "plastic waste",
    "water withdrawal", "biodiversity",
]
_ESG_RELEVANT_KW = (
    _CRITICAL_KW + _HIGH_KW + _MEDIUM_KW + [
        "environment", "climate", "emission", "waste", "pollution",
        "governance", "board", "csr", "social", "labour", "safety",
        "hazardous", "toxic", "remediation", "tribunal", "order",
    ]
)

_SECTOR_MAP = {
    "cement":        "Cement",
    "steel":         "Steel",
    "aluminium":     "Aluminium",
    "mining":        "Mining",
    "coal":          "Mining",
    "pharmaceutical": "Pharmaceuticals",
    "pharma":        "Pharmaceuticals",
    "chemical":      "Chemicals",
    "pesticide":     "Chemicals",
    "fertilizer":    "Chemicals",
    "oil":           "Oil & Gas",
    "gas":           "Oil & Gas",
    "petroleum":     "Oil & Gas",
    "power":         "Power",
    "electricity":   "Power",
    "thermal":       "Power",
    "textile":       "Textile",
    "paper":         "Paper",
    "automobile":    "Automobile",
    "auto":          "Automobile",
    "vehicle":       "Automobile",
    "bank":          "Banking",
    "nbfc":          "Banking",
    "financial":     "BFSI",
    "insurance":     "BFSI",
    "it ":           "IT",
    "software":      "IT",
    "technology":    "IT",
    "food":          "FMCG",
    "fmcg":          "FMCG",
    "packaging":     "Packaging",
    "real estate":   "Real Estate",
    "construction":  "Construction",
}

_CAT_KW = {
    "Regulatory":    ["sebi", "circular", "regulation", "amendment", "compliance", "nse", "bse", "exchange"],
    "Environmental": ["environment", "pollution", "emission", "waste", "ngt", "tribunal", "green", "climate", "carbon"],
    "Governance":    ["governance", "board", "director", "audit", "disclosure", "insider", "fraud"],
    "Market":        ["market", "listing", "ipo", "delisting", "acquisition", "merger"],
    "ESG":           ["esg", "sustainability", "brsr", "csr", "responsible", "social"],
}


def _classify(text: str) -> dict:
    t = text.lower()

    # ESG relevance gate
    if not any(kw in t for kw in _ESG_RELEVANT_KW):
        return None

    # Severity
    if any(kw in t for kw in _CRITICAL_KW):
        severity = "Critical"
    elif any(kw in t for kw in _HIGH_KW):
        severity = "High"
    elif any(kw in t for kw in _MEDIUM_KW):
        severity = "Medium"
    else:
        severity = "Low"

    # Category (pick first match; ESG is catch-all)
    category = "ESG"
    for cat, kws in _CAT_KW.items():
        if any(kw in t for kw in kws):
            category = cat
            break

    # Affected sectors
    sectors = []
    for kw, sec in _SECTOR_MAP.items():
        if kw in t and sec not in sectors:
            sectors.append(sec)
    if not sectors:
        sectors = ["All sectors"]

    return {"severity": severity, "category": category, "affected_sectors": sectors}


def _parse_date(raw: str) -> str:
    if not raw:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fmts = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%d %b %Y",
        "%d/%m/%Y",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    return m.group(1) if m else datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "").strip()


def _fetch_rss(url: str, timeout: int = 12) -> list:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "GreenCurve-ESGBot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read()
    except Exception as e:
        print(f"  [skip] {url}: {e}")
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"  [xml-err] {url}: {e}")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = root.findall(".//item") or root.findall(".//atom:entry", ns)
    results = []
    for item in items:
        def t(tag):
            el = item.find(tag) or item.find("atom:" + tag, ns)
            return (el.text or "").strip() if el is not None else ""

        title   = _strip_html(t("title"))
        summary = _strip_html(t("description") or t("summary") or t("content"))
        link    = t("link") or t("guid")
        date    = _parse_date(t("pubDate") or t("published") or t("updated"))

        if title:
            results.append({"title": title, "summary": summary[:400], "link": link, "date": date})
    return results


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] scrape_esg_events.py starting")
    cache = _load_cache()
    seen_titles = set(cache.get("seen_titles", []))
    events = list(cache.get("events", []))   # carry forward previous events (up to 90 days)

    cutoff = datetime.now(timezone.utc)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    new_count = 0
    for src in SOURCES:
        for url in src["urls"]:
            print(f"  Fetching {src['name']}: {url}")
            items = _fetch_rss(url)
            for item in items:
                key = item["title"][:80]
                if key in seen_titles:
                    continue
                clf = _classify(item["title"] + " " + item["summary"])
                if clf is None:
                    continue
                seen_titles.add(key)
                events.append({
                    "title":            item["title"],
                    "summary":          item["summary"],
                    "source":           src["name"],
                    "date":             item["date"],
                    "category":         clf["category"],
                    "severity":         clf["severity"],
                    "affected_sectors": clf["affected_sectors"],
                    "companies":        [],
                    "reference":        "",
                    "url":              item["link"],
                })
                new_count += 1
            time.sleep(0.5)   # polite crawl

    # Prune events older than 90 days
    min_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from datetime import timedelta
    prune_before = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    events = [e for e in events if e.get("date", "2000-01-01") >= prune_before]

    # Sort newest-first
    events.sort(key=lambda e: e.get("date", ""), reverse=True)

    updated_at = datetime.now(timezone.utc).strftime("%d %b %Y")
    payload = {"updated_at": updated_at, "events": events}

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Wrote {len(events)} events ({new_count} new) → {OUT_FILE}")

    # Persist cache (cap seen_titles at 5000)
    seen_list = list(seen_titles)[-5000:]
    _save_cache({"seen_titles": seen_list, "events": events})
    print("Done.")


if __name__ == "__main__":
    main()
