"""
Green Curve — Blog/Insights Index Generator
Reads every article in posts/ and writes posts/index.html — a single hub page
that internally links all articles. Without this, the article pages are orphans
(only cross-linked to each other), which Google crawls poorly. The hub also gets
listed in sitemap.xml by generate_company_pages.py.

Run after publishing new posts:
    GC_SITE_URL=https://greencurve.solutions python generate_posts_index.py
"""

import os, re, html, json
from datetime import date

BASE_URL = os.environ.get("GC_SITE_URL", "https://greencurve.solutions").rstrip("/")
POSTS_DIR = "posts"


def meta(content, prop):
    """Extract a <meta property/name=...> content value from raw HTML."""
    m = re.search(rf'(?:property|name)="{re.escape(prop)}"\s*content="([^"]*)"', content)
    if not m:
        m = re.search(rf'content="([^"]*)"\s*(?:property|name)="{re.escape(prop)}"', content)
    return html.unescape(m.group(1)).strip() if m else ""


posts = []
for fn in os.listdir(POSTS_DIR):
    if not fn.endswith(".html") or fn == "index.html":
        continue
    with open(os.path.join(POSTS_DIR, fn), encoding="utf-8") as f:
        raw = f.read()
    title = meta(raw, "og:title")
    if not title:
        tm = re.search(r"<title>(.*?)</title>", raw, re.DOTALL)
        title = html.unescape(tm.group(1).replace("— Green Curve", "").strip()) if tm else fn
    posts.append({
        "file": fn,
        "title": title,
        "desc": meta(raw, "og:description"),
        "section": meta(raw, "article:section") or "Insight",
        "date": meta(raw, "article:published_time") or "",
    })

# Newest first
posts.sort(key=lambda p: p["date"], reverse=True)
print(f"Indexing {len(posts)} articles…")

cards = "\n".join(f"""
      <a class="post-card" href="{html.escape(p['file'][:-5])}">
        <span class="post-cat">{html.escape(p['section'])}</span>
        <h2 class="post-title">{html.escape(p['title'])}</h2>
        <p class="post-desc">{html.escape(p['desc'][:180])}…</p>
        <span class="post-date">{html.escape(p['date'])}</span>
      </a>""" for p in posts)

# ItemList JSON-LD helps Google understand the article collection
items = ",\n".join(
    f'        {{"@type":"ListItem","position":{i+1},'
    f'"url":"{BASE_URL}/posts/{p["file"][:-5]}","name":{json.dumps(p["title"])}}}'
    for i, p in enumerate(posts)
)

