// ESG Financial Quotient Dashboard
// Reads assets/data/esg_quotient.json and renders all 4 panels

let INTEL = null;
let allCompanies = [];
let API_BASE = '';   // set dynamically from brsr-generator.js if available

// Try to read API_BASE from brsr-generator config (set by start_brsr.py)
try {
  const scripts = document.querySelectorAll('script[src]');
  // API_BASE is set in brsr-generator.js — read from localStorage if previously set
  API_BASE = localStorage.getItem('gc_api_base') || '';
} catch(e) {}

// Allow brsr-generator.js to share its API_BASE
window.setIntelApiBase = (url) => { API_BASE = url; localStorage.setItem('gc_api_base', url); };

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
    const res = await fetch('assets/data/esg_quotient.json?v=' + Date.now());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    INTEL = await res.json();
    allCompanies = INTEL.companies || [];

    const s = INTEL.summary || {};
    statusEl.textContent =
      `${s.total_companies || 0} companies analysed · ${s.regulations_analysed || 0} regulations tracked · Updated ${INTEL.data_as_of || ''}`;

    renderKPIs(s);
    renderCharts();
    renderScreener();
    populateSectorDropdown();
    // Wire column sort headers
    document.querySelectorAll('.th-sort').forEach(th => {
      th.addEventListener('click', () => setColSort(th.dataset.col));
    });
    renderDoubleMateriality();
    renderRegulations();
    renderTargets();
    renderSupplyChain();
    renderMaterials();
    renderCalendar();
    renderAnomalies();
    checkAlerts();
    // Heat map renders lazily when the tab is clicked (Plotly needs a visible container)
    const dmTitle = document.getElementById('dmChartTitle');
    if (dmTitle) dmTitle.textContent = `Double Materiality Matrix — All ${allCompanies.length} Companies`;
  } catch (e) {
    statusEl.textContent = 'Quotient data not yet available — runs daily after 2 AM.';
    console.warn('ESG Intel load failed:', e);
    renderPlaceholder();
  }
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

