/* =============================================================================
   Green Curve — Guided ESG Data Baseline Wizard
   -----------------------------------------------------------------------------
   Helps a company capture "rough but consistent" ESG data across two quarters —
   the antidote to "we don't have the data". 100% client-side: everything is
   stored in the browser (localStorage) and nothing is sent to any server, so
   there is zero PII / DPDP exposure. The output hands off to the GHG Calculator
   and Compliance Calendar.
   ============================================================================ */

const BL_KEY = 'gc_baseline_v1';

const BL_CATS = [
  { id: 'energy', icon: '⚡', name: 'Purchased Electricity', tag: 'Scope 2',
    source: 'Electricity bills / DG meter readings',
    metrics: [{ id: 'grid_kwh', label: 'Grid electricity', unit: 'kWh' }] },
  { id: 'fuel', icon: '🔥', name: 'Combustion Fuels', tag: 'Scope 1',
    source: 'Fuel invoices, DG logs, vehicle fuel cards',
    metrics: [
      { id: 'diesel_l', label: 'Diesel', unit: 'litres' },
      { id: 'petrol_l', label: 'Petrol', unit: 'litres' },
      { id: 'lpg_kg', label: 'LPG', unit: 'kg' },
      { id: 'cng_kg', label: 'CNG', unit: 'kg' },
    ] },
  { id: 'water', icon: '💧', name: 'Water', tag: 'Environment',
    source: 'Water bills, borewell meter, tanker invoices',
    metrics: [{ id: 'water_kl', label: 'Water withdrawn', unit: 'kL' }] },
  { id: 'waste', icon: '🗑️', name: 'Waste', tag: 'Environment',
    source: 'Waste manifests, authorised-vendor receipts',
    metrics: [
      { id: 'waste_haz_t', label: 'Hazardous waste', unit: 'tonnes' },
      { id: 'waste_nonhaz_t', label: 'Non-hazardous waste', unit: 'tonnes' },
    ] },
  { id: 'workforce', icon: '👥', name: 'Workforce', tag: 'Social',
    source: 'HR / payroll records',
    metrics: [
      { id: 'emp_total', label: 'Total employees', unit: 'count', single: true },
      { id: 'emp_female_pct', label: 'Female employees', unit: '%', single: true },
      { id: 'lti', label: 'Lost-time injuries', unit: 'count' },
    ] },
  { id: 'travel', icon: '✈️', name: 'Business Travel', tag: 'Scope 3',
    source: 'Travel desk, expense reports',
    metrics: [
      { id: 'air_km', label: 'Air travel', unit: 'passenger-km' },
      { id: 'road_km', label: 'Road travel', unit: 'km' },
    ] },
];

let blState = { selected: [], data: {} }; // data: { metricId: {q1, q2} }

function blLoad() {
  try {
    const raw = localStorage.getItem(BL_KEY);
    if (raw) blState = Object.assign({ selected: [], data: {} }, JSON.parse(raw));
  } catch (e) { /* ignore */ }
}
function blSave() {
  try { localStorage.setItem(BL_KEY, JSON.stringify(blState)); } catch (e) { /* ignore */ }
}

function el(id) { return document.getElementById(id); }

// ── completeness ─────────────────────────────────────────────────────────────
function blMetricsForSelected() {
  const out = [];
  BL_CATS.filter(c => blState.selected.includes(c.id)).forEach(c =>
    c.metrics.forEach(m => out.push({ cat: c, m })));
  return out;
}
function blCompleteness() {
  const all = blMetricsForSelected();
  if (!all.length) return { pct: 0, filled: 0, total: 0 };
  let filled = 0, total = 0;
  all.forEach(({ m }) => {
    const d = blState.data[m.id] || {};
    if (m.single) { total += 1; if (d.q1 !== undefined && d.q1 !== '') filled += 1; }
    else { total += 2; if (d.q1 !== undefined && d.q1 !== '') filled += 1; if (d.q2 !== undefined && d.q2 !== '') filled += 1; }
  });
  return { pct: Math.round(filled / total * 100), filled, total };
}

// ── steps ────────────────────────────────────────────────────────────────────
let blStep = 0; // 0 intro, 1 select, 2 entry, 3 summary
const BL_STEPS = ['Intro', 'Choose categories', 'Enter data', 'Your baseline'];

