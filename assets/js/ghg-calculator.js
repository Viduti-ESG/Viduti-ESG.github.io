// === constants ================================================================
const STORAGE_KEY = 'greencurve_ghg_v2';

const CATEGORY_LABELS = {
  'Fuels': 'Combustion Fuels',
  'Passenger vehicles': 'Company / Owned Vehicles',
  'Delivery vehicles': 'Delivery & Fleet Vehicles',
  'Refrigerant & other': 'Refrigerants & Gases',
  'Bioenergy': 'Bioenergy',
  'Electricity': 'Grid Electricity (by country)',
  'Heat and steam': 'Heat & Steam',
  'UK electricity': 'UK Grid Electricity',
  'UK electricity for Evs': 'UK EV Electricity',
  'UK electricity T&D for EVs': 'UK EV T&D',
  'Business travel- air': 'Air Travel',
  'Business travel- land': 'Employee Land Travel',
  'Business travel- sea': 'Sea Travel',
  'Freighting goods': 'Freight & Logistics',
  'Hotel stay': 'Hotel Stays',
  'Managed assets- electricity': 'Managed Assets – Electricity',
  'Managed assets- vehicles': 'Managed Assets – Vehicles',
  'Material use': 'Materials',
  'Transmission and distribution': 'T&D Losses',
  'Waste disposal': 'Waste Disposal',
  'Water supply': 'Water Supply',
  'Water treatment': 'Water Treatment',
  'WTT- UK & overseas elec': 'WTT – Electricity',
  'WTT- bioenergy': 'WTT – Bioenergy',
  'WTT- business travel- air': 'WTT – Air Travel',
  'WTT- business travel- sea': 'WTT – Sea Travel',
  'WTT- delivery vehs & freight': 'WTT – Delivery & Freight',
  'WTT- fuels': 'WTT – Fuels',
  'WTT- heat and steam': 'WTT – Heat & Steam',
  'WTT- pass vehs & travel- land': 'WTT – Land Travel',
};

const WTT_SET = new Set([
  'WTT- UK & overseas elec', 'WTT- bioenergy', 'WTT- business travel- air',
  'WTT- business travel- sea', 'WTT- delivery vehs & freight', 'WTT- fuels',
  'WTT- heat and steam', 'WTT- pass vehs & travel- land',
]);

// === state ====================================================================
const state = {
  factors: [],
  scope: 'Scope 1',
  level1: '',
  level2: null,   // null = not applicable (no level2 in hierarchy for this category)
  level3: '',
  uom: '',
  activeEntry: null,
  items: [],
};

// === DOM refs =================================================================
const els = {
  category:      document.getElementById('dd-category'),
  subcatGroup:   document.getElementById('dd-subcat-group'),
  subcat:        document.getElementById('dd-subcat'),
  sourceGroup:   document.getElementById('dd-source-group'),
  source:        document.getElementById('dd-source'),
  unitGroup:     document.getElementById('dd-unit-group'),
  unit:          document.getElementById('dd-unit'),
  factorPreview: document.getElementById('factor-preview'),
  factorValue:   document.getElementById('factor-value'),
  factorSrc:     document.getElementById('factor-source-val'),
  qtyGroup:      document.getElementById('dd-qty-group'),
  qty:           document.getElementById('dd-qty'),
  addBtn:        document.getElementById('dd-add'),
  customDesc:    document.getElementById('custom-description'),
  customFactor:  document.getElementById('custom-factor'),
  customUnit:    document.getElementById('custom-unit'),
  customAmount:  document.getElementById('custom-amount'),
  customAdd:     document.getElementById('custom-add'),
  itemsTable:    document.getElementById('items-table'),
  totalEmissions:document.getElementById('total-emissions'),
  scope1Total:   document.getElementById('scope1-total'),
  scope2Total:   document.getElementById('scope2-total'),
  scope3Total:   document.getElementById('scope3-total'),
  loadedCount:   document.getElementById('loaded-count'),
  scope1Count:   document.getElementById('scope1-count'),
  scope2Count:   document.getElementById('scope2-count'),
  scope3Count:   document.getElementById('scope3-count'),
  resetItems:    document.getElementById('reset-items'),
  downloadReport:document.getElementById('download-report'),
  exportJson:    document.getElementById('export-json'),
};

// === utilities ================================================================
function fmt(v, d = 2) {
  return new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: d, maximumFractionDigits: d,
  }).format(v);
}

// === data helpers =============================================================
function getLevel1List(scope) {
  return [...new Set(
    state.factors
      .filter(e => e.scope === scope && !WTT_SET.has(e.level1))
      .map(e => e.level1)
  )].sort();
}

function getLevel2List(scope, level1) {
  return [...new Set(
    state.factors
      .filter(e => e.scope === scope && e.level1 === level1 && e.level2)
      .map(e => e.level2)
  )].sort();
}

