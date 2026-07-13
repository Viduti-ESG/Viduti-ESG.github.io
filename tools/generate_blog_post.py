#!/usr/bin/env python3
"""Green Curve daily blog generator (Anthropic-billed).

Writes one SEO article per run into blog/ (untracked — server-generated files
survive the reset-hard deploy), regenerates blog/index.html, and pings IndexNow.
Designed to run as the gc-daily-blog systemd timer (User=www-data,
EnvironmentFile=/var/www/greencurve/.env) or via POST /api/admin/blog/generate.

Run from the site root:  venv/bin/python tools/generate_blog_post.py [--topic "..."]

Exit codes: 0 = published, 3 = Anthropic key missing/unfunded (dormant, not an
error in monitoring terms), 1 = real failure.
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BLOG_DIR = BASE_DIR / "blog"
SITE     = "https://greencurve.solutions"
GA_ID    = "G-VS37JR0KK7"
MODEL    = "claude-sonnet-4-6"

# Evergreen India-ESG topics, rotated in order; slugs already published are
# skipped, so the list is a queue, not a calendar.
TOPICS = [
    "BRSR for first-time filers: what SEBI actually expects in your first report",
    "Scope 1 vs Scope 2 vs Scope 3 emissions explained for Indian companies",
    "How to compute Scope 2 emissions from electricity bills using the CEA grid factor",
    "BRSR Core: the 9 attributes and reasonable assurance explained",
    "What is a materiality assessment and how mid-cap companies should run one",
    "E-waste rules and EPR obligations for Indian electronics companies",
    "How ESG scores affect the cost of capital for Indian listed companies",
    "Water risk disclosure in BRSR: what to measure and how",
    "POSH complaints and social disclosures: getting Principle 5 right",
    "The compliance calendar: key India ESG deadlines every quarter",
    "Carbon Credit Trading Scheme (CCTS): who is covered and what to do now",
    "Value chain (Scope 3) reporting: practical first steps for suppliers",
    "How to set a science-aligned emissions baseline with two quarters of data",
    "Green claims and greenwashing risk under Indian law",
    "Board oversight of ESG: what directors should ask management",
    "LTIFR and safety metrics in BRSR Principle 3: a practical guide",
    "Renewable energy purchase options for Indian SMEs: open access, rooftop, RECs",
    "ESG due diligence in M&A: red flags hidden in BRSR filings",
    "How lenders read your BRSR: ESG-linked credit in India",
    "Waste intensity and circularity metrics that matter in BRSR",
    "Diversity disclosures: women on boards and in the workforce",
    "The difference between BRSR, GRI and ISSB for Indian filers",
    "Energy intensity benchmarking: how you compare with sector peers",
    "Preparing for reasonable assurance: an internal audit checklist",
    "Supplier ESG assessments: building a vendor scorecard that works",
    "Climate risk (physical vs transition) for Indian manufacturers",
    "GHG inventory quality: the five errors auditors find most often",
    "ESG data collection: moving from spreadsheets to a repeatable system",
    "How small listed companies can do BRSR without hiring a big-4 firm",
    "Biodiversity and land-use disclosures: the next frontier in BRSR",
    "Internal carbon pricing: should your company adopt one?",
    "Employee wellbeing spend and its disclosure under Principle 3",
    "CSR vs ESG in India: obligations, overlaps and differences",
    "Green buildings and operational emissions: what counts where",
    "Grievance mechanisms under BRSR: what good looks like",
    "ESG ratings vs disclosures: why they diverge and what to trust",
]

PROMPT = """You are the in-house sustainability editor at Green Curve Solutions, an Indian
ESG intelligence platform (greencurve.solutions). Write a practical, authoritative blog
post for Indian compliance officers, CFOs and sustainability leads.

TOPIC: {topic}

Rules:
- 900–1200 words. Practical, specific to India (SEBI/BRSR/CPCB/CEA context where relevant).
- Plain professional English. No marketing fluff, no salesy language.
- NEVER use vendor jargon like "Control Tower", "ITAM", "HCM", "CSM" or other
  SAP/ServiceNow terms. Use plain words.