function blRender() {
  const c = blCompleteness();
  el('bl-progress-bar').style.width = (blStep / (BL_STEPS.length - 1) * 100) + '%';
  el('bl-step').textContent = `Step ${blStep + 1} of ${BL_STEPS.length} · ${BL_STEPS[blStep]}`;
  if (blStep === 0) return blIntro();
  if (blStep === 1) return blSelect();
  if (blStep === 2) return blEntry();
  return blSummary();
}

function blIntro() {
  el('bl-card').innerHTML = `
    <h2 class="bl-h">First baseline? Start rough, stay consistent.</h2>
    <p class="bl-p">You don't need perfect data to begin. The goal of a baseline is <strong>rough but consistent</strong> numbers across two quarters — precision improves later. Gather whatever you can from these sources:</p>
    <ul class="bl-sources">
      ${BL_CATS.map(c => `<li><span>${c.icon}</span><div><strong>${c.name}</strong><em>${c.source}</em></div></li>`).join('')}
    </ul>
    <p class="bl-tip">💡 No exact figure? Estimate from a typical month × 3, or last year's total ÷ 4. A consistent estimate beats a blank.</p>
    <div class="bl-nav"><span></span><button class="bl-next" id="bl-go">Choose your categories &rarr;</button></div>`;
  el('bl-go').addEventListener('click', () => { blStep = 1; blRender(); });
}

function blSelect() {
  el('bl-card').innerHTML = `
    <h2 class="bl-h">Which apply to your operations?</h2>
    <p class="bl-p">Pick everything relevant — you can refine later. Most companies start with energy, fuel and workforce.</p>
    <div class="bl-cats">
      ${BL_CATS.map(c => `
        <button class="bl-cat${blState.selected.includes(c.id) ? ' bl-cat--on' : ''}" data-id="${c.id}">
          <span class="bl-cat__ic">${c.icon}</span>
          <span class="bl-cat__name">${c.name}</span>
          <span class="bl-cat__tag">${c.tag}</span>
        </button>`).join('')}
    </div>
    <div class="bl-nav">
      <button class="bl-back" id="bl-b">&larr; Back</button>
      <button class="bl-next" id="bl-n">Enter your data &rarr;</button>
    </div>`;
  el('bl-card').querySelectorAll('.bl-cat').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.id;
      const i = blState.selected.indexOf(id);
      if (i >= 0) blState.selected.splice(i, 1); else blState.selected.push(id);
      btn.classList.toggle('bl-cat--on');
      blSave();
    });
  });
  el('bl-b').addEventListener('click', () => { blStep = 0; blRender(); });
  el('bl-n').addEventListener('click', () => {
    if (!blState.selected.length) { alert('Pick at least one category to continue.'); return; }
    blStep = 2; blRender();
  });
}

function blEntry() {
  const cats = BL_CATS.filter(c => blState.selected.includes(c.id));
  el('bl-card').innerHTML = `
    <h2 class="bl-h">Enter what you have — two quarters</h2>
    <p class="bl-p">Rough figures are fine. Leave blanks where you genuinely have nothing yet; your completeness score updates live.</p>
    ${cats.map(c => `
      <div class="bl-grp">
        <div class="bl-grp__top"><span>${c.icon}</span><strong>${c.name}</strong><em>${c.source}</em></div>
        <div class="bl-rows">
          <div class="bl-rowhead"><span></span><span>Q1</span><span>${'Q2'}</span></div>
          ${c.metrics.map(m => {
            const d = blState.data[m.id] || {};
            return `<div class="bl-row">
              <label>${m.label} <em>(${m.unit})</em></label>
              <input type="number" min="0" step="any" data-mid="${m.id}" data-q="q1" value="${d.q1 ?? ''}" placeholder="0"/>
              ${m.single
                ? '<span class="bl-single">latest</span>'
                : `<input type="number" min="0" step="any" data-mid="${m.id}" data-q="q2" value="${d.q2 ?? ''}" placeholder="0"/>`}
            </div>`;
          }).join('')}
        </div>
      </div>`).join('')}
    <div class="bl-live">Completeness: <strong id="bl-live-pct">0%</strong></div>
    <div class="bl-nav">
      <button class="bl-back" id="bl-b">&larr; Categories</button>
      <button class="bl-next" id="bl-n">See my baseline &rarr;</button>
    </div>`;

  const updLive = () => { el('bl-live-pct').textContent = blCompleteness().pct + '%'; };
  updLive();
  el('bl-card').querySelectorAll('input[data-mid]').forEach(inp => {
    inp.addEventListener('input', () => {
      const mid = inp.dataset.mid, q = inp.dataset.q;
      blState.data[mid] = blState.data[mid] || {};
      blState.data[mid][q] = inp.value;
      blSave(); updLive();
    });
  });
  el('bl-b').addEventListener('click', () => { blStep = 1; blRender(); });
  el('bl-n').addEventListener('click', () => { blStep = 3; blRender(); });
}

