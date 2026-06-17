// ESG Financial Quotient Dashboard
// Reads assets/data/esg_quotient.json and renders all 4 panels

let INTEL = null;
let allCompanies = [];
const _tabRendered = new Set(); // tracks which tabs have been initialised at least once
let API_BASE = '';   // set dynamically from brsr-generator.js if available
let _SECTOR_AVG_CACHE = null;  // F-C: sector averages, computed once after data loads
let _FILING_TRACKER   = null;  // F-D: recent BSE BRSR filings
let _RECENT_FILERS    = new Set(); // F-D: company names with filings in the tracker period
let _scoreTrack       = 'standard'; // F-E: 'standard' | 'conservative'
let _SUPPLIER_RESPONSES = null;    // F-A: value-chain supplier form responses
let _GHG_ESTIMATES     = null;    // P4-A: ML-predicted GHG for non-disclosers
let _ESG_EVENTS        = null;    // P4-D: SEBI/BSE/NGT ESG event feed
let _capFilter         = 'all';   // P4-B: CAP active status filter
let _screenerData      = [];      // filtered+sorted screener rows (all pages)
let _screenerPage      = 0;       // current 0-based page index
const _SCREENER_PAGE_SIZE = 50;   // rows per page

// Try to read API_BASE from brsr-generator config (set by start_brsr.py)
try {
  // Resolved by gc-config.js: localStorage override else same-origin '/gcai'.
  API_BASE = window._gcApiBase || localStorage.getItem('gc_api_base') || '';
} catch(e) {}

// Allow brsr-generator.js to share its API_BASE
window.setIntelApiBase = (url) => { API_BASE = url; localStorage.setItem('gc_api_base', url); };

// ── AI feedback widget (thumbs up/down) ─────────────────────────────────────
function _gcAiFeedback(container, aiType, companyName) {
  if (!container) return;
  if (container.querySelector('.gc-ai-feedback')) return;
  const widget = document.createElement('div');
  widget.className = 'gc-ai-feedback';
  widget.style.cssText = 'margin-top:14px;display:flex;align-items:center;gap:10px;font-size:.78rem;color:rgba(226,232,240,.5);border-top:1px solid rgba(255,255,255,.06);padding-top:12px';
  widget.innerHTML = `
    <span>Was this analysis helpful?</span>
    <button class="gc-fb-btn" data-v="1" title="Yes, helpful" style="background:rgba(52,211,153,.1);border:1px solid rgba(52,211,153,.2);color:#34d399;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:.8rem">👍</button>
    <button class="gc-fb-btn" data-v="0" title="Needs improvement" style="background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);color:rgba(226,232,240,.5);padding:4px 10px;border-radius:6px;cursor:pointer;font-size:.8rem">👎</button>
  `;
  widget.querySelectorAll('.gc-fb-btn').forEach(btn => {
    btn.addEventListener('click', function () {
      const v = parseInt(this.dataset.v);
      fetch((API_BASE || '') + '/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ai_type: aiType, company: companyName, helpful: v }),
      }).catch(() => {});
      widget.innerHTML = '<span style="color:#34d399">Thanks for the feedback!</span>';
    }, { once: true });
  });
  container.appendChild(widget);
}

const MATERIAL_ICONS = {
  plastic: '🧴', 'e-waste': '💻', battery: '🔋',
  tyres: '⚙️', chemicals: '⚗️', steel: '🔩', water: '💧', carbon: '🌫️',
};

// ── Shared sector name cleaner (NIC codes → readable names) ──────────────────
const _NIC_MAP = {
  '62011':'Software development','62012':'Software development','62013':'Software development',
  '62099':'IT & software services','62090':'IT & computer services','62021':'IT consulting',
  '64191':'Banking','64192':'Banking','64990':'Financial services','65110':'Life insurance',
  '65120':'Non-life insurance','66190':'Financial services aux','66110':'Fund management',
  '24101':'Iron & steel','24102':'Iron & steel','24103':'Iron & steel','24200':'Steel tubes & pipes',
  '24311':'Precious metals','25910':'Metal containers','25930':'Fasteners & screws',
  '20111':'Industrial gases','20112':'Dyes & pigments','20113':'Specialty chemicals',
  '20211':'Pesticides','20221':'Paints & coatings','20231':'Soap & detergents',
  '20291':'Other chemicals','21001':'Pharmaceuticals','21002':'Pharmaceuticals',
  '26101':'Electronic components','26102':'Electronic components','26301':'Telecom equipment',
  '35101':'Electricity generation','35102':'Electricity transmission','35201':'Gas supply',
  '41001':'Construction','41002':'Construction','42101':'Roads & highways',
  '45101':'Motor vehicles wholesale','45201':'Motor vehicle repair',
  '46100':'Wholesale trade','47110':'Retail — food','47190':'Retail — general',
  '55101':'Hotels','56101':'Restaurants',
  '61100':'Telecom — wired','61200':'Telecom — wireless','61300':'Satellite telecom',
  '68100':'Real estate','68200':'Rental of real estate',
  '72100':'R&D natural sciences','73100':'Advertising',
  '10101':'Processed meat','10201':'Fish processing','10301':'Fruit & veg processing',
  '10411':'Edible oils','10501':'Dairy products','10611':'Grain milling',
  '13111':'Cotton yarn spinning','13121':'Weaving','13941':'Cordage & ropes',
  '14101':'Wearing apparel','15121':'Footwear',
  '16101':'Sawmilling','17011':'Pulp','17012':'Paper','17021':'Paperboard',
  '22111':'Rubber tyres','22192':'Other rubber products','22210':'Plastic products',
  '23101':'Glass','23910':'Abrasives','23921':'Cement','23931':'Cement products',
  '27101':'Electric motors','27102':'Batteries','27201':'Lighting equipment',
  '28111':'Engines & turbines','28121':'Pumps & compressors','28131':'Taps & valves',
  '29101':'Motor vehicles','29102':'Motor vehicle parts','30111':'Ships','31001':'Furniture',
};

function _cleanSector(s) {
  const raw = (s || '').replace('Manufacturing — ', '').trim();
  // Pure NIC code (3-6 digits)
  if (/^\d{3,6}$/.test(raw)) return _NIC_MAP[raw] || `NIC ${raw}`;
  // "64920 - Description" format — extract code first
  const m = raw.match(/^(\d{4,6})\s*[-–]\s*/);
  if (m) return _NIC_MAP[m[1]] || raw.replace(m[0], '').trim().slice(0, 45);
  // Product descriptions (start with number+period or long plain-English phrases)
  if (/^\d+\./.test(raw) || raw.length > 55) return raw.slice(0, 45).trim() + '…';
  return raw;
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function initDashboard() {
  const statusEl = document.getElementById('heroMeta');
  try {
    // Fetch ESG data from DB API; fall back to static JSON if API returns empty.
    // Other files still served statically (small, rarely change).
    const _cv = new Date().toISOString().slice(0, 10);
    const [res, ftRes, srRes, ghgRes, evRes] = await Promise.all([
      fetch('/api/esg/data'),
      fetch('assets/data/filing_tracker.json?v='      + _cv).catch(() => null),
      fetch('assets/data/supplier_responses.json?v='  + _cv).catch(() => null),
      fetch('assets/data/ghg_estimates.json?v='       + _cv).catch(() => null),
      fetch('assets/data/esg_events.json?v='          + _cv).catch(() => null),
    ]);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    INTEL = await res.json();
    allCompanies = INTEL.companies || [];

    // Load filing tracker (non-fatal if missing)
    if (ftRes && ftRes.ok) {
      try {
        _FILING_TRACKER = await ftRes.json();
        (_FILING_TRACKER.recent_filings || []).forEach(f => {
          if (f.company_name) _RECENT_FILERS.add(f.company_name);
        });
      } catch { _FILING_TRACKER = null; }
    }

    // F-A: Load supplier responses (non-fatal if missing)
    if (srRes && srRes.ok) {
      try { _SUPPLIER_RESPONSES = await srRes.json(); } catch { _SUPPLIER_RESPONSES = null; }
    }

    // P4-A: Load ML GHG estimates (non-fatal if missing)
    if (ghgRes && ghgRes.ok) {
      try {
        const ghgJson = await ghgRes.json();
        _GHG_ESTIMATES = ghgJson.estimates || {};
        // Staleness warning: flag if data is older than stale_after_days
        const genAt  = ghgJson.generated_at ? new Date(ghgJson.generated_at) : null;
        const staleDays = ghgJson.stale_after_days || 7;
        if (genAt && (Date.now() - genAt.getTime()) > staleDays * 86400_000) {
          console.warn('[GreenCurve] ghg_estimates.json is stale (generated', ghgJson.data_last_updated || 'unknown', '). Re-run predict_ghg.py.');
        }
      } catch { _GHG_ESTIMATES = null; }
    }

    // P4-D: Load ESG event feed (non-fatal if missing)
    if (evRes && evRes.ok) {
      try { _ESG_EVENTS = await evRes.json(); } catch { _ESG_EVENTS = null; }
    }

    // Auth: pre-load watchlist, snapshots, prefs, CAP from server (non-fatal)
    if (typeof gcAuth !== 'undefined' && gcAuth.isLoggedIn()) {
      try {
        const [wlData, snapData, prefsData, capData] = await Promise.all([
          gcAuth.getWatchlist().catch(() => []),
          gcAuth.getSnapshots().catch(() => ({})),
          gcAuth.getPrefs().catch(() => ({ tier_change: true, high_risk: true })),
          gcAuth.getCAP().catch(() => ({})),
        ]);
        _WL._names = wlData || [];
        _WL._snaps = snapData || {};
        _WL._prefs = prefsData || { tier_change: true, high_risk: true };
        // CAP cache: server returns { companyName: { recId: {...} } }
        // Flatten each company's map into _CAP_CACHE
        _CAP_CACHE = capData || {};
      } catch (e) {
        console.warn('[GC] user data pre-load failed:', e.message);
      }

      // Admin banner: check if ANTHROPIC_API_KEY is missing on server
      try {
        const user = gcAuth.getUser();
        if (user && user.role === 'admin') {
          const healthRes = await fetch((API_BASE || '') + '/health').catch(() => null);
          if (healthRes && healthRes.ok) {
            const health = await healthRes.json();
            if (!health.anthropic_configured) {
              const banner = document.createElement('div');
              banner.style.cssText = 'position:sticky;top:0;z-index:8000;background:#7c1d1d;color:#fca5a5;padding:10px 20px;font-size:.82rem;font-family:"DM Sans",sans-serif;display:flex;align-items:center;gap:12px';
              banner.innerHTML = '<strong>⚠ Admin:</strong> <span>ANTHROPIC_API_KEY is not set on the server — AI features (CCTS, TCFD, digest) will fail. Add it to <code style="font-size:.78rem">/opt/greencurve/.env</code> and restart the service.</span><button onclick="this.parentNode.remove()" style="margin-left:auto;background:none;border:none;color:#fca5a5;font-size:1rem;cursor:pointer">✕</button>';
              document.body.prepend(banner);
            }
          }
        }
      } catch { /* non-fatal */ }
    }

    const s = INTEL.summary || {};
    statusEl.textContent = INTEL.data_as_of || '—';

    // populate hero stat badges
    const hrEl = document.getElementById('heroHighRisk');
    if (hrEl) hrEl.textContent = (s.high_risk_companies || s.high_risk_count || s.risk_distribution?.High || '—');

    const _s = (fn, label) => { try { fn(); } catch(e) { console.warn('[GC]', label, 'failed:', e.message); } };
    _s(() => renderKPIs(s),           'renderKPIs');
    _s(addAssuranceKPIStat,           'assuranceKPI');
    _s(renderScreener,                'renderScreener');
    _s(populateSectorDropdown,        'sectorDropdown');
    document.querySelectorAll('.th-sort').forEach(th => {
      th.addEventListener('click', () => setColSort(th.dataset.col));
    });
    _s(renderRegulations,             'regulations');
    _s(renderTargets,                 'targets');
    _s(renderMaterials,               'materials');
    _s(renderCalendar,                'calendar');
    _s(renderAnomalies,               'anomalies');
    _s(checkAlerts,                   'checkAlerts');
    _s(renderSpotlight,               'spotlight');
    const dmTitle = document.getElementById('dmChartTitle');
    if (dmTitle) dmTitle.textContent = `Double Materiality Matrix — All ${allCompanies.length} Companies`;

    // The Overview charts, Double Materiality matrix, and Supply Chain charts
    // are all drawn with Plotly, which is lazy-loaded on the first chart-tab
    // click. But these render eagerly here (Overview is the default tab; the
    // others aren't wired into the lazy chart-tab path), so they were drawing
    // blank. Trigger the Plotly load now and draw them once it is ready.
    const _renderPlotlyTabs = () => {
      _s(renderCharts,            'renderCharts');
      _s(renderDoubleMateriality, 'doubleMateriality');
      _s(renderSupplyChain,       'supplyChain');
    };
    if (typeof _ensurePlotly === 'function') _ensurePlotly(_renderPlotlyTabs);
    else _renderPlotlyTabs();

    // Remaining tabs render lazily on first click — nothing else eager here.
    // _tabRendered tracks which tabs have been initialised; see tab click handler in HTML.

    // Honour deep-links (#tab + ?company=) now that data is loaded so the target
    // tool can render and pre-filter to the requested company.
    if (typeof window.__applyDeepLink === 'function') {
      try { window.__applyDeepLink(); } catch (e) { console.warn('[GC] deep-link apply failed:', e.message); }
    }
  } catch (e) {
    statusEl.textContent = 'Load error: ' + e.message.slice(0, 80);
    console.error('[GC] initDashboard FAILED:', e);
    renderPlaceholder();
  }
}

function renderSpotlight() {
  const grid = document.getElementById('spotlightGrid');
  if (!grid || !allCompanies.length) return;
  const leaders = allCompanies
    .filter(c => c.risk_tier === 'Low' && c.esg_risk_score != null)
    .sort((a, b) => a.esg_risk_score - b.esg_risk_score)
    .slice(0, 6);
  if (!leaders.length) { document.getElementById('gcSpotlight').style.display = 'none'; return; }
  grid.innerHTML = leaders.map(c => `
    <div class="gc-spotlight__card" onclick="openDeepDive('${(c.company_name||'').replace(/'/g,"\\'")}')">
      <div class="gc-spotlight__company" title="${c.company_name||''}">${c.company_name||'—'}</div>
      <div class="gc-spotlight__sector" title="${_cleanSector(c.sector)||''}">${_cleanSector(c.sector)||'—'}</div>
      <div class="gc-spotlight__score-row">
        <div class="gc-spotlight__score">${c.esg_risk_score.toFixed(1)}</div>
        <span class="gc-spotlight__badge">Low Risk</span>
      </div>
    </div>`).join('');
}

function renderPlaceholder() {
  document.getElementById('kpiGrid').innerHTML = `
    <div class="kpi-card" style="grid-column:1/-1;text-align:center;padding:40px">
      <p style="color:#94a3b8;font-size:.95rem">Intelligence data is generated nightly.<br>Check back after 2 AM or run the CPCB agent manually.</p>
    </div>`;
}

// ── KPI cards ─────────────────────────────────────────────────────────────────
function renderKPIs(s) {
  const kpis = [
    { value: s.total_companies || 0,        label: 'Companies Analysed',       cls: '' },
    { value: s.high_risk_companies || 0,    label: 'High Risk Companies',       cls: 'kpi-card__value--red' },
    { value: s.medium_risk_companies || 0,  label: 'Medium Risk',               cls: 'kpi-card__value--amber' },
    { value: s.low_risk_companies || 0,     label: 'Low Risk',                  cls: 'kpi-card__value--green' },
    { value: s.regulations_analysed || 0,   label: 'Regulations Tracked',       cls: '' },
    { value: s.high_impact_regulations || 0,label: 'High-Impact Rules',         cls: 'kpi-card__value--red' },
    { value: (s.avg_esg_risk_score || 0).toFixed(1), label: 'Avg ESG Risk Score', cls: '' },
  ];
  document.getElementById('kpiGrid').innerHTML = kpis.map(k => `
    <div class="kpi-card">
      <div class="kpi-card__value ${k.cls}">${k.value}</div>
      <div class="kpi-card__label">${k.label}</div>
    </div>`).join('');
}

function addAssuranceKPIStat() {
  const grid = document.getElementById('kpiGrid');
  if (!grid || !allCompanies.length) return;
  const assuredCount = allCompanies.filter(c => (c.governance?.brsr_assurance||'None') !== 'None').length;
  const fullCovCount = allCompanies.filter(c => _dcCoverage(c).pct >= 57).length; // 4+ of 7 key fields

  // F-E: portfolio conservative score average
  const conservScores = allCompanies.map(c => getConservativeScore(c).conservative).filter(v => v != null);
  const avgConservScore = conservScores.length
    ? (conservScores.reduce((a, b) => a + b, 0) / conservScores.length).toFixed(1)
    : '—';
  const stdScores  = allCompanies.map(c => c.esg_risk_score).filter(v => v != null);
  const avgStdScore = stdScores.length
    ? (stdScores.reduce((a, b) => a + b, 0) / stdScores.length).toFixed(1)
    : '—';

  grid.insertAdjacentHTML('beforeend', `
    <div class="kpi-card">
      <div class="kpi-card__value kpi-card__value--green">${assuredCount}</div>
      <div class="kpi-card__label">BRSR Core Assured</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-card__value">${fullCovCount}</div>
      <div class="kpi-card__label">High Data Coverage</div>
    </div>
    <div class="kpi-card" title="Standard avg: ${avgStdScore} vs Conservative (confidence-adjusted) avg: ${avgConservScore}">
      <div class="kpi-card__value">${avgStdScore} <span style="font-size:.85rem;color:#818cf8">→ ${avgConservScore}</span></div>
      <div class="kpi-card__label">Avg Score: Std → Conservative</div>
    </div>
  `);
}

// ── Charts ─────────────────────────────────────────────────────────────────────
function renderCharts() {
  if (typeof Plotly === 'undefined') { console.warn('[GC] Plotly not loaded — charts skipped'); return; }
  renderSectorRiskChart();
  renderFactorsChart();
  renderRegImpactChart();
  renderMaterialsChart();
}

function renderSectorRiskChart() {
  const sector_map = {};
  allCompanies.forEach(c => {
    const sec = (c.sector || 'Other').slice(0, 35);
    if (!sector_map[sec]) sector_map[sec] = [];
    sector_map[sec].push(c.esg_risk_score);
  });
  const entries = Object.entries(sector_map)
    .map(([s, scores]) => ({ sector: s, avg: scores.reduce((a,b) => a+b,0)/scores.length }))
    .filter(e => e.sector && e.sector !== 'Other')
    .sort((a,b) => b.avg - a.avg)
    .slice(0, 12);

  Plotly.newPlot('chartSectorRisk', [{
    type: 'bar', orientation: 'h',
    x: entries.map(e => +e.avg.toFixed(1)),
    y: entries.map(e => e.sector.replace('Manufacturing — ', '')),
    marker: { color: entries.map(e => e.avg >= 6.5 ? 'rgba(248,113,113,.75)' : e.avg >= 4 ? 'rgba(251,191,36,.75)' : 'rgba(52,211,153,.75)'), line: { width: 0 } },
    hovertemplate: '<b>%{y}</b><br>Avg ESG Risk: %{x:.1f}/10<extra></extra>',
  }], {
    paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
    font: { color: '#94a3b8', family: 'DM Sans, sans-serif', size: 11 },
    xaxis: { range: [0, 10], gridcolor: 'rgba(255,255,255,.05)', tickfont: { color: '#94a3b8' } },
    yaxis: { gridcolor: 'transparent', tickfont: { color: '#cbd5e1', size: 11 }, automargin: true },
    margin: { l: 10, r: 20, t: 10, b: 40 }, height: 280,
  }, { displayModeBar: false, responsive: true });
}

function renderFactorsChart() {
  const factors = INTEL.factor_matrix?.factors || {};
  const labels = Object.values(factors).map(f => f.label);
  const scores = labels.map((_, i) => {
    const f = Object.values(factors)[i];
    const vals = Object.values(f.sector_risk || {});
    return vals.length ? (vals.reduce((a,b)=>a+b,0)/vals.length).toFixed(1) : 5;
  });

  Plotly.newPlot('chartFactors', [{
    type: 'scatterpolar',
    r: [...scores, scores[0]],
    theta: [...labels, labels[0]],
    fill: 'toself',
    fillcolor: 'rgba(99,102,241,.2)',
    line: { color: 'rgba(99,102,241,.8)' },
    marker: { color: '#818cf8', size: 4 },
    hovertemplate: '<b>%{theta}</b><br>Risk: %{r:.1f}/10<extra></extra>',
  }], {
    paper_bgcolor: 'transparent',
    font: { color: '#94a3b8', family: 'DM Sans, sans-serif', size: 11 },
    polar: {
      radialaxis: { visible: true, range: [0, 10], gridcolor: 'rgba(255,255,255,.07)', tickfont: { color: '#94a3b8', size: 9 } },
      angularaxis: { tickfont: { color: '#cbd5e1', size: 11 }, gridcolor: 'rgba(255,255,255,.07)' },
      bgcolor: 'transparent',
    },
    showlegend: false,
    margin: { l: 40, r: 40, t: 40, b: 40 }, height: 280,
  }, { displayModeBar: false, responsive: true });
}

function renderRegImpactChart() {
  const regs = (INTEL.regulations || []).slice(0, 15).reverse();
  Plotly.newPlot('chartRegImpact', [{
    type: 'bar', orientation: 'h',
    x: regs.map(r => r.impact_score || 0),
    y: regs.map(r => (r.title || '').slice(0, 40) + (r.title?.length > 40 ? '…' : '')),
    marker: { color: regs.map(r => r.urgency === 'High' ? 'rgba(248,113,113,.75)' : r.urgency === 'Medium' ? 'rgba(251,191,36,.75)' : 'rgba(52,211,153,.75)'), line: { width: 0 } },
    hovertemplate: '<b>%{y}</b><br>Impact Score: %{x:.1f}/10<extra></extra>',
  }], {
    paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
    font: { color: '#94a3b8', family: 'DM Sans, sans-serif', size: 10 },
    xaxis: { range: [0, 10], gridcolor: 'rgba(255,255,255,.05)', tickfont: { color: '#94a3b8' } },
    yaxis: { gridcolor: 'transparent', tickfont: { color: '#94a3b8', size: 10 }, automargin: true },
    margin: { l: 10, r: 20, t: 10, b: 40 }, height: 260,
  }, { displayModeBar: false, responsive: true });
}

function renderMaterialsChart() {
  const freq = INTEL.factor_matrix?.material_frequency || {};
  const entries = Object.entries(freq).sort((a,b) => b[1]-a[1]).slice(0, 8);
  Plotly.newPlot('chartMaterials', [{
    type: 'pie', hole: 0.4,
    labels: entries.map(([k]) => k.charAt(0).toUpperCase() + k.slice(1)),
    values: entries.map(([,v]) => v),
    marker: { colors: ['#10b981','#6366f1','#f59e0b','#f87171','#38bdf8','#a78bfa','#34d399','#fb923c'] },
    hovertemplate: '<b>%{label}</b><br>%{value} companies (%{percent})<extra></extra>',
    textinfo: 'label+percent',
    textfont: { size: 10, color: '#cbd5e1' },
  }], {
    paper_bgcolor: 'transparent',
    font: { color: '#94a3b8', family: 'DM Sans, sans-serif', size: 11 },
    showlegend: false,
    margin: { l: 10, r: 10, t: 10, b: 10 }, height: 260,
  }, { displayModeBar: false, responsive: true });
}

// ── Company Screener ──────────────────────────────────────────────────────────
// ── Column sort state ─────────────────────────────────────────────────────────
const colSort = { col: 'esg_risk_score', dir: 'desc' };

function setColSort(col) {
  if (colSort.col === col) colSort.dir = colSort.dir === 'desc' ? 'asc' : 'desc';
  else { colSort.col = col; colSort.dir = 'desc'; }
  // Update all sort icons
  document.querySelectorAll('.sort-icon').forEach(el => el.textContent = '↕');
  document.querySelectorAll('.th-sort').forEach(el => el.classList.remove('th-sort--asc','th-sort--desc'));
  const icon = document.getElementById('si-' + col);
  const th   = document.querySelector(`.th-sort[data-col="${col}"]`);
  if (icon) icon.textContent = colSort.dir === 'desc' ? '↓' : '↑';
  if (th) th.classList.add(colSort.dir === 'desc' ? 'th-sort--desc' : 'th-sort--asc');
  applyColFilters();
}

// ── Populate sector dropdown ──────────────────────────────────────────────────
function populateSectorDropdown() {
  const sel = document.getElementById('cf-sector');
  if (!sel || sel.options.length > 1) return;

  // Count frequency of each sector value
  const freq = {};
  allCompanies.forEach(c => {
    const raw = (c.sector || '').replace('Manufacturing — ', '').trim();
    if (raw) freq[raw] = (freq[raw] || 0) + 1;
  });

  const sectors = Object.entries(freq)
    .filter(([s, count]) =>
      count >= 2 &&          // must appear on 2+ companies
      /^[A-Za-z]/.test(s) && // must start with a letter
      s.length <= 50 &&      // no long descriptions
      !/\b(is a|includes|delivers|manufactures|project|portfolio|leading|supplier|services|provides)\b/i.test(s)
    )
    .map(([s]) => s)
    .sort();

  sectors.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s;
    opt.textContent = s.length > 42 ? s.slice(0, 40) + '…' : s;
    sel.appendChild(opt);
  });
}

// ── Column filters ────────────────────────────────────────────────────────────
// ── Pre-built Screener Templates ───────────────────────────────────────────────
const SCREENER_TEMPLATES = [
  { name: 'High GHG',                ghgMin: 7 },
  { name: 'High Water Risk',         waterMin: 7 },
  { name: 'EPR Exposed',             eprMin: 7 },
  { name: 'Compliance Lag',          compMin: 7 },
  { name: 'Large-Cap High Risk',     riskTier: 'High', revMin: 5000 },
  { name: 'Chemicals Sector',        topSearch: 'chemical' },
  { name: 'Green Leaders',           riskTier: 'Low', revMin: 1000 },
  { name: 'Positive Return Low Risk',retDir: 'pos', riskTier: 'Low' },
  { name: 'BRSR Core Assured',       confidence: 'assured' },
];

function applyTemplate(idx) {
  const tmpl = SCREENER_TEMPLATES[idx];
  if (!tmpl) return;

  // Highlight active pill
  document.querySelectorAll('.st-pill[data-tmpl]').forEach(b => b.classList.toggle('st-pill--active', Number(b.dataset.tmpl) === idx));

  // Clear all filter inputs first
  ['cf-company','cf-ghg','cf-water','cf-epr','cf-comp','cf-rev-min','cf-cap-min'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
  ['cf-sector','cf-risk-tier','cf-return','screenerSearch','screenerRisk'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });

  // Apply template values to DOM inputs
  if (tmpl.ghgMin)     { const el = document.getElementById('cf-ghg');      if (el) el.value = tmpl.ghgMin; }
  if (tmpl.waterMin)   { const el = document.getElementById('cf-water');    if (el) el.value = tmpl.waterMin; }
  if (tmpl.eprMin)     { const el = document.getElementById('cf-epr');      if (el) el.value = tmpl.eprMin; }
  if (tmpl.compMin)    { const el = document.getElementById('cf-comp');     if (el) el.value = tmpl.compMin; }
  if (tmpl.revMin)     { const el = document.getElementById('cf-rev-min');  if (el) el.value = tmpl.revMin; }
  if (tmpl.riskTier)   { const el = document.getElementById('cf-risk-tier'); if (el) el.value = tmpl.riskTier; }
  if (tmpl.retDir)     { const el = document.getElementById('cf-return');       if (el) el.value = tmpl.retDir; }
  if (tmpl.confidence) { const el = document.getElementById('cf-confidence');   if (el) el.value = tmpl.confidence; }
  if (tmpl.topSearch)  { const el = document.getElementById('screenerSearch');  if (el) el.value = tmpl.topSearch; }

  applyColFilters(false);
}

function clearTemplate() {
  document.querySelectorAll('.st-pill[data-tmpl]').forEach(b => b.classList.remove('st-pill--active'));
  resetColFilters();
}
window.applyTemplate = applyTemplate;
window.clearTemplate = clearTemplate;

function applyColFilters(clearActiveTmpl) {
  if (clearActiveTmpl !== false) {
    document.querySelectorAll('.st-pill[data-tmpl]').forEach(b => b.classList.remove('st-pill--active'));
  }
  const company  = (document.getElementById('cf-company')?.value  || '').toLowerCase();
  const sector   = document.getElementById('cf-sector')?.value   || '';
  const riskTier = document.getElementById('cf-risk-tier')?.value || '';
  const ghgMin   = Number(document.getElementById('cf-ghg')?.value   || 0);
  const waterMin = Number(document.getElementById('cf-water')?.value || 0);
  const eprMin   = Number(document.getElementById('cf-epr')?.value   || 0);
  const compMin  = Number(document.getElementById('cf-comp')?.value  || 0);
  const revMin   = Number(document.getElementById('cf-rev-min')?.value || 0);
  const capMin   = Number(document.getElementById('cf-cap-min')?.value || 0);
  const retDir    = document.getElementById('cf-return')?.value || '';
  const confidence = document.getElementById('cf-confidence')?.value || '';
  // Also sync legacy top-bar filters
  const topSearch = (document.getElementById('screenerSearch')?.value || '').toLowerCase();

  renderScreener('', '', '', {
    company, sector, riskTier, ghgMin, waterMin, eprMin, compMin, revMin, capMin, retDir, confidence, topSearch
  });
}

function resetColFilters() {
  ['cf-company','cf-ghg','cf-water','cf-epr','cf-comp','cf-rev-min','cf-cap-min'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  ['cf-sector','cf-risk-tier','cf-return','cf-confidence'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  // Also reset legacy top-bar
  const ss = document.getElementById('screenerSearch');
  const sr = document.getElementById('screenerRisk');
  if (ss) ss.value = '';
  if (sr) sr.value = '';
  colSort.col = 'esg_risk_score'; colSort.dir = 'desc';
  document.querySelectorAll('.sort-icon').forEach(el => el.textContent = '↕');
  document.querySelectorAll('.th-sort').forEach(el => el.classList.remove('th-sort--asc','th-sort--desc'));
  renderScreener();
}
window.applyColFilters  = applyColFilters;
window.resetColFilters  = resetColFilters;
window.setColSort       = setColSort;

function exportScreenerCSV() {
  if (!_screenerData.length) return;
  const cols = [
    ['Company',        c => c.company_name || ''],
    ['CIN',            c => c.cin || ''],
    ['Sector',         c => (c.sector||'').replace('Manufacturing — ','')],
    ['ESG Risk Score', c => c.esg_risk_score ?? ''],
    ['Risk Tier',      c => c.risk_tier || ''],
    ['GHG Intensity',  c => c.risk_breakdown?.ghg_intensity ?? ''],
    ['Water Intensity',c => c.risk_breakdown?.water_intensity ?? ''],
    ['EPR Exposure',   c => c.risk_breakdown?.epr_exposure ?? ''],
    ['Compliance Risk',c => c.risk_breakdown?.compliance_risk ?? ''],
    ['Revenue (₹Cr)',  c => c.revenue_crore ?? ''],
    ['Market Cap (₹Cr)',c=> c.market_data?.market_cap_crore ?? ''],
    ['1Y Return %',    c => c.market_data?.return_1y_pct ?? ''],
    ['BRSR Assurance', c => c.governance?.brsr_assurance || 'None'],
  ];
  const header = cols.map(([h]) => `"${h}"`).join(',');
  const rows   = _screenerData.map(c =>
    cols.map(([, fn]) => {
      const v = fn(c);
      return typeof v === 'string' ? `"${v.replace(/"/g, '""')}"` : v;
    }).join(',')
  );
  const csv  = [header, ...rows].join('\n');
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
  const a    = document.createElement('a');
  a.href     = URL.createObjectURL(blob);
  a.download = `GreenCurve_Screener_${new Date().toISOString().slice(0,10)}.csv`;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); document.body.removeChild(a); }, 1000);
}
window.exportScreenerCSV = exportScreenerCSV;

function toggleScoreTrack() {
  _scoreTrack = _scoreTrack === 'standard' ? 'conservative' : 'standard';
  const btn = document.getElementById('scoreTrackBtn');
  if (btn) {
    btn.textContent = _scoreTrack === 'standard' ? '⚖ Standard Score' : '🔒 Conservative Score';
    btn.classList.toggle('stc-btn--active', _scoreTrack === 'conservative');
  }
  const th = document.getElementById('th-esg-risk');
  if (th) th.title = _scoreTrack === 'conservative'
    ? 'Conservative score: confidence-weighted blend with sector average'
    : 'Standard ESG risk score (all public data)';
  applyColFilters(false);
}
window.toggleScoreTrack = toggleScoreTrack;

function renderScreener(filter = '', risk = '', sort = '', colFilters = null) {
  let data = [...allCompanies];

  // Legacy top-bar filters (kept for backwards compat)
  const f = colFilters?.topSearch || filter.toLowerCase();
  if (f) data = data.filter(c =>
    (c.company_name||'').toLowerCase().includes(f) ||
    (c.sector||'').toLowerCase().includes(f)
  );

  const rt = colFilters?.riskTier || risk;
  if (rt) data = data.filter(c => c.risk_tier === rt);

  // Column filters
  if (colFilters) {
    if (colFilters.company)  data = data.filter(c => (c.company_name||'').toLowerCase().includes(colFilters.company));
    if (colFilters.sector)   data = data.filter(c => (c.sector||'').replace('Manufacturing — ','').trim() === colFilters.sector);
    if (colFilters.ghgMin)   data = data.filter(c => (c.risk_breakdown?.ghg_intensity||0)   >= colFilters.ghgMin);
    if (colFilters.waterMin) data = data.filter(c => (c.risk_breakdown?.water_intensity||0) >= colFilters.waterMin);
    if (colFilters.eprMin)   data = data.filter(c => (c.risk_breakdown?.epr_exposure||0)    >= colFilters.eprMin);
    if (colFilters.compMin)  data = data.filter(c => (c.risk_breakdown?.compliance_risk||0) >= colFilters.compMin);
    if (colFilters.revMin)   data = data.filter(c => (c.revenue_crore||0) >= colFilters.revMin);
    if (colFilters.capMin)   data = data.filter(c => (c.market_data?.market_cap_crore||0)   >= colFilters.capMin);
    if (colFilters.retDir === 'pos') data = data.filter(c => (c.market_data?.return_1y_pct||0) >= 0);
    if (colFilters.retDir === 'neg') data = data.filter(c => (c.market_data?.return_1y_pct||0) < 0);
    if (colFilters.confidence === 'assured')  data = data.filter(c => (c.governance?.brsr_assurance||'None') !== 'None');
    if (colFilters.confidence === 'reported') data = data.filter(c => _dcCoverage(c).pct >= 57);   // 4+ of 7 fields
    if (colFilters.confidence === 'partial')  data = data.filter(c => { const v = _dcCoverage(c).pct; return v > 0 && v < 57; });
    if (colFilters.confidence === 'missing')  data = data.filter(c => _dcCoverage(c).pct === 0);
  }

  // Sort — column header sort takes priority
  const sortCol = colSort.col;
  const sortDir = colSort.dir === 'desc' ? -1 : 1;
  data.sort((a, b) => {
    let va, vb;
    switch (sortCol) {
      case 'company_name':   va = a.company_name||''; vb = b.company_name||''; return va.localeCompare(vb) * sortDir;
      case 'sector':         va = a.sector||'';       vb = b.sector||'';       return va.localeCompare(vb) * sortDir;
      case 'esg_risk_score': va = a.esg_risk_score||0; vb = b.esg_risk_score||0; break;
      case 'ghg':            va = a.risk_breakdown?.ghg_intensity||0;   vb = b.risk_breakdown?.ghg_intensity||0;   break;
      case 'water':          va = a.risk_breakdown?.water_intensity||0; vb = b.risk_breakdown?.water_intensity||0; break;
      case 'epr':            va = a.risk_breakdown?.epr_exposure||0;    vb = b.risk_breakdown?.epr_exposure||0;    break;
      case 'compliance':     va = a.risk_breakdown?.compliance_risk||0; vb = b.risk_breakdown?.compliance_risk||0; break;
      case 'revenue_crore':  va = a.revenue_crore||0;                   vb = b.revenue_crore||0;                   break;
      case 'market_cap':     va = a.market_data?.market_cap_crore||0;   vb = b.market_data?.market_cap_crore||0;   break;
      case 'return_1y':      va = a.market_data?.return_1y_pct??-999;   vb = b.market_data?.return_1y_pct??-999;   break;
      default:               va = a.esg_risk_score||0; vb = b.esg_risk_score||0;
    }
    return (vb - va) * sortDir;
  });

  _screenerData = data;
  _screenerPage = 0;
  document.getElementById('screenerCount').textContent = `${data.length} companies`;
  _renderScreenerPage(0);
}

