"""
Green Curve — Static Company Page Generator
Reads assets/data/esg_intelligence.json and writes one HTML file per company
into the company/ directory, plus company/index.html and updates sitemap.xml.
"""

import json, os, re, html
from datetime import date

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_URL   = "https://viduti-esg.github.io"
DATA_FILE  = "assets/data/esg_intelligence.json"
OUT_DIR    = "company"
TODAY      = date.today().isoformat()

os.makedirs(OUT_DIR, exist_ok=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def slugify(name):
    s = name.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')

def esc(v):
    return html.escape(str(v)) if v is not None else ''

def score_color(v):
    if v is None: return '#94a3b8'
    return '#f87171' if v >= 7 else '#fbbf24' if v >= 4.5 else '#34d399'

def tier_color(tier):
    return {'High':'#f87171','Medium':'#fbbf24','Low':'#34d399'}.get(tier,'#94a3b8')

def fmt_num(v):
    if v is None: return '—'
    return f"{v:,.1f}"

def risk_bar(val, label):
    v = val or 0
    col = score_color(v)
    pct = v * 10
    return f"""
      <div class="rb-row">
        <span class="rb-label">{esc(label)}</span>
        <div class="rb-track"><div class="rb-fill" style="width:{pct}%;background:{col}"></div></div>
        <span class="rb-val" style="color:{col}">{v:.1f}</span>
      </div>"""

# ── Load data ─────────────────────────────────────────────────────────────────
with open(DATA_FILE, encoding='utf-8') as f:
    intel = json.load(f)

companies  = intel.get('companies', [])
data_as_of = intel.get('data_as_of', TODAY)
slug_map   = {}   # company_name → slug (for cross-links)

for c in companies:
    slug_map[c['company_name']] = slugify(c['company_name'])

print(f"Generating {len(companies)} company pages…")

# ── Per-company HTML ───────────────────────────────────────────────────────────
NAV = """
<header class="site-header" id="site-header">
  <nav class="nav container">
    <a href="../index.html" class="nav__logo">
      <img class="logo-mark" src="../assets/img/logo.png" alt="Green Curve" style="height:32px"/>
      <span class="nav__logo-text">Green <span class="nav__logo-accent">Curve</span></span>
    </a>
    <ul class="nav__links" role="list">
      <li><a href="../index.html#insights">Insights</a></li>
      <li><a href="../index.html#topics">Topics</a></li>
      <li><a href="../calculator.html">GHG Calculator</a></li>
      <li><a href="../brsr-simple.html">BRSR Report</a></li>
      <li><a href="../esg-intelligence.html" style="color:var(--emerald)">ESG Quotient</a></li>
      <li><a href="../index.html#contact">Contact</a></li>
    </ul>
  </nav>
</header>"""

FOOTER = f"""
<footer class="site-footer">
  <div class="container footer__inner">
    <div class="footer__left">
      <a href="../index.html" class="footer__logo">Green Curve</a>
      <p>Climate transition intelligence for Indian businesses.</p>
    </div>
    <div class="footer__right">
      <p>Data sourced from companies' publicly filed SEBI BRSR annual disclosures. Scores are Green Curve's own analytical output — not ratings issued by any SEBI-registered ESG Rating Provider.</p>
      <p style="font-size:.72rem;color:#475569;margin-top:6px">Not investment advice. Always verify against original company filings.</p>
      <p class="footer__copy">&copy; {date.today().year} Green Curve. All rights reserved.</p>
    </div>
  </div>
</footer>"""

def make_page(c):
    slug      = slug_map[c['company_name']]
    name      = c['company_name']
    score     = c.get('esg_risk_score', 0)
    tier      = c.get('risk_tier', 'Medium')
    sector    = c.get('sector', '')
    products  = c.get('products', '')
    fy        = c.get('financial_year', '')
    cin       = c.get('cin', '')
    nse       = c.get('nse_symbol', '')
    revenue   = c.get('revenue_crore')
    rb        = c.get('risk_breakdown', {})
    fe        = c.get('financial_exposure', {})
    sc        = c.get('supply_chain', {})
    gov       = c.get('governance', {})
    dm        = c.get('double_materiality', {})
    targets   = c.get('esg_targets', [])
    materials = c.get('materials_exposed', [])
    top_risks = c.get('top_risk_factors', [])
    ai_sum    = c.get('ai_summary', '')

    t_color   = tier_color(tier)
    risks_str = ', '.join(top_risks[:3]) if top_risks else 'N/A'
    meta_desc = (f"ESG risk score {score}/10 ({tier} Risk). Key risks: {risks_str}. "
                 f"Sector: {sector[:60]}. Based on SEBI BRSR FY {fy}.")

    # Schema.org JSON-LD
    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": f"{name} ESG Score & Risk Analysis",
        "description": meta_desc,
        "publisher": {"@type": "Organization", "name": "Green Curve",
                      "url": BASE_URL, "logo": f"{BASE_URL}/assets/img/logo.png"},
        "dateModified": TODAY,
        "mainEntityOfPage": f"{BASE_URL}/company/{slug}.html"
    }, ensure_ascii=False)

    # Risk breakdown bars
    rb_html = ''.join([
        risk_bar(rb.get('ghg_intensity'),    'GHG Intensity'),
        risk_bar(rb.get('water_intensity'),  'Water Intensity'),
        risk_bar(rb.get('waste_intensity'),  'Waste Intensity'),
        risk_bar(rb.get('epr_exposure'),     'EPR Exposure'),
        risk_bar(rb.get('compliance_risk'),  'Compliance Risk'),
        risk_bar(rb.get('hr_risk'),          'HR Risk'),
        risk_bar(rb.get('governance_risk'),  'Governance Risk'),
    ])

    # ESG targets
    targets_html = ''
    if targets:
        rows = ''.join(f"""<tr>
          <td>{esc(t.get('topic',''))}</td>
          <td>{esc(t.get('metric',''))}</td>
          <td><span class="badge badge--{'green' if t.get('type')=='Achieved' else 'amber'}">{esc(t.get('type',''))}</span></td>
        </tr>""" for t in targets)
        targets_html = f"""
        <div class="cp-card">
          <h2 class="cp-section-title">ESG Targets &amp; Commitments</h2>
          <table class="cp-table"><thead><tr><th>Topic</th><th>Target / Metric</th><th>Status</th></tr></thead>
          <tbody>{rows}</tbody></table>
        </div>"""

    # Materials
    mats_html = ''
    if materials:
        pills = ''.join(f'<span class="mat-pill">{esc(m)}</span>' for m in materials)
        mats_html = f'<div class="cp-card"><h2 class="cp-section-title">Material Risks</h2><div class="pills">{pills}</div></div>'

    # AI summary
    ai_html = ''
    if ai_sum:
        ai_html = f"""
        <div class="cp-card">
          <h2 class="cp-section-title">AI Risk Summary</h2>
          <p class="cp-ai-text">{esc(ai_sum)}</p>
          <p class="cp-disclaimer">Source: {esc(name)} BRSR Filing, FY {esc(fy)}. Derived from the company's own public disclosures. Not investment advice or a regulatory determination.</p>
        </div>"""

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{esc(name)} ESG Score &amp; Risk Analysis | Green Curve</title>
  <meta name="description" content="{esc(meta_desc)}"/>
  <meta name="robots" content="index,follow"/>
  <link rel="canonical" href="{BASE_URL}/company/{slug}.html"/>
  <meta property="og:title" content="{esc(name)} ESG Score | Green Curve"/>
  <meta property="og:description" content="{esc(meta_desc)}"/>
  <meta property="og:image" content="{BASE_URL}/assets/img/logo.png"/>
  <meta property="og:url" content="{BASE_URL}/company/{slug}.html"/>
  <meta name="twitter:card" content="summary"/>
  <meta name="twitter:title" content="{esc(name)} ESG Score | Green Curve"/>
  <meta name="twitter:description" content="{esc(meta_desc)}"/>
  <script type="application/ld+json">{schema}</script>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600&display=swap" rel="stylesheet"/>
  <link rel="stylesheet" href="../assets/css/style.css"/>
  <link rel="stylesheet" href="../assets/css/company-page.css"/>
  <link rel="icon" type="image/svg+xml" href="../assets/img/favicon.svg"/>
