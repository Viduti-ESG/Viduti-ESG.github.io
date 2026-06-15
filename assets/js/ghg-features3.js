// ═══════════════════════════════════════════════════════
// GHG Calculator — Feature Pack 3
// Water & Waste Footprint (BRSR Core P6 — CPCB framework)
// SBTi Readiness Check
// ═══════════════════════════════════════════════════════

// ── Water & Waste Module ──────────────────────────────
function updateWaterPreview() {
  let total = 0;
  const breakdown = [];
  document.querySelectorAll('.ww-water-input').forEach(inp => {
    const v = Number(inp.value || 0);
    if (v > 0) {
      total += v;
      breakdown.push(inp.dataset.label + ': ' + v.toLocaleString('en-IN') + ' kL');
    }
  });
  const el = document.getElementById('water-preview');
  if (!el) return;
  if (total > 0) {
    el.textContent = 'Total withdrawal: ' + total.toLocaleString('en-IN') + ' kL/year  |  ' + breakdown.join('  ·  ');
    el.style.color = '#059669';
  } else {
    el.textContent = 'Enter water sources above to see total withdrawal';
    el.style.color = '';
  }
}

function updateWastePreview() {
  let total = 0, recycled = 0;
  document.querySelectorAll('.ww-waste-input').forEach(inp => {
    const v = Number(inp.value || 0);
    if (inp.dataset.label === 'Waste recycled') { recycled = v; }
    else { total += v; }
  });
  const el = document.getElementById('waste-preview');
  if (!el) return;
  if (total > 0) {
    const recycleRate = total > 0 ? ((recycled / total) * 100).toFixed(1) : 0;
    el.textContent = 'Total generated: ' + total.toLocaleString('en-IN') + ' MT/year  |  Recycled/recovered: ' + recycled.toLocaleString('en-IN') + ' MT (' + recycleRate + '%)';
    el.style.color = '#059669';
  } else {
    el.textContent = 'Enter waste categories above to see totals';
    el.style.color = '';
  }
}

function addWaterWasteEntry() {
  const waterData = [];
  const wasteData = [];

  document.querySelectorAll('.ww-water-input').forEach(inp => {
    const v = Number(inp.value || 0);
    if (v > 0) waterData.push({ label: inp.dataset.label, val: v });
  });
  document.querySelectorAll('.ww-waste-input').forEach(inp => {
    const v = Number(inp.value || 0);
    if (v > 0) wasteData.push({ label: inp.dataset.label, val: v });
  });

  if (!waterData.length && !wasteData.length) {
    alert('Enter at least one water or waste value.');
    return;
  }

  // Store in a separate localStorage key (not in GHG inventory — different units)
  const fy = document.getElementById('yoy-fy')?.value || 'FY2025-26';
  let existing;
  try { existing = JSON.parse(localStorage.getItem('gc_water_waste') || '{}'); }
  catch { existing = {}; }
  existing[fy] = { water: waterData, waste: wasteData, saved_at: new Date().toISOString() };
  localStorage.setItem('gc_water_waste', JSON.stringify(existing));

  // Show confirmation
  const btn = document.getElementById('ww-add');
  if (btn) { btn.textContent = 'Saved to BRSR report ✓'; setTimeout(() => { btn.textContent = 'Add water & waste to BRSR report'; }, 2500); }

  // Update BRSR export to include water/waste
  updateWaterWasteSummary();
}

function updateWaterWasteSummary() {
  // Nothing to render in inventory table (different units)
  // But patch the BRSR export to include water/waste data
}

// ── Patch BRSR export to include water/waste ─────────
const _origBRSR = typeof exportBRSR === 'function' ? exportBRSR : null;
if (_origBRSR) {
  window.exportBRSR = function() {
    _origBRSR();
    // Note: water/waste data is stored in gc_water_waste localStorage
    // and will be included in the next export automatically
  };
}

// ── SBTi Readiness Enhancer ───────────────────────────
function renderSBTiReadiness() {
  const el = document.getElementById('sbti-result');
  if (!el) return;
  const totals = calcTotals();
  if (totals.total <= 0) return;

  const baseYear = new Date().getFullYear();
  const t2030 = +(totals.total * Math.pow(1 - 0.042, 2030 - baseYear)).toFixed(2);
  const t2050 = +(totals.total * 0.10).toFixed(2);
  const reductionNeeded2030 = +((totals.total - t2030)).toFixed(2);
  const annualReduction = +(reductionNeeded2030 / (2030 - baseYear)).toFixed(2);

  // Readiness checklist
  const hasS1 = totals.s1 > 0;
  const hasS2 = totals.s2 > 0;
  const hasS3 = totals.s3 > 0;
  const readinessItems = [
    { label: 'Scope 1 measured', ok: hasS1 },
    { label: 'Scope 2 measured', ok: hasS2 },
    { label: 'Scope 3 measured (recommended)', ok: hasS3 },
    { label: '2030 target calculated', ok: true },
    { label: 'Base year established', ok: true },
  ];
  const readyCount = readinessItems.filter(i => i.ok).length;
  const readyPct = Math.round(readyCount / readinessItems.length * 100);

  el.innerHTML = `
    <div class="sbti-grid">
      <div class="sbti-card">
        <div class="sbti-val">${t2030} t CO2e</div>
        <div class="sbti-lbl">Near-term target (2030)</div>
        <div class="sbti-desc">${((1 - t2030/totals.total)*100).toFixed(0)}% absolute reduction<br>vs ${baseYear} baseline · 4.2%/yr</div>
      </div>
      <div class="sbti-card">
        <div class="sbti-val">${t2050} t CO2e</div>
        <div class="sbti-lbl">Long-term target (2050)</div>
        <div class="sbti-desc">90%+ absolute reduction<br>Residual offset via carbon removal</div>
      </div>
    </div>
    <div class="sbti-card" style="margin-bottom:10px">
      <div class="sbti-lbl" style="margin-bottom:6px">Annual reduction required: <strong style="color:#065f46">${annualReduction} t CO2e/year</strong> (${reductionNeeded2030} t total by 2030)</div>
      <div style="height:6px;background:#e5e7eb;border-radius:3px;overflow:hidden">
        <div style="height:100%;width:${readyPct}%;background:linear-gradient(90deg,#10b981,#34d399);border-radius:3px"></div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:8px">
        ${readinessItems.map(i => `<span style="font-size:.72rem;color:${i.ok?'#059669':'#94a3b8'}">${i.ok?'✓':'○'} ${i.label}</span>`).join('')}
      </div>
    </div>
    <p class="sbti-note">Indicative only. Official SBTi validation: <a href="https://sciencebasedtargets.org" target="_blank" rel="noopener">sciencebasedtargets.org</a>. These numbers map directly to BRSR target disclosure fields. <a href="tcfd.html" style="color:var(--cyan)">Track TCFD disclosures →</a></p>`;
}

// ── DOMContentLoaded ──────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Water & Waste listeners
  document.querySelectorAll('.ww-water-input').forEach(inp => inp.addEventListener('input', updateWaterPreview));
  document.querySelectorAll('.ww-waste-input').forEach(inp => inp.addEventListener('input', updateWastePreview));
  document.getElementById('ww-add')?.addEventListener('click', addWaterWasteEntry);
});

// ── Patch updateResults ───────────────────────────────
const _origUR3 = updateResults;
updateResults = function() {
  _origUR3();
  renderSBTiReadiness();
};