- Where a Green Curve tool is genuinely relevant, mention at most ONE of:
  the ESG Quotient screener ({site}/search), the GHG calculator ({site}/calculator),
  the BRSR generator ({site}/brsr-generator), or the compliance calendar
  ({site}/compliance-calendar) — as a single natural sentence, not a pitch.
- Do not fabricate statistics, fines, or case names. If citing a rule, name the
  actual regulation (e.g. SEBI LODR, E-Waste Management Rules 2022) without
  invented clause numbers.

Return ONLY valid JSON:
{{
  "title": "<compelling, specific title, max 70 chars>",
  "meta_description": "<max 155 chars>",
  "slug": "<kebab-case-slug-max-6-words>",
  "body_html": "<the article as clean HTML using only h2, h3, p, ul, ol, li, strong, em tags — no h1, no inline styles, no scripts>"
}}"""

PAGE_TMPL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>{title} — Green Curve Solutions</title>
<meta name="description" content="{meta}"/>
<link rel="canonical" href="{site}/blog/{stem}"/>
<meta property="og:title" content="{title}"/>
<meta property="og:description" content="{meta}"/>
<meta property="og:type" content="article"/>
<meta property="og:url" content="{site}/blog/{stem}"/>
<meta property="og:image" content="{site}/assets/img/logo.png"/>
<link rel="icon" href="/assets/img/logo.png?v=2" type="image/png"/>
<script async src="https://www.googletagmanager.com/gtag/js?id={ga}"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{ga}');</script>
<style>
:root{{--pine:#0B3E2C;--curve:#149256;--spring:#3CC479;--ink:#1e293b;--muted:#64748b}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Georgia,'Times New Roman',serif;color:var(--ink);background:#fdfdfb;line-height:1.75}}
.topbar{{background:var(--pine);padding:14px 20px}}
.topbar a{{color:#fff;text-decoration:none;font-family:Arial,Helvetica,sans-serif;font-weight:700}}
.topbar a span{{color:var(--spring)}}
article{{max-width:760px;margin:0 auto;padding:48px 20px 24px}}
.kicker{{font-family:Arial,Helvetica,sans-serif;font-size:.8rem;letter-spacing:.12em;text-transform:uppercase;color:var(--curve);font-weight:700}}
h1{{font-size:2.1rem;line-height:1.25;margin:10px 0 8px;color:var(--pine)}}
.date{{font-family:Arial,Helvetica,sans-serif;color:var(--muted);font-size:.85rem;margin-bottom:28px}}
h2{{color:var(--pine);margin:34px 0 12px;font-size:1.45rem}}
h3{{color:var(--pine);margin:26px 0 10px;font-size:1.15rem}}
p{{margin:0 0 16px}} ul,ol{{margin:0 0 16px 24px}} li{{margin-bottom:6px}}
a{{color:var(--curve)}}
.footer{{max-width:760px;margin:0 auto;padding:24px 20px 56px;border-top:1px solid #e2e8f0;
font-family:Arial,Helvetica,sans-serif;font-size:.82rem;color:var(--muted)}}
.footer a{{color:var(--curve)}}
</style>
</head>
<body>
<div class="topbar"><a href="/">Green <span>Curve</span> Solutions</a></div>
<article>
<div class="kicker">Green Curve Insights</div>
<h1>{title}</h1>
<div class="date">{pretty_date} · Green Curve Solutions</div>
{body}
</article>
<div class="footer">
<p>Published by <a href="/">Green Curve Solutions</a> — ESG intelligence for Indian
companies. Questions: <a href="mailto:neha@greencurve.solutions">neha@greencurve.solutions</a>.</p>
<p style="margin-top:8px">This article is for general information and is not legal,
financial or assurance advice.</p>
<p style="margin-top:8px"><a href="/blog/">← All articles</a></p>
</div>
</body>
</html>
"""


def existing_slugs() -> set:
    return {re.sub(r"^\d{4}-\d{2}-\d{2}-", "", p.stem) for p in BLOG_DIR.glob("*.html")
            if p.name != "index.html"}


def pick_topic(cli_topic: str | None) -> str:
    if cli_topic:
        return cli_topic
    done = existing_slugs()
    for t in TOPICS:
        rough = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
        # a topic counts as done if any published slug shares its first 3 words
        head = "-".join(rough.split("-")[:3])
        if not any(s.startswith(head) for s in done):
            return t
    # every topic used — recycle by weekday so the queue never starves
    return TOPICS[date.today().toordinal() % len(TOPICS)]