// ── Charts ─────────────────────────────────────────────────────────────────────
function renderCharts() {
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
function applyColFilters() {
  const company  = (document.getElementById('cf-company')?.value  || '').toLowerCase();
  const sector   = document.getElementById('cf-sector')?.value   || '';
  const riskTier = document.getElementById('cf-risk-tier')?.value || '';
  const ghgMin   = Number(document.getElementById('cf-ghg')?.value   || 0);
  const waterMin = Number(document.getElementById('cf-water')?.value || 0);
  const eprMin   = Number(document.getElementById('cf-epr')?.value   || 0);
  const compMin  = Number(document.getElementById('cf-comp')?.value  || 0);
  const revMin   = Number(document.getElementById('cf-rev-min')?.value || 0);
  const capMin   = Number(document.getElementById('cf-cap-min')?.value || 0);
  const retDir   = document.getElementById('cf-return')?.value || '';
  // Also sync legacy top-bar filters
  const topSearch = (document.getElementById('screenerSearch')?.value || '').toLowerCase();

  renderScreener('', '', '', {
    company, sector, riskTier, ghgMin, waterMin, eprMin, compMin, revMin, capMin, retDir, topSearch
  });
}

function resetColFilters() {
  ['cf-company','cf-ghg','cf-water','cf-epr','cf-comp','cf-rev-min','cf-cap-min'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  ['cf-sector','cf-risk-tier','cf-return'].forEach(id => {
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

  document.getElementById('screenerCount').textContent = `${data.length} companies`;

  const tbody = document.getElementById('screenerBody');
  tbody.innerHTML = data.map(c => {
    const rb = c.risk_breakdown || {};
    const md = c.market_data || {};
    const ret = md.return_1y_pct;
    const retHtml = ret != null
      ? `<span style="color:${ret >= 0 ? '#10b981' : '#f87171'}">${ret >= 0 ? '+' : ''}${ret}%</span>`
      : '<span style="color:#475569">N/A</span>';
    const inCmp = compareList.includes(c.company_name);
    const cov = _dcCoverage(c);
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
          ${esc((c.company_name||'').slice(0,28))}${(c.company_name||'').length > 28 ? '…' : ''}${(c.anomaly_flags||[]).length ? `<span class="anomaly-dot" title="${esc((c.anomaly_flags||[]).map(f=>f.label).join(', '))}">⚠</span>` : ''}
          <div class="dc-coverage" title="Data coverage: ${cov.reported}/${cov.total} key fields reported in BRSR">
            <div class="dc-coverage__bar"><div class="dc-coverage__fill" style="width:${cov.pct}%"></div></div>
            <span class="dc-coverage__txt">${cov.pct}%</span>
          </div>
        </td>
        <td class="sector-cell">${esc((c.sector||'').replace('Manufacturing — ','').slice(0,30))}</td>
        <td><span class="risk-badge risk-badge--${c.risk_tier}">${c.esg_risk_score}</span></td>
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
  return `
    <div class="dd-overview-grid">
      <div class="dd-kpi"><div class="dd-kpi-val">${p.revenue_crore ? '₹'+fmt(p.revenue_crore)+' Cr' : '—'}</div><div class="dd-kpi-lbl">Revenue</div></div>
      <div class="dd-kpi"><div class="dd-kpi-val">${md.market_cap_crore ? '₹'+fmt(md.market_cap_crore)+' Cr' : '—'}</div><div class="dd-kpi-lbl">Market Cap</div></div>
      <div class="dd-kpi"><div class="dd-kpi-val ${md.return_1y_pct != null ? (md.return_1y_pct>=0?'green':'red') : ''}">${md.return_1y_pct != null ? (md.return_1y_pct>=0?'+':'')+md.return_1y_pct+'%' : '—'}</div><div class="dd-kpi-lbl">1Y Return</div></div>
      <div class="dd-kpi"><div class="dd-kpi-val">${fe.estimated_compliance_cost_band||'—'}</div><div class="dd-kpi-lbl">Est. Compliance Cost</div></div>
    </div>
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
          <span class="dc-legend__item"><span class="dc-badge dc-reported">Reported</span> Company BRSR filing (SEBI)</span>
          <span class="dc-legend__item"><span class="dc-badge dc-estimated">Estimated</span> Green Curve model</span>
          <span class="dc-legend__item"><span class="dc-badge dc-missing">Missing</span> Not in filing</span>
        </div>`;
      })()}
      <div class="dd-kv-grid">
        ${[
          ['Scope 1 Emissions',    fe.scope1_emissions_tco2e,                                       fe.scope1_emissions_tco2e ? fe.scope1_emissions_tco2e+' tCO2e' : '—',  'reported'],
          ['Scope 2 Emissions',    fe.scope2_emissions_tco2e,                                       fe.scope2_emissions_tco2e ? fe.scope2_emissions_tco2e+' tCO2e' : '—',  'reported'],
          ['Water Withdrawal',     fe.water_withdrawal_m3,                                          fe.water_withdrawal_m3 ? fmt(fe.water_withdrawal_m3)+' m³' : '—',      'reported'],
          ['Waste Generated',      fe.waste_tonnes,                                                 fe.waste_tonnes ? fmt(fe.waste_tonnes)+' tonnes' : '—',                'reported'],
          ['EPR Applicable',       fe.epr_applicable && fe.epr_applicable !== 'Unknown' ? fe.epr_applicable : null, fe.epr_applicable||'Unknown',                         'reported'],
          ['Est. Compliance Cost', fe.estimated_compliance_cost_band,                               fe.estimated_compliance_cost_band||'—',                                'estimated'],
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
  const dims = [
    ['GHG Intensity',   rb.ghg_intensity],
    ['Water Intensity', rb.water_intensity],
    ['Waste Intensity', rb.waste_intensity],
    ['EPR Exposure',    rb.epr_exposure],
    ['Compliance Risk', rb.compliance_risk],
    ['HR Risk',         rb.hr_risk],
    ['Governance Risk', rb.governance_risk],
  ];
  return `<div class="dd-section">
    <div class="dd-section-title">Risk Dimension Breakdown</div>
    <div class="dd-risk-bars">
      ${dims.map(([label, val]) => {
        const v = val || 0;
        const cls = v >= 7 ? 'red' : v >= 4.5 ? 'amber' : 'green';
        return `<div class="dd-risk-row">
          <span class="dd-risk-label">${label}</span>
          <div class="dd-risk-track">
            <div class="dd-risk-fill dd-risk-fill--${cls}" style="width:${v*10}%"></div>
          </div>
          <span class="dd-risk-score">${v.toFixed(1)}</span>
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
  const peers   = data?.sector_peers || allCompanies.filter(c =>
    c.company_name !== p.company_name &&
    (c.sector||'').slice(0,20).toLowerCase() === sector.slice(0,20).toLowerCase()
  ).slice(0, 5);

  const allSectorScores = peers.map(pp => pp.esg_risk_score);
  const sectorAvg = allSectorScores.length
    ? allSectorScores.reduce((a,b)=>a+b,0)/allSectorScores.length : 0;
  const position  = p.esg_risk_score > sectorAvg + 0.5 ? 'Higher risk than sector avg'
                  : p.esg_risk_score < sectorAvg - 0.5 ? 'Lower risk than sector avg'
                  : 'At sector average';

  return `<div class="dd-section">
    <div class="dd-section-title">Sector Peer Comparison</div>
    <div class="dd-bench-position ${p.esg_risk_score > sectorAvg ? 'bench-worse' : 'bench-better'}">
      ${position} · Sector avg: ${sectorAvg.toFixed(1)} · This company: ${p.esg_risk_score}
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

// ── Sector ESG Heat Map (Feature 11) ─────────────────────────────────────────
let _hmClickAttached = false;

function renderHeatMap() {
  const sectorFilter = document.getElementById('hm-sector-filter')?.value || '';
  const sizeBy       = document.getElementById('hm-size-by')?.value || 'uniform';
  const countEl      = document.getElementById('hm-count');
  const div          = document.getElementById('heatmapChart');
  if (!div) return;

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

function renderFilingTracker() {
  if (_ftRendered) return;
  _ftRendered = true;

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
const _WL = {
  _K:  'gc_watchlist',
  _SK: 'gc_wl_snapshots',
  _PK: 'gc_wl_alert_prefs',
  list()  { try { return JSON.parse(localStorage.getItem(this._K)  || '[]');  } catch { return []; } },
  save(a) { localStorage.setItem(this._K, JSON.stringify(a)); },
  add(n)  { const l = this.list(); if (!l.includes(n)) { l.push(n); this.save(l); } },
  remove(n){ this.save(this.list().filter(x => x !== n)); },
  has(n)  { return this.list().includes(n); },
  getSnaps()   { try { return JSON.parse(localStorage.getItem(this._SK) || '{}'); } catch { return {}; } },
  saveSnaps(o) { localStorage.setItem(this._SK, JSON.stringify(o)); },
  getPrefs()   { try { return JSON.parse(localStorage.getItem(this._PK) || '{"tier_change":true,"high_risk":true}'); } catch { return {tier_change:true,high_risk:true}; } },
  savePrefs(o) { localStorage.setItem(this._PK, JSON.stringify(o)); },
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
  const p = _WL.getPrefs(); p[key] = val; _WL.savePrefs(p);
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

initDashboard();
