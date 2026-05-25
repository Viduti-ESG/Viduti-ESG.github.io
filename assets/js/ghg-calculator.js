const STORAGE_KEY = 'greencurve_ghg_items';
const state = {
  factors: [],
  selected: null,
  items: [],
  filter: 'All',
};

const els = {
  search: document.getElementById('factor-search'),
  results: document.getElementById('search-results'),
  filterBar: document.getElementById('filter-bar'),
  selectedCard: document.getElementById('selected-card'),
  selectedTitle: document.getElementById('selected-title'),
  selectedDetails: document.getElementById('selected-details'),
  selectedScope: document.getElementById('selected-scope'),
  selectedUnit: document.getElementById('selected-unit'),
  selectedFactor: document.getElementById('selected-factor'),
  amount: document.getElementById('item-amount'),
  addItem: document.getElementById('item-add'),
  customDescription: document.getElementById('custom-description'),
  customFactor: document.getElementById('custom-factor'),
  customUnit: document.getElementById('custom-unit'),
  customAmount: document.getElementById('custom-amount'),
  customAdd: document.getElementById('custom-add'),
  itemsTable: document.getElementById('items-table'),
  totalEmissions: document.getElementById('total-emissions'),
  scope1Total: document.getElementById('scope1-total'),
  scope2Total: document.getElementById('scope2-total'),
  scope3Total: document.getElementById('scope3-total'),
  loadedCount: document.getElementById('loaded-count'),
  scope1Count: document.getElementById('scope1-count'),
  scope2Count: document.getElementById('scope2-count'),
  scope3Count: document.getElementById('scope3-count'),
  resetItems: document.getElementById('reset-items'),
  downloadReport: document.getElementById('download-report'),
  exportJson: document.getElementById('export-json'),
};

const FILTERS = [
  { key: 'All', label: 'All sources', predicate: () => true },
  { key: 'Scope 1', label: 'Scope 1', predicate: entry => entry.scope === 'Scope 1' },
  { key: 'Scope 2', label: 'Scope 2', predicate: entry => entry.scope === 'Scope 2' },
  { key: 'Scope 3', label: 'Scope 3', predicate: entry => entry.scope === 'Scope 3' },
  { key: 'Fuels', label: 'Fuels', predicate: entry => /fuel/i.test([entry.level1, entry.level2, entry.level3, entry.label].join(' ')) },
  { key: 'Electricity', label: 'Electricity & heat', predicate: entry => /electricity|heat|cooling|steam|transmission|district/i.test([entry.level1, entry.level2, entry.level3, entry.label].join(' ')) },
  { key: 'Refrigerants', label: 'Refrigerants', predicate: entry => /refrigerant|hfc|pfc|sf6/i.test([entry.level1, entry.level2, entry.level3, entry.label].join(' ')) },
  { key: 'Transport', label: 'Transport', predicate: entry => /vehicle|travel|flight|freight|sea|rail|road|transport|commuting/i.test([entry.level1, entry.level2, entry.level3, entry.label].join(' ')) },
  { key: 'Materials', label: 'Materials & waste', predicate: entry => /material|waste|water|food/i.test([entry.level1, entry.level2, entry.level3, entry.label].join(' ')) },
];

function formatNumber(value, digits = 2) {
  return new Intl.NumberFormat('en-IN', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
}

function createTextNode(value) {
  return document.createTextNode(value == null ? '' : String(value));
}

function loadSavedItems() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed;
  } catch {
    // ignore
  }
  return [];
}

function saveItems() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.items));
}

function buildReportPayload() {
  const totals = {
    total: 0,
    scope1: 0,
    scope2: 0,
    scope3: 0,
  };
  const items = state.items.map(item => {
    const resultTonnes = (item.factor * item.amount) / 1000;
    totals.total += resultTonnes;
    if (item.scope === 'Scope 1') totals.scope1 += resultTonnes;
    if (item.scope === 'Scope 2') totals.scope2 += resultTonnes;
    if (item.scope === 'Scope 3') totals.scope3 += resultTonnes;
    return {
      description: item.description,
      scope: item.scope,
      amount: item.amount,
      unit: item.unit,
      factor: item.factor,
      result_t_co2e: Number(resultTonnes.toFixed(3)),
    };
  });
  return {
    generated_at: new Date().toISOString(),
    filter: state.filter,
    item_count: items.length,
    totals: {
      total_t_co2e: Number(totals.total.toFixed(3)),
      scope1_t_co2e: Number(totals.scope1.toFixed(3)),
      scope2_t_co2e: Number(totals.scope2.toFixed(3)),
      scope3_t_co2e: Number(totals.scope3.toFixed(3)),
    },
    items,
  };
}

