// Green Curve — BRSR Supplier ESG Form Logic

(function () {
  'use strict';

  // ── Parse URL params ────────────────────────────────────────────────────────
  var params          = new URLSearchParams(window.location.search);
  var mandatingName   = decodeURIComponent(params.get('company') || '');
  var mandatingCin    = decodeURIComponent(params.get('cin')     || '');
  var token           = decodeURIComponent(params.get('token')   || '');
  var gcApiBase       = (function () {
    try { return localStorage.getItem('gc_api_base') || ''; } catch (_) { return ''; }
  })();

  // ── On DOMContentLoaded ─────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.js-mandating-name').forEach(function (el) {
      el.textContent = mandatingName || 'the requesting company';
    });

    var fToken    = document.getElementById('f-token');
    var fMandName = document.getElementById('f-mandating-name');
    var fMandCin  = document.getElementById('f-mandating-cin');
    if (fToken)    fToken.value    = token;
    if (fMandName) fMandName.value = mandatingName;
    if (fMandCin)  fMandCin.value  = mandatingCin;

    bindNd('chk-scope1-nd', 'inp-scope1');
    bindNd('chk-scope2-nd', 'inp-scope2');
    bindNd('chk-water-nd',  'inp-water');
    bindNd('chk-waste-nd',  'inp-waste');

    wireScrollProgress();
  });

  function bindNd(checkId, inputId) {
    var chk = document.getElementById(checkId);
    var inp = document.getElementById(inputId);
    if (!chk || !inp) return;
    chk.addEventListener('change', function () {
      inp.disabled = chk.checked;
      if (chk.checked) inp.value = '';
      inp.required = !chk.checked;
    });
  }

  function wireScrollProgress() {
    var sections = ['sf-sec-a', 'sf-sec-b', 'sf-sec-c', 'sf-sec-d'];
    var steps    = document.querySelectorAll('.sf-step');
    if (!steps.length) return;
    window.addEventListener('scroll', function () {
      var scrollMid = window.scrollY + window.innerHeight * 0.4;
      var activeIdx = 0;
      sections.forEach(function (id, i) {
        var el = document.getElementById(id);
        if (el && el.offsetTop <= scrollMid) activeIdx = i;
      });
      steps.forEach(function (s, i) {
        s.classList.toggle('active', i <= activeIdx);
      });
    }, { passive: true });
  }

  // ── ESG risk score (0–10 scale, consistent with dashboard scoring) ──────────
  function computeSupplierEsgRisk(d) {
    var score = 5.0;

    if (!d.has_environmental_policy) score += 1.0;
    if (d.scope1_not_disclosed)      score += 0.5;
    if (d.scope2_not_disclosed)      score += 0.5;
    if (d.water_not_disclosed)       score += 0.2;
    if (d.waste_not_disclosed)       score += 0.2;
    if (!d.has_hr_policy)            score += 0.5;
    if (d.safety_incidents > 0)      score += Math.min(1.0, d.safety_incidents * 0.3);
    if (!d.has_code_of_conduct)      score += 0.5;
    if (d.regulatory_violations > 0) score += Math.min(2.0, d.regulatory_violations * 0.8);

    if (d.has_brsr_disclosure)      score -= 1.0;
    if (d.has_environmental_policy) score -= 0.3;
    if (d.is_msme)                  score -= 0.2;

    return Math.max(1.0, Math.min(9.5, Math.round(score * 10) / 10));
  }

  // ── Submit ──────────────────────────────────────────────────────────────────
  function submitSupplierForm(e) {
    e.preventDefault();
    var form = document.getElementById('sf-form');
    if (!form) return;

    var btn = document.getElementById('sf-submit-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Submitting…'; }

    var fd = new FormData(form);
    var scope1Nd = fd.get('scope1_not_disclosed') === 'on';
    var scope2Nd = fd.get('scope2_not_disclosed') === 'on';
    var waterNd  = fd.get('water_not_disclosed')  === 'on';
    var wasteNd  = fd.get('waste_not_disclosed')  === 'on';

    var data = {
      token:                  fd.get('token') || token,
      mandating_company_name: fd.get('mandating_name') || mandatingName,
      mandating_company_cin:  fd.get('mandating_cin')  || mandatingCin,
      submitted_at:           new Date().toISOString(),
      supplier_name:          (fd.get('supplier_name')  || '').trim(),
      supplier_gstin:         (fd.get('supplier_gstin') || '').trim().toUpperCase(),
      supplier_cin:           (fd.get('supplier_cin')   || '').trim().toUpperCase(),
      annual_revenue_band:    fd.get('annual_revenue_band') || '',
      is_msme:                fd.get('is_msme') === 'yes',
      has_environmental_policy: fd.get('has_environmental_policy') === 'yes',
      scope1_tco2e:           scope1Nd ? null : (parseFloat(fd.get('scope1_tco2e')) || null),
      scope1_not_disclosed:   scope1Nd,
      scope2_tco2e:           scope2Nd ? null : (parseFloat(fd.get('scope2_tco2e')) || null),
      scope2_not_disclosed:   scope2Nd,
      water_m3:               waterNd  ? null : (parseFloat(fd.get('water_m3'))     || null),
      water_not_disclosed:    waterNd,
      waste_tonnes:           wasteNd  ? null : (parseFloat(fd.get('waste_tonnes')) || null),
      waste_not_disclosed:    wasteNd,
      total_employees:        parseInt(fd.get('total_employees'), 10) || 0,
      has_hr_policy:          fd.get('has_hr_policy') === 'yes',
      safety_incidents:       parseInt(fd.get('safety_incidents'), 10) || 0,
      women_pct:              parseFloat(fd.get('women_pct')) || 0,
      has_brsr_disclosure:    fd.get('has_brsr_disclosure') === 'yes',
      has_code_of_conduct:    fd.get('has_code_of_conduct') === 'yes',
      regulatory_violations:  parseInt(fd.get('regulatory_violations'), 10) || 0,
    };
    data.esg_risk_score = computeSupplierEsgRisk(data);

    if (gcApiBase) {
      fetch(gcApiBase + '/api/supplier-response', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(data),
      })
        .then(function (r) {
          if (r.ok) { showThankYou(data, false); }
          else      { fallbackDownload(data); }
        })
        .catch(function () { fallbackDownload(data); });
    } else {
      fallbackDownload(data);
    }
  }

  function fallbackDownload(data) {
    var blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    var url  = URL.createObjectURL(blob);
    var a    = document.createElement('a');
    var slug = (data.supplier_name || 'supplier')
      .replace(/\s+/g, '-').toLowerCase().replace(/[^a-z0-9-]/g, '');
    a.href     = url;
    a.download = 'supplier-esg-' + slug + '.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showThankYou(data, true);
  }

  function showThankYou(data, downloaded) {
    var wrap = document.getElementById('sf-form-wrap');
    var ty   = document.getElementById('sf-thankyou');
    if (wrap) wrap.style.display = 'none';
    if (!ty)  return;
    ty.style.display = 'block';

    var score = data.esg_risk_score;
    var tier  = score >= 6.5 ? 'High Risk' : score >= 3.5 ? 'Medium Risk' : 'Low Risk';
    var color = score >= 6.5 ? '#f87171'   : score >= 3.5 ? '#fbbf24'      : '#34d399';

    var elCo    = document.getElementById('ty-company');
    var elScore = document.getElementById('ty-score');
    var elTier  = document.getElementById('ty-tier');
    var elNote  = document.getElementById('ty-download-note');
    if (elCo)    elCo.textContent    = data.supplier_name || 'Your company';
    if (elScore) { elScore.textContent = score.toFixed(1); elScore.style.color = color; }
    if (elTier)  { elTier.textContent  = tier;             elTier.style.color  = color; }
    if (elNote && downloaded) {
      elNote.style.display = 'block';
      elNote.textContent   = 'Your response has been downloaded as a JSON file. Please email it to ' +
        (data.mandating_company_name || 'the requesting company') + ' to complete submission.';
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  window.submitSupplierForm = submitSupplierForm;

})();