function _renderScreenerPage(page) {
  _screenerPage = page;
  const isLoggedIn = typeof gcAuth !== 'undefined' && gcAuth.isLoggedIn();
  const _GUEST_LIMIT = 10;

  // Gate: guest users see first 10 rows only
  const start = page * _SCREENER_PAGE_SIZE;
  let slice = _screenerData.slice(start, start + _SCREENER_PAGE_SIZE);
  let gated  = false;
  if (!isLoggedIn && start === 0 && _screenerData.length > _GUEST_LIMIT) {
    slice  = slice.slice(0, _GUEST_LIMIT);
    gated  = true;
  }

  const tbody = document.getElementById('screenerBody');
  tbody.innerHTML = slice.map(c => {
    const rb = c.risk_breakdown || {};
    const md = c.market_data || {};
    const ret = md.return_1y_pct;
    const retHtml = ret != null
      ? `<span style="color:${ret >= 0 ? '#10b981' : '#f87171'}">${ret >= 0 ? '+' : ''}${ret}%</span>`
      : '<span style="color:#475569">N/A</span>';
    const inCmp = compareList.includes(c.company_name);
    const cov = _dcCoverage(c);
    // F-E: score track — Standard uses raw score, Conservative uses confidence-adjusted
    const displayScore = _scoreTrack === 'conservative'
      ? (getConservativeScore(c).conservative ?? c.esg_risk_score)
      : c.esg_risk_score;
    const displayTier  = _scoreTrack === 'conservative'
      ? (displayScore >= 6.5 ? 'High' : displayScore >= 3.5 ? 'Medium' : 'Low')
      : c.risk_tier;
    return `
      <tr style="cursor:pointer" onclick="openDeepDive('${esc(c.company_name)}')">
        <td onclick="event.stopPropagation()" style="padding:0 6px;width:56px;white-space:nowrap">
          <button class="cmp-btn${inCmp?' cmp-btn--active':''}" data-name="${esc(c.company_name)}"
            onclick="toggleCompare('${esc(c.company_name)}',event)"
            title="${inCmp?'Remove from compare':'Add to compare'}">${inCmp?'✓':'+'}</button>
          <button class="wl-btn${_WL.has(c.company_name)?' wl-btn--active':''}" data-name="${esc(c.company_name)}"
            onclick="toggleWatchlist('${esc(c.company_name)}',event)"
            title="${_WL.has(c.company_name)?'Remove from watchlist':'Add to watchlist'}">${_WL.has(c.company_name)?'★':'☆'}</button>
        </td>
        <td class="company-name" title="${esc(c.company_name)}">
          ${esc((c.company_name||'').slice(0,28))}${(c.company_name||'').length > 28 ? '…' : ''}${(c.anomaly_flags||[]).length ? `<span class="anomaly-dot" title="${esc((c.anomaly_flags||[]).map(f=>f.label).join(', '))}">⚠</span>` : ''}${_RECENT_FILERS.has(c.company_name) ? '<span class="ft-new-badge" title="New BRSR filing detected on BSE">NEW BRSR</span>' : ''}
          <div class="dc-coverage" title="Data coverage: ${cov.reported}/${cov.total} key fields reported in BRSR">
            <div class="dc-coverage__bar"><div class="dc-coverage__fill" style="width:${cov.pct}%"></div></div>
            <span class="dc-coverage__txt">${cov.pct}%</span>
          </div>
        </td>
        <td class="sector-cell">${esc((c.sector||'').replace('Manufacturing — ','').slice(0,30))}</td>
        <td><span class="risk-badge risk-badge--${displayTier}" title="${_scoreTrack === 'conservative' ? 'Conservative (confidence-adjusted) score' : 'Standard score'}">${displayScore}</span></td>
        <td>${_pctileBadge(getSectorPercentile(c))}</td>
        <td>${scoreBar(rb.ghg_intensity)}</td>
        <td>${scoreBar(rb.water_intensity)}</td>
        <td>${scoreBar(rb.epr_exposure)}</td>
        <td>${scoreBar(rb.compliance_risk)}</td>
        <td>${c.revenue_crore != null ? fmt(c.revenue_crore) : '—'}</td>
        <td>${md.market_cap_crore != null ? fmt(md.market_cap_crore) : '—'}</td>
        <td>${retHtml}</td>
        <td style="font-size:.78rem;color:#94a3b8">${esc((c.top_risk_factors||[])[0]||'—')}</td>
      </tr>`;
  }).join('');

  if (gated) {
    const remaining = _screenerData.length - _GUEST_LIMIT;
    tbody.innerHTML += `
      <tr class="screener-gate-row">
        <td colspan="13">
          <div class="screener-gate">
            <div class="screener-gate__icon">🔒</div>
            <div class="screener-gate__title">See all ${_screenerData.length.toLocaleString('en-IN')} companies</div>
            <div class="screener-gate__sub">${remaining.toLocaleString('en-IN')} more results hidden · Free account required</div>
            <div class="screener-gate__btns">
              <a href="/login#register" class="screener-gate__btn screener-gate__btn--primary">Create Free Account</a>
              <a href="/login" class="screener-gate__btn">Log In</a>
            </div>
          </div>
        </td>
      </tr>`;
  }

  _renderScreenerPagination(!gated);
}

function _renderScreenerPagination(showPagination = true) {
  const pg = document.getElementById('screener-pagination');
  if (!pg) return;
  if (!showPagination) { pg.innerHTML = ''; return; }
  const total = _screenerData.length;
  const pages = Math.ceil(total / _SCREENER_PAGE_SIZE);
  if (pages <= 1) { pg.innerHTML = ''; return; }

  const cur = _screenerPage;
  let html = '';

  html += `<button class="pg-btn" ${cur === 0 ? 'disabled' : ''} onclick="_renderScreenerPage(${cur - 1})">&#8592; Prev</button>`;

  // Window of page pills: show first, last, and up to 5 around current
  const pills = new Set([0, pages - 1]);
  for (let i = Math.max(0, cur - 2); i <= Math.min(pages - 1, cur + 2); i++) pills.add(i);
  const sorted = [...pills].sort((a, b) => a - b);

  let prev = -1;
  for (const p of sorted) {
    if (prev >= 0 && p - prev > 1) html += `<span class="pg-info">…</span>`;
    html += `<button class="pg-btn${p === cur ? ' pg-btn--active' : ''}" onclick="_renderScreenerPage(${p})">${p + 1}</button>`;
    prev = p;
  }

  html += `<button class="pg-btn" ${cur === pages - 1 ? 'disabled' : ''} onclick="_renderScreenerPage(${cur + 1})">Next &#8594;</button>`;
  html += `<span class="pg-info">${cur * _SCREENER_PAGE_SIZE + 1}–${Math.min((cur + 1) * _SCREENER_PAGE_SIZE, total)} of ${total}</span>`;

  pg.innerHTML = html;
}
window._renderScreenerPage = _renderScreenerPage;

function _pctileBadge(pct) {
  if (pct == null) return '<span class="pct-badge pct-badge--na">—</span>';
  const cls = pct >= 75 ? 'high' : pct >= 40 ? 'mid' : 'low';
  return `<span class="pct-badge pct-badge--${cls}" title="${pct}th percentile within sector (higher = worse)">${pct}<sup>th</sup></span>`;
}

function scoreBar(val) {
  const v = val || 0;
  const cls = v >= 7 ? 'red' : v >= 4.5 ? 'amber' : '';
  return `<div class="score-bar">
    <div class="score-bar__track"><div class="score-bar__fill score-bar__fill--${cls}" style="width:${v*10}%"></div></div>
    <span style="font-size:.75rem;color:#94a3b8">${v.toFixed(1)}</span>
  </div>`;
}

// Screener filter wiring — top bar syncs with column filters
document.getElementById('screenerSearch')?.addEventListener('input', applyColFilters);
document.getElementById('screenerRisk')?.addEventListener('change', e => {
  const cfRisk = document.getElementById('cf-risk-tier');
  if (cfRisk) cfRisk.value = e.target.value;
  applyColFilters();
});
document.getElementById('screenerSort')?.addEventListener('change', e => {
  const map = { esg_risk_score:'esg_risk_score', revenue_crore:'revenue_crore', ghg:'ghg', market_return:'return_1y' };
  const col = map[e.target.value] || 'esg_risk_score';
  colSort.col = col; colSort.dir = 'desc';
  applyColFilters();
});

// ── Regulation Tracker ────────────────────────────────────────────────────────
function renderRegulations(filter = '', urgency = '') {
  let regs = [...(INTEL?.regulations || [])];
  if (filter) {
    const q = filter.toLowerCase();
    regs = regs.filter(r => (r.title||'').toLowerCase().includes(q) || (r.description||'').toLowerCase().includes(q));
  }
  if (urgency) regs = regs.filter(r => r.urgency === urgency);

  document.getElementById('regCards').innerHTML = regs.map(r => {
    const fi = r.financial_impact || {};
    const sectors = (r.affected_sectors || []).slice(0, 5);
    return `
      <div class="reg-card reg-card--${r.urgency || 'Medium'}">
        <div class="reg-card__header">
          <div class="reg-card__title">${esc(r.title || 'Untitled')}</div>
          <div class="reg-card__score">Impact ${(r.impact_score||0).toFixed(1)}/10</div>
        </div>
        <div class="reg-card__meta">${esc(r.date || '')}${r.source ? ' · ' + esc(r.source) : ''} · Urgency: <strong style="color:${r.urgency==='High'?'#f87171':r.urgency==='Medium'?'#fbbf24':'#10b981'}">${r.urgency||'Medium'}</strong></div>
        <div class="reg-card__body">
          <div class="reg-card__field"><strong>Financial Impact Nature</strong>${esc(fi.nature || 'N/A')}</div>
          <div class="reg-card__field"><strong>Estimated Cost</strong>${esc(fi.estimated_range_crore || 'N/A')}</div>
          <div class="reg-card__field"><strong>Compliance Action</strong>${esc(r.compliance_action_required || 'N/A')}</div>
          <div class="reg-card__field"><strong>Companies Most at Risk</strong>${esc(r.companies_most_at_risk || 'N/A')}</div>
          ${r.supply_chain_impact ? `<div class="reg-card__field" style="grid-column:1/-1"><strong>Supply Chain Impact</strong>${esc(r.supply_chain_impact)}</div>` : ''}
        </div>
        ${sectors.length ? `<div class="reg-card__sectors">${sectors.map(s => `<span class="reg-card__sector-pill">${esc(s)}</span>`).join('')}</div>` : ''}
      </div>`;
  }).join('') || '<p style="color:#94a3b8;padding:20px">No regulations found.</p>';
}

document.getElementById('regSearch').addEventListener('input', e =>
  renderRegulations(e.target.value, document.getElementById('regUrgency').value));
document.getElementById('regUrgency').addEventListener('change', e =>
  renderRegulations(document.getElementById('regSearch').value, e.target.value));

// ── Supply Chain ──────────────────────────────────────────────────────────────
function renderSupplyChain() {
  const sc = INTEL?.supply_chain || {};

  // Summary cards
  document.getElementById('scSummary').innerHTML = [
    { val: sc.total_companies_analysed || 0,  lbl: 'Companies Analysed' },
    { val: sc.companies_with_epr || 0,         lbl: 'With EPR Obligations' },
    { val: sc.companies_low_msme || 0,         lbl: 'Low MSME Sourcing (<15%)' },
    { val: Object.keys(sc.upstream_bottlenecks || {}).length, lbl: 'Material Bottlenecks' },
  ].map(k => `<div class="sc-summary-card"><div class="sc-summary-card__val">${k.val}</div><div class="sc-summary-card__lbl">${k.lbl}</div></div>`).join('');

  // MSME chart
  const msme = (sc.msme_dependency || []).filter(d => d.msme_pct != null);
  const bands = { '<15%': 0, '15–30%': 0, '30–50%': 0, '>50%': 0 };
  msme.forEach(d => {
    if (d.msme_pct < 15) bands['<15%']++;
    else if (d.msme_pct < 30) bands['15–30%']++;
    else if (d.msme_pct < 50) bands['30–50%']++;
    else bands['>50%']++;
  });
  Plotly.newPlot('chartMsme', [{
    type: 'pie', hole: 0.4,
    labels: Object.keys(bands),
    values: Object.values(bands),
    marker: { colors: ['#f87171','#fbbf24','#34d399','#10b981'] },
    hovertemplate: '<b>%{label}</b><br>%{value} companies (%{percent})<extra></extra>',
    textinfo: 'label+percent',
    textfont: { size: 11, color: '#cbd5e1' },
  }], {
    paper_bgcolor: 'transparent',
    font: { color: '#94a3b8', family: 'DM Sans, sans-serif' },
    showlegend: false,
    margin: { l: 10, r: 10, t: 10, b: 10 }, height: 280,
  }, { displayModeBar: false, responsive: true });

  // Upstream bottlenecks chart
  const upstream = Object.entries(sc.upstream_bottlenecks || {})
    .sort((a,b) => b[1].max_impact_score - a[1].max_impact_score).slice(0, 8);
  Plotly.newPlot('chartUpstream', [
    {
      type: 'bar', name: 'Max Regulation Impact',
      x: upstream.map(([,v]) => v.material_label),
      y: upstream.map(([,v]) => v.max_impact_score),
      marker: { color: 'rgba(248,113,113,.7)', line: { width: 0 } },
      hovertemplate: '<b>%{x}</b><br>Max Impact: %{y:.1f}<extra></extra>',
    },
    {
      type: 'bar', name: 'Companies Exposed',
      x: upstream.map(([,v]) => v.material_label),
      y: upstream.map(([,v]) => v.companies_exposed),
      marker: { color: 'rgba(99,102,241,.7)', line: { width: 0 } },
      hovertemplate: '<b>%{x}</b><br>Companies: %{y}<extra></extra>',
    },
  ], {
    paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
    font: { color: '#94a3b8', family: 'DM Sans, sans-serif', size: 11 },
    barmode: 'group',
    legend: { font: { color: '#94a3b8' }, bgcolor: 'transparent' },
    xaxis: { gridcolor: 'transparent', tickfont: { color: '#94a3b8' } },
    yaxis: { gridcolor: 'rgba(255,255,255,.05)', tickfont: { color: '#94a3b8' } },
    margin: { l: 40, r: 10, t: 10, b: 80 }, height: 280,
  }, { displayModeBar: false, responsive: true });

  // MSME table
  const lowMsme = msme.filter(d => d.msme_pct < 15).slice(0, 30);
  document.getElementById('msmeBody').innerHTML = lowMsme.map(d => `
    <tr>
      <td class="company-name">${esc(d.company)}</td>
      <td class="sector-cell">${esc((d.sector||'').replace('Manufacturing — ',''))}</td>
      <td style="color:#f87171;font-weight:700">${d.msme_pct.toFixed(1)}%</td>
      <td>${scoreBar(d.risk_score)}</td>
      <td style="font-size:.78rem;color:#94a3b8">${esc(d.risk_note||'')}</td>
    </tr>`).join('') || '<tr><td colspan="5" style="color:#94a3b8;text-align:center;padding:20px">No companies below 15% MSME threshold.</td></tr>';
}

// ── Material Monitor ──────────────────────────────────────────────────────────
function renderMaterials() {
  const me = INTEL?.supply_chain?.material_exposure || {};
  const ub = INTEL?.supply_chain?.upstream_bottlenecks || {};

  document.getElementById('materialCards').innerHTML = Object.entries(me).map(([key, data]) => {
    const icon = MATERIAL_ICONS[key] || '⚠️';
    const ubData = ub[key] || {};
    return `
      <div class="material-card">
        <div class="material-card__header">
          <div class="material-card__icon">${icon}</div>
          <div>
            <div class="material-card__name">${esc(data.label || key)}</div>
            <div class="material-card__reg">${esc(data.regulation || '')}</div>
          </div>
        </div>
        <div class="material-card__stats">
          <div class="material-card__stat">
            <span class="material-card__stat-label">Companies exposed</span>
            <span class="material-card__stat-val">${data.company_count || 0}</span>
          </div>
          <div class="material-card__stat">
            <span class="material-card__stat-label">Avg ESG risk score</span>
            <span class="material-card__stat-val">${(data.avg_risk||0).toFixed(1)}</span>
          </div>
          <div class="material-card__stat">
            <span class="material-card__stat-label">High-risk companies</span>
            <span class="material-card__stat-val" style="color:#f87171">${data.high_risk_count||0}</span>
          </div>
          ${ubData.regulation_count ? `
          <div class="material-card__stat">
            <span class="material-card__stat-label">Active regulations</span>
            <span class="material-card__stat-val" style="color:#fbbf24">${ubData.regulation_count}</span>
          </div>` : ''}
        </div>
        <div class="material-card__epr material-card__epr--${data.epr_required ? 'yes' : 'no'}">
          ${data.epr_required ? '⚠ EPR compliance required' : '✓ No EPR obligation'}
        </div>
        ${(data.top_companies||[]).length ? `
        <div class="material-card__companies">
          <strong>Top exposed:</strong> ${data.top_companies.slice(0,3).map(c => esc(c)).join(', ')}
        </div>` : ''}
      </div>`;
  }).join('') || '<p style="color:#94a3b8;padding:20px">Material data will appear after the first intelligence run.</p>';
}

// ── Double Materiality ────────────────────────────────────────────────────────
let _dmClickAttached = false;

function renderDoubleMateriality(sectorFilter = '') {
  if (typeof Plotly === 'undefined') return;
  const data = sectorFilter
    ? allCompanies.filter(c => {
        const raw = (c.sector||'').replace('Manufacturing — ','').trim();
        const NIC_MAP2 = {'62099':'IT & software services','62090':'IT & computer services','62021':'IT consulting','64191':'Banking','64192':'Banking','64990':'Financial services','24101':'Iron & steel','24102':'Iron & steel','20113':'Specialty chemicals','21001':'Pharmaceuticals','21002':'Pharmaceuticals','35101':'Electricity generation','35102':'Electricity transmission'};
        const cleaned = /^\d{4,6}$/.test(raw) ? (NIC_MAP2[raw] || `NIC ${raw}`) : raw;
        return cleaned.includes(sectorFilter) || raw.includes(sectorFilter);
      })
    : allCompanies;

  document.getElementById('dmCount').textContent = `${data.length} companies`;

  // Populate sector filter
  const sectorSelect = document.getElementById('dmSectorFilter');
  if (sectorSelect.options.length <= 1) {
    const NIC_MAP = {
      '62011':'Software development','62012':'Software development','62013':'Software development',
      '62099':'IT & software services','62090':'IT & computer services','62021':'IT consulting',
      '64191':'Banking','64192':'Banking','64990':'Financial services','65110':'Life insurance',
      '65120':'Non-life insurance','66190':'Financial services aux','66110':'Fund management',
      '24101':'Iron & steel','24102':'Iron & steel','24103':'Iron & steel','24200':'Steel tubes & pipes',
      '24311':'Precious metals','25910':'Metal containers','25930':'Fasteners & screws',
      '20111':'Industrial gases','20112':'Dyes & pigments','20113':'Specialty chemicals',
      '20211':'Pesticides','20221':'Paints & coatings','20231':'Soap & detergents',
      '20291':'Other chemicals','21001':'Pharmaceuticals','21002':'Pharmaceuticals',
      '26101':'Electronic components','26102':'Electronic components','26301':'Telecom equipment',
      '35101':'Electricity generation','35102':'Electricity transmission','35201':'Gas supply',
      '41001':'Construction','41002':'Construction','42101':'Roads & highways',
      '45101':'Motor vehicles wholesale','45201':'Motor vehicle repair',
      '46100':'Wholesale trade','47110':'Retail — food','47190':'Retail — general',
      '55101':'Hotels','56101':'Restaurants',
      '61100':'Telecom — wired','61200':'Telecom — wireless','61300':'Satellite telecom',
      '68100':'Real estate','68200':'Rental of real estate',
      '72100':'R&D natural sciences','73100':'Advertising',
      '10101':'Processed meat','10201':'Fish processing','10301':'Fruit & veg processing',
      '10411':'Edible oils','10501':'Dairy products','10611':'Grain milling',
      '13111':'Cotton yarn spinning','13121':'Weaving','13941':'Cordage & ropes',
      '14101':'Wearing apparel','15121':'Footwear',
      '16101':'Sawmilling','17011':'Pulp','17012':'Paper','17021':'Paperboard',
      '22111':'Rubber tyres','22192':'Other rubber products','22210':'Plastic products',
      '23101':'Glass','23910':'Abrasives','23921':'Cement','23931':'Cement products',
      '27101':'Electric motors','27102':'Batteries','27201':'Lighting equipment',
      '28111':'Engines & turbines','28121':'Pumps & compressors','28131':'Taps & valves',
      '29101':'Motor vehicles','29102':'Motor vehicle parts','30111':'Ships',
      '31001':'Furniture',
    };
    const cleanSector = s => {
      const trimmed = (s||'').replace('Manufacturing — ','').trim();
      if (/^\d{4,6}$/.test(trimmed)) return NIC_MAP[trimmed] || `NIC ${trimmed}`;
      return trimmed;
    };
    const sectors = [...new Set(allCompanies.map(c => cleanSector(c.sector)))]
      .filter(s => s && s.length > 1)
      .sort();
    sectors.forEach(s => { const o = document.createElement('option'); o.value = s; o.textContent = s; sectorSelect.appendChild(o); });
  }

  const points = data.map(c => {
    const dm = c.double_materiality || {};
    return {
      x: dm.financial_materiality || c.esg_risk_score,
      y: dm.impact_materiality || c.esg_risk_score,
      label: c.company_name,
      tier: c.risk_tier,
      quadrant: dm.quadrant || 'Watch List',
    };
  });

  const colorMap = { High: 'rgba(248,113,113,.8)', Medium: 'rgba(251,191,36,.8)', Low: 'rgba(52,211,153,.8)' };

  const dmDiv = document.getElementById('chartDualMateriality');
  Plotly.react(dmDiv, [{
    type: 'scatter', mode: 'markers',
    x: points.map(p => p.x),
    y: points.map(p => p.y),
    customdata: points.map(p => [p.label, p.quadrant]),
    marker: {
      color: points.map(p => colorMap[p.tier] || 'rgba(148,163,184,.7)'),
      size: 8, line: { width: 0 },
    },
    hovertemplate: '<b>%{customdata[0]}</b><br>Financial: %{x:.1f}  Impact: %{y:.1f}<br>Quadrant: %{customdata[1]}<extra></extra>',
  }], {
    paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
    font: { color: '#94a3b8', family: 'DM Sans, sans-serif', size: 11 },
    xaxis: { range: [0, 10], title: { text: 'Financial Materiality →', font: { color: '#94a3b8' } }, gridcolor: 'rgba(255,255,255,.05)', tickfont: { color: '#94a3b8' } },
    yaxis: { range: [0, 10], title: { text: 'Impact Materiality →', font: { color: '#94a3b8' } }, gridcolor: 'rgba(255,255,255,.05)', tickfont: { color: '#94a3b8' } },
    shapes: [
      { type: 'line', x0: 5, x1: 5, y0: 0, y1: 10, line: { color: 'rgba(255,255,255,.15)', width: 1 } },
      { type: 'line', x0: 0, x1: 10, y0: 5, y1: 5, line: { color: 'rgba(255,255,255,.15)', width: 1 } },
    ],
    margin: { l: 60, r: 20, t: 20, b: 60 }, height: 400,
  }, { displayModeBar: false, responsive: true });

  if (!_dmClickAttached) {
    _dmClickAttached = true;
    dmDiv.on('plotly_click', evData => {
      if (evData.points[0]) openDeepDive(evData.points[0].customdata[0]);
    });
  }

  // Quadrant breakdown
  const quads = { 'Dual Materiality':[], 'Financially Material':[], 'Impact Material':[], 'Watch List':[] };
  data.forEach(c => {
    const q = c.double_materiality?.quadrant || 'Watch List';
    if (quads[q]) quads[q].push(c);
  });
  document.getElementById('dmQuadGrid').innerHTML = Object.entries(quads).map(([q, companies]) => `
    <div class="dm-quad-card dm-quad-card--${q.replace(/\s+/g,'-').toLowerCase()}">
      <div class="dm-quad-title">${q} <span>(${companies.length})</span></div>
      <div class="dm-quad-companies">
        ${companies.slice(0,6).map(c => `
          <div class="dm-quad-company" onclick="openDeepDive('${esc(c.company_name)}')">
            <span>${esc(c.company_name.slice(0,28))}</span>
            <span class="risk-badge risk-badge--${c.risk_tier}" style="font-size:.65rem">${c.esg_risk_score}</span>
          </div>`).join('')}
        ${companies.length > 6 ? `<div style="font-size:.75rem;color:#64748b;padding:4px">+${companies.length-6} more</div>` : ''}
      </div>
    </div>`).join('');
}

document.getElementById('dmSectorFilter').addEventListener('change', e => renderDoubleMateriality(e.target.value));

// ── ESG Target Tracker ────────────────────────────────────────────────────────
function renderTargets(filter = '', typeFilter = '') {
  const rows = [];
  allCompanies.forEach(c => {
    (c.esg_targets || []).forEach(t => {
      rows.push({ company: c.company_name, sector: c.sector, risk: c.esg_risk_score, tier: c.risk_tier, ...t });
    });
  });

  let filtered = rows;
  if (filter) {
    const q = filter.toLowerCase();
    filtered = filtered.filter(r => r.company.toLowerCase().includes(q) || (r.topic||'').toLowerCase().includes(q));
  }
  if (typeFilter) filtered = filtered.filter(r => r.type === typeFilter);

  // Summary KPIs
  const achieved    = rows.filter(r => r.type === 'Achieved').length;
  const commitments = rows.filter(r => r.type === 'Commitment').length;
  const topics      = [...new Set(rows.map(r => r.topic))].length;
  document.getElementById('targetSummary').innerHTML = [
    { v: rows.length,   l: 'Total Disclosures' },
    { v: achieved,      l: 'Targets Achieved',  cls: 'kpi-card__value--green' },
    { v: commitments,   l: 'Commitments',        cls: 'kpi-card__value--amber' },
    { v: topics,        l: 'ESG Topics Covered' },
  ].map(k => `<div class="kpi-card"><div class="kpi-card__value ${k.cls||''}">${k.v}</div><div class="kpi-card__label">${k.l}</div></div>`).join('');

  document.getElementById('targetCount').textContent = `${filtered.length} disclosures`;
  document.getElementById('targetBody').innerHTML = filtered.map(r => `
    <tr style="cursor:pointer" onclick="openDeepDive('${esc(r.company)}')">
      <td class="company-name">${esc(r.company.slice(0,28))}</td>
      <td class="sector-cell">${esc((r.sector||'').replace('Manufacturing — ','').slice(0,28))}</td>
      <td style="color:#10b981;font-size:.82rem">${esc(r.topic||'')}</td>
      <td style="font-size:.82rem;color:#cbd5e1">${esc(r.metric||'')}</td>
      <td><span class="risk-badge ${r.type==='Achieved'?'risk-badge--Low':'risk-badge--Medium'}">${r.type||''}</span></td>
      <td>${scoreBar(r.risk)}</td>
    </tr>`).join('') || '<tr><td colspan="6" style="text-align:center;color:#64748b;padding:20px">No target data found in current dataset.</td></tr>';
}

document.getElementById('targetSearch').addEventListener('input', e => renderTargets(e.target.value, document.getElementById('targetType').value));
document.getElementById('targetType').addEventListener('change', e => renderTargets(document.getElementById('targetSearch').value, e.target.value));

// ── Global Search ─────────────────────────────────────────────────────────────
document.getElementById('globalSearchBtn').addEventListener('click', runGlobalSearch);
document.getElementById('globalSearch').addEventListener('keydown', e => {
  if (e.key === 'Enter') runGlobalSearch();
});

async function runGlobalSearch() {
  const q = document.getElementById('globalSearch').value.trim();
  if (!q) return;
  const resultsEl = document.getElementById('searchResults');
  resultsEl.classList.add('is-open');
  resultsEl.innerHTML = `<div class="search-loading">
    <div class="dd-spinner"></div><span>Searching across 155 companies + regulations…</span>
  </div>`;

  // Client-side fast-path: search existing data before hitting API
  const clientResults = clientSearch(q);

  if (!API_BASE) {
    // No backend — show client-side results only
    renderSearchResults({ answer: null, company_profiles: clientResults, matched_regulations: [] }, q);
    return;
  }

  try {
    const r = await fetch(`${API_BASE}/api/esg-search`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q, limit: 8 }),
      signal: AbortSignal.timeout(15000),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    renderSearchResults(await r.json(), q);
  } catch {
    // Fall back to client-side
    renderSearchResults({ answer: null, company_profiles: clientResults, matched_regulations: [] }, q);
  }
}

function clientSearch(q) {
  const terms = q.toLowerCase().split(/\s+/);
  return allCompanies.filter(c => {
    const blob = [c.company_name, c.sector, ...(c.top_risk_factors||[]),
                  c.risk_tier, c.ai_summary||''].join(' ').toLowerCase();
    return terms.every(t => blob.includes(t));
  }).slice(0, 8);
}

function renderSearchResults(data, query) {
  const el = document.getElementById('searchResults');
  const companies = data.company_profiles || [];
  const regs      = data.matched_regulations || [];
  const answer    = data.answer;
  const insight   = data.key_insight;
  const followups = data.follow_up_questions || [];

  let html = `<div class="search-header">
    <span class="search-query">"${esc(query)}"</span>
    <button class="search-close" onclick="document.getElementById('searchResults').classList.remove('is-open')">✕</button>
  </div>`;

  if (answer) {
    html += `<div class="search-answer">
      ${insight ? `<div class="search-insight">💡 ${esc(insight)}</div>` : ''}
      <p>${esc(answer)}</p>
    </div>`;
  }

  if (companies.length) {
    html += `<div class="search-section-title">Matching Companies (${companies.length})</div>
    <div class="search-companies">
      ${companies.map(c => `
        <div class="search-company-card" onclick="openDeepDive('${esc(c.company_name)}')">
          <div class="search-company-name">${esc(c.company_name)}</div>
          <div class="search-company-meta">${esc((c.sector||'').replace('Manufacturing — ','').slice(0,30))}</div>
          <span class="risk-badge risk-badge--${c.risk_tier}">${c.esg_risk_score}</span>
        </div>`).join('')}
    </div>`;
  }

  if (regs.length) {
    html += `<div class="search-section-title">Related Regulations</div>
    <ul class="search-regs">${regs.map(r => `<li>${esc(r)}</li>`).join('')}</ul>`;
  }

  if (followups.length) {
    html += `<div class="search-section-title">Try also</div>
    <div class="search-followups">
      ${followups.map(f => `<button class="search-followup" onclick="document.getElementById('globalSearch').value='${esc(f)}';runGlobalSearch()">${esc(f)}</button>`).join('')}
    </div>`;
  }

  if (!companies.length && !answer) {
    html += `<p style="color:#94a3b8;padding:12px">No matches found. Try different keywords.</p>`;
  }

  el.innerHTML = html;
}

// ── Company Deep Dive ─────────────────────────────────────────────────────────
document.getElementById('deepDiveClose').addEventListener('click', () => {
  document.getElementById('deepDiveOverlay').classList.remove('is-open');
});
document.getElementById('deepDiveOverlay').addEventListener('click', e => {
  if (e.target === e.currentTarget) e.currentTarget.classList.remove('is-open');
});
document.querySelectorAll('.dd-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.dd-tab').forEach(b => b.classList.remove('dd-tab--active'));
    btn.classList.add('dd-tab--active');
    renderDDTab(btn.dataset.ddtab);
  });
});

let _currentDDData = null;
let _currentDDCompany = null;

function _track(event, params) {
  if (typeof gtag === 'function') gtag('event', event, params || {});
}

async function openDeepDive(companyName) {
  const overlay = document.getElementById('deepDiveOverlay');
  const body    = document.getElementById('deepDiveBody');
  const loading = document.getElementById('ddLoading');

  // Find basic profile from local data
  const profile = allCompanies.find(c => c.company_name === companyName);
  if (!profile) return;
  _track('esg_company_viewed', { company: companyName, sector: profile.sector, risk_tier: profile.risk_tier });

  _currentDDCompany = profile;
  window._currentDeepDiveCompany = companyName;
  _currentDDData    = null;
  const briefBtn = document.getElementById('ddBriefingBtn');
  if (briefBtn) {
    briefBtn.style.display = (window._gcApiBase || localStorage.getItem('gc_api_base')) ? '' : 'none';
    briefBtn.textContent = '↓ Board Briefing PDF';
  }

  document.getElementById('ddCompany').textContent = profile.company_name;
  document.getElementById('ddSector').textContent  = (profile.sector||'').replace('Manufacturing — ','');
  document.getElementById('ddScore').innerHTML =
    `<span class="risk-badge risk-badge--${profile.risk_tier}">${profile.esg_risk_score}/10</span>`;

  // Reset tabs
  document.querySelectorAll('.dd-tab').forEach(b => b.classList.remove('dd-tab--active'));
  document.querySelector('.dd-tab[data-ddtab="overview"]').classList.add('dd-tab--active');

  overlay.classList.add('is-open');

  // The bulk /api/esg/data payload omits ai_summary (≈49% of its size) to keep
  // it light. Lazy-fetch the full same-origin record once per company and merge.
  if (profile.ai_summary === undefined) {
    try {
      const full = await fetch('/api/esg/company/' + encodeURIComponent(companyName),
                               { signal: AbortSignal.timeout(8000) });
      if (full.ok) Object.assign(profile, await full.json());
    } catch { /* render with what we have if the detail fetch fails */ }
  }

  // Show client-side overview immediately
  body.innerHTML = renderDDOverviewLocal(profile);

  // Fetch AI deep dive if backend available
  if (API_BASE) {
    body.innerHTML += `<div id="ddAiSection" style="margin-top:20px">
      <div class="dd-loading"><div class="dd-spinner"></div><p>Loading AI analysis…</p></div>
    </div>`;
    try {
      const r = await fetch(`${API_BASE}/api/esg-company-profile`, {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ company_name: companyName }),
        signal: AbortSignal.timeout(30000),
      });
      if (r.ok) {
        _currentDDData = await r.json();
        renderDDTab('overview');
      }
    } catch {
      document.getElementById('ddAiSection').innerHTML =
        '<p style="color:#64748b;font-size:.8rem">AI analysis unavailable — backend offline.</p>';
    }
  }
}

