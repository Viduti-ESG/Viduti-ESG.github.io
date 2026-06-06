/**
 * value-chain.js — Company dashboard for BRSR Value-Chain Supplier Assessment
 * Handles: registration, invite creation, dashboard rendering.
 */

const API_BASE        = "https://7334807f62be7d.lhr.life";
const TOKEN_STORE_KEY = "gc_vc_company_token";

const SECTORS = [
  "Banking & Financial Services","IT & Software","Manufacturing — Steel/Metals",
  "Manufacturing — Chemicals","Manufacturing — Pharmaceuticals","Manufacturing — FMCG",
  "Manufacturing — Textiles","Manufacturing — Cement/Construction Materials",
  "Manufacturing — Auto & Auto Components","Manufacturing — Capital Goods",
  "Manufacturing — Others","Oil & Gas / Energy","Power & Utilities",
  "Infrastructure & Construction","Real Estate","Telecom",
  "Retail & Consumer","Healthcare","Agriculture & Food Processing",
  "Mining & Minerals","Media & Entertainment","Logistics & Transport","Other",
];

// ── State ─────────────────────────────────────────────────────────────────────
let companyToken  = null;
let dashboardData = null;
let lastInviteUrl = null;

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  // Try URL param first, then localStorage
  const urlToken = new URLSearchParams(window.location.search).get("company");
  companyToken   = urlToken || localStorage.getItem(TOKEN_STORE_KEY);

  if (companyToken) {
    showDashboard();
  } else {
    showRegister();
  }
});

// ── Registration ──────────────────────────────────────────────────────────────

function showRegister() {
  const app = document.getElementById("vc-app");

  // Build sector options
  const sectorOpts = SECTORS.map(s => `<option value="${s}">${s}</option>`).join("");

  app.innerHTML = `
    <div class="vc-card">
      <div class="vc-card__title">Set up your Value-Chain Dashboard</div>
      <div class="vc-card__sub">Register once — you'll get a unique link to invite suppliers and track their ESG responses.</div>

      <div id="reg-error"></div>

      <div class="vc-form-grid">
        <div class="vc-field full">
          <label>Company Name <span style="color:var(--cyan)">*</span></label>
          <input type="text" id="reg-name" placeholder="Tata Steel Ltd" required />
        </div>
        <div class="vc-field">
          <label>CIN <span style="color:var(--text-40);font-size:.75rem">optional</span></label>
          <input type="text" id="reg-cin" placeholder="L27100MH1907PLC000260" />
        </div>
        <div class="vc-field">
          <label>Sector <span style="color:var(--cyan)">*</span></label>
          <select id="reg-sector">
            <option value="">— Select —</option>
            ${sectorOpts}
          </select>
        </div>
        <div class="vc-field">
          <label>Your Name <span style="color:var(--cyan)">*</span></label>
          <input type="text" id="reg-contact-name" placeholder="Sustainability Manager" />
        </div>
        <div class="vc-field">
          <label>Your Email <span style="color:var(--cyan)">*</span></label>
          <input type="email" id="reg-contact-email" placeholder="esg@company.com" />
        </div>
      </div>

      <div style="margin-top:24px;display:flex;gap:12px;align-items:center">
        <button class="vc-btn vc-btn--primary" id="reg-submit-btn" onclick="submitRegistration()">
          Create Dashboard →
        </button>
        <span id="reg-loading" style="display:none;color:var(--text-40);font-size:.85rem">
          <span class="vc-spinner" style="width:18px;height:18px;display:inline-block;vertical-align:middle;margin-right:6px"></span>Setting up…
        </span>
      </div>

      <div class="vc-hero__reg-note" style="margin-top:16px">
        Already registered? <a href="value-chain.html?company=YOUR_TOKEN" style="color:var(--cyan)">
        Enter your dashboard link</a> or bookmark this page after registering.
      </div>
    </div>
  `;
}

