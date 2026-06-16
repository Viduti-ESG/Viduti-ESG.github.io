// Green Curve — BRSR Value-Chain Supplier Tab (F-A)
// Depends on: _SUPPLIER_RESPONSES, esc() from esg-intelligence.js

let _supplierFiltered = [];

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
    const dateStr  = r.submitted_at ? r.submitted_at.slice(0, 10) : '—';
    const msmeTag  = r.is_msme ? `<span class="supp-msme-tag">MSME</span>` : '';
    const brsrIcon = r.has_brsr_disclosure ? '✅' : `<span style="color:#64748b">—</span>`;
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
