// ═══════════════════════════════════════════════════════
// GHG Calculator — Feature Pack 2
// Net Zero Pathway, Spend-based S3, Reduction Levers,
// SBTi Generator, Shareable Profile, Offsets,
// Anomaly Detection, AI Chat
// ═══════════════════════════════════════════════════════

// ── Net Zero Pathway (Multi-Scenario, Plotly) ─────────────────────────────
function renderNetZeroPathway() {
  const section = document.getElementById('nz-section');
  if (!section) return;
  const totals = calcTotals();
  if (totals.total <= 0) { section.hidden = true; return; }
  section.hidden = false;

  const plotDiv = document.getElementById('nzChart');
  if (!plotDiv || !window.Plotly) return;

  const baseYear  = new Date().getFullYear();
  const endYear   = 2050;
  const years     = Array.from({length: endYear - baseYear + 1}, (_, i) => baseYear + i);
  const highlight = document.getElementById('nz-scenario-highlight')?.value || 'all';

  const bau    = years.map(() => +totals.total.toFixed(2));
  const b2deg  = years.map((_,i) => +(totals.total * Math.pow(1-0.025, i)).toFixed(2));
  const p15    = years.map((_,i) => +(totals.total * Math.pow(1-0.042, i)).toFixed(2));
  const nzs    = years.map((_,i) => +(totals.total * Math.max(0.10, 1-(i/(endYear-baseYear))*0.90)).toFixed(2));

  const showAll = highlight === 'all';
  const traces = [
    { x:years, y:bau,   name:'BAU (no action)',              line:{color:'#f87171',dash:'dot',width:2},              mode:'lines', visible: showAll ? true : 'legendonly' },
    { x:years, y:b2deg, name:'Well-below 2°C (−2.5%/yr)',   line:{color:'#fbbf24',width:2},                         mode:'lines', visible: showAll ? true : 'legendonly' },
    { x:years, y:p15,   name:'1.5°C Paris (−4.2%/yr)',      line:{color:'#10b981',width:2.5}, fill:'tozeroy', fillcolor:'rgba(16,185,129,.07)', mode:'lines', visible: (showAll || highlight==='paris') ? true : 'legendonly' },
    { x:years, y:nzs,   name:'Science-Based Net-Zero (−90% by 2050)',line:{color:'#6366f1',dash:'dash',width:2},              mode:'lines', visible: (showAll || highlight==='nzs') ? true : 'legendonly' },
  ];

  const layout = {
    paper_bgcolor:'transparent', plot_bgcolor:'transparent',
    font:{ family:'DM Sans, system-ui', color:'#64748b', size:11 },
    xaxis:{ gridcolor:'rgba(0,0,0,.06)', tickformat:'d', color:'#94a3b8', dtick:5 },
    yaxis:{ gridcolor:'rgba(0,0,0,.06)', title:{text:'t CO₂e/year',font:{size:10,color:'#94a3b8'}}, ticksuffix:'t', color:'#94a3b8' },
    legend:{ orientation:'h', x:0, y:-0.35, font:{size:10} },
    margin:{ t:8, r:8, b:90, l:55 },
    hovermode:'x unified',
    hoverlabel:{ bgcolor:'#1e293b', bordercolor:'#334155', font:{color:'#e2e8f0',size:11} },
  };

  Plotly.newPlot(plotDiv, traces, layout, {
    displayModeBar:true, displaylogo:false, responsive:true,
    modeBarButtonsToKeep:['toImage','zoom2d','resetScale2d','pan2d'],
  });

  const el = document.getElementById('nz-milestones');
  if (el) {
    el.innerHTML = [2030,2040,2050].map(yr => {
      const i   = yr - baseYear;
      const val = p15[i] || 0;
      const pct = ((1 - val/totals.total)*100).toFixed(0);
      return `<div class="nz-milestone"><strong>${val.toFixed(1)} t</strong><span>${yr}<br/>${pct}% reduction</span></div>`;
    }).join('');
  }
}

// ── Spend-based Scope 3 ──────────────────────────────────
const SPEND_FACTORS = {
  'Raw materials & components':     0.00054,
  'Logistics & freight':            0.00062,
  'Business travel (flights)':      0.00148,
  'Business travel (land)':         0.00042,
  'IT equipment & electronics':     0.00089,
  'Paper & office supplies':        0.00121,
  'Food & catering':                0.00076,
  'Professional services':          0.00028,
  'Utilities (outsourced)':         0.00095,
  'Construction & capex':           0.00118,
};

