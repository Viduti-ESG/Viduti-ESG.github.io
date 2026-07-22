/* Green Curve — AI usage/trial status banner + toast.
 * Shared across every page that calls a Claude-billed AI endpoint, so users
 * see their trial/quota status proactively instead of only on a 403/429.
 * Puts the existing (previously unused) .gc-toast CSS component to work.
 */
(function () {
  function apiBase() {
    return window._gcApiBase || localStorage.getItem('gc_api_base') || '';
  }
  function authHeaders() {
    var t = localStorage.getItem('gc_token');
    return t ? { Authorization: 'Bearer ' + t } : {};
  }
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ── Toast ────────────────────────────────────────────────────────────────
  function gcToast(message, kind) {
    kind = kind || 'info';
    var el = document.getElementById('gc-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'gc-toast';
      document.body.appendChild(el);
    }
    el.className = 'gc-toast gc-toast--' + kind;
    el.textContent = message;
    el.style.display = 'flex';
    clearTimeout(el._gcHideTimer);
    if (kind !== 'error') {
      el._gcHideTimer = setTimeout(function () { el.style.display = 'none'; }, 6000);
    }
  }
  window.gcToast = gcToast;

  // Call this from a fetch's error path (403 trial-ended / 429 quota / any
  // other failure) instead of alert() or silently doing nothing.
  window.gcShowAiError = function (err) {
    var msg = (err && err.detail) || (err && err.message) || 'Something went wrong. Please try again.';
    gcToast(msg, 'error');
  };

  // ── Proactive usage/trial banner ────────────────────────────────────────
  // containerId: an element already on the page (e.g. <div id="gc-ai-status" class="gc-ai-status-banner"></div>)
  // metrics: array of metric keys this page cares about, e.g. ['ccts_scorecard']
  // service: 'esg-site' (default — ccts_scorecard/epr_scorecard/tcfd_gap/nl_query/
  //          tcfd_pdf/generate_digest, path /api/user/ai-status) or 'gcai'
  //          (report/briefing/ghg_chat/extract_bill/esg_search, path
  //          /api/gcai/ai-status) — the two services can't share one path.
  async function renderAiStatusBanner(containerId, metrics, service) {
    var el = document.getElementById(containerId);
    var api = apiBase();
    if (!el || !api) return;
    var path = service === 'gcai' ? '/api/gcai/ai-status' : '/api/user/ai-status';
    try {
      var res = await fetch(
        api + path + '?metrics=' + encodeURIComponent((metrics || []).join(',')),
        { headers: authHeaders(), signal: AbortSignal.timeout(8000) }
      );
      if (!res.ok) return;  // banner is best-effort — never block the page on it
      var data = await res.json();

      if (data.plan === 'internal') { el.style.display = 'none'; return; }

      if (data.lapsed) {
        el.innerHTML = '<span>Your paid plan has ended'
          + (data.trial_ends_at ? ' on ' + esc(data.trial_ends_at) : '')
          + '. Email <a href="mailto:neha@greencurve.solutions">neha@greencurve.solutions</a> to renew.</span>';
        el.className = 'gc-ai-status-banner gc-ai-status-banner--warn';
        el.style.display = 'flex';
        return;
      }

      var parts = [];
      if (data.plan === 'free' && data.trial_ends_at) {
        parts.push('Free trial — ends ' + esc(data.trial_ends_at));
      } else if (data.plan === 'paid') {
        parts.push('Paid plan');
      }
      Object.keys(data.usage || {}).forEach(function (metric) {
        var u = data.usage[metric];
        if (u.limit == null) return;
        var span = (u.period && u.period.indexOf('-W') !== -1) ? 'week' : 'month';
        parts.push(u.used + '/' + u.limit + ' used this ' + span);
      });
      if (!parts.length) { el.style.display = 'none'; return; }

      el.innerHTML = '<span>' + parts.join(' · ') + '</span>'
        + (data.plan === 'free' ? ' <a href="mailto:neha@greencurve.solutions">Upgrade</a>' : '');
      el.className = 'gc-ai-status-banner';
      el.style.display = 'flex';
    } catch (e) { /* banner is best-effort — never block the page */ }
  }
  window.gcRenderAiStatusBanner = renderAiStatusBanner;
})();
