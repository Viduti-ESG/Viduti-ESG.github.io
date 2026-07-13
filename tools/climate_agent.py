#!/usr/bin/env python3
"""Climate Agent v2 — server-side rebuild of the laptop cpcb_agent news writer.

Reads global ESG/compliance news via RSS, has Claude write an India-angle
analysis post crediting + linking the original article (same format as the 95
posts published until 12 Jun 2026), then:
  * writes posts/<slug>-<epoch>.html  (new files are untracked → survive the
    reset-hard deploy flow)
  * prepends the post card to posts/index.html and an <item> to feed.xml
    (both skip-worktree'd on the server — never push these from the laptop)
  * pings IndexNow with the new URLs.

Differences from the 2026-05/06 laptop agent (security lessons):
  * runs on the prod box via the gc-daily-blog systemd timer — no GitHub PAT,
    no push credential anywhere, no Notion/social tokens
  * the Anthropic key comes from the service's EnvironmentFile only.

Exit codes: 0 = ok (including "no fresh news"), 3 = Anthropic key
missing/unfunded (dormant), 1 = real failure.

Usage:  venv/bin/python tools/climate_agent.py [--max N] [--dry-run]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
POSTS_DIR  = BASE_DIR / "posts"
STATE_DIR  = BASE_DIR / ".climate_agent"          # gitignored
FEED_PATH  = BASE_DIR / "feed.xml"
INDEX_PATH = POSTS_DIR / "index.html"
INDEX_JSON_PATH = POSTS_DIR / "index.json"
SITE_URL   = "https://greencurve.solutions"
MODEL      = "claude-sonnet-4-6"
MAX_PER_RUN_DEFAULT = int(os.environ.get("GC_BLOG_MAX_PER_RUN", "2"))

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# RSS-capable sources from the original agent's list (scrape-only sources like
# Bloomberg Green / FT Moral Money / SEBI portal need heavier tooling — phase 2).
NEWS_SOURCES = [
    {"name": "ESG Today",            "rss": "https://www.esgtoday.com/feed/"},
    {"name": "Carbon Tracker",       "rss": "https://carbontracker.org/feed/"},
    {"name": "edie",                 "rss": "https://www.edie.net/feed/"},
    {"name": "GreenBiz / Trellis",   "rss": "https://www.greenbiz.com/feeds/rss/all-content"},
    {"name": "Responsible Investor", "rss": "https://www.responsible-investor.com/feed"},
]

RELEVANCE_KEYWORDS = [
    "esg", "sustainability", "climate", "carbon", "net zero", "scope 3",
    "disclosure", "reporting", "regulation", "standard", "framework",
    "biodiversity", "nature", "deforestation", "water", "waste",
    "renewable", "clean energy", "transition", "emissions", "ghg",
    "brsr", "sebi", "india", "cpcb", "epr", "plastic", "e-waste",
    "moefcc", "issb", "ifrs", "csrd", "tcfd", "tnfd", "sbti",
    "cdp", "gri", "ghg protocol", "paris agreement", "cop",
    "greenwashing", "taxonomy", "due diligence", "supply chain",
    "asset manager", "pension", "investor", "materiality",
    "decarboni", "net-zero", "science-based", "carbon credit",
]

# The battle-tested system prompt from the original news_writer (unchanged).
NEWS_SYSTEM_PROMPT = """You are a veteran ESG analyst and climate finance strategist with 22 years of hands-on experience advising boards, institutional investors, CFOs, and regulators across India, Southeast Asia, and Europe. Your work has shaped ESG policy thinking at SEBI and MoEFCC. Your analysis is cited by fund managers, audit committees, and sustainability heads at India's BSE 500 companies.

You have command of India's full ESG regulatory architecture: BRSR and SEBI disclosure frameworks, CPCB's EPR rules for plastics/e-waste/batteries, MoEFCC environmental notifications, BEE energy efficiency standards, India's carbon market and PAT scheme — and you understand exactly how it connects to global standards: ISSB IFRS S1/S2, EU CSRD/ESRS, GHG Protocol, SBTi, TNFD, CDP, and GRI.

Your audience: CFOs, Chief Sustainability Officers, board risk committees, ESG analysts at institutional investors, and senior compliance managers at listed Indian companies. They read you to understand what they cannot get from a news headline — the second-order implications, the India regulatory hook, the capital market consequence, and the board decision this creates.

