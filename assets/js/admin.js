/**
 * Green Curve Admin Panel JS
 * All API calls include X-Admin-Key header from sessionStorage.
 */

let ADMIN_KEY    = '';
let currentPage  = 1;
let totalPages   = 1;
let editingName  = null;   // null = add mode, string = edit mode
let searchTimer  = null;

// ── Auth ──────────────────────────────────────────────────────────────────────
function doAdminLogin() {
  const key = document.getElementById('admin-key-input').value.trim();
  if (!key) return;
  ADMIN_KEY = key;
  // Verify by hitting a protected endpoint
  adminFetch('/api/admin/companies?limit=1')
    .then(() => {
      document.getElementById('admin-auth').style.display = 'none';
      document.getElementById('admin-app').style.display  = 'block';
      loadStats();
      loadSectors();
      loadPage(1);
    })
    .catch(() => {
      ADMIN_KEY = '';
      const err = document.getElementById('admin-auth-err');
      err.textContent = 'Invalid admin key. Try again.';
      err.style.display = 'block';
    });
}

document.getElementById('admin-key-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') doAdminLogin();
});

// ── Core fetch ────────────────────────────────────────────────────────────────
async function adminFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', 'X-Admin-Key': ADMIN_KEY, ...(opts.headers || {}) };
  const res = await fetch(path, { ...opts, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

// ── Stats ─────────────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const d = await adminFetch('/api/esg/stats');
    document.getElementById('stat-total').textContent  = d.total;
    document.getElementById('stat-high').textContent   = d.high;
    document.getElementById('stat-medium').textContent = d.medium;
    document.getElementById('stat-low').textContent    = d.low;
    document.getElementById('topbar-count').textContent = d.total + ' companies';
  } catch {}
}

// ── Sectors dropdown ──────────────────────────────────────────────────────────
async function loadSectors() {
  try {
    const d = await adminFetch('/api/esg/sectors');
    const sel = document.getElementById('filter-sector');
    d.sectors.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s;
      opt.textContent = s.length > 40 ? s.slice(0, 40) + '…' : s;
      sel.appendChild(opt);
    });
  } catch {}
}

// ── Company list ──────────────────────────────────────────────────────────────
function onSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadPage(1), 350);
}

async function loadPage(page) {
  if (page < 1 || page > totalPages) return;
  currentPage = page;

  const search   = document.getElementById('search-input').value.trim();
  const sector   = document.getElementById('filter-sector').value;
  const tier     = document.getElementById('filter-tier').value;

  const params = new URLSearchParams({ page, limit: 50 });
  if (search) params.set('search', search);
  if (sector) params.set('sector', sector);
  if (tier)   params.set('risk_tier', tier);

  try {
    const d = await adminFetch('/api/admin/companies?' + params);
    totalPages = d.pages || 1;
    renderTable(d.companies);
    document.getElementById('page-info').textContent =
      `Page ${page} of ${totalPages} · ${d.total} companies`;
    document.getElementById('btn-prev').disabled = page <= 1;
    document.getElementById('btn-next').disabled = page >= totalPages;
  } catch (e) {
    toast('Load failed: ' + e.message, 'err');
  }
}

function renderTable(companies) {
  const tbody = document.getElementById('company-tbody');
  if (!companies.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:40px;color:var(--text-20)">No companies found</td></tr>';
    return;
  }
  tbody.innerHTML = companies.map(c => `
    <tr>
      <td>
        <div class="co-name">${esc(c.company_name)}</div>
      </td>
      <td><span class="co-cin">${esc(c.cin || '—')}</span></td>
      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc((c.sector||'').slice(0,40))}</td>
      <td>${Number(c.esg_risk_score || 0).toFixed(1)}</td>
      <td><span class="risk-pill risk-pill--${esc(c.risk_tier)}">${esc(c.risk_tier)}</span></td>
      <td style="font-size:.75rem;color:var(--text-20)">${(c.updated_at||'').slice(0,10)}</td>
      <td>
        <button class="admin-btn admin-btn--ghost" style="padding:4px 10px;font-size:.78rem"
          onclick="openEditModal(${JSON.stringify(c.company_name)})">Edit</button>
      </td>
    </tr>
  `).join('');
}

// ── Add / Edit modal ──────────────────────────────────────────────────────────
function openAddModal() {
  editingName = null;
  document.getElementById('modal-title').textContent = 'Add Company';
  document.getElementById('btn-delete').style.display = 'none';
  clearForm();
  document.getElementById('f-company_name').disabled = false;
  document.getElementById('edit-modal').classList.add('open');
}