async function submitRegistration() {
  const name    = document.getElementById("reg-name").value.trim();
  const cin     = document.getElementById("reg-cin").value.trim();
  const sector  = document.getElementById("reg-sector").value;
  const cName   = document.getElementById("reg-contact-name").value.trim();
  const cEmail  = document.getElementById("reg-contact-email").value.trim();
  const errEl   = document.getElementById("reg-error");

  errEl.innerHTML = "";

  if (!name || !sector || !cName || !cEmail) {
    errEl.innerHTML = `<div class="vc-notice vc-notice--error">Please fill in all required fields.</div>`;
    return;
  }

  const btn = document.getElementById("reg-submit-btn");
  const loading = document.getElementById("reg-loading");
  btn.disabled = true;
  loading.style.display = "inline-flex";

  try {
    const res = await fetch(`${API_BASE}/api/value-chain/register`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        company_name:  name,
        company_cin:   cin,
        sector,
        contact_name:  cName,
        contact_email: cEmail,
      }),
    });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();

    companyToken = data.company_token;
    localStorage.setItem(TOKEN_STORE_KEY, companyToken);
    window.history.replaceState({}, "", `?company=${companyToken}`);
    showDashboard();
  } catch (err) {
    errEl.innerHTML = `<div class="vc-notice vc-notice--error">Failed to register: ${err.message}. Check backend is running.</div>`;
    btn.disabled = false;
    loading.style.display = "none";
  }
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

async function showDashboard() {
  const app = document.getElementById("vc-app");

  app.innerHTML = `
    <div class="vc-loading" id="dashboard-loading">
      <div class="vc-spinner"></div>
      Loading your dashboard…
    </div>
  `;

  try {
    const res = await fetch(`${API_BASE}/api/value-chain/responses/${companyToken}`);
    if (res.status === 404) {
      // Token stale — clear and show register
      localStorage.removeItem(TOKEN_STORE_KEY);
      companyToken = null;
      showRegister();
      return;
    }
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    dashboardData = await res.json();
    renderDashboard(dashboardData);
  } catch (err) {
    app.innerHTML = `
      <div class="vc-notice vc-notice--error" style="max-width:640px;margin:0 auto">
        Could not load dashboard: ${err.message}.<br>
        <small style="opacity:.6">Ensure the backend is running at ${API_BASE}</small>
      </div>
      <div style="text-align:center;margin-top:24px">
        <button class="vc-btn vc-btn--outline vc-btn--sm" onclick="showDashboard()">Retry</button>
        <button class="vc-btn vc-btn--outline vc-btn--sm" style="margin-left:8px" onclick="clearAndRegister()">Use different token</button>
      </div>
    `;
  }
}

function clearAndRegister() {
  localStorage.removeItem(TOKEN_STORE_KEY);
  companyToken = null;
  window.history.replaceState({}, "", "value-chain.html");
  showRegister();
}