function renderDDTab(tab) {
  const body    = document.getElementById('deepDiveBody');
  const profile = _currentDDCompany;
  const data    = _currentDDData;

  if (tab === 'overview') {
    body.innerHTML = renderDDOverviewLocal(profile);
    if (data) {
      body.innerHTML += `
        <div class="dd-section">
          <div class="dd-section-title">AI Analysis</div>
          <p class="dd-text">${esc(data.executive_summary||'')}</p>
        </div>
        <div class="dd-section">
          <div class="dd-section-title">Financial Risk Analysis</div>
          <p class="dd-text">${esc(data.financial_risk_analysis||'')}</p>
        </div>
        ${data.investment_signal ? `<div class="dd-insight-box">💡 <strong>Investor Signal:</strong> ${esc(data.investment_signal)}</div>` : ''}
        <p class="dd-disclaimer">AI analysis based on publicly filed BRSR data. Not investment advice. Not a SEBI-registered Research Analyst or ESG Rating Provider output.</p>`;
      setTimeout(() => _gcAiFeedback(body, 'deepdive', profile.company_name), 100);
    }
  }
  else if (tab === 'risks') {
    body.innerHTML = renderDDRisks(profile);
  }
  else if (tab === 'materiality') {
    body.innerHTML = renderDDMateriality(profile, data);
  }
  else if (tab === 'regulations') {
    body.innerHTML = renderDDRegulations(profile, data);
  }
  else if (tab === 'benchmark') {
    body.innerHTML = renderDDBenchmark(profile, data);
  }
  else if (tab === 'targets') {
    body.innerHTML = renderDDTargets(profile);
  }
  else if (tab === 'actions') {
    body.innerHTML = renderDDActions(data);
  }
  else if (tab === 'netzero') {
    body.innerHTML = renderDDNetZero(profile);
    _plotNetZeroChart(profile);
  }
  else if (tab === 'waterfall') {
    body.innerHTML = renderDDWaterfall(profile);
    _plotWaterfallChart(profile);
  }
  else if (tab === 'wwbench') {
    body.innerHTML = renderDDWWBench(profile);
    _plotWWScatter(profile);
  }
  else if (tab === 'datagaps') {
    body.innerHTML = renderDDDataGaps(profile);
  }
  else if (tab === 'ccts') {
    body.innerHTML = renderDDCCTS(profile);
    loadCCTSScorecard(profile);
  }
  else if (tab === 'tcfd') {
    body.innerHTML = renderDDTCFD(profile);
    loadTCFDGap(profile);
  }
}

// ── Sector Score Blending (Feature F-C) ───────────────────────────────────────

function _getSectorAverages() {
  if (_SECTOR_AVG_CACHE) return _SECTOR_AVG_CACHE;
  _SECTOR_AVG_CACHE = {};
  const groups = {};
  allCompanies.forEach(c => {
    const sec = c.sector || 'Unknown';
    if (!groups[sec]) groups[sec] = [];
    groups[sec].push(c);
  });
  Object.entries(groups).forEach(([sec, companies]) => {
    const avg = field => {
      const vals = companies.map(c => c.risk_breakdown?.[field]).filter(v => v != null && !isNaN(v));
      return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    };
    const avgTop = field => {
      const vals = companies.map(c => c[field]).filter(v => v != null && !isNaN(v));
      return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    };
    _SECTOR_AVG_CACHE[sec] = {
      ghg_intensity:   avg('ghg_intensity'),
      water_intensity: avg('water_intensity'),
      waste_intensity: avg('waste_intensity'),
      epr_exposure:    avg('epr_exposure'),
      compliance_risk: avg('compliance_risk'),
      hr_risk:         avg('hr_risk'),
      governance_risk: avg('governance_risk'),
      esg_risk_score:  avgTop('esg_risk_score'),
      count: companies.length,
    };
  });
  return _SECTOR_AVG_CACHE;
}

// P2-E: Sector percentile cache — built lazily after data loads
let _SECTOR_PCT_CACHE = null;

function _getSectorPercentiles() {
  if (_SECTOR_PCT_CACHE) return _SECTOR_PCT_CACHE;
  _SECTOR_PCT_CACHE = {};
  if (!allCompanies.length) return _SECTOR_PCT_CACHE;
  const bySecor = {};
  allCompanies.forEach(c => {
    const sec = (c.sector || '').trim();
    if (!bySecor[sec]) bySecor[sec] = [];
    bySecor[sec].push(c);
  });
  Object.entries(bySecor).forEach(([sec, companies]) => {
    const sorted = [...companies].sort((a, b) => (a.esg_risk_score||a.esg_risk_score||0) - (b.esg_risk_score||b.esg_risk_score||0));
    sorted.forEach((c, i) => {
      _SECTOR_PCT_CACHE[c.company_name] = Math.round((i / Math.max(sorted.length - 1, 1)) * 100);
    });
  });
  return _SECTOR_PCT_CACHE;
}

function getSectorPercentile(company) {
  const pcts = _getSectorPercentiles();
  return pcts[company.company_name] ?? null;
}

/**
 * Returns sector-blended E/S/G sub-scores for a company.
 * E blend: 60% company + 40% sector avg (CRISIL methodology)
 * S blend: 75% company + 25% sector avg
 * G: company only — regulatory/governance risk is company-specific
 */
function getBlendedScores(company) {
  const avgs = _getSectorAverages();
  const secAvg = avgs[company.sector || 'Unknown'] || {};
  const rb = company.risk_breakdown || {};

  const blend = (field, wComp, wSec) => {
    const c = rb[field];
    const s = secAvg[field];
    if (c == null && s == null) return null;
    if (c == null) return +(s).toFixed(2);
    if (s == null) return +(c).toFixed(2);
    return +(wComp * c + wSec * s).toFixed(2);
  };

  const blended = {
    ghg_intensity:   blend('ghg_intensity',   0.6, 0.4),
    water_intensity: blend('water_intensity', 0.6, 0.4),
    waste_intensity: blend('waste_intensity', 0.6, 0.4),
    epr_exposure:    blend('epr_exposure',    0.6, 0.4),
    hr_risk:         blend('hr_risk',         0.75, 0.25),
    governance_risk: rb.governance_risk != null ? +rb.governance_risk.toFixed(2) : null,
    compliance_risk: rb.compliance_risk != null ? +rb.compliance_risk.toFixed(2) : null,
  };

  const avg = vals => {
    const f = vals.filter(v => v != null);
    return f.length ? +(f.reduce((a, b) => a + b, 0) / f.length).toFixed(1) : null;
  };

  return {
    e: avg([blended.ghg_intensity, blended.water_intensity, blended.waste_intensity, blended.epr_exposure]),
    s: blended.hr_risk != null ? +blended.hr_risk.toFixed(1) : null,
    g: avg([blended.governance_risk, blended.compliance_risk]),
    blended,
    sectorAvg: secAvg,
    peerCount: secAvg.count || 0,
  };
}

/**
 * F-E: Assured vs Standard Score Track.
 * Returns two score tracks for a company:
 *   standard  — current esg_risk_score (all public data + GC estimates)
 *   conservative — confidence-weighted: assured companies keep raw score;
 *                  non-assured companies blend toward sector average
 *                  proportional to data coverage (how much is actually verified).
 *
 * Rationale: A company reporting 0% of key KPIs gets the sector average as
 * its conservative score. A company with BRSR Core assurance keeps its own score.
 * This lets CFOs and auditors see the "quality-adjusted" risk signal.
 */
function getConservativeScore(company) {
  const assurance = company.governance?.brsr_assurance || 'None';
  const rawScore  = company.esg_risk_score ?? null;

  if (rawScore === null) {
    return { standard: null, conservative: null, confidence: 0, track: 'missing', diff: null };
  }

  // ── Assured companies: score is fully verified ─────────────────────────────
  if (assurance === 'Reasonable' || assurance === 'Limited') {
    return {
      standard:     rawScore,
      conservative: rawScore,
      confidence:   1.0,
      track:        'assured',
      assuranceLabel: assurance + ' Assurance',
      provider:     company.governance?.assurance_provider || '',
      diff:         0,
    };
  }

  // ── Non-assured: blend raw score with sector average by coverage % ─────────
  const cov = _dcCoverage(company);
  const confidence = cov.pct / 100;   // 0.0 → 1.0

  const sectorAvgScore = _getSectorAverages()[company.sector || 'Unknown']?.esg_risk_score;
  const fallback = sectorAvgScore ?? rawScore;  // use sector avg, else raw (sector of 1)

  const conservative = +(confidence * rawScore + (1 - confidence) * fallback).toFixed(1);
  const diff = +(conservative - rawScore).toFixed(1);

  return {
    standard:     rawScore,
    conservative,
    confidence,
    track: confidence >= 0.75 ? 'reported' : confidence >= 0.25 ? 'estimated' : 'missing',
    assuranceLabel: `${Math.round(confidence * 100)}% data verified`,
    provider: '',
    diff,
  };
}

// ── Data Confidence helpers (Feature #3) ──────────────────────────────────────

/**
 * Returns a coloured badge indicating how confident we are in a KPI value.
 * source: 'reported' | 'estimated' | 'assured' | 'missing'
 * When rawValue is falsy/zero/unknown the badge is always 'missing'.
 */
function _dcBadge(rawValue, source) {
  const empty = !rawValue || rawValue === '—' || rawValue === 'Unknown' || rawValue === 0;
  if (empty) return '<span class="dc-badge dc-missing" title="Not reported in BRSR filing">Missing</span>';
  const cfg = {
    assured:   ['dc-assured',   'Assured',   'Third-party verified (BRSR Core assurance)'],
    reported:  ['dc-reported',  'Reported',  'Company self-reported in SEBI BRSR filing'],
    estimated: ['dc-estimated', 'Estimated', 'Modelled by Green Curve from public data'],
  };
  const [cls, label, tip] = cfg[source] || cfg.reported;
  return `<span class="dc-badge ${cls}" title="${tip}">${label}</span>`;
}

/**
 * Returns the data confidence tier for a single KPI value.
 * Checks governance.brsr_assurance so assured companies get the green badge.
 * Compliance cost is always 'estimated' (Green Curve model output).
 */
function _dcTier(company, rawValue, forceEstimated) {
  if (forceEstimated) return 'estimated';
  if (rawValue === null || rawValue === undefined || rawValue === '' || rawValue === 'Unknown') return 'missing';
  const assurance = company.governance?.brsr_assurance || 'None';
  if (assurance === 'Reasonable' || assurance === 'Limited') return 'assured';
  return 'reported';
}

/**
 * Computes a simple data-coverage score for a company profile.
 * Returns { reported, total, pct } based on key environmental KPIs.
 */
function _dcCoverage(p) {
  const fe = p.financial_exposure || {};
  const checks = [
    !!fe.scope1_emissions_tco2e,
    !!fe.scope2_emissions_tco2e,
    !!fe.water_withdrawal_m3,
    !!fe.waste_tonnes,
    !!(fe.epr_applicable && fe.epr_applicable !== 'Unknown'),
    !!p.revenue_crore,
    !!(p.risk_breakdown?.ghg_intensity),
  ];
  const reported = checks.filter(Boolean).length;
  return { reported, total: checks.length, pct: Math.round((reported / checks.length) * 100) };
}

// ─────────────────────────────────────────────────────────────────────────────

function renderDDOverviewLocal(p) {
  const rb = p.risk_breakdown || {};
  const fe = p.financial_exposure || {};
  const md = p.market_data || {};
  // F-D: look up most recent filing for this company
  const _ftFiling = (_FILING_TRACKER?.recent_filings || []).find(f => f.company_name === p.company_name);

  return `
    ${_ftFiling ? `
    <div class="ft-dd-alert">
      <span class="ft-dd-alert__badge">NEW BRSR FILING</span>
      <span class="ft-dd-alert__text">BSE filing detected: ${esc(_ftFiling.headline || 'BRSR / Annual Report')} · ${esc(_ftFiling.filing_date)} · <a class="ft-dd-alert__link" href="${esc(_ftFiling.url)}" target="_blank" rel="noopener">View on BSE ↗</a></span>
      <span class="ft-dd-alert__note">ESG score may not yet reflect this filing. Run <code>check_brsr_filings.py</code> then regenerate to update.</span>
    </div>` : ''}
    <div class="dd-overview-grid">
      <div class="dd-kpi"><div class="dd-kpi-val">${p.revenue_crore ? '₹'+fmt(p.revenue_crore)+' Cr' : '—'}</div><div class="dd-kpi-lbl">Revenue</div></div>
      <div class="dd-kpi"><div class="dd-kpi-val">${md.market_cap_crore ? '₹'+fmt(md.market_cap_crore)+' Cr' : '—'}</div><div class="dd-kpi-lbl">Market Cap</div></div>
      <div class="dd-kpi"><div class="dd-kpi-val ${md.return_1y_pct != null ? (md.return_1y_pct>=0?'green':'red') : ''}">${md.return_1y_pct != null ? (md.return_1y_pct>=0?'+':'')+md.return_1y_pct+'%' : '—'}</div><div class="dd-kpi-lbl">1Y Return</div></div>
      <div class="dd-kpi"><div class="dd-kpi-val">${fe.estimated_compliance_cost_band||'—'}</div><div class="dd-kpi-lbl">Est. Compliance Cost</div></div>
      ${(() => {
        const pct = getSectorPercentile(p);
        const pctCol = pct == null ? '#64748b' : pct >= 75 ? '#f87171' : pct >= 40 ? '#fbbf24' : '#34d399';
        const pctLbl = pct == null ? '—' : `${pct}<sup>th</sup>`;
        return `<div class="dd-kpi"><div class="dd-kpi-val" style="color:${pctCol}">${pctLbl}</div><div class="dd-kpi-lbl">Sector Percentile</div><div class="dd-kpi-sub">${pct == null ? 'N/A' : pct >= 75 ? 'High-risk vs peers' : pct >= 40 ? 'Mid-tier vs peers' : 'Better than most peers'}</div></div>`;
      })()}
    </div>
    ${(() => {
      const bs = getBlendedScores(p);
      const scoreClass = v => v == null ? '' : v >= 7 ? 'esg-sub-score-val--red' : v >= 4.5 ? 'esg-sub-score-val--amber' : 'esg-sub-score-val--green';
      return `
    <div class="esg-sub-scores">
      <div class="esg-sub-score-card">
        <div class="esg-sub-score-val ${scoreClass(bs.e)}">${bs.e != null ? bs.e : '—'}</div>
        <div class="esg-sub-score-lbl">E Score</div>
        <div class="esg-sub-score-note">GHG · Water · Waste · EPR<br>60% company + 40% sector</div>
      </div>
      <div class="esg-sub-score-card">
        <div class="esg-sub-score-val ${scoreClass(bs.s)}">${bs.s != null ? bs.s : '—'}</div>
        <div class="esg-sub-score-lbl">S Score</div>
        <div class="esg-sub-score-note">HR Risk<br>75% company + 25% sector</div>
      </div>
      <div class="esg-sub-score-card">
        <div class="esg-sub-score-val ${scoreClass(bs.g)}">${bs.g != null ? bs.g : '—'}</div>
        <div class="esg-sub-score-lbl">G Score</div>
        <div class="esg-sub-score-note">Governance · Compliance<br>Company data only</div>
      </div>
      <div class="esg-sub-score-meta">
        Sector avg ESG: <strong>${bs.sectorAvg.esg_risk_score != null ? bs.sectorAvg.esg_risk_score.toFixed(1) : '—'}</strong> · ${bs.peerCount} companies · CRISIL-inspired blending
      </div>
    </div>`;
    })()}
    ${(() => {
      const cs = getConservativeScore(p);
      if (cs.standard === null) return '';
      const rCls = v => v == null ? '' : v >= 7 ? 'stc-val--red' : v >= 4.5 ? 'stc-val--amber' : 'stc-val--green';
      const diffSign   = cs.diff > 0 ? '+' : '';
      const diffColor  = cs.diff > 0 ? '#f87171' : cs.diff < 0 ? '#34d399' : '#64748b';
      const trackIcon  = cs.track === 'assured' ? '✅' : cs.track === 'reported' ? '🔵' : cs.track === 'estimated' ? '🟡' : '⬜';
      const pctBar     = Math.round(cs.confidence * 100);
      return `
    <div class="stc-compare">
      <div class="stc-card stc-card--standard">
        <div class="stc-label">Standard Score</div>
        <div class="stc-val ${rCls(cs.standard)}">${cs.standard}</div>
        <div class="stc-note">All public data<br>GC estimates included</div>
      </div>
      <div class="stc-divider">
        ${cs.diff !== 0
          ? `<div class="stc-diff" style="color:${diffColor}">${diffSign}${cs.diff}</div>`
          : `<div class="stc-diff stc-diff--same">≡</div>`}
        <div class="stc-arrow">→</div>
      </div>
      <div class="stc-card stc-card--conservative">
        <div class="stc-label">${trackIcon} Conservative Score</div>
        <div class="stc-val ${rCls(cs.conservative)}">${cs.conservative}</div>
        <div class="stc-note">${esc(cs.assuranceLabel)}${cs.provider ? ' · ' + esc(cs.provider) : ''}</div>
      </div>
      <div class="stc-confidence">
        <div class="stc-conf-label">Data confidence</div>
        <div class="stc-conf-bar-wrap">
          <div class="stc-conf-bar" style="width:${pctBar}%;background:${cs.track==='assured'?'#34d399':cs.track==='reported'?'#00c8ff':cs.track==='estimated'?'#fbbf24':'#475569'}"></div>
        </div>
        <span class="stc-conf-pct">${pctBar}%</span>
      </div>
    </div>`;
    })()}
    ${p.ai_summary ? `
    <div class="dd-section">
      <p class="dd-text dd-summary">${esc(p.ai_summary)}</p>
      <p class="dd-disclaimer">Source: ${esc(p.company_name)} BRSR Filing, FY ${esc(p.financial_year||'2024-25')}. This analysis is derived from the company's own public disclosures and is not investment advice or a regulatory determination.</p>
    </div>` : ''}
    <div class="dd-section">
      <div class="dd-section-title">Top Risk Factors</div>
      <div class="dd-risk-pills">${(p.top_risk_factors||[]).map(r => `<span class="dd-risk-pill">${esc(r)}</span>`).join('')}</div>
    </div>
    <div class="dd-section">
      <div class="dd-section-title">Financial Exposure</div>
      ${(() => {
        const cov = _dcCoverage(p);
        return `
        <div class="dc-summary-row">
          <span class="dc-summary-row__label">Data Coverage</span>
          <div class="dc-summary-row__bar-wrap">
            <div class="dc-summary-row__bar" style="width:${cov.pct}%"></div>
          </div>
          <span class="dc-summary-row__count">${cov.reported}/${cov.total} fields reported</span>
        </div>
        <div class="dc-legend">
          <span class="dc-legend__title">Key:</span>
          <span class="dc-legend__item"><span class="dc-badge dc-assured">Assured</span> Third-party verified (BRSR Core)</span>
          <span class="dc-legend__item"><span class="dc-badge dc-reported">Reported</span> Company BRSR filing (SEBI)</span>
          <span class="dc-legend__item"><span class="dc-badge dc-estimated">Estimated</span> Green Curve model</span>
          <span class="dc-legend__item"><span class="dc-badge dc-missing">Missing</span> Not in filing</span>
        </div>`;
      })()}
      ${(() => {
        const gov = p.governance || {};
        const assuranceLevel = gov.brsr_assurance || 'None';
        const hasAssurance = assuranceLevel !== 'None';
        const provider = gov.assurance_provider || '';
        if (hasAssurance) return `
        <div class="dc-assurance-row">
          <span class="dc-badge dc-assured">BRSR Core Assured</span>
          <span class="dc-assurance-detail">
            ${esc(assuranceLevel)} assurance${provider ? ' · ' + esc(provider) : ''}
          </span>
        </div>`;
        return '';
      })()}
      <div class="dd-kv-grid">
        ${[
          ['Scope 1 Emissions',    fe.scope1_emissions_tco2e,                                                               fe.scope1_emissions_tco2e ? fe.scope1_emissions_tco2e+' tCO2e' : '—',  _dcTier(p, fe.scope1_emissions_tco2e)],
          ['Scope 2 Emissions',    fe.scope2_emissions_tco2e,                                                               fe.scope2_emissions_tco2e ? fe.scope2_emissions_tco2e+' tCO2e' : '—',  _dcTier(p, fe.scope2_emissions_tco2e)],
          ['Water Withdrawal',     fe.water_withdrawal_m3,                                                                  fe.water_withdrawal_m3 ? fmt(fe.water_withdrawal_m3)+' m³' : '—',      _dcTier(p, fe.water_withdrawal_m3)],
          ['Waste Generated',      fe.waste_tonnes,                                                                         fe.waste_tonnes ? fmt(fe.waste_tonnes)+' tonnes' : '—',                _dcTier(p, fe.waste_tonnes)],
          ['EPR Applicable',       fe.epr_applicable && fe.epr_applicable !== 'Unknown' ? fe.epr_applicable : null,         fe.epr_applicable||'Unknown',                                           _dcTier(p, fe.epr_applicable && fe.epr_applicable !== 'Unknown' ? fe.epr_applicable : null)],
          ['Est. Compliance Cost', fe.estimated_compliance_cost_band,                                                       fe.estimated_compliance_cost_band||'—',                                 _dcTier(p, fe.estimated_compliance_cost_band, true)],
        ].map(([l, rawVal, display, src]) =>
          `<div class="dd-kv">
            <span class="dd-kv-label">${l}</span>
            <span class="dd-kv-val">${display}${_dcBadge(rawVal, src)}</span>
          </div>`
        ).join('')}
      </div>
    </div>`;
}

function renderDDRisks(p) {
  const rb = p.risk_breakdown || {};
  const bs = getBlendedScores(p);
  const sec = bs.sectorAvg;

  // [label, raw, blended, sectorAvgVal, E/S/G category]
  const dims = [
    ['GHG Intensity',   rb.ghg_intensity,   bs.blended.ghg_intensity,   sec.ghg_intensity,   'E'],
    ['Water Intensity', rb.water_intensity, bs.blended.water_intensity, sec.water_intensity, 'E'],
    ['Waste Intensity', rb.waste_intensity, bs.blended.waste_intensity, sec.waste_intensity, 'E'],
    ['EPR Exposure',    rb.epr_exposure,    bs.blended.epr_exposure,    sec.epr_exposure,    'E'],
    ['HR Risk',         rb.hr_risk,         bs.blended.hr_risk,         sec.hr_risk,         'S'],
    ['Compliance Risk', rb.compliance_risk, rb.compliance_risk,         sec.compliance_risk, 'G'],
    ['Governance Risk', rb.governance_risk, rb.governance_risk,         sec.governance_risk, 'G'],
  ];

  return `<div class="dd-section">
    <div class="dd-section-title">Risk Dimension Breakdown</div>
    <div class="dd-risks-legend-row">
      <span class="dd-rl-bar">━━</span> Raw company score
      &nbsp;·&nbsp; <span class="dd-rl-mark">│</span> Sector avg (${bs.peerCount} cos.)
      &nbsp;·&nbsp; <span class="dd-rl-blend">◉</span> Sector-blended
    </div>
    <div class="dd-risk-bars">
      ${dims.map(([label, raw, blended, secAvgVal, cat]) => {
        const v = raw != null ? raw : 0;
        const cls = v >= 7 ? 'red' : v >= 4.5 ? 'amber' : 'green';
        const secLeft = secAvgVal != null ? Math.min(99, secAvgVal * 10).toFixed(1) : null;
        const showBlend = blended != null && raw != null && Math.abs(blended - v) >= 0.1;
        const blendTip = cat === 'E' ? '60% company + 40% sector avg' : cat === 'S' ? '75% company + 25% sector avg' : 'Company data only';
        return `<div class="dd-risk-row">
          <span class="dd-risk-label">
            <span class="dd-dim-badge dd-dim-badge--${cat.toLowerCase()}">${cat}</span>${label}
          </span>
          <div class="dd-risk-track">
            <div class="dd-risk-fill dd-risk-fill--${cls}" style="width:${v*10}%"></div>
            ${secLeft !== null ? `<div class="dd-risk-sec-mark" style="left:${secLeft}%" title="Sector avg: ${(secAvgVal||0).toFixed(1)}"></div>` : ''}
          </div>
          <span class="dd-risk-score">${v.toFixed(1)}</span>
          ${showBlend ? `<span class="dd-risk-blended" title="${blendTip}">${(blended||0).toFixed(1)}</span>` : '<span class="dd-risk-blended-empty"></span>'}
        </div>`;
      }).join('')}
    </div>
  </div>`;
}

function renderDDRegulations(p, data) {
  const kb = INTEL?.knowledge_base?.india_regulations || [];
  const sector = (p.sector||'').toLowerCase();
  const applicable = kb.filter(r =>
    (r.affected_sectors||[]).some(s => sector.includes(s.toLowerCase().slice(0,6)))
    || r.id === 'BRSR_EXPANSION'
  );

  let html = `<div class="dd-section">
    <div class="dd-section-title">Applicable India Regulations</div>
    <div class="dd-reg-list">
      ${applicable.map(r => `
        <div class="dd-reg-item">
          <div class="dd-reg-name">${esc(r.name)}</div>
          <div class="dd-reg-auth">${esc(r.authority)} · ${esc(r.effective_fy || r.effective_date || '')}</div>
          <div class="dd-reg-impact">${esc(r.financial_impact||'')}</div>
        </div>`).join('')}
    </div>
  </div>`;

  if (data?.regulatory_obligations?.length) {
    html += `<div class="dd-section">
      <div class="dd-section-title">Specific Obligations (AI Analysis)</div>
      ${data.regulatory_obligations.map(o => `
        <div class="dd-obligation">
          <div class="dd-obligation-reg">${esc(o.regulation||'')}</div>
          <div class="dd-obligation-text">${esc(o.obligation||'')}</div>
          <div class="dd-obligation-meta">
            ${o.deadline ? `<span>📅 ${esc(o.deadline)}</span>` : ''}
            ${o.cost_estimate ? `<span>💰 ${esc(o.cost_estimate)}</span>` : ''}
          </div>
        </div>`).join('')}
    </div>`;
  }
  return html;
}

function renderDDBenchmark(p, data) {
  const sector  = p.sector || '';
  // Use full sector average from cache (all companies in sector, not just 5 peers)
  const bs = getBlendedScores(p);
  const fullSectorAvg = bs.sectorAvg.esg_risk_score || 0;
  const sectorAvg = fullSectorAvg;
  const peers   = data?.sector_peers || allCompanies.filter(c =>
    c.company_name !== p.company_name &&
    (c.sector||'').slice(0,20).toLowerCase() === sector.slice(0,20).toLowerCase()
  ).slice(0, 5);

  const position  = p.esg_risk_score > sectorAvg + 0.5 ? 'Higher risk than sector avg'
                  : p.esg_risk_score < sectorAvg - 0.5 ? 'Lower risk than sector avg'
                  : 'At sector average';

  return `<div class="dd-section">
    <div class="dd-section-title">Sector Peer Comparison</div>
    <div class="dd-bench-position ${p.esg_risk_score > sectorAvg ? 'bench-worse' : 'bench-better'}">
      ${position} · Full-sector avg: ${sectorAvg.toFixed(1)} (${bs.peerCount} cos.) · This company: ${p.esg_risk_score}
    </div>
    <div class="dd-peer-table">
      ${[p, ...peers].map((c, i) => `
        <div class="dd-peer-row ${i===0?'dd-peer-row--current':''}">
          <span class="dd-peer-name">${i===0?'▶ ':''} ${esc(c.company_name)}</span>
          <div class="score-bar">
            <div class="score-bar__track" style="width:80px">
              <div class="score-bar__fill score-bar__fill--${c.esg_risk_score>=6.5?'red':c.esg_risk_score>=4?'amber':''}"
                style="width:${c.esg_risk_score*10}%"></div>
            </div>
            <span style="font-size:.8rem;color:#94a3b8">${c.esg_risk_score}</span>
          </div>
          <span style="font-size:.78rem;color:#64748b">${c.revenue_crore?'₹'+fmt(c.revenue_crore)+' Cr':'—'}</span>
        </div>`).join('')}
    </div>
    ${(() => {
      const peersW = allCompanies.filter(c =>
        c.company_name !== p.company_name &&
        (c.sector || '').slice(0, 20).toLowerCase() === sector.slice(0, 20).toLowerCase() &&
        c.financial_exposure?.waste_tonnes && c.revenue_crore > 0
      );
      if (peersW.length < 3) return '';
      const sorted = peersW.map(c => c.financial_exposure.waste_tonnes / c.revenue_crore).sort((a, b) => a - b);
      const n = sorted.length;
      const minV = sorted[0], maxV = sorted[n - 1], median = sorted[Math.floor(n / 2)];
      const mine = p.financial_exposure?.waste_tonnes && p.revenue_crore > 0
        ? p.financial_exposure.waste_tonnes / p.revenue_crore : null;
      const percentile = mine !== null
        ? Math.round(sorted.filter(v => v <= mine).length / n * 100) : null;
      const posLeft = v => Math.min(98, Math.max(2, ((v - minV) / (maxV - minV + 0.001)) * 100)).toFixed(1);
      const pColor = percentile > 75 ? '#f87171' : percentile > 50 ? '#fbbf24' : '#34d399';
      return `
        <div class="dd-section-title" style="margin-top:16px">Waste Intensity vs Sector</div>
        <div style="font-size:.72rem;color:#64748b;margin-bottom:10px">${n} sector peers with disclosed data · t/₹Cr</div>
        <div style="padding:0 4px">
          <div style="position:relative;height:6px;background:linear-gradient(90deg,#34d399,#fbbf24,#f87171);border-radius:4px">
            ${mine !== null ? `<div style="position:absolute;top:50%;left:${posLeft(mine)}%;transform:translate(-50%,-50%)"><div style="width:3px;height:16px;background:#fff;border-radius:2px;box-shadow:0 0 6px rgba(0,0,0,.6)"></div></div>` : ''}
          </div>
          <div style="display:flex;justify-content:space-between;font-size:.68rem;color:#475569;margin-top:3px">
            <span>${minV.toFixed(1)}</span><span>med ${median.toFixed(1)}</span><span>${maxV.toFixed(1)}</span>
          </div>
        </div>
        ${mine !== null
          ? `<div style="font-size:.8rem;margin-top:6px">This company: <strong style="color:${pColor}">${mine.toFixed(1)} t/₹Cr</strong> · <strong>${percentile}th percentile</strong></div>`
          : `<div style="font-size:.75rem;color:#64748b;margin-top:4px">Waste not disclosed in BRSR filing.</div>`}`;
    })()}
    ${data?.benchmark_vs_peers ? `
    <div class="dd-section-title" style="margin-top:16px">AI Benchmark Analysis</div>
    ${data.benchmark_vs_peers.strengths?.length ? `
      <div style="margin-bottom:8px"><strong style="color:#10b981">Strengths</strong>
      <ul class="dd-list">${data.benchmark_vs_peers.strengths.map(s=>`<li>${esc(s)}</li>`).join('')}</ul></div>` : ''}
    ${data.benchmark_vs_peers.weaknesses?.length ? `
      <div><strong style="color:#f87171">Weaknesses</strong>
      <ul class="dd-list">${data.benchmark_vs_peers.weaknesses.map(w=>`<li>${esc(w)}</li>`).join('')}</ul></div>` : ''}
    ` : ''}
  </div>`;
}

function renderDDActions(data) {
  if (!data?.action_recommendations?.length) {
    return `<div class="dd-section"><p style="color:#94a3b8">Action recommendations available after AI analysis loads. Backend must be running.</p></div>`;
  }
  const priorityColor = { High: '#f87171', Medium: '#fbbf24', Low: '#10b981' };
  return `<div class="dd-section">
    <div class="dd-section-title">Recommended Actions</div>
    <div class="dd-actions-list">
      ${data.action_recommendations.map(a => `
        <div class="dd-action">
          <div class="dd-action-header">
            <span class="dd-action-priority" style="color:${priorityColor[a.priority]||'#94a3b8'}">${a.priority||'Medium'}</span>
            <span class="dd-action-title">${esc(a.action||'')}</span>
          </div>
          <div class="dd-action-meta">
            ${a.timeline?`<span>⏱ ${esc(a.timeline)}</span>`:''}
            ${a.expected_benefit?`<span>✓ ${esc(a.expected_benefit)}</span>`:''}
          </div>
        </div>`).join('')}
    </div>
    ${data.esg_score_trajectory ? `<div class="dd-insight-box">📈 <strong>Trajectory:</strong> ${esc(data.esg_score_trajectory)}</div>` : ''}
  </div>`;
}

function renderDDMateriality(p, data) {
  const dm = p.double_materiality || {};
  const fin = dm.financial_materiality || p.esg_risk_score;
  const imp = dm.impact_materiality || p.esg_risk_score;
  const quadrant = dm.quadrant || 'Watch List';
  const qColor = {
    'Dual Materiality':    '#f87171',
    'Financially Material':'#fbbf24',
    'Impact Material':     '#6366f1',
    'Watch List':          '#64748b',
  }[quadrant] || '#94a3b8';

  return `<div class="dd-section">
    <div class="dd-section-title">Double Materiality Position</div>
    <div class="dm-dd-scores">
      <div class="dm-dd-score-card">
        <div class="dm-dd-score-val" style="color:#fbbf24">${fin.toFixed(1)}</div>
        <div class="dm-dd-score-lbl">Financial Materiality</div>
        <div class="dm-dd-score-desc">How ESG risks affect company finances</div>
      </div>
      <div class="dm-dd-score-card">
        <div class="dm-dd-score-val" style="color:#6366f1">${imp.toFixed(1)}</div>
        <div class="dm-dd-score-lbl">Impact Materiality</div>
        <div class="dm-dd-score-desc">Company's impact on environment & society</div>
      </div>
      <div class="dm-dd-score-card">
        <div class="dm-dd-score-val" style="color:${qColor};font-size:1rem">${quadrant}</div>
        <div class="dm-dd-score-lbl">IRO Quadrant</div>
        <div class="dm-dd-score-desc">Based on ESRS double materiality framework</div>
      </div>
    </div>
    <div class="dd-insight-box" style="margin-top:16px">
      ${quadrant === 'Dual Materiality'
        ? '⚠️ <strong>Dual Materiality:</strong> This company both faces significant financial risk from ESG factors AND has meaningful environmental/social impact. Highest priority for disclosure and action.'
        : quadrant === 'Financially Material'
        ? '💰 <strong>Financially Material:</strong> ESG risks significantly affect this company\'s financial performance. Focus on risk mitigation and financial resilience planning.'
        : quadrant === 'Impact Material'
        ? '🌍 <strong>Impact Material:</strong> This company has significant environmental/social footprint but lower direct financial ESG risk. Focus on impact reduction and stakeholder disclosure.'
        : '📋 <strong>Watch List:</strong> Currently lower materiality on both dimensions. Monitor for regulatory changes that could shift this profile.'}
    </div>
  </div>
  <div class="dd-section">
    <div class="dd-section-title">IRO Context (ESRS Framework)</div>
    <div class="dd-reg-list">
      <div class="dd-reg-item"><div class="dd-reg-name">Impacts</div><div class="dd-reg-impact">Company's positive/negative effects on environment, workers, communities and economy through its operations and value chain</div></div>
      <div class="dd-reg-item"><div class="dd-reg-name">Risks</div><div class="dd-reg-impact">Physical climate risks, transition risks, regulatory penalties, reputational risks that affect financial performance</div></div>
      <div class="dd-reg-item"><div class="dd-reg-name">Opportunities</div><div class="dd-reg-impact">Energy savings from efficiency, green financing access, new market access through sustainable products, premium pricing</div></div>
    </div>
  </div>`;
}

