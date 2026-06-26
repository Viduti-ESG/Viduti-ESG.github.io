/* Green Curve — BRSR Workspace
 * Account-bound, resumable, per-FY BRSR reports with completion tracking,
 * filing deadlines, status, Data Room evidence linking, and export.
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
    if (type === 'success') setTimeout(() => m.classList.remove('show'), 3500);
  }

  async function api(method, path, body) {
    const headers = { 'Authorization': 'Bearer ' + token() };
    const opts = { method, headers };
    if (body !== undefined) { headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    const res = await fetch(API + path, opts);
    if (res.status === 401) { localStorage.removeItem('gc_auth_token'); localStorage.removeItem('gc_auth_user'); location.href = '/login?next=/brsr-workspace'; throw new Error('Not authenticated'); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.message || 'Request failed');
    return data;
  }

  let schema = [];
  let current = null;       // currently open report (full object)
  let saveTimer = null;

  function daysLeft(dl) {
    if (!dl) return null;
    const d = Math.ceil((new Date(dl) - new Date()) / 86400000);
    return d;
  }
  function deadlineLabel(dl) {
    const d = daysLeft(dl);
    if (d == null) return '';
    if (d < 0) return `<span class="dl overdue">⚠ ${-d}d overdue</span>`;
    if (d <= 30) return `<span class="dl soon">⏳ ${d}d left</span>`;
    return `<span class="dl ok">${d}d left</span>`;
  }

  const GC = {
    async createReport() {
      const title = $('r_title').value.trim();
      if (!title) return msg('Give the report a title', 'error');
      try {
        const { report_id } = await api('POST', '/api/brsr/reports', {
          title, financial_year: $('r_fy').value.trim(), filing_deadline: $('r_deadline').value,
        });
        $('r_title').value = ''; $('r_fy').value = ''; $('r_deadline').value = '';
        msg('Report created.', 'success');
        await loadReports();
        GC.openReport(report_id);
      } catch (e) { msg(e.message, 'error'); }
    },

    async openReport(id) {
      try {
        const { report } = await api('GET', '/api/brsr/reports/' + id);
        current = report;
        renderEditor();
        show($('editor'));
        loadShareTeams();
        loadShares();
        loadComments();
        $('editor').scrollIntoView({ behavior: 'smooth' });
      } catch (e) { msg(e.message, 'error'); }
    },

    closeEditor() { current = null; hide($('editor')); loadReports(); },

    async deleteReport(id) {
      if (!confirm('Delete this BRSR report permanently?')) return;
      try { await api('DELETE', '/api/brsr/reports/' + id); if (current && current.id === id) GC.closeEditor(); msg('Deleted.', 'success'); loadReports(); }
      catch (e) { msg(e.message, 'error'); }
    },

    queueSave() {
      if (saveTimer) clearTimeout(saveTimer);
      $('saveState').textContent = 'Saving…';
      saveTimer = setTimeout(GC.saveNow, 800);
    },

    async saveNow() {
      if (!current) return;
      const answers = {};
      schema.forEach(sec => sec.fields.forEach(f => {
        const el = $('fld_' + f.key);
        if (el && el.value !== '') answers[f.key] = el.value;
      }));
      try {
        const r = await api('PUT', '/api/brsr/reports/' + current.id, {
          answers,
          title: $('e_title').value.trim(),
          financial_year: $('e_fy').value.trim(),
          filing_deadline: $('e_deadline').value,
          status: $('e_status').value,
        });
        current.answers = answers;
        $('saveState').textContent = '✓ Saved · ' + r.completion_pct + '% complete';
        setProgress(r.completion_pct);
      } catch (e) { $('saveState').textContent = 'Save failed'; msg(e.message, 'error'); }
    },

    exportReport() {
      if (!current) return;
      fetch(API + '/api/brsr/reports/' + current.id + '/export', { headers: { 'Authorization': 'Bearer ' + token() } })
        .then(r => { if (!r.ok) throw new Error('Export failed'); return r.blob(); })
        .then(b => { const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = 'brsr-report.json'; a.click(); URL.revokeObjectURL(u); })
        .catch(e => msg(e.message, 'error'));
    },

    async openEvidencePicker() {
      try {
        const { documents } = await api('GET', '/api/dataroom/documents');
        if (!documents.length) { msg('No Data Room documents yet. Upload evidence in the Data Room first.', 'error'); return; }
        const sel = $('ev_doc');
        sel.innerHTML = documents.map(d => `<option value="${d.id}">${esc(d.title)} (${esc(d.category)})</option>`).join('');
        show($('evPicker'));
      } catch (e) { msg(e.message, 'error'); }
    },

    async attachEvidence() {
      const docId = parseInt($('ev_doc').value);
      if (!docId) return;
      try {
        await api('POST', '/api/brsr/reports/' + current.id + '/evidence', { document_id: docId });
        hide($('evPicker'));
        const { report } = await api('GET', '/api/brsr/reports/' + current.id);
        current = report; renderEvidence();
        msg('Evidence linked.', 'success');
      } catch (e) { msg(e.message, 'error'); }
    },

    async detachEvidence(eid) {
      try {
        await api('DELETE', '/api/brsr/reports/' + current.id + '/evidence/' + eid);
        current.evidence = current.evidence.filter(x => x.id !== eid);
        renderEvidence();
      } catch (e) { msg(e.message, 'error'); }
    },

    async shareReport() {
      const teamId = parseInt($('share_team').value);
      if (!teamId) return msg('Create a team first (Team page).', 'error');
      try {
        await api('POST', '/api/collab/share', {
          team_id: teamId, resource_type: 'brsr_report', resource_id: current.id, permission: $('share_perm').value,
        });
        msg('Shared with team.', 'success');
        loadShares();
      } catch (e) { msg(e.message, 'error'); }
    },

    async unshare(teamId) {
      try {
        await api('DELETE', `/api/collab/share?team_id=${teamId}&resource_type=brsr_report&resource_id=${current.id}`);
        loadShares();
      } catch (e) { msg(e.message, 'error'); }
    },

    async addComment() {
      const body = $('c_body').value.trim();
      if (!body) return;
      try {
        await api('POST', '/api/collab/comments', { resource_type: 'brsr_report', resource_id: current.id, body });
        $('c_body').value = '';
        loadComments();
      } catch (e) { msg(e.message, 'error'); }
    },

    async delComment(id) {
      try { await api('DELETE', '/api/collab/comments/' + id); loadComments(); }
      catch (e) { msg(e.message, 'error'); }
    },
  };
  window.GC = GC;

  const me = (function () { try { return JSON.parse(localStorage.getItem('gc_auth_user') || 'null'); } catch { return null; } })();
  const myEmail = me ? me.email : '';

  async function loadShareTeams() {
    try {
      const { teams } = await api('GET', '/api/collab/teams');
      const sel = $('share_team');
      sel.innerHTML = teams.length ? teams.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join('')
        : '<option value="">No teams yet</option>';
    } catch (e) { /* non-fatal */ }
  }

  async function loadShares() {
    try {
      const { shares } = await api('GET', `/api/collab/resource-shares?resource_type=brsr_report&resource_id=${current.id}`);
      $('shareOwnerBox').classList.remove('hidden');
      $('shareList').innerHTML = shares.length
        ? shares.map(s => `<span class="chip">👥 ${esc(s.team)} · ${esc(s.permission)} <button onclick="GC.unshare(${s.team_id})">×</button></span>`).join('')
        : '<span class="savebar">Not shared yet.</span>';
    } catch (e) {
      // Non-owners cannot see/manage shares — hide the owner box for them.
      $('shareOwnerBox').classList.add('hidden');
    }
  }

  async function loadComments() {
    try {
      const { comments } = await api('GET', `/api/collab/comments?resource_type=brsr_report&resource_id=${current.id}`);
      $('commentList').innerHTML = comments.length ? comments.map(c => `
        <div class="chip" style="display:flex;width:100%;box-sizing:border-box;justify-content:space-between">
          <span><strong>${esc(c.author_email)}</strong> · ${esc((c.created_at || '').slice(0, 16))}<br>${esc(c.body)}</span>
          ${c.author_email === myEmail ? `<button onclick="GC.delComment(${c.id})">×</button>` : ''}
        </div>`).join('') : '<span class="savebar">No comments yet.</span>';
    } catch (e) { $('commentList').innerHTML = '<span class="savebar">' + esc(e.message) + '</span>'; }
  }

  function setProgress(pct) {
    $('progFill').style.width = pct + '%';
    $('progLabel').textContent = pct + '% complete';
  }

  function renderEvidence() {
    const box = $('evList');
    const ev = (current.evidence || []);
    box.innerHTML = ev.length
      ? ev.map(e => `<span class="chip">📎 ${esc(e.label || e.doc_title)} <button onclick="GC.detachEvidence(${e.id})">×</button></span>`).join('')
      : '<span style="color:#789;font-size:.85rem">No evidence linked yet.</span>';
  }

  function renderEditor() {
    $('e_title').value = current.title || '';
    $('e_fy').value = current.financial_year || '';
    $('e_deadline').value = current.filing_deadline || '';
    $('e_status').value = current.status || 'draft';
    setProgress(current.completion_pct || 0);
    $('saveState').textContent = '';

    $('sections').innerHTML = schema.map(sec => `
      <div class="sec">
        <h3>${esc(sec.title)}</h3>
        <div class="sec-grid">
          ${sec.fields.map(f => fieldHTML(f, current.answers[f.key])).join('')}
        </div>
      </div>`).join('');

    // bind autosave
    schema.forEach(sec => sec.fields.forEach(f => {
      const el = $('fld_' + f.key);
      if (el) el.addEventListener('input', GC.queueSave);
    }));
    ['e_title', 'e_fy', 'e_deadline', 'e_status'].forEach(id => $(id).addEventListener('input', GC.queueSave));
    renderEvidence();
  }

  function fieldHTML(f, val) {
    val = val == null ? '' : val;
    const req = f.required ? ' <span class="req">*</span>' : '';
    const lbl = `<label for="fld_${f.key}">${esc(f.label)}${req}</label>`;
    if (f.type === 'textarea') return `<div class="fld wide">${lbl}<textarea id="fld_${f.key}">${esc(val)}</textarea></div>`;
    if (f.type === 'select') return `<div class="fld">${lbl}<select id="fld_${f.key}"><option value="">—</option>${f.options.map(o => `<option ${o === val ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select></div>`;
    const t = (f.type === 'number' || f.type === 'percent') ? 'number' : 'text';
    return `<div class="fld">${lbl}<input id="fld_${f.key}" type="${t}" value="${esc(val)}" /></div>`;
  }

  async function loadReports() {
    const { reports } = await api('GET', '/api/brsr/reports');
    $('reportList').innerHTML = reports.length ? reports.map(r => `
      <div class="rcard" onclick="GC.openReport(${r.id})">
        <div class="rcard-top">
          <h4>${esc(r.title)}</h4>
          <span class="pill ${r.status}">${r.status.replace('_', ' ')}</span>
        </div>
        <div class="rmeta">${r.financial_year ? 'FY ' + esc(r.financial_year) + ' · ' : ''}${deadlineLabel(r.filing_deadline)}</div>
        <div class="prog"><div class="prog-fill" style="width:${r.completion_pct}%"></div></div>
        <div class="rmeta">${r.completion_pct}% complete</div>
        <button class="rdel" title="Delete" onclick="event.stopPropagation();GC.deleteReport(${r.id})">Delete</button>
      </div>`).join('') : '<p style="color:#789">No BRSR reports yet. Create one above to start your annual filing.</p>';
  }

  async function start() {
    if (!token()) { show($('loginGate')); return; }
    try {
      const s = await (await fetch(API + '/api/brsr/schema')).json();
      schema = s.sections;
      show($('workspace'));
      await loadReports();
      // Deep link: /brsr-workspace?report=ID opens that report directly (e.g. from Team page).
      const rid = new URLSearchParams(location.search).get('report');
      if (rid) GC.openReport(parseInt(rid));
    } catch (e) {
      if (/auth|token|401/i.test(e.message)) show($('loginGate'));
      else msg(e.message, 'error');
    }
  }

  start();
})();
