/**
 * BRSR Generator Wizard
 * Fetches form schema from backend, renders multi-step wizard,
 * submits to /api/generate-report, and displays the result.
 */

const API_BASE = "https://6bb7794aaffbe1.lhr.life";
// const API_BASE = "https://6bb7794aaffbe1.lhr.life";  // uncomment for local dev

let formSchema   = null;
let currentStep  = 0;
let formData     = {};
let generatedReport = null;

// ── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("startWizardBtn").addEventListener("click", openWizard);
  document.getElementById("wizardClose").addEventListener("click", closeWizard);
  document.getElementById("btnNext").addEventListener("click", nextStep);
  document.getElementById("btnBack").addEventListener("click", prevStep);
  document.getElementById("btnGenerate").addEventListener("click", generateReport);
  document.getElementById("reportClose").addEventListener("click", closeReport);
  document.getElementById("btnDownloadPdf").addEventListener("click", downloadPdf);
  document.getElementById("btnDownloadJson").addEventListener("click", downloadJson);
  document.getElementById("btnDownloadXbrl").addEventListener("click", downloadXbrl);

  // Close overlays on backdrop click
  document.getElementById("wizardOverlay").addEventListener("click", e => {
    if (e.target === e.currentTarget) closeWizard();
  });
  document.getElementById("reportOverlay").addEventListener("click", e => {
    if (e.target === e.currentTarget) closeReport();
  });
});

async function openWizard() {
  show("wizardOverlay");

  if (!formSchema) {
    try {
      const r = await fetch(`${API_BASE}/api/form-schema`, { signal: AbortSignal.timeout(8000) });
      if (!r.ok) throw new Error("Schema fetch failed");
      formSchema = await r.json();
    } catch (e) {
      alert("Could not connect to the BRSR Generator backend. Please try again in a moment — the server may be waking up (takes ~30 seconds).\n\n" +
            "If the page still shows the offline message after a refresh, please contact support.");
      hide("wizardOverlay");
      return;
    }
  }

  currentStep = 0;
  formData = {};
  renderNav();
  renderStep(0);
}

function closeWizard() {
  hide("wizardOverlay");
}

// ── Navigation ────────────────────────────────────────────────────────────────

function renderNav() {
  const nav = document.getElementById("wizardNav");
  nav.innerHTML = "";
  formSchema.sections.forEach((section, i) => {
    const btn = document.createElement("button");
    btn.className = "wizard-nav__item" + (i === currentStep ? " active" : "");
    btn.dataset.step = i;
    btn.innerHTML = `
      <div class="wizard-nav__dot">${i + 1}</div>
      <span class="wizard-nav__label">${section.title}</span>
    `;
    btn.addEventListener("click", () => {
      // Only allow navigating to completed steps
      if (i < currentStep) { currentStep = i; renderNav(); renderStep(i); }
    });
    nav.appendChild(btn);
  });
}

function updateNav() {
  document.querySelectorAll(".wizard-nav__item").forEach((btn, i) => {
    btn.className = "wizard-nav__item" +
      (i === currentStep ? " active" : i < currentStep ? " completed" : "");
    const dot = btn.querySelector(".wizard-nav__dot");
    dot.textContent = i < currentStep ? "✓" : (i + 1);
  });
}

// ── Step rendering ────────────────────────────────────────────────────────────

function renderStep(stepIdx) {
  const section  = formSchema.sections[stepIdx];
  const total    = formSchema.sections.length;
  const isLast   = stepIdx === total - 1;

  document.getElementById("stepCounter").textContent = `${stepIdx + 1} / ${total}`;
  document.getElementById("btnBack").hidden   = stepIdx === 0;
  document.getElementById("btnNext").hidden   = isLast;
  document.getElementById("btnGenerate").hidden = !isLast;

  const content = document.getElementById("wizardContent");
  content.innerHTML = `
    <div class="step-header">
      <div class="step-header__badge">${section.subtitle || "Step " + (stepIdx + 1)}</div>
      <h2 class="step-header__title">${section.title}</h2>
    </div>
    <div class="form-grid" id="formGrid">
      ${section.fields.map(field => renderField(field)).join("")}
    </div>
  `;

  // Restore saved values
  section.fields.forEach(field => restoreValue(field));

  // Scroll to top
  content.scrollTop = 0;
}

