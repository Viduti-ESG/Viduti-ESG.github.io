// Green Curve — AI ESG Query Assistant (P3-D)
// Depends on: allCompanies, esc(), scoreBar(), fmt(), openDeepDive() from esg-intelligence.js

function initAIQuery() {
  if (typeof gcRenderAiStatusBanner === 'function') gcRenderAiStatusBanner('gc-ai-status', ['nl_query']);
}

function aiqSetAndRun(q) {
  const inp = document.getElementById('aiq-input');
  if (inp) inp.value = q;
  runAIQuery();
}

async function runAIQuery() {
  const inp    = document.getElementById('aiq-input');
  const status = document.getElementById('aiq-status');
  const result = document.getElementById('aiq-result');
  const countEl= document.getElementById('aiq-result-count');
  const exEl   = document.getElementById('aiq-result-explain');
  const tbody  = document.getElementById('aiq-tbody');
  if (!inp) return;

  const q = inp.value.trim();
  if (!q) return;

  status.style.display = '';
  status.className = 'aiq-status aiq-status--loading';
  status.textContent = 'Thinking…';
  result.style.display = 'none';

  const api = window._gcApiBase || localStorage.getItem('gc_api_base') || '';

  try {
    let filters = null;
    let explain = '';

    if (api) {
      const res = await fetch(api + '/api/nl-query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q }),
        signal: AbortSignal.timeout(20000),
      });
      if (res.ok) {
        const data = await res.json();
        filters = data.filters;
        explain = data.explanation || '';
        if (typeof gcRenderAiStatusBanner === 'function') gcRenderAiStatusBanner('gc-ai-status', ['nl_query']);
      } else if (res.status === 429 || res.status === 403) {
        const e = await res.json().catch(() => ({}));
        status.className = 'aiq-status aiq-status--error';
        status.textContent = e.detail || (res.status === 429
          ? 'Rate limit reached — please wait 60 seconds and try again.'
          : 'Your AI search trial has ended.');
        return;
      }
    }

    let rows;
    if (filters) {
      rows = _aiqApplyFilters(allCompanies, filters);
    } else {
      rows = _aiqKeywordFallback(allCompanies, q);
      explain = explain || 'Backend offline — using keyword search.';
    }

    status.style.display = 'none';
    result.style.display = '';
    countEl.textContent  = `${rows.length} companies matched`;
    exEl.textContent     = explain;
    tbody.innerHTML      = rows.slice(0, 100).map(c => {
      const rb = c.risk_breakdown || {};
      const col = c.esg_risk_score <= 3 ? '#34d399' : c.esg_risk_score <= 6 ? '#fbbf24' : '#f87171';
      return `<tr style="cursor:pointer" onclick="openDeepDive('${esc(c.company_name)}')">
        <td class="company-name">${esc((c.company_name||'').slice(0,28))}${(c.company_name||'').length>28?'…':''}</td>
        <td class="sector-cell">${esc((c.sector||'').replace('Manufacturing — ','').slice(0,30))}</td>
        <td><span class="risk-badge risk-badge--${c.risk_tier}" style="color:${col}">${c.esg_risk_score}</span></td>
        <td>${scoreBar(rb.ghg_intensity)}</td>
        <td>${scoreBar(rb.water_intensity)}</td>
        <td>${scoreBar(rb.compliance_risk)}</td>
        <td>${c.revenue_crore != null ? fmt(c.revenue_crore) : '—'}</td>
      </tr>`;
    }).join('');
    if (!rows.length) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#475569;padding:30px">No companies matched this query.</td></tr>';
  } catch (e) {
    status.className = 'aiq-status aiq-status--error';
    status.textContent = 'Query failed: ' + e.message;
  }
}

