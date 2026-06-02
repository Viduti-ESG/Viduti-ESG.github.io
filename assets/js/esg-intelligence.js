// ESG Financial Intelligence Dashboard
// Reads assets/data/esg_intelligence.json and renders all 4 panels

let INTEL = null;
let allCompanies = [];

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
    renderRegulations();
    renderSupplyChain();
    renderMaterials();
  } catch (e) {
    statusEl.textContent = 'Intelligence data not yet available — runs daily after 2 AM.';
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
      <tr>
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

// ── Utilities ──────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fmt(n) {
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(n);
}

initDashboard();