function renderField(field) {
  const required = field.required ? '<span class="required-star">*</span>' : "";
  const label    = `<label class="field-label" for="${field.id}">${field.label} ${required}</label>`;
  const hint     = field.placeholder ? `<span class="field-hint">${field.placeholder}</span>` : "";

  let input = "";
  switch (field.type) {
    case "text":
    case "url":
    case "email":
    case "number":
      input = `<input class="field-input" type="${field.type}" id="${field.id}"
        name="${field.id}" placeholder="${field.placeholder || ""}"
        ${field.required ? "required" : ""}
        ${field.default !== undefined ? `value="${field.default}"` : ""}
      >`;
      break;

    case "textarea":
      input = `<textarea class="field-textarea" id="${field.id}" name="${field.id}"
        placeholder="${field.placeholder || ""}"
        ${field.required ? "required" : ""}></textarea>`;
      break;

    case "select":
      const opts = (field.options || []).map(o =>
        `<option value="${o}">${o}</option>`
      ).join("");
      input = `<select class="field-select" id="${field.id}" name="${field.id}"
        ${field.required ? "required" : ""}>
        <option value="">— Select —</option>
        ${opts}
      </select>`;
      break;

    case "radio":
      const radios = (field.options || []).map(o => `
        <label class="radio-option">
          <input type="radio" name="${field.id}" value="${o}">
          ${o}
        </label>`).join("");
      input = `<div class="radio-group" id="${field.id}">${radios}</div>`;
      break;

    case "multiselect":
      const checks = (field.options || []).map(o => `
        <label class="check-option">
          <input type="checkbox" name="${field.id}" value="${o}">
          ${o}
        </label>`).join("");
      input = `<div class="check-group" id="${field.id}">${checks}</div>`;
      break;

    default:
      input = `<input class="field-input" type="text" id="${field.id}" name="${field.id}">`;
  }

  const isWide = ["textarea", "radio", "multiselect"].includes(field.type) || field.id.includes("description") || field.id.includes("initiatives");
  const colSpan = isWide ? ' style="grid-column: 1/-1"' : "";
  const isGrid2 = document.querySelector(".form-grid--2");

  return `
    <div class="field-group" ${colSpan}>
      ${label}
      ${input}
      ${hint}
    </div>`;
}

function restoreValue(field) {
  const saved = formData[field.id];
  if (saved === undefined || saved === null) return;

  if (field.type === "radio") {
    document.querySelectorAll(`input[name="${field.id}"]`).forEach(radio => {
      radio.checked = radio.value === saved;
    });
  } else if (field.type === "multiselect") {
    const vals = Array.isArray(saved) ? saved : [saved];
    document.querySelectorAll(`input[name="${field.id}"]`).forEach(cb => {
      cb.checked = vals.includes(cb.value);
    });
  } else {
    const el = document.getElementById(field.id);
    if (el) el.value = saved;
  }
}

// ── Data collection ───────────────────────────────────────────────────────────

function collectStepData(stepIdx) {
  const section = formSchema.sections[stepIdx];
  section.fields.forEach(field => {
    if (field.type === "radio") {
      const checked = document.querySelector(`input[name="${field.id}"]:checked`);
      if (checked) formData[field.id] = checked.value;
    } else if (field.type === "multiselect") {
      const checked = [...document.querySelectorAll(`input[name="${field.id}"]:checked`)];
      formData[field.id] = checked.map(cb => cb.value);
    } else {
      const el = document.getElementById(field.id);
      if (el && el.value.trim() !== "") formData[field.id] = el.value.trim();
    }
  });
}

// ── Step navigation ───────────────────────────────────────────────────────────

function nextStep() {
  collectStepData(currentStep);
  if (currentStep < formSchema.sections.length - 1) {
    currentStep++;
    updateNav();
    renderStep(currentStep);
  }
}

function prevStep() {
  collectStepData(currentStep);
  if (currentStep > 0) {
    currentStep--;
    updateNav();
    renderStep(currentStep);
  }
}

// ── Report generation ─────────────────────────────────────────────────────────

async function generateReport() {
  collectStepData(currentStep);

  if (!formData.company_name || !formData.cin) {
    alert("Company name and CIN are required. Please go back and fill them in.");
    return;
  }

  show("loadingOverlay");
  hide("wizardOverlay");

  try {
    // Animate loading steps
    animateLoadingSteps();

    const response = await fetch(`${API_BASE}/api/generate-report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ form_data: formData }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${response.status}`);
    }

    const result = await response.json();
    generatedReport = result.report;

    hide("loadingOverlay");
    renderReport(generatedReport);
    show("reportOverlay");

  } catch (e) {
    hide("loadingOverlay");
    alert(`Report generation failed: ${e.message}\n\nPlease try again. If the issue persists, contact support.`);
    show("wizardOverlay");
  }
}