function getLevel3List(scope, level1, level2) {
  // level2 === null means "category has no level2" (e.g. Electricity)
  return [...new Set(
    state.factors
      .filter(e =>
        e.scope === scope &&
        e.level1 === level1 &&
        (level2 !== null ? e.level2 === level2 : !e.level2)
      )
      .map(e => e.level3).filter(Boolean)
  )].sort();
}

function getUomList(scope, level1, level2, level3) {
  return [...new Set(
    state.factors
      .filter(e =>
        e.scope === scope &&
        e.level1 === level1 &&
        (level2 !== null ? e.level2 === level2 : !e.level2) &&
        e.level3 === level3
      )
      .map(e => e.uom).filter(Boolean)
  )].sort();
}

function findEntry(scope, level1, level2, level3, uom) {
  return state.factors.find(e =>
    e.scope === scope &&
    e.level1 === level1 &&
    (level2 !== null ? e.level2 === level2 : !e.level2) &&
    e.level3 === level3 &&
    e.uom === uom
  ) || null;
}

// === dropdown helpers =========================================================
function fillSelect(el, options, placeholder, labelFn) {
  el.innerHTML = '';
  el.appendChild(new Option(placeholder, ''));
  options.forEach(v => {
    const label = labelFn ? labelFn(v) : v;
    el.appendChild(new Option(label, v));
  });
}

function hideStepsFrom(step) {
  // step order: subcat → source → unit → factorPreview → qty
  const order = ['subcat', 'source', 'unit', 'factor', 'qty'];
  const idx = order.indexOf(step);
  if (idx <= 0) { els.subcatGroup.hidden = true; els.subcat.value = ''; state.level2 = null; }
  if (idx <= 1) { els.sourceGroup.hidden = true; els.source.value = ''; state.level3 = ''; }
  if (idx <= 2) { els.unitGroup.hidden = true; els.unit.value = ''; state.uom = ''; }
  if (idx <= 3) { els.factorPreview.hidden = true; state.activeEntry = null; }
  if (idx <= 4) { els.qtyGroup.hidden = true; els.addBtn.hidden = true; if (els.qty) els.qty.value = ''; }
}

// === scope change =============================================================
function handleScopeChange(scope) {
  state.scope = scope;
  state.level1 = '';
  state.level2 = null;
  state.level3 = '';
  state.uom = '';
  state.activeEntry = null;

  document.querySelectorAll('.scope-tab').forEach(btn => {
    const active = btn.dataset.scope === scope;
    btn.classList.toggle('scope-tab--active', active);
    btn.setAttribute('aria-selected', String(active));
  });

  fillSelect(els.category, getLevel1List(scope),
    '— Choose activity category',
    k => CATEGORY_LABELS[k] || k);

  hideStepsFrom('subcat');
}

// === cascading dropdowns ======================================================
function handleCategoryChange() {
  const level1 = els.category.value;
  state.level1 = level1;
  hideStepsFrom('subcat');

  if (!level1) return;

  const level2s = getLevel2List(state.scope, level1);

  if (level2s.length) {
    fillSelect(els.subcat, level2s, '— Choose sub-category');
    els.subcatGroup.hidden = false;
  } else {
    // No level2 for this category (e.g. Electricity → jump to countries)
    state.level2 = null;
    const level3s = getLevel3List(state.scope, level1, null);
    fillSelect(els.source, level3s, '— Choose source');
    els.sourceGroup.hidden = false;
  }
}

function handleSubcatChange() {
  const level2 = els.subcat.value;
  state.level2 = level2 || null;
  hideStepsFrom('source');

  if (!level2) return;

  const level3s = getLevel3List(state.scope, state.level1, level2);
  fillSelect(els.source, level3s, '— Choose source');
  els.sourceGroup.hidden = false;
}

function handleSourceChange() {
  const level3 = els.source.value;
  state.level3 = level3;
  hideStepsFrom('unit');

  if (!level3) return;

  const uoms = getUomList(state.scope, state.level1, state.level2, level3);

  if (uoms.length === 1) {
    state.uom = uoms[0];
    els.unitGroup.hidden = true;
    showFactorPreview();
  } else {
    fillSelect(els.unit, uoms, '— Choose unit');
    els.unitGroup.hidden = false;
  }
}

function handleUomChange() {
  state.uom = els.unit.value;
  hideStepsFrom('factor');
  if (state.uom) showFactorPreview();
}

function showFactorPreview() {
  const entry = findEntry(state.scope, state.level1, state.level2, state.level3, state.uom);
  state.activeEntry = entry;
  if (!entry) return;

  els.factorValue.textContent = `${entry.factor} kg CO₂e / ${entry.uom || entry.uom_simple}`;
  if (els.factorSrc) {
    const parts = [entry.source, entry.vintage, entry.country].filter(Boolean);
    els.factorSrc.textContent = parts.join(' · ') || 'DEFRA';
  }
  els.factorPreview.hidden = false;
  els.qtyGroup.hidden = false;
  els.addBtn.hidden = false;
  els.qty.focus();
}

