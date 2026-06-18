#!/usr/bin/env python3
"""Generate esg-risk-leaderboard.html from assets/data/esg_quotient.json.

A pre-rendered (crawlable, citable) data page ranking Indian listed companies
by Green Curve's ESG risk score. Designed as a link-magnet: data tables that
journalists/analysts cite and link to. Re-run whenever the dataset updates:

    python tools/build_leaderboard.py
"""
import json, os, re, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "assets", "data", "esg_quotient.json")
OUT = os.path.join(ROOT, "esg-risk-leaderboard.html")
GA_ID = "G-VS37JR0KK7"
YEAR = 2026


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s


def esc(s):
    return html.escape(str(s), quote=True)


def main():
    d = json.load(open(DATA, encoding="utf-8"))
    companies = [c for c in d["companies"] if isinstance(c.get("esg_risk_score"), (int, float))]
    summ = d.get("summary", {})
    data_as_of = d.get("data_as_of") or d.get("generated_at") or ""

    have_profile = set(
        f[:-5] for f in os.listdir(os.path.join(ROOT, "company")) if f.endswith(".html")
    )

    def row(rank, c):
        name = c["company_name"]
        sg = slug(name)
        label = esc(name.title() if name.isupper() else name)
        cell = (
            f'<a href="company/{sg}.html">{label}</a>' if sg in have_profile else label
        )
        score = f'{c["esg_risk_score"]:.1f}'
        tier = c.get("risk_tier", "")
        cls = {"High": "badge-high", "Medium": "badge-med", "Low": "badge-low"}.get(tier, "badge-med")
        sector = esc((c.get("sector") or "").strip()[:48])
        return (
            f"<tr><td class='rank'>{rank}</td><td>{cell}</td><td>{sector}</td>"
            f"<td class='num'>{score}</td><td><span class='badge {cls}'>{esc(tier)}</span></td></tr>"
        )

    high = sorted(
        [c for c in companies if c.get("risk_tier") == "High"],
        key=lambda c: (-c["esg_risk_score"], c["company_name"]),
    )
    low = sorted(companies, key=lambda c: (c["esg_risk_score"], c["company_name"]))[:50]

    high_rows = "\n".join(row(i, c) for i, c in enumerate(high, 1))
    low_rows = "\n".join(row(i, c) for i, c in enumerate(low, 1))

    total = summ.get("total_companies", len(companies))
    avg = summ.get("avg_esg_risk_score", "")
    n_high = summ.get("high_risk_companies", len(high))
    at_risk_sector = esc(summ.get("most_at_risk_sector", ""))
    top_risk = esc((summ.get("top_material_risk", "") or "").title())

    title = f"India ESG Risk Leaderboard {YEAR}: {total} Listed Companies Ranked | Green Curve"
    desc = (
        f"Green Curve's ESG risk ranking of {total} Indian listed companies. "
        f"See the highest- and lowest-risk companies, average ESG risk score, "
        f"and the most at-risk sector. Independent analysis across SEBI BRSR, "
        f"CPCB, MoEFCC and climate regulations."
    )
    url = "https://greencurve.solutions/esg-risk-leaderboard.html"

    jsonld_dataset = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": f"India ESG Risk Leaderboard {YEAR}",
        "description": desc, "url": url,
        "creator": {"@type": "Organization", "name": "Green Curve Research",
                    "url": "https://greencurve.solutions/"},
        "temporalCoverage": str(data_as_of), "inLanguage": "en-IN",
        "keywords": ["ESG India", "ESG risk score", "BRSR", "sustainability ranking",
                     "Indian listed companies ESG"],
    }, ensure_ascii=False)
    jsonld_crumb = json.dumps({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://greencurve.solutions/"},
            {"@type": "ListItem", "position": 2, "name": "ESG Risk Leaderboard", "item": url},
        ],
    }, ensure_ascii=False)

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(desc)}"/>
  <meta name="keywords" content="ESG ranking India, ESG risk score, best ESG companies India, ESG leaderboard, BRSR companies, sustainability ranking India, ESG rating Indian companies"/>
  <meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large"/>
  <link rel="canonical" href="{url}"/>
  <meta property="og:type" content="article"/>
  <meta property="og:url" content="{url}"/>
  <meta property="og:site_name" content="Green Curve"/>
  <meta property="og:title" content="{esc(title)}"/>
  <meta property="og:description" content="{esc(desc)}"/>
  <meta property="og:image" content="https://greencurve.solutions/assets/img/logo.png"/>
  <meta name="twitter:card" content="summary_large_image"/>
  <meta name="twitter:title" content="India ESG Risk Leaderboard {YEAR}"/>
  <meta name="twitter:description" content="{esc(desc)}"/>
  <meta name="twitter:image" content="https://greencurve.solutions/assets/img/logo.png"/>
  <script type="application/ld+json">{jsonld_dataset}</script>
  <script type="application/ld+json">{jsonld_crumb}</script>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600&display=swap" rel="stylesheet"/>
  <link rel="icon" type="image/svg+xml" href="assets/img/favicon.svg"/>
  <style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#0a0f1a;--surface:#111827;--border:rgba(255,255,255,.08);--text:#e2e8f0;--muted:#94a3b8;--dim:#64748b;--emerald:#10b981;--emerald2:#34d399}}