</head>
<body>

{NAV}

<!-- BREADCRUMB -->
<div class="breadcrumb container">
  <a href="../index.html">Home</a> &rsaquo;
  <a href="../esg-intelligence.html">ESG Quotient</a> &rsaquo;
  <span>{esc(name)}</span>
</div>

<!-- HERO -->
<section class="cp-hero">
  <div class="container cp-hero__inner">
    <div class="cp-hero__left">
      <div class="cp-tier-badge" style="background:{t_color}22;color:{t_color};border:1px solid {t_color}44">
        {esc(tier)} Risk
      </div>
      <h1 class="cp-hero__title">{esc(name)}</h1>
      <p class="cp-hero__sector">{esc(sector)}</p>
      <div class="cp-hero__meta">
        {f'<span>NSE: <strong>{esc(nse)}</strong></span>' if nse else ''}
        {f'<span>CIN: {esc(cin)}</span>' if cin else ''}
        {f'<span>FY: {esc(fy)}</span>' if fy else ''}
        {f'<span>Revenue: ₹{fmt_num(revenue)} Cr</span>' if revenue else ''}
      </div>
    </div>
    <div class="cp-hero__right">
      <div class="cp-score-ring" style="border-color:{t_color}">
        <div class="cp-score-val" style="color:{t_color}">{score}</div>
        <div class="cp-score-label">ESG Risk<br/>Score /10</div>
      </div>
    </div>
  </div>