function _aiqApplyFilters(data, filters) {
  let rows = [...data];
  if (filters.sector)           rows = rows.filter(c => (c.sector||'').toLowerCase().includes(filters.sector.toLowerCase()));
  if (filters.risk_tier)        rows = rows.filter(c => (c.risk_tier||'').toLowerCase() === filters.risk_tier.toLowerCase());
  if (filters.min_esg != null)  rows = rows.filter(c => (c.esg_risk_score||0) >= filters.min_esg);
  if (filters.max_esg != null)  rows = rows.filter(c => (c.esg_risk_score||0) <= filters.max_esg);
  if (filters.min_ghg != null)  rows = rows.filter(c => (c.risk_breakdown?.ghg_intensity||0) >= filters.min_ghg);
  if (filters.min_water != null)rows = rows.filter(c => (c.risk_breakdown?.water_intensity||0) >= filters.min_water);
  if (filters.min_compliance != null) rows = rows.filter(c => (c.risk_breakdown?.compliance_risk||0) >= filters.min_compliance);
  if (filters.has_scope1 === false) rows = rows.filter(c => c.financial_exposure?.scope1_emissions_tco2e == null);
  if (filters.has_scope1 === true)  rows = rows.filter(c => c.financial_exposure?.scope1_emissions_tco2e != null);
  if (filters.has_assurance)    rows = rows.filter(c => (c.governance?.brsr_assurance||'None') !== 'None');
  if (filters.sort === 'water_intensity_desc') rows.sort((a,b) => (b.risk_breakdown?.water_intensity||0) - (a.risk_breakdown?.water_intensity||0));
  else if (filters.sort === 'esg_desc')        rows.sort((a,b) => (b.esg_risk_score||0) - (a.esg_risk_score||0));
  else                                          rows.sort((a,b) => (b.esg_risk_score||0) - (a.esg_risk_score||0));
  if (filters.limit) rows = rows.slice(0, filters.limit);
  return rows;
}

function _aiqKeywordFallback(data, query) {
  const q = query.toLowerCase();
  const SECTOR_MAP = { cement:'Cement', steel:'Steel', pharma:'Pharmaceuticals', power:'Power', it:'IT', bank:'Banking', chemical:'Chemical', auto:'Automobile', textile:'Textile', paper:'Paper' };
  let rows = [...data];
  for (const [kw, sec] of Object.entries(SECTOR_MAP)) {
    if (q.includes(kw)) { rows = rows.filter(c => (c.sector||'').toLowerCase().includes(kw)); break; }
  }
  const ghgMatch   = q.match(/ghg.*?(\d+(\.\d+)?)/);
  const waterMatch = q.match(/water.*?(\d+(\.\d+)?)/);
  const esgMatch   = q.match(/esg.*?(\d+(\.\d+)?)/);
  if (ghgMatch)   rows = rows.filter(c => (c.risk_breakdown?.ghg_intensity||0)   >= parseFloat(ghgMatch[1]));
  if (waterMatch) rows = rows.filter(c => (c.risk_breakdown?.water_intensity||0) >= parseFloat(waterMatch[1]));
  if (esgMatch)   rows = rows.filter(c => (c.esg_risk_score||0)                  >= parseFloat(esgMatch[1]));
  if (q.includes('high risk') || q.includes('high-risk')) rows = rows.filter(c => c.risk_tier === 'High');
  if (q.includes('low risk')  || q.includes('low-risk'))  rows = rows.filter(c => c.risk_tier === 'Low');
  if (q.includes('assurance') || q.includes('assured')) rows = rows.filter(c => (c.governance?.brsr_assurance||'None') !== 'None');
  if (q.includes('no scope') || q.includes('scope 1') && (q.includes('missing')||q.includes('no '))) rows = rows.filter(c => c.financial_exposure?.scope1_emissions_tco2e == null);
  const topMatch = q.match(/top\s+(\d+)/);
  const limit    = topMatch ? parseInt(topMatch[1], 10) : 100;
  if (q.includes('water intensity')) rows.sort((a,b) => (b.risk_breakdown?.water_intensity||0) - (a.risk_breakdown?.water_intensity||0));
  else rows.sort((a,b) => (b.esg_risk_score||0) - (a.esg_risk_score||0));
  return rows.slice(0, limit);
}

window.runAIQuery   = runAIQuery;
window.aiqSetAndRun = aiqSetAndRun;
