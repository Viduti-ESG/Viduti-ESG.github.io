// ESG Financial Quotient Dashboard
// Reads assets/data/esg_intelligence.json and renders all 4 panels

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

// ── Init ──────────────────────────────────────────────────────────────────────
async function initDashboard() {
  const statusEl = document.getElementById('heroMeta');
  try {
    const res = await fetch('assets/data/esg_intelligence.json?v=' + Date.now());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    INTEL = await res.json();
    allCompanies = INTEL.companies || [];

    const s = INTEL.summary || {};
    statusEl.textContent =
      `${s.total_companies || 0} companies analysed · ${s.regulations_analysed || 0} regulations tracked · Updated ${INTEL.data_as_of || ''}`;

    renderKPIs(s);
    renderCharts();
    renderScreener();
    renderDoubleMateriality();
    renderRegulations();
    renderTargets();
    renderSupplyChain();
    renderMaterials();
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

  new Chart(document.getElementById('chartSectorRisk'), {
    type: 'bar',
    data: {
      labels: entries.map(e => e.sector.replace('Manufacturing — ', '')),
      datasets: [{
        label: 'Avg ESG Risk Score',
        data: entries.map(e => e.avg.toFixed(1)),
        backgroundColor: entries.map(e => e.avg >= 6.5 ? 'rgba(248,113,113,.75)' : e.avg >= 4 ? 'rgba(251,191,36,.75)' : 'rgba(52,211,153,.75)'),
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: {
        x: { max: 10, grid: { color: 'rgba(255,255,255,.05)' }, ticks: { color: '#94a3b8' } },
        y: { grid: { display: false }, ticks: { color: '#cbd5e1', font: { size: 11 } } },
      },
    },
  });
}

function renderFactorsChart() {
  const factors = INTEL.factor_matrix?.factors || {};
  const labels = Object.values(factors).map(f => f.label);
  const scores = labels.map((_, i) => {
    const f = Object.values(factors)[i];
    const vals = Object.values(f.sector_risk || {});
    return vals.length ? (vals.reduce((a,b)=>a+b,0)/vals.length).toFixed(1) : 5;
  });

  new Chart(document.getElementById('chartFactors'), {
    type: 'radar',
    data: {
      labels,
      datasets: [{
        label: 'Avg Risk',
        data: scores,
        backgroundColor: 'rgba(99,102,241,.2)',
        borderColor: 'rgba(99,102,241,.8)',
        pointBackgroundColor: '#818cf8',
        pointRadius: 4,
      }],
    },
    options: {
      scales: {
        r: {
          min: 0, max: 10,
          grid: { color: 'rgba(255,255,255,.07)' },
          ticks: { color: '#94a3b8', backdropColor: 'transparent', stepSize: 2 },
          pointLabels: { color: '#cbd5e1', font: { size: 11 } },
        },
      },
      plugins: { legend: { display: false } },
    },
  });
}

function renderRegImpactChart() {
  const regs = (INTEL.regulations || []).slice(0, 15).reverse();
  new Chart(document.getElementById('chartRegImpact'), {
    type: 'bar',
    data: {
      labels: regs.map(r => (r.title || '').slice(0, 40) + (r.title?.length > 40 ? '…' : '')),
      datasets: [{
        label: 'Impact Score',
        data: regs.map(r => r.impact_score || 0),
        backgroundColor: regs.map(r => r.urgency === 'High' ? 'rgba(248,113,113,.75)' : r.urgency === 'Medium' ? 'rgba(251,191,36,.75)' : 'rgba(52,211,153,.75)'),
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: {
        x: { max: 10, grid: { color: 'rgba(255,255,255,.05)' }, ticks: { color: '#94a3b8' } },
        y: { grid: { display: false }, ticks: { color: '#94a3b8', font: { size: 10 } } },
      },
    },
  });
}

function renderMaterialsChart() {
  const freq = INTEL.factor_matrix?.material_frequency || {};
  const entries = Object.entries(freq).sort((a,b) => b[1]-a[1]).slice(0, 8);
  new Chart(document.getElementById('chartMaterials'), {
    type: 'doughnut',
    data: {
      labels: entries.map(([k]) => k.charAt(0).toUpperCase() + k.slice(1)),
      datasets: [{
        data: entries.map(([,v]) => v),
        backgroundColor: ['#10b981','#6366f1','#f59e0b','#f87171','#38bdf8','#a78bfa','#34d399','#fb923c'],
        borderWidth: 0,
      }],
    },
    options: {
      plugins: {
        legend: { position: 'right', labels: { color: '#94a3b8', font: { size: 11 }, padding: 12 } },
      },
    },
  });
}

// ── Company Screener ──────────────────────────────────────────────────────────
function renderScreener(filter = '', risk = '', sort = 'esg_risk_score') {
  let data = [...allCompanies];

  if (filter) {
    const q = filter.toLowerCase();
    data = data.filter(c =>
      (c.company_name || '').toLowerCase().includes(q) ||
      (c.sector || '').toLowerCase().includes(q)
    );
  }
  if (risk) data = data.filter(c => c.risk_tier === risk);

  if (sort === 'esg_risk_score') data.sort((a,b) => b.esg_risk_score - a.esg_risk_score);
  else if (sort === 'revenue_crore') data.sort((a,b) => (b.revenue_crore||0) - (a.revenue_crore||0));
  else if (sort === 'ghg') data.sort((a,b) => (b.risk_breakdown?.ghg_intensity||0) - (a.risk_breakdown?.ghg_intensity||0));
  else if (sort === 'market_return') data.sort((a,b) => (b.market_data?.return_1y_pct||0) - (a.market_data?.return_1y_pct||0));

  document.getElementById('screenerCount').textContent = `${data.length} companies`;

  const tbody = document.getElementById('screenerBody');
  tbody.innerHTML = data.map(c => {
    const rb = c.risk_breakdown || {};
    const md = c.market_data || {};
    const ret = md.return_1y_pct;
    const retHtml = ret != null
      ? `<span style="color:${ret >= 0 ? '#10b981' : '#f87171'}">${ret >= 0 ? '+' : ''}${ret}%</span>`
      : '<span style="color:#475569">N/A</span>';
    return `
      <tr style="cursor:pointer" onclick="openDeepDive('${esc(c.company_name)}')">
        <td class="company-name" title="${esc(c.company_name)}">${esc((c.company_name||'').slice(0,28))}${(c.company_name||'').length > 28 ? '…' : ''}</td>
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

// Screener filter wiring
document.getElementById('screenerSearch').addEventListener('input', e =>
  renderScreener(e.target.value, document.getElementById('screenerRisk').value, document.getElementById('screenerSort').value));
document.getElementById('screenerRisk').addEventListener('change', e =>
  renderScreener(document.getElementById('screenerSearch').value, e.target.value, document.getElementById('screenerSort').value));
document.getElementById('screenerSort').addEventListener('change', e =>
  renderScreener(document.getElementById('screenerSearch').value, document.getElementById('screenerRisk').value, e.target.value));

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
  new Chart(document.getElementById('chartMsme'), {
    type: 'doughnut',
    data: {
      labels: Object.keys(bands),
      datasets: [{ data: Object.values(bands), backgroundColor: ['#f87171','#fbbf24','#34d399','#10b981'], borderWidth: 0 }],
    },
    options: { plugins: { legend: { position: 'right', labels: { color: '#94a3b8' } } } },
  });

  // Upstream bottlenecks chart
  const upstream = Object.entries(sc.upstream_bottlenecks || {})
    .sort((a,b) => b[1].max_impact_score - a[1].max_impact_score).slice(0, 8);
  new Chart(document.getElementById('chartUpstream'), {
    type: 'bar',
    data: {
      labels: upstream.map(([,v]) => v.material_label),
      datasets: [
        { label: 'Max Regulation Impact', data: upstream.map(([,v]) => v.max_impact_score), backgroundColor: 'rgba(248,113,113,.7)', borderRadius: 4 },
        { label: 'Companies Exposed',     data: upstream.map(([,v]) => v.companies_exposed), backgroundColor: 'rgba(99,102,241,.7)', borderRadius: 4 },
      ],
    },
    options: {
      plugins: { legend: { labels: { color: '#94a3b8' } } },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#94a3b8' } },
        y: { grid: { color: 'rgba(255,255,255,.05)' }, ticks: { color: '#94a3b8' } },
      },
    },
  });

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
let _dmChart = null;

function renderDoubleMateriality(sectorFilter = '') {
  const data = sectorFilter
    ? allCompanies.filter(c => (c.sector||'').includes(sectorFilter))
    : allCompanies;

  document.getElementById('dmCount').textContent = `${data.length} companies`;

  // Populate sector filter
  const sectorSelect = document.getElementById('dmSectorFilter');
  if (sectorSelect.options.length <= 1) {
    const sectors = [...new Set(allCompanies.map(c => (c.sector||'').replace('Manufacturing — ','').slice(0,40)))].sort();
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

  if (_dmChart) _dmChart.destroy();
  _dmChart = new Chart(document.getElementById('chartDualMateriality'), {
    type: 'scatter',
    data: {
      datasets: [{
        label: 'Companies',
        data: points,
        backgroundColor: points.map(p => colorMap[p.tier] || 'rgba(148,163,184,.7)'),
        pointRadius: 6,
        pointHoverRadius: 9,
      }],
    },
    options: {
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => {
              const p = points[ctx.dataIndex];
              return [`${p.label}`, `Financial: ${ctx.parsed.x.toFixed(1)}  Impact: ${ctx.parsed.y.toFixed(1)}`, `Quadrant: ${p.quadrant}`];
            },
          },
        },
        annotation: {
          annotations: {
            vLine: { type:'line', xMin:5, xMax:5, borderColor:'rgba(255,255,255,.15)', borderWidth:1 },
            hLine: { type:'line', yMin:5, yMax:5, borderColor:'rgba(255,255,255,.15)', borderWidth:1 },
          },
        },
      },
      onClick: (e, els) => {
        if (els[0]) { const p = points[els[0].index]; openDeepDive(p.label); }
      },
      scales: {
        x: { min:0, max:10, title:{ display:true, text:'Financial Materiality →', color:'#94a3b8' }, grid:{ color:'rgba(255,255,255,.05)' }, ticks:{ color:'#94a3b8' } },
        y: { min:0, max:10, title:{ display:true, text:'Impact Materiality →', color:'#94a3b8' }, grid:{ color:'rgba(255,255,255,.05)' }, ticks:{ color:'#94a3b8' } },
      },
    },
  });

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

async function openDeepDive(companyName) {
  const overlay = document.getElementById('deepDiveOverlay');
  const body    = document.getElementById('deepDiveBody');
  const loading = document.getElementById('ddLoading');

  // Find basic profile from local data
  const profile = allCompanies.find(c => c.company_name === companyName);
  if (!profile) return;

  _currentDDCompany = profile;
  _currentDDData    = null;

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
      <div class="dd-kv-grid">
        ${[
          ['Scope 1 Emissions', fe.scope1_emissions_tco2e ? fe.scope1_emissions_tco2e+' tCO2e' : '—'],
          ['Scope 2 Emissions', fe.scope2_emissions_tco2e ? fe.scope2_emissions_tco2e+' tCO2e' : '—'],
          ['Water Withdrawal', fe.water_withdrawal_m3 ? fmt(fe.water_withdrawal_m3)+' m³' : '—'],
          ['Waste Generated', fe.waste_tonnes ? fmt(fe.waste_tonnes)+' tonnes' : '—'],
          ['EPR Applicable', fe.epr_applicable||'Unknown'],
        ].map(([l,v]) => `<div class="dd-kv"><span class="dd-kv-label">${l}</span><span class="dd-kv-val">${v}</span></div>`).join('')}
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

// ── Utilities ──────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fmt(n) {
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(n);
}

initDashboard();