function animateLoadingSteps() {
  const steps = ["ls2","ls3","ls4","ls5"];
  const msgs  = [
    "Finding similar companies in SEBI XBRL database...",
    "Drafting Section A — General Disclosures...",
    "Writing Principles P1–P9 with Essential & Leadership Indicators...",
    "Adding sector benchmarks...",
  ];
  let i = 0;
  const interval = setInterval(() => {
    if (i > 0) {
      const prev = document.getElementById(steps[i-1]);
      if (prev) { prev.className = "loading-step loading-step--done"; prev.textContent = "✓ " + msgs[i-1].replace("...", ""); }
    }
    const cur = document.getElementById(steps[i]);
    if (cur) { cur.className = "loading-step loading-step--active"; cur.textContent = "⟳ " + msgs[i]; }
    document.getElementById("loadingMsg").textContent = msgs[i];
    i++;
    if (i >= steps.length) clearInterval(interval);
  }, 8000);
}

// ── Report rendering ──────────────────────────────────────────────────────────

function renderReport(report) {
  document.getElementById("reportTitle").textContent =
    `BRSR Report — ${report.company_name || ""}`;
  document.getElementById("reportSubtitle").textContent =
    `FY ${report.financial_year || ""} · ${report.reporting_boundary || ""} · Generated by Green Curve`;

  const body = document.getElementById("reportBody");
  body.innerHTML = "";

  // Section A
  const secA = report.section_a || {};
  let html = `<div class="report-section">
    <div class="report-section__title">SECTION A: GENERAL DISCLOSURES</div>`;

  const details = secA.i_details_of_listed_entity || {};
  if (details.data?.length) {
    html += `<table class="report-kv-table">`;
    details.data.forEach(item => {
      html += `<tr><td>${esc(item.label)}</td><td>${esc(item.value)}</td></tr>`;
    });
    html += `</table>`;
  }

  const prods = secA.ii_products_services || {};
  if (prods.description || prods.top_products?.length) {
    html += `<h4 style="color:#10b981;margin:16px 0 8px">Products & Services</h4>`;
    if (prods.description) html += `<p>${esc(prods.description)}</p>`;
    if (prods.top_products?.length) {
      html += `<ul>${prods.top_products.map(p => `<li>${esc(p)}</li>`).join("")}</ul>`;
    }
  }

  const emp = secA.iv_employees?.table;
  if (emp) {
    html += `<h4 style="color:#10b981;margin:16px 0 8px">Employees & Workers</h4>
    <table class="bench-table">
      <tr>${emp.headers.map(h => `<th>${esc(h)}</th>`).join("")}</tr>
      ${emp.rows.map(row => `<tr>${row.map(c => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}
    </table>`;
  }
  html += `</div>`;

  // Section B
  const secB = report.section_b || {};
  html += `<div class="report-section">
    <div class="report-section__title">SECTION B: MANAGEMENT AND PROCESS DISCLOSURES</div>`;
  if (secB.policy_overview?.description) {
    html += `<p><strong>Policy Overview:</strong> ${esc(secB.policy_overview.description)}</p>`;
  }
  const gov = secB.governance || {};
  if (gov.responsible_director) {
    html += `<table class="report-kv-table">
      <tr><td>Responsible Director</td><td>${esc(gov.responsible_director)} (DIN: ${esc(gov.din || "N/A")})</td></tr>
      <tr><td>Performance Incentive for ESG</td><td>${esc(gov.performance_incentive || "")}</td></tr>
      <tr><td>Grievance Mechanism</td><td>${esc(gov.grievance_mechanism || "")}</td></tr>
      <tr><td>Stakeholder Policy</td><td>${esc(gov.stakeholder_policy || "")}</td></tr>
    </table>`;
  }
  const assurance = secB.assurance || {};
  if (assurance.obtained) {
    html += `<p><strong>BRSR Assurance:</strong> ${esc(assurance.obtained)}
      ${assurance.type ? "· " + esc(assurance.type) : ""}
      ${assurance.provider ? "· " + esc(assurance.provider) : ""}</p>`;
  }
  html += `</div>`;

  // Section C — Principles
  const secC = report.section_c || {};
  html += `<div class="report-section">
    <div class="report-section__title">SECTION C: PRINCIPLE-WISE PERFORMANCE DISCLOSURE</div>`;

  (secC.principles || []).forEach((p, idx) => {
    html += `<div class="principle-block">
      <div class="principle-block__header" onclick="togglePrinciple(this)">
        <span>${esc(p.id)}: ${esc(p.title)}</span>
        <span class="toggle-icon">▼</span>
      </div>
      <div class="principle-block__body" id="p-body-${idx}">`;

    if (p.management_approach) {
      html += `<div class="principle-mgmt"><strong>Management Approach:</strong> ${esc(p.management_approach)}</div>`;
    }

    if (p.essential_indicators?.length) {
      html += `<h5 style="color:#10b981;margin:12px 0 8px;font-size:.85rem">Essential Indicators</h5>`;
      p.essential_indicators.forEach(ind => {
        html += `<div class="indicator-row">
          <div class="indicator-q">${esc(ind.indicator)}</div>
          <div class="indicator-a">${esc(ind.response || "Not disclosed")}</div>
        </div>`;
      });
    }

    if (p.leadership_indicators?.length) {
      html += `<h5 style="color:#7c3aed;margin:12px 0 8px;font-size:.85rem">Leadership Indicators</h5>`;
      p.leadership_indicators.forEach(ind => {
        html += `<div class="indicator-row">
          <div class="indicator-q">${esc(ind.indicator)}</div>
          <div class="indicator-a">${esc(ind.response || "Not disclosed")}</div>
        </div>`;
      });
    }

    html += `</div></div>`;
  });
  html += `</div>`;

  // Benchmarks
  const bench = report.benchmarks || {};
  if (bench.items?.length) {
    html += `<div class="report-section">
      <div class="report-section__title">BENCHMARKING vs. SIMILAR COMPANIES</div>
      <table class="bench-table">
        <tr><th>Metric</th><th>Your Value</th><th>Sector Comparison</th><th>Note</th></tr>
        ${bench.items.map(b => `<tr>
          <td>${esc(b.metric)}</td>
          <td><strong>${esc(b.company_value)}</strong></td>
          <td>${esc(b.sector_comparison)}</td>
          <td style="color:#64748b">${esc(b.note || "")}</td>
        </tr>`).join("")}
      </table>
    </div>`;
  }

  // Metadata
  const meta = report.metadata || {};
  html += `<div style="padding:16px;background:#f8fafc;border-radius:8px;margin-top:24px;font-size:.75rem;color:#94a3b8">
    Generated by Green Curve · ${meta.generated_at || ""} ·
    Data completeness: ${meta.data_completeness_pct || 0}% ·
    Reference companies: ${(meta.similar_companies_used || []).join(", ")}
  </div>`;

  body.innerHTML = html;

  // Auto-open first principle
  const firstBody = document.getElementById("p-body-0");
  if (firstBody) {
    firstBody.classList.add("open");
    firstBody.previousElementSibling?.classList.add("open");
  }
}

function togglePrinciple(header) {
  header.classList.toggle("open");
  const body = header.nextElementSibling;
  if (body) body.classList.toggle("open");
}

// ── PDF / JSON download ───────────────────────────────────────────────────────

async function downloadPdf() {
  if (!generatedReport) return;
  const btn = document.getElementById("btnDownloadPdf");
  btn.textContent = "⟳ Generating PDF...";
  btn.disabled = true;

  try {
    const r = await fetch(`${API_BASE}/api/export-pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report: generatedReport }),
    });

    if (!r.ok) throw new Error(`PDF export failed: ${r.status}`);

    const blob = await r.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `BRSR_${(generatedReport.company_name || "Report").replace(/\s+/g, "_")}_${generatedReport.financial_year || ""}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert(`PDF download failed: ${e.message}`);
  } finally {
    btn.textContent = "⬇ Download PDF";
    btn.disabled = false;
  }
}

function downloadJson() {
  if (!generatedReport) return;
  const blob = new Blob([JSON.stringify(generatedReport, null, 2)], { type: "application/json" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `BRSR_${(generatedReport.company_name || "Report").replace(/\s+/g, "_")}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

async function downloadXbrl() {
  if (!generatedReport) return;
  const btn = document.getElementById("btnDownloadXbrl");
  btn.textContent = "⟳ Generating XBRL...";
  btn.disabled = true;

  try {
    const r = await fetch(`${API_BASE}/api/export-xbrl`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report: generatedReport, form_data: formData }),
    });

    if (!r.ok) throw new Error(`XBRL export failed: ${r.status}`);

    const blob = await r.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `BRSR_${(generatedReport.company_name || "Report").replace(/\s+/g, "_")}_${generatedReport.financial_year || ""}.xml`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert(`XBRL download failed: ${e.message}`);
  } finally {
    btn.textContent = "⬇ Download XBRL";
    btn.disabled = false;
  }
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function show(id) { document.getElementById(id).removeAttribute("hidden"); }
function hide(id) { document.getElementById(id).setAttribute("hidden", ""); }
function esc(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function closeReport() {
  hide("reportOverlay");
}