// === add item =================================================================
function handleAddItem() {
  const entry = state.activeEntry;
  const qty = Number(els.qty.value);

  if (!entry) { alert('Select a complete emission source first.'); return; }
  if (!qty || qty <= 0) { alert('Enter a quantity greater than 0.'); return; }

  const parts = [
    CATEGORY_LABELS[state.level1] || state.level1,
    state.level2,
    state.level3,
  ].filter(Boolean);

  state.items.push({
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    description: parts.join(' › '),
    scope: entry.scope,
    amount: qty,
    unit: entry.uom || entry.uom_simple || 'unit',
    factor: entry.factor,
  });

  els.qty.value = '';
  updateResults();
}

// === custom item ==============================================================
function addCustomItem() {
  const desc   = els.customDesc.value.trim();
  const factor = Number(els.customFactor.value);
  const amount = Number(els.customAmount.value);
  const unit   = els.customUnit.value.trim() || 'unit';

  if (!desc)             { alert('Enter a description.'); return; }
  if (!factor || factor <= 0) { alert('Enter a valid emission factor (kg CO₂e per unit).'); return; }
  if (!amount || amount <= 0) { alert('Enter a valid quantity.'); return; }

  state.items.push({
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    description: desc, scope: 'Custom', amount, unit, factor,
  });
  els.customDesc.value = '';
  els.customFactor.value = '';
  els.customUnit.value = '';
  els.customAmount.value = '';
  updateResults();
}

// === results ==================================================================
function calcTotals() {
  return state.items.reduce((t, item) => {
    const v = (item.factor * item.amount) / 1000;
    t.total += v;
    if (item.scope === 'Scope 1') t.s1 += v;
    if (item.scope === 'Scope 2') t.s2 += v;
    if (item.scope === 'Scope 3') t.s3 += v;
    return t;
  }, { total: 0, s1: 0, s2: 0, s3: 0 });
}

function loadSavedItems() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) { const p = JSON.parse(raw); if (Array.isArray(p)) return p; }
  } catch { /* ignore */ }
  return [];
}

function saveItems() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.items));
}

function updateResults() {
  const totals = calcTotals();
  els.itemsTable.innerHTML = '';

  state.items.forEach(item => {
    const t = (item.factor * item.amount) / 1000;
    const row = document.createElement('tr');
    [
      { text: item.description, strong: true },
      { text: item.scope },
      { text: `${fmt(item.amount)} ${item.unit}` },
      { text: `${fmt(item.factor, 3)} kg` },
      { text: `${fmt(t, 3)} t` },
      { removeId: item.id },
    ].forEach(cell => {
      const td = document.createElement('td');
      if (cell.removeId) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = '✕';
        btn.title = 'Remove';
        btn.addEventListener('click', () => removeItem(cell.removeId));
        td.appendChild(btn);
      } else if (cell.strong) {
        const s = document.createElement('strong');
        s.textContent = cell.text;
        td.appendChild(s);
      } else {
        td.textContent = cell.text;
      }
      row.appendChild(td);
    });
    els.itemsTable.appendChild(row);
  });

  els.totalEmissions.textContent = fmt(totals.total, 3);
  els.scope1Total.textContent    = fmt(totals.s1, 3);
  els.scope2Total.textContent    = fmt(totals.s2, 3);
  els.scope3Total.textContent    = fmt(totals.s3, 3);
  saveItems();
}

function removeItem(id) {
  state.items = state.items.filter(i => i.id !== id);
  updateResults();
}

// === download / export ========================================================
function buildPayload() {
  const totals = calcTotals();
  const items = state.items.map(item => {
    const t = (item.factor * item.amount) / 1000;
    return { description: item.description, scope: item.scope, amount: item.amount,
             unit: item.unit, factor_kg_co2e: item.factor, result_t_co2e: +t.toFixed(3) };
  });
  return {
    generated_at: new Date().toISOString(), item_count: items.length,
    totals: { total_t_co2e: +totals.total.toFixed(3), scope1_t_co2e: +totals.s1.toFixed(3),
              scope2_t_co2e: +totals.s2.toFixed(3), scope3_t_co2e: +totals.s3.toFixed(3) },
    items,
  };
}

function downloadCSV() {
  if (!state.items.length) { alert('Add at least one item before downloading.'); return; }
  const header = ['Description','Scope','Amount','Unit','Factor (kg CO2e/unit)','Result (t CO2e)'];
  const rows = state.items.map(i => {
    const t = (i.factor * i.amount) / 1000;
    return [i.description, i.scope, i.amount, i.unit, i.factor, +t.toFixed(3)];
  });
  const csv = [header, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\r\n');
  triggerDownload(new Blob([csv], { type: 'text/csv;charset=utf-8;' }), `ghg-report-${Date.now()}.csv`);
}

function downloadJSON() {
  if (!state.items.length) { alert('Add at least one item before exporting.'); return; }
  triggerDownload(new Blob([JSON.stringify(buildPayload(), null, 2)], { type: 'application/json' }), `ghg-report-${Date.now()}.json`);
}

function triggerDownload(blob, filename) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
}