function renderSpendEstimator() {
  let total = 0;
  document.querySelectorAll('.spend-input').forEach(inp => {
    const v = Number(inp.value || 0);
    const factor = Number(inp.dataset.factor || 0);
    total += v * 10000000 * factor / 1000; // crore -> INR -> kg -> t
  });
  const preview = document.getElementById('spend-preview');
  if (preview) {
    if (total > 0) {
      preview.textContent = 'Estimated Scope 3: ~' + total.toFixed(1) + ' t CO2e/year from entered spend';
      preview.className = 'commute-preview commute-preview--active';
    } else {
      preview.textContent = 'Enter annual spend in INR Crore per category to estimate Scope 3';
      preview.className = 'commute-preview';
    }
  }
  return total;
}

function addSpendEntry() {
  const total = renderSpendEstimator();
  if (total <= 0) { alert('Enter at least one spend category.'); return; }
  state.items.push({
    id: 'spend-' + Date.now(),
    description: 'Scope 3 Spend-based estimate (Cat 1/4/6)',
    scope: 'Scope 3', amount: 1, unit: 'annual',
    factor: total * 1000,
  });
  document.querySelectorAll('.spend-input').forEach(inp => inp.value = '');
  renderSpendEstimator();
  updateResults();
}
window.addSpendEntry = addSpendEntry;

// ── Reduction Levers ─────────────────────────────────────
const REDUCTION_LEVERS = [
  { icon: '💡', title: 'Switch to LED lighting',           scope: 'Scope 2',   reduction: '5-15%',      cost: 'Low',         time: '3-6 months',   brsr: 'P6 Energy'          },
  { icon: '☀️', title: 'Install rooftop solar',            scope: 'Scope 2',   reduction: '20-60%',     cost: 'Medium',      time: '6-12 months',  brsr: 'P6 Energy + RPO'    },
  { icon: '🚗', title: 'Switch fleet to BS VI / EV',       scope: 'Scope 1',   reduction: '10-30%',     cost: 'Medium-High', time: '12-24 months', brsr: 'P6 Emissions'       },
  { icon: '❄️', title: 'Optimize HVAC & cooling',          scope: 'Scope 2',   reduction: '10-20%',     cost: 'Low-Medium',  time: '3-9 months',   brsr: 'P6 Energy'          },
  { icon: '🚂', title: 'Shift freight road → rail',        scope: 'Scope 3',   reduction: '60-80%',     cost: 'Low',         time: '1-3 months',   brsr: 'P6 Value Chain'     },
  { icon: '🏠', title: 'Remote / hybrid work policy',      scope: 'Scope 3',   reduction: '2-8%',       cost: 'None',        time: 'Immediate',    brsr: 'P6 Cat 7'           },
  { icon: '🟢', title: 'Buy RECs / green tariff',          scope: 'Scope 2',   reduction: '80-100%',    cost: 'Low',         time: '1-3 months',   brsr: 'P6 Market-based'    },
  { icon: '♻️', title: 'EPR compliance (plastics/e-waste)', scope: 'Scope 3',  reduction: 'Penalty avoidance', cost: 'Varies', time: '3-6 months', brsr: 'P6 EPR + CPCB'    },
  { icon: '⚙️', title: 'BEE-rated motors & pumps',         scope: 'Scope 1/2', reduction: '5-15%',      cost: 'Medium',      time: '6-18 months',  brsr: 'P6 Energy'          },
  { icon: '🔥', title: 'Waste-to-energy / biogas',         scope: 'Scope 1',   reduction: '3-10%',      cost: 'Medium',      time: '12-24 months', brsr: 'P6 Waste'           },
];

function renderReductionLevers() {
  const el = document.getElementById('levers-list');
  if (!el) return;
  el.innerHTML = REDUCTION_LEVERS.map(l => `
    <div class="lever-card">
      <div class="lever-icon">${l.icon}</div>
      <div class="lever-body">
        <div class="lever-title">${l.title}</div>
        <div class="lever-meta">
          <span class="lever-scope">${l.scope}</span>
          <span class="lever-reduction">↓ ${l.reduction}</span>
          <span class="lever-cost">Cost: ${l.cost}</span>
          <span class="lever-time">${l.time}</span>
        </div>
        <div class="lever-brsr">BRSR: ${l.brsr}</div>
      </div>
    </div>`).join('');
}