def generate(topic: str) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("DORMANT: ANTHROPIC_API_KEY not set — skipping blog generation.")
        sys.exit(3)
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            messages=[{"role": "user",
                       "content": PROMPT.format(topic=topic, site=SITE)}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "meta_description": {"type": "string"},
                            "slug": {"type": "string"},
                            "body_html": {"type": "string"},
                        },
                        "required": ["title", "meta_description", "slug", "body_html"],
                        "additionalProperties": False,
                    },
                }
            },
        )
    except anthropic.BadRequestError as e:
        if "credit balance" in str(e).lower():
            print("DORMANT: Anthropic credit balance is empty — top up to enable daily blogs.")
            sys.exit(3)
        raise
    post = json.loads(msg.content[0].text.strip())
    for field in ("title", "meta_description", "slug", "body_html"):
        if not post.get(field):
            raise ValueError(f"model response missing {field}")
    # never trust model HTML blindly: strip script/style tags defensively
    post["body_html"] = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", post["body_html"])
    post["slug"] = re.sub(r"[^a-z0-9-]", "", post["slug"].lower())[:60].strip("-") or "esg-insights"
    return post


def rebuild_index() -> None:
    """Regenerate blog/index.html from the published posts (newest first)."""
    items = []
    for p in sorted(BLOG_DIR.glob("*.html"), reverse=True):
        if p.name == "index.html":
            continue
        text = p.read_text(encoding="utf-8")
        title = re.search(r"<h1>(.*?)</h1>", text, re.DOTALL)
        meta  = re.search(r'name="description" content="(.*?)"', text)
        d     = re.match(r"(\d{4}-\d{2}-\d{2})-", p.name)
        items.append(
            f'<li><a href="/blog/{p.stem}">{title.group(1).strip() if title else p.stem}</a>'
            f'<div class="idx-meta">{d.group(1) if d else ""} — '
            f'{html.escape(meta.group(1)) if meta else ""}</div></li>'
        )
    body = ("<ul class='idx'>" + "\n".join(items) + "</ul>") if items else \
           "<p>Articles are on their way — check back tomorrow.</p>"
    page = PAGE_TMPL.format(
        title="Green Curve Insights — the India ESG &amp; BRSR blog",
        meta="Practical articles on BRSR, GHG accounting and ESG compliance for Indian companies. A new article every day.",
        stem="", site=SITE, ga=GA_ID, pretty_date=date.today().strftime("%d %b %Y"),
        body=body,
    ).replace("</style>",
              ".idx{list-style:none;margin:0}.idx li{margin:0 0 18px}"
              ".idx a{font-size:1.15rem;font-weight:700;text-decoration:none}"
              ".idx-meta{font-family:Arial,Helvetica,sans-serif;font-size:.82rem;color:#64748b}"
              "</style>")
    (BLOG_DIR / "index.html").write_text(page, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default=None, help="override the rotating topic queue")
    ap.add_argument("--dry-run", action="store_true", help="generate but don't write/ping")
    args = ap.parse_args()

    BLOG_DIR.mkdir(exist_ok=True)
    topic = pick_topic(args.topic)
    print(f"Topic: {topic}")
    post = generate(topic)

    stem = f"{date.today().isoformat()}-{post['slug']}"
    page = PAGE_TMPL.format(
        title=html.escape(post["title"]), meta=html.escape(post["meta_description"]),
        stem=stem, site=SITE, ga=GA_ID,
        pretty_date=date.today().strftime("%d %b %Y"), body=post["body_html"],
    )
    if args.dry_run:
        print(f"DRY RUN — would write blog/{stem}.html ({len(page)} bytes)")
        return 0

    out = BLOG_DIR / f"{stem}.html"
    out.write_text(page, encoding="utf-8")
    rebuild_index()
    print(f"Published: {SITE}/blog/{stem}")

    try:
        subprocess.run(
            [sys.executable, str(BASE_DIR / "tools" / "indexnow_ping.py"),
             f"{SITE}/blog/{stem}"],
            cwd=BASE_DIR, timeout=90, check=False,
        )
    except Exception as e:
        print(f"IndexNow ping skipped: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