// === navigation ===============================================================
function initNavigation() {
  const burger    = document.getElementById('nav-burger');
  const mobileNav = document.getElementById('nav-mobile');
  if (!burger || !mobileNav) return;
  burger.addEventListener('click', () => {
    const open = burger.classList.toggle('open');
    mobileNav.classList.toggle('open', open);
    document.body.style.overflow = open ? 'hidden' : '';
    burger.setAttribute('aria-expanded', String(open));
  });
  mobileNav.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
    burger.classList.remove('open');
    mobileNav.classList.remove('open');
    document.body.style.overflow = '';
    burger.setAttribute('aria-expanded', 'false');
  }));
}

// === init =====================================================================
async function initCalculator() {
  if (!els.category || !els.itemsTable) return;

  if (!document.querySelector('script[src="assets/js/app.js"]')) initNavigation();

  state.items = loadSavedItems();
  updateResults();

  const statusEl  = document.getElementById('calc-status');
  const statusTxt = document.getElementById('calc-status-text');

  function setStatus(type, msg) {
    if (!statusEl) return;
    statusEl.className = `calc-status calc-status--${type}`;
    if (statusTxt) statusTxt.textContent = msg;
    if (type === 'ok') setTimeout(() => { statusEl.hidden = true; }, 5000);
  }

  try {
    setStatus('loading', 'Loading emission factors…');
    const res = await fetch('assets/data/ghg-factors.json?v=20260529');
    if (!res.ok) throw new Error(`HTTP ${res.status} — file not found`);
    state.factors = await res.json();

    const s1 = state.factors.filter(f => f.scope === 'Scope 1').length;
    const s2 = state.factors.filter(f => f.scope === 'Scope 2').length;
    const s3 = state.factors.filter(f => f.scope === 'Scope 3').length;
    if (els.loadedCount) els.loadedCount.textContent = state.factors.length.toLocaleString();
    if (els.scope1Count) els.scope1Count.textContent = s1.toLocaleString();
    if (els.scope2Count) els.scope2Count.textContent = s2.toLocaleString();
    if (els.scope3Count) els.scope3Count.textContent = s3.toLocaleString();

    handleScopeChange('Scope 1');
    setStatus('ok', `✓ ${state.factors.length.toLocaleString()} emission factors loaded. Select a scope to begin.`);

  } catch (err) {
    console.error('GHG factors load failed:', err);
    setStatus('error', `⚠ Failed to load factors: ${err.message}. Try refreshing the page (Ctrl+Shift+R).`);
    if (els.category) els.category.innerHTML = '<option value="">— Data unavailable — try refreshing</option>';
  }

  document.querySelectorAll('.scope-tab').forEach(btn =>
    btn.addEventListener('click', () => handleScopeChange(btn.dataset.scope)));

  els.category.addEventListener('change', handleCategoryChange);
  els.subcat.addEventListener('change', handleSubcatChange);
  els.source.addEventListener('change', handleSourceChange);
  els.unit.addEventListener('change', handleUomChange);
  els.addBtn.addEventListener('click', handleAddItem);
  els.qty.addEventListener('keydown', e => { if (e.key === 'Enter') handleAddItem(); });
  els.customAdd.addEventListener('click', addCustomItem);

  els.resetItems.addEventListener('click', () => {
    if (confirm('Clear all items from the inventory?')) {
      state.items = []; saveItems(); updateResults();
    }
  });

  if (els.downloadReport) els.downloadReport.addEventListener('click', downloadCSV);
  if (els.exportJson)     els.exportJson.addEventListener('click', downloadJSON);

  // BRSR export
  const brBtn = document.getElementById('export-brsr');
  if (brBtn) brBtn.addEventListener('click', exportBRSR);

  // CEA module
  const ceaBtn = document.getElementById('cea-add');
  if (ceaBtn) ceaBtn.addEventListener('click', addCEAEntry);

  // Commute module
  initCommuteModule();

  // Intensity live update
  ['int-revenue','int-employees'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', updateIntensity);
  });

  // Sector benchmarking
  initBenchmarking();

  // YoY
  const yoySave = document.getElementById('yoy-save');
  if (yoySave) yoySave.addEventListener('click', saveYoYSnapshot);
  renderYoYTable();

  // Detect India electricity selection → show CEA notice
  els.source.addEventListener('change', () => {
    const notice = document.getElementById('cea-notice');
    if (notice) notice.hidden = !(state.level3 && state.level3.toLowerCase().includes('india'));
  });
}

