// ═══════════════════════════════════════════════════════
// GHG Calculator — Feature Pack 2
// Net Zero Pathway, Spend-based S3, Reduction Levers,
// SBTi Generator, Shareable Profile, Offsets,
// Anomaly Detection, AI Chat
// ═══════════════════════════════════════════════════════

// ── Net Zero Pathway ──────────────────────────────────────
function renderNetZeroPathway() {
  const section = document.getElementById('nz-section');
  if (!section) return;
  const totals = calcTotals();
  if (totals.total <= 0) { section.hidden = true; return; }
  section.hidden = false;

  const baseYear = new Date().getFullYear();
  const RATE = 0.042; // SBTi 1.5 degrees: ~4.2% per year
  const milestones = [2030, 2040, 2050];
  const vals = milestones.map(yr => +(totals.total * Math.pow(1 - RATE, yr - baseYear)).toFixed(2));
  vals[2] = +(totals.total * 0.10).toFixed(2); // 90% cut by 2050

  const canvas = document.getElementById('nzChart');
  if (!canvas) return;
  if (window._nzChart) window._nzChart.destroy();

  const allYears = Array.from({length: 2050 - baseYear + 1}, (_, i) => baseYear + i);
  const allVals  = allYears.map((yr, i) => {
    if (yr <= 2050) return +(totals.total * Math.pow(1 - RATE, i)).toFixed(2);
    return 0;
  });

  window._nzChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: allYears.filter((_, i) => i % 5 === 0),
      datasets: [{
        label: '1.5°C Required Pathway',
        data: allVals.filter((_, i) => i % 5 === 0),
        borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,.08)',
        borderWidth: 2.5, pointRadius: 3, fill: true, tension: 0.3,
      }],
    },
    options: {
      plugins: { legend: { labels: { color: '#374151', font: { size: 11 } } } },
      scales: {
        x: { ticks: { color: '#6b7280' }, grid: { color: 'rgba(0,0,0,.05)' } },
        y: {
          ticks: { color: '#6b7280', callback: v => v + 't' },
          grid: { color: 'rgba(0,0,0,.05)' },
          title: { display: true, text: 't CO2e/year', color: '#6b7280' },
        },
      },
    },
  });

  const el = document.getElementById('nz-milestones');
  if (el) {
    el.innerHTML = milestones.map((yr, i) => `
      <div class="nz-milestone">
        <strong>${vals[i]} t</strong>
        <span>${yr}<br/>${((1 - vals[i]/totals.total)*100).toFixed(0)}% reduction</span>
      </div>`).join('');
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
  const origin  = (location.origin && location.origin !== 'null') ? location.origin : 'https://viduti-esg.github.io';
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