function downloadReport() {
  if (!state.items.length) {
    alert('Add at least one item before downloading a report.');
    return;
  }

  const headers = ['Description', 'Scope', 'Amount', 'Unit', 'Factor (kg CO2e/unit)', 'Result (t CO2e)'];
  const rows = state.items.map(item => {
    const resultTonnes = (item.factor * item.amount) / 1000;
    return [
      item.description,
      item.scope,
      item.amount,
      item.unit,
      item.factor,
      Number(resultTonnes.toFixed(3)),
    ];
  });

  const csvRows = [headers, ...rows].map(row => row.map(value => `"${String(value).replace(/"/g, '""')}"`).join(','));
  csvRows.push('');
  csvRows.push(`"Total emissions","","","","",${formatNumber(buildReportPayload().totals.total_t_co2e, 3)}`);

  const blob = new Blob([csvRows.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  link.href = url;
  link.setAttribute('download', `ghg-emissions-report-${Date.now()}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function exportJSON() {
  if (!state.items.length) {
    alert('Add at least one item before exporting JSON.');
    return;
  }
  const payload = buildReportPayload();
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  link.href = url;
  link.setAttribute('download', `ghg-emissions-report-${Date.now()}.json`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function renderStats() {
  const allFactors = state.factors;
  const scope1 = allFactors.filter(f => f.scope === 'Scope 1').length;
  const scope2 = allFactors.filter(f => f.scope === 'Scope 2').length;
  const scope3 = allFactors.filter(f => f.scope === 'Scope 3').length;
  els.loadedCount.textContent = allFactors.length.toLocaleString();
  els.scope1Count.textContent = scope1.toLocaleString();
  els.scope2Count.textContent = scope2.toLocaleString();
  els.scope3Count.textContent = scope3.toLocaleString();
}

function getFilterCount(filter) {
  return state.factors.filter(filter.predicate).length;
}

function filterMatches(entry) {
  const current = FILTERS.find(filter => filter.key === state.filter);
  return current ? current.predicate(entry) : true;
}

function renderFilterBar() {
  if (!els.filterBar) return;
  els.filterBar.innerHTML = '';
  FILTERS.forEach(filter => {
    const count = getFilterCount(filter);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `calc-filter${filter.key === state.filter ? ' calc-filter--active' : ''}`;
    button.innerHTML = `${filter.label} <span class="filter-count">${count.toLocaleString()}</span>`;
    button.addEventListener('click', () => {
      state.filter = filter.key;
      renderFilterBar();
      handleSearchInput();
    });
    els.filterBar.appendChild(button);
  });
}

function showSelected(entry) {
  state.selected = entry;
  els.selectedCard.hidden = false;
  els.selectedTitle.textContent = entry.label || entry.column_text || 'Dataset entry';
  const details = [entry.scope, entry.level1, entry.level2, entry.level3].filter(Boolean).join(' · ');
  els.selectedDetails.textContent = details || 'Emission source details';
  els.selectedScope.textContent = entry.scope || 'Scope';
  els.selectedUnit.value = entry.uom || entry.uom_simple || 'unit';
  els.selectedFactor.value = entry.factor != null ? `${entry.factor} kg CO2e/${entry.uom || ''}` : 'No factor';
  els.amount.value = '';
}

function clearSelected() {
  state.selected = null;
  els.selectedCard.hidden = true;
  els.selectedTitle.textContent = '';
  els.selectedDetails.textContent = '';
  els.selectedScope.textContent = '';
  els.selectedUnit.value = '';
  els.selectedFactor.value = '';
  els.amount.value = '';
}

function updateResults() {
  const totals = {
    total: 0,
    scope1: 0,
    scope2: 0,
    scope3: 0,
  };

  els.itemsTable.innerHTML = '';

  state.items.forEach(item => {
    const row = document.createElement('tr');
    const resultValue = item.factor * item.amount;
    const resultTonnes = resultValue / 1000;
    totals.total += resultTonnes;
    if (item.scope === 'Scope 1') totals.scope1 += resultTonnes;
    if (item.scope === 'Scope 2') totals.scope2 += resultTonnes;
    if (item.scope === 'Scope 3') totals.scope3 += resultTonnes;

    const cells = [
      { content: item.description, strong: true },
      { content: item.scope },
      { content: `${formatNumber(item.amount, 2)} ${item.unit || ''}` },
      { content: `${formatNumber(item.factor, 3)} kg` },
      { content: `${formatNumber(resultTonnes, 3)} t` },
      { content: 'Remove', action: true, id: item.id },
    ];

    cells.forEach(cell => {
      const td = document.createElement('td');
      if (cell.action) {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = cell.content;
        button.dataset.removeId = cell.id;
        button.addEventListener('click', () => removeItem(cell.id));
        td.appendChild(button);
      } else {
        if (cell.strong) {
          const strong = document.createElement('strong');
          strong.textContent = cell.content;
          td.appendChild(strong);
        } else {
          td.textContent = cell.content;
        }
      }
      row.appendChild(td);
    });

    els.itemsTable.appendChild(row);
  });

  els.totalEmissions.textContent = formatNumber(totals.total, 3);
  els.scope1Total.textContent = formatNumber(totals.scope1, 3);
  els.scope2Total.textContent = formatNumber(totals.scope2, 3);
  els.scope3Total.textContent = formatNumber(totals.scope3, 3);
  saveItems();
}

function removeItem(id) {
  state.items = state.items.filter(item => item.id !== id);
  updateResults();
}

function addEntry(entry, amount) {
  if (!entry || !amount || amount <= 0) return;
  const description = entry.label || entry.column_text || 'Emission item';
  state.items.push({
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    description,
    scope: entry.scope || 'Scope 1',
    amount,
    unit: entry.uom || entry.uom_simple || 'unit',
    factor: entry.factor || 0,
  });
  updateResults();
}

function addCustomItem() {
  const description = els.customDescription.value.trim();
  const factor = Number(els.customFactor.value);
  const amount = Number(els.customAmount.value);
  const unit = els.customUnit.value.trim() || 'unit';

  if (!description) {
    alert('Enter a description for the custom emission source.');
    return;
  }
  if (!factor || factor <= 0) {
    alert('Enter a valid custom emission factor in kg CO2e per unit.');
    return;
  }
  if (!amount || amount <= 0) {
    alert('Enter a valid quantity for the custom emission source.');
    return;
  }

  state.items.push({
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    description,
    scope: 'Custom',
    amount,
    unit,
    factor,
  });
  els.customDescription.value = '';
  els.customFactor.value = '';
  els.customUnit.value = '';
  els.customAmount.value = '';
  updateResults();
}

function renderSearchResults(matches) {
  els.results.innerHTML = '';
  if (!matches.length) {
    const noResult = document.createElement('div');
    noResult.className = 'search-no-results';
    noResult.textContent = 'No matching emission source found. Try a broader term.';
    els.results.appendChild(noResult);
    return;
  }

  matches.forEach(entry => {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.entryId = entry.id;
    button.innerHTML = `
      <strong>${entry.label || entry.column_text}</strong>
      <span class="result-meta">${[entry.scope, entry.level1, entry.level2].filter(Boolean).join(' · ')} • ${entry.uom || entry.uom_simple || ''}</span>
    `;
    button.addEventListener('click', () => {
      showSelected(entry);
      els.results.innerHTML = '';
      els.search.value = entry.label || entry.column_text || '';
    });
    els.results.appendChild(button);
  });
}

function handleSearchInput() {
  const query = els.search.value.trim().toLowerCase();
  let matches = state.factors.filter(filterMatches);

  if (query) {
    matches = matches.filter(entry => {
      return [entry.label, entry.scope, entry.level1, entry.level2, entry.level3, entry.column_text, entry.uom]
        .filter(Boolean)
        .some(value => String(value).toLowerCase().includes(query));
    });
  }

  renderSearchResults(matches.slice(0, 35));
}

function resetItems() {
  if (!confirm('Clear all emission items from the calculator?')) return;
  state.items = [];
  saveItems();
  updateResults();
}

function initNavigation() {
  const burger = document.getElementById('nav-burger');
  const mobileNav = document.getElementById('nav-mobile');
  if (!burger || !mobileNav) return;
  burger.addEventListener('click', () => {
    const open = burger.classList.toggle('open');
    mobileNav.classList.toggle('open', open);
    document.body.style.overflow = open ? 'hidden' : '';
    burger.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  mobileNav.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
    burger.classList.remove('open');
    mobileNav.classList.remove('open');
    document.body.style.overflow = '';
    burger.setAttribute('aria-expanded', 'false');
  }));
}

async function initCalculator() {
  if (!els.search || !els.itemsTable) return;
  if (!document.querySelector('script[src="assets/js/app.js"]')) {
    initNavigation();
  }
  state.items = loadSavedItems();
  updateResults();

  try {
    const response = await fetch('assets/data/ghg-factors.json');
    state.factors = await response.json();
    renderStats();
    renderFilterBar();
    handleSearchInput();
  } catch (error) {
    console.error('Failed to load factor dataset', error);
    if (els.loadedCount) els.loadedCount.textContent = '0';
  }

  els.search.addEventListener('input', handleSearchInput);
  els.addItem.addEventListener('click', () => {
    const amount = Number(els.amount.value);
    if (!state.selected) {
      alert('Select an emission source from the search results first.');
      return;
    }
    if (!amount || amount <= 0) {
      alert('Enter a valid amount before adding the item.');
      return;
    }
    addEntry(state.selected, amount);
  });

  els.customAdd.addEventListener('click', addCustomItem);
  els.resetItems.addEventListener('click', resetItems);
  if (els.downloadReport) els.downloadReport.addEventListener('click', downloadReport);
  if (els.exportJson) els.exportJson.addEventListener('click', exportJSON);
}

initCalculator();
