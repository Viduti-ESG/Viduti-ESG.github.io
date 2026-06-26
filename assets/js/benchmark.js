/* Green Curve — Peer Benchmarking
 * "You vs your sector" — percentile, distribution, sub-dimensions, nearest peers.
 * Public data; no auth required.
 */
(function () {
  const API = (window._gcApiBase || '');
  const $ = id => document.getElementById(id);
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
  function show(el) { el && el.classList.remove('hidden'); }
  function hide(el) { el && el.classList.add('hidden'); }
  function msg(t, type) { const m = $('msg'); m.textContent = t; m.className = 'msg show ' + (type || 'error'); }
  function clearMsg() { $('msg').className = 'msg'; }

  async function get(path) {
    const res = await fetch(API + path);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Request failed');
    return data;
  }

  // lower risk = better → percentile "lower risk than X%"
  function pctColor(p) { return p >= 67 ? '#1f7a4d' : p >= 34 ? '#b06a00' : '#b42318'; }

  const GC = {
    async run() {
      const q = $('q').value.trim();
      if (!q) return msg('Enter a company name');
      clearMsg();
      $('results').innerHTML = '<p style="color:#789">Loading…</p>';
      show($('results'));
      try {
        const b = await get('/api/benchmark/company?name=' + encodeURIComponent(q));
        render(b);
        history.replaceState(null, '', '/benchmark?company=' + encodeURIComponent(b.company.company_name));
      } catch (e) { $('results').innerHTML = '<p style="color:#b42318">' + esc(e.message) + '</p>'; }
    },
  };
  window.GC = GC;

  function distBar(dist, score) {
    if (!dist || !dist.count) return '';
    const lo = dist.min, hi = dist.max, span = (hi - lo) || 1;
    const pos = Math.max(0, Math.min(100, ((score - lo) / span) * 100));
    const mark = v => Math.max(0, Math.min(100, ((v - lo) / span) * 100));
    return `<div class="distwrap">
      <div class="distbar">
        <div class="q q25" style="left:${mark(dist.p25)}%"></div>
        <div class="q qmed" style="left:${mark(dist.median)}%"></div>
        <div class="q q75" style="left:${mark(dist.p75)}%"></div>
        <div class="you" style="left:${pos}%" title="This company: ${score}"></div>
      </div>
      <div class="distlabels"><span>best ${lo}</span><span>median ${dist.median}</span><span>worst ${hi}</span></div>
    </div>`;
  }

  function render(b) {
    const co = b.company;
    const p = b.sector_percentile;
    const pTxt = p == null ? '—' : Math.round(p) + '%';
    const subRows = (b.subdimensions || []).map(d => {
      const better = d.pct_lower_risk;
      return `<tr>
        <td>${esc(d.label)}</td>
        <td class="num">${d.value}</td>
        <td class="num">${d.sector_median}</td>
        <td class="num" style="color:${better == null ? '#789' : pctColor(better)};font-weight:600">${better == null ? '—' : Math.round(better) + '%'}</td>
      </tr>`;
    }).join('');
    const peerRows = (b.peers || []).map(pr => `<tr class="${pr.is_target ? 'target' : ''}">
        <td>${esc(pr.company_name)}${pr.is_target ? ' <span class="youpill">you</span>' : ''}</td>
        <td class="num">${pr.esg_risk_score}</td>
        <td>${esc(pr.risk_tier || '')}</td>
      </tr>`).join('');

    $('results').innerHTML = `
      <div class="headline">
        <div>
          <h2>${esc(co.company_name)}</h2>
          <div class="sub">${esc(co.sector)} · ESG risk ${co.esg_risk_score} (${esc(co.risk_tier || '')})</div>
        </div>
        <div class="pctbox" style="border-color:${pctColor(p || 0)}">
          <div class="pctnum" style="color:${pctColor(p || 0)}">${pTxt}</div>
          <div class="pctlbl">lower risk than this share of<br><strong>${esc(co.sector)}</strong> peers</div>
        </div>
      </div>
      <div class="ranks">Rank <strong>#${b.sector_rank || '—'}</strong> of ${b.sector_size} in sector · lower risk than <strong>${b.overall_percentile == null ? '—' : Math.round(b.overall_percentile) + '%'}</strong> of all ${b.overall_distribution.count} companies</div>

      <h3>Where it sits in ${esc(co.sector)}</h3>
      ${distBar(b.sector_distribution, co.esg_risk_score)}

      <h3>Risk by dimension <span class="hint">(vs sector median · lower is better)</span></h3>
      <table class="bm">
        <thead><tr><th>Dimension</th><th class="num">This co.</th><th class="num">Sector median</th><th class="num">Better than</th></tr></thead>
        <tbody>${subRows || '<tr><td colspan="4" style="color:#789">No sub-dimension data.</td></tr>'}</tbody>
      </table>

      <h3>Nearest peers</h3>
      <table class="bm">
        <thead><tr><th>Company</th><th class="num">ESG risk</th><th>Tier</th></tr></thead>
        <tbody>${peerRows}</tbody>
      </table>

      <p class="disclaimer">${esc(b.disclaimer)}</p>`;
  }

  // deep link / enter key
  document.addEventListener('DOMContentLoaded', function () {
    $('q').addEventListener('keydown', e => { if (e.key === 'Enter') GC.run(); });
    const c = new URLSearchParams(location.search).get('company');
    if (c) { $('q').value = c.replace(/-/g, ' '); GC.run(); }
  });
})();