function renderDDTargets(p) {
  const targets = p.esg_targets || [];
  if (!targets.length) {
    return `<div class="dd-section"><p style="color:#94a3b8">No ESG targets or commitments found in this company's BRSR disclosures. This may indicate limited voluntary sustainability commitments.</p></div>`;
  }
  return `<div class="dd-section">
    <div class="dd-section-title">ESG Targets & Commitments (from BRSR)</div>
    <div class="dd-actions-list">
      ${targets.map(t => `
        <div class="dd-action">
          <div class="dd-action-header">
            <span class="dd-action-priority" style="color:${t.type==='Achieved'?'#10b981':'#fbbf24'}">${t.type}</span>
            <span class="dd-action-title">${esc(t.topic)}</span>
          </div>
          <div style="font-size:.85rem;color:#cbd5e1;margin-top:4px">${esc(t.metric)}</div>
        </div>`).join('')}
    </div>
    <div class="dd-insight-box" style="margin-top:16px">
      💡 Companies with more verified targets typically command lower cost of capital and better ESG ratings from MSCI, Sustainalytics, and CDP.
    </div>
  </div>`;
}

// ── P2-A: Net Zero Trajectory Visualizer ─────────────────────────────────────

const NZ_YEARS = Array.from({ length: 26 }, (_, i) => 2025 + i);  // 2025-2050

function _nzBaseline(profile) {
  const fe = profile.financial_exposure || {};
  const s1 = fe.scope1_emissions_tco2e;
  const s2 = fe.scope2_emissions_tco2e;
  if (s1 != null && s2 != null) return s1 + s2;
  if (s1 != null) return s1;
  // P4-A: Use ML sector-intensity estimate when available
  if (_GHG_ESTIMATES) {
    const est = _GHG_ESTIMATES[profile.company_name];
    if (est && est.total_estimated_tco2e > 0) return est.total_estimated_tco2e;
  }
  // Final fallback: GHG intensity × revenue (rough proxy)
  const ghg  = profile.risk_breakdown?.ghg_intensity;
  const rev  = profile.revenue_crore;
  if (ghg != null && rev > 0) return Math.round(ghg * rev * 100);
  return null;
}

function _nzIsEstimated(profile) {
  const fe = profile.financial_exposure || {};
  if (fe.scope1_emissions_tco2e != null || fe.scope2_emissions_tco2e != null) return false;
  return !!((_GHG_ESTIMATES || {})[profile.company_name]);
}

function _nzAlignment(baseline) {
  if (baseline == null) return { label: 'Unknown', color: '#64748b', temp: null };
  // Implied temperature based on how far baseline is from global budget thresholds.
  // These are illustrative sector-agnostic ranges; not a formal ITR calculation.
  const perUnit = baseline;  // Just used for thresholds below
  // We use the reduction trajectory the company would need to reach net zero by 2050.
  // If the company shows NO reduction commitment, assume BAU = 3.5°C
  // These are rough alignment buckets for display purpose.
  return { label: 'On BAU Trajectory', color: '#f87171', temp: '~3.5°C', degree: 3.5 };
}

function _nzTargetYear(profile) {
  const targets = profile.esg_targets || [];
  for (const t of targets) {
    const metric = (t.metric || '').toLowerCase();
    const m = metric.match(/net.?zero.*?(\d{4})|(\d{4}).*?net.?zero|carbon.?neutral.*?(\d{4})/);
    if (m) {
      const yr = parseInt(m[1] || m[2] || m[3], 10);
      if (yr >= 2025 && yr <= 2060) return yr;
    }
  }
  return null;
}

function _nzPath(baseline, reductionPctPerYear) {
  if (baseline == null) return NZ_YEARS.map(() => null);
  return NZ_YEARS.map((_, i) => Math.max(0, Math.round(baseline * Math.pow(1 - reductionPctPerYear, i))));
}

function renderDDNetZero(profile) {
  const fe       = profile.financial_exposure || {};
  const baseline = _nzBaseline(profile);
  const s1       = fe.scope1_emissions_tco2e;
  const s2       = fe.scope2_emissions_tco2e;
  const s3       = fe.scope3_emissions_tco2e;
  const targetYr = _nzTargetYear(profile);
  const targets  = profile.esg_targets || [];

  const hasData    = baseline != null;
  const isEstimated = _nzIsEstimated(profile);
  const isProxy    = (s1 == null || s2 == null) && hasData && !isEstimated;

  let alignColor = '#f87171', alignLabel = 'BAU — No reduction trajectory', alignTemp = '~3.5°C';
  if (targetYr && targetYr <= 2050) { alignColor = '#34d399'; alignLabel = `Net Zero by ${targetYr}`; alignTemp = '≤1.5°C target'; }
  else if (targetYr && targetYr <= 2060) { alignColor = '#fbbf24'; alignLabel = `Net Zero by ${targetYr}`; alignTemp = '~2°C aligned'; }
  else if (targets.some(t => /net.?zero|carbon.?neutral/i.test(t.metric || ''))) {
    alignColor = '#fbbf24'; alignLabel = 'Net Zero target (year unspecified)'; alignTemp = '~2°C potential';
  }

  return `
  <div class="dd-section">
    <div class="dd-section-title">Net Zero Pathway Analysis</div>

    <div class="nz-kpi-row">
      <div class="nz-kpi">
        <div class="nz-kpi__val" style="color:${s1!=null?'#e2e8f0':'#64748b'}">${s1!=null ? s1.toLocaleString('en-IN') : '—'}</div>
        <div class="nz-kpi__lbl">Scope 1 (tCO₂e)</div>
      </div>
      <div class="nz-kpi">
        <div class="nz-kpi__val" style="color:${s2!=null?'#e2e8f0':'#64748b'}">${s2!=null ? s2.toLocaleString('en-IN') : '—'}</div>
        <div class="nz-kpi__lbl">Scope 2 (tCO₂e)</div>
      </div>
      <div class="nz-kpi">
        <div class="nz-kpi__val" style="color:${s3!=null?'#e2e8f0':'#64748b'}">${s3!=null ? s3.toLocaleString('en-IN') : '—'}</div>
        <div class="nz-kpi__lbl">Scope 3 (tCO₂e)</div>
      </div>
      <div class="nz-kpi nz-kpi--align">
        <div class="nz-kpi__val" style="color:${alignColor}">${alignTemp}</div>
        <div class="nz-kpi__lbl">${alignLabel}</div>
      </div>
    </div>

    ${!hasData ? `
      <div class="nz-no-data">
        <div class="nz-no-data__icon">📊</div>
        <div class="nz-no-data__title">GHG Data Not Disclosed</div>
        <div class="nz-no-data__sub">This company has not disclosed Scope 1 or Scope 2 emissions in its BRSR filing. Net Zero trajectory cannot be calculated without a verified GHG baseline.</div>
      </div>` : `
      ${isEstimated ? (() => { const est = (_GHG_ESTIMATES||{})[profile.company_name]||{}; return `<div class="nz-proxy-note nz-proxy-note--est"><span class="est-badge">Est.</span> GHG not disclosed — trajectory uses ML sector-intensity estimate (${(est.sector_matched||'general industry')}, ${est.intensity_factor_used||'?'} tCO₂e/₹Cr). Confidence: ±40%. <a href="#" onclick="document.querySelector('[data-tab=aiquery]')?.click();return false">Run AI Query for peers</a></div>`; })() : ''}
      ${isProxy ? `<div class="nz-proxy-note">⚠ Exact Scope 1/2 not separately disclosed — trajectory estimated from GHG intensity × revenue. Refer to the company's BRSR filing for verified data.</div>` : ''}
      <div id="nz-chart" style="height:340px;width:100%;margin:16px 0 8px"></div>
      <div class="nz-legend-row">
        <span class="nz-leg nz-leg--bau">BAU (no reduction)</span>
        <span class="nz-leg nz-leg--1p5">1.5°C Science-Based Target path (7%/yr)</span>
        <span class="nz-leg nz-leg--2deg">Well-below 2°C path (2.5%/yr)</span>
        ${targetYr ? `<span class="nz-leg nz-leg--target">Company target: Net Zero ${targetYr}</span>` : ''}
      </div>
      <div class="nz-insight-row">
        <div class="nz-insight-card">
          <div class="nz-insight-card__label">Reduction needed for 1.5°C by 2050</div>
          <div class="nz-insight-card__val" style="color:#34d399">${baseline!=null ? '7.0%/yr' : '—'}</div>
          <div class="nz-insight-card__sub">Scope 1+2 absolute contraction</div>
        </div>
        <div class="nz-insight-card">
          <div class="nz-insight-card__label">Cumulative reduction 2025-2050</div>
          <div class="nz-insight-card__val" style="color:#34d399">${baseline!=null ? Math.round(baseline * (1 - Math.pow(0.93, 25))).toLocaleString('en-IN') + ' tCO₂e' : '—'}</div>
          <div class="nz-insight-card__sub">Required for 1.5°C Science-Based Target path</div>
        </div>
        <div class="nz-insight-card">
          <div class="nz-insight-card__label">Year emissions reach net zero</div>
          <div class="nz-insight-card__val" style="color:${targetYr?'#34d399':'#f87171'}">${targetYr || 'Not committed'}</div>
          <div class="nz-insight-card__sub">${targetYr ? 'From stated BRSR target' : 'No net-zero year found in BRSR'}</div>
        </div>
      </div>`}
    <p class="dd-disclaimer" style="margin-top:12px">Pathways use IPCC AR6 / SBTi Absolute Contraction Approach. Temperature alignment is indicative only — not a validated ITR calculation. Based on publicly filed BRSR data.</p>
  </div>`;
}

function _plotNetZeroChart(profile) {
  const el = document.getElementById('nz-chart');
  if (!el || typeof Plotly === 'undefined') return;

  const baseline = _nzBaseline(profile);
  if (baseline == null) return;

  const targetYr = _nzTargetYear(profile);
  const bau    = _nzPath(baseline, 0);
  const p15    = _nzPath(baseline, 0.07);
  const p2     = _nzPath(baseline, 0.025);

  const traces = [
    {
      x: NZ_YEARS, y: bau,
      name: 'BAU (no reduction)',
      mode: 'lines',
      line: { color: '#f87171', width: 2, dash: 'dot' },
    },
    {
      x: NZ_YEARS, y: p2,
      name: 'Well-below 2°C (2.5%/yr)',
      mode: 'lines',
      line: { color: '#fbbf24', width: 2, dash: 'dash' },
    },
    {
      x: NZ_YEARS, y: p15,
      name: '1.5°C Science-Based Target path (7%/yr)',
      mode: 'lines',
      line: { color: '#34d399', width: 2.5, dash: 'dash' },
    },
  ];

  if (targetYr && targetYr >= 2025 && targetYr <= 2060) {
    const tYears  = [2025, targetYr];
    const tVals   = [baseline, 0];
    traces.push({
      x: tYears, y: tVals,
      name: `Company target (Net Zero ${targetYr})`,
      mode: 'lines+markers',
      line: { color: '#00c8ff', width: 2.5 },
      marker: { size: 7, color: '#00c8ff' },
    });
  }

  const maxY = Math.ceil(baseline * 1.05);

  Plotly.newPlot(el, traces, {
    paper_bgcolor: 'transparent',
    plot_bgcolor:  'rgba(12,22,41,.5)',
    font:   { color: '#94a3b8', family: 'DM Sans, sans-serif', size: 11 },
    margin: { l: 70, r: 20, t: 20, b: 50 },
    xaxis: {
      title: { text: 'Year', font: { size: 11, color: '#64748b' } },
      range: [2024.5, 2050.5],
      gridcolor: 'rgba(255,255,255,.05)',
      tickfont: { color: '#94a3b8' },
      dtick: 5,
    },
    yaxis: {
      title: { text: 'GHG Emissions (tCO₂e/yr)', font: { size: 11, color: '#64748b' } },
      rangemode: 'tozero',
      gridcolor: 'rgba(255,255,255,.05)',
      tickfont: { color: '#94a3b8' },
    },
    legend: {
      orientation: 'h',
      y: -0.18,
      x: 0,
      font: { size: 10 },
    },
    annotations: [
      { x: 2050, y: 0, text: 'Net Zero', showarrow: false, font: { size: 9, color: 'rgba(52,211,153,.5)' }, xanchor: 'right', yanchor: 'bottom' },
    ],
    shapes: [
      { type: 'line', x0: 2025, x1: 2050, y0: 0, y1: 0, line: { color: 'rgba(52,211,153,.25)', width: 1.5, dash: 'dot' } },
    ],
  }, { displayModeBar: false, responsive: true });
}

// ── P2-B: ESG Score Decomposition Waterfall ───────────────────────────────────

const WF_DIMS = [
  { key: 'ghg_intensity',    label: 'GHG Intensity',   color: '#f87171' },
  { key: 'water_intensity',  label: 'Water Intensity',  color: '#60a5fa' },
  { key: 'waste_intensity',  label: 'Waste Intensity',  color: '#a78bfa' },
  { key: 'epr_exposure',     label: 'EPR Exposure',     color: '#fb923c' },
  { key: 'compliance_risk',  label: 'Compliance Risk',  color: '#f472b6' },
  { key: 'hr_risk',          label: 'HR Risk',          color: '#facc15' },
  { key: 'governance_risk',  label: 'Governance Risk',  color: '#94a3b8' },
];

function renderDDWaterfall(profile) {
  const rb  = profile.risk_breakdown || {};
  const tot = profile.esg_risk_score  || 0;
  const dims = WF_DIMS.map(d => ({ ...d, val: rb[d.key] ?? null }));
  const known = dims.filter(d => d.val != null);
  const missing = dims.filter(d => d.val == null);

  const sectorAvgs = _getSectorAverages();
  const secKey = (profile.sector || '').trim();
  const secAvg = sectorAvgs[secKey] ? sectorAvgs[secKey].esg_risk_score : null;
  const secLabel = secKey || 'Sector';

  const riskLabel = tot <= 3 ? 'Low' : tot <= 6 ? 'Medium' : 'High';
  const riskColor = tot <= 3 ? '#34d399' : tot <= 6 ? '#fbbf24' : '#f87171';

  const dimRows = dims.map(d => {
    const v = d.val;
    if (v == null) return `<tr><td>${d.label}</td><td colspan="2" style="color:#475569;font-size:.8rem">Not disclosed</td></tr>`;
    const bar = Math.min(100, Math.round((v / 10) * 100));
    return `<tr>
      <td style="color:#94a3b8;font-size:.8rem">${d.label}</td>
      <td style="width:140px">
        <div style="background:rgba(255,255,255,.06);border-radius:4px;height:6px;overflow:hidden">
          <div style="width:${bar}%;height:100%;background:${d.color};border-radius:4px"></div>
        </div>
      </td>
      <td style="color:${d.color};font-size:.85rem;font-weight:700;text-align:right">${v.toFixed(1)}</td>
    </tr>`;
  }).join('');

  return `
  <div class="dd-section">
    <div class="dd-section-title">ESG Score Decomposition</div>

    <div class="wf-summary-row">
      <div class="wf-total-card">
        <div class="wf-total-card__label">Composite ESG Risk Score</div>
        <div class="wf-total-card__score" style="color:${riskColor}">${tot.toFixed(1)}</div>
        <div class="wf-total-card__tag" style="background:${riskColor}22;color:${riskColor}">${riskLabel} Risk</div>
      </div>
      ${secAvg != null ? `
      <div class="wf-total-card wf-total-card--sec">
        <div class="wf-total-card__label">${secLabel} Sector Avg</div>
        <div class="wf-total-card__score" style="color:#94a3b8">${secAvg.toFixed(1)}</div>
        <div class="wf-total-card__tag" style="background:rgba(148,163,184,.12);color:#94a3b8">${tot < secAvg ? 'Below avg (better)' : 'Above avg (worse)'}</div>
      </div>` : ''}
    </div>

    <div id="wf-chart" style="height:320px;width:100%;margin:16px 0 8px"></div>

    <table class="wf-dim-table">
      <thead><tr><th>Dimension</th><th>Contribution</th><th style="text-align:right">Score/10</th></tr></thead>
      <tbody>${dimRows}</tbody>
    </table>

    ${missing.length ? `<div class="wf-missing-note">⚠ ${missing.map(d=>d.label).join(', ')} not available in BRSR filing — excluded from waterfall.</div>` : ''}
    <p class="dd-disclaimer" style="margin-top:12px">Each dimension scored 0–10 (higher = higher risk). Composite is a weighted average across disclosed dimensions. Sector average based on all ${secKey || ''} companies in the Green Curve dataset.</p>
  </div>`;
}

function _plotWaterfallChart(profile) {
  const el = document.getElementById('wf-chart');
  if (!el || typeof Plotly === 'undefined') return;

  const rb  = profile.risk_breakdown || {};
  const tot = profile.esg_risk_score  || 0;

  const dims   = WF_DIMS.filter(d => rb[d.key] != null);
  if (!dims.length) { el.innerHTML = '<div style="color:#475569;text-align:center;padding:60px 0;font-size:.85rem">No risk breakdown data available.</div>'; return; }

  const labels = dims.map(d => d.label);
  const values = dims.map(d => rb[d.key]);
  const colors = dims.map(d => d.color);

  // Sort descending for impact visibility
  const sorted = dims.map((d, i) => ({ label: labels[i], val: values[i], color: colors[i] }))
    .sort((a, b) => b.val - a.val);

  const sectorAvgs = _getSectorAverages();
  const secKey = (profile.sector || '').trim();
  const secAvg = sectorAvgs[secKey] ? sectorAvgs[secKey].esg_risk_score : null;

  const traces = [
    {
      type: 'bar',
      x: sorted.map(d => d.label),
      y: sorted.map(d => d.val),
      marker: { color: sorted.map(d => d.color) },
      text: sorted.map(d => d.val.toFixed(1)),
      textposition: 'outside',
      textfont: { color: '#94a3b8', size: 11 },
      hovertemplate: '%{x}: <b>%{y:.1f}</b> / 10<extra></extra>',
    },
  ];

  const shapes = [];
  if (secAvg != null) {
    // sector avg reference line — horizontal across bars (using axis value on y)
  }

  const annotations = [];
  if (secAvg != null) {
    annotations.push({
      x: sorted.length - 0.5, y: secAvg,
      text: `Sector avg ${secAvg.toFixed(1)}`,
      showarrow: false,
      font: { size: 9, color: 'rgba(148,163,184,.7)' },
      xanchor: 'right',
      bgcolor: 'rgba(12,22,41,.7)',
      borderpad: 3,
    });
    shapes.push({
      type: 'line',
      x0: -0.5, x1: sorted.length - 0.5,
      y0: secAvg, y1: secAvg,
      line: { color: 'rgba(148,163,184,.35)', width: 1.5, dash: 'dot' },
    });
  }

  Plotly.newPlot(el, traces, {
    paper_bgcolor: 'transparent',
    plot_bgcolor:  'rgba(12,22,41,.5)',
    font:   { color: '#94a3b8', family: 'DM Sans, sans-serif', size: 11 },
    margin: { l: 50, r: 20, t: 30, b: 90 },
    xaxis: {
      tickangle: -30,
      tickfont: { color: '#94a3b8', size: 10 },
      gridcolor: 'rgba(255,255,255,.05)',
    },
    yaxis: {
      title: { text: 'Risk Score (0–10)', font: { size: 11, color: '#64748b' } },
      range: [0, 10.5],
      gridcolor: 'rgba(255,255,255,.05)',
      tickfont: { color: '#94a3b8' },
    },
    shapes,
    annotations,
    bargap: 0.3,
  }, { displayModeBar: false, responsive: true });
}

// ── P3-A: Water & Waste Peer Benchmarking ────────────────────────────────────

function _wwStats(company, field) {
  const sec  = (company.sector || '').trim();
  const self = company.risk_breakdown?.[field];
  const peers = allCompanies
    .filter(c => (c.sector||'').trim() === sec && c.risk_breakdown?.[field] != null);
  if (!peers.length) return { self, mean: null, std: null, z: null, pct: null, n: 0 };
  const vals = peers.map(c => c.risk_breakdown[field]);
  const n    = vals.length;
  const mean = vals.reduce((s, v) => s + v, 0) / n;
  const std  = Math.sqrt(vals.reduce((s, v) => s + (v - mean) ** 2, 0) / n) || 0.001;
  const z    = self != null ? ((self - mean) / std) : null;
  const below = vals.filter(v => v < (self ?? Infinity)).length;
  const pct  = self != null ? Math.round((below / n) * 100) : null;
  return { self, mean, std, z, pct, n };
}

function renderDDWWBench(profile) {
  const wSt = _wwStats(profile, 'water_intensity');
  const wtSt = _wwStats(profile, 'waste_intensity');
  const fe   = profile.financial_exposure || {};

  function statCard(label, st, rawVal, rawUnit) {
    if (st.self == null) return `
      <div class="ww-stat-card">
        <div class="ww-stat-card__label">${label}</div>
        <div class="ww-stat-card__na">Not disclosed</div>
      </div>`;
    const zCol  = Math.abs(st.z) > 2 ? '#f87171' : Math.abs(st.z) > 1 ? '#fbbf24' : '#34d399';
    const flag  = Math.abs(st.z) > 2 ? '⚠ Statistical outlier' : Math.abs(st.z) > 1 ? '↑ Above average' : '✓ Within normal range';
    return `
      <div class="ww-stat-card">
        <div class="ww-stat-card__label">${label}</div>
        <div class="ww-stat-card__score" style="color:${zCol}">${st.self.toFixed(1)}<span style="font-size:.6em;color:#64748b">/10</span></div>
        <div class="ww-stat-card__row"><span>Sector mean</span><b>${st.mean?.toFixed(2) ?? '—'}</b></div>
        <div class="ww-stat-card__row"><span>Z-score</span><b style="color:${zCol}">${st.z != null ? (st.z > 0 ? '+' : '') + st.z.toFixed(2) : '—'}</b></div>
        <div class="ww-stat-card__row"><span>Percentile</span><b>${st.pct != null ? st.pct + 'th' : '—'}</b></div>
        <div class="ww-stat-card__flag" style="color:${zCol}">${flag}</div>
        ${rawVal != null ? `<div class="ww-stat-card__raw">${rawVal.toLocaleString('en-IN')} ${rawUnit}</div>` : ''}
      </div>`;
  }

  return `
  <div class="dd-section">
    <div class="dd-section-title">Water &amp; Waste Intensity Benchmarking</div>
    <p style="font-size:.8rem;color:#64748b;margin-bottom:16px">Intensity scores (0–10) compare this company against ${wSt.n || wtSt.n} sector peers. Z-score &gt;2 = statistical outlier requiring attention.</p>

    <div class="ww-stat-row">
      ${statCard('Water Intensity', wSt, fe.water_withdrawal_m3, 'm³/yr')}
      ${statCard('Waste Intensity', wtSt, fe.waste_tonnes, 'tonnes/yr')}
    </div>

    <div id="ww-chart" style="height:340px;width:100%;margin:16px 0 8px"></div>
    <p style="font-size:.72rem;color:#475569;margin-top:4px">Each dot = one company in the same sector. Dot size = revenue (₹Cr). This company shown in bright colour. Grey band = ±1σ from sector mean.</p>
    <p class="dd-disclaimer">Intensity scores derived from BRSR-disclosed absolute volumes normalised by revenue. Outlier threshold: |z| &gt; 2 (95th percentile). Sector: ${esc(profile.sector || '—')}.</p>
  </div>`;
}

function _plotWWScatter(profile) {
  const el = document.getElementById('ww-chart');
  if (!el || typeof Plotly === 'undefined') return;
  const sec = (profile.sector || '').trim();
  const peers = allCompanies.filter(c => (c.sector||'').trim() === sec && c.risk_breakdown?.water_intensity != null && c.risk_breakdown?.waste_intensity != null);
  if (peers.length < 2) { el.innerHTML = '<div style="color:#475569;text-align:center;padding:60px 0;font-size:.85rem">Not enough sector peers with both water and waste data.</div>'; return; }

  const isSelf = c => c.company_name === profile.company_name;
  const others = peers.filter(c => !isSelf(c));
  const self   = peers.find(isSelf);

  const maxRev = Math.max(...peers.map(c => c.revenue_crore || 1));
  const sizeOf = c => 6 + Math.round((c.revenue_crore || 1) / maxRev * 18);

  const wSt  = _wwStats(profile, 'water_intensity');
  const wtSt = _wwStats(profile, 'waste_intensity');

  const traces = [];

  // Peers
  traces.push({
    type: 'scatter', mode: 'markers',
    name: 'Sector peers',
    x: others.map(c => c.risk_breakdown.water_intensity),
    y: others.map(c => c.risk_breakdown.waste_intensity),
    text: others.map(c => c.company_name),
    hovertemplate: '<b>%{text}</b><br>Water: %{x:.1f} · Waste: %{y:.1f}<extra></extra>',
    marker: { color: 'rgba(148,163,184,.35)', size: others.map(sizeOf), line: { width: 0 } },
  });

  // This company
  if (self) {
    const col = (Math.abs(wSt.z ?? 0) > 2 || Math.abs(wtSt.z ?? 0) > 2) ? '#f87171' : '#34d399';
    traces.push({
      type: 'scatter', mode: 'markers+text',
      name: profile.company_name,
      x: [self.risk_breakdown.water_intensity],
      y: [self.risk_breakdown.waste_intensity],
      text: [profile.company_name.length > 18 ? profile.company_name.slice(0,16)+'…' : profile.company_name],
      textposition: 'top center',
      textfont: { color: col, size: 10 },
      hovertemplate: `<b>${esc(profile.company_name)}</b><br>Water: %{x:.1f} · Waste: %{y:.1f}<extra></extra>`,
      marker: { color: col, size: 16, line: { color: '#0f1e35', width: 2 } },
    });
  }

  const shapes = [];
  if (wSt.mean != null && wSt.std != null && wtSt.mean != null && wtSt.std != null) {
    shapes.push({ type:'rect', x0: wSt.mean - wSt.std, x1: wSt.mean + wSt.std, y0: wtSt.mean - wtSt.std, y1: wtSt.mean + wtSt.std, fillcolor: 'rgba(148,163,184,.06)', line: { color: 'rgba(148,163,184,.15)', width: 1 } });
    shapes.push({ type:'line', x0: wSt.mean, x1: wSt.mean, y0: 0, y1: 10, line: { color: 'rgba(148,163,184,.25)', dash:'dot', width: 1 } });
    shapes.push({ type:'line', x0: 0, x1: 10, y0: wtSt.mean, y1: wtSt.mean, line: { color: 'rgba(148,163,184,.25)', dash:'dot', width: 1 } });
  }

  Plotly.newPlot(el, traces, {
    paper_bgcolor: 'transparent', plot_bgcolor: 'rgba(12,22,41,.5)',
    font: { color: '#94a3b8', family: 'DM Sans, sans-serif', size: 11 },
    margin: { l: 60, r: 20, t: 20, b: 60 },
    xaxis: { title: { text: 'Water Intensity (0–10)', font: { size: 11, color: '#64748b' } }, range: [-0.2, 10.5], gridcolor: 'rgba(255,255,255,.05)', tickfont: { color: '#94a3b8' } },
    yaxis: { title: { text: 'Waste Intensity (0–10)', font: { size: 11, color: '#64748b' } }, range: [-0.2, 10.5], gridcolor: 'rgba(255,255,255,.05)', tickfont: { color: '#94a3b8' } },
    legend: { x: 1, xanchor: 'right', y: 1, font: { size: 10 }, bgcolor: 'rgba(12,22,41,.7)' },
    shapes,
  }, { displayModeBar: false, responsive: true });
}

// ── P3-E: ESG Data Completeness Advisor ──────────────────────────────────────

const DG_FIELDS = [
  { group: 'GHG Emissions',    fields: [
    { label: 'Scope 1 Emissions (tCO₂e)',     key: 'fe.scope1_emissions_tco2e',  weight: 3 },
    { label: 'Scope 2 Emissions (tCO₂e)',     key: 'fe.scope2_emissions_tco2e',  weight: 3 },
    { label: 'Scope 3 Emissions (tCO₂e)',     key: 'fe.scope3_emissions_tco2e',  weight: 2 },
  ]},
  { group: 'Resource Use',     fields: [
    { label: 'Water Withdrawal (m³)',          key: 'fe.water_withdrawal_m3',     weight: 2 },
    { label: 'Waste Generated (tonnes)',       key: 'fe.waste_tonnes',            weight: 2 },
  ]},
  { group: 'Risk Scores',      fields: [
    { label: 'GHG Intensity Score',            key: 'rb.ghg_intensity',           weight: 2 },
    { label: 'Water Intensity Score',          key: 'rb.water_intensity',         weight: 1 },
    { label: 'Waste Intensity Score',          key: 'rb.waste_intensity',         weight: 1 },
    { label: 'EPR Exposure Score',             key: 'rb.epr_exposure',            weight: 1 },
    { label: 'Compliance Risk Score',          key: 'rb.compliance_risk',         weight: 2 },
    { label: 'HR Risk Score',                  key: 'rb.hr_risk',                 weight: 1 },
    { label: 'Governance Risk Score',          key: 'rb.governance_risk',         weight: 1 },
  ]},
  { group: 'Governance',       fields: [
    { label: 'BRSR Assurance Level',           key: 'gov.brsr_assurance',         weight: 2 },
    { label: 'Anti-Corruption Policy',         key: 'gov.anti_corruption_policy', weight: 1 },
  ]},
  { group: 'Market Data',      fields: [
    { label: 'Market Capitalisation (₹Cr)',    key: 'md.market_cap_crore',        weight: 1 },
    { label: '1-Year Stock Return (%)',        key: 'md.return_1y_pct',           weight: 1 },
  ]},
];

function _dgGet(profile, key) {
  const fe  = profile.financial_exposure || {};
  const rb  = profile.risk_breakdown || {};
  const gov = profile.governance || {};
  const md  = profile.market_data || {};
  const [ns, field] = key.split('.');
  const src = { fe, rb, gov, md }[ns];
  const val = src?.[field];
  return (val !== null && val !== undefined && val !== '' && val !== 'Unknown') ? val : null;
}

function renderDDDataGaps(profile) {
  let totalWeight = 0, disclosedWeight = 0;
  const allFields = [];
  DG_FIELDS.forEach(group => group.fields.forEach(f => {
    const val = _dgGet(profile, f.key);
    totalWeight    += f.weight;
    if (val != null) disclosedWeight += f.weight;
    allFields.push({ ...f, group: group.group, val, disclosed: val != null });
  }));

  const pct = Math.round((disclosedWeight / totalWeight) * 100);
  const gaugeCol = pct >= 75 ? '#34d399' : pct >= 50 ? '#fbbf24' : '#f87171';
  const gaugeLabel = pct >= 75 ? 'Good' : pct >= 50 ? 'Partial' : 'Poor';

  const missing = allFields.filter(f => !f.disclosed).sort((a, b) => b.weight - a.weight);
  const top3    = missing.slice(0, 3);

  const groupRows = DG_FIELDS.map(g => {
    const rows = g.fields.map(f => {
      const val = _dgGet(profile, f.key);
      const dis = val != null;
      const dispVal = dis ? (typeof val === 'number' ? val.toLocaleString('en-IN') : val) : null;
      return `<tr>
        <td class="dg-field-name">${f.label}</td>
        <td class="dg-field-val">${dis ? dispVal : '<span class="dg-missing">Missing</span>'}</td>
        <td class="dg-field-weight">${'●'.repeat(f.weight)}<span style="color:#1e2d45">${'●'.repeat(3 - f.weight)}</span></td>
        <td class="dg-field-status ${dis ? 'dg-ok' : 'dg-gap'}">${dis ? '✓' : '✕'}</td>
      </tr>`;
    }).join('');
    return `<tr class="dg-group-row"><td colspan="4" class="dg-group-label">${g.group}</td></tr>${rows}`;
  }).join('');

  return `
  <div class="dd-section">
    <div class="dd-section-title">ESG Data Completeness</div>

    <div class="dg-summary-row">
      <div class="dg-gauge">
        <svg viewBox="0 0 120 70" width="160" height="95">
          <path d="M10,65 A50,50 0 0,1 110,65" fill="none" stroke="rgba(255,255,255,.06)" stroke-width="12" stroke-linecap="round"/>
          <path d="M10,65 A50,50 0 0,1 110,65" fill="none" stroke="${gaugeCol}" stroke-width="12" stroke-linecap="round"
            stroke-dasharray="${Math.PI * 50}" stroke-dashoffset="${Math.PI * 50 * (1 - pct/100)}" opacity=".85"/>
          <text x="60" y="60" text-anchor="middle" font-size="18" font-weight="800" fill="${gaugeCol}">${pct}%</text>
          <text x="60" y="72" text-anchor="middle" font-size="8" fill="#64748b">${gaugeLabel} coverage</text>
        </svg>
      </div>
      <div class="dg-summary-stats">
        <div class="dg-sum-row"><span>Fields disclosed</span><b style="color:#e2e8f0">${allFields.filter(f=>f.disclosed).length} / ${allFields.length}</b></div>
        <div class="dg-sum-row"><span>Weighted coverage</span><b style="color:${gaugeCol}">${pct}%</b></div>
        <div class="dg-sum-row"><span>Critical gaps</span><b style="color:${missing.filter(f=>f.weight>=3).length ? '#f87171':'#34d399'}">${missing.filter(f=>f.weight>=3).length}</b></div>
        <div class="dg-sum-row"><span>Sector</span><b style="color:#94a3b8">${esc(profile.sector||'—')}</b></div>
      </div>
      ${top3.length ? `
      <div class="dg-top3">
        <div class="dg-top3-title">Top gaps to fix first</div>
        ${top3.map((f, i) => `<div class="dg-top3-item"><span class="dg-top3-num">${i+1}</span><span>${f.label}</span><span class="dg-top3-impact">Impact: ${'★'.repeat(f.weight)}${'☆'.repeat(3-f.weight)}</span></div>`).join('')}
      </div>` : '<div class="dg-top3" style="color:#34d399;align-items:center;justify-content:center">✓ All high-priority fields disclosed</div>'}
    </div>

    <div class="table-wrap" style="margin-top:16px">
      <table class="dg-table">
        <thead><tr><th>Field</th><th>Disclosed Value</th><th>Priority</th><th>Status</th></tr></thead>
        <tbody>${groupRows}</tbody>
      </table>
    </div>
    <p class="dd-disclaimer" style="margin-top:12px">Priority (●) reflects impact on ESG risk score accuracy. 3 dots = critical. Data sourced from BRSR filings; missing fields may be available in annual reports not yet parsed.</p>
  </div>`;
}

