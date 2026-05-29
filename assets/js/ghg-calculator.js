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
  const totals = { total: 0, s1: 0, s2: 0, s3: 0 };
  els.itemsTable.innerHTML = '';

  state.items.forEach(item => {
    const t = (item.factor * item.amount) / 1000;
    totals.total += t;
    if (item.scope === 'Scope 1') totals.s1 += t;
    if (item.scope === 'Scope 2') totals.s2 += t;
    if (item.scope === 'Scope 3') totals.s3 += t;

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
  const totals = { total: 0, s1: 0, s2: 0, s3: 0 };
  const items = state.items.map(item => {
    const t = (item.factor * item.amount) / 1000;
    totals.total += t;
    if (item.scope === 'Scope 1') totals.s1 += t;
    if (item.scope === 'Scope 2') totals.s2 += t;
    if (item.scope === 'Scope 3') totals.s3 += t;
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
}

initCalculator();
