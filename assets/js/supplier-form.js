/**
 * supplier-form.js — Supplier ESG Questionnaire (BRSR Value-Chain)
 * Reads ?t=<supplier_token> from URL, fetches context, renders 5-step form.
 */

const API_BASE = "https://7334807f62be7d.lhr.life";

const STEPS = ["Identity", "Environment", "Social", "Governance", "Products"];
const STEP_MAXPTS = [null, 30, 30, 25, 15]; // null for identity (no score)

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
let supplierToken = null;
let formInfo      = null;
let currentStep   = 0;   // 0-indexed; step 5 = result screen
const formData    = {};

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  supplierToken = new URLSearchParams(window.location.search).get("t");

  if (!supplierToken) {
    showInvalidToken("No invite token found in URL. Please use the link provided by your buyer.");
    return;
  }

  showLoading();

  try {
    const res = await fetch(`${API_BASE}/api/value-chain/form-info/${supplierToken}`);
    if (res.status === 404) {
      showInvalidToken("This invite link is not valid or has expired. Please contact your buyer for a new link.");
      return;
    }
    if (!res.ok) throw new Error(`Server error ${res.status}`);

    formInfo = await res.json();

    if (formInfo.already_submitted) {
      showAlreadySubmitted();
      return;
    }

    setInvitedBy(formInfo.company_name);
    renderStep(0);
  } catch (err) {
    showInvalidToken(`Could not load form: ${err.message}. Ensure the backend is reachable.`);
  }
});

// ── Screen helpers ────────────────────────────────────────────────────────────

function showLoading() {
  document.getElementById("sf-content").innerHTML = `
    <div class="vc-loading"><div class="vc-spinner"></div>Loading your form…</div>
  `;
  document.getElementById("sf-nav").style.display = "none";
  document.getElementById("sf-progress-wrap").style.display = "none";
}

function showInvalidToken(msg) {
  document.getElementById("sf-content").innerHTML = `
    <div class="sf-invalid">
      <div class="sf-invalid__icon">🔗</div>
      <div class="sf-invalid__title">Invalid invite link</div>
      <div class="sf-invalid__sub">${escHtml(msg)}</div>
    </div>
  `;
  document.getElementById("sf-nav").style.display = "none";
  document.getElementById("sf-progress-wrap").style.display = "none";
}

function showAlreadySubmitted() {
  document.getElementById("sf-content").innerHTML = `
    <div class="sf-already">
      <div class="sf-already__icon">✅</div>
      <div class="sf-already__title">Already Submitted</div>
      <div class="sf-already__sub">
        Your ESG questionnaire for <strong style="color:var(--cyan)">${escHtml(formInfo?.company_name || "")}</strong>
        has already been submitted. Thank you.
      </div>
    </div>
  `;
  document.getElementById("sf-nav").style.display = "none";
  document.getElementById("sf-progress-wrap").style.display = "none";
}