</section>

<main class="container cp-main">

  <!-- Top Risk Factors -->
  <div class="cp-top-risks">
    {''.join(f'<span class="top-risk-pill">{esc(r)}</span>' for r in top_risks)}
  </div>

  <div class="cp-grid">

    <!-- Risk Breakdown -->
    <div class="cp-card">
      <h2 class="cp-section-title">Risk Breakdown</h2>
      <div class="rb-list">{rb_html}</div>
    </div>

    <!-- Financial Exposure -->
    <div class="cp-card">
      <h2 class="cp-section-title">Financial Exposure</h2>
      <div class="fe-grid">
        <div class="fe-item"><span class="fe-label">Est. Compliance Cost</span><span class="fe-val">{esc(fe.get('estimated_compliance_cost_band','—'))}</span></div>
        <div class="fe-item"><span class="fe-label">EPR Applicable</span><span class="fe-val">{esc(fe.get('epr_applicable','Unknown'))}</span></div>
        <div class="fe-item"><span class="fe-label">Scope 1 Emissions</span><span class="fe-val">{fmt_num(fe.get('scope1_emissions_tco2e'))} tCO2e</span></div>
        <div class="fe-item"><span class="fe-label">Scope 2 Emissions</span><span class="fe-val">{fmt_num(fe.get('scope2_emissions_tco2e'))} tCO2e</span></div>
        <div class="fe-item"><span class="fe-label">Water Withdrawal</span><span class="fe-val">{fmt_num(fe.get('water_withdrawal_m3'))} m³</span></div>
        <div class="fe-item"><span class="fe-label">Waste Generated</span><span class="fe-val">{fmt_num(fe.get('waste_tonnes'))} T</span></div>
      </div>
    </div>

    <!-- Governance -->
    <div class="cp-card">
      <h2 class="cp-section-title">Governance</h2>
      <div class="fe-grid">
        <div class="fe-item"><span class="fe-label">Anti-Corruption Policy</span><span class="fe-val">{esc(gov.get('anti_corruption_policy','—'))}</span></div>
        <div class="fe-item"><span class="fe-label">Conflict of Interest Policy</span><span class="fe-val">{esc(gov.get('conflict_of_interest','—'))}</span></div>
        <div class="fe-item"><span class="fe-label">BRSR Assurance</span><span class="fe-val">{esc(gov.get('brsr_assurance','—'))}</span></div>
        <div class="fe-item"><span class="fe-label">Assurance Provider</span><span class="fe-val">{esc(gov.get('assurance_provider','—'))}</span></div>
      </div>
    </div>

    <!-- Double Materiality -->
    <div class="cp-card">
      <h2 class="cp-section-title">Double Materiality</h2>
      <div class="fe-grid">
        <div class="fe-item"><span class="fe-label">Financial Materiality</span><span class="fe-val" style="color:{score_color(dm.get('financial_materiality'))}">{dm.get('financial_materiality','—')}</span></div>
        <div class="fe-item"><span class="fe-label">Impact Materiality</span><span class="fe-val" style="color:{score_color(dm.get('impact_materiality'))}">{dm.get('impact_materiality','—')}</span></div>
        <div class="fe-item" style="grid-column:1/-1"><span class="fe-label">Quadrant</span><span class="fe-val">{esc(dm.get('quadrant','—'))}</span></div>
      </div>
    </div>

    <!-- Supply Chain -->
    <div class="cp-card">
      <h2 class="cp-section-title">Supply Chain</h2>
      <div class="fe-grid">
        <div class="fe-item"><span class="fe-label">MSME Sourcing</span><span class="fe-val">{fmt_num(sc.get('msme_sourcing_pct'))}%</span></div>
        <div class="fe-item"><span class="fe-label">Lifecycle Assessment</span><span class="fe-val">{esc(sc.get('lifecycle_assessment','—'))}</span></div>
        <div class="fe-item"><span class="fe-label">Product Reclaim</span><span class="fe-val">{'Yes' if sc.get('product_reclaim_process') else 'No'}</span></div>
      </div>
    </div>

  </div><!-- /cp-grid -->

  {mats_html}
  {targets_html}
  {ai_html}

  <!-- Back CTA -->
  <div class="cp-cta">
    <a href="../esg-intelligence.html" class="cp-cta-btn">&larr; Back to ESG Quotient Dashboard</a>
    <a href="index.html" class="cp-cta-link">Browse all companies &rarr;</a>
  </div>