// ── Feature 2: Scope 3 GHG Protocol Category Labels ──────────────────────────
const S3_CATEGORY_MAP = {
  'Material use':                'Cat 1 · Purchased Goods & Services',
  'Freighting goods':            'Cat 4 · Upstream Transport & Distribution',
  'Waste disposal':              'Cat 5 · Waste in Operations',
  'Business travel- air':        'Cat 6 · Business Travel',
  'Business travel- land':       'Cat 6 · Business Travel',
  'Business travel- sea':        'Cat 6 · Business Travel',
  'Hotel stay':                  'Cat 6 · Business Travel',
  'Employee commuting':          'Cat 7 · Employee Commuting',
  'Water supply':                'Cat 1 · Purchased Goods & Services',
  'Water treatment':             'Cat 5 · Waste in Operations',
  'Managed assets- electricity': 'Cat 15 · Investments / Managed Assets',
  'Managed assets- vehicles':    'Cat 15 · Investments / Managed Assets',
  'Transmission and distribution':'Cat 3 · Energy-Related Activities (T&D)',
};

function getS3Label(level1) {
  return S3_CATEGORY_MAP[level1] || null;
}

// ── Feature 1: Hotspot Chart (Plotly sunburst — drill-down by Scope → Category) ──
function renderHotspot() {
  const section = document.getElementById('hotspot-section');
  if (!section || !state.items.length) { if (section) section.hidden = true; return; }
  section.hidden = false;

  const div = document.getElementById('hotspotChart');
  if (!div) return;

  const totals = calcTotals();
  const SCOPE_COLORS = { 'Scope 1': '#10b981', 'Scope 2': '#6366f1', 'Scope 3': '#f59e0b' };
  const CAT_PALETTES = {
    'Scope 1': ['rgba(16,185,129,.85)','rgba(52,211,153,.75)','rgba(110,231,183,.65)','rgba(167,243,208,.55)'],
    'Scope 2': ['rgba(99,102,241,.85)','rgba(129,140,248,.75)','rgba(165,180,252,.65)','rgba(199,210,254,.55)'],
    'Scope 3': ['rgba(245,158,11,.85)','rgba(251,191,36,.75)','rgba(252,211,77,.65)','rgba(253,230,138,.55)'],
  };

  // Root node
  const ids = ['root'], labels = ['All Scopes'], parents = [''], values = [0];
  const colors = ['rgba(52,211,153,.15)'];

  // Scope subtotals
  [['Scope 1', totals.s1], ['Scope 2', totals.s2], ['Scope 3', totals.s3]].forEach(([scope, sv]) => {
    if (sv > 0.0001) {
      ids.push(scope); labels.push(scope); parents.push('root');
      values.push(sv); colors.push(SCOPE_COLORS[scope]);
    }
  });

  // Category breakdown per scope
  const catMap = {};
  state.items.forEach(item => {
    const cat = item.description.split(' › ')[0] || item.description;
    const key = `${item.scope}|||${cat}`;
    if (!catMap[key]) catMap[key] = { scope: item.scope, cat, val: 0 };
    catMap[key].val += (item.factor * item.amount) / 1000;
  });

  const scopeCatIdx = { 'Scope 1': 0, 'Scope 2': 0, 'Scope 3': 0 };
  Object.values(catMap).sort((a, b) => b.val - a.val).forEach(({ scope, cat, val }) => {
    if (val <= 0.0001 || !SCOPE_COLORS[scope]) return;
    const idx = scopeCatIdx[scope]++;
    ids.push(`${scope}|||${cat}`);
    labels.push(cat.length > 20 ? cat.slice(0, 18) + '…' : cat);
    parents.push(scope);
    values.push(val);
    colors.push(CAT_PALETTES[scope][idx % CAT_PALETTES[scope].length]);
  });

  Plotly.react(div, [{
    type: 'sunburst',
    ids, labels, parents, values,
    branchvalues: 'total',
    marker: { colors, line: { width: 1, color: 'rgba(0,0,0,.2)' } },
    hovertemplate: '<b>%{label}</b><br>%{value:.3f} t CO₂e<br>%{percentParent:.0%} of parent<extra></extra>',
    textinfo: 'label+percent parent',
    textfont: { size: 10, color: '#fff' },
    insidetextorientation: 'auto',
  }], {
    paper_bgcolor: 'transparent',
    font: { color: '#cbd5e1', family: 'DM Sans, sans-serif', size: 10 },
    margin: { l: 0, r: 0, t: 0, b: 0 },
    height: 220,
  }, { displayModeBar: false, responsive: true });

  // Legend: top categories by emissions
  const COLORS = ['#10b981','#6366f1','#f59e0b','#f87171','#38bdf8','#a78bfa','#64748b'];
  const legendEl = document.getElementById('hotspot-legend');
  if (legendEl) {
    const topCats = Object.values(catMap).sort((a, b) => b.val - a.val).slice(0, 7);
    legendEl.innerHTML = topCats.map(({ cat, val }, i) => {
      const pct = totals.total > 0 ? (val / totals.total * 100).toFixed(1) : '0';
      const lbl = cat.length > 22 ? cat.slice(0, 20) + '…' : cat;
      return `<div class="hs-legend-item">
        <span class="hs-dot" style="background:${COLORS[i]}"></span>
        <span class="hs-label">${lbl}</span>
        <span class="hs-pct">${pct}%</span>
      </div>`;
    }).join('');
  }
}

