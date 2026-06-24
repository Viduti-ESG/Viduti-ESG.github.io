"""
Green Curve — Evergreen Pillar-Page Generator
Builds long-form, evergreen guide pages that target high-volume head terms
("BRSR reporting", "EPR registration", "what is BRSR", "Scope 3 emissions",
"ISSB IFRS S1 S2", "carbon credit trading scheme India"). Each page funnels
into a Green Curve tool via a prominent CTA.

Unlike posts/ (dated news that decays) these are undated, maintained reference
pages. They live at the site root so nav/asset paths match the rest of the site.

Run:  GC_SITE_URL=https://greencurve.solutions python generate_guides.py
Then run generate_company_pages.py to refresh sitemap.xml (it lists these pages).
"""

import os, html, json

BASE_URL = os.environ.get("GC_SITE_URL", "https://greencurve.solutions").rstrip("/")

# ── Shared chrome ─────────────────────────────────────────────────────────────
CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0a0f1a;--surface:#111827;--border:rgba(255,255,255,.08);--text:#e2e8f0;--muted:#94a3b8;--dim:#64748b;--emerald:#10b981;--emerald2:#34d399}
html{scroll-behavior:smooth}
body{font-family:'DM Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);line-height:1.7}
a{color:inherit;text-decoration:none}
.container{max-width:1180px;margin:0 auto;padding:0 24px}
.site-header{position:sticky;top:0;z-index:50;background:rgba(10,15,26,.85);backdrop-filter:blur(10px);border-bottom:1px solid var(--border)}
.nav{display:flex;align-items:center;justify-content:space-between;height:64px}
.nav__logo{display:flex;align-items:center;gap:10px;font-family:'DM Serif Display',serif;font-size:1.25rem}
.nav__logo-accent{color:var(--emerald)}
.nav__links{display:flex;gap:22px;list-style:none;font-size:.92rem;align-items:center}
.nav__links a:hover{color:var(--emerald)}
.nav__cta{background:var(--emerald);color:#04110b!important;padding:8px 16px;border-radius:8px;font-weight:600;font-size:.88rem}
.breadcrumb{padding:18px 0;font-size:.82rem;color:var(--dim)}
.breadcrumb a:hover{color:var(--emerald)}
.hero{padding:26px 0 8px}
.hero .kicker{color:var(--emerald2);font-size:.8rem;font-weight:600;text-transform:uppercase;letter-spacing:.07em}
.hero h1{font-family:'DM Serif Display',serif;font-size:2.5rem;line-height:1.12;margin:10px 0 14px}
.hero .intro{color:var(--muted);font-size:1.08rem;max-width:760px}
.layout{display:grid;grid-template-columns:240px 1fr;gap:48px;padding:40px 0 70px;align-items:start}
.toc{position:sticky;top:90px;font-size:.86rem}
.toc h4{color:var(--dim);text-transform:uppercase;letter-spacing:.05em;font-size:.72rem;margin-bottom:12px}
.toc a{display:block;color:var(--muted);padding:5px 0;border-left:2px solid transparent;padding-left:12px;margin-left:-2px}
.toc a:hover,.toc a.active{color:var(--emerald2);border-left-color:var(--emerald)}
.article h2{font-family:'DM Serif Display',serif;font-size:1.7rem;margin:38px 0 14px;scroll-margin-top:84px}
.article h3{font-size:1.18rem;margin:24px 0 8px;color:#f1f5f9}
.article p{margin:12px 0;color:#cbd5e1}
.article ul,.article ol{margin:12px 0 12px 22px;color:#cbd5e1}
.article li{margin:7px 0}
.article strong{color:#f1f5f9}
.article a{color:var(--emerald2);text-decoration:underline;text-underline-offset:2px}
.callout{background:rgba(16,185,129,.06);border:1px solid rgba(16,185,129,.22);border-radius:12px;padding:18px 22px;margin:22px 0}
.callout strong{color:var(--emerald2)}
table.gc{width:100%;border-collapse:collapse;margin:18px 0;font-size:.9rem}
table.gc th,table.gc td{border:1px solid var(--border);padding:10px 12px;text-align:left}
table.gc th{background:var(--surface);color:#f1f5f9}
.cta-band{background:linear-gradient(135deg,rgba(16,185,129,.14),rgba(16,185,129,.04));border:1px solid rgba(16,185,129,.3);border-radius:16px;padding:30px;margin:36px 0;text-align:center}
.cta-band h3{font-family:'DM Serif Display',serif;font-size:1.5rem;margin-bottom:8px;color:#fff}
.cta-band p{color:var(--muted);margin-bottom:18px;max-width:560px;margin-left:auto;margin-right:auto}
.cta-btn{display:inline-block;background:var(--emerald);color:#04110b;padding:12px 26px;border-radius:10px;font-weight:700}
.faq-item{border-bottom:1px solid var(--border)}
.faq-q{width:100%;text-align:left;background:none;border:none;color:#f1f5f9;font-size:1.02rem;font-weight:600;padding:18px 0;cursor:pointer;display:flex;justify-content:space-between;gap:16px;font-family:inherit}
.faq-q::after{content:'+';color:var(--emerald2);font-size:1.3rem;line-height:1}
.faq-item.open .faq-q::after{content:'\\2212'}
.faq-a{max-height:0;overflow:hidden;transition:max-height .25s ease;color:var(--muted)}
.faq-item.open .faq-a{max-height:600px;padding-bottom:18px}
.related{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px;margin:18px 0 0}
.related a{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;font-weight:600;font-size:.92rem}
.related a:hover{border-color:var(--emerald)}
.site-footer{border-top:1px solid var(--border);padding:30px 0;color:var(--dim);font-size:.82rem}
.site-footer a{color:var(--muted)}
@media(max-width:860px){.layout{grid-template-columns:1fr}.toc{display:none}.hero h1{font-size:1.9rem}}
"""

def header():
    return """
<header class="site-header">
  <nav class="nav container">
    <a href="index.html" class="nav__logo">
      <img src="assets/img/logo.png" alt="Green Curve" style="height:30px"/>
      <span>Green <span class="nav__logo-accent">Curve</span></span>
    </a>
    <ul class="nav__links" role="list">
      <li><a href="esg-intelligence.html">ESG Quotient</a></li>
      <li><a href="brsr-simple.html">BRSR Report</a></li>
      <li><a href="calculator.html">GHG Calculator</a></li>
      <li><a href="posts/">Insights</a></li>
      <li><a href="calculator.html" class="nav__cta">Calculate &rarr;</a></li>
    </ul>
  </nav>
</header>"""

def footer():
    return """
<footer class="site-footer">
  <div class="container">
    <p>&copy; <span id="year"></span> Green Curve Research. Climate transition intelligence for Indian businesses.
       &nbsp;&middot;&nbsp; <a href="privacy-policy.html">Privacy</a> &nbsp;&middot;&nbsp;
       <a href="terms-of-use.html">Terms</a></p>
    <p style="margin-top:8px;color:#475569">Educational reference, not legal or investment advice. Always verify against the latest SEBI / CPCB / MoEFCC notifications.</p>
  </div>
</footer>
<script>
  document.getElementById('year').textContent = new Date().getFullYear();
  function toggleFaq(b){var it=b.closest('.faq-item');var open=it.classList.contains('open');
    document.querySelectorAll('.faq-item.open').forEach(function(e){e.classList.remove('open')});
    if(!open)it.classList.add('open');}
  var secs=[].slice.call(document.querySelectorAll('.article h2[id]'));
  var links=[].slice.call(document.querySelectorAll('.toc a'));
  window.addEventListener('scroll',function(){var a='';secs.forEach(function(s){if(s.getBoundingClientRect().top<=110)a='#'+s.id});
    links.forEach(function(l){l.classList.toggle('active',l.getAttribute('href')===a)})},{passive:true});
</script>"""

def render(g):
    toc = "\n".join(
        f'    <a href="#{s["id"]}">{html.escape(s["h2"])}</a>' for s in g["sections"])
    body = "\n".join(
        f'  <h2 id="{s["id"]}">{html.escape(s["h2"])}</h2>\n{s["html"]}' for s in g["sections"])
    faqs = "\n".join(f"""
    <div class="faq-item">
      <button class="faq-q" onclick="toggleFaq(this)">{html.escape(q)}</button>
      <div class="faq-a"><p>{a}</p></div>
    </div>""" for q, a in g["faqs"])
    related = "\n".join(
        f'      <a href="{u}">{html.escape(l)}</a>' for u, l in g["related"])

    faq_ld = {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{
            "@type": "Question", "name": q,
            "acceptedAnswer": {"@type": "Answer", "text": _strip(a)}
        } for q, a in g["faqs"]]
    }
    article_ld = {
        "@context": "https://schema.org", "@type": "Article",
        "headline": g["h1"], "description": g["description"],
        "url": f"{BASE_URL}/{g['slug']}",
        "publisher": {"@type": "Organization", "name": "Green Curve Research",
                      "url": f"{BASE_URL}/", "logo": f"{BASE_URL}/assets/img/logo.png"},
        "inLanguage": "en-IN"
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{html.escape(g['title'])}</title>
  <meta name="description" content="{html.escape(g['description'])}"/>
  <meta name="keywords" content="{html.escape(g['keywords'])}"/>
  <meta name="robots" content="index, follow"/>
  <link rel="canonical" href="{BASE_URL}/{g['slug']}"/>
  <meta property="og:type" content="article"/>
  <meta property="og:url" content="{BASE_URL}/{g['slug']}"/>
  <meta property="og:site_name" content="Green Curve"/>
  <meta property="og:title" content="{html.escape(g['title'])}"/>
  <meta property="og:description" content="{html.escape(g['description'])}"/>
  <meta property="og:image" content="{BASE_URL}/assets/img/logo.png"/>
  <meta name="twitter:card" content="summary_large_image"/>
  <meta name="twitter:title" content="{html.escape(g['h1'])}"/>
  <meta name="twitter:description" content="{html.escape(g['description'])}"/>
  <meta name="twitter:image" content="{BASE_URL}/assets/img/logo.png"/>
  <script type="application/ld+json">{json.dumps(article_ld, ensure_ascii=False)}</script>
  <script type="application/ld+json">{json.dumps(faq_ld, ensure_ascii=False)}</script>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600&display=swap" rel="stylesheet"/>
  <link rel="icon" type="image/svg+xml" href="assets/img/favicon.svg"/>
  <style>{CSS}</style>
</head>
<body>
{header()}
<div class="container">
  <div class="breadcrumb"><a href="index.html">Home</a> &rsaquo; <a href="posts/">Guides</a> &rsaquo; <span>{html.escape(g['short'])}</span></div>
  <div class="hero">
    <div class="kicker">{html.escape(g['kicker'])}</div>
    <h1>{html.escape(g['h1'])}</h1>
    <p class="intro">{g['intro']}</p>
  </div>
  <div class="layout">
    <aside class="toc">
      <h4>On this page</h4>
{toc}
    </aside>
    <article class="article">
{body}

      <div class="cta-band">
        <h3>{html.escape(g['cta']['heading'])}</h3>
        <p>{g['cta']['text']}</p>
        <a class="cta-btn" href="{g['cta']['url']}">{html.escape(g['cta']['label'])}</a>
      </div>

      <h2 id="faq">Frequently asked questions</h2>
      <div class="faq">{faqs}
      </div>

      <h2 id="related">Related tools &amp; guides</h2>
      <div class="related">
{related}
      </div>
    </article>
  </div>
</div>
{footer()}
</body>
</html>"""

def _strip(s):
    import re
    return re.sub(r"<[^>]+>", "", s).replace("&amp;", "&").strip()


# ── Content ───────────────────────────────────────────────────────────────────
GUIDES = [
{
  "slug": "brsr-reporting",
  "short": "BRSR Reporting",
  "kicker": "SEBI Disclosure · India",
  "title": "BRSR Reporting in India: Complete 2026 Guide (Format, Applicability, Core) | Green Curve",
  "h1": "BRSR Reporting in India: The Complete Guide",
  "description": "What BRSR is, who must file, the report format, the 9 NGRBC principles, and BRSR Core reasonable-assurance timelines for India's top-1000 listed companies — explained for 2026.",
  "keywords": "BRSR reporting, what is BRSR, BRSR full form, BRSR applicability, BRSR format, BRSR Core, BRSR vs BRR, SEBI BRSR, business responsibility and sustainability report, BRSR 9 principles",
  "intro": "The Business Responsibility and Sustainability Report (BRSR) is SEBI's mandatory ESG disclosure for India's largest listed companies. This guide explains what BRSR is, who must file it, what goes in each section, and how the BRSR Core assurance mandate ramps up to the top 1,000 companies by FY 2026-27.",
  "sections": [
    {"id":"what","h2":"What is BRSR?","html":
     "<p><strong>BRSR (Business Responsibility and Sustainability Report)</strong> is a standardised ESG disclosure framework introduced by the Securities and Exchange Board of India (SEBI) in May 2021. It replaced the older Business Responsibility Report (BRR) and is built on the nine principles of the <strong>National Guidelines on Responsible Business Conduct (NGRBC)</strong>.</p>"
     "<p>BRSR converts sustainability from a narrative annexure into a structured, quantitative, comparable disclosure — covering greenhouse-gas emissions, energy and water use, waste, employee wellbeing, human rights, community impact and governance — filed as part of the company's annual report.</p>"},
    {"id":"who","h2":"Who must file BRSR? (Applicability)","html":
     "<p>BRSR is mandatory for the <strong>top 1,000 listed companies by market capitalisation</strong> (as of 31 March each year) from <strong>FY 2022-23</strong> onwards. Companies below that threshold may file voluntarily, and unlisted companies increasingly adopt it for value-chain and investor reasons.</p>"
     "<div class='callout'><strong>Tip:</strong> Market cap is assessed each 31 March, so a company that crosses into the top 1,000 becomes subject to BRSR for that financial year. Track your rank early.</div>"},
    {"id":"format","h2":"BRSR format: the three sections","html":
     "<p>The BRSR is organised into three sections:</p>"
     "<table class='gc'><thead><tr><th>Section</th><th>What it covers</th></tr></thead><tbody>"
     "<tr><td><strong>A — General Disclosures</strong></td><td>Company identity, operations, products, employees, CSR, complaints.</td></tr>"
     "<tr><td><strong>B — Management &amp; Process</strong></td><td>Policies, governance, leadership and oversight mapped to the 9 NGRBC principles.</td></tr>"
     "<tr><td><strong>C — Principle-wise Performance</strong></td><td>Quantitative and qualitative KPIs for each of the 9 principles — the bulk of the report.</td></tr>"
     "</tbody></table>"
     "<p>Disclosures are split into <strong>Essential Indicators</strong> (mandatory for all filers) and <strong>Leadership Indicators</strong> (advanced metrics, voluntary but expected of mature programmes) — roughly 140 data points in total.</p>"},
    {"id":"principles","h2":"The 9 NGRBC principles","html":
     "<ol>"
     "<li><strong>P1 — Ethics &amp; transparency:</strong> integrity, anti-corruption, governance.</li>"
     "<li><strong>P2 — Sustainable &amp; safe goods:</strong> product lifecycle, R&amp;D, recyclability.</li>"
     "<li><strong>P3 — Employee wellbeing:</strong> wages, safety, benefits, diversity.</li>"
     "<li><strong>P4 — Stakeholder responsiveness:</strong> identifying and engaging stakeholders.</li>"
     "<li><strong>P5 — Human rights:</strong> across operations and the value chain.</li>"
     "<li><strong>P6 — Environment:</strong> emissions, energy, water, waste, biodiversity.</li>"
     "<li><strong>P7 — Policy advocacy:</strong> responsible and transparent lobbying.</li>"
     "<li><strong>P8 — Inclusive growth:</strong> community development and equitable impact.</li>"
     "<li><strong>P9 — Consumer value:</strong> product safety, data privacy, fair disclosure.</li>"
     "</ol>"},
    {"id":"core","h2":"BRSR Core and the assurance glide-path","html":
     "<p><strong>BRSR Core</strong> is a focused subset of the most decision-useful ESG KPIs (around 49 attributes across nine themes such as GHG intensity, water, energy, waste, and job creation) that require independent <strong>reasonable assurance</strong>. SEBI introduced it in July 2023 with a phased rollout:</p>"
     "<table class='gc'><thead><tr><th>Financial year</th><th>Reasonable assurance on BRSR Core</th></tr></thead><tbody>"
     "<tr><td>FY 2023-24</td><td>Top 150 listed companies</td></tr>"
     "<tr><td>FY 2024-25</td><td>Top 250 listed companies</td></tr>"
     "<tr><td>FY 2025-26</td><td>Top 500 listed companies</td></tr>"
     "<tr><td>FY 2026-27</td><td>Top 1,000 listed companies</td></tr>"
     "</tbody></table>"
     "<p>A parallel <strong>value-chain</strong> requirement extends ESG disclosure (on a comply-or-explain basis) to the company's significant upstream and downstream partners — making supplier data collection a practical necessity.</p>"},
    {"id":"how","h2":"How to prepare your BRSR","html":
     "<p>A practical sequence:</p><ol>"
     "<li><strong>Map data owners</strong> across HR, EHS, finance, procurement and legal.</li>"
     "<li><strong>Build your GHG inventory</strong> (Scope 1, 2 and material Scope 3) using consistent emission factors.</li>"
     "<li><strong>Collect value-chain data</strong> from significant suppliers early — it is the slowest input.</li>"
     "<li><strong>Draft Section C</strong> principle-by-principle, keeping audit-ready evidence.</li>"
     "<li><strong>Get BRSR Core assured</strong> if you are in scope for the year.</li>"
     "</ol>"},
  ],
  "cta": {"heading":"Generate a SEBI-format BRSR report — free",
          "text":"Skip the blank template. Enter your ESG data and export a structured BRSR draft in your browser, then check your readiness for reasonable assurance.",
          "url":"brsr-simple.html","label":"Open the free BRSR generator"},
  "faqs": [
    ("What is the full form of BRSR?","BRSR stands for <strong>Business Responsibility and Sustainability Report</strong>, SEBI's mandatory ESG disclosure for India's largest listed companies."),
    ("Is BRSR mandatory?","Yes — it is mandatory for the top 1,000 listed companies by market capitalisation from FY 2022-23. Other companies may file voluntarily."),
    ("What is the difference between BRSR and BRSR Core?","BRSR is the full disclosure; BRSR Core is a smaller set of ~49 key KPIs that require independent reasonable assurance, rolled out to the top 1,000 companies by FY 2026-27."),
    ("How many indicators are in a BRSR?","Around 140 data points, split between mandatory Essential Indicators and voluntary Leadership Indicators across the nine NGRBC principles."),
    ("Where are BRSR reports published?","They are filed as part of the annual report and disclosed publicly on the BSE and NSE websites."),
  ],
  "related": [("brsr-simple.html","Free BRSR Report Generator"),("assurance.html","BRSR Core Assurance Checker"),
              ("value-chain.html","Value-Chain Supplier Assessment"),("scope-3-emissions.html","Scope 3 Emissions Guide"),
              ("esg-intelligence.html","ESG Quotient — company scores")],
},
{
  "slug": "epr-registration",
  "short": "EPR Registration",
  "kicker": "CPCB Compliance · India",
  "title": "EPR Registration in India (2026): Plastic, E-Waste & Battery — CPCB Guide | Green Curve",
  "h1": "EPR Registration in India: Plastic, E-Waste & Battery",
  "description": "Who must register for Extended Producer Responsibility in India, how the CPCB portals work for plastic, e-waste and battery waste, EPR targets and certificates, and penalties for non-compliance.",
  "keywords": "EPR registration, EPR plastic waste, EPR e-waste, EPR battery, CPCB EPR portal, extended producer responsibility India, EPR certificate, PIBO registration, environmental compensation, plastic waste management rules",
  "intro": "Extended Producer Responsibility (EPR) makes producers, importers and brand owners responsible for the end-of-life of the products and packaging they put on the market. This guide covers EPR registration in India across plastic, e-waste and batteries — the CPCB portals, targets, certificates and penalties.",
  "sections": [
    {"id":"what","h2":"What is EPR?","html":
     "<p><strong>Extended Producer Responsibility (EPR)</strong> is a policy principle that shifts the responsibility for collecting and recycling waste back to the entities that introduce products into the market. In India it is administered by the <strong>Central Pollution Control Board (CPCB)</strong> through dedicated online registration and reporting portals for each waste stream.</p>"},
    {"id":"who","h2":"Who must register for EPR?","html":
     "<p>EPR obligations fall on <strong>Producers, Importers and Brand Owners (PIBOs)</strong> — and, in some streams, on recyclers and refurbishers. If your business manufactures, imports, or sells products under its brand in any of the regulated categories below, you almost certainly need to register.</p>"
     "<div class='callout'><strong>Importers, note:</strong> EPR registration is increasingly a gateway for customs clearance. Missing registration can block consignments at the port.</div>"},
    {"id":"streams","h2":"The main EPR waste streams","html":
     "<table class='gc'><thead><tr><th>Stream</th><th>Governing rules</th><th>Who registers</th></tr></thead><tbody>"
     "<tr><td><strong>Plastic packaging</strong></td><td>Plastic Waste Management Rules, 2016 (amended 2022, with EPR guidelines and later amendments)</td><td>Producers, importers, brand owners</td></tr>"
     "<tr><td><strong>E-waste</strong></td><td>E-Waste (Management) Rules, 2022 (effective 1 April 2023)</td><td>Producers, manufacturers, recyclers, refurbishers</td></tr>"
     "<tr><td><strong>Batteries</strong></td><td>Battery Waste Management Rules, 2022</td><td>Producers and importers of batteries</td></tr>"
     "<tr><td><strong>Tyres / used oil</strong></td><td>Hazardous &amp; Other Wastes rules with EPR schedules</td><td>Producers and importers</td></tr>"
     "</tbody></table>"},
    {"id":"how","h2":"How EPR registration works","html":
     "<p>The mechanics are broadly similar across streams:</p><ol>"
     "<li><strong>Register</strong> on the relevant CPCB EPR portal with your incorporation, PAN and GST documents.</li>"
     "<li><strong>Declare</strong> the quantity and category of material you place on the market.</li>"
     "<li><strong>Meet annual EPR targets</strong> — collect/recycle a prescribed percentage of that quantity.</li>"
     "<li><strong>Buy or generate EPR certificates</strong> from registered recyclers to evidence fulfilment.</li>"
     "<li><strong>File annual returns</strong> reconciling obligations against certificates.</li>"
     "</ol>"},
    {"id":"penalties","h2":"Penalties for non-compliance","html":
     "<p>Shortfalls attract <strong>Environmental Compensation (EC)</strong> levied by CPCB under the Environment (Protection) Act — calculated on the unfulfilled obligation, and in serious cases accompanied by suspension of registration or blocked imports. EC is intended to be higher than the cost of compliance, so it is rarely cheaper to default.</p>"},
    {"id":"brsr","h2":"How EPR connects to BRSR","html":
     "<p>EPR data — quantities placed on market, recycling achieved, EC paid — feeds directly into Principle 2 and Principle 6 of your <a href='brsr-reporting.html'>BRSR</a>. Treating EPR and BRSR as one data pipeline avoids duplicate effort and inconsistent numbers.</p>"},
  ],
  "cta": {"heading":"See where Indian companies stand on EPR &amp; environment",
          "text":"Green Curve's ESG Quotient analyses EPR exposure and environmental risk for 1,200+ Indian listed companies from their public BRSR filings.",
          "url":"esg-intelligence.html","label":"Explore the ESG Quotient"},
  "faqs": [
    ("Who needs EPR registration in India?","Producers, importers and brand owners (PIBOs) dealing in plastic packaging, electronics, batteries, tyres and similar regulated products must register on the relevant CPCB portal."),
    ("Is EPR registration mandatory for importers?","Yes. For many product categories EPR registration is effectively required for customs clearance, and importing without it can lead to blocked consignments."),
    ("What is an EPR certificate?","An EPR certificate is proof — generated by a registered recycler — that a quantity of waste has been collected and recycled. Producers buy or generate these to meet their annual EPR targets."),
    ("What happens if I miss my EPR target?","CPCB levies Environmental Compensation on the unfulfilled portion and can suspend your registration. The charge is designed to exceed the cost of genuine compliance."),
    ("Which rules govern plastic EPR?","The Plastic Waste Management Rules, 2016, as amended in 2022 (which introduced the EPR guidelines) and subsequent amendments covering recycled-content and end-of-life categories."),
  ],
  "related": [("brsr-reporting.html","BRSR Reporting Guide"),("esg-intelligence.html","ESG Quotient — EPR exposure"),
              ("posts/","Latest EPR / CPCB notices"),("scope-3-emissions.html","Scope 3 Emissions Guide"),
              ("value-chain.html","Value-Chain Supplier Assessment")],
},
{
  "slug": "scope-3-emissions",
  "short": "Scope 3 Emissions",
  "kicker": "GHG Accounting · Value Chain",
  "title": "Scope 3 Emissions Explained: The 15 Categories & How to Measure Them | Green Curve",
  "h1": "Scope 3 Emissions: The Value-Chain Guide",
  "description": "What Scope 3 emissions are, the 15 GHG Protocol categories, why they often exceed 70% of a company's footprint, and how Indian companies can measure value-chain emissions for BRSR and SBTi.",
  "keywords": "Scope 3 emissions, scope 3 categories, value chain emissions, GHG Protocol scope 3, scope 1 2 3, scope 3 calculation, supplier emissions, BRSR scope 3, SBTi scope 3",
  "intro": "Scope 3 covers the indirect emissions across a company's value chain — usually the largest and hardest-to-measure part of the carbon footprint. This guide explains the 15 GHG Protocol categories, why Scope 3 matters for BRSR and SBTi, and a practical path to measuring it.",
  "sections": [
    {"id":"what","h2":"Scope 1, 2 and 3 — the difference","html":
     "<p>The GHG Protocol splits emissions into three scopes:</p><ul>"
     "<li><strong>Scope 1</strong> — direct emissions from owned or controlled sources (fuel combustion, company vehicles, process emissions).</li>"
     "<li><strong>Scope 2</strong> — indirect emissions from purchased electricity, steam, heat and cooling.</li>"
     "<li><strong>Scope 3</strong> — all other indirect emissions across the value chain, upstream and downstream.</li>"
     "</ul><div class='callout'><strong>Why it matters:</strong> For most companies Scope 3 is <strong>70%+ of total emissions</strong> — sometimes well over 90% — so a footprint without it is incomplete.</div>"},
    {"id":"categories","h2":"The 15 Scope 3 categories","html":
     "<p>The GHG Protocol Corporate Value Chain (Scope 3) Standard defines 15 categories — 8 upstream and 7 downstream:</p>"
     "<table class='gc'><thead><tr><th>Upstream</th><th>Downstream</th></tr></thead><tbody>"
     "<tr><td>1. Purchased goods &amp; services</td><td>9. Downstream transport &amp; distribution</td></tr>"
     "<tr><td>2. Capital goods</td><td>10. Processing of sold products</td></tr>"
     "<tr><td>3. Fuel- &amp; energy-related activities</td><td>11. Use of sold products</td></tr>"
     "<tr><td>4. Upstream transport &amp; distribution</td><td>12. End-of-life of sold products</td></tr>"
     "<tr><td>5. Waste generated in operations</td><td>13. Downstream leased assets</td></tr>"
     "<tr><td>6. Business travel</td><td>14. Franchises</td></tr>"
     "<tr><td>7. Employee commuting</td><td>15. Investments</td></tr>"
     "<tr><td>8. Upstream leased assets</td><td></td></tr>"
     "</tbody></table>"},
    {"id":"measure","h2":"How to measure Scope 3","html":
     "<p>A pragmatic approach:</p><ol>"
     "<li><strong>Screen</strong> all 15 categories to find which are material to your business — typically categories 1, 4, 11 and 12.</li>"
     "<li><strong>Start spend-based</strong> (emission factors × procurement spend) for a fast first estimate.</li>"
     "<li><strong>Move to activity- and supplier-specific data</strong> for your largest categories over time.</li>"
     "<li><strong>Engage suppliers</strong> for primary data — the single biggest accuracy improvement.</li>"
     "</ol>"},
    {"id":"india","h2":"Scope 3 for BRSR and SBTi in India","html":
     "<p>India's <a href='brsr-reporting.html'>BRSR</a> captures Scope 1 and 2 as essential indicators and Scope 3 as a leadership indicator, while BRSR Core and value-chain disclosures push Scope 3 up the agenda. For science-based targets, the SBTi requires a Scope 3 inventory and target where Scope 3 exceeds 40% of total emissions — true for most companies.</p>"},
  ],
  "cta": {"heading":"Measure your value-chain emissions",
          "text":"Use Green Curve's GHG calculator to build your Scope 1, 2 and 3 inventory with India-specific factors — then collect supplier data through the value-chain module.",
          "url":"calculator.html","label":"Open the free GHG calculator"},
  "faqs": [
    ("What are Scope 3 emissions?","Scope 3 emissions are all indirect greenhouse-gas emissions that occur across a company's value chain — both upstream (e.g. purchased goods) and downstream (e.g. use of sold products) — outside its own operations and energy purchases."),
    ("How many Scope 3 categories are there?","Fifteen, as defined by the GHG Protocol: eight upstream and seven downstream categories."),
    ("Why is Scope 3 so important?","For most companies Scope 3 is the majority of the total carbon footprint — often more than 70% — so emissions targets and disclosures are incomplete without it."),
    ("Is Scope 3 required for BRSR?","Scope 1 and 2 are essential BRSR indicators; Scope 3 is a leadership indicator and is increasingly expected, particularly under BRSR Core and value-chain disclosure."),
    ("How do I start measuring Scope 3?","Screen all 15 categories for materiality, begin with a spend-based estimate for the largest categories, then progressively replace it with supplier-specific data."),
  ],
  "related": [("calculator.html","GHG Calculator"),("value-chain.html","Value-Chain / Supplier ESG"),
              ("learn.html","Carbon Literacy"),("brsr-reporting.html","BRSR Reporting Guide"),
              ("issb-ifrs-india.html","ISSB IFRS S1 / S2 Guide")],
},
{
  "slug": "issb-ifrs-india",
  "short": "ISSB IFRS S1/S2",
  "kicker": "Global Disclosure · ISSB",
  "title": "ISSB & IFRS S1/S2 Explained: What Indian Companies Need to Know | Green Curve",
  "h1": "ISSB and IFRS S1 / S2: A Guide for Indian Companies",
  "description": "What the ISSB is, how IFRS S1 and S2 sustainability disclosure standards work, how they build on TCFD, and why Indian exporters and subsidiaries should prepare even before any local mandate.",
  "keywords": "ISSB, IFRS S1, IFRS S2, ISSB standards India, sustainability disclosure standards, TCFD ISSB, IFRS sustainability, climate disclosure India, ISSB IFRS S2 climate",
  "intro": "The International Sustainability Standards Board (ISSB) has created a global baseline for sustainability and climate disclosure through IFRS S1 and IFRS S2. This guide explains what they require, how they relate to TCFD and BRSR, and what Indian companies should do now.",
  "sections": [
    {"id":"what","h2":"What is the ISSB?","html":
     "<p>The <strong>International Sustainability Standards Board (ISSB)</strong> was established by the IFRS Foundation at COP26 in November 2021 to create a global baseline of sustainability disclosures for capital markets. It consolidated several earlier frameworks (TCFD, SASB, CDSB, Integrated Reporting) into one standard-setter.</p>"},
    {"id":"standards","h2":"IFRS S1 and IFRS S2","html":
     "<p>The ISSB issued its first two standards in June 2023, effective for annual periods beginning on or after 1 January 2024:</p><ul>"
     "<li><strong>IFRS S1 — General Requirements:</strong> disclose all sustainability-related risks and opportunities that could affect a company's prospects, using the familiar governance / strategy / risk-management / metrics-and-targets structure.</li>"
     "<li><strong>IFRS S2 — Climate-related Disclosures:</strong> climate-specific requirements including Scope 1, 2 and 3 GHG emissions, transition plans, and scenario analysis.</li>"
     "</ul>"},
    {"id":"tcfd","h2":"How ISSB relates to TCFD","html":
     "<p>IFRS S2 fully incorporates the recommendations of the <a href='tcfd.html'>Task Force on Climate-related Financial Disclosures (TCFD)</a>. From 2024 the ISSB took over responsibility for monitoring climate-disclosure progress from the TCFD. In practice, a company already aligned to TCFD has a strong head start on IFRS S2.</p>"
     "<div class='callout'>Use the <a href='tcfd-checker.html'>free TCFD gap checker</a> to benchmark your current climate disclosures against the four pillars that underpin IFRS S2.</div>"},
    {"id":"india","h2":"Why this matters for Indian companies","html":
     "<p>India has not mandated IFRS S1/S2 domestically — SEBI's <a href='brsr-reporting.html'>BRSR</a> remains the local requirement, and it already overlaps substantially with ISSB on climate and governance. But ISSB matters for Indian companies that:</p><ul>"
     "<li>are <strong>subsidiaries</strong> of multinational groups reporting under ISSB;</li>"
     "<li><strong>export</strong> to markets adopting ISSB-based rules;</li>"
     "<li>seek <strong>global capital</strong> from investors using ISSB as the baseline.</li>"
     "</ul><p>Aligning BRSR data to ISSB concepts now reduces duplicate reporting later.</p>"},
  ],
  "cta": {"heading":"Check your climate-disclosure readiness",
          "text":"IFRS S2 is built on the four TCFD pillars. Run the free gap checker to see where your disclosures stand and what to fix first.",
          "url":"tcfd-checker.html","label":"Open the free TCFD gap checker"},
  "faqs": [
    ("What is the ISSB?","The International Sustainability Standards Board, set up by the IFRS Foundation in 2021 to create a global baseline of sustainability and climate disclosure standards for investors."),
    ("What is the difference between IFRS S1 and S2?","IFRS S1 sets general sustainability disclosure requirements across all topics; IFRS S2 is the climate-specific standard, covering GHG emissions, transition plans and scenario analysis."),
    ("Is ISSB mandatory in India?","Not currently. India's mandatory framework is SEBI's BRSR. ISSB still matters for Indian exporters, multinational subsidiaries, and companies raising global capital."),
    ("How does ISSB relate to TCFD?","IFRS S2 incorporates the TCFD recommendations in full, and the ISSB took over TCFD's monitoring role from 2024 — so TCFD alignment is the foundation for IFRS S2."),
    ("Does IFRS S2 require Scope 3?","Yes. IFRS S2 requires disclosure of Scope 1, 2 and material Scope 3 greenhouse-gas emissions."),
  ],
  "related": [("tcfd-checker.html","TCFD Gap Checker"),("tcfd.html","TCFD Disclosure Tracker"),
              ("scope-3-emissions.html","Scope 3 Emissions Guide"),("brsr-reporting.html","BRSR Reporting Guide"),
              ("learn.html","Carbon Literacy")],
},
{
  "slug": "carbon-credit-trading-scheme",
  "short": "CCTS (India)",
  "kicker": "Carbon Market · India",
  "title": "Carbon Credit Trading Scheme (CCTS) India: How the Carbon Market Works | Green Curve",
  "h1": "India's Carbon Credit Trading Scheme (CCTS) Explained",
  "description": "How India's Carbon Credit Trading Scheme works — the compliance and offset mechanisms, GEI targets, carbon credit certificates, the transition from PAT, and what obligated companies should do.",
  "keywords": "carbon credit trading scheme, CCTS India, Indian carbon market, carbon credit certificate, GEI target, PAT scheme transition, BEE carbon market, compliance carbon market India, offset mechanism",
  "intro": "The Carbon Credit Trading Scheme (CCTS) is India's framework for a national carbon market. This guide explains its compliance and offset mechanisms, how carbon credit certificates are earned and traded, and how it evolves from the earlier PAT energy-efficiency scheme.",
  "sections": [
    {"id":"what","h2":"What is the CCTS?","html":
     "<p>The <strong>Carbon Credit Trading Scheme (CCTS)</strong> establishes a national carbon market in India under the Energy Conservation (Amendment) Act, 2022. It is administered primarily by the <strong>Bureau of Energy Efficiency (BEE)</strong> with the Grid Controller of India as registry, under the Ministry of Power, and overseen by a National Steering Committee for the Indian Carbon Market.</p>"},
    {"id":"mechanisms","h2":"The two mechanisms","html":
     "<table class='gc'><thead><tr><th>Mechanism</th><th>How it works</th></tr></thead><tbody>"
     "<tr><td><strong>Compliance mechanism</strong></td><td>Notified energy-intensive sectors receive Greenhouse-gas Emission Intensity (GEI) targets. Beating the target earns Carbon Credit Certificates (CCCs); missing it requires buying CCCs to comply.</td></tr>"
     "<tr><td><strong>Offset mechanism</strong></td><td>Non-obligated entities can register voluntary projects that reduce or remove emissions and earn tradable CCCs.</td></tr>"
     "</tbody></table>"
     "<p>CCCs are traded on power exchanges under a market framework regulated by the CERC.</p>"},
    {"id":"pat","h2":"From PAT to CCTS","html":
     "<p>CCTS evolves from the long-running <strong>PAT (Perform, Achieve and Trade)</strong> energy-efficiency scheme. Where PAT issued Energy Saving Certificates against specific-energy-consumption targets, CCTS shifts the unit of account to <strong>emissions intensity</strong> and broadens participation — moving India from an efficiency-certificate market toward a true carbon market.</p>"},
    {"id":"prepare","h2":"What obligated companies should do","html":
     "<ol>"
     "<li><strong>Confirm whether your sector is notified</strong> for compliance obligations and note your baseline year.</li>"
     "<li><strong>Build a verified GHG inventory</strong> — accurate Scope 1 and 2 data is the basis of GEI targets.</li>"
     "<li><strong>Model your trajectory</strong> against likely targets to see if you are a buyer or seller of CCCs.</li>"
     "<li><strong>Plan abatement</strong> early — the cheapest credits are the emissions you avoid.</li>"
     "</ol>"},
  ],
  "cta": {"heading":"Track your CCTS compliance position",
          "text":"Green Curve's CCTS tracker helps obligated entities model GEI targets and certificate positions as India's carbon market ramps up.",
          "url":"ccts.html","label":"Open the CCTS compliance tracker"},
  "faqs": [
    ("What is the Carbon Credit Trading Scheme?","It is India's framework for a national carbon market, set up under the Energy Conservation (Amendment) Act 2022 and administered by the Bureau of Energy Efficiency, with compliance and offset mechanisms that trade Carbon Credit Certificates."),
    ("Who administers the Indian carbon market?","The Bureau of Energy Efficiency (BEE) under the Ministry of Power, with the Grid Controller of India as registry and oversight from the National Steering Committee for the Indian Carbon Market."),
    ("What is a Carbon Credit Certificate (CCC)?","A tradable certificate representing one tonne of CO2-equivalent. Obligated entities earn CCCs by beating their emission-intensity target, or buy them to meet it; voluntary projects earn them through the offset mechanism."),
    ("How is CCTS different from PAT?","PAT targeted specific energy consumption and issued Energy Saving Certificates; CCTS targets greenhouse-gas emission intensity and issues Carbon Credit Certificates, broadening into a full carbon market."),
    ("What is a GEI target?","A Greenhouse-gas Emission Intensity target — the emissions allowed per unit of output for an obligated entity under the CCTS compliance mechanism."),
  ],
  "related": [("ccts.html","CCTS Compliance Tracker"),("calculator.html","GHG Calculator"),
              ("scope-3-emissions.html","Scope 3 Emissions Guide"),("brsr-reporting.html","BRSR Reporting Guide"),
              ("esg-intelligence.html","ESG Quotient")],
},
]

if __name__ == "__main__":
    print(f"Generating {len(GUIDES)} pillar pages…")
    for g in GUIDES:
        out = render(g)
        with open(f"{g['slug']}.html", "w", encoding="utf-8") as f:
            f.write(out)
        print(f"  Written {g['slug']}.html ({len(out)//1024} KB)")
    print("Done. Run generate_company_pages.py to refresh the sitemap.")