// ── SBTi Target Generator ────────────────────────────────
function renderSBTiTarget() {
  const el = document.getElementById('sbti-result');
  if (!el) return;
  const totals = calcTotals();
  if (totals.total <= 0) {
    el.innerHTML = '<p class="calc-note">Add emission items to generate SBTi targets.</p>';
    return;
  }
  const baseYear = new Date().getFullYear();
  const t2030 = +(totals.total * Math.pow(1 - 0.042, 2030 - baseYear)).toFixed(2);
  const t2050 = +(totals.total * 0.10).toFixed(2);

  el.innerHTML = `
    <div class="sbti-grid">
      <div class="sbti-card">
        <div class="sbti-val">${t2030} t CO2e</div>
        <div class="sbti-lbl">Near-term target (2030)</div>
        <div class="sbti-desc">${((1 - t2030/totals.total)*100).toFixed(0)}% absolute reduction<br>vs ${baseYear} baseline • 4.2%/yr</div>
      </div>
      <div class="sbti-card">
        <div class="sbti-val">${t2050} t CO2e</div>
        <div class="sbti-lbl">Long-term target (2050)</div>
        <div class="sbti-desc">90%+ absolute reduction<br>Residual offset via carbon removal</div>
      </div>
    </div>
    <p class="sbti-note">Indicative only. Official SBTi validation: <a href="https://sciencebasedtargets.org" target="_blank" rel="noopener">sciencebasedtargets.org</a>. These numbers map directly to BRSR target disclosure fields.</p>`;
}

// ── Shareable Profile ────────────────────────────────────
function generateShareableProfile() {
  const totals = calcTotals();
  if (totals.total <= 0) {
    alert('Add emission items to your inventory first.');
    return;
  }
  const revenue   = Number(document.getElementById('int-revenue')?.value || 0);
  const employees = Number(document.getElementById('int-employees')?.value || 0);
  const fy        = document.getElementById('yoy-fy')?.value || 'FY2025-26';
  const payload = {
    fy,
    s1: totals.s1.toFixed(2), s2: totals.s2.toFixed(2),
    s3: totals.s3.toFixed(2), tot: totals.total.toFixed(2),
    ri: revenue   > 0 ? (totals.total / revenue).toFixed(4)   : '',
    em: employees > 0 ? (totals.total / employees).toFixed(3) : '',
  };
  const encoded = btoa(JSON.stringify(payload));
  // Build base URL — works for file://, localhost, and GitHub Pages
  const origin  = (location.origin && location.origin !== 'null') ? location.origin : 'https://greencurve.solutions';
  const base    = origin + location.pathname.replace(/[^/]*$/, '');
  const url     = base + 'ghg-profile.html?d=' + encoded;

  navigator.clipboard.writeText(url)
    .then(() => showProfileToast(url))
    .catch(() => showProfileToast(url)); // show toast even if clipboard fails (HTTPS required for clipboard)
}
window.generateShareableProfile = generateShareableProfile;

function showProfileToast(url) {
  const toast   = document.getElementById('profile-toast');
  const urlEl   = document.getElementById('profile-toast-url');
  const viewBtn = document.getElementById('profile-toast-view');
  if (!toast) return;
  if (urlEl)   urlEl.textContent = url;
  if (viewBtn) viewBtn.href = url;
  toast.style.display = 'block';
  // Auto-dismiss after 6s
  clearTimeout(window._profileToastTimer);
  window._profileToastTimer = setTimeout(hideProfileToast, 6000);
}
window.showProfileToast = showProfileToast;

function hideProfileToast() {
  const toast = document.getElementById('profile-toast');
  if (toast) toast.style.display = 'none';
}
window.hideProfileToast = hideProfileToast;