// ── Feature 4: Intensity Metrics ──────────────────────────────────────────────
function updateIntensity() {
  const totals  = calcTotals();
  const revenue = Number(document.getElementById('int-revenue')?.value || 0);
  const employees = Number(document.getElementById('int-employees')?.value || 0);

  const revVal = document.getElementById('int-rev-val');
  const empVal = document.getElementById('int-emp-val');
  const s1PctVal = document.getElementById('int-s1pct-val');

  if (revVal) revVal.textContent   = revenue > 0 ? (totals.total / revenue).toFixed(4) : '—';
  if (empVal) empVal.textContent   = employees > 0 ? (totals.total / employees).toFixed(3) : '—';
  if (s1PctVal) s1PctVal.textContent = totals.total > 0 ? (totals.s1/totals.total*100).toFixed(1)+'%' : '—';
}

// ── Feature 3: CEA State Grid ─────────────────────────────────────────────────
function addCEAEntry() {
  const stateEl = document.getElementById('cea-state');
  const kwhEl   = document.getElementById('cea-kwh');
  const factor  = Number(stateEl?.value);
  const kwh     = Number(kwhEl?.value);
  const label   = stateEl?.options[stateEl.selectedIndex]?.text?.split('—')[0]?.trim() || 'India';

  if (!factor) { alert('Select a state / region.'); return; }
  if (!kwh || kwh <= 0) { alert('Enter kWh consumed.'); return; }

  // Convert tCO₂/MWh × MWh to kg CO₂ factor per kWh: factor * 1000 / 1000 = factor kg/kWh
  const factorKg = factor; // tCO₂/MWh = kg CO₂/kWh
  state.items.push({
    id: `cea-${Date.now()}`,
    description: `Grid Electricity (CEA) › ${label}`,
    scope: 'Scope 2',
    amount: kwh,
    unit: 'kWh',
    factor: factorKg * 1000, // kg CO₂e per MWh, so per kWh = factor
  });

  kwhEl.value = '';
  updateResults();
}

// ── Feature 6: Employee Commute Module ────────────────────────────────────────
function initCommuteModule() {
  document.querySelectorAll('.commute-km').forEach(inp => {
    inp.addEventListener('input', updateCommutePreview);
  });
  const btn = document.getElementById('commute-add');
  if (btn) btn.addEventListener('click', addCommuteEntry);
  updateCommutePreview();
}

function updateCommutePreview() {
  const employees = Number(document.getElementById('com-employees')?.value || 0);
  const days      = Number(document.getElementById('com-days')?.value || 240);
  const rows      = document.querySelectorAll('.commute-km');
  let totalKm     = 0;
  let totalCO2    = 0;

  rows.forEach(inp => {
    const km = Number(inp.value || 0);
    const factor = Number(inp.dataset.factor || 0);
    totalKm  += km;
    totalCO2 += km * 2 * factor * employees * days; // round-trip, all employees, all days
  });

  // Update % labels
  rows.forEach(inp => {
    const km = Number(inp.value || 0);
    const pct = totalKm > 0 ? Math.round(km / totalKm * 100) : 0;
    // Find the sibling pct span (next sibling after input)
    const row = inp.closest('.commute-row');
    if (row) {
      const pctSpan = row.querySelector('.commute-pct');
      if (pctSpan) pctSpan.textContent = `${pct}%`;
    }
  });

  const preview = document.getElementById('commute-preview');
  if (preview) {
    if (employees > 0 && totalKm > 0) {
      preview.innerHTML = `<strong>${(totalCO2 / 1000).toFixed(2)} t CO₂e/year</strong> estimated for ${employees} employees over ${days} working days.`;
      preview.className = 'commute-preview commute-preview--active';
    } else {
      preview.innerHTML = 'Enter employee count and commute distances to preview emissions.';
      preview.className = 'commute-preview';
    }
  }
}

function addCommuteEntry() {
  const employees = Number(document.getElementById('com-employees')?.value || 0);
  const days      = Number(document.getElementById('com-days')?.value || 240);

  if (!employees || employees <= 0) { alert('Enter number of employees.'); return; }

  let totalCO2 = 0;
  document.querySelectorAll('.commute-km').forEach(inp => {
    const km = Number(inp.value || 0);
    const factor = Number(inp.dataset.factor || 0);
    totalCO2 += km * 2 * factor * employees * days;
  });

  if (totalCO2 <= 0) { alert('Enter at least one commute distance greater than 0.'); return; }

  // Add as a single Scope 3 line item (total kg CO₂e = totalCO2, qty=1, factor=totalCO2)
  state.items.push({
    id: `commute-${Date.now()}`,
    description: `Employee Commuting (Cat 7) › ${employees} employees, ${days} days`,
    scope: 'Scope 3',
    amount: 1,
    unit: 'annual total',
    factor: totalCO2,
  });

  updateResults();
}