async function openEditModal(name) {
  editingName = name;
  document.getElementById('modal-title').textContent = 'Edit: ' + name;
  document.getElementById('btn-delete').style.display = '';
  clearForm();
  try {
    const c = await adminFetch('/api/esg/company/' + encodeURIComponent(name));
    document.getElementById('f-company_name').value     = c.company_name || '';
    document.getElementById('f-company_name').disabled  = true;
    document.getElementById('f-cin').value              = c.cin || '';
    document.getElementById('f-nse_symbol').value       = c.nse_symbol || '';
    document.getElementById('f-sector').value           = c.sector || '';
    document.getElementById('f-revenue_crore').value    = c.revenue_crore || 0;
    document.getElementById('f-financial_year').value   = c.financial_year || '';
    document.getElementById('f-esg_risk_score').value   = c.esg_risk_score || 0;
    document.getElementById('f-risk_tier').value        = c.risk_tier || 'Medium';
    document.getElementById('f-risk_breakdown').value   = JSON.stringify(c.risk_breakdown || {}, null, 2);
    document.getElementById('f-top_risk_factors').value = JSON.stringify(c.top_risk_factors || []);
    document.getElementById('f-governance').value       = JSON.stringify(c.governance || {});
    document.getElementById('f-ai_summary').value       = c.ai_summary || '';
    document.getElementById('edit-modal').classList.add('open');
  } catch (e) {
    toast('Load failed: ' + e.message, 'err');
  }
}

function closeModal() {
  document.getElementById('edit-modal').classList.remove('open');
}

function clearForm() {
  ['f-company_name','f-cin','f-nse_symbol','f-sector','f-financial_year','f-ai_summary'].forEach(id => {
    document.getElementById(id).value = '';
  });
  document.getElementById('f-revenue_crore').value  = '0';
  document.getElementById('f-esg_risk_score').value = '5';
  document.getElementById('f-risk_tier').value      = 'Medium';
  document.getElementById('f-risk_breakdown').value = '{}';
  document.getElementById('f-top_risk_factors').value = '[]';
  document.getElementById('f-governance').value     = '{}';
}

function readForm() {
  const parseJSON = (id, fallback) => {
    try { return JSON.parse(document.getElementById(id).value || JSON.stringify(fallback)); }
    catch { return fallback; }
  };
  return {
    company_name:       document.getElementById('f-company_name').value.trim(),
    cin:                document.getElementById('f-cin').value.trim(),
    nse_symbol:         document.getElementById('f-nse_symbol').value.trim(),
    sector:             document.getElementById('f-sector').value.trim(),
    revenue_crore:      parseFloat(document.getElementById('f-revenue_crore').value) || 0,
    financial_year:     document.getElementById('f-financial_year').value.trim(),
    esg_risk_score:     parseFloat(document.getElementById('f-esg_risk_score').value) || 0,
    risk_tier:          document.getElementById('f-risk_tier').value,
    risk_breakdown:     parseJSON('f-risk_breakdown', {}),
    top_risk_factors:   parseJSON('f-top_risk_factors', []),
    governance:         parseJSON('f-governance', {}),
    ai_summary:         document.getElementById('f-ai_summary').value.trim(),
  };
}

async function saveCompany() {
  const body = readForm();
  if (!body.company_name) { toast('Company name is required', 'err'); return; }
  try {
    if (editingName) {
      await adminFetch('/api/admin/companies/' + encodeURIComponent(editingName),
        { method: 'PUT', body: JSON.stringify(body) });
      toast('Company updated', 'ok');
    } else {
      await adminFetch('/api/admin/companies', { method: 'POST', body: JSON.stringify(body) });
      toast('Company added', 'ok');
    }
    closeModal();
    loadPage(currentPage);
    loadStats();
  } catch (e) {
    toast('Save failed: ' + e.message, 'err');
  }
}

async function deleteCompany() {
  if (!editingName || !confirm(`Delete "${editingName}"? This cannot be undone.`)) return;
  try {
    await adminFetch('/api/admin/companies/' + encodeURIComponent(editingName), { method: 'DELETE' });
    toast('Company deleted', 'ok');
    closeModal();
    loadPage(1);
    loadStats();
  } catch (e) {
    toast('Delete failed: ' + e.message, 'err');
  }
}

// ── Re-import ─────────────────────────────────────────────────────────────────
async function triggerReimport() {
  if (!confirm('Re-import all companies from esg_quotient.json on the server?\nThis will update all existing records.')) return;
  try {
    toast('Importing…', 'ok');
    const d = await adminFetch('/api/admin/reimport', { method: 'POST' });
    toast(`Done — ${d.inserted} inserted, ${d.updated} updated`, 'ok');
    loadPage(1);
    loadStats();
  } catch (e) {
    toast('Import failed: ' + e.message, 'err');
  }
}

// ── Toast ─────────────────────────────────────────────────────────────────────
let _toastTimer = null;
function toast(msg, type = 'ok') {
  const el = document.getElementById('admin-toast');
  el.textContent = msg;
  el.className = `admin-toast admin-toast--${type} show`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 3000);
}

// ── Utils ─────────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