function blSummary() {
  const c = blCompleteness();
  const cats = BL_CATS.filter(x => blState.selected.includes(x.id));
  // consistency flags: Q2 vs Q1 divergence > 60%
  const flags = [];
  cats.forEach(cat => cat.metrics.forEach(m => {
    if (m.single) return;
    const d = blState.data[m.id] || {};
    const q1 = parseFloat(d.q1), q2 = parseFloat(d.q2);
    if (q1 > 0 && q2 > 0) {
      const div = Math.abs(q2 - q1) / Math.max(q1, q2);
      if (div > 0.6) flags.push(`${cat.name} — ${m.label}: Q1 and Q2 differ by ${Math.round(div * 100)}%. Double-check the figures or note the reason.`);
    }
  }));
  const band = c.pct < 34 ? { t: 'Getting started', cls: 'low' }
    : c.pct < 75 ? { t: 'Solid baseline forming', cls: 'mid' }
    : { t: 'Baseline ready', cls: 'high' };

  const catStatus = cats.map(cat => {
    let f = 0, t = 0;
    cat.metrics.forEach(m => { const d = blState.data[m.id] || {}; const n = m.single ? 1 : 2; t += n; if (d.q1) f += 1; if (!m.single && d.q2) f += 1; });
    const pc = t ? Math.round(f / t * 100) : 0;
    return `<div class="bl-cs"><span>${cat.icon} ${cat.name}</span><span class="bl-cs__pct bl-cs__pct--${pc < 34 ? 'low' : pc < 75 ? 'mid' : 'high'}">${pc}%</span></div>`;
  }).join('');

  el('bl-card').innerHTML = `
    <div class="bl-result bl-result--${band.cls}">
      <div class="bl-ring"><div class="bl-ring__n">${c.pct}<span>%</span></div><div class="bl-ring__b">${band.t}</div></div>
      <p class="bl-p">You've captured <strong>${c.filled} of ${c.total}</strong> data points across ${cats.length} categor${cats.length === 1 ? 'y' : 'ies'}. ${c.pct >= 75 ? 'That\'s enough to start calculating and benchmarking.' : 'Keep filling the gaps quarter by quarter — consistency compounds.'}</p>
    </div>
    <h3 class="bl-sub">By category</h3>
    <div class="bl-csgrid">${catStatus}</div>
    ${flags.length ? `<h3 class="bl-sub">Consistency checks</h3><div class="bl-flags">${flags.map(f => `<div class="bl-flag">⚠ ${f}</div>`).join('')}</div>` : ''}
    <h3 class="bl-sub">Your next moves</h3>
    <div class="bl-recos">
      <div class="bl-reco"><p>Turn your energy & fuel figures into a Scope 1, 2 & 3 number using India CEA + DEFRA factors.</p><a href="calculator.html">Open the GHG Calculator &rarr;</a></div>
      <div class="bl-reco"><p>Lock in the filing dates so this baseline lands on time every cycle.</p><a href="compliance-calendar.html">Open the Compliance Calendar &rarr;</a></div>
      <div class="bl-reco"><p>Move from a spreadsheet to a year-round workspace with owners and evidence.</p><a href="/brsr-workspace">Open the BRSR Workspace &rarr;</a></div>
    </div>
    <div class="bl-actions">
      <button class="bl-back" id="bl-edit">&larr; Edit my data</button>
      <button class="bl-ghost" id="bl-reset">Clear &amp; start over</button>
    </div>
    <p class="bl-disc">Saved only in this browser — nothing is uploaded. This is a self-assessment aid, not a compliance filing.</p>`;

  el('bl-edit').addEventListener('click', () => { blStep = 2; blRender(); });
  el('bl-reset').addEventListener('click', () => {
    if (!confirm('Clear all baseline data from this browser?')) return;
    blState = { selected: [], data: {} }; blSave(); blStep = 0; blRender();
  });
  if (window.gtag) gtag('event', 'baseline_wizard_complete', { completeness: c.pct, categories: cats.length });
}

document.addEventListener('DOMContentLoaded', () => {
  blLoad();
  // resume where the user left off if they had data
  if (blState.selected.length && Object.keys(blState.data).length) blStep = 2;
  blRender();
});