// ── Feature 5: BRSR Export ────────────────────────────────────────────────────
function exportBRSR() {
  if (!state.items.length) { alert('Add at least one item before exporting.'); return; }
  const totals  = calcTotals();
  const revenue = Number(document.getElementById('int-revenue')?.value || 0);
  const employees = Number(document.getElementById('int-employees')?.value || 0);
  const fy = document.getElementById('yoy-fy')?.value || 'FY2025-26';

  const rows = [
    ['BRSR Section C — Principle 6: GHG Emissions (Draft)', '', '', ''],
    ['Generated by Green Curve GHG Calculator', new Date().toLocaleDateString('en-IN'), '', ''],
    ['Financial Year', fy, '', ''],
    ['DISCLAIMER: This is a draft export for data collection. Verify against audited data before BRSR submission.', '', '', ''],
    [''],
    ['Parameter', 'Unit', `${fy} (Current)`, 'Notes'],
    ['Scope 1 – Total GHG Emissions (Direct)', 'Metric tonnes CO₂e', totals.s1.toFixed(3), 'GHG Protocol Corporate Standard'],
    ['Scope 2 – Total GHG Emissions (Indirect - Purchased Energy)', 'Metric tonnes CO₂e', totals.s2.toFixed(3), 'Location-based method'],
    ['Scope 3 – Total GHG Emissions (Value Chain)', 'Metric tonnes CO₂e', totals.s3.toFixed(3), 'Voluntary under BRSR; mandatory under BRSR Core'],
    ['Total GHG Emissions (Scope 1 + Scope 2)', 'Metric tonnes CO₂e', (totals.s1 + totals.s2).toFixed(3), 'Required for BRSR mandatory disclosure'],
    [''],
    ['Intensity Metrics (BRSR Principle 6 – Required)', '', '', ''],
    ['GHG Emission Intensity per Rupee of Turnover', 'tCO₂e / ₹ Crore', revenue > 0 ? (totals.total/revenue).toFixed(4) : 'Enter revenue above', 'Scope 1+2+3 / Revenue (₹ Cr)'],
    ['GHG Emission Intensity per Employee', 'tCO₂e / Employee', employees > 0 ? (totals.total/employees).toFixed(3) : 'Enter employees above', 'Scope 1+2+3 / Total employees'],
    [''],
    ['Line Item Detail', '', '', ''],
    ['Description', 'Scope', 'Amount & Unit', 'Result (t CO₂e)'],
    ...state.items.map(item => {
      const t = (item.factor * item.amount) / 1000;
      return [item.description, item.scope, `${fmt(item.amount)} ${item.unit}`, t.toFixed(3)];
    }),
    [''],
    ['Data Sources', '', '', ''],
    ['Emission Factors', 'DEFRA 2024 / CEA CO₂ Baseline Database V21.0 (Nov 2025)', '', ''],
    ['Standard', 'GHG Protocol Corporate Standard / SEBI BRSR Framework', '', ''],
    ['Calculator', 'Green Curve GHG Calculator (viduti-esg.github.io/calculator.html)', '', ''],
  ];

  const csv = rows.map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\r\n');
  triggerDownload(new Blob(['﻿' + csv, { type: 'text/csv;charset=utf-8;' }]), `BRSR-GHG-${fy}-${Date.now()}.csv`);
}

// ── Feature 7: Year-on-Year Comparison ────────────────────────────────────────
const YOY_KEY = 'greencurve_ghg_yoy';

function loadYoYSnapshots() {
  try { return JSON.parse(localStorage.getItem(YOY_KEY) || '{}'); } catch { return {}; }
}

function saveYoYSnapshot() {
  const fy = document.getElementById('yoy-fy')?.value;
  if (!fy) return;
  if (!state.items.length) { alert('Add items before saving a snapshot.'); return; }
  const totals = calcTotals();
  const snaps  = loadYoYSnapshots();
  snaps[fy] = {
    fy,
    saved_at: new Date().toISOString(),
    total: +totals.total.toFixed(3),
    s1:    +totals.s1.toFixed(3),
    s2:    +totals.s2.toFixed(3),
    s3:    +totals.s3.toFixed(3),
    items: state.items.length,
  };
  localStorage.setItem(YOY_KEY, JSON.stringify(snaps));
  renderYoYTable();
  alert(`Snapshot saved for ${fy}: ${totals.total.toFixed(2)} t CO₂e`);
}