// ── Carbon Offset Links ──────────────────────────────────
function renderCarbonOffsets() {
  const el = document.getElementById('offsets-list');
  if (!el) return;
  const totals = calcTotals();
  el.innerHTML = (totals.total > 0 ? `<p class="offsets-total">Your residual to offset: <strong>${totals.total.toFixed(1)} t CO2e</strong></p>` : '') + `
    <div class="offset-grid">
      <a class="offset-card" href="https://registry.goldstandard.org/projects?q=india" target="_blank" rel="noopener">
        <div class="offset-badge" style="background:#f59e0b;color:#fff">Gold Standard</div>
        <div class="offset-name">Gold Standard India</div>
        <div class="offset-desc">Cookstoves, solar, biogas, forestry — ICROA endorsed</div>
      </a>
      <a class="offset-card" href="https://registry.verra.org/app/projectPublicSearch/VCSATCM" target="_blank" rel="noopener">
        <div class="offset-badge" style="background:#10b981;color:#fff">Verra VCS</div>
        <div class="offset-name">Verra India Projects</div>
        <div class="offset-desc">REDD+, renewables, sustainable agriculture</div>
      </a>
      <a class="offset-card" href="https://cpcb.nic.in" target="_blank" rel="noopener">
        <div class="offset-badge" style="background:#6366f1;color:#fff">India CCTS</div>
        <div class="offset-name">India Carbon Credit Trading</div>
        <div class="offset-desc">Domestic credits under BEE-CCTS scheme</div>
      </a>
    </div>
    <p class="calc-note">Green Curve does not endorse specific providers. Verify credentials independently. Reduce emissions first — offsets are a last resort.</p>`;
}

// ── Anomaly Detection ────────────────────────────────────
function detectAnomalies() {
  const section = document.getElementById('anomaly-section');
  const list = document.getElementById('anomaly-list');
  if (!section || !list) return;
  if (!state.items.length) { section.hidden = true; return; }
  const totals = calcTotals();
  const flags = [];
  state.items.forEach(item => {
    const t = (item.factor * item.amount) / 1000;
    const pct = totals.total > 0 ? (t / totals.total * 100) : 0;
    if (pct > 60) flags.push('Single item <strong>' + item.description + '</strong> is ' + pct.toFixed(0) + '% of total — verify quantity and unit.');
    if (item.factor > 50000) flags.push('Very high emission factor for <strong>' + item.description + '</strong> (' + item.factor.toFixed(0) + ' kg/unit) — double-check unit selection.');
  });
  if (totals.s1 === 0 && state.items.length > 0) flags.push('No Scope 1 (Direct) emissions yet — have you added fuels or combustion sources?');
  if (totals.s2 === 0 && state.items.length > 0) flags.push('No Scope 2 (Electricity) yet — add grid electricity or CEA state entry.');
  section.hidden = flags.length === 0;
  list.innerHTML = flags.map(f => '<div class="anomaly-item">⚠ ' + f + '</div>').join('');
}

// ── AI Carbon Copilot ────────────────────────────────────
function initChatCopilot() {
  const toggle = document.getElementById('chat-toggle');
  const panel  = document.getElementById('chat-panel');
  if (!toggle || !panel) return;
  toggle.addEventListener('click', () => { panel.hidden = !panel.hidden; if (!panel.hidden) document.getElementById('chat-input')?.focus(); });
  document.getElementById('chat-close')?.addEventListener('click', () => { panel.hidden = true; });
  document.getElementById('chat-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    const input = document.getElementById('chat-input');
    const q = input?.value?.trim();
    if (!q) return;
    input.value = '';
    appendChatMsg('user', q);
    appendChatMsg('bot', '...', true);
    const api = window._gcApiBase || localStorage.getItem('gc_api_base') || '';
    if (!api) { updateLastChatMsg('Chat needs the Green Curve backend online. Start it via start_brsr.py or deploy to Render.'); return; }
    const totals = calcTotals();
    try {
      const res = await fetch(api + '/api/ghg-chat', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          question: q,
          inventory: state.items.map(i => ({ description: i.description, scope: i.scope, amount: i.amount, unit: i.unit, result_t_co2e: +((i.factor*i.amount)/1000).toFixed(3) })),
          total_t_co2e: +totals.total.toFixed(3), scope1: +totals.s1.toFixed(3), scope2: +totals.s2.toFixed(3), scope3: +totals.s3.toFixed(3),
        }),
        signal: AbortSignal.timeout(20000),
      });
      if (!res.ok) { updateLastChatMsg('The AI copilot is temporarily unavailable — please try again later.'); return; }
      const data = await res.json();
      updateLastChatMsg(data.answer || 'No response.');
    } catch { updateLastChatMsg('Could not reach backend. Make sure it is running.'); }
  });
}