// ── P3-B: CCTS Remediation Scorecard (Claude Haiku) ──────────────────────────

const CCTS_SECTORS = ['cement', 'aluminium', 'steel', 'iron', 'petrochemical', 'chlor-alkali', 'paper', 'pulp', 'power', 'thermal', 'refin'];

function _isCCTSSector(profile) {
  const sec  = (profile.sector || '').toLowerCase();
  const prod = (profile.products || '').toLowerCase();
  return CCTS_SECTORS.some(s => sec.includes(s) || prod.includes(s));
}

const CCTS_OBLIGATIONS = [
  { id: 'registration',  label: 'Phase I Registration',        deadline: '31 Dec 2026', desc: 'Register on BEE Carbon Credit Trading platform.' },
  { id: 'inventory',     label: 'GHG Inventory Submission',    deadline: '30 Sep 2026', desc: 'Submit verified Scope 1 inventory to BEE portal.' },
  { id: 'verification',  label: 'Third-party Verification',    deadline: '30 Sep 2026', desc: 'Scope 1 emissions verified by BEE-accredited body.' },
  { id: 'target_setting',label: 'GHG Intensity Target',        deadline: '31 Mar 2027', desc: 'GHG intensity reduction target agreed with BEE.' },
  { id: 'brsr_core',     label: 'BRSR Core Assurance',         deadline: 'FY2026-27',   desc: 'Mandatory for top 250 companies — 3rd party BRSR assurance.' },
  { id: 'scope2_report', label: 'Scope 2 Reporting',           deadline: 'FY2026-27',   desc: 'Scope 2 (market-based + location-based) must be reported separately.' },
];

function renderDDCCTS(profile) {
  const inScope = _isCCTSSector(profile);
  return `
  <div class="dd-section">
    <div class="dd-section-title">CCTS Carbon Credit Remediation Scorecard</div>
    <div class="ccts-scope-banner ${inScope ? 'ccts-scope-banner--in' : 'ccts-scope-banner--out'}">
      ${inScope
        ? `<b>⚡ In Scope:</b> ${esc(profile.sector)} falls within CCTS Phase I obligated sectors (BEE / MoP Carbon Credit Trading Scheme 2023).`
        : `<b>ℹ Out of Scope:</b> ${esc(profile.sector)} is not currently in CCTS Phase I. Monitor for Phase II expansion. Voluntary participation remains possible.`}
    </div>
    <div id="ccts-body">
      <div class="ccts-loading"><span class="ccts-spinner"></span> Generating CCTS scorecard via AI…</div>
    </div>
  </div>`;
}

async function loadCCTSScorecard(profile) {
  const el = document.getElementById('ccts-body');
  if (!el) return;

  const api = window._gcApiBase || localStorage.getItem('gc_api_base') || '';
  if (!api) {
    el.innerHTML = _renderCCTSFallback(profile);
    return;
  }

  try {
    const res = await fetch(api + '/api/ccts-scorecard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company_name: profile.company_name,
        sector: profile.sector,
        products: profile.products,
        scope1_emissions: profile.financial_exposure?.scope1_emissions_tco2e,
        scope2_emissions: profile.financial_exposure?.scope2_emissions_tco2e,
        brsr_assurance: profile.governance?.brsr_assurance,
        compliance_risk: profile.risk_breakdown?.compliance_risk,
        ghg_intensity: profile.risk_breakdown?.ghg_intensity,
        revenue_crore: profile.revenue_crore,
        esg_targets: profile.esg_targets,
      }),
      signal: AbortSignal.timeout(30000),
    });
    if (res.status === 429) { el.innerHTML = '<p style="color:#fbbf24;padding:20px">Rate limit reached — please wait 60 seconds and try again.</p>'; return; }
    if (!res.ok) throw new Error('API error');
    const data = await res.json();
    el.innerHTML = _renderCCTSResult(data, profile);
    _gcAiFeedback(el, 'ccts', profile.company_name);
  } catch {
    el.innerHTML = _renderCCTSFallback(profile);
  }
}

function _renderCCTSFallback(profile) {
  const fe  = profile.financial_exposure || {};
  const gov = profile.governance || {};
  const rb  = profile.risk_breakdown || {};
  const inScope = _isCCTSSector(profile);

  function _rag(condition, na) {
    if (na) return { cls: 'ccts-na', icon: '—', label: 'N/A' };
    if (condition === true)  return { cls: 'ccts-green',  icon: '✓', label: 'Compliant' };
    if (condition === false) return { cls: 'ccts-red',    icon: '✕', label: 'Action needed' };
    return { cls: 'ccts-amber', icon: '⚠', label: 'Partial / unclear' };
  }

  const checks = [
    { ...CCTS_OBLIGATIONS[0], rag: _rag(!inScope ? null : null, !inScope) },
    { ...CCTS_OBLIGATIONS[1], rag: _rag(fe.scope1_emissions_tco2e != null ? true : false, !inScope) },
    { ...CCTS_OBLIGATIONS[2], rag: _rag(gov.brsr_assurance && gov.brsr_assurance !== 'None' ? true : false, !inScope) },
    { ...CCTS_OBLIGATIONS[3], rag: _rag((profile.esg_targets||[]).some(t => /ghg|emission|carbon|intensity/i.test(t.metric||'')) ? true : false, !inScope) },
    { ...CCTS_OBLIGATIONS[4], rag: _rag(gov.brsr_assurance && gov.brsr_assurance !== 'None', false) },
    { ...CCTS_OBLIGATIONS[5], rag: _rag(fe.scope2_emissions_tco2e != null, false) },
  ];

  const rows = checks.map(c => `
    <tr class="ccts-row">
      <td class="ccts-obligation">${c.label}</td>
      <td class="ccts-deadline">${c.deadline}</td>
      <td><span class="${c.rag.cls}">${c.rag.icon} ${c.rag.label}</span></td>
      <td class="ccts-desc">${c.desc}</td>
    </tr>`).join('');

  const actions = checks.filter(c => c.rag.cls === 'ccts-red' && !c.rag.na).map(c =>
    `<li>📌 <b>${c.label}</b> — ${c.desc} Deadline: ${c.deadline}.</li>`).join('');

  return `
    <table class="ccts-table"><thead><tr><th>Obligation</th><th>Deadline</th><th>Status</th><th>Detail</th></tr></thead>
    <tbody>${rows}</tbody></table>
    ${actions ? `<div class="ccts-actions"><div class="ccts-actions-title">Priority Actions</div><ul>${actions}</ul></div>` : '<div class="ccts-actions" style="color:#34d399">✓ No critical gaps detected from available BRSR data.</div>'}
    <p class="dd-disclaimer" style="margin-top:10px">Static assessment from BRSR data — activate backend for AI-enhanced action plan. Not legal advice.</p>`;
}

function _renderCCTSResult(data, profile) {
  const obligations = data.obligations || [];
  const narrative   = data.narrative   || '';
  const actions     = data.actions     || [];

  const rows = obligations.map(o => {
    const ragCls = o.status === 'compliant' ? 'ccts-green' : o.status === 'partial' ? 'ccts-amber' : o.status === 'na' ? 'ccts-na' : 'ccts-red';
    const icon   = o.status === 'compliant' ? '✓' : o.status === 'partial' ? '⚠' : o.status === 'na' ? '—' : '✕';
    return `<tr class="ccts-row">
      <td class="ccts-obligation">${esc(o.label||'')}</td>
      <td class="ccts-deadline">${esc(o.deadline||'')}</td>
      <td><span class="${ragCls}">${icon} ${esc(o.status_label||o.status||'')}</span></td>
      <td class="ccts-desc">${esc(o.detail||'')}</td>
    </tr>`;
  }).join('');

  const actionItems = actions.map(a => `<li>${esc(a)}</li>`).join('');

  return `
    ${narrative ? `<div class="ccts-narrative">${esc(narrative)}</div>` : ''}
    <table class="ccts-table"><thead><tr><th>Obligation</th><th>Deadline</th><th>Status</th><th>Detail</th></tr></thead>
    <tbody>${rows}</tbody></table>
    ${actionItems ? `<div class="ccts-actions"><div class="ccts-actions-title">AI-Generated Priority Actions</div><ul>${actionItems}</ul></div>` : ''}
    <p class="dd-disclaimer" style="margin-top:10px">AI-generated assessment. Verify against latest BEE circulars. Not legal advice.</p>`;
}

// ── P3-C: TCFD Disclosure Gap Analysis (Claude Haiku) ────────────────────────

const TCFD_PILLARS = [
  {
    id: 'governance', label: 'Governance', icon: '🏛',
    elements: [
      { id: 'board_oversight',   label: 'Board oversight of climate risks',         dataKey: 'gov.anti_corruption_policy' },
      { id: 'mgmt_role',        label: 'Management role in climate assessment',    dataKey: null },
    ],
  },
  {
    id: 'strategy', label: 'Strategy', icon: '🎯',
    elements: [
      { id: 'physical_risks',   label: 'Physical climate risks identified',         dataKey: null },
      { id: 'transition_risks', label: 'Transition risks &amp; opportunities',      dataKey: 'rb.compliance_risk' },
      { id: 'scenario_analysis',label: 'Scenario analysis (1.5°C / 2°C)',           dataKey: null },
    ],
  },
  {
    id: 'risk_mgmt', label: 'Risk Management', icon: '🛡',
    elements: [
      { id: 'risk_id_process',  label: 'Process for identifying climate risks',     dataKey: 'rb.compliance_risk' },
      { id: 'risk_integration', label: 'Integration into overall risk management',  dataKey: null },
    ],
  },
  {
    id: 'metrics', label: 'Metrics &amp; Targets', icon: '📊',
    elements: [
      { id: 'scope1',           label: 'Scope 1 GHG emissions disclosed',           dataKey: 'fe.scope1_emissions_tco2e' },
      { id: 'scope2',           label: 'Scope 2 GHG emissions disclosed',           dataKey: 'fe.scope2_emissions_tco2e' },
      { id: 'scope3',           label: 'Scope 3 GHG emissions disclosed',           dataKey: 'fe.scope3_emissions_tco2e' },
      { id: 'climate_target',   label: 'Climate target with year set',              dataKey: null },
    ],
  },
];

function _tcfdDataCheck(profile, dataKey) {
  if (!dataKey) return null;
  return _dgGet(profile, dataKey);
}

function renderDDTCFD(profile) {
  return `
  <div class="dd-section">
    <div class="dd-section-title">TCFD Disclosure Gap Analysis
      <a href="tcfd-checker.html" target="_blank" style="margin-left:12px;font-size:.74rem;font-weight:600;color:#34d399;background:rgba(52,211,153,.1);border:1px solid rgba(52,211,153,.22);border-radius:8px;padding:3px 10px;text-decoration:none">📄 Upload Full Report →</a>
    </div>
    <p style="font-size:.8rem;color:#64748b;margin-bottom:16px">Task Force on Climate-related Financial Disclosures (TCFD) alignment check based on BRSR-filed data. SEBI mandates TCFD-aligned disclosures for top 1000 listed companies from FY2024-25. Upload the full sustainability report for a deeper PDF analysis.</p>
    <div id="tcfd-body">
      <div class="ccts-loading"><span class="ccts-spinner"></span> Analysing TCFD alignment…</div>
    </div>
  </div>`;
}

async function loadTCFDGap(profile) {
  const el = document.getElementById('tcfd-body');
  if (!el) return;

  const api = window._gcApiBase || localStorage.getItem('gc_api_base') || '';
  if (!api) {
    el.innerHTML = _renderTCFDFallback(profile);
    return;
  }

  try {
    const res = await fetch(api + '/api/tcfd-gap', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company_name: profile.company_name,
        sector: profile.sector,
        scope1_emissions: profile.financial_exposure?.scope1_emissions_tco2e,
        scope2_emissions: profile.financial_exposure?.scope2_emissions_tco2e,
        scope3_emissions: profile.financial_exposure?.scope3_emissions_tco2e,
        brsr_assurance: profile.governance?.brsr_assurance,
        compliance_risk: profile.risk_breakdown?.compliance_risk,
        governance_risk: profile.risk_breakdown?.governance_risk,
        esg_targets: profile.esg_targets,
        anti_corruption_policy: profile.governance?.anti_corruption_policy,
      }),
      signal: AbortSignal.timeout(30000),
    });
    if (res.status === 429) { el.innerHTML = '<p style="color:#fbbf24;padding:20px">Rate limit reached — please wait 60 seconds and try again.</p>'; return; }
    if (!res.ok) throw new Error('API error');
    const data = await res.json();
    el.innerHTML = _renderTCFDResult(data);
    _gcAiFeedback(el, 'tcfd', profile.company_name);
  } catch {
    el.innerHTML = _renderTCFDFallback(profile);
  }
}

function _tcfdPillarCard(pillar, profile, aiPillar) {
  const elements = pillar.elements.map(el => {
    let status = 'gap';
    let note   = 'Not found in BRSR data';
    if (aiPillar) {
      const aiEl = (aiPillar.elements || []).find(e => e.id === el.id);
      if (aiEl) { status = aiEl.status || 'gap'; note = aiEl.note || ''; }
    } else {
      const val = _tcfdDataCheck(profile, el.dataKey);
      if (val != null) { status = 'partial'; note = 'Signal found in BRSR data — verify full disclosure'; }
    }
    const icon = status === 'disclosed' ? '✓' : status === 'partial' ? '⚠' : '✕';
    const col  = status === 'disclosed' ? '#34d399' : status === 'partial' ? '#fbbf24' : '#f87171';
    return `<div class="tcfd-element">
      <span class="tcfd-el-icon" style="color:${col}">${icon}</span>
      <span class="tcfd-el-label">${el.label}</span>
      ${note ? `<span class="tcfd-el-note">${esc(note)}</span>` : ''}
    </div>`;
  }).join('');

  const disclosed = pillar.elements.filter(el => {
    if (aiPillar) {
      const aiEl = (aiPillar?.elements||[]).find(e => e.id === el.id);
      return aiEl?.status === 'disclosed';
    }
    return _tcfdDataCheck(profile, el.dataKey) != null;
  }).length;
  const total = pillar.elements.length;
  const pct   = Math.round((disclosed / total) * 100);
  const col   = pct >= 75 ? '#34d399' : pct >= 40 ? '#fbbf24' : '#f87171';

  return `
  <div class="tcfd-pillar">
    <div class="tcfd-pillar-header">
      <span class="tcfd-pillar-icon">${pillar.icon}</span>
      <span class="tcfd-pillar-label">${pillar.label}</span>
      <span class="tcfd-pillar-pct" style="color:${col}">${pct}%</span>
    </div>
    <div class="tcfd-elements">${elements}</div>
  </div>`;
}

function _renderTCFDFallback(profile) {
  const targets = profile.esg_targets || [];
  const hasClimateTarget = targets.some(t => /net.?zero|carbon|ghg|emission|climate|1\.5|2°c/i.test(t.metric || ''));
  const augmented = TCFD_PILLARS.map(p => ({
    ...p,
    elements: p.elements.map(el => {
      if (el.id === 'climate_target') return { ...el, dataKey: hasClimateTarget ? 'FOUND' : null };
      return el;
    }),
  }));

  const cards  = augmented.map(p => _tcfdPillarCard(p, profile, null)).join('');
  const allEls = augmented.flatMap(p => p.elements);
  const gaps   = allEls.filter(el => _tcfdDataCheck(profile, el.dataKey) == null);
  const gapList= gaps.slice(0, 5).map(g => `<li>${g.label}</li>`).join('');

  return `
    <div class="tcfd-grid">${cards}</div>
    ${gapList ? `<div class="ccts-actions"><div class="ccts-actions-title">Top TCFD Gaps (from BRSR data)</div><ul>${gapList}</ul></div>` : ''}
    <p class="dd-disclaimer" style="margin-top:10px">Static check against BRSR-filed data only. Activate backend for AI-enhanced gap narrative. TCFD recommendations: governance, strategy, risk management, metrics &amp; targets.</p>`;
}

function _renderTCFDResult(data) {
  const pillars = data.pillars || [];
  const summary = data.summary || '';
  const gaps    = data.gaps    || [];

  const cards = TCFD_PILLARS.map(p => {
    const aiPillar = pillars.find(ap => ap.id === p.id);
    return `
    <div class="tcfd-pillar">
      <div class="tcfd-pillar-header">
        <span class="tcfd-pillar-icon">${p.icon}</span>
        <span class="tcfd-pillar-label">${p.label}</span>
        ${aiPillar?.score != null ? `<span class="tcfd-pillar-pct" style="color:${aiPillar.score>=75?'#34d399':aiPillar.score>=40?'#fbbf24':'#f87171'}">${aiPillar.score}%</span>` : ''}
      </div>
      <div class="tcfd-elements">
        ${(aiPillar?.elements||[]).map(el => {
          const col  = el.status === 'disclosed' ? '#34d399' : el.status === 'partial' ? '#fbbf24' : '#f87171';
          const icon = el.status === 'disclosed' ? '✓' : el.status === 'partial' ? '⚠' : '✕';
          return `<div class="tcfd-element"><span class="tcfd-el-icon" style="color:${col}">${icon}</span><span class="tcfd-el-label">${esc(el.label||'')}</span>${el.note?`<span class="tcfd-el-note">${esc(el.note)}</span>`:''}</div>`;
        }).join('')}
      </div>
    </div>`;
  }).join('');

  return `
    ${summary ? `<div class="ccts-narrative">${esc(summary)}</div>` : ''}
    <div class="tcfd-grid">${cards}</div>
    ${gaps.length ? `<div class="ccts-actions"><div class="ccts-actions-title">AI-Identified TCFD Gaps</div><ul>${gaps.map(g=>`<li>${esc(g)}</li>`).join('')}</ul></div>` : ''}
    <p class="dd-disclaimer" style="margin-top:10px">AI-generated analysis from BRSR data. Verify against the company's full sustainability report. Not investment advice.</p>`;
}

// ── P4-C: India Physical Climate Risk by State ────────────────────────────────
// Risk scores 0–10 from NDMA District Risk Atlas 2020 + IMD/CEA state-level data
const _STATE_RISK = {
  AP:{ name:'Andhra Pradesh',    flood:8, drought:5, heatwave:7, cyclone:9 },
  AR:{ name:'Arunachal Pradesh', flood:6, drought:2, heatwave:2, cyclone:1 },
  AS:{ name:'Assam',             flood:9, drought:3, heatwave:4, cyclone:2 },
  BR:{ name:'Bihar',             flood:8, drought:5, heatwave:7, cyclone:2 },
  CG:{ name:'Chhattisgarh',      flood:5, drought:6, heatwave:6, cyclone:1 },
  CT:{ name:'Chhattisgarh',      flood:5, drought:6, heatwave:6, cyclone:1 },
  GA:{ name:'Goa',               flood:5, drought:2, heatwave:4, cyclone:5 },
  GJ:{ name:'Gujarat',           flood:5, drought:7, heatwave:8, cyclone:7 },
  HR:{ name:'Haryana',           flood:4, drought:6, heatwave:8, cyclone:1 },
  HP:{ name:'Himachal Pradesh',  flood:6, drought:3, heatwave:3, cyclone:1 },
  JK:{ name:'Jammu & Kashmir',   flood:5, drought:4, heatwave:2, cyclone:1 },
  JH:{ name:'Jharkhand',         flood:5, drought:6, heatwave:7, cyclone:1 },
  KA:{ name:'Karnataka',         flood:5, drought:7, heatwave:6, cyclone:4 },
  KL:{ name:'Kerala',            flood:7, drought:3, heatwave:4, cyclone:6 },
  MP:{ name:'Madhya Pradesh',    flood:5, drought:7, heatwave:8, cyclone:1 },
  MH:{ name:'Maharashtra',       flood:6, drought:7, heatwave:7, cyclone:4 },
  MN:{ name:'Manipur',           flood:6, drought:2, heatwave:3, cyclone:1 },
  ML:{ name:'Meghalaya',         flood:6, drought:2, heatwave:2, cyclone:1 },
  MZ:{ name:'Mizoram',           flood:5, drought:2, heatwave:2, cyclone:2 },
  NL:{ name:'Nagaland',          flood:5, drought:2, heatwave:2, cyclone:1 },
  OD:{ name:'Odisha',            flood:8, drought:6, heatwave:7, cyclone:9 },
  OR:{ name:'Odisha',            flood:8, drought:6, heatwave:7, cyclone:9 },
  PB:{ name:'Punjab',            flood:4, drought:5, heatwave:7, cyclone:1 },
  RJ:{ name:'Rajasthan',         flood:3, drought:9, heatwave:9, cyclone:2 },
  SK:{ name:'Sikkim',            flood:6, drought:1, heatwave:1, cyclone:1 },
  TN:{ name:'Tamil Nadu',        flood:6, drought:6, heatwave:6, cyclone:8 },
  TG:{ name:'Telangana',         flood:6, drought:7, heatwave:8, cyclone:3 },
  TR:{ name:'Tripura',           flood:6, drought:2, heatwave:4, cyclone:3 },
  UK:{ name:'Uttarakhand',       flood:7, drought:3, heatwave:3, cyclone:1 },
  UP:{ name:'Uttar Pradesh',     flood:7, drought:6, heatwave:8, cyclone:1 },
  WB:{ name:'West Bengal',       flood:8, drought:4, heatwave:6, cyclone:7 },
  DL:{ name:'Delhi',             flood:4, drought:5, heatwave:9, cyclone:1 },
  PY:{ name:'Puducherry',        flood:6, drought:4, heatwave:6, cyclone:7 },
  CH:{ name:'Chandigarh',        flood:3, drought:4, heatwave:7, cyclone:1 },
  AN:{ name:'Andaman & Nicobar', flood:5, drought:2, heatwave:5, cyclone:8 },
  LA:{ name:'Ladakh',            flood:4, drought:5, heatwave:1, cyclone:1 },
};

function _stateCodeFromCIN(cin) {
  if (!cin || cin.length < 6) return null;
  return cin.substring(4, 6).toUpperCase();
}

function _stateRiskOverall(r) {
  return Math.round(((r.flood + r.drought + r.heatwave + r.cyclone) / 4) * 10) / 10;
}

function _riskColor(val) {
  if (val >= 7) return '#f87171';
  if (val >= 5) return '#fbbf24';
  return '#34d399';
}

function renderClimateRisk() {
  const el = document.getElementById('tab-climaterisk');
  if (!el || !allCompanies.length) return;

  // Aggregate companies by state
  const stateMap = {};
  allCompanies.forEach(c => {
    const code = _stateCodeFromCIN(c.cin);
    if (!code || !_STATE_RISK[code]) return;
    if (!stateMap[code]) stateMap[code] = { risk: _STATE_RISK[code], companies: [] };
    stateMap[code].companies.push(c);
  });

  // Sort states by overall risk descending
  const sorted = Object.entries(stateMap)
    .map(([code, d]) => ({ code, ...d.risk, overall: _stateRiskOverall(d.risk), companies: d.companies }))
    .sort((a, b) => b.overall - a.overall);

  // Plotly bar
  const hasPlotly = typeof Plotly !== 'undefined';
  const stateLabels = sorted.map(s => s.name || s.code);
  const overallVals = sorted.map(s => s.overall);
  const colors      = overallVals.map(v => _riskColor(v));

  const companyRows = sorted.map(s => {
    const topCo = s.companies.slice(0, 3).map(c =>
      `<span class="cr-chip" onclick="openDeepDive('${(c.company_name||'').replace(/'/g,"\\'")}')">
        ${esc(c.company_name.slice(0,30))}
      </span>`
    ).join('');
    return `<tr>
      <td class="cr-state">${esc(s.name || s.code)}</td>
      <td><span class="cr-score" style="color:${_riskColor(s.flood)}">${s.flood.toFixed(1)}</span></td>
      <td><span class="cr-score" style="color:${_riskColor(s.drought)}">${s.drought.toFixed(1)}</span></td>
      <td><span class="cr-score" style="color:${_riskColor(s.heatwave)}">${s.heatwave.toFixed(1)}</span></td>
      <td><span class="cr-score" style="color:${_riskColor(s.cyclone)}">${s.cyclone.toFixed(1)}</span></td>
      <td><strong style="color:${_riskColor(s.overall)}">${s.overall.toFixed(1)}</strong></td>
      <td class="cr-count">${s.companies.length}</td>
      <td class="cr-chips">${topCo}${s.companies.length>3?`<span class="cr-more">+${s.companies.length-3}</span>`:''}</td>
    </tr>`;
  }).join('');

  el.innerHTML = `
  <div class="dm-intro">
    <h3 class="dm-intro__title">India Physical Climate Risk by State</h3>
    <p class="dm-intro__sub">State-level physical climate hazard exposure for portfolio companies, derived from NDMA District Risk Atlas 2020 and IMD historical data. Risk scores 0–10 (higher = greater exposure). State identified from company CIN registration code.</p>
  </div>
  <div id="cr-chart" style="height:320px;width:100%;margin-bottom:20px"></div>
  <div class="cr-legend-row">
    <span class="cr-leg cr-leg--high">High ≥7</span>
    <span class="cr-leg cr-leg--med">Medium 5–6.9</span>
    <span class="cr-leg cr-leg--low">Low &lt;5</span>
    <span class="cr-leg cr-leg--na" style="margin-left:auto">${allCompanies.filter(c=>!_STATE_RISK[_stateCodeFromCIN(c.cin)||'']).length} companies with unknown state (CIN unresolvable)</span>
  </div>
  <div class="table-wrap" style="margin-top:16px">
    <table class="cr-table">
      <thead><tr>
        <th>State</th><th>Flood</th><th>Drought</th><th>Heatwave</th><th>Cyclone</th><th>Overall</th><th>Companies</th><th>Top Companies (click to open)</th>
      </tr></thead>
      <tbody>${companyRows}</tbody>
    </table>
  </div>`;

  if (hasPlotly) {
    Plotly.newPlot('cr-chart', [{
      type: 'bar', orientation: 'h',
      x: overallVals.slice().reverse(),
      y: stateLabels.slice().reverse(),
      marker: { color: colors.slice().reverse() },
      hovertemplate: '<b>%{y}</b><br>Overall Risk: %{x:.1f}<extra></extra>',
    }], {
      paper_bgcolor:'transparent', plot_bgcolor:'transparent',
      margin: { l:140, r:20, t:10, b:40 },
      xaxis: { range:[0,10], gridcolor:'rgba(255,255,255,.06)', tickfont:{ color:'#94a3b8',size:11 }, title:{ text:'Overall Risk Score (0–10)', font:{ color:'#64748b',size:11 } } },
      yaxis: { tickfont:{ color:'#e2e8f0',size:11 }, automargin:true },
      font: { family:'DM Sans,sans-serif' },
    }, { displayModeBar:false, responsive:true });
  }
}
window.renderClimateRisk = renderClimateRisk;


// ── P4-D: SEBI/BSE/NGT ESG Event Alert Feed ──────────────────────────────────
const _EV_CATS   = ['All','Regulatory','Environmental','Governance','Market'];
const _EV_SEVS   = ['All','Critical','High','Medium'];
let _evFilter    = { cat:'All', sev:'All', watchOnly:false, search:'' };
let _evRendered  = false;

function renderESGEvents() {
  const el = document.getElementById('tab-esgEvents');
  if (!el) return;

  if (!_ESG_EVENTS || !_ESG_EVENTS.events) {
    el.innerHTML = `<div class="dm-intro"><h3 class="dm-intro__title">ESG Event Alert Feed</h3>
      <p class="dm-intro__sub">No event data found. Place <code>assets/data/esg_events.json</code> to enable this feed.</p></div>`;
    return;
  }

  _evRendered = true;
  _applyEventsRender(el);
}

function _applyEventsRender(el) {
  const watchlist = _WL.list();
  let events = (_ESG_EVENTS.events || []).slice().sort((a, b) => b.date.localeCompare(a.date));

  // Apply filters
  if (_evFilter.cat !== 'All')    events = events.filter(e => e.category === _evFilter.cat);
  if (_evFilter.sev !== 'All')    events = events.filter(e => e.severity === _evFilter.sev);
  if (_evFilter.watchOnly)        events = events.filter(e => !e.companies?.length || e.companies.some(co => watchlist.includes(co)) || (e.affected_sectors||[]).includes('All'));
  if (_evFilter.search.trim())    {
    const q = _evFilter.search.toLowerCase();
    events = events.filter(e => (e.title+e.summary+e.source).toLowerCase().includes(q));
  }

  const sevColor = { Critical:'#f87171', High:'#fb923c', Medium:'#fbbf24', Low:'#94a3b8' };
  const catIcon  = { Regulatory:'⚖', Environmental:'🌿', Governance:'🏛', Market:'📈', ESG:'🌍' };

  const rows = events.map(e => {
    const dt = e.date ? new Date(e.date).toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'}) : '—';
    const sc = sevColor[e.severity] || '#94a3b8';
    const ci = catIcon[e.category]  || '📋';
    const sectors = (e.affected_sectors||[]).join(', ') || 'All sectors';
    const companies = (e.companies||[]).slice(0,3).map(co=>`<span class="ev-co-chip" onclick="openDeepDive('${co.replace(/'/g,"\\'")}')">
      ${esc(co.slice(0,25))}</span>`).join('');
    return `
    <div class="ev-card ev-card--${(e.severity||'').toLowerCase()}">
      <div class="ev-card__top">
        <span class="ev-source">${ci} ${esc(e.source||'—')}</span>
        <span class="ev-date">${dt}</span>
        <span class="ev-sev" style="color:${sc}">${e.severity||'—'}</span>
      </div>
      <div class="ev-title">${esc(e.title||'')}</div>
      <div class="ev-summary">${esc(e.summary||'')}</div>
      <div class="ev-footer">
        <span class="ev-sectors">Sectors: ${esc(sectors)}</span>
        ${companies ? `<span class="ev-cos">${companies}</span>` : ''}
        ${e.reference ? `<span class="ev-ref">Ref: ${esc(e.reference)}</span>` : ''}
      </div>
    </div>`;
  }).join('') || '<div style="text-align:center;padding:40px;color:#64748b">No events match current filters.</div>';

  const filterBar = `
  <div class="ev-filters">
    <div class="ev-filter-group">
      ${_EV_CATS.map(c=>`<button class="ev-filter-btn${_evFilter.cat===c?' ev-filter-btn--active':''}" onclick="window.setEvFilter('cat',${JSON.stringify(c)})">${c}</button>`).join('')}
    </div>
    <div class="ev-filter-group" style="margin-top:6px">
      ${_EV_SEVS.map(s=>`<button class="ev-filter-btn${_evFilter.sev===s?' ev-filter-btn--active':''}" onclick="window.setEvFilter('sev',${JSON.stringify(s)})">${s}</button>`).join('')}
      <button class="ev-filter-btn${_evFilter.watchOnly?' ev-filter-btn--active':''}" onclick="window.setEvFilter('watchOnly',${!_evFilter.watchOnly})" style="margin-left:8px">Watchlist Only</button>
    </div>
    <div class="ev-search-wrap" style="margin-top:8px">
      <input class="ev-search" type="search" placeholder="Search events…" value="${esc(_evFilter.search)}"
        oninput="window.setEvFilter('search',this.value)">
    </div>
    <div class="ev-meta" style="margin-top:6px;font-size:.75rem;color:#64748b">
      ${events.length} event${events.length!==1?'s':''} · Updated ${_ESG_EVENTS.updated_at||'—'}
    </div>
  </div>`;

  el.innerHTML = `
  <div class="dm-intro">
    <h3 class="dm-intro__title">ESG Event Alert Feed</h3>
    <p class="dm-intro__sub">Regulatory circulars, enforcement actions, and ESG-relevant market events from SEBI, BSE, NGT, and MoEFCC. Filter by category, severity, or watchlist companies.</p>
  </div>
  ${filterBar}
  <div class="ev-cards-wrap">${rows}</div>`;
}

window.setEvFilter = function(key, val) {
  _evFilter[key] = val;
  const el = document.getElementById('tab-esgEvents');
  if (el) _applyEventsRender(el);
};
window.renderESGEvents = renderESGEvents;


// Make openDeepDive callable from screener rows
window.openDeepDive = openDeepDive;