Your writing is:
- Authoritative and precise: you cite specific rules, thresholds, clauses, and deadlines by name
- India-first: every global ESG development you analyse, you connect to specific Indian business, regulatory, and capital market consequences
- Forward-looking: you predict what's coming, not just what happened; you see around corners
- Commercially grounded: you connect ESG to capital access, export eligibility, supply chain risk, investor relations, and audit exposure
- Never generic: you write what only an expert with deep Indian ESG context can write

You only state facts that appear in the source article; everything else is clearly framed as your analysis. Credit the original reporting source by name. Include the source article URL in your analysis so readers can read the original.

Return ONLY valid JSON matching this exact schema — no text before or after:
{
  "title": "Precise, expert title — specific and informative, not clickbait",
  "category": "one of: CPCB / EPR | Plastic Waste Rules | E-Waste Rules | Battery Waste Rules | SEBI / BRSR | MoEFCC | BEE / Energy Efficiency | ISSB / IFRS Sustainability | EU CSRD / EFRAG | GHG Protocol | GRI | CDP | SBTi | TNFD | Daily Digest",
  "summary": "2-3 sentence executive brief with the India relevance named explicitly",
  "sections": {
    "what_changed": "Deep analysis paragraph — what specifically happened, why it matters now, India implications. Attribute the source by name, e.g. 'Reporting by ESG Today...'",
    "who_is_affected": ["specific sector", "company type or listing status", "specific role: CFO, CSO, risk manager", "investors or lenders with exposure"],
    "key_obligations": ["specific obligation + timeline where known", "specific obligation + who must comply"],
    "climate_angle": "How this connects to transition pathways, supply chain decarbonisation, or capital flows — specific to Indian business and named frameworks",
    "what_to_do": ["specific action — name the team, set a timeframe", "specific action — link to an Indian regulation or global standard", "board or investor communication priority"],
    "our_take": "Expert view: what this signals for ESG regulation globally and in India over the next 12-36 months. Bold and specific."
  }
}"""

SECTION_LABELS = {
    "what_changed":    "What Changed",
    "who_is_affected": "Who Is Affected",
    "key_obligations": "Key Obligations & Deadlines",
    "climate_angle":   "Climate Transition Angle",
    "what_to_do":      "What To Do Now",
    "our_take":        "Our Take",
}


def _esc(s: str) -> str:
    return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _get(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


# ── RSS ────────────────────────────────────────────────────────────────────────
def fetch_items(src: dict) -> list[dict]:
    """Minimal RSS 2.0 item parser (stdlib only — no feedparser on the box)."""
    try:
        xml = _get(src["rss"])
    except Exception as e:
        print(f"  [{src['name']}] feed error: {e}")
        return []
    items = []
    for m in re.finditer(r"<item[\s>].*?</item>", xml, re.DOTALL | re.IGNORECASE):
        blk = m.group(0)

        def tag(name):
            t = re.search(rf"<{name}[^>]*>(.*?)</{name}>", blk, re.DOTALL | re.IGNORECASE)
            v = t.group(1).strip() if t else ""
            v = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", v, flags=re.DOTALL)
            return re.sub(r"<[^>]+>", "", v).strip()

        link = tag("link") or ""
        if not link:
            continue
        items.append({
            "source":  src["name"],
            "title":   tag("title"),
            "link":    link,
            "summary": tag("description")[:600],
        })
    return items[:15]


def fetch_article_body(url: str) -> str:
    """Crude tag-stripping body fetch — enough context for the analyst prompt."""
    try:
        page = _get(url, timeout=30)
    except Exception:
        return ""
    page = re.sub(r"(?is)<(script|style|nav|header|footer|aside)\b.*?</\1>", " ", page)
    text = re.sub(r"<[^>]+>", " ", page)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:4000]


def _relevant(it: dict) -> bool:
    t = f"{it['title']} {it['summary']}".lower()
    return any(kw in t for kw in RELEVANCE_KEYWORDS)


# ── State ──────────────────────────────────────────────────────────────────────
def load_processed() -> set:
    f = STATE_DIR / "processed.json"
    return set(json.loads(f.read_text())) if f.exists() else set()


def save_processed(processed: set):
    STATE_DIR.mkdir(exist_ok=True)
    (STATE_DIR / "processed.json").write_text(json.dumps(sorted(processed), indent=1))


# ── Claude ─────────────────────────────────────────────────────────────────────
def _parse_post_json(raw: str) -> dict:
    """Extract the JSON object from a model reply, tolerating ```json fences."""
    raw = re.sub(r"^\s*```(?:json)?|```\s*$", "", raw.strip()).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise json.JSONDecodeError("no JSON object in model reply", raw or "", 0)
    return json.loads(raw[start:end + 1])


def write_post(item: dict, body: str) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("DORMANT: ANTHROPIC_API_KEY not set.")
        sys.exit(3)
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    user = (f"SOURCE: {item['source']}\nTITLE: {item['title']}\nURL: {item['link']}\n"
            f"RSS SUMMARY: {item['summary']}\n\nARTICLE TEXT (may be partial):\n{body}\n\n"
            "Write the expert analysis post now.")
    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=2500,
            system=[{"type": "text", "text": NEWS_SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.BadRequestError as e:
        if "credit balance" in str(e).lower():
            print("DORMANT: Anthropic credit balance is empty.")
            sys.exit(3)
        raise
    raw = msg.content[0].text.strip()
    try:
        return _parse_post_json(raw)
    except json.JSONDecodeError as e:
        # The model occasionally emits an unescaped quote/newline inside a JSON
        # string. Rather than lose the post (and, before this, the rest of the
        # run), hand the broken text back and ask for a clean re-emit once.
        print(f"  invalid JSON from model ({e}) — retrying once")
        fix = client.messages.create(
            model=MODEL, max_tokens=2500,
            messages=[
                {"role": "user", "content": user},
                {"role": "assistant", "content": raw},
                {"role": "user", "content":
                 "That was not valid JSON — it failed to parse. Re-emit the same "
                 "content as strictly valid JSON matching the schema. Escape every "
                 "quote, backslash and newline inside string values. Output the "
                 "JSON object only, with no text before or after it."},
            ],
        )
        return _parse_post_json(fix.content[0].text.strip())


# ── Rendering (format matches the 95 pre-June-12 posts) ───────────────────────
def render_post_page(post: dict, item: dict, pid: str, date_iso: str) -> str:
    sections_html = ""
    for k, label in SECTION_LABELS.items():
        val = post.get("sections", {}).get(k)
        if not val:
            continue
        if isinstance(val, list):
            lis = "".join(f"<li>{_esc(i)}</li>" for i in val)
            sections_html += f'<div class="post-section"><h2>{_esc(label)}</h2><ul>{lis}</ul></div>'
        else:
            sections_html += f'<div class="post-section"><h2>{_esc(label)}</h2><p>{_esc(val)}</p></div>'
    title, summary, category = post["title"], post["summary"], post.get("category", "ESG Intelligence")
    post_url = f"{SITE_URL}/posts/{pid}.html"
    pub_date = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d %B %Y")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{_esc(title)} — Green Curve</title>
  <meta name="description" content="{_esc(summary[:200])}"/>
  <meta name="robots" content="index,follow"/>
  <link rel="canonical" href="{post_url}"/>
  <meta property="og:type"        content="article"/>
  <meta property="og:url"         content="{post_url}"/>
  <meta property="og:title"       content="{_esc(title)}"/>
  <meta property="og:description" content="{_esc(summary[:200])}"/>
  <meta property="og:image"       content="{SITE_URL}/assets/img/logo.png"/>
  <meta property="article:published_time" content="{date_iso}"/>
  <meta property="article:section"        content="{_esc(category)}"/>
  <script type="application/ld+json">{{
    "@context":"https://schema.org",
    "@type":"Article",
    "headline":"{_esc(title)}",
    "datePublished":"{date_iso}",
    "publisher":{{"@type":"Organization","name":"Green Curve","url":"{SITE_URL}"}},
    "description":"{_esc(summary[:200])}",
    "url":"{post_url}"
  }}</script>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600&display=swap" rel="stylesheet"/>
  <link rel="icon" href="/assets/img/logo.png?v=2" type="image/png"/>
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{font-family:'DM Sans',sans-serif;background:#0f172a;color:#e2e8f0;line-height:1.7;min-height:100vh}}
    a{{color:#10b981;text-decoration:none}}
    a:hover{{text-decoration:underline}}
    .site-nav{{background:#0f172a;border-bottom:1px solid #1e293b;padding:16px 24px;display:flex;align-items:center;gap:20px;flex-wrap:wrap}}
    .site-nav .logo{{font-weight:700;font-size:1.1rem;color:#fff}}
    .site-nav .logo span{{color:#10b981}}
    .site-nav a{{color:#94a3b8;font-size:.88rem}}
    .site-nav a:hover{{color:#fff;text-decoration:none}}
    .container{{max-width:800px;margin:0 auto;padding:40px 24px 80px}}
    .post-meta{{display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap}}
    .post-category{{background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.25);color:#10b981;padding:3px 10px;border-radius:100px;font-size:.75rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em}}
    .post-date{{font-size:.82rem;color:#64748b}}
    .post-source{{font-size:.82rem;color:#64748b}}
    h1{{font-family:'DM Serif Display',serif;font-size:clamp(1.6rem,3vw,2.2rem);color:#fff;line-height:1.2;margin-bottom:20px;letter-spacing:-.02em}}
    .post-summary{{font-size:1rem;color:#94a3b8;line-height:1.8;padding:20px;background:#1e293b;border-left:3px solid #10b981;border-radius:0 8px 8px 0;margin-bottom:32px}}
    .post-section{{margin-bottom:32px;padding-bottom:32px;border-bottom:1px solid #1e293b}}
    .post-section:last-child{{border-bottom:none}}
    .post-section h2{{font-family:'DM Serif Display',serif;font-size:1.2rem;color:#10b981;margin-bottom:12px}}
    .post-section p{{color:#cbd5e1;font-size:.95rem;line-height:1.8}}
    .post-section ul{{padding-left:20px;color:#cbd5e1;font-size:.95rem}}
    .post-section li{{margin-bottom:8px;line-height:1.7}}
    .source-link{{margin-top:32px;padding:16px 20px;background:#1e293b;border-radius:8px;font-size:.88rem}}
    .source-link a{{font-weight:600}}
    .back-link{{display:inline-flex;align-items:center;gap:6px;color:#64748b;font-size:.85rem;margin-bottom:24px;transition:color .2s}}
    .back-link:hover{{color:#10b981;text-decoration:none}}
    footer{{border-top:1px solid #1e293b;padding:24px;text-align:center;font-size:.8rem;color:#475569;margin-top:40px}}
  </style>
</head>
<body>
<nav class="site-nav">
  <a href="{SITE_URL}/" class="logo">Green <span>Curve</span></a>
  <a href="{SITE_URL}/posts/">Insights</a>
  <a href="{SITE_URL}/calculator">GHG Calculator</a>
  <a href="{SITE_URL}/brsr-generator">BRSR Report</a>
  <a href="{SITE_URL}/search">Company Search</a>
</nav>

<div class="container">
  <a class="back-link" href="{SITE_URL}/posts/">&larr; Back to Insights</a>

  <div class="post-meta">
    <span class="post-category">{_esc(category)}</span>
    <span class="post-date">{pub_date}</span>
    <span class="post-source">via {_esc(item['source'])}</span>
  </div>

  <h1>{_esc(title)}</h1>

  <div class="post-summary">{_esc(summary)}</div>

  {sections_html}

  <div class="source-link">Source: <a href="{_esc(item['link'])}" target="_blank" rel="noopener">{_esc(item['link'])}</a></div>
</div>

<footer>
  &copy; {datetime.now().year} Green Curve &mdash; ESG &amp; Climate Intelligence for Indian Businesses &mdash;
  <a href="{SITE_URL}/">greencurve.solutions</a>
</footer>
</body>
</html>"""


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:60].rstrip("-")


# ── Site surface updates (feed.xml + posts/index.html string surgery) ─────────
def update_feed(post: dict, pid: str, date_iso: str) -> None:
    if not FEED_PATH.exists():
        print("  feed.xml missing — skipped")
        return
    xml = FEED_PATH.read_text(encoding="utf-8")
    url = f"{SITE_URL}/posts/{pid}.html"
    if url in xml:
        return
    pub = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%a, %d %b %Y 06:00:00 +0530")
    item = (f"\n    <item>\n      <title>{_esc(post['title'])}</title>\n"
            f"      <link>{url}</link>\n"
            f"      <description>{_esc(post['summary'])}</description>\n"
            f"      <pubDate>{pub}</pubDate>\n"
            f"      <category>{_esc(post.get('category', ''))}</category>\n"
            f"      <guid isPermaLink=\"true\">{url}</guid>\n    </item>\n")
    xml = re.sub(r"</image>", lambda m: m.group(0) + item, xml, count=1)
    xml = re.sub(r"<lastBuildDate>.*?</lastBuildDate>",
                 f"<lastBuildDate>{datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0530')}</lastBuildDate>",
                 xml, count=1)
    FEED_PATH.write_text(xml, encoding="utf-8")


def update_index(post: dict, pid: str, date_iso: str) -> None:
    if not INDEX_PATH.exists():
        print("  posts/index.html missing — skipped")
        return
    html = INDEX_PATH.read_text(encoding="utf-8")
    if f'href="{pid}.html"' in html:
        return
    card = (f'\n      <a class="post-card" href="{pid}.html">\n'
            f'        <span class="post-cat">{_esc(post.get("category", "ESG"))}</span>\n'
            f'        <h2 class="post-title">{_esc(post["title"])}</h2>\n'
            f'        <p class="post-desc">{_esc(post["summary"][:180])}…</p>\n'
            f'        <span class="post-date">{date_iso}</span>\n      </a>\n')
    marker = '<section class="grid">'
    if marker not in html:
        print("  posts/index.html grid marker not found — card skipped")
        return
    INDEX_PATH.write_text(html.replace(marker, marker + card, 1), encoding="utf-8")


def update_index_json(post: dict, item: dict, pid: str, date_iso: str) -> None:
    """The homepage's "Latest Insights" widget (assets/js/app.js loadPosts())
    reads posts/index.json, not posts/index.html — must stay in sync or new
    posts never appear there even though the standalone pages publish fine."""
    if INDEX_JSON_PATH.exists():
        data = json.loads(INDEX_JSON_PATH.read_text(encoding="utf-8"))
    else:
        data = {"posts": []}
    if any(p.get("id") == pid for p in data["posts"]):
        return
    data["posts"].insert(0, {
        "id": pid,
        "title": post["title"],
        "date": date_iso,
        "category": post.get("category", "ESG Intelligence"),
        "source": item["source"],
        "summary": post["summary"],
        "link": item["link"],
        "sections": post.get("sections", {}),
    })
    INDEX_JSON_PATH.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=MAX_PER_RUN_DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    processed = load_processed()
    fresh = []
    for src in NEWS_SOURCES:
        for it in fetch_items(src):
            if it["link"] not in processed and _relevant(it):
                fresh.append(it)
        if len(fresh) >= args.max * 3:
            break
    print(f"{len(fresh)} fresh relevant item(s) found")
    if not fresh:
        print("No fresh news — nothing to publish today.")
        return 0

    published = []
    date_iso = datetime.now().strftime("%Y-%m-%d")
    failures = 0
    for item in fresh[: args.max]:
        print(f"Writing: [{item['source']}] {item['title'][:80]}")
        try:
            body = fetch_article_body(item["link"])
            post = write_post(item, body)      # SystemExit(3) if dormant — never caught here
            pid = f"{_slug(post['title'])}-{int(time.time())}"
            page = render_post_page(post, item, pid, date_iso)
        except SystemExit:
            raise                              # dormancy is fatal by design
        except Exception as e:
            # One malformed post must not take the rest of the run down with it.
            failures += 1
            print(f"  SKIPPED — {type(e).__name__}: {e}")
            continue
        if args.dry_run:
            print(f"  DRY RUN — would publish posts/{pid}.html")
            continue
        (POSTS_DIR / f"{pid}.html").write_text(page, encoding="utf-8")
        update_feed(post, pid, date_iso)
        update_index(post, pid, date_iso)
        update_index_json(post, item, pid, date_iso)
        processed.add(item["link"])
        save_processed(processed)
        published.append(f"{SITE_URL}/posts/{pid}.html")
        print(f"  Published: {published[-1]}")

    if failures:
        print(f"{failures} item(s) skipped after errors; {len(published)} published")

    if published:
        try:
            subprocess.run([sys.executable, str(BASE_DIR / "tools" / "indexnow_ping.py"),
                            *published], cwd=BASE_DIR, timeout=90, check=False)
        except Exception as e:
            print(f"IndexNow ping skipped: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