page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>ESG &amp; Climate Insights — BRSR, EPR, GHG, ISSB News for India | Green Curve</title>
  <meta name="description" content="Daily ESG and climate-compliance insights for Indian business — SEBI BRSR, CPCB EPR, plastic &amp; e-waste rules, GHG Protocol, ISSB IFRS S1/S2, SBTi, TNFD and EU CSRD, explained for India."/>
  <meta name="keywords" content="ESG news India, BRSR updates, EPR compliance news, GHG Protocol, ISSB IFRS, SBTi India, TNFD, CSRD, climate regulation India"/>
  <meta name="robots" content="index, follow"/>
  <link rel="canonical" href="{BASE_URL}/posts/"/>
  <meta property="og:type" content="website"/>
  <meta property="og:url" content="{BASE_URL}/posts/"/>
  <meta property="og:site_name" content="Green Curve"/>
  <meta property="og:title" content="ESG &amp; Climate Insights for India — Green Curve"/>
  <meta property="og:description" content="Daily ESG and climate-compliance insights for Indian business — BRSR, EPR, GHG, ISSB, SBTi, TNFD and more."/>
  <meta property="og:image" content="{BASE_URL}/assets/img/logo.png"/>
  <meta name="twitter:card" content="summary_large_image"/>
  <meta name="twitter:title" content="ESG &amp; Climate Insights for India — Green Curve"/>
  <meta name="twitter:description" content="Daily ESG and climate-compliance insights for Indian business."/>
  <meta name="twitter:image" content="{BASE_URL}/assets/img/logo.png"/>
  <link rel="alternate" type="application/rss+xml" title="Green Curve Insights" href="{BASE_URL}/feed.xml"/>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600&display=swap" rel="stylesheet"/>
  <link rel="icon" type="image/svg+xml" href="../assets/img/favicon.svg"/>
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    "name": "Green Curve Insights",
    "description": "Daily ESG and climate-compliance insights for Indian business.",
    "url": "{BASE_URL}/posts/",
    "publisher": {{"@type": "Organization", "name": "Green Curve", "url": "{BASE_URL}/"}},
    "mainEntity": {{
      "@type": "ItemList",
      "numberOfItems": {len(posts)},
      "itemListElement": [
{items}
      ]
    }}
  }}
  </script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'DM Sans', -apple-system, sans-serif; background: #0a0f1a; color: #e2e8f0; line-height: 1.6; }}
    a {{ color: inherit; text-decoration: none; }}
    .container {{ max-width: 1180px; margin: 0 auto; padding: 0 24px; }}
    .site-header {{ border-bottom: 1px solid rgba(255,255,255,.07); position: sticky; top: 0; background: rgba(10,15,26,.85); backdrop-filter: blur(10px); z-index: 50; }}
    .nav {{ display: flex; align-items: center; justify-content: space-between; height: 64px; }}
    .nav__logo {{ display: flex; align-items: center; gap: 10px; font-family: 'DM Serif Display', serif; font-size: 1.25rem; }}
    .nav__logo-accent {{ color: #10b981; }}
    .nav__links {{ display: flex; gap: 22px; list-style: none; font-size: .92rem; }}
    .nav__links a:hover {{ color: #10b981; }}
    .breadcrumb {{ padding: 18px 24px; font-size: .82rem; color: #64748b; max-width: 1180px; margin: 0 auto; }}
    .breadcrumb a:hover {{ color: #10b981; }}
    .hero {{ padding: 28px 0 14px; }}
    .hero h1 {{ font-family: 'DM Serif Display', serif; font-size: 2.4rem; line-height: 1.15; margin-bottom: 10px; }}
    .hero p {{ color: #94a3b8; max-width: 720px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 18px; padding: 28px 0 80px; }}
    .post-card {{ display: flex; flex-direction: column; background: #111827; border: 1px solid rgba(255,255,255,.07); border-radius: 14px; padding: 22px; transition: border-color .2s, transform .2s; }}
    .post-card:hover {{ border-color: #10b981; transform: translateY(-3px); }}
    .post-cat {{ font-size: .72rem; font-weight: 600; color: #10b981; text-transform: uppercase; letter-spacing: .04em; }}
    .post-title {{ font-size: 1.12rem; font-weight: 600; color: #f1f5f9; margin: 8px 0; line-height: 1.3; }}
    .post-desc {{ font-size: .88rem; color: #94a3b8; flex: 1; }}
    .post-date {{ font-size: .76rem; color: #64748b; margin-top: 12px; }}
    .site-footer {{ border-top: 1px solid rgba(255,255,255,.07); padding: 28px 0; color: #64748b; font-size: .82rem; }}
    @media (max-width: 640px) {{ .nav__links {{ display: none; }} .hero h1 {{ font-size: 1.8rem; }} }}
  </style>
</head>
<body>

<header class="site-header">
  <nav class="nav container">
    <a href="../index.html" class="nav__logo">
      <img src="../assets/img/logo.png" alt="Green Curve" style="height:30px"/>
      <span>Green <span class="nav__logo-accent">Curve</span></span>
    </a>
    <ul class="nav__links">
      <li><a href="../index.html#insights">Insights</a></li>
      <li><a href="../calculator.html">GHG Calculator</a></li>
      <li><a href="../brsr-simple.html">BRSR Report</a></li>
      <li><a href="../esg-intelligence.html" style="color:#10b981">ESG Quotient</a></li>
      <li><a href="../pricing.html">Pricing</a></li>
    </ul>
  </nav>
</header>

<div class="breadcrumb">
  <a href="../index.html">Home</a> &rsaquo; <span>Insights</span>
</div>

<main class="container">
  <section class="hero">
    <h1>ESG &amp; Climate Insights for India</h1>
    <p>Daily analysis of the regulations shaping Indian business — SEBI BRSR, CPCB EPR, plastic &amp; e-waste rules, GHG Protocol, ISSB IFRS S1/S2, SBTi, TNFD and EU CSRD. {len(posts)} articles and counting.</p>
  </section>

  <section class="grid">
{cards}
  </section>
</main>

<footer class="site-footer">
  <div class="container">
    <p>&copy; {date.today().year} Green Curve. Climate transition intelligence for Indian businesses. Not investment advice.</p>
  </div>
</footer>

</body>
</html>
"""

with open(os.path.join(POSTS_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(page)
print(f"  Written {POSTS_DIR}/index.html ({len(posts)} articles linked)")