function renderDashboard(d) {
  const app = document.getElementById("vc-app");

  const green = d.tier_counts?.Green || 0;
  const amber = d.tier_counts?.Amber || 0;
  const red   = d.tier_counts?.Red   || 0;

  const suppRows = d.suppliers.length === 0
    ? `<tr><td colspan="6"><div class="vc-empty"><div class="vc-empty__icon">📋</div><div class="vc-empty__text">No suppliers invited yet. Use the form above to send your first invite.</div></div></td></tr>`
    : d.suppliers.map(s => supplierRow(s)).join("");

  app.innerHTML = `
    <div class="vc-dashboard">

      <div class="vc-dashboard__header">
        <div>
          <div class="vc-dashboard__name">${escHtml(d.company_name)}</div>
          <div class="vc-dashboard__meta">${escHtml(d.company_cin || "")} ${d.sector ? "· " + escHtml(d.sector) : ""}</div>
        </div>
        <div class="vc-dashboard__token-wrap">
          <span class="vc-dashboard__token-label">Dashboard Token</span>
          <span class="vc-dashboard__token-val" id="token-display">${escHtml(companyToken)}</span>
          <button class="vc-link-box__copy" onclick="copyToken()">Copy</button>
        </div>
      </div>

      <div class="vc-token-save">
        <strong>Bookmark this page</strong> or save your dashboard link:
        <strong>value-chain.html?company=${escHtml(companyToken)}</strong>
        — you'll need it to return to this dashboard.
      </div>

      <!-- Stats -->
      <div class="vc-stats">
        <div class="vc-stat vc-stat--cyan">
          <div class="vc-stat__val">${d.total_invited}</div>
          <div class="vc-stat__label">Invited</div>
        </div>
        <div class="vc-stat">
          <div class="vc-stat__val">${d.total_submitted}</div>
          <div class="vc-stat__label">Responded</div>
        </div>
        <div class="vc-stat">
          <div class="vc-stat__val">${d.avg_score !== null ? d.avg_score : "—"}</div>
          <div class="vc-stat__label">Avg ESG Score</div>
        </div>
        <div class="vc-stat">
          <div class="vc-stat__val" style="font-size:1rem;display:flex;gap:8px;align-items:center">
            <span style="color:var(--emerald)">${green}G</span>
            <span style="color:var(--amber)">${amber}A</span>
            <span style="color:#f87171">${red}R</span>
          </div>
          <div class="vc-stat__label">Tier Breakdown</div>
        </div>
      </div>

      <!-- Invite panel -->
      <div class="vc-invite-panel">
        <div class="vc-invite-panel__title">Invite a Supplier</div>
        <div id="invite-error"></div>
        <div class="vc-invite-row">
          <div class="vc-field">
            <label>Supplier Company Name</label>
            <input type="text" id="inv-name" placeholder="ABC Suppliers Pvt Ltd" />
          </div>
          <div class="vc-field">
            <label>Supplier Email <span style="color:var(--text-40);font-size:.75rem">optional</span></label>
            <input type="email" id="inv-email" placeholder="esg@supplier.com" />
          </div>
          <button class="vc-btn vc-btn--primary" id="inv-btn" onclick="inviteSupplier()" style="margin-bottom:0">
            Send Invite →
          </button>
        </div>

        <div id="invite-result" style="display:none">
          <div class="vc-notice vc-notice--success" style="margin-top:14px">
            ✓ Invite created for <strong id="inv-done-name"></strong>.
            Share this link with them:
          </div>
          <div class="vc-link-box">
            <span class="vc-link-box__url" id="inv-link-text"></span>
            <button class="vc-link-box__copy" id="inv-copy-btn" onclick="copyInviteLink()">Copy link</button>
          </div>
        </div>
      </div>

      <!-- Supplier table -->
      <div class="vc-table-wrap">
        <div class="vc-table-title">Suppliers (${d.total_invited})</div>
        <table class="vc-table">
          <thead>
            <tr>
              <th>Supplier</th>
              <th>Status</th>
              <th>Score</th>
              <th>Tier</th>
              <th>Data Coverage</th>
              <th>Link</th>
            </tr>
          </thead>
          <tbody id="supplier-tbody">
            ${suppRows}
          </tbody>
        </table>
      </div>

    </div>
  `;
}

function supplierRow(s) {
  const statusBadge = s.status === "submitted"
    ? `<span class="tier-badge tier-badge--Green">Submitted</span>`
    : `<span class="tier-badge tier-badge--pending">Pending</span>`;

  const scorePill = s.score != null
    ? `<span class="score-pill score-pill--${s.risk_tier}">${s.score}</span>`
    : `<span style="color:var(--text-40)">—</span>`;

  const tierBadge = s.risk_tier
    ? `<span class="tier-badge tier-badge--${s.risk_tier}">${s.risk_tier}</span>`
    : `<span style="color:var(--text-40)">—</span>`;

  const coverage = s.confidence_summary
    ? `<span style="color:var(--text-70);font-size:.82rem">${s.confidence_summary.reported}/10 fields</span>`
    : `<span style="color:var(--text-40)">—</span>`;

  const formLink = `<a href="${escHtml(s.form_url)}" target="_blank" style="color:var(--cyan);font-size:.8rem">Form ↗</a>`;

  return `
    <tr>
      <td>
        <div class="name-cell">${escHtml(s.supplier_name)}</div>
        ${s.supplier_email ? `<div style="font-size:.75rem;color:var(--text-40)">${escHtml(s.supplier_email)}</div>` : ""}
      </td>
      <td>${statusBadge}</td>
      <td>${scorePill}</td>
      <td>${tierBadge}</td>
      <td>${coverage}</td>
      <td>${formLink}</td>
    </tr>
  `;
}