function appendChatMsg(role, text, loading) {
  const msgs = document.getElementById('chat-messages');
  if (!msgs) return;
  const d = document.createElement('div');
  d.className = 'chat-msg chat-msg--' + role + (loading ? ' chat-msg--loading' : '');
  d.textContent = text;
  msgs.appendChild(d);
  msgs.scrollTop = msgs.scrollHeight;
}
function updateLastChatMsg(text) {
  const el = document.querySelector('#chat-messages .chat-msg--loading');
  if (el) { el.textContent = text; el.classList.remove('chat-msg--loading'); }
}

// ── Feature: PDF Electricity Bill Import ─────────────────
async function uploadBill(input) {
  const file = input.files[0];
  if (!file) return;
  const status = document.getElementById('bill-extract-status');
  const api = window._gcApiBase || localStorage.getItem('gc_api_base') || '';
  if (!api) {
    status.textContent = '✗ Backend offline — start the BRSR backend first';
    status.style.color = '#f87171';
    input.value = '';
    return;
  }
  status.textContent = '⏳ Reading bill…';
  status.style.color = '#94a3b8';
  try {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(api + '/api/extract-bill', {
      method: 'POST', body: form,
      signal: AbortSignal.timeout(30000),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Server error');
    }
    const result = await res.json();
    const d = result.data;

    // Pre-fill kWh field
    if (d.kwh) document.getElementById('cea-kwh').value = d.kwh;

    // Match state in dropdown
    if (d.state) {
      const sel = document.getElementById('cea-state');
      const needle = d.state.toLowerCase();
      const match = Array.from(sel.options).find(o =>
        o.text.toLowerCase().includes(needle) ||
        needle.includes(o.text.toLowerCase().split(/[\s—–]/)[0].trim())
      );
      if (match) sel.value = match.value;
    }

    const parts = [`${d.kwh.toLocaleString('en-IN')} kWh`];
    if (d.state)  parts.push(d.state);
    if (d.discom) parts.push(d.discom);
    if (d.period_months > 1) parts.push(`${d.period_months}-month bill`);
    status.textContent = `✓ ${parts.join(' · ')} — review state & click Add`;
    status.style.color = '#10b981';

    document.getElementById('cea-module')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    if (typeof gtag === 'function') gtag('event', 'bill_pdf_extracted', { kwh: d.kwh, state: d.state });
  } catch (e) {
    status.textContent = `✗ ${e.message || 'Extraction failed'} — enter kWh manually`;
    status.style.color = '#f87171';
  }
  input.value = '';
}
window.uploadBill = uploadBill;

// ── Feature 14: Python Math Verification ─────────────────
async function verifyGHGMath() {
  const label = document.getElementById('verify-ghg-label');
  if (!label) return;
  if (!state.items.length) { alert('Add items first.'); return; }
  const api = window._gcApiBase || localStorage.getItem('gc_api_base') || '';
  if (!api) {
    label.textContent = '✗ Backend offline';
    setTimeout(() => { label.textContent = '✓ Verify Math'; }, 3000);
    return;
  }
  label.textContent = '⏳ Verifying…';
  try {
    const res = await fetch(api + '/api/verify-ghg', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        items: state.items.map(i => ({
          description: i.description, scope: i.scope,
          amount: i.amount, unit: i.unit, factor: i.factor,
        })),
      }),
      signal: AbortSignal.timeout(10000),
    });
    const data = await res.json();
    if (data.verified) {
      const jsTotal = calcTotals().total;
      const pyTotal = data.total_t;
      const match = Math.abs(jsTotal - pyTotal) < 0.005;
      label.textContent = match ? `✓ Verified ${pyTotal.toFixed(3)} t` : `⚠ Mismatch JS:${jsTotal.toFixed(3)} Py:${pyTotal.toFixed(3)}`;
      setTimeout(() => { label.textContent = '✓ Verify Math'; }, 6000);
    }
  } catch {
    label.textContent = '✗ Verify failed';
    setTimeout(() => { label.textContent = '✓ Verify Math'; }, 3000);
  }
}
window.verifyGHGMath = verifyGHGMath;

// ── Patch updateResults ───────────────────────────────────
const _origUR2 = updateResults;
updateResults = function() {
  _origUR2();
  renderNetZeroPathway();
  renderSBTiTarget();
  renderReductionLevers();
  renderCarbonOffsets();
  detectAnomalies();
};

// ── DOMContentLoaded init ─────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.spend-input').forEach(inp => inp.addEventListener('input', renderSpendEstimator));
  document.getElementById('spend-add')?.addEventListener('click', addSpendEntry);
  renderSpendEstimator();
  renderReductionLevers();
  initChatCopilot();
});