</main>

{FOOTER}
<script>
  const h = document.getElementById('site-header');
  window.addEventListener('scroll', () => h.classList.toggle('scrolled', scrollY > 20), {{passive:true}});
</script>
</body>
</html>"""
    return page, slug

# ── Write company pages ────────────────────────────────────────────────────────
generated = []
for c in companies:
    page_html, slug = make_page(c)
    out_path = os.path.join(OUT_DIR, f"{slug}.html")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(page_html)
    generated.append((c['company_name'], slug, c.get('esg_risk_score',0), c.get('risk_tier','Medium'), c.get('sector','')))

print(f"  Written {len(generated)} company pages to ./{OUT_DIR}/")

# ── company/index.html ─────────────────────────────────────────────────────────
rows_html = '\n'.join(f"""
  <tr>
    <td><a href="{slug}.html">{esc(name)}</a></td>
    <td style="font-size:.8rem;color:#94a3b8">{esc(sector[:50])}</td>
    <td><span style="color:{tier_color(tier)};font-weight:700">{score}</span></td>
    <td><span style="color:{tier_color(tier)}">{tier}</span></td>
  </tr>""" for name, slug, score, tier, sector in sorted(generated, key=lambda x: -x[2]))

index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>ESG Risk Scores — All Indian Listed Companies | Green Curve</title>
  <meta name="description" content="ESG risk scores and BRSR-based financial risk analysis for {len(generated)} Indian listed companies. Powered by Green Curve."/>
  <meta name="robots" content="index,follow"/>
  <link rel="canonical" href="{BASE_URL}/company/"/>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600&display=swap" rel="stylesheet"/>
  <link rel="stylesheet" href="../assets/css/style.css"/>
  <link rel="stylesheet" href="../assets/css/company-page.css"/>
  <link rel="icon" type="image/svg+xml" href="../assets/img/favicon.svg"/>
</head>
<body>
{NAV}
<div class="breadcrumb container">
  <a href="../index.html">Home</a> &rsaquo;
  <a href="../esg-intelligence.html">ESG Quotient</a> &rsaquo;
  <span>All Companies</span>
</div>
<div class="container" style="padding:40px 0 80px">
  <h1 style="font-size:2rem;margin-bottom:8px">ESG Risk Scores — Indian Listed Companies</h1>
  <p style="color:#94a3b8;margin-bottom:32px">{len(generated)} companies analysed · Based on SEBI BRSR public filings · Updated {data_as_of}</p>
  <div class="table-wrap">
    <table class="screener-table">
      <thead><tr><th>Company</th><th>Sector</th><th>ESG Risk Score</th><th>Risk Tier</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
  <p style="margin-top:24px;font-size:.78rem;color:#475569">Scores derived from companies' own SEBI BRSR filings. Not investment advice. Not a SEBI-registered ESG Rating Provider output.</p>
</div>
{FOOTER}
<script>
  const h = document.getElementById('site-header');
  window.addEventListener('scroll', () => h.classList.toggle('scrolled', scrollY > 20), {{passive:true}});
</script>
</body>
</html>"""

with open(os.path.join(OUT_DIR, 'index.html'), 'w', encoding='utf-8') as f:
    f.write(index_html)
print(f"  Written company/index.html")

# ── Update sitemap.xml ─────────────────────────────────────────────────────────
with open('sitemap.xml', encoding='utf-8') as f:
    sitemap = f.read()

# Remove old company entries if any, then insert before closing </urlset>
sitemap = re.sub(r'\s*<!-- COMPANY PAGES -->.*?<!-- /COMPANY PAGES -->', '',
                 sitemap, flags=re.DOTALL)

company_urls = '\n'.join(f"""  <url>
    <loc>{BASE_URL}/company/{slug}.html</loc>
    <lastmod>{TODAY}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>""" for _, slug, *_ in generated)

company_urls = f"\n  <!-- COMPANY PAGES -->\n{company_urls}\n  <!-- /COMPANY PAGES -->"

# Also add company index
company_urls = f"""
  <url>
    <loc>{BASE_URL}/company/</loc>
    <lastmod>{TODAY}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>{company_urls}"""

sitemap = sitemap.replace('</urlset>', company_urls + '\n</urlset>')

with open('sitemap.xml', 'w', encoding='utf-8') as f:
    f.write(sitemap)
print(f"  Updated sitemap.xml with {len(generated) + 1} new URLs")

print(f"\nDone. {len(generated)} company pages + index + sitemap updated.")