// ── Invite supplier ───────────────────────────────────────────────────────────

async function inviteSupplier() {
  const name  = document.getElementById("inv-name").value.trim();
  const email = document.getElementById("inv-email").value.trim();
  const errEl = document.getElementById("invite-error");
  errEl.innerHTML = "";

  if (!name) {
    errEl.innerHTML = `<div class="vc-notice vc-notice--error">Supplier name is required.</div>`;
    return;
  }

  const btn = document.getElementById("inv-btn");
  btn.disabled = true;
  btn.textContent = "Creating…";

  try {
    const res = await fetch(`${API_BASE}/api/value-chain/invite`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        company_token: companyToken,
        supplier_name:  name,
        supplier_email: email,
      }),
    });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();

    lastInviteUrl = data.form_url;
    document.getElementById("inv-done-name").textContent = data.supplier_name;
    document.getElementById("inv-link-text").textContent  = data.form_url;
    document.getElementById("invite-result").style.display = "block";

    // Clear fields
    document.getElementById("inv-name").value  = "";
    document.getElementById("inv-email").value = "";

    // Refresh dashboard data
    await refreshSupplierList();
  } catch (err) {
    errEl.innerHTML = `<div class="vc-notice vc-notice--error">Invite failed: ${err.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Send Invite →";
  }
}

async function refreshSupplierList() {
  try {
    const res = await fetch(`${API_BASE}/api/value-chain/responses/${companyToken}`);
    if (!res.ok) return;
    dashboardData = await res.json();

    // Update stats
    const green = dashboardData.tier_counts?.Green || 0;
    const amber = dashboardData.tier_counts?.Amber || 0;
    const red   = dashboardData.tier_counts?.Red   || 0;

    const statsVals = document.querySelectorAll(".vc-stat__val");
    if (statsVals.length >= 4) {
      statsVals[0].textContent = dashboardData.total_invited;
      statsVals[1].textContent = dashboardData.total_submitted;
      statsVals[2].textContent = dashboardData.avg_score !== null ? dashboardData.avg_score : "—";
    }

    const tbody = document.getElementById("supplier-tbody");
    if (tbody) {
      const rows = dashboardData.suppliers.length === 0
        ? `<tr><td colspan="6"><div class="vc-empty"><div class="vc-empty__icon">📋</div><div class="vc-empty__text">No suppliers invited yet.</div></div></td></tr>`
        : dashboardData.suppliers.map(s => supplierRow(s)).join("");
      tbody.innerHTML = rows;
    }
  } catch (_) { /* silent */ }
}

// ── Clipboard helpers ─────────────────────────────────────────────────────────

function copyToken() {
  navigator.clipboard.writeText(companyToken).then(() => {
    const btn = document.querySelector(".vc-dashboard__token-wrap .vc-link-box__copy");
    if (btn) { btn.textContent = "Copied!"; btn.classList.add("copied"); setTimeout(() => { btn.textContent = "Copy"; btn.classList.remove("copied"); }, 2000); }
  });
}

function copyInviteLink() {
  if (!lastInviteUrl) return;
  navigator.clipboard.writeText(lastInviteUrl).then(() => {
    const btn = document.getElementById("inv-copy-btn");
    if (btn) { btn.textContent = "Copied!"; btn.classList.add("copied"); setTimeout(() => { btn.textContent = "Copy link"; btn.classList.remove("copied"); }, 2000); }
  });
}

// ── Utility ───────────────────────────────────────────────────────────────────

function escHtml(str) {
  return String(str || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