html{{scroll-behavior:smooth}}
body{{font-family:'DM Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);line-height:1.7}}
a{{color:inherit;text-decoration:none}}
.container{{max-width:1180px;margin:0 auto;padding:0 24px}}
.site-header{{position:sticky;top:0;z-index:50;background:rgba(10,15,26,.85);backdrop-filter:blur(10px);border-bottom:1px solid var(--border)}}
.nav{{display:flex;align-items:center;justify-content:space-between;height:64px}}
.nav__logo{{display:flex;align-items:center;gap:10px;font-family:'DM Serif Display',serif;font-size:1.25rem}}
.nav__logo-accent{{color:var(--emerald)}}
.nav__links{{display:flex;gap:22px;list-style:none;font-size:.92rem;align-items:center}}
.nav__links a:hover{{color:var(--emerald)}}
.nav__cta{{background:var(--emerald);color:#04110b!important;padding:8px 16px;border-radius:8px;font-weight:600;font-size:.88rem}}
.breadcrumb{{padding:18px 0;font-size:.82rem;color:var(--dim)}}
.breadcrumb a:hover{{color:var(--emerald)}}
.hero{{padding:26px 0 8px}}
.hero .kicker{{color:var(--emerald2);font-size:.8rem;font-weight:600;text-transform:uppercase;letter-spacing:.07em}}
.hero h1{{font-family:'DM Serif Display',serif;font-size:2.5rem;line-height:1.12;margin:10px 0 14px}}
.hero .intro{{color:var(--muted);font-size:1.08rem;max-width:820px}}
.wrap{{padding:30px 0 70px}}
.stat-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin:28px 0}}
.stat-card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px}}
.stat-card .v{{font-family:'DM Serif Display',serif;font-size:2rem;color:var(--emerald2);line-height:1}}
.stat-card .l{{color:var(--muted);font-size:.82rem;margin-top:8px}}
h2.sec{{font-family:'DM Serif Display',serif;font-size:1.7rem;margin:42px 0 6px}}
.sec-sub{{color:var(--muted);margin-bottom:14px;max-width:780px}}
table.lb{{width:100%;border-collapse:collapse;margin:14px 0;font-size:.9rem}}
table.lb th,table.lb td{{border-bottom:1px solid var(--border);padding:9px 12px;text-align:left}}
table.lb th{{background:var(--surface);color:#f1f5f9;position:sticky;top:64px;font-size:.8rem;text-transform:uppercase;letter-spacing:.04em}}
table.lb td a{{color:var(--emerald2)}}
table.lb td a:hover{{text-decoration:underline}}
.rank{{color:var(--dim);width:48px}}
.num{{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}}
.badge{{font-size:.74rem;padding:3px 9px;border-radius:20px;font-weight:600}}
.badge-high{{background:rgba(248,113,113,.14);color:#f87171}}
.badge-med{{background:rgba(251,191,36,.13);color:#fbbf24}}
.badge-low{{background:rgba(52,211,153,.14);color:#34d399}}
.callout{{background:rgba(16,185,129,.06);border:1px solid rgba(16,185,129,.22);border-radius:12px;padding:18px 22px;margin:26px 0;color:#cbd5e1;font-size:.92rem}}
.callout strong{{color:var(--emerald2)}}
.cta-band{{background:linear-gradient(135deg,rgba(16,185,129,.14),rgba(16,185,129,.04));border:1px solid rgba(16,185,129,.3);border-radius:16px;padding:30px;margin:40px 0;text-align:center}}
.cta-band h3{{font-family:'DM Serif Display',serif;font-size:1.5rem;margin-bottom:8px;color:#fff}}
.cta-band p{{color:var(--muted);margin-bottom:18px;max-width:560px;margin-left:auto;margin-right:auto}}
.cta-btn{{display:inline-block;background:var(--emerald);color:#04110b;padding:12px 26px;border-radius:10px;font-weight:700}}
.site-footer{{border-top:1px solid var(--border);padding:30px 0;color:var(--dim);font-size:.82rem}}
.site-footer a{{color:var(--muted)}}
@media(max-width:860px){{.hero h1{{font-size:1.9rem}}table.lb th{{top:0}}}}
  </style>
  <!-- Google Analytics (consent mode - analytics blocked until user accepts) -->
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('consent', 'default', {{ analytics_storage: 'denied' }});
  </script>
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
  <script>
    gtag('js', new Date());
    gtag('config', '{GA_ID}');
  </script>
</head>
<body>
<header class="site-header">
  <nav class="nav container">
    <a href="index.html" class="nav__logo">
      <img src="assets/img/logo.png" alt="Green Curve" style="height:30px"/>
      <span>Green <span class="nav__logo-accent">Curve</span></span>
    </a>
    <ul class="nav__links" role="list">
      <li><a href="epr-market.html">EPR Market</a></li>
      <li><a href="esg-intelligence.html">ESG Quotient</a></li>
      <li><a href="brsr-simple.html">BRSR Report</a></li>
      <li><a href="calculator.html">GHG Calculator</a></li>
      <li><a href="posts/">Insights</a></li>
      <li><a href="esg-intelligence.html" class="nav__cta">Screen companies &rarr;</a></li>
    </ul>
  </nav>
</header>
<div class="container">
  <div class="breadcrumb"><a href="index.html">Home</a> &rsaquo; <span>ESG Risk Leaderboard</span></div>
  <div class="hero">
    <div class="kicker">Data · {total} Indian Listed Companies</div>
    <h1>India ESG Risk Leaderboard {YEAR}</h1>
    <p class="intro">Green Curve scores the ESG and climate-transition risk of {total} Indian listed companies against SEBI BRSR, CPCB, MoEFCC and global climate frameworks. Lower scores mean lower ESG risk. Below are the highest- and lowest-risk companies, plus the headline numbers for the market.</p>
  </div>
  <div class="wrap">
    <div class="stat-grid">
      <div class="stat-card"><div class="v">{total}</div><div class="l">Listed companies analysed</div></div>
      <div class="stat-card"><div class="v">{avg}</div><div class="l">Average ESG risk score (0&ndash;10)</div></div>
      <div class="stat-card"><div class="v">{n_high}</div><div class="l">High-risk companies</div></div>
      <div class="stat-card"><div class="v">{top_risk}</div><div class="l">Top material risk factor</div></div>
    </div>

    <div class="callout">
      <strong>How to read this:</strong> The ESG risk score runs from 0 (lowest risk) to 10 (highest risk),
      combining regulatory exposure, sector materiality, governance and climate-transition factors.
      The most at-risk sector in this dataset is <strong>{at_risk_sector}</strong>.
      This is an independent screening model for research and education &mdash; not investment advice or a credit rating.
    </div>

    <h2 class="sec">Highest ESG-Risk Companies in India</h2>
    <p class="sec-sub">The {len(high)} companies in the &ldquo;High&rdquo; risk tier &mdash; the listed firms with the greatest regulatory, climate and governance exposure in our dataset. Ranked highest risk first.</p>
    <table class="lb">
      <thead><tr><th>#</th><th>Company</th><th>Sector</th><th class="num">Risk score</th><th>Tier</th></tr></thead>
      <tbody>
{high_rows}
      </tbody>
    </table>

    <h2 class="sec">Lowest ESG-Risk Companies (Leaders)</h2>
    <p class="sec-sub">The 50 listed companies with the lowest ESG risk in our dataset &mdash; the relative ESG leaders. Ranked lowest risk first.</p>
    <table class="lb">
      <thead><tr><th>#</th><th>Company</th><th>Sector</th><th class="num">Risk score</th><th>Tier</th></tr></thead>
      <tbody>
{low_rows}
      </tbody>
    </table>

    <div class="cta-band">
      <h3>Screen all {total} companies yourself</h3>
      <p>Filter by sector, risk tier and material factor, run an AI query on any company, and see the full risk breakdown on the ESG Quotient dashboard &mdash; free.</p>
      <a class="cta-btn" href="esg-intelligence.html">Open the ESG Quotient screener</a>
    </div>

    <p style="color:var(--muted);font-size:.85rem">Methodology and data sources are described on our <a href="methodology.html" style="color:var(--emerald2);text-decoration:underline">methodology page</a>. Data as of {esc(str(data_as_of))}. Companies are ranked by Green Curve's composite ESG risk score; ties are ordered alphabetically.</p>
  </div>
</div>

<footer class="site-footer">
  <div class="container">
    <p>&copy; <span id="year"></span> Green Curve Research. Climate transition intelligence for Indian businesses.
       &nbsp;&middot;&nbsp; <a href="privacy-policy.html">Privacy</a> &nbsp;&middot;&nbsp;
       <a href="terms-of-use.html">Terms</a></p>
    <p style="margin-top:8px;color:#475569">Educational reference, not legal or investment advice. Always verify against the latest SEBI / CPCB / MoEFCC notifications.</p>
  </div>
</footer>
<script>document.getElementById('year').textContent = new Date().getFullYear();</script>
<script src="assets/js/cookie-consent.js"></script>
</body>
</html>
"""
    open(OUT, "w", encoding="utf-8").write(page)
    print(f"Wrote {OUT}  ({len(page)} bytes)  high={len(high)} low={len(low)}")


if __name__ == "__main__":
    main()