function setInvitedBy(companyName) {
  const el = document.getElementById("sf-invited-by");
  if (el) el.innerHTML = `Invited by <span>${escHtml(companyName)}</span>`;
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function updateProgress(step) {
  const pct = Math.round((step / STEPS.length) * 100);
  document.getElementById("sf-progress-fill").style.width = pct + "%";

  document.querySelectorAll(".sf-progress-label").forEach((el, i) => {
    el.classList.remove("active", "done");
    if (i === step)    el.classList.add("active");
    if (i < step)      el.classList.add("done");
  });

  const counter = document.getElementById("sf-step-count");
  if (counter) counter.textContent = `Step ${step + 1} of ${STEPS.length}`;
}

// ── Step renderer ─────────────────────────────────────────────────────────────

function renderStep(step) {
  currentStep = step;
  updateProgress(step);

  document.getElementById("sf-nav").style.display = "flex";
  document.getElementById("sf-progress-wrap").style.display = "block";

  // Back button
  const backBtn = document.getElementById("sf-back-btn");
  backBtn.style.display = step > 0 ? "inline-flex" : "none";

  // Next / Submit button
  const nextBtn = document.getElementById("sf-next-btn");
  if (step === STEPS.length - 1) {
    nextBtn.textContent = "Submit →";
    nextBtn.onclick = handleSubmit;
  } else {
    nextBtn.textContent = "Next →";
    nextBtn.onclick = handleNext;
  }

  const builders = [buildStep0, buildStep1, buildStep2, buildStep3, buildStep4];
  document.getElementById("sf-content").innerHTML = builders[step]();
  bindRadioHighlight();
}

// ── Step 0: Identity ──────────────────────────────────────────────────────────

function buildStep0() {
  const sectorOpts = SECTORS.map(s => `<option value="${s}" ${(formData.supplier_sector||"")=== s ? "selected":""} >${escHtml(s)}</option>`).join("");
  return `
    <div class="sf-section-header">
      <div class="sf-section-header__step">Step 1 of 5</div>
      <div class="sf-section-header__title">Supplier Identity</div>
      <div class="sf-section-header__desc">
        Basic information about your organisation — required to attribute your ESG data to the correct entity.
      </div>
    </div>

    <div class="sf-field">
      <label>Your Company Name <span class="req">*</span></label>
      <input type="text" id="f-supplier_company_name" value="${escVal(formData.supplier_company_name)}"
             placeholder="ABC Components Pvt Ltd" />
    </div>
    <div class="sf-two-col">
      <div class="sf-field">
        <label>CIN <span class="opt">optional</span></label>
        <input type="text" id="f-supplier_cin" value="${escVal(formData.supplier_cin)}"
               placeholder="U12345MH2010PTC210000" />
      </div>
      <div class="sf-field">
        <label>Annual Turnover Band</label>
        <select id="f-annual_turnover_band">
          <option value="">— Select —</option>
          ${["< ₹10 Crore","₹10–100 Crore","₹100–500 Crore","> ₹500 Crore","Prefer not to disclose"].map(
            o => `<option value="${o}" ${(formData.annual_turnover_band||"")=== o?"selected":""}>${o}</option>`
          ).join("")}
        </select>
      </div>
    </div>
    <div class="sf-two-col">
      <div class="sf-field">
        <label>Industry / Sector</label>
        <select id="f-supplier_sector">
          <option value="">— Select —</option>
          ${sectorOpts}
        </select>
      </div>
      <div class="sf-field">
        <label>Total Employees <span class="opt">optional</span></label>
        <input type="number" id="f-total_employees" value="${formData.total_employees ?? ""}"
               placeholder="250" min="0" />
      </div>
    </div>
  `;
}

// ── Step 1: Environment ───────────────────────────────────────────────────────

function buildStep1() {
  return `
    <div class="sf-section-header">
      <div class="sf-section-header__step">Step 2 of 5</div>
      <div class="sf-section-header__title">Environment</div>
      <div class="sf-section-header__desc">
        Greenhouse gas emissions, energy use, and resource consumption. Leave blank if not yet measured —
        your buyer can see which fields were provided.
      </div>
    </div>

    <div class="sf-two-col">
      <div class="sf-field">
        <label>Scope 1 Emissions <span class="opt">tCO₂e</span></label>
        <input type="number" id="f-scope1_emissions" value="${formData.scope1_emissions ?? ""}"
               placeholder="Not calculated" min="0" step="0.01" />
        <div class="sf-field__hint">Direct emissions from owned sources</div>
      </div>
      <div class="sf-field">
        <label>Scope 2 Emissions <span class="opt">tCO₂e</span></label>
        <input type="number" id="f-scope2_emissions" value="${formData.scope2_emissions ?? ""}"
               placeholder="Not calculated" min="0" step="0.01" />
        <div class="sf-field__hint">From purchased electricity / heat</div>
      </div>
    </div>
    <div class="sf-two-col">
      <div class="sf-field">
        <label>Total Energy Consumed <span class="opt">GJ</span></label>
        <input type="number" id="f-energy_total_gj" value="${formData.energy_total_gj ?? ""}"
               placeholder="Not measured" min="0" step="0.1" />
      </div>
      <div class="sf-field">
        <label>% Renewable Energy <span class="opt">0–100</span></label>
        <input type="number" id="f-renewable_energy_pct" value="${formData.renewable_energy_pct ?? ""}"
               placeholder="0" min="0" max="100" step="0.1" />
      </div>
    </div>
    <div class="sf-two-col">
      <div class="sf-field">
        <label>Water Consumption <span class="opt">KL</span></label>
        <input type="number" id="f-water_consumption_kl" value="${formData.water_consumption_kl ?? ""}"
               placeholder="Not measured" min="0" step="1" />
      </div>
      <div class="sf-field">
        <label>Total Waste Generated <span class="opt">tonnes</span></label>
        <input type="number" id="f-waste_total_tonnes" value="${formData.waste_total_tonnes ?? ""}"
               placeholder="Not measured" min="0" step="0.1" />
      </div>
    </div>
  `;
}

// ── Step 2: Social & Labour ───────────────────────────────────────────────────

function buildStep2() {
  const wageOpts = [
    "All employees paid minimum wage or above",
    "Majority paid minimum wage or above",
    "Some employees paid below minimum wage",
  ];
  const clOpts = ["None", "Yes — incidents reported"];

  return `
    <div class="sf-section-header">
      <div class="sf-section-header__step">Step 3 of 5</div>
      <div class="sf-section-header__title">Social &amp; Labour</div>
      <div class="sf-section-header__desc">
        Workforce practices, occupational safety, and human rights compliance —
        aligned to BRSR Principles 3 &amp; 5.
      </div>
    </div>

    <div class="sf-field">
      <label>Minimum Wage Compliance <span class="req">*</span></label>
      <div class="sf-radios" id="rg-min_wage_compliance">
        ${wageOpts.map(o => radioOpt("min_wage_compliance", o, formData.min_wage_compliance === o)).join("")}
      </div>
    </div>
    <div class="sf-two-col">
      <div class="sf-field">
        <label>Work-related Fatalities (current year)</label>
        <input type="number" id="f-fatalities_current_year" value="${formData.fatalities_current_year ?? 0}"
               min="0" step="1" />
        <div class="sf-field__hint">Employees + workers combined</div>
      </div>
      <div class="sf-field">
        <label>Lost Time Injury Frequency Rate <span class="opt">optional</span></label>
        <input type="number" id="f-ltifr" value="${formData.ltifr ?? ""}"
               placeholder="e.g. 0.45" min="0" step="0.01" />
        <div class="sf-field__hint">Per million hours worked</div>
      </div>
    </div>
    <div class="sf-field">
      <label>% Employees Trained on Safety / ESG (current year)</label>
      <input type="number" id="f-safety_training_pct" value="${formData.safety_training_pct ?? ""}"
             placeholder="0" min="0" max="100" step="1" />
    </div>
    <div class="sf-field">
      <label>Child Labour / Forced Labour Incidents <span class="req">*</span></label>
      <div class="sf-radios" id="rg-child_labour_incidents">
        ${clOpts.map(o => radioOpt("child_labour_incidents", o, (formData.child_labour_incidents || "None") === o)).join("")}
      </div>
    </div>
  `;
}

// ── Step 3: Governance ────────────────────────────────────────────────────────

function buildStep3() {
  const yesNo      = ["Yes", "No"];
  const trainOpts  = ["Yes", "Planned", "No"];
  const violOpts   = ["None", "Yes — details below"];

  return `
    <div class="sf-section-header">
      <div class="sf-section-header__step">Step 4 of 5</div>
      <div class="sf-section-header__title">Governance</div>
      <div class="sf-section-header__desc">
        Ethics, anti-corruption, and regulatory compliance — aligned to BRSR Principle 1.
      </div>
    </div>

    <div class="sf-field">
      <label>Anti-Corruption / Anti-Bribery Policy in place? <span class="req">*</span></label>
      <div class="sf-radios" id="rg-anti_corruption_policy">
        ${yesNo.map(o => radioOpt("anti_corruption_policy", o, formData.anti_corruption_policy === o)).join("")}
      </div>
    </div>
    <div class="sf-field">
      <label>Whistleblower / Vigil Mechanism in place? <span class="req">*</span></label>
      <div class="sf-radios" id="rg-whistleblower_mechanism">
        ${yesNo.map(o => radioOpt("whistleblower_mechanism", o, formData.whistleblower_mechanism === o)).join("")}
      </div>
    </div>
    <div class="sf-field">
      <label>ESG / Ethics Training conducted for employees?</label>
      <div class="sf-radios" id="rg-ethics_training">
        ${trainOpts.map(o => radioOpt("ethics_training", o, formData.ethics_training === o)).join("")}
      </div>
    </div>
    <div class="sf-field">
      <label>Regulatory Notices / Violations in last 2 years?</label>
      <div class="sf-radios" id="rg-regulatory_violations">
        ${violOpts.map(o => radioOpt("regulatory_violations", o, (formData.regulatory_violations || "None") === o)).join("")}
      </div>
    </div>
    <div class="sf-field" id="viol-detail-wrap" style="${formData.regulatory_violations === 'Yes — details below' ? '' : 'display:none'}">
      <label>Violation Details</label>
      <textarea id="f-regulatory_violations_detail" rows="3"
                placeholder="Briefly describe the nature and current status of any regulatory notices">${escHtml(formData.regulatory_violations_detail || "")}</textarea>
    </div>
  `;
}

// ── Step 4: Products & Compliance ─────────────────────────────────────────────

function buildStep4() {
  const eprOpts = [
    "No — not applicable",
    "Yes — EPR return filed",
    "Yes — EPR return NOT yet filed",
    "Not sure",
  ];

  return `
    <div class="sf-section-header">
      <div class="sf-section-header__step">Step 5 of 5</div>
      <div class="sf-section-header__title">Products &amp; Compliance</div>
      <div class="sf-section-header__desc">
        Extended Producer Responsibility, recycled inputs, and certifications —
        aligned to BRSR Principles 2 &amp; 8.
      </div>
    </div>

    <div class="sf-field">
      <label>EPR (Extended Producer Responsibility) Status</label>
      <div class="sf-radios" id="rg-epr_applicable">
        ${eprOpts.map(o => radioOpt("epr_applicable", o, formData.epr_applicable === o)).join("")}
      </div>
      <div class="sf-field__hint">Plastic, e-waste, or battery EPR under CPCB rules</div>
    </div>
    <div class="sf-field">
      <label>% Input Material from Recycled / Reused Sources <span class="opt">optional</span></label>
      <input type="number" id="f-recycled_input_pct" value="${formData.recycled_input_pct ?? ""}"
             placeholder="0" min="0" max="100" step="0.1" />
    </div>
    <div class="sf-field">
      <label>Relevant Certifications <span class="opt">optional</span></label>
      <input type="text" id="f-certifications" value="${escVal(formData.certifications)}"
             placeholder="ISO 14001, SA8000, GreenPro, BIS, etc." />
    </div>

    <div class="sf-field" style="margin-top:28px">
      <div class="sf-checkbox-wrap">
        <input type="checkbox" id="f-declaration" ${formData.declaration ? "checked" : ""} />
        <span>I confirm that the information provided in this questionnaire is accurate to the best of my knowledge and belief, and represents the activities of my organisation for the current financial year.</span>
      </div>
    </div>
  `;
}

// ── Radio helper ──────────────────────────────────────────────────────────────

function radioOpt(name, value, checked) {
  return `
    <label class="sf-radio-opt ${checked ? "selected" : ""}">
      <input type="radio" name="${escAttr(name)}" value="${escAttr(value)}" ${checked ? "checked" : ""} />
      <span>${escHtml(value)}</span>
    </label>
  `;
}

function bindRadioHighlight() {
  document.querySelectorAll(".sf-radio-opt input[type=radio]").forEach(radio => {
    radio.addEventListener("change", () => {
      const group = radio.closest(".sf-radios");
      if (group) group.querySelectorAll(".sf-radio-opt").forEach(opt => opt.classList.remove("selected"));
      radio.closest(".sf-radio-opt")?.classList.add("selected");

      // Special: show/hide violation detail textarea
      if (radio.name === "regulatory_violations") {
        const wrap = document.getElementById("viol-detail-wrap");
        if (wrap) wrap.style.display = radio.value === "Yes — details below" ? "" : "none";
      }
    });
  });
}

// ── Navigation ────────────────────────────────────────────────────────────────

function handleNext() {
  if (!collectStep(currentStep)) return;
  renderStep(currentStep + 1);
}

document.addEventListener("DOMContentLoaded", () => {
  // Wire back button after DOM ready
  const backBtn = document.getElementById("sf-back-btn");
  if (backBtn) backBtn.onclick = () => { collectStep(currentStep, true); renderStep(currentStep - 1); };
});

// ── Collect step data ─────────────────────────────────────────────────────────

function collectStep(step, silent = false) {
  const errEl = document.getElementById("sf-step-error");
  if (errEl) errEl.remove();

  if (step === 0) {
    const name = val("f-supplier_company_name");
    if (!name && !silent) { showStepError("Company name is required."); return false; }
    formData.supplier_company_name = name;
    formData.supplier_cin          = val("f-supplier_cin");
    formData.supplier_sector       = val("f-supplier_sector");
    formData.annual_turnover_band  = val("f-annual_turnover_band");
    formData.total_employees       = numVal("f-total_employees");
  }

  if (step === 1) {
    formData.scope1_emissions     = numVal("f-scope1_emissions");
    formData.scope2_emissions     = numVal("f-scope2_emissions");
    formData.energy_total_gj      = numVal("f-energy_total_gj");
    formData.renewable_energy_pct = numVal("f-renewable_energy_pct");
    formData.water_consumption_kl = numVal("f-water_consumption_kl");
    formData.waste_total_tonnes   = numVal("f-waste_total_tonnes");
  }

  if (step === 2) {
    const wage = radioVal("min_wage_compliance");
    const cl   = radioVal("child_labour_incidents");
    if (!wage && !silent) { showStepError("Minimum wage compliance is required."); return false; }
    if (!cl   && !silent) { showStepError("Child labour field is required."); return false; }
    formData.min_wage_compliance    = wage;
    formData.fatalities_current_year = parseInt(val("f-fatalities_current_year") || "0", 10);
    formData.ltifr                  = numVal("f-ltifr");
    formData.safety_training_pct    = numVal("f-safety_training_pct");
    formData.child_labour_incidents = cl || "None";
  }

  if (step === 3) {
    const acp = radioVal("anti_corruption_policy");
    const wb  = radioVal("whistleblower_mechanism");
    if (!acp && !silent) { showStepError("Anti-corruption policy field is required."); return false; }
    if (!wb  && !silent) { showStepError("Whistleblower mechanism field is required."); return false; }
    formData.anti_corruption_policy        = acp;
    formData.whistleblower_mechanism       = wb;
    formData.ethics_training               = radioVal("ethics_training") || "";
    formData.regulatory_violations         = radioVal("regulatory_violations") || "None";
    formData.regulatory_violations_detail  = val("f-regulatory_violations_detail");
  }

  if (step === 4) {
    const decl = document.getElementById("f-declaration")?.checked;
    if (!decl && !silent) { showStepError("Please confirm the declaration before submitting."); return false; }
    formData.epr_applicable      = radioVal("epr_applicable") || "";
    formData.recycled_input_pct  = numVal("f-recycled_input_pct");
    formData.certifications      = val("f-certifications");
    formData.declaration         = decl;
  }

  return true;
}

function showStepError(msg) {
  const content = document.getElementById("sf-content");
  const div = document.createElement("div");
  div.id = "sf-step-error";
  div.className = "vc-notice vc-notice--error";
  div.style.marginTop = "16px";
  div.textContent = msg;
  content.appendChild(div);
  div.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ── Submit ────────────────────────────────────────────────────────────────────

async function handleSubmit() {
  if (!collectStep(4)) return;

  const nextBtn = document.getElementById("sf-next-btn");
  nextBtn.disabled = true;
  nextBtn.textContent = "Submitting…";

  try {
    const res = await fetch(`${API_BASE}/api/value-chain/submit`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        supplier_token: supplierToken,
        form_data:      formData,
      }),
    });
    if (res.status === 409) {
      showAlreadySubmitted();
      return;
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${res.status}`);
    }
    const result = await res.json();
    showResult(result);
  } catch (err) {
    showStepError(`Submission failed: ${err.message}`);
    nextBtn.disabled = false;
    nextBtn.textContent = "Submit →";
  }
}

// ── Result screen ─────────────────────────────────────────────────────────────

function showResult(result) {
  document.getElementById("sf-nav").style.display = "none";
  document.getElementById("sf-progress-wrap").style.display = "none";

  const { score, risk_tier, breakdown } = result;
  const tierLabel = { Green: "Low Risk", Amber: "Medium Risk", Red: "High Risk" }[risk_tier] || risk_tier;
  const maxPts = { environment: 30, social: 30, governance: 25, products: 15 };

  const brows = ["environment", "social", "governance", "products"].map(k => {
    const pts  = breakdown?.[k] ?? 0;
    const max  = maxPts[k];
    const pct  = Math.round((pts / max) * 100);
    return `
      <div class="sf-brow">
        <span class="sf-brow__label">${k.charAt(0).toUpperCase() + k.slice(1)}</span>
        <div class="sf-brow__bar-wrap">
          <div class="sf-brow__bar" style="width:${pct}%"></div>
        </div>
        <span class="sf-brow__pts">${pts}/${max}</span>
      </div>
    `;
  }).join("");

  document.getElementById("sf-content").innerHTML = `
    <div class="sf-result">
      <div class="sf-result__title">Thank you!</div>
      <div class="sf-result__sub">
        Your ESG questionnaire for <strong style="color:var(--cyan)">${escHtml(formInfo?.company_name || "")}</strong>
        has been submitted.
      </div>

      <div class="sf-score-circle sf-score-circle--${risk_tier}">
        <span class="sf-score-num">${score}</span>
        <span class="sf-score-label sf-score-label--${risk_tier}">${tierLabel}</span>
      </div>

      <div class="sf-breakdown">
        <div class="sf-breakdown__title">Score Breakdown</div>
        ${brows}
      </div>

      <div class="sf-result__note">
        This ESG Value-Chain Score (0–100) is based on your BRSR-aligned disclosures across
        Environment, Social, Governance, and Products dimensions.
        It will be shared with <strong>${escHtml(formInfo?.company_name || "your buyer")}</strong>
        as part of their SEBI BRSR value-chain disclosure.
      </div>
    </div>
  `;
}

// ── Utility ───────────────────────────────────────────────────────────────────

function val(id) {
  return (document.getElementById(id)?.value || "").trim();
}
function numVal(id) {
  const v = val(id);
  return v === "" ? null : parseFloat(v);
}
function radioVal(name) {
  const checked = document.querySelector(`input[name="${name}"]:checked`);
  return checked ? checked.value : null;
}
function escHtml(str) {
  return String(str || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
function escVal(str)  { return escHtml(str || ""); }
function escAttr(str) { return escHtml(str || ""); }