function renderYoYTable() {
  const wrap = document.getElementById('yoy-table-wrap');
  if (!wrap) return;
  const snaps = loadYoYSnapshots();
  const entries = Object.values(snaps).sort((a,b) => b.fy.localeCompare(a.fy));
  if (!entries.length) { wrap.hidden = true; return; }
  wrap.hidden = false;

  const rows = entries.map((s, i) => {
    const prev = entries[i+1];
    const chg  = prev ? ((s.total - prev.total) / prev.total * 100) : null;
    const chgHtml = chg !== null
      ? `<span style="color:${chg<=0?'#10b981':'#f87171'}">${chg>=0?'+':''}${chg.toFixed(1)}%</span>`
      : '—';
    return `<tr>
      <td><strong>${s.fy}</strong></td>
      <td>${s.total.toFixed(2)}</td>
      <td>${s.s1.toFixed(2)}</td>
      <td>${s.s2.toFixed(2)}</td>
      <td>${s.s3.toFixed(2)}</td>
      <td>${chgHtml}</td>
      <td><button class="yoy-delete" onclick="deleteYoYSnapshot('${s.fy}')">✕</button></td>
    </tr>`;
  }).join('');

  wrap.innerHTML = `<table class="calc-table">
    <thead><tr><th>FY</th><th>Total (t)</th><th>S1</th><th>S2</th><th>S3</th><th>vs Prior</th><th></th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function deleteYoYSnapshot(fy) {
  const snaps = loadYoYSnapshots();
  delete snaps[fy];
  localStorage.setItem(YOY_KEY, JSON.stringify(snaps));
  renderYoYTable();
}
window.deleteYoYSnapshot = deleteYoYSnapshot;

// ── Feature 8: Sector Benchmarking ────────────────────────────────────────────
async function initBenchmarking() {
  const sel = document.getElementById('bench-sector');
  if (!sel) return;
  try {
    const res = await fetch('assets/data/esg_quotient.json?v=' + Date.now());
    if (!res.ok) return;
    const data = await res.json();
    const companies = data.companies || [];

    // Build sector → intensity list
    const sectorMap = {};
    companies.forEach(c => {
      const sec = (c.sector || '').replace('Manufacturing — ','').trim().slice(0, 50);
      if (!sec || /^\d+$/.test(sec)) return;
      const fe  = c.financial_exposure || {};
      const s1  = fe.scope1_emissions_tco2e;
      const s2  = fe.scope2_emissions_tco2e;
      const rev = c.revenue_crore;
      if (s1 != null && s2 != null && rev > 0) {
        if (!sectorMap[sec]) sectorMap[sec] = [];
        sectorMap[sec].push({ total: (s1 + s2) / 1000, revenue: rev, score: c.esg_risk_score });
      }
    });

    // Only sectors with 3+ companies
    const validSectors = Object.entries(sectorMap)
      .filter(([,arr]) => arr.length >= 3)
      .sort(([a],[b]) => a.localeCompare(b));

    validSectors.forEach(([sec]) => {
      sel.appendChild(new Option(sec, sec));
    });

    sel.addEventListener('change', () => renderBenchmark(sel.value, sectorMap));
  } catch { /* benchmarking optional */ }
}

function renderBenchmark(sector, sectorMap) {
  const result = document.getElementById('benchmark-result');
  if (!result) return;
  if (!sector || !sectorMap[sector]) { result.hidden = true; return; }

  const peers    = sectorMap[sector];
  const avgInt   = peers.reduce((s,p) => s + p.total/p.revenue, 0) / peers.length;
  const avgScore = peers.reduce((s,p) => s + p.score, 0) / peers.length;
  const totals   = calcTotals();
  const revenue  = Number(document.getElementById('int-revenue')?.value || 0);

  result.hidden = false;

  if (revenue <= 0 || totals.total <= 0) {
    result.innerHTML = `<div class="bench-info">
      <strong>${peers.length} peer companies</strong> in "${sector}" tracked in Green Curve BRSR dataset.<br>
      Enter your revenue and emission items above to see how you compare.
    </div>`;
    return;
  }

  const yourInt = totals.total / revenue;
  const pctDiff = ((yourInt - avgInt) / avgInt * 100);
  const better  = pctDiff <= 0;
  const col     = better ? '#10b981' : '#f87171';

  result.innerHTML = `<div class="bench-result-grid">
    <div class="bench-card">
      <div class="bench-val">${yourInt.toFixed(4)}</div>
      <div class="bench-lbl">Your intensity (tCO₂e/₹Cr)</div>
    </div>
    <div class="bench-card">
      <div class="bench-val">${avgInt.toFixed(4)}</div>
      <div class="bench-lbl">Sector avg (${peers.length} peers)</div>
    </div>
    <div class="bench-card">
      <div class="bench-val" style="color:${col}">${better?'':'+'}${pctDiff.toFixed(1)}%</div>
      <div class="bench-lbl">${better ? 'Below sector avg ✓' : 'Above sector avg'}</div>
    </div>
    <div class="bench-card">
      <div class="bench-val">${avgScore.toFixed(1)}/10</div>
      <div class="bench-lbl">Avg ESG risk score</div>
    </div>
  </div>
  <p class="bench-note">Based on ${peers.length} companies' SEBI BRSR disclosures in the "${sector}" sector. Not investment advice.</p>`;
}

// ── Patch updateResults to trigger new features ────────────────────────────────
const _origUpdateResults = updateResults;
updateResults = function() {
  _origUpdateResults();
  renderHotspot();
  updateIntensity();
};

initCalculator();