// ── Regulation Calendar ───────────────────────────────────────────────────────
const CALENDAR_DEADLINES = [
  // EPR — Battery
  { date:'2026-08-15', title:'EPR Annual Return — Batteries FY 2025-26', category:'EPR',    urgency:'Critical', rule:'Battery Waste Management Rules 2022', body:'CPCB',  detail:'Filing of Annual Return for all registered Producers, Recyclers and Refurbishers under Battery Waste Management Rules. Extended deadline.' },
  { date:'2026-04-30', title:'EPR Battery Certificate generation deadline FY 2025-26', category:'EPR', urgency:'High', rule:'Battery Waste Management Rules 2022', body:'CPCB', detail:'Last date for waste battery recyclers to generate EPR credits/certificates for FY 2025-26 on the eprbattery.cpcb.gov.in portal.' },
  { date:'2027-08-15', title:'EPR Annual Return — Batteries FY 2026-27', category:'EPR',    urgency:'Medium', rule:'Battery Waste Management Rules 2022', body:'CPCB',  detail:'Annual return filing deadline for next cycle. Mark calendar now.' },

  // EPR — Plastics
  { date:'2026-06-30', title:'EPR Annual Return — Plastics FY 2025-26',   category:'EPR',    urgency:'Critical', rule:'Plastic Waste Management Rules 2016 (amended 2022)', body:'CPCB', detail:'PIBOs and PWPs must file annual EPR compliance return on eprplastic.cpcb.gov.in for FY 2025-26 plastic waste obligations.' },
  { date:'2026-03-31', title:'EPR Plastic — Credit procurement deadline FY 2025-26', category:'EPR', urgency:'High', rule:'Plastic Waste Management Rules', body:'CPCB', detail:'Last date for PIBOs to procure EPR certificates from registered Plastic Waste Processors to meet recycling targets for the year.' },

  // EPR — E-Waste
  { date:'2026-06-30', title:'EPR Annual Return — E-Waste FY 2025-26',    category:'EPR',    urgency:'Critical', rule:'E-Waste (Management) Rules 2022', body:'CPCB', detail:'Producers, recyclers and refurbishers must file annual compliance return on eprewaste.cpcb.gov.in. 70% recycling target for FY 2025-26.' },
  { date:'2027-06-30', title:'EPR E-Waste recycling target rises to 80%', category:'EPR',    urgency:'Medium',   rule:'E-Waste (Management) Rules 2022', body:'CPCB', detail:'Recycling obligation increases from 70% (FY25-26) to 80% from FY 2026-27 onwards for established producers.' },

  // EPR — Tyres
  { date:'2026-08-15', title:'EPR Annual Return — Waste Tyres FY 2024-25 (extended)', category:'EPR', urgency:'High', rule:'Waste Tyre EPR Notification 2022', body:'CPCB', detail:'Annual Return for FY 2024-25 extended to 15 August 2026. Contact: wastetyre.cpcb@gov.in' },
  { date:'2026-04-30', title:'EPR Tyre Certificate generation FY 2025-26', category:'EPR',   urgency:'High', rule:'Waste Tyre EPR Notification 2022', body:'CPCB', detail:'Waste tyre recyclers may submit sales data and generate denominated EPR certificates on or before 30 April 2026.' },

  // BRSR / SEBI
  { date:'2026-09-30', title:'BRSR Filing Deadline — Top 1000 companies FY 2025-26', category:'BRSR', urgency:'Critical', rule:'SEBI LODR Regulations / BRSR Framework', body:'SEBI', detail:'All top 1000 listed companies by market cap must include BRSR in Annual Report and file in XBRL format with BSE/NSE. AGM deadline is 6 months from year-end (Sep 30).' },
  { date:'2026-09-30', title:'BRSR Core — Reasonable Assurance (Top 150 companies)', category:'BRSR', urgency:'Critical', rule:'SEBI Circular Jul 2023 — BRSR Core', body:'SEBI', detail:'Top 150 listed entities must obtain reasonable assurance on BRSR Core indicators from a registered assurance provider. Part of SEBI\'s glide path for FY 2025-26.' },
  { date:'2027-09-30', title:'BRSR Core Assurance extends to Top 250 companies',     category:'BRSR', urgency:'Medium',   rule:'SEBI BRSR Core Glide Path', body:'SEBI', detail:'Reasonable assurance on BRSR Core mandatory for top 250 companies from FY 2026-27.' },
  { date:'2028-09-30', title:'BRSR Core Assurance extends to Top 500 companies',     category:'BRSR', urgency:'Medium',   rule:'SEBI BRSR Core Glide Path', body:'SEBI', detail:'Reasonable assurance on BRSR Core mandatory for top 500 companies from FY 2027-28.' },
  { date:'2026-12-31', title:'BRSR Value Chain disclosures — Top 250 companies',     category:'BRSR', urgency:'High',     rule:'SEBI BRSR Core — Value Chain', body:'SEBI', detail:'Top 250 listed entities must disclose BRSR Core indicators for value chain partners constituting ≥75% of purchases/sales from FY 2025-26.' },

  // BEE / Energy
  { date:'2026-06-30', title:'BEE PAT Cycle VIII — Baseline submission deadline',    category:'BEE',  urgency:'High',     rule:'Energy Conservation Act / PAT Scheme', body:'BEE', detail:'Designated Consumers under PAT Cycle VIII must submit baseline energy consumption data. Applies to energy-intensive industries.' },
  { date:'2026-09-30', title:'BEE Star Label renewal — Mandatory products',          category:'BEE',  urgency:'Medium',   rule:'Energy Conservation (Amendment) Act 2022', body:'BEE', detail:'Annual renewal of BEE star labels for mandatory star-labelled products. Manufacturers must comply or face market withdrawal.' },
  { date:'2026-03-31', title:'RPO Compliance — Renewable Purchase Obligation FY 2025-26', category:'BEE', urgency:'High', rule:'Electricity Act / RPO Guidelines', body:'MNRE/CERC', detail:'Obligated entities (discoms, open access consumers, captive users) must meet Renewable Purchase Obligation targets for FY 2025-26.' },

  // Carbon / CCTS
  { date:'2026-12-31', title:'CCTS — Phase I Obligated Entities Registration Deadline', category:'CCTS', urgency:'Critical', rule:'Carbon Credit Trading Scheme 2023', body:'BEE/MoP', detail:'Phase I covered entities (cement, aluminium, iron & steel, petrochemicals, chlor-alkali, paper) must complete registration on the Carbon Credit Trading platform.' },
  { date:'2027-03-31', title:'CCTS — First compliance period assessment',              category:'CCTS', urgency:'High',     rule:'Carbon Credit Trading Scheme 2023', body:'BEE/MoP', detail:'First formal assessment of GHG intensity targets for Phase I CCTS participants. Non-compliance attracts penalties under Energy Conservation Act.' },
  { date:'2026-09-30', title:'GHG Inventory — Third-party verification deadline',     category:'CCTS', urgency:'High',     rule:'SEBI BRSR Core / CCTS', body:'SEBI/BEE', detail:'Listed entities in CCTS sectors must have Scope 1 emissions verified by an accredited third party. Required for both BRSR Core assurance and CCTS compliance.' },

  // MoEFCC
  { date:'2026-06-05', title:'World Environment Day — MoEFCC Annual Report deadline', category:'MoEFCC', urgency:'Medium', rule:'Environment Protection Act', body:'MoEFCC', detail:'Annual Environmental Performance Reports due for entities under Environment Protection Act and related notifications.' },
  { date:'2026-07-31', title:'Hazardous Waste Annual Returns FY 2025-26',             category:'MoEFCC', urgency:'High',   rule:'Hazardous and Other Wastes (M&TBM) Rules 2016', body:'CPCB/SPCB', detail:'Occupiers and authorised operators must file annual returns for hazardous waste generation, storage, and disposal with respective SPCBs.' },
  { date:'2026-09-30', title:'Environmental Clearance — Annual Compliance Report',    category:'MoEFCC', urgency:'Medium', rule:'EIA Notification 2006', body:'MoEFCC', detail:'Project proponents with Environment Clearance must submit Half-Yearly Compliance Reports. Second half report due September 30.' },
];

function renderCalendar(categoryFilter = '', urgencyFilter = '') {
  const today = new Date();
  today.setHours(0,0,0,0);

  let deadlines = [...CALENDAR_DEADLINES];

  // Merge any dates from the regulations data
  (INTEL?.regulations || []).forEach(r => {
    if (r.date && r.title) {
      const parsed = new Date(r.date);
      if (!isNaN(parsed)) {
        deadlines.push({
          date: r.date,
          title: r.title,
          category: r.source || 'Regulation',
          urgency: r.urgency || 'Medium',
          rule: r.source || '',
          body: r.source || '',
          detail: r.description || '',
        });
      }
    }
  });

  // Filter
  if (categoryFilter) deadlines = deadlines.filter(d => d.category === categoryFilter);
  if (urgencyFilter)  deadlines = deadlines.filter(d => d.urgency === urgencyFilter);

  // Sort by date
  deadlines.sort((a, b) => new Date(a.date) - new Date(b.date));

  const container = document.getElementById('calTimeline');
  if (!deadlines.length) {
    container.innerHTML = '<p style="color:#64748b;padding:20px">No deadlines match the selected filters.</p>';
    return;
  }

  // Group by month
  const groups = {};
  deadlines.forEach(d => {
    const dt  = new Date(d.date);
    const key = `${dt.getFullYear()}-${String(dt.getMonth()+1).padStart(2,'0')}`;
    const lbl = dt.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' });
    if (!groups[key]) groups[key] = { label: lbl, items: [] };
    groups[key].items.push({ ...d, dt });
  });

  const urgencyCol = { Critical: '#f87171', High: '#fbbf24', Medium: '#34d399' };
  const categoryBadgeColor = {
    EPR: '#6366f1', BRSR: '#10b981', BEE: '#f59e0b',
    CCTS: '#06b6d4', MoEFCC: '#8b5cf6', Regulation: '#64748b',
  };

  let html = '';
  Object.entries(groups).forEach(([, group]) => {
    const allPast = group.items.every(d => d.dt < today);
    html += `<div class="cal-month${allPast ? ' cal-month--past' : ''}">
      <div class="cal-month-label">${group.label}</div>
      <div class="cal-items">`;

    group.items.forEach(d => {
      const isPast    = d.dt < today;
      const isToday   = d.dt.toDateString() === today.toDateString();
      const daysAway  = Math.round((d.dt - today) / 86400000);
      const urgColor  = urgencyCol[d.urgency] || '#94a3b8';
      const catColor  = categoryBadgeColor[d.category] || '#64748b';
      const dateStr   = d.dt.toLocaleDateString('en-IN', { day:'numeric', month:'short', year:'numeric' });

      let daysLabel = '';
      if (isPast) daysLabel = `<span class="cal-days-label cal-days-label--past">Passed</span>`;
      else if (isToday) daysLabel = `<span class="cal-days-label cal-days-label--today">Today</span>`;
      else if (daysAway <= 30) daysLabel = `<span class="cal-days-label cal-days-label--soon">${daysAway}d away</span>`;
      else daysLabel = `<span class="cal-days-label">${daysAway}d away</span>`;

      html += `
        <div class="cal-item${isPast?' cal-item--past':''}" style="border-left:3px solid ${isPast?'#334155':urgColor}">
          <div class="cal-item__top">
            <span class="cal-cat-badge" style="background:${catColor}22;color:${catColor}">${esc(d.category)}</span>
            <span class="cal-urg-badge" style="color:${isPast?'#475569':urgColor}">${esc(d.urgency)}</span>
            ${daysLabel}
          </div>
          <div class="cal-item__date">${dateStr}</div>
          <div class="cal-item__title">${esc(d.title)}</div>
          ${d.rule ? `<div class="cal-item__rule">${esc(d.rule)} · ${esc(d.body)}</div>` : ''}
          ${d.detail ? `<details class="cal-detail"><summary>Details</summary><p>${esc(d.detail)}</p></details>` : ''}
        </div>`;
    });

    html += '</div></div>';
  });

  container.innerHTML = html;
}

document.getElementById('calCategoryFilter').addEventListener('change', e =>
  renderCalendar(e.target.value, document.getElementById('calUrgencyFilter').value));
document.getElementById('calUrgencyFilter').addEventListener('change', e =>
  renderCalendar(document.getElementById('calCategoryFilter').value, e.target.value));

// ── Company Comparison ────────────────────────────────────────────────────────
let compareList = [];

function toggleCompare(name, e) {
  e.stopPropagation();
  const idx = compareList.indexOf(name);
  if (idx > -1) {
    compareList.splice(idx, 1);
  } else {
    if (compareList.length >= 10) return;
    compareList.push(name);
  }
  updateCompareTray();
  // refresh screener button states
  document.querySelectorAll('.cmp-btn').forEach(btn => {
    const n = btn.dataset.name;
    const active = compareList.includes(n);
    btn.classList.toggle('cmp-btn--active', active);
    btn.textContent = active ? '✓' : '+';
    btn.title = active ? 'Remove from compare' : 'Add to compare';
  });
}

function updateCompareTray() {
  const tray    = document.getElementById('cmpTray');
  const slots   = document.getElementById('cmpSlots');
  const countEl = document.getElementById('cmpCount');
  const btn     = document.getElementById('cmpBtn');

  countEl.textContent = `${compareList.length} / 10 selected`;
  btn.disabled = compareList.length < 2;
  tray.classList.toggle('cmp-tray--visible', compareList.length > 0);

  slots.innerHTML = compareList.map(name => {
    const c = allCompanies.find(x => x.company_name === name);
    if (!c) return '';
    const col = c.risk_tier === 'High' ? '#f87171' : c.risk_tier === 'Low' ? '#34d399' : '#fbbf24';
    return `<div class="cmp-slot">
      <span class="cmp-slot__score" style="color:${col}">${c.esg_risk_score}</span>
      <span class="cmp-slot__name">${esc(c.company_name.slice(0,22))}${c.company_name.length>22?'…':''}</span>
      <button class="cmp-slot__remove" onclick="toggleCompare('${esc(name)}',event)" aria-label="Remove">✕</button>
    </div>`;
  }).join('');
}

function clearCompare() {
  compareList = [];
  updateCompareTray();
  document.querySelectorAll('.cmp-btn').forEach(btn => {
    btn.classList.remove('cmp-btn--active');
    btn.textContent = '+';
  });
}

function openCompareModal() {
  if (compareList.length < 2) return;
  document.getElementById('cmpOverlay').classList.add('is-open');
  renderCompareModal();
}

document.getElementById('cmpClose').addEventListener('click', () =>
  document.getElementById('cmpOverlay').classList.remove('is-open'));
document.getElementById('cmpOverlay').addEventListener('click', e => {
  if (e.target === e.currentTarget) e.currentTarget.classList.remove('is-open');
});

const CMP_COLORS = ['#10b981','#6366f1','#f59e0b','#f87171','#38bdf8','#a78bfa','#34d399','#fb923c','#94a3b8','#e879f9'];
const CMP_DIM_LABELS = ['GHG Intensity','Water Intensity','Waste Intensity','EPR Exposure','Compliance Risk','HR Risk','Governance Risk'];
const CMP_DIM_KEYS   = ['ghg_intensity','water_intensity','waste_intensity','epr_exposure','compliance_risk','hr_risk','governance_risk'];

function renderCompareModal() {
  const companies = compareList.map(n => allCompanies.find(c => c.company_name === n)).filter(Boolean);
  const dims = [
    ['GHG Intensity',   'ghg_intensity'],
    ['Water Intensity', 'water_intensity'],
    ['Waste Intensity', 'waste_intensity'],
    ['EPR Exposure',    'epr_exposure'],
    ['Compliance Risk', 'compliance_risk'],
    ['HR Risk',         'hr_risk'],
    ['Governance Risk', 'governance_risk'],
  ];

  const tierCol = t => t==='High'?'#f87171':t==='Low'?'#34d399':'#fbbf24';

  // Radar chart
  let html = `<div id="cmpRadarChart" style="height:360px;width:100%;margin-bottom:24px"></div>`;

  // Header row
  html += `<div class="cmp-table">
    <div class="cmp-col cmp-col--label">
      <div class="cmp-cell cmp-cell--head"></div>
      <div class="cmp-cell cmp-cell--metric">Overall ESG Score</div>
      <div class="cmp-cell cmp-cell--metric">Risk Tier</div>
      <div class="cmp-cell cmp-cell--metric">Revenue (₹Cr)</div>
      <div class="cmp-cell cmp-cell--metric">Est. Compliance Cost</div>
      <div class="cmp-cell cmp-cell--metric cmp-cell--section">EPR Applicable</div>
      ${dims.map(([l]) => `<div class="cmp-cell cmp-cell--metric">${l}</div>`).join('')}
      <div class="cmp-cell cmp-cell--metric cmp-cell--section">Scope 1 Emissions</div>
      <div class="cmp-cell cmp-cell--metric">Waste (tonnes)</div>
      <div class="cmp-cell cmp-cell--metric">MSME Sourcing %</div>
      <div class="cmp-cell cmp-cell--metric cmp-cell--section">BRSR Assurance</div>
      <div class="cmp-cell cmp-cell--metric">Top Risk Factor</div>
    </div>`;

  companies.forEach(c => {
    const rb = c.risk_breakdown || {};
    const fe = c.financial_exposure || {};
    const sc = c.supply_chain || {};
    const gov = c.governance || {};
    const tc = tierCol(c.risk_tier);

    html += `<div class="cmp-col">
      <div class="cmp-cell cmp-cell--head">
        <div class="cmp-company-name">${esc(c.company_name)}</div>
        <div class="cmp-company-sector">${esc((c.sector||'').replace('Manufacturing — ','').slice(0,40))}</div>
      </div>
      <div class="cmp-cell">
        <span class="cmp-big-score" style="color:${tc}">${c.esg_risk_score}</span>
        <div class="cmp-score-bar"><div style="width:${c.esg_risk_score*10}%;background:${tc};height:4px;border-radius:2px"></div></div>
      </div>
      <div class="cmp-cell"><span class="risk-badge risk-badge--${c.risk_tier}">${c.risk_tier}</span></div>
      <div class="cmp-cell cmp-val">${c.revenue_crore ? '₹'+fmt(c.revenue_crore) : '—'}</div>
      <div class="cmp-cell cmp-val">${esc(fe.estimated_compliance_cost_band||'—')}</div>
      <div class="cmp-cell cmp-val cmp-cell--section">${esc(fe.epr_applicable||'Unknown')}</div>
      ${dims.map(([,k]) => {
        const v = rb[k] || 0;
        const col = v>=7?'#f87171':v>=4.5?'#fbbf24':'#34d399';
        return `<div class="cmp-cell">
          <span style="color:${col};font-weight:700;font-size:.95rem">${v.toFixed(1)}</span>
          <div class="cmp-score-bar"><div style="width:${v*10}%;background:${col};height:4px;border-radius:2px"></div></div>
        </div>`;
      }).join('')}
      <div class="cmp-cell cmp-val cmp-cell--section">${fe.scope1_emissions_tco2e != null ? fmt(fe.scope1_emissions_tco2e)+' tCO2e' : '—'}</div>
      <div class="cmp-cell cmp-val">${fe.waste_tonnes != null ? fmt(fe.waste_tonnes)+' T' : '—'}</div>
      <div class="cmp-cell cmp-val">${sc.msme_sourcing_pct != null ? sc.msme_sourcing_pct.toFixed(1)+'%' : '—'}</div>
      <div class="cmp-cell cmp-val cmp-cell--section">${esc(gov.brsr_assurance||'—')}</div>
      <div class="cmp-cell cmp-val" style="font-size:.8rem">${esc((c.top_risk_factors||[])[0]||'—')}</div>
    </div>`;
  });

  html += '</div>';

  // Share / copy link
  html += `<div class="cmp-share">
    <button class="cmp-share-btn" onclick="copyCompareLink()">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>
      Copy comparison link
    </button>
    <span id="cmpShareMsg" style="font-size:.78rem;color:#34d399;display:none">Link copied!</span>
  </div>`;

  document.getElementById('cmpBody').innerHTML = html;

  // Render Plotly radar after innerHTML is set
  const traces = companies.map((c, i) => {
    const values = CMP_DIM_KEYS.map(k => c.risk_breakdown?.[k] || 0);
    return {
      type: 'scatterpolar',
      name: c.company_name.slice(0, 28),
      r: [...values, values[0]],
      theta: [...CMP_DIM_LABELS, CMP_DIM_LABELS[0]],
      fill: 'toself',
      fillcolor: CMP_COLORS[i] + '22',
      line: { color: CMP_COLORS[i], width: 2 },
      marker: { color: CMP_COLORS[i], size: 4 },
      hovertemplate: `<b>${esc(c.company_name.slice(0, 28))}</b><br>%{theta}: %{r:.1f}/10<extra></extra>`,
    };
  });

  Plotly.newPlot('cmpRadarChart', traces, {
    paper_bgcolor: 'transparent',
    font: { color: '#94a3b8', family: 'DM Sans, sans-serif', size: 11 },
    polar: {
      radialaxis: { visible: true, range: [0, 10], gridcolor: 'rgba(255,255,255,.07)', tickfont: { color: '#94a3b8', size: 9 } },
      angularaxis: { tickfont: { color: '#cbd5e1', size: 11 }, gridcolor: 'rgba(255,255,255,.07)' },
      bgcolor: 'transparent',
    },
    legend: { font: { color: '#94a3b8' }, bgcolor: 'transparent', orientation: 'h', y: -0.12 },
    margin: { l: 60, r: 60, t: 20, b: 60 },
    height: 360,
  }, { displayModeBar: false, responsive: true });
}

function copyCompareLink() {
  const params = compareList.map(n => encodeURIComponent(n)).join(',');
  const url = `${location.origin}${location.pathname}?compare=${params}#screener`;
  navigator.clipboard.writeText(url).then(() => {
    const msg = document.getElementById('cmpShareMsg');
    msg.style.display = 'inline';
    setTimeout(() => { msg.style.display = 'none'; }, 2500);
  });
}

