/* Green Curve — Monitoring & Alerts
 * One personal feed of what changed / what's due, from official & owned sources.
 */
(function () {
  const API = (window._gcApiBase || '');
  const $ = id => document.getElementById(id);
  function token() { return localStorage.getItem('gc_auth_token'); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
  function show(el) { el && el.classList.remove('hidden'); }
  function hide(el) { el && el.classList.add('hidden'); }
  function msg(text, type) {
    const m = $('msg'); m.textContent = text;
    m.className = 'msg show ' + (type || 'success');
    if (type === 'success') setTimeout(() => m.classList.remove('show'), 3000);
  }
  async function api(method, path, body) {
    const headers = { 'Authorization': 'Bearer ' + token() };
    const opts = { method, headers };
    if (body !== undefined) { headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    const res = await fetch(API + path, opts);
    if (res.status === 401) { localStorage.removeItem('gc_auth_token'); localStorage.removeItem('gc_auth_user'); location.href = '/login?next=/alerts'; throw new Error('Not authenticated'); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.message || 'Request failed');
    return data;
  }

  const TYPE_LABEL = {
    score_change: 'Score change', high_risk: 'High risk', regulatory: 'Regulatory',
    filing_deadline: 'Deadline', task_due: 'Task',
  };
  const TYPE_ICON = {
    score_change: '📈', high_risk: '⚠️', regulatory: '🏛️', filing_deadline: '⏳', task_due: '✅',
  };

  let prefs = {};

  const GC = {
    async ack() {
      try { await api('POST', '/api/alerts/ack'); msg('Marked as seen.', 'success'); load(); }
      catch (e) { msg(e.message, 'error'); }
    },
    async savePrefs() {
      const p = {};
      ['score_change', 'high_risk', 'regulatory', 'filing_deadline', 'task_due', 'digest_email'].forEach(k => {
        const el = $('pref_' + k); if (el) p[k] = el.checked;
      });
      p.digest_freq = $('pref_digest_freq').value;
      try { const r = await api('PUT', '/api/alerts/prefs', { prefs: p }); prefs = r.prefs; msg('Preferences saved.', 'success'); load(); }
      catch (e) { msg(e.message, 'error'); }
    },
    filter(type) {
      document.querySelectorAll('.fbtn').forEach(b => b.classList.toggle('active', b.dataset.t === type));
      document.querySelectorAll('.alert').forEach(el => {
        el.style.display = (type === 'all' || el.dataset.type === type) ? '' : 'none';
      });
    },
  };
  window.GC = GC;

  function renderPrefs() {
    ['score_change', 'high_risk', 'regulatory', 'filing_deadline', 'task_due', 'digest_email'].forEach(k => {
      const el = $('pref_' + k); if (el) el.checked = prefs[k] !== false && prefs[k] !== undefined ? !!prefs[k] : !!prefs[k];
      if (el) el.checked = !!prefs[k];
    });
    if ($('pref_digest_freq')) $('pref_digest_freq').value = prefs.digest_freq || 'weekly';
  }

  function alertHTML(a) {
    const sev = (a.severity || 'info');
    const ref = a.reference ? ` · <a href="${esc(a.reference)}" target="_blank" rel="noopener">source ↗</a>` : '';
    const go = a.link ? `<a class="alert-go" href="${esc(a.link)}">View →</a>` : '';
    return `<div class="alert sev-${esc(sev)} ${a.is_new ? 'is-new' : ''}" data-type="${esc(a.type)}">
      <div class="alert-icon">${TYPE_ICON[a.type] || '•'}</div>
      <div class="alert-body">
        <div class="alert-top">
          <span class="alert-title">${esc(a.title)}</span>
          ${a.is_new ? '<span class="newdot" title="New"></span>' : ''}
        </div>
        <div class="alert-detail">${esc(a.detail)}</div>
        <div class="alert-meta">${esc(TYPE_LABEL[a.type] || a.type)} · ${esc(a.source || '')}${a.date ? ' · ' + esc(a.date) : ''}${ref}</div>
      </div>
      <div class="alert-actions">${go}</div>
    </div>`;
  }

  function renderCounts(feed) {
    const counts = { all: feed.length };
    feed.forEach(a => { counts[a.type] = (counts[a.type] || 0) + 1; });
    document.querySelectorAll('.fbtn').forEach(b => {
      const t = b.dataset.t;
      const n = counts[t] || 0;
      b.querySelector('.fc').textContent = n;
      b.style.display = (t === 'all' || n > 0) ? '' : 'none';
    });
  }

  async function load() {
    try {
      const data = await api('GET', '/api/alerts/feed');
      $('newBadge').textContent = data.new_count ? `${data.new_count} new` : 'All caught up';
      $('newBadge').className = 'badge ' + (data.new_count ? 'has-new' : 'clear');
      renderCounts(data.alerts);
      $('feed').innerHTML = data.alerts.length
        ? data.alerts.map(alertHTML).join('')
        : '<div class="empty">No active alerts. Add companies to your <a href="/esg-intelligence">watchlist</a> and create BRSR reports to start monitoring.</div>';
    } catch (e) { $('feed').innerHTML = '<div class="empty">' + esc(e.message) + '</div>'; }
  }

  async function start() {
    if (!token()) { show($('loginGate')); return; }
    show($('workspace'));
    try {
      const p = await api('GET', '/api/alerts/prefs');
      prefs = p.prefs; renderPrefs();
      await load();
    } catch (e) { msg(e.message, 'error'); }
  }

  start();
})();