// ── Anomaly Detection ─────────────────────────────────────────────────────────
function renderAnomalies() {
  const flagged = allCompanies.filter(c => (c.anomaly_flags || []).length > 0)
    .sort((a, b) => b.esg_risk_score - a.esg_risk_score);
  const el = document.getElementById('anomalyList');
  if (!el) return;

  if (!flagged.length) {
    el.innerHTML = '<p style="color:#94a3b8;padding:20px">No anomalies detected in current dataset.</p>';
    return;
  }

  const rows = flagged.flatMap(c =>
    (c.anomaly_flags || []).map(f => `
      <tr style="cursor:pointer" onclick="openDeepDive('${esc(c.company_name)}')">
        <td class="company-name">${esc((c.company_name||'').slice(0, 28))}${c.company_name.length > 28 ? '…' : ''}</td>
        <td style="font-size:.78rem;color:#94a3b8">${esc((c.sector||'').replace('Manufacturing — ','').slice(0, 30))}</td>
        <td><span class="risk-badge risk-badge--${c.risk_tier}">${c.esg_risk_score}</span></td>
        <td><span class="anomaly-badge anomaly-badge--${f.severity}">${esc(f.label)}</span></td>
        <td style="font-size:.78rem;color:#94a3b8">${esc(f.detail)}</td>
      </tr>`)
  ).join('');

  el.innerHTML = `
    <p style="margin-bottom:14px;font-size:.82rem;color:#94a3b8">${flagged.length} companies flagged across ${flagged.reduce((s,c)=>(s+(c.anomaly_flags||[]).length),0)} signals</p>
    <div class="table-wrap">
      <table class="screener-table">
        <thead><tr><th>Company</th><th>Sector</th><th>ESG Score</th><th>Flag</th><th>Detail</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

// ── Board ESG Briefing PDF download ──────────────────────────────────────────
async function downloadBoardBriefing() {
  const company = _currentDDCompany;
  if (!company) return;
  const api = window._gcApiBase || localStorage.getItem('gc_api_base') || '';
  if (!api) { alert('Backend offline — start the BRSR backend first.'); return; }
  const btn = document.getElementById('ddBriefingBtn');
  if (btn) { btn.textContent = '⏳ Generating PDF…'; btn.disabled = true; }
  try {
    const res = await fetch(api + '/api/board-briefing', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company_name: company.company_name }),
      signal: AbortSignal.timeout(45000),
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || 'Server error'); }
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url;
    a.download = `Board_ESG_Briefing_${company.company_name.replace(/[^A-Za-z0-9]/g,'_').slice(0,40)}.pdf`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
    _track('board_briefing_downloaded', { company: company.company_name });
    if (btn) { btn.textContent = '✓ Downloaded'; setTimeout(() => { btn.textContent = '↓ Board Briefing PDF'; btn.disabled = false; }, 3000); }
  } catch (e) {
    alert(`Board briefing failed: ${e.message}`);
    if (btn) { btn.textContent = '↓ Board Briefing PDF'; btn.disabled = false; }
  }
}
window.downloadBoardBriefing = downloadBoardBriefing;

function printDeepDive() {
  const modal = document.getElementById('deepDiveOverlay');
  if (!modal) return;
  // Clone the modal content into a print-only container
  const clone = modal.querySelector('.deepdive-modal')?.cloneNode(true);
  if (!clone) { window.print(); return; }
  // Remove buttons from the clone
  clone.querySelectorAll('button, .deepdive-close, #ddBriefingBtn').forEach(el => el.remove());
  const wrap = document.createElement('div');
  wrap.id = 'gc-print-frame';
  wrap.appendChild(clone);
  document.body.appendChild(wrap);
  window.print();
  document.body.removeChild(wrap);
}
window.printDeepDive = printDeepDive;

// ── Sector ESG Heat Map (Feature 11) ─────────────────────────────────────────
let _hmClickAttached = false;

function renderHeatMap() {
  // Diagnostic: mark function as running
  const _dbgEl = document.getElementById('hm-total');
  if (_dbgEl) _dbgEl.textContent = '…';

  try {
  const sectorFilter = document.getElementById('hm-sector-filter')?.value || '';
  const sizeBy       = document.getElementById('hm-size-by')?.value || 'uniform';
  const countEl      = document.getElementById('hm-count');
  const div          = document.getElementById('heatmapChart');
  if (!div) { if (_dbgEl) _dbgEl.textContent = 'no-div'; return; }

  // Populate sector dropdown once
  const sel = document.getElementById('hm-sector-filter');
  if (sel && sel.options.length <= 1) {
    const sectors = [...new Set(allCompanies.map(c => _cleanSector(c.sector)))]
      .filter(s => s && s.length > 1 && !s.startsWith('NIC '))
      .sort();
    sectors.forEach(s => {
      const o = document.createElement('option');
      o.value = s; o.textContent = s.length > 45 ? s.slice(0, 43) + '…' : s;
      sel.appendChild(o);
    });
  }

  const data = sectorFilter
    ? allCompanies.filter(c => _cleanSector(c.sector) === sectorFilter)
    : allCompanies;

  if (countEl) countEl.textContent = `${data.length} companies`;

  // Populate KPI strip
  const high = data.filter(c => (c.esg_risk_score || 0) >= 6.5).length;
  const med  = data.filter(c => (c.esg_risk_score || 0) >= 4.5 && (c.esg_risk_score || 0) < 6.5).length;
  const low  = data.filter(c => (c.esg_risk_score || 0) < 4.5).length;
  const avg  = data.length ? data.reduce((s, c) => s + (c.esg_risk_score || 0), 0) / data.length : 0;
  const _set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  _set('hm-total',     data.length);
  _set('hm-avg-score', avg.toFixed(1));
  _set('hm-high-count', high);
  _set('hm-med-count',  med);
  _set('hm-low-count',  low);

  // Build treemap hierarchy
  const ids = ['__root__'], labels = ['All Companies'], parents = [''], values = [0];
  const colors = ['transparent'], texts = [''];

  const sectorGroups = {};
  data.forEach(c => {
    const sec = _cleanSector(c.sector) || 'Other';
    if (!sectorGroups[sec]) sectorGroups[sec] = [];
    sectorGroups[sec].push(c);
  });

  Object.entries(sectorGroups).sort((a, b) => b[1].length - a[1].length).forEach(([sec, cos]) => {
    const secId = 'sec:' + sec;
    const avg = cos.reduce((s, c) => s + (c.esg_risk_score || 0), 0) / cos.length;
    ids.push(secId); labels.push(sec.length > 28 ? sec.slice(0, 26) + '…' : sec);
    parents.push('__root__'); values.push(0);
    colors.push(avg >= 6.5 ? 'rgba(248,113,113,.2)' : avg >= 4.5 ? 'rgba(251,191,36,.15)' : 'rgba(52,211,153,.12)');
    texts.push(`${sec}<br>${cos.length} companies · avg ${avg.toFixed(1)}`);

    cos.forEach(c => {
      const v = sizeBy === 'revenue' ? (c.revenue_crore || 1)
              : sizeBy === 'market_cap' ? (c.market_data?.market_cap_crore || 1) : 1;
      const score = c.esg_risk_score || 0;
      ids.push(c.company_name); labels.push((c.company_name || '').slice(0, 20));
      parents.push(secId); values.push(Math.max(v, 1));
      colors.push(score >= 6.5 ? 'rgba(248,113,113,.85)' : score >= 4.5 ? 'rgba(251,191,36,.85)' : 'rgba(52,211,153,.85)');
      texts.push(`<b>${esc(c.company_name)}</b><br>ESG Risk: ${score} (${c.risk_tier})<br>${c.sector ? (c.sector).replace('Manufacturing — ','').slice(0,30) : ''}<br>${c.revenue_crore ? '₹' + c.revenue_crore.toFixed(0) + ' Cr revenue' : 'Revenue N/A'}`);
    });
  });

  Plotly.react(div, [{
    type: 'treemap', ids, labels, parents, values, text: texts,
    marker: { colors, line: { width: 0.5, color: '#0f172a' }, pad: { t: 18 } },
    hovertemplate: '%{text}<extra></extra>',
    textinfo: 'label', textfont: { size: 9, color: '#fff' },
    pathbar: { visible: true, side: 'top', thickness: 20 },
    tiling: { packing: 'squarify', pad: 2 },
    branchvalues: 'remainder',
  }], {
    paper_bgcolor: 'transparent',
    font: { color: '#94a3b8', family: 'DM Sans, sans-serif', size: 10 },
    margin: { l: 0, r: 0, t: 0, b: 0 }, height: 560,
  }, { displayModeBar: false, responsive: true });

  if (!_hmClickAttached) {
    _hmClickAttached = true;
    div.on('plotly_click', evData => {
      const pt = evData?.points?.[0];
      if (pt && pt.id && !String(pt.id).startsWith('sec:') && pt.id !== '__root__') {
        openDeepDive(pt.id);
      }
    });
  }
  } catch(e) {
    if (_dbgEl) _dbgEl.textContent = 'ERR:' + e.message;
    console.error('[GC] renderHeatMap error:', e);
  }
}
window.renderHeatMap = renderHeatMap;

// Re-expose for HTML onclick
window.toggleCompare  = toggleCompare;
window.clearCompare   = clearCompare;
window.openCompareModal = openCompareModal;
window.copyCompareLink  = copyCompareLink;

// ── BRSR Filing Tracker ────────────────────────────────────────────────────────
let _ftRendered = false;
let _ftSortCol = 'revenue_crore';
let _ftSortDir = -1;

function _ftAssuranceRank(a) { return a === 'All' ? 2 : a === 'Partial' ? 1 : 0; }

function _ftEnrich(c, rankMap) {
  const rev = c.revenue_crore || 0;
  const assurance = c.governance?.brsr_assurance || 'None';
  const rank = rankMap[c.company_name] || 9999;
  const isTop250 = rank <= 250;
  let coreStatus, coreCls;
  if (isTop250) {
    if (assurance === 'All')     { coreStatus = 'BRSR Core Ready'; coreCls = 'ft-status--ready'; }
    else if (assurance === 'Partial') { coreStatus = 'Partial Gap'; coreCls = 'ft-status--partial'; }
    else                         { coreStatus = 'Core Gap';        coreCls = 'ft-status--gap'; }
  } else {
    coreStatus = 'Not Mandated'; coreCls = 'ft-status--na';
  }
  return { ...c, _rev: rev, _assurance: assurance, _rank: rank, _isTop250: isTop250, _coreStatus: coreStatus, _coreCls: coreCls };
}

function _renderRecentFilingsFeed() {
  const container = document.getElementById('ft-recent-feed');
  if (!container) return;

  const tracker = _FILING_TRACKER;
  if (!tracker || !tracker.last_checked) {
    container.innerHTML = `
      <div class="ft-feed-empty">
        <p>No live filing data yet. Run <code>python check_brsr_filings.py</code> to poll BSE for recent BRSR filings.</p>
        <p class="ft-feed-hint">The script writes <code>assets/data/filing_tracker.json</code> — refresh the page after running it.</p>
      </div>`;
    return;
  }

  const checkedAt = new Date(tracker.last_checked);
  const checkedStr = isNaN(checkedAt) ? tracker.last_checked : checkedAt.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
  const filings = tracker.recent_filings || [];

  if (!filings.length) {
    container.innerHTML = `
      <div class="ft-feed-meta">Last checked: ${esc(checkedStr)} · Period: ${tracker.check_period_days} days · 0 BRSR filings found</div>
      <div class="ft-feed-empty"><p>No new BRSR filings found in the last ${tracker.check_period_days} days.</p></div>`;
    return;
  }

  container.innerHTML = `
    <div class="ft-feed-meta">
      Last checked: <strong>${esc(checkedStr)}</strong> · Period: ${tracker.check_period_days} days ·
      <strong>${filings.length}</strong> BRSR filing${filings.length !== 1 ? 's' : ''} detected
    </div>
    <div class="ft-feed-list">
      ${filings.slice(0, 20).map(f => {
        const riskCls = f.risk_tier === 'High' ? 'red' : f.risk_tier === 'Low' ? 'green' : 'amber';
        return `
        <div class="ft-feed-item" onclick="openDeepDive('${esc(f.company_name)}')" title="Open company deep-dive">
          <div class="ft-feed-item__left">
            <span class="ft-feed-item__name">${esc(f.company_name)}</span>
            <span class="ft-feed-item__sector">${esc((f.sector||'').replace('Manufacturing — ','').slice(0,30))}</span>
          </div>
          <div class="ft-feed-item__center">
            <span class="ft-feed-item__headline">${esc((f.headline||'BRSR Filing').slice(0, 80))}</span>
          </div>
          <div class="ft-feed-item__right">
            <span class="ft-feed-item__date">${esc(f.filing_date)}</span>
            ${f.esg_risk_score != null ? `<span class="risk-badge risk-badge--${f.risk_tier}">${f.esg_risk_score}</span>` : ''}
            <a class="ft-feed-item__link" href="${esc(f.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">BSE ↗</a>
          </div>
        </div>`;
      }).join('')}
    </div>`;
}

function renderFilingTracker() {
  if (_ftRendered) return;
  _ftRendered = true;

  _renderRecentFilingsFeed();

  // Build revenue rank map O(n log n) once
  const ranked = allCompanies.slice().sort((a,b) => (b.revenue_crore||0) - (a.revenue_crore||0));
  const rankMap = {};
  ranked.forEach((c, i) => { rankMap[c.company_name] = i + 1; });
  const enriched = allCompanies.map(c => _ftEnrich(c, rankMap));
  enriched.sort((a,b) => _ftSortDir * ((b._rev||0) - (a._rev||0)));

  // KPIs
  const total     = enriched.length;
  const fullAss   = enriched.filter(c => c._assurance === 'All').length;
  const partAss   = enriched.filter(c => c._assurance === 'Partial').length;
  const noAss     = enriched.filter(c => c._assurance === 'None').length;
  const top250    = enriched.filter(c => c._isTop250).length;
  const coreReady = enriched.filter(c => c._isTop250 && c._assurance === 'All').length;

  document.getElementById('ft-kpi-row').innerHTML = `
    <div class="ft-kpi"><div class="ft-kpi__val">${total.toLocaleString('en-IN')}</div><div class="ft-kpi__lbl">Companies Tracked</div></div>
    <div class="ft-kpi ft-kpi--green"><div class="ft-kpi__val">${fullAss}</div><div class="ft-kpi__lbl">Full Assurance</div></div>
    <div class="ft-kpi ft-kpi--amber"><div class="ft-kpi__val">${partAss}</div><div class="ft-kpi__lbl">Partial Assurance</div></div>
    <div class="ft-kpi ft-kpi--red"><div class="ft-kpi__val">${noAss}</div><div class="ft-kpi__lbl">No Assurance</div></div>
    <div class="ft-kpi ft-kpi--cyan"><div class="ft-kpi__val">${coreReady} / ${top250}</div><div class="ft-kpi__lbl">BRSR Core Ready (Top 250)</div></div>`;

  // Sector dropdown
  const sectors = [...new Set(enriched.map(c => _cleanSector(c.sector)))].sort();
  const sel = document.getElementById('ft-sector');
  if (sel && sel.options.length === 1) {
    sectors.forEach(s => { const o = document.createElement('option'); o.value = s; o.textContent = s; sel.appendChild(o); });
  }

  // Store enriched for filtering
  window._ftData = enriched;

  // Column sort
  document.querySelectorAll('.ft-th').forEach(th => {
    th.addEventListener('click', () => {
      if (_ftSortCol === th.dataset.ftcol) _ftSortDir *= -1;
      else { _ftSortCol = th.dataset.ftcol; _ftSortDir = -1; }
      applyFTFilters();
    });
  });

  applyFTFilters();
}
window.renderFilingTracker = renderFilingTracker;

function applyFTFilters() {
  if (!window._ftData) return;
  const q       = (document.getElementById('ft-search')?.value || '').toLowerCase();
  const sector  = document.getElementById('ft-sector')?.value  || '';
  const assur   = document.getElementById('ft-assurance')?.value || '';
  const mandate = document.getElementById('ft-mandate')?.value || '';

  let rows = window._ftData.filter(c => {
    if (q && !c.company_name.toLowerCase().includes(q)) return false;
    if (sector && _cleanSector(c.sector) !== sector) return false;
    if (assur  && c._assurance !== assur) return false;
    if (mandate === 'top250' && !c._isTop250) return false;
    if (mandate === 'other'  &&  c._isTop250) return false;
    return true;
  });

  const colMap = { company_name: 'company_name', sector: 'sector', revenue_crore: '_rev', assurance: '_assurance' };
  const col = colMap[_ftSortCol] || '_rev';
  rows.sort((a,b) => {
    const av = a[col] ?? '';
    const bv = b[col] ?? '';
    if (typeof av === 'number') return _ftSortDir * (bv - av);
    return _ftSortDir * String(bv).localeCompare(String(av));
  });

  const countEl = document.getElementById('ft-count');
  if (countEl) countEl.textContent = `${rows.length.toLocaleString('en-IN')} companies`;

  const assBadge = a => {
    const cls = a === 'All' ? 'ft-ass--full' : a === 'Partial' ? 'ft-ass--partial' : 'ft-ass--none';
    return `<span class="ft-ass-badge ${cls}">${a === 'All' ? 'Full' : a}</span>`;
  };

  document.getElementById('ft-tbody').innerHTML = rows.map(c => `
    <tr>
      <td class="company-name" title="${esc(c.company_name)}" style="cursor:pointer" onclick="openDeepDive('${esc(c.company_name)}')">${esc(c.company_name.slice(0,32))}${c.company_name.length>32?'…':''}</td>
      <td style="font-size:.78rem;color:#94a3b8">${esc(_cleanSector(c.sector).slice(0,28))}</td>
      <td style="text-align:right">${c._rev ? fmt(c._rev) : '—'}</td>
      <td>${c._isTop250 ? `<span class="ft-mandate-badge ft-mandate--top250">Top ${c._rank}</span>` : '<span class="ft-mandate-badge ft-mandate--other">Listed</span>'}</td>
      <td>${assBadge(c._assurance)}</td>
      <td><span class="ft-status ${c._coreCls}">${c._coreStatus}</span></td>
      <td><a class="ft-cin-link" href="https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do?cin=${esc(c.cin||'')}" target="_blank" rel="noopener" title="MCA Portal">${esc(c.cin||'—')}</a></td>
    </tr>`).join('');
}
window.applyFTFilters = applyFTFilters;

// ── Watchlist + Alerts ─────────────────────────────────────────────────────────
// In-memory cache — loaded from API at init, written back on change.
const _WL = {
  _names: [],
  _snaps: {},
  _prefs: { tier_change: true, high_risk: true },

  list()   { return this._names.slice(); },
  has(n)   { return this._names.includes(n); },

  add(n) {
    if (!this._names.includes(n)) {
      this._names.push(n);
      gcAuth.addToWatchlist(n).catch(() => {});
    }
  },
  remove(n) {
    this._names = this._names.filter(x => x !== n);
    gcAuth.removeFromWatchlist(n).catch(() => {});
  },

  getSnaps()    { return this._snaps; },
  saveSnaps(o)  {
    this._snaps = o;
    // persist each changed snapshot
    Object.entries(o).forEach(([co, data]) => gcAuth.saveSnapshot(co, data).catch(() => {}));
  },

  getPrefs()   { return this._prefs; },
  savePrefs(o) {
    this._prefs = o;
    gcAuth.savePrefs(o).catch(() => {});
  },
};

function toggleWatchlist(name, event) {
  event.stopPropagation();
  const wasWatching = _WL.has(name);
  if (wasWatching) {
    _WL.remove(name);
  } else {
    _WL.add(name);
    const co = allCompanies.find(c => c.company_name === name);
    if (co) {
      const snaps = _WL.getSnaps();
      if (!snaps[name]) {
        snaps[name] = { esg_risk_score: co.esg_risk_score, risk_tier: co.risk_tier, snapped_at: new Date().toISOString().slice(0,10) };
        _WL.saveSnaps(snaps);
      }
    }
  }
  const nowWatching = _WL.has(name);
  document.querySelectorAll(`.wl-btn[data-name="${CSS.escape(name)}"]`).forEach(btn => {
    btn.textContent = nowWatching ? '★' : '☆';
    btn.title = nowWatching ? 'Remove from watchlist' : 'Add to watchlist';
    btn.classList.toggle('wl-btn--active', nowWatching);
  });
  const panel = document.getElementById('tab-watchlist');
  if (panel && panel.classList.contains('active')) renderWatchlist();
}
window.toggleWatchlist = toggleWatchlist;

function renderWatchlist() {
  const container = document.getElementById('wl-panel-content');
  if (!container) return;
  const names    = _WL.list();
  const prefs    = _WL.getPrefs();
  const snaps    = _WL.getSnaps();

  if (names.length === 0) {
    container.innerHTML = `
      <div style="text-align:center;padding:80px 20px">
        <div style="font-size:3rem;margin-bottom:16px;opacity:.35">☆</div>
        <h3 style="color:var(--text-60);margin-bottom:8px;font-size:1.05rem;font-weight:600">No companies tracked yet</h3>
        <p style="color:var(--text-40);font-size:.88rem;max-width:360px;margin:0 auto">
          Go to the <strong>Company Screener</strong> tab and click ☆ next to any company to start tracking it here.
        </p>
      </div>`;
    return;
  }

  const companies = names.map(n => allCompanies.find(c => c.company_name === n)).filter(Boolean);

  const prefHtml = `
    <div class="wl-prefs" style="margin-bottom:20px">
      <div class="wl-prefs__title">Alert preferences</div>
      <div class="wl-prefs__row">
        <span class="wl-prefs__label">Alert when risk tier changes</span>
        <label class="wl-toggle">
          <input type="checkbox" ${prefs.tier_change ? 'checked' : ''}
            onchange="window._wlSavePref('tier_change',this.checked)">
          <span class="wl-toggle__slider"></span>
        </label>
      </div>
      <div class="wl-prefs__row">
        <span class="wl-prefs__label">Alert when score enters High risk zone</span>
        <label class="wl-toggle">
          <input type="checkbox" ${prefs.high_risk ? 'checked' : ''}
            onchange="window._wlSavePref('high_risk',this.checked)">
          <span class="wl-toggle__slider"></span>
        </label>
      </div>
    </div>`;

  const cards = companies.map(c => {
    const snap = snaps[c.company_name];
    const tierChanged = snap && snap.risk_tier !== c.risk_tier;
    const diff = snap ? +(c.esg_risk_score - snap.esg_risk_score).toFixed(1) : null;
    const changeCls = diff === null ? '' : diff > 0 ? 'up' : diff < 0 ? 'down' : 'flat';
    const changeHtml = diff !== null
      ? `<span class="wl-card__change wl-card__change--${changeCls}">${diff > 0 ? '▲' : diff < 0 ? '▼' : '─'}${Math.abs(diff)}</span>`
      : '';
    return `
      <div class="wl-card${tierChanged ? ' wl-card--alert' : ''}">
        <div class="wl-card__header">
          <div style="flex:1;min-width:0">
            <div class="wl-card__name" onclick="openDeepDive('${esc(c.company_name)}')" title="Open deep dive">${esc(c.company_name)}</div>
            <div class="wl-card__sector">${esc((c.sector||'').replace('Manufacturing — ','').slice(0,36))}</div>
          </div>
          <button class="wl-card__remove" data-name="${esc(c.company_name)}"
            onclick="toggleWatchlist('${esc(c.company_name)}',event)" title="Remove from watchlist">✕</button>
        </div>
        <div class="wl-card__meta">
          <span class="risk-badge risk-badge--${c.risk_tier}">${c.esg_risk_score}</span>
          <span class="wl-card__risk-label">${c.risk_tier} Risk</span>
          ${changeHtml}
          ${tierChanged ? `<span class="wl-card__alert-tag">⚠ Tier changed</span>` : ''}
        </div>
        ${snap ? `<div class="wl-card__top-risk"><strong>Baseline</strong>${snap.snapped_at}: ${snap.esg_risk_score} (${snap.risk_tier})</div>` : ''}
      </div>`;
  }).join('');

  container.innerHTML = `${prefHtml}<div class="wl-grid">${cards}</div>`;
}
window.renderWatchlist = renderWatchlist;

function _wlSavePref(key, val) {
  const p = Object.assign({}, _WL.getPrefs()); p[key] = val; _WL.savePrefs(p);
}
window._wlSavePref = _wlSavePref;

function checkAlerts() {
  const names = _WL.list();
  if (!names.length) return;
  const prefs  = _WL.getPrefs();
  const snaps  = _WL.getSnaps();
  const alerts = [];

  names.forEach(name => {
    const co   = allCompanies.find(c => c.company_name === name);
    const snap = snaps[name];
    if (!co || !snap) return;
    if (prefs.tier_change && snap.risk_tier !== co.risk_tier) {
      alerts.push(`<strong>${esc(name)}</strong>: tier changed ${snap.risk_tier} → ${co.risk_tier}`);
    } else if (prefs.high_risk && co.risk_tier === 'High' && snap.risk_tier !== 'High') {
      alerts.push(`<strong>${esc(name)}</strong>: entered High risk zone (score ${co.esg_risk_score})`);
    }
  });

  if (!alerts.length) return;
  const strip = document.getElementById('wl-alert-strip');
  const list  = document.getElementById('wl-alert-list');
  if (strip && list) {
    list.innerHTML = alerts.map(a => `<li>${a}</li>`).join('');
    strip.hidden = false;
  }
  const tabBtn = document.getElementById('wl-tab-btn');
  if (tabBtn) tabBtn.innerHTML = `★ Watchlist <span class="wl-tab-badge">${alerts.length}</span>`;
}

// ── Utilities ──────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fmt(n) {
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(n);
}

// ── Feature #3: Filing Deadline Countdown ─────────────────────────────────────
function _renderFilingDeadline() {
  const container = document.getElementById('ft-deadline-strip');
  if (!container) return;
  const deadlines = [
    { label: 'EPR Annual Return FY2025-26',         date: '2026-06-30', who: 'EPR-obligated entities',           urgency: 'high' },
    { label: 'BRSR Core Annual Report Filing',       date: '2026-09-30', who: 'Top 500 companies by revenue',    urgency: 'high' },
    { label: 'Annual Report — All Listed Companies', date: '2026-09-30', who: 'All BSE/NSE listed companies',    urgency: 'medium' },
    { label: 'Value-Chain Data Collection Deadline', date: '2026-12-31', who: 'Top 1000 (BRSR FY2026-27 prep)', urgency: 'medium' },
  ];
  const now = new Date();
  container.innerHTML = deadlines.map(d => {
    const dt   = new Date(d.date);
    const days = Math.ceil((dt - now) / 86400000);
    const passed = days < 0;
    const cls = passed ? 'ft-dl--passed' : (d.urgency === 'high' && days <= 120) ? 'ft-dl--urgent' : 'ft-dl--ok';
    const daysLabel = passed ? 'Passed' : days + 'd';
    return `
    <div class="ft-dl-item ${cls}">
      <div class="ft-dl-days">${daysLabel}</div>
      <div class="ft-dl-info">
        <div class="ft-dl-label">${esc(d.label)}</div>
        <div class="ft-dl-who">${esc(d.who)} · ${esc(d.date)}</div>
      </div>
    </div>`;
  }).join('');
}

window._renderFilingDeadline = _renderFilingDeadline;

// ── Feature #1: BRSR Improvement Plan (CAP) ───────────────────────────────────
// In-memory cache keyed { companyName: { recId: {status,assignee,due_date,notes} } }
let _CAP_CACHE = {};

function _capActions(c) {
  if (!c) return [];
  const rb   = c.risk_breakdown || {};
  const assur = (c.governance && c.governance.brsr_assurance) || 'None';
  const actions = [];
  let id = 0;
  const add = (cat, priority, title, desc, estCost, deadline) =>
    actions.push({ id: c.company_name + '::' + (id++), cat, priority, title, desc, estCost, deadline });

  if ((rb.ghg_intensity || 0) >= 7)
    add('GHG', 'High', 'Set Science-Based GHG Target',
      'Commission a third-party energy audit and set a Science-Based Target (SBT) for Scope 1 & 2. Disclose baseline year and reduction pathway in BRSR Principle 6.',
      '₹15–40 lakh', 'Within 6 months');
  else if ((rb.ghg_intensity || 0) >= 4)
    add('GHG', 'Medium', 'Initiate Monthly GHG Monitoring',
      'Deploy an automated GHG inventory system with monthly intensity tracking. Target 10% intensity reduction by next BRSR cycle.',
      '₹5–15 lakh', 'Within 12 months');

  if ((rb.water_intensity || 0) >= 7)
    add('Water', 'High', 'Implement Zero Liquid Discharge (ZLD) Plan',
      'Engage a certified water-technology provider to design ZLD infrastructure. Report recycling rate (target ≥60%) in BRSR Principle 6.',
      '₹20–80 lakh', 'Within 9 months');
  else if ((rb.water_intensity || 0) >= 4)
    add('Water', 'Medium', 'Deploy Water Metering & Recycling',
      'Install sub-metering at all high-consumption points. Target 20% reduction in freshwater withdrawal per unit output.',
      '₹3–10 lakh', 'Within 6 months');

  if ((rb.waste_intensity || 0) >= 7)
    add('Waste', 'High', 'Critical: EPR Registration & Waste Management Plan',
      'Register on MoEFCC Extended Producer Responsibility (EPR) portal immediately. Engage MoEFCC-approved processor. Non-registration attracts ₹5–15 crore penalty.',
      '₹10–30 lakh', 'Immediate — within 30 days');
  else if ((rb.waste_intensity || 0) >= 4)
    add('Waste', 'Medium', 'Waste Segregation & Recycler Tie-up',
      'Implement source-level waste segregation and sign MoU with authorised recyclers. Disclose waste recycled (tonnes) in BRSR P6-24.',
      '₹2–8 lakh', 'Within 6 months');

  if ((rb.epr_exposure || 0) >= 7)
    add('EPR', 'High', 'File EPR Annual Return & Reconcile Credits',
      'Submit Annual EPR return on MoEFCC portal before deadline. Reconcile plastic credits to match generation data and avoid auto-suspension.',
      '₹1–5 lakh', 'June 30, 2026');

  if ((rb.compliance_risk || 0) >= 7)
    add('Compliance', 'High', 'Immediate BRSR Core Gap Assessment',
      'Engage a SEBI-recognised assurance provider for a pre-filing BRSR Core gap assessment. Prepare board briefing on financial exposure to non-compliance.',
      '₹8–25 lakh', 'Within 3 months');
  else if ((rb.compliance_risk || 0) >= 4)
    add('Compliance', 'Medium', 'Internal Compliance Review & Team Training',
      'Conduct internal BRSR compliance review workshop. Map all KPIs to BRSR Core mandatory indicators and document gaps.',
      '₹1–3 lakh', 'Within 6 months');

  if ((rb.hr_risk || 0) >= 7)
    add('Social', 'High', 'Establish Worker Grievance Mechanism',
      'Implement formal grievance redressal aligned with BRSR Principle 5. Disclose number of grievances received and resolved in Annual Report.',
      '₹2–6 lakh', 'Within 6 months');

  if ((rb.governance_risk || 0) >= 6)
    add('Governance', 'Medium', 'Appoint Board-Level ESG Committee',
      'Constitute a Board-level ESG/Sustainability Committee with at least one independent director. Disclose committee charter in BRSR Principle 1.',
      '₹0 (board resolution)', 'Next AGM');

  if (assur === 'None')
    add('Assurance', 'High', 'Engage BRSR Core Assurance Provider',
      'Engage a SEBI-recognised assurance provider (Big 4 or accredited CA firm) for BRSR Core attestation. Full Assurance is mandatory for BRSR Core-mandated companies.',
      '₹8–20 lakh', 'Before September 30, 2026');
  else if (assur === 'Partial')
    add('Assurance', 'Medium', 'Upgrade to Full BRSR Core Assurance',
      'Extend assurance scope from Partial to Full. Work with your existing provider to include all mandatory KPIs in the engagement scope.',
      '₹3–8 lakh additional', 'Before September 30, 2026');

  const ord = { High: 0, Medium: 1, Low: 2 };
  actions.sort((a, b) => ord[a.priority] - ord[b.priority]);
  return actions;
}

// Returns flat { rec_id: {status,assignee,due_date,notes} } for the current deep-dive company
function _capGetProgress() {
  const company = window._currentDeepDiveCompany || '';
  return _CAP_CACHE[company] || {};
}

// Persist one rec_id update to in-memory cache + API
function _capSaveProgress(p) {
  const company = window._currentDeepDiveCompany || '';
  _CAP_CACHE[company] = p;
}

// Returns normalized object {status, assignee, due_date, notes} with backward-compat migration
function _capGetObj(progress, id) {
  const val = progress[id];
  if (!val) return { status: 'Not Started', assignee: '', due_date: '', notes: '' };
  if (typeof val === 'string') {
    const legacyMap = { 'Open': 'Not Started', 'In Progress': 'In Progress', 'Closed': 'Completed' };
    return { status: legacyMap[val] || 'Not Started', assignee: '', due_date: '', notes: '' };
  }
  return { status: val.status || 'Not Started', assignee: val.assignee || '', due_date: val.due_date || '', notes: val.notes || '' };
}

function _capSaveField(id, field, value) {
  const p = _capGetProgress();
  const obj = _capGetObj(p, id);
  obj[field] = value;
  p[id] = obj;
  _capSaveProgress(p);
  const company = window._currentDeepDiveCompany || '';
  if (company) gcAuth.updateCAP(company, id, { [field]: value }).catch(() => {});
}

function populateCAPDropdown() {
  const sel = document.getElementById('cap-company-select');
  if (!sel || sel.options.length > 1) return;
  allCompanies.slice()
    .sort((a, b) => a.company_name.localeCompare(b.company_name))
    .forEach(c => {
      const o = document.createElement('option');
      o.value = c.company_name;
      o.textContent = c.company_name.slice(0, 55);
      sel.appendChild(o);
    });
}
window.populateCAPDropdown = populateCAPDropdown;

function _capProgressBar(actions, progress) {
  if (!actions.length) return '';
  const total     = actions.length;
  const completed = actions.filter(a => _capGetObj(progress, a.id).status === 'Completed').length;
  const inprog    = actions.filter(a => _capGetObj(progress, a.id).status === 'In Progress').length;
  const archived  = actions.filter(a => _capGetObj(progress, a.id).status === 'Archived').length;
  const pct       = Math.round((completed / total) * 100);
  return `
  <div class="cap-progress-wrap">
    <div class="cap-progress-bar">
      <div class="cap-progress-fill" style="width:${pct}%"></div>
    </div>
    <div class="cap-progress-stats">
      <span class="cap-ps cap-ps--done">${completed} Completed</span>
      <span class="cap-ps cap-ps--wip">${inprog} In Progress</span>
      <span class="cap-ps cap-ps--arch">${archived} Archived</span>
      <span class="cap-ps cap-ps--pct">${pct}% done</span>
    </div>
  </div>`;
}

function _capFilterBar() {
  const opts = [
    { key: 'all',          label: 'All' },
    { key: 'Not Started',  label: 'Not Started' },
    { key: 'In Progress',  label: 'In Progress' },
    { key: 'Completed',    label: 'Completed' },
    { key: 'Archived',     label: 'Archived' },
  ];
  return `<div class="cap-filter-bar">
    ${opts.map(o => `<button class="cap-filter-btn${_capFilter === o.key ? ' cap-filter-btn--active' : ''}" onclick="window.setCAPFilter(${JSON.stringify(o.key)})">${o.label}</button>`).join('')}
  </div>`;
}

function renderCAP() {
  const sel     = document.getElementById('cap-company-select');
  const name    = sel ? sel.value : '';
  const content = document.getElementById('cap-content');
  if (!content) return;

  if (!name) {
    content.innerHTML = `<div style="text-align:center;padding:80px 20px">
      <div style="font-size:3rem;margin-bottom:16px;opacity:.3">📋</div>
      <p style="color:#64748b;font-size:.9rem">Select a company above to view its BRSR Improvement Plan.</p>
    </div>`;
    return;
  }

  const c = allCompanies.find(x => x.company_name === name);
  if (!c) return;

  const actions  = _capActions(c);
  const progress = _capGetProgress();
  const countEl  = document.getElementById('cap-actions-count');
  if (countEl) {
    const completed = actions.filter(a => _capGetObj(progress, a.id).status === 'Completed').length;
    countEl.textContent = `${actions.length} actions · ${completed} completed`;
  }

  const priCls    = { High: 'cap-pri--high', Medium: 'cap-pri--medium', Low: 'cap-pri--low' };
  const ringColor = c.risk_tier === 'High' ? '#f87171' : c.risk_tier === 'Low' ? '#34d399' : '#fbbf24';
  const dash      = ((c.esg_risk_score || 0) / 10) * 188.5;
  const statusOpts = ['Not Started', 'In Progress', 'Completed', 'Archived'];

  const header = `
  <div class="cap-header">
    <div class="cap-header__left">
      <div class="cap-header__name">${esc(c.company_name)}</div>
      <div class="cap-header__meta">${esc(_cleanSector(c.sector))} &nbsp;·&nbsp; ESG Risk ${c.esg_risk_score}/10 &nbsp;·&nbsp; ${(c.governance && c.governance.brsr_assurance) || 'No'} Assurance</div>
    </div>
    <div class="cap-header__right">
      <div class="cap-score-ring">
        <svg width="72" height="72" viewBox="0 0 72 72" aria-hidden="true">
          <circle cx="36" cy="36" r="30" fill="none" stroke="rgba(255,255,255,.06)" stroke-width="6"/>
          <circle cx="36" cy="36" r="30" fill="none" stroke="${ringColor}" stroke-width="6"
            stroke-linecap="round" stroke-dasharray="${dash.toFixed(1)} 188.5"
            transform="rotate(-90 36 36)"/>
          <text x="36" y="41" text-anchor="middle" font-family="DM Sans,sans-serif" font-size="16" font-weight="700" fill="#fff">${c.esg_risk_score}</text>
        </svg>
      </div>
      <div>
        <div class="cap-badge cap-badge--${c.risk_tier.toLowerCase()}">${c.risk_tier} Risk</div>
        <div style="font-size:.72rem;color:#64748b;margin-top:4px" id="cap-closed-count">
          ${actions.filter(a => _capGetObj(progress, a.id).status === 'Completed').length}/${actions.length} completed
        </div>
      </div>
    </div>
  </div>`;

  const cards = actions
    .filter(a => _capFilter === 'all' || _capGetObj(progress, a.id).status === _capFilter)
    .map(a => {
      const obj    = _capGetObj(progress, a.id);
      const status = obj.status;
      const cardCls = status === 'Completed' ? 'cap-card--done' : status === 'In Progress' ? 'cap-card--wip' : status === 'Archived' ? 'cap-card--arch' : '';
      const safeId  = a.id.replace(/[^a-zA-Z0-9_-]/g, '_');
      return `
      <div class="cap-card ${cardCls}" id="capcard_${safeId}">
        <div class="cap-card__top">
          <span class="cap-pri ${priCls[a.priority] || ''}">${a.priority}</span>
          <span class="cap-cat">${esc(a.cat)}</span>
          <select class="cap-status-sel" onchange="window.setCAPStatus(${JSON.stringify(a.id)},this.value,${JSON.stringify(name)})">
            ${statusOpts.map(s => `<option${s === status ? ' selected' : ''}>${s}</option>`).join('')}
          </select>
        </div>
        <div class="cap-card__title">${esc(a.title)}</div>
        <div class="cap-card__desc">${esc(a.desc)}</div>
        <div class="cap-card__footer">
          <span class="cap-meta">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg>
            ${esc(a.deadline)}
          </span>
          <span class="cap-meta cap-meta--cost">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
            Est. ${esc(a.estCost)}
          </span>
          <button class="cap-details-toggle" onclick="window.toggleCAPDetails(${JSON.stringify(safeId)})">Details ▾</button>
        </div>
        <div class="cap-details" id="capdetails_${safeId}" style="display:none">
          <div class="cap-detail-row">
            <label class="cap-detail-lbl">Assignee</label>
            <input class="cap-detail-input" type="text" placeholder="Name or team" value="${esc(obj.assignee)}"
              onblur="window.saveCAPField(${JSON.stringify(a.id)},'assignee',this.value)">
          </div>
          <div class="cap-detail-row">
            <label class="cap-detail-lbl">Due Date</label>
            <input class="cap-detail-input cap-detail-input--date" type="date" value="${esc(obj.due_date)}"
              onchange="window.saveCAPField(${JSON.stringify(a.id)},'due_date',this.value)">
          </div>
          <div class="cap-detail-row cap-detail-row--notes">
            <label class="cap-detail-lbl">Notes</label>
            <textarea class="cap-detail-textarea" rows="3" placeholder="Progress notes, blockers, decisions…"
              onblur="window.saveCAPField(${JSON.stringify(a.id)},'notes',this.value)">${esc(obj.notes)}</textarea>
          </div>
        </div>
      </div>`;
    }).join('');

  const emptyMsg = _capFilter !== 'all' && !cards.trim()
    ? `<div style="text-align:center;padding:40px;color:#64748b">No actions with status "${_capFilter}"</div>`
    : '';

  content.innerHTML = header + _capProgressBar(actions, progress) + _capFilterBar() + `<div class="cap-grid">${cards}${emptyMsg}</div>`;
}
window.renderCAP = renderCAP;

window.setCAPFilter = function(filterKey) {
  _capFilter = filterKey;
  renderCAP();
};

window.toggleCAPDetails = function(safeId) {
  const el = document.getElementById('capdetails_' + safeId);
  if (!el) return;
  const open = el.style.display !== 'none';
  el.style.display = open ? 'none' : 'block';
  const btn = el.previousElementSibling?.querySelector('.cap-details-toggle');
  if (btn) btn.textContent = open ? 'Details ▾' : 'Details ▴';
};

window.saveCAPField = function(id, field, value) {
  _capSaveField(id, field, value);
};

window.setCAPStatus = function(id, status, companyName) {
  _capSaveField(id, 'status', status);
  const safeId = id.replace(/[^a-zA-Z0-9_-]/g, '_');
  const card = document.getElementById('capcard_' + safeId);
  if (card) {
    card.classList.remove('cap-card--done', 'cap-card--wip', 'cap-card--arch');
    if (status === 'Completed')   card.classList.add('cap-card--done');
    else if (status === 'In Progress') card.classList.add('cap-card--wip');
    else if (status === 'Archived')    card.classList.add('cap-card--arch');
  }
  const c       = allCompanies.find(x => x.company_name === companyName);
  const actions = c ? _capActions(c) : [];
  const prog    = _capGetProgress();
  const completed = actions.filter(a => _capGetObj(prog, a.id).status === 'Completed').length;
  const ccEl  = document.getElementById('cap-closed-count');
  if (ccEl) ccEl.textContent = `${completed}/${actions.length} completed`;
  const countEl = document.getElementById('cap-actions-count');
  if (countEl) countEl.textContent = `${actions.length} actions · ${completed} completed`;
  // Re-render progress bar
  const pbWrap = document.querySelector('.cap-progress-wrap');
  if (pbWrap) pbWrap.outerHTML = _capProgressBar(actions, prog);
};

// ── Feature #2: ESG Controversy / Anomaly Feed ────────────────────────────────
let _ctvRendered = false;
let _ctvItems    = [];

const _ANOMALY_MAP = {
  sector_risk_outlier:    { cat: 'Environmental', label: 'Sector Risk Outlier' },
  waste_intensity_anomaly:{ cat: 'Environmental', label: 'Waste Intensity Anomaly' },
  compliance_outlier:     { cat: 'Governance',    label: 'Compliance Gap Detected' },
  water_anomaly:          { cat: 'Environmental', label: 'Water Intensity Anomaly' },
  ghg_anomaly:            { cat: 'Environmental', label: 'GHG Intensity Anomaly' },
  epr_gap:                { cat: 'Regulatory',    label: 'EPR Compliance Gap' },
};

function renderControversy() {
  if (_ctvRendered) { applyCtv(); return; }
  _ctvRendered = true;

  _ctvItems = [];
  const dataDate = INTEL && INTEL.data_as_of ? INTEL.data_as_of : 'Jun 2026';
  allCompanies.forEach(c => {
    (c.anomaly_flags || []).forEach(flag => {
      const m = _ANOMALY_MAP[flag.type] || { cat: 'Regulatory', label: flag.label || 'Risk Flag' };
      const sev = flag.severity === 'high' ? 'High' : flag.severity === 'medium' ? 'Medium' : 'Low';
      _ctvItems.push({
        company:   c.company_name,
        sector:    _cleanSector(c.sector),
        date:      dataDate,
        title:     m.label,
        desc:      flag.detail || '',
        severity:  sev,
        type:      m.cat,
        esg_score: c.esg_risk_score || 0,
      });
    });
  });

  const ord = { High: 0, Medium: 1, Low: 2 };
  _ctvItems.sort((a, b) => ord[a.severity] - ord[b.severity] || b.esg_score - a.esg_score);
  applyCtv();
}
window.renderControversy = renderControversy;

function applyCtv() {
  const q    = (document.getElementById('ctv-search') ? document.getElementById('ctv-search').value : '').toLowerCase();
  const sev  = document.getElementById('ctv-severity') ? document.getElementById('ctv-severity').value : '';
  const type = document.getElementById('ctv-type')     ? document.getElementById('ctv-type').value     : '';

  const items = _ctvItems.filter(item => {
    if (q   && !item.company.toLowerCase().includes(q) && !item.title.toLowerCase().includes(q) && !item.desc.toLowerCase().includes(q)) return false;
    if (sev  && item.severity !== sev) return false;
    if (type && item.type     !== type) return false;
    return true;
  });

  const countEl = document.getElementById('ctv-count');
  if (countEl) countEl.textContent = `${items.length.toLocaleString('en-IN')} events`;

  const feed = document.getElementById('ctv-feed');
  if (!feed) return;

  if (!items.length) {
    feed.innerHTML = `<div style="text-align:center;padding:60px 20px;color:#64748b">No events match your filters.</div>`;
    return;
  }

  const sevCls  = { High: 'ctv-sev--high', Medium: 'ctv-sev--medium', Low: 'ctv-sev--low' };
  const typeCls = { Environmental: 'ctv-type--env', Regulatory: 'ctv-type--reg', Governance: 'ctv-type--gov', Social: 'ctv-type--soc' };

  feed.innerHTML = items.slice(0, 150).map(item => `
    <div class="ctv-card">
      <div class="ctv-card__badges">
        <span class="ctv-sev ${sevCls[item.severity] || ''}">${item.severity}</span>
        <span class="ctv-type-badge ${typeCls[item.type] || ''}">${esc(item.type)}</span>
      </div>
      <div class="ctv-card__title">${esc(item.title)}</div>
      <div class="ctv-card__desc">${esc(item.desc)}</div>
      <div class="ctv-card__footer">
        <span class="ctv-company" onclick="openDeepDive('${esc(item.company)}')">${esc(item.company.slice(0, 42))}</span>
        <span class="ctv-sector">${esc(item.sector.slice(0, 28))}</span>
        <span class="ctv-score">ESG ${item.esg_score}</span>
        <span class="ctv-date">${esc(item.date)}</span>
      </div>
    </div>`).join('');
}
window.applyCtv = applyCtv;

// ── Feature #4: BRSR Excellence Badge ────────────────────────────────────────
let _badgeRendered = false;

function _badgeTier(c) {
  const assur = (c.governance && c.governance.brsr_assurance) || 'None';
  if (c.risk_tier === 'Low' && assur === 'All')
    return { name: 'BRSR Leader',    color: '#4ade80', emoji: '🏅' };
  if (c.risk_tier === 'Low')
    return { name: 'ESG Monitor',    color: '#818cf8', emoji: '🔵' };
  return   { name: 'BRSR Reporter',  color: '#fbbf24', emoji: '🟡' };
}

function _buildBadgeSVG(name, tier) {
  const nm = name.length > 26 ? name.slice(0, 24) + '…' : name;
  const rgb = tier.color === '#4ade80' ? '74,222,128' : tier.color === '#818cf8' ? '129,140,248' : '251,191,36';
  return `<svg width="220" height="88" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${esc(nm)} — ${tier.name} 2025-26">
  <rect width="220" height="88" rx="10" fill="#0c1629" stroke="${tier.color}" stroke-width="1.5"/>
  <text x="14" y="26" font-family="DM Sans,sans-serif" font-size="8.5" fill="${tier.color}" font-weight="700" letter-spacing="1.5">GREEN CURVE · ESG ANALYTICS</text>
  <text x="14" y="48" font-family="DM Sans,sans-serif" font-size="13.5" fill="#f1f5f9" font-weight="600">${esc(tier.name)} 2025-26</text>
  <text x="14" y="64" font-family="DM Sans,sans-serif" font-size="9" fill="#94a3b8">${esc(nm)}</text>
  <text x="14" y="78" font-family="DM Sans,sans-serif" font-size="7.5" fill="#475569">Not a SEBI-registered Rating · greencurve.solutions</text>
  <circle cx="196" cy="44" r="18" fill="rgba(${rgb},.1)" stroke="${tier.color}" stroke-width="1.5"/>
  <text x="196" y="50" text-anchor="middle" font-family="DM Sans,sans-serif" font-size="18" fill="${tier.color}">✓</text>
</svg>`;
}

function renderBadge() {
  if (_badgeRendered) return;
  _badgeRendered = true;

  const panel = document.getElementById('badge-panel');
  if (!panel) return;

  const ranked = allCompanies.slice().sort((a, b) => (a.esg_risk_score || 10) - (b.esg_risk_score || 10));
  const rankMap = {};
  ranked.forEach((c, i) => { rankMap[c.company_name] = i + 1; });

  const eligible = allCompanies.filter(c =>
    c.risk_tier === 'Low' ||
    (c.risk_tier === 'Medium' && (c.governance && c.governance.brsr_assurance) === 'All')
  ).sort((a, b) => (a.esg_risk_score || 10) - (b.esg_risk_score || 10));

  window._badgeState = { eligible, rankMap };

  panel.innerHTML = `
    <div class="badge-tiers">
      <div class="badge-tier badge-tier--gold">
        <div class="badge-tier__icon">🏅</div>
        <div class="badge-tier__name">BRSR Leader</div>
        <div class="badge-tier__desc">Low Risk · Full Assurance</div>
      </div>
      <div class="badge-tier badge-tier--silver">
        <div class="badge-tier__icon">🔵</div>
        <div class="badge-tier__name">ESG Monitor</div>
        <div class="badge-tier__desc">Low Risk · Partial / No Assurance</div>
      </div>
      <div class="badge-tier badge-tier--bronze">
        <div class="badge-tier__icon">🟡</div>
        <div class="badge-tier__name">BRSR Reporter</div>
        <div class="badge-tier__desc">Medium Risk · Full Assurance</div>
      </div>
    </div>
    <h4 style="margin:0 0 16px;font-size:.8rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em">${eligible.length} eligible companies — click any card to get embed code</h4>
    <div class="badge-grid">
      ${eligible.map(c => {
        const t = _badgeTier(c);
        return `<div class="badge-co-card" onclick="window.showBadgeEmbed('${esc(c.company_name)}')">
          <div class="badge-co-preview">${_buildBadgeSVG(c.company_name, t)}</div>
          <div class="badge-co-name">${esc(c.company_name.slice(0, 36))}</div>
          <div class="badge-co-meta">Rank #${rankMap[c.company_name] || '—'} · ${esc(_cleanSector(c.sector).slice(0, 26))}</div>
        </div>`;
      }).join('')}
    </div>`;
}
window.renderBadge = renderBadge;

window.showBadgeEmbed = function(name) {
  const embedPanel = document.getElementById('badge-embed-panel');
  if (!embedPanel || !window._badgeState) return;
  const c = window._badgeState.eligible.find(x => x.company_name === name);
  if (!c) return;
  const t   = _badgeTier(c);
  const svg = _buildBadgeSVG(name, t);
  const b64 = btoa(unescape(encodeURIComponent(svg)));
  const verifyUrl = 'https://greencurve.solutions/esg-intelligence.html';
  const embedCode = `<a href="${verifyUrl}" target="_blank" rel="noopener">\n  <img src="data:image/svg+xml;base64,${b64}"\n       alt="${name} — ${t.name} 2025-26 — Green Curve ESG Analytics"\n       width="220" height="88"/>\n</a>`;
  embedPanel.hidden = false;
  embedPanel.innerHTML = `
    <div class="badge-embed__title">Embed Code — ${esc(name)}</div>
    <pre class="badge-embed__code">${esc(embedCode)}</pre>
    <button class="cap-status-sel" style="margin-top:10px;padding:6px 18px;cursor:pointer;border-radius:8px"
      onclick="navigator.clipboard.writeText(${JSON.stringify(embedCode)}).then(()=>{this.textContent='✓ Copied!';setTimeout(()=>this.textContent='Copy Embed Code',2000)}).catch(()=>{})">
      Copy Embed Code
    </button>
    <div class="badge-embed__note">Paste into your Annual Report website, investor deck, or company sustainability page. The badge links back to Green Curve for verification.</div>`;
  embedPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
};

// ── Feature #6: India ESG Market Map ─────────────────────────────────────────
let _mmRendered = false;

function renderMarketMap() {
  if (_mmRendered) return;
  _mmRendered = true;

  const sectors = {};
  allCompanies.forEach(c => {
    const sec = _cleanSector(c.sector) || 'Other';
    if (!sec || sec === 'Other' || sec.startsWith('NIC ')) return;
    if (!sectors[sec]) sectors[sec] = { cos: [], totalRev: 0, totalRisk: 0 };
    sectors[sec].cos.push(c);
    sectors[sec].totalRev  += c.revenue_crore || 0;
    sectors[sec].totalRisk += c.esg_risk_score || 0;
  });

  const entries = Object.entries(sectors)
    .map(([name, d]) => ({
      name,
      count:   d.cos.length,
      avgRisk: d.totalRisk / d.cos.length,
      totalRev: d.totalRev,
      highRisk: d.cos.filter(x => x.risk_tier === 'High').length,
    }))
    .filter(e => e.count >= 2)
    .sort((a, b) => b.count - a.count)
    .slice(0, 26);

  const colors = entries.map(e =>
    e.avgRisk >= 6.5 ? 'rgba(248,113,113,.8)' :
    e.avgRisk >= 4.5 ? 'rgba(251,191,36,.75)' : 'rgba(52,211,153,.75)');

  Plotly.newPlot('mm-chart', [{
    type: 'scatter', mode: 'markers+text',
    x: entries.map(e => +e.avgRisk.toFixed(2)),
    y: entries.map(e => +(e.totalRev / 1e5).toFixed(2)),
    text: entries.map(e => e.name.slice(0, 16)),
    textposition: 'top center',
    textfont: { size: 9, color: '#94a3b8' },
    marker: {
      size: entries.map(e => Math.max(14, Math.min(56, e.count * 3))),
      color: colors,
      line: { color: 'rgba(0,0,0,.4)', width: 1 },
    },
    customdata: entries.map(e => [e.name, e.count, e.avgRisk.toFixed(1), (e.totalRev / 1e5).toFixed(2), e.highRisk]),
    hovertemplate: '<b>%{customdata[0]}</b><br>Companies: %{customdata[1]}<br>Avg ESG Risk: %{customdata[2]}/10<br>Total Revenue: ₹%{customdata[3]}L Cr<br>High Risk cos: %{customdata[4]}<extra></extra>',
  }], {
    paper_bgcolor: 'transparent', plot_bgcolor: 'rgba(12,22,41,.6)',
    font: { color: '#94a3b8', family: 'DM Sans, sans-serif', size: 11 },
    xaxis: {
      title: { text: 'Average ESG Risk Score →', font: { size: 11, color: '#64748b' } },
      range: [3, 9.5], gridcolor: 'rgba(255,255,255,.05)', tickfont: { color: '#94a3b8' }, zeroline: false,
    },
    yaxis: {
      title: { text: 'Total Sector Revenue (₹ lakh crore) →', font: { size: 11, color: '#64748b' } },
      gridcolor: 'rgba(255,255,255,.05)', tickfont: { color: '#94a3b8' }, zeroline: false,
    },
    shapes: [
      { type: 'line', x0: 6.5, x1: 6.5, y0: 0, y1: 1, yref: 'paper', line: { color: 'rgba(248,113,113,.25)', width: 1, dash: 'dot' } },
      { type: 'line', x0: 4.5, x1: 4.5, y0: 0, y1: 1, yref: 'paper', line: { color: 'rgba(251,191,36,.25)',  width: 1, dash: 'dot' } },
    ],
    annotations: [
      { x: 3.8, y: 0.97, yref: 'paper', text: 'Low Risk Zone',   showarrow: false, font: { size: 9, color: 'rgba(52,211,153,.55)'  } },
      { x: 5.5, y: 0.97, yref: 'paper', text: 'Medium Risk',     showarrow: false, font: { size: 9, color: 'rgba(251,191,36,.55)'  } },
      { x: 7.8, y: 0.97, yref: 'paper', text: 'High Risk Zone',  showarrow: false, font: { size: 9, color: 'rgba(248,113,113,.55)' } },
    ],
    margin: { l: 70, r: 30, t: 30, b: 60 }, height: 480,
  }, { displayModeBar: false, responsive: true });

  const grid = document.getElementById('mm-sector-grid');
  if (grid) {
    grid.innerHTML = entries.map(e => `
      <div class="mm-sector-card" style="border-color:${e.avgRisk >= 6.5 ? 'rgba(248,113,113,.2)' : e.avgRisk >= 4.5 ? 'rgba(251,191,36,.15)' : 'rgba(52,211,153,.12)'}">
        <div class="mm-sector-name">${esc(e.name.slice(0, 32))}</div>
        <div class="mm-sector-stats">
          <span>${e.count} cos</span>
          <span style="color:${e.avgRisk >= 6.5 ? '#f87171' : e.avgRisk >= 4.5 ? '#fbbf24' : '#34d399'}">${e.avgRisk.toFixed(1)} avg risk</span>
          <span>${e.highRisk} high</span>
        </div>
      </div>`).join('');
  }
}
window.renderMarketMap = renderMarketMap;

// ── F-A: BRSR Value-Chain Supplier Tracker ─────────────────────────────────────
// TODO: migrated to assets/js/gc-supplier-tab.js — remove these originals once confirmed stable

function _suppRiskColor(score) {
  if (score >= 6.5) return '#f87171';
  if (score >= 3.5) return '#fbbf24';
  return '#34d399';
}
function _suppTier(score) {
  if (score >= 6.5) return 'High';
  if (score >= 3.5) return 'Medium';
  return 'Low';
}
function _suppDisclosureLevel(r) {
  if (!r.scope1_not_disclosed && !r.scope2_not_disclosed) return 'full';
  if (r.scope1_not_disclosed && r.scope2_not_disclosed)   return 'none';
  return 'partial';
}

function renderSupplierTab() {
  const responses = (_SUPPLIER_RESPONSES && _SUPPLIER_RESPONSES.responses) || [];
  _renderSupplierKPIs(responses);
  _supplierFiltered = responses.slice();
  const cntEl = document.getElementById('supp-count');
  if (cntEl) cntEl.textContent = `${responses.length} responses`;
  _renderSupplierTable(_supplierFiltered);
}
window.renderSupplierTab = renderSupplierTab;

function _renderSupplierKPIs(responses) {
  const row = document.getElementById('supp-kpi-row');
  if (!row) return;
  const total   = responses.length;
  const avgRisk = total
    ? +(responses.reduce((s, r) => s + (r.esg_risk_score || 5), 0) / total).toFixed(1)
    : null;
  const high   = responses.filter(r => (r.esg_risk_score || 0) >= 6.5).length;
  const brsrCt = responses.filter(r => r.has_brsr_disclosure).length;
  const discCt = responses.filter(r => !r.scope1_not_disclosed && !r.scope2_not_disclosed).length;
  row.innerHTML = `
    <div class="supp-kpi"><div class="supp-kpi__val">${total}</div><div class="supp-kpi__lbl">Supplier Responses</div></div>
    <div class="supp-kpi">
      <div class="supp-kpi__val" style="color:${avgRisk != null ? _suppRiskColor(avgRisk) : '#64748b'}">${avgRisk != null ? avgRisk : '—'}</div>
      <div class="supp-kpi__lbl">Avg ESG Risk Score</div>
    </div>
    <div class="supp-kpi"><div class="supp-kpi__val" style="color:#f87171">${high}</div><div class="supp-kpi__lbl">High-Risk Suppliers</div></div>
    <div class="supp-kpi"><div class="supp-kpi__val" style="color:#34d399">${discCt}</div><div class="supp-kpi__lbl">Full GHG Disclosure</div></div>
    <div class="supp-kpi"><div class="supp-kpi__val">${brsrCt}</div><div class="supp-kpi__lbl">With BRSR Report</div></div>
  `;
}

function applySupplierFilters() {
  const responses = (_SUPPLIER_RESPONSES && _SUPPLIER_RESPONSES.responses) || [];
  const q    = (document.getElementById('supp-search')?.value || '').toLowerCase().trim();
  const risk = document.getElementById('supp-risk-filter')?.value || '';
  const disc = document.getElementById('supp-disc-filter')?.value || '';
  _supplierFiltered = responses.filter(r => {
    if (q && !((r.supplier_name || '').toLowerCase().includes(q) ||
               (r.mandating_company_name || '').toLowerCase().includes(q))) return false;
    if (risk) {
      const sc = r.esg_risk_score || 5;
      if (risk === 'low'    && sc >= 3.5) return false;
      if (risk === 'medium' && (sc < 3.5 || sc >= 6.5)) return false;
      if (risk === 'high'   && sc < 6.5) return false;
    }
    if (disc) {
      const lv = _suppDisclosureLevel(r);
      if (disc !== lv) return false;
    }
    return true;
  });
  const cntEl = document.getElementById('supp-count');
  if (cntEl) cntEl.textContent = `${_supplierFiltered.length} of ${responses.length}`;
  _renderSupplierTable(_supplierFiltered);
}
window.applySupplierFilters = applySupplierFilters;

function _renderSupplierTable(rows) {
  const tbody   = document.getElementById('supp-tbody');
  const emptyEl = document.getElementById('supp-empty');
  if (!tbody) return;
  if (!rows.length) {
    tbody.innerHTML = '';
    if (emptyEl) emptyEl.style.display = 'block';
    return;
  }
  if (emptyEl) emptyEl.style.display = 'none';
  tbody.innerHTML = rows.map(r => {
    const score   = r.esg_risk_score != null ? +r.esg_risk_score : null;
    const color   = score != null ? _suppRiskColor(score) : '#64748b';
    const tier    = score != null ? _suppTier(score) : '—';
    const scope12 = (r.scope1_not_disclosed && r.scope2_not_disclosed)
      ? `<span style="color:#64748b;font-size:.78rem">Not disclosed</span>`
      : `<span style="color:#e2e8f0">${((r.scope1_tco2e||0)+(r.scope2_tco2e||0)).toLocaleString('en-IN',{maximumFractionDigits:0})}</span>`;
    const dateStr   = r.submitted_at ? r.submitted_at.slice(0, 10) : '—';
    const msmeTag   = r.is_msme ? `<span class="supp-msme-tag">MSME</span>` : '';
    const brsrIcon  = r.has_brsr_disclosure ? '✅' : `<span style="color:#64748b">—</span>`;
    return `<tr>
      <td><strong style="color:#e2e8f0">${esc(r.supplier_name||'—')}</strong>${msmeTag ? ' ' + msmeTag : ''}</td>
      <td style="color:#64748b;font-size:.82rem">${esc(r.mandating_company_name||'—')}</td>
      <td>${esc(r.annual_revenue_band||'—')}</td>
      <td>${r.is_msme ? '<span style="color:#34d399">Yes</span>' : '<span style="color:#64748b">No</span>'}</td>
      <td>${scope12}</td>
      <td><span style="color:${color};font-weight:700;font-size:.95rem">${score!=null?score.toFixed(1):'—'}</span> <span style="color:#64748b;font-size:.76rem">${tier}</span></td>
      <td>${brsrIcon}</td>
      <td style="color:#64748b;font-size:.8rem">${dateStr}</td>
    </tr>`;
  }).join('');
}

function generateSupplierLink() {
  const coInput  = document.getElementById('supp-co-input');
  const cinInput = document.getElementById('supp-cin-input');
  const out      = document.getElementById('supp-link-output');
  const urlEl    = document.getElementById('supp-link-url');
  const copyBtn  = document.getElementById('supp-copy-btn');
  if (!coInput || !out || !urlEl) return;
  const co  = coInput.value.trim();
  const cin = cinInput ? cinInput.value.trim() : '';
  if (!co) { coInput.focus(); return; }
  const base = window.location.origin + window.location.pathname.replace(/[^/]*$/, '');
  const link = base + 'supplier-form.html?company=' + encodeURIComponent(co) +
    (cin ? '&cin=' + encodeURIComponent(cin) : '');
  urlEl.textContent = link;
  out.style.display = 'block';
  if (copyBtn) { copyBtn.textContent = 'Copy'; copyBtn.classList.remove('supp-copy-btn--done'); }
}
window.generateSupplierLink = generateSupplierLink;

function copySupplierLink() {
  const urlEl   = document.getElementById('supp-link-url');
  const copyBtn = document.getElementById('supp-copy-btn');
  if (!urlEl) return;
  const text = urlEl.textContent.trim();
  const done = () => {
    if (copyBtn) { copyBtn.textContent = 'Copied!'; copyBtn.classList.add('supp-copy-btn--done'); }
    setTimeout(() => {
      if (copyBtn) { copyBtn.textContent = 'Copy'; copyBtn.classList.remove('supp-copy-btn--done'); }
    }, 2000);
  };
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(done).catch(() => {
      const ta = document.createElement('textarea');
      ta.value = text; document.body.appendChild(ta); ta.select();
      document.execCommand('copy'); document.body.removeChild(ta); done();
    });
  } else {
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); document.body.removeChild(ta); done();
  }
}
window.copySupplierLink = copySupplierLink;

// ── P2-C: Sector ESG Distribution ────────────────────────────────────────────

const SD_DIMS = {
  esg_quotient:    'Overall ESG Score',
  ghg_intensity:   'GHG Intensity',
  water_intensity: 'Water Intensity',
  waste_intensity: 'Waste Intensity',
  epr_exposure:    'EPR Exposure',
  compliance_risk: 'Compliance Risk',
  hr_risk:         'HR Risk',
  governance_risk: 'Governance Risk',
};

let _SD_INIT = false;

function _sdPopulateSectors() {
  const sel = document.getElementById('sd-sector-select');
  if (!sel || !allCompanies.length) return;
  const sectors = [...new Set(allCompanies.map(c => (c.sector||'').trim()).filter(Boolean))].sort();
  sel.innerHTML = '<option value="">— Select a Sector —</option>' +
    sectors.map(s => `<option value="${s}">${s}</option>`).join('');
}

function renderSectorDistTab() {
  if (!_SD_INIT) { _sdPopulateSectors(); _SD_INIT = true; }

  const secSel  = document.getElementById('sd-sector-select');
  const dimSel  = document.getElementById('sd-dim-select');
  const countEl = document.getElementById('sd-count');
  const chartEl = document.getElementById('sd-chart');
  const statsEl = document.getElementById('sd-stats-row');
  const outEl   = document.getElementById('sd-outlier-row');
  const emptyEl = document.getElementById('sd-empty');
  if (!secSel || !chartEl) return;

  const sec = secSel.value;
  const dim = dimSel ? dimSel.value : 'esg_quotient';
  const dimLabel = SD_DIMS[dim] || dim;

  if (!sec) {
    emptyEl && (emptyEl.style.display = '');
    chartEl.style.display = 'none';
    statsEl && (statsEl.innerHTML = '');
    outEl   && (outEl.innerHTML = '');
    if (countEl) countEl.textContent = '';
    return;
  }
  emptyEl && (emptyEl.style.display = 'none');
  chartEl.style.display = '';

  const companies = allCompanies.filter(c => (c.sector||'').trim() === sec);
  const vals = companies.map(c => {
    if (dim === 'esg_quotient') return c.esg_risk_score;
    return c.risk_breakdown ? c.risk_breakdown[dim] : null;
  }).filter(v => v != null);

  if (countEl) countEl.textContent = `${companies.length} companies · ${vals.length} with ${dimLabel} data`;

  if (!vals.length) {
    chartEl.innerHTML = `<div style="color:#475569;text-align:center;padding:80px 0;font-size:.85rem">No ${dimLabel} data available for ${sec}</div>`;
    statsEl && (statsEl.innerHTML = '');
    outEl   && (outEl.innerHTML = '');
    return;
  }

  // Stats
  const sorted = [...vals].sort((a, b) => a - b);
  const n    = sorted.length;
  const mean = vals.reduce((s, v) => s + v, 0) / n;
  const med  = n % 2 === 0 ? (sorted[n/2-1]+sorted[n/2])/2 : sorted[Math.floor(n/2)];
  const std  = Math.sqrt(vals.reduce((s, v) => s + (v - mean)**2, 0) / n);
  const q1   = sorted[Math.floor(n * 0.25)];
  const q3   = sorted[Math.floor(n * 0.75)];
  const min  = sorted[0];
  const max  = sorted[n - 1];

  if (statsEl) statsEl.innerHTML = `
    <div class="sd-stat"><div class="sd-stat__val">${mean.toFixed(2)}</div><div class="sd-stat__lbl">Mean</div></div>
    <div class="sd-stat"><div class="sd-stat__val">${med.toFixed(2)}</div><div class="sd-stat__lbl">Median</div></div>
    <div class="sd-stat"><div class="sd-stat__val">${std.toFixed(2)}</div><div class="sd-stat__lbl">Std Dev</div></div>
    <div class="sd-stat"><div class="sd-stat__val">${q1.toFixed(2)}</div><div class="sd-stat__lbl">P25</div></div>
    <div class="sd-stat"><div class="sd-stat__val">${q3.toFixed(2)}</div><div class="sd-stat__lbl">P75</div></div>
    <div class="sd-stat"><div class="sd-stat__val">${min.toFixed(2)} – ${max.toFixed(2)}</div><div class="sd-stat__lbl">Range</div></div>
  `;

  // Outliers: beyond 1.5 × IQR
  const iqr   = q3 - q1;
  const fence = 1.5 * iqr;
  const outliers = companies.filter(c => {
    const v = dim === 'esg_quotient' ? c.esg_risk_score : (c.risk_breakdown?.[dim]);
    return v != null && (v < q1 - fence || v > q3 + fence);
  }).sort((a, b) => {
    const va = dim === 'esg_quotient' ? b.esg_risk_score : (b.risk_breakdown?.[dim]||0);
    const vb = dim === 'esg_quotient' ? a.esg_risk_score : (a.risk_breakdown?.[dim]||0);
    return va - vb;
  }).slice(0, 6);

  if (outEl) {
    if (outliers.length) {
      outEl.innerHTML = `<div class="sd-outlier-title">Outliers (beyond 1.5×IQR)</div>` +
        outliers.map(c => {
          const v = dim === 'esg_quotient' ? c.esg_risk_score : (c.risk_breakdown?.[dim]);
          const col = v > q3 + fence ? '#f87171' : '#34d399';
          return `<span class="sd-outlier-chip" style="border-color:${col}33;color:${col}">${c.company_name} <b>${v.toFixed(1)}</b></span>`;
        }).join('');
    } else {
      outEl.innerHTML = '<div class="sd-outlier-title" style="color:#475569">No statistical outliers in this sector for the selected dimension.</div>';
    }
  }

  // Plot
  if (typeof Plotly === 'undefined') return;

  const companiesSorted = companies.filter(c => {
    const v = dim === 'esg_quotient' ? c.esg_risk_score : (c.risk_breakdown?.[dim]);
    return v != null;
  }).sort((a, b) => {
    const va = dim === 'esg_quotient' ? a.esg_risk_score : (a.risk_breakdown?.[dim]||0);
    const vb = dim === 'esg_quotient' ? b.esg_risk_score : (b.risk_breakdown?.[dim]||0);
    return va - vb;
  });

  const xNames = companiesSorted.map(c => c.company_name.length > 22 ? c.company_name.slice(0,20)+'…' : c.company_name);
  const yVals  = companiesSorted.map(c => dim === 'esg_quotient' ? c.esg_risk_score : (c.risk_breakdown?.[dim]));
  const barColors = yVals.map(v => {
    if (v == null) return '#475569';
    if (v <= 3)  return '#34d399';
    if (v <= 6)  return '#fbbf24';
    return '#f87171';
  });

  const traces = [
    {
      type: 'bar',
      x: xNames,
      y: yVals,
      marker: { color: barColors },
      hovertemplate: '%{x}: <b>%{y:.2f}</b><extra></extra>',
      text: yVals.map(v => v != null ? v.toFixed(1) : ''),
      textposition: 'outside',
      textfont: { size: 9, color: '#64748b' },
    },
  ];

  const shapes = [
    { type: 'line', x0: -0.5, x1: xNames.length - 0.5, y0: mean, y1: mean, line: { color: 'rgba(148,163,184,.5)', width: 1.5, dash: 'dot' } },
    { type: 'rect',  x0: -0.5, x1: xNames.length - 0.5, y0: q1, y1: q3,  line: { width: 0 }, fillcolor: 'rgba(148,163,184,.07)' },
  ];

  const annotations = [
    { x: xNames.length - 0.5, y: mean, text: `Mean ${mean.toFixed(1)}`, showarrow: false, font: { size: 9, color: 'rgba(148,163,184,.8)' }, xanchor: 'right', bgcolor: 'rgba(12,22,41,.7)', borderpad: 2 },
  ];

  Plotly.newPlot(chartEl, traces, {
    paper_bgcolor: 'transparent',
    plot_bgcolor:  'rgba(12,22,41,.5)',
    font:   { color: '#94a3b8', family: 'DM Sans, sans-serif', size: 10 },
    margin: { l: 50, r: 20, t: 20, b: 110 },
    xaxis: {
      tickangle: -40,
      tickfont: { size: 9, color: '#64748b' },
      gridcolor: 'rgba(255,255,255,.04)',
    },
    yaxis: {
      title: { text: dimLabel + ' (0–10)', font: { size: 11, color: '#64748b' } },
      range: [0, 10.5],
      gridcolor: 'rgba(255,255,255,.05)',
      tickfont: { color: '#94a3b8' },
    },
    shapes,
    annotations,
    bargap: 0.25,
  }, { displayModeBar: false, responsive: true });
}

window.renderSectorDistTab = renderSectorDistTab;

// ── P2-D: BRSR Disclosure Heatmap ────────────────────────────────────────────

const BH_DIMS = [
  { key: 'ghg_intensity',   label: 'GHG' },
  { key: 'water_intensity', label: 'Water' },
  { key: 'waste_intensity', label: 'Waste' },
  { key: 'epr_exposure',    label: 'EPR' },
  { key: 'compliance_risk', label: 'Compliance' },
  { key: 'hr_risk',         label: 'HR' },
  { key: 'governance_risk', label: 'Governance' },
];

let _BH_INIT = false;

function _bhPopulateSectors() {
  const sel = document.getElementById('bh-sector-select');
  if (!sel || !allCompanies.length) return;
  const sectors = [...new Set(allCompanies.map(c => (c.sector||'').trim()).filter(Boolean))].sort();
  sel.innerHTML = '<option value="">— Select a Sector —</option>' +
    sectors.map(s => `<option value="${s}">${s}</option>`).join('');
}

function _bhColor(val) {
  if (val == null) return { bg: '#1a2540', text: '#334155', label: '—' };
  const v = Math.min(10, Math.max(0, val));
  if (v <= 3)  return { bg: `rgba(52,211,153,${0.15 + v*0.05})`,  text: '#34d399', label: v.toFixed(1) };
  if (v <= 6)  return { bg: `rgba(251,191,36,${0.10 + (v-3)*0.05})`, text: '#fbbf24', label: v.toFixed(1) };
  return { bg: `rgba(248,113,113,${0.10 + (v-6)*0.07})`, text: '#f87171', label: v.toFixed(1) };
}

function renderBRSRHeatmap() {
  if (!_BH_INIT) { _bhPopulateSectors(); _BH_INIT = true; }

  const secSel   = document.getElementById('bh-sector-select');
  const searchEl = document.getElementById('bh-search');
  const countEl  = document.getElementById('bh-count');
  const wrap     = document.getElementById('bh-chart-wrap');
  if (!secSel || !wrap) return;

  const sec   = secSel.value;
  const query = (searchEl ? searchEl.value : '').toLowerCase().trim();

  if (!sec) {
    wrap.innerHTML = `<div id="bh-empty" class="supp-empty-state">
      <div class="supp-empty-icon">🔲</div>
      <div class="supp-empty-title">Select a sector to render the heatmap</div>
      <div class="supp-empty-sub">Each row is a company; each column is a BRSR risk dimension.</div>
    </div>`;
    if (countEl) countEl.textContent = '';
    return;
  }

  let companies = allCompanies.filter(c => (c.sector||'').trim() === sec);
  if (query) companies = companies.filter(c => (c.company_name||'').toLowerCase().includes(query));
  companies = [...companies].sort((a, b) => (b.esg_risk_score||0) - (a.esg_risk_score||0));

  if (countEl) countEl.textContent = `${companies.length} companies`;

  // Disclosure coverage per company: count of non-null dims
  const maxRows = 80;
  const shown   = companies.slice(0, maxRows);

  // Build HTML heatmap table
  const headerCells = BH_DIMS.map(d => `<th class="bh-th">${d.label}</th>`).join('');
  const rows = shown.map(c => {
    const rb = c.risk_breakdown || {};
    const nameFmt = c.company_name.length > 28 ? c.company_name.slice(0,26)+'…' : c.company_name;
    const tot = c.esg_risk_score != null ? c.esg_risk_score.toFixed(1) : '—';
    const totColor = c.esg_risk_score == null ? '#475569' : c.esg_risk_score <= 3 ? '#34d399' : c.esg_risk_score <= 6 ? '#fbbf24' : '#f87171';
    const cells = BH_DIMS.map(d => {
      const { bg, text, label } = _bhColor(rb[d.key]);
      return `<td class="bh-cell" style="background:${bg};color:${text}" title="${d.label}: ${label}">${label}</td>`;
    }).join('');
    const disclosed = BH_DIMS.filter(d => rb[d.key] != null).length;
    const discPct   = Math.round((disclosed / BH_DIMS.length) * 100);
    return `<tr class="bh-row" onclick="openDeepDive('${c.company_name.replace(/'/g,"\\'")}')">
      <td class="bh-name">${nameFmt}</td>
      ${cells}
      <td class="bh-total" style="color:${totColor}">${tot}</td>
      <td class="bh-cov">${discPct}%</td>
    </tr>`;
  }).join('');

  const truncNote = companies.length > maxRows ? `<div class="bh-trunc-note">Showing top ${maxRows} of ${companies.length} companies by ESG score. Refine with the search box.</div>` : '';

  wrap.innerHTML = `
    ${truncNote}
    <div class="bh-legend-row">
      <span class="bh-leg bh-leg--low">Low risk (0–3)</span>
      <span class="bh-leg bh-leg--med">Medium (3–6)</span>
      <span class="bh-leg bh-leg--high">High (6–10)</span>
      <span class="bh-leg bh-leg--na">Not disclosed</span>
    </div>
    <div class="bh-scroll-wrap">
      <table class="bh-table">
        <thead><tr>
          <th class="bh-th bh-th--name">Company</th>
          ${headerCells}
          <th class="bh-th">Overall</th>
          <th class="bh-th">Disclosed</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

window.renderBRSRHeatmap = renderBRSRHeatmap;

// ── P3-D: AI ESG Query Assistant — extracted to gc-ai-query.js ────────────────
// TODO: migrated to assets/js/gc-ai-query.js — remove these originals once confirmed stable

function initAIQuery() {
  // nothing to pre-load; ready on open
}

function aiqSetAndRun(q) {
  const inp = document.getElementById('aiq-input');
  if (inp) inp.value = q;
  runAIQuery();
}

async function runAIQuery() {
  const inp    = document.getElementById('aiq-input');
  const status = document.getElementById('aiq-status');
  const result = document.getElementById('aiq-result');
  const countEl= document.getElementById('aiq-result-count');
  const exEl   = document.getElementById('aiq-result-explain');
  const tbody  = document.getElementById('aiq-tbody');
  if (!inp) return;

  const q = inp.value.trim();
  if (!q) return;

  status.style.display = '';
  status.className = 'aiq-status aiq-status--loading';
  status.textContent = 'Thinking…';
  result.style.display = 'none';

  const api = window._gcApiBase || localStorage.getItem('gc_api_base') || '';

  try {
    let filters = null;
    let explain = '';

    if (api) {
      const res = await fetch(api + '/api/nl-query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q }),
        signal: AbortSignal.timeout(20000),
      });
      if (res.ok) {
        const data = await res.json();
        filters = data.filters;
        explain = data.explanation || '';
      }
    }

    let rows;
    if (filters) {
      rows = _aiqApplyFilters(allCompanies, filters);
    } else {
      // Keyword fallback — extract numbers and keywords from query text
      rows = _aiqKeywordFallback(allCompanies, q);
      explain = explain || 'Backend offline — using keyword search.';
    }

    status.style.display = 'none';
    result.style.display = '';
    countEl.textContent  = `${rows.length} companies matched`;
    exEl.textContent     = explain;
    tbody.innerHTML      = rows.slice(0, 100).map(c => {
      const rb = c.risk_breakdown || {};
      const col = c.esg_risk_score <= 3 ? '#34d399' : c.esg_risk_score <= 6 ? '#fbbf24' : '#f87171';
      return `<tr style="cursor:pointer" onclick="openDeepDive('${esc(c.company_name)}')">
        <td class="company-name">${esc((c.company_name||'').slice(0,28))}${(c.company_name||'').length>28?'…':''}</td>
        <td class="sector-cell">${esc((c.sector||'').replace('Manufacturing — ','').slice(0,30))}</td>
        <td><span class="risk-badge risk-badge--${c.risk_tier}" style="color:${col}">${c.esg_risk_score}</span></td>
        <td>${scoreBar(rb.ghg_intensity)}</td>
        <td>${scoreBar(rb.water_intensity)}</td>
        <td>${scoreBar(rb.compliance_risk)}</td>
        <td>${c.revenue_crore != null ? fmt(c.revenue_crore) : '—'}</td>
      </tr>`;
    }).join('');
    if (!rows.length) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#475569;padding:30px">No companies matched this query.</td></tr>';
  } catch (e) {
    status.className = 'aiq-status aiq-status--error';
    status.textContent = 'Query failed: ' + e.message;
  }
}

function _aiqApplyFilters(data, filters) {
  let rows = [...data];
  if (filters.sector)           rows = rows.filter(c => (c.sector||'').toLowerCase().includes(filters.sector.toLowerCase()));
  if (filters.risk_tier)        rows = rows.filter(c => (c.risk_tier||'').toLowerCase() === filters.risk_tier.toLowerCase());
  if (filters.min_esg != null)  rows = rows.filter(c => (c.esg_risk_score||0) >= filters.min_esg);
  if (filters.max_esg != null)  rows = rows.filter(c => (c.esg_risk_score||0) <= filters.max_esg);
  if (filters.min_ghg != null)  rows = rows.filter(c => (c.risk_breakdown?.ghg_intensity||0) >= filters.min_ghg);
  if (filters.min_water != null)rows = rows.filter(c => (c.risk_breakdown?.water_intensity||0) >= filters.min_water);
  if (filters.min_compliance != null) rows = rows.filter(c => (c.risk_breakdown?.compliance_risk||0) >= filters.min_compliance);
  if (filters.has_scope1 === false) rows = rows.filter(c => c.financial_exposure?.scope1_emissions_tco2e == null);
  if (filters.has_scope1 === true)  rows = rows.filter(c => c.financial_exposure?.scope1_emissions_tco2e != null);
  if (filters.has_assurance)    rows = rows.filter(c => (c.governance?.brsr_assurance||'None') !== 'None');
  if (filters.sort === 'water_intensity_desc') rows.sort((a,b) => (b.risk_breakdown?.water_intensity||0) - (a.risk_breakdown?.water_intensity||0));
  else if (filters.sort === 'esg_desc')        rows.sort((a,b) => (b.esg_risk_score||0) - (a.esg_risk_score||0));
  else                                          rows.sort((a,b) => (b.esg_risk_score||0) - (a.esg_risk_score||0));
  if (filters.limit) rows = rows.slice(0, filters.limit);
  return rows;
}

function _aiqKeywordFallback(data, query) {
  const q = query.toLowerCase();
  // Extract sector keywords
  const SECTOR_MAP = { cement:'Cement', steel:'Steel', pharma:'Pharmaceuticals', power:'Power', it:'IT', bank:'Banking', chemical:'Chemical', auto:'Automobile', textile:'Textile', paper:'Paper' };
  let rows = [...data];
  for (const [kw, sec] of Object.entries(SECTOR_MAP)) {
    if (q.includes(kw)) { rows = rows.filter(c => (c.sector||'').toLowerCase().includes(kw)); break; }
  }
  // Extract numeric thresholds
  const ghgMatch   = q.match(/ghg.*?(\d+(\.\d+)?)/);
  const waterMatch = q.match(/water.*?(\d+(\.\d+)?)/);
  const esgMatch   = q.match(/esg.*?(\d+(\.\d+)?)/);
  if (ghgMatch)   rows = rows.filter(c => (c.risk_breakdown?.ghg_intensity||0)   >= parseFloat(ghgMatch[1]));
  if (waterMatch) rows = rows.filter(c => (c.risk_breakdown?.water_intensity||0) >= parseFloat(waterMatch[1]));
  if (esgMatch)   rows = rows.filter(c => (c.esg_risk_score||0)                  >= parseFloat(esgMatch[1]));
  // Risk tier
  if (q.includes('high risk') || q.includes('high-risk')) rows = rows.filter(c => c.risk_tier === 'High');
  if (q.includes('low risk')  || q.includes('low-risk'))  rows = rows.filter(c => c.risk_tier === 'Low');
  // Assurance
  if (q.includes('assurance') || q.includes('assured')) rows = rows.filter(c => (c.governance?.brsr_assurance||'None') !== 'None');
  // No scope 1
  if (q.includes('no scope') || q.includes('scope 1') && (q.includes('missing')||q.includes('no '))) rows = rows.filter(c => c.financial_exposure?.scope1_emissions_tco2e == null);
  // Top N
  const topMatch = q.match(/top\s+(\d+)/);
  const limit    = topMatch ? parseInt(topMatch[1], 10) : 100;
  // Sort
  if (q.includes('water intensity')) rows.sort((a,b) => (b.risk_breakdown?.water_intensity||0) - (a.risk_breakdown?.water_intensity||0));
  else rows.sort((a,b) => (b.esg_risk_score||0) - (a.esg_risk_score||0));
  return rows.slice(0, limit);
}

window.runAIQuery  = runAIQuery;
window.aiqSetAndRun= aiqSetAndRun;
window.initAIQuery = initAIQuery;

initDashboard();
