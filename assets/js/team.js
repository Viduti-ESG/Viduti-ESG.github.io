/* Green Curve — Team & Collaboration
 * Manage teams, members & roles, see resources shared with you, and your assigned tasks.
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
    if (res.status === 401) { location.href = '/login?next=/team'; throw new Error('Not authenticated'); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.message || 'Request failed');
    return data;
  }

  let teams = [];
  let currentTeam = null;
  let myRole = null;

  const GC = {
    async createTeam() {
      const name = $('t_name').value.trim();
      if (!name) return msg('Team name is required', 'error');
      try {
        const { team_id } = await api('POST', '/api/collab/teams', { name });
        $('t_name').value = '';
        msg('Team created.', 'success');
        await loadTeams(team_id);
      } catch (e) { msg(e.message, 'error'); }
    },

    async selectTeam(id) {
      currentTeam = teams.find(t => t.id === id) || null;
      myRole = currentTeam ? currentTeam.role : null;
      document.querySelectorAll('.team-tab').forEach(el => el.classList.toggle('active', String(el.dataset.id) === String(id)));
      if (!currentTeam) { hide($('teamDetail')); return; }
      show($('teamDetail'));
      $('detailName').textContent = currentTeam.name;
      $('myRoleBadge').textContent = 'You: ' + currentTeam.role;
      const canManage = (myRole === 'owner' || myRole === 'admin');
      $('inviteBox').classList.toggle('hidden', !canManage);
      await loadMembers();
    },

    async invite() {
      const email = $('i_email').value.trim();
      if (!email) return msg('Enter an email to invite', 'error');
      try {
        const r = await api('POST', `/api/collab/teams/${currentTeam.id}/invite`, { email, role: $('i_role').value });
        $('i_email').value = '';
        msg(r.status === 'active' ? 'Member added.' : 'Invite recorded — they join when they sign in with that email.', 'success');
        loadMembers();
      } catch (e) { msg(e.message, 'error'); }
    },

    async changeRole(memberId, role) {
      try { await api('PUT', `/api/collab/teams/${currentTeam.id}/members/${memberId}/role`, { role }); msg('Role updated.', 'success'); loadMembers(); }
      catch (e) { msg(e.message, 'error'); loadMembers(); }
    },

    async removeMember(memberId) {
      if (!confirm('Remove this member from the team?')) return;
      try { await api('DELETE', `/api/collab/teams/${currentTeam.id}/members/${memberId}`); loadMembers(); }
      catch (e) { msg(e.message, 'error'); }
    },

    async setTask(id, status) {
      try { await api('PUT', '/api/collab/tasks/' + id, { status }); loadMyTasks(); }
      catch (e) { msg(e.message, 'error'); }
    },
  };
  window.GC = GC;

  async function loadMembers() {
    try {
      const { members } = await api('GET', `/api/collab/teams/${currentTeam.id}/members`);
      const canManage = (myRole === 'owner' || myRole === 'admin');
      $('memberList').innerHTML = members.map(m => {
        const who = m.user_email
          ? `${esc(m.user_name || m.user_email)} <span class="muted">${esc(m.user_email)}</span>`
          : `${esc(m.invited_email)} <span class="pill invited">invited</span>`;
        let roleCell;
        if (canManage && m.role !== 'owner') {
          roleCell = `<select onchange="GC.changeRole(${m.id}, this.value)">
            ${['admin', 'editor', 'viewer'].map(r => `<option ${r === m.role ? 'selected' : ''}>${r}</option>`).join('')}
          </select>`;
        } else {
          roleCell = `<span class="pill role">${esc(m.role)}</span>`;
        }
        const rm = (canManage && m.role !== 'owner') ? `<button class="link-del" onclick="GC.removeMember(${m.id})">remove</button>` : '';
        return `<tr><td>${who}</td><td>${roleCell}</td><td>${rm}</td></tr>`;
      }).join('');
    } catch (e) { msg(e.message, 'error'); }
  }

  async function loadSharedWithMe() {
    try {
      const { documents, reports } = await api('GET', '/api/collab/shared-with-me');
      const docHtml = documents.map(d =>
        `<li><a href="/data-room?doc=${d.id}">📄 ${esc(d.title)}</a> <span class="muted">${esc(d.category)} · ${esc(d.permission)} · from ${esc(d.owner)} (${esc(d.team)})</span></li>`).join('');
      const repHtml = reports.map(r =>
        `<li><a href="/brsr-workspace?report=${r.id}">📋 ${esc(r.title)}</a> <span class="muted">${r.completion_pct}% · ${esc(r.permission)} · from ${esc(r.owner)} (${esc(r.team)})</span></li>`).join('');
      const out = docHtml + repHtml;
      $('sharedList').innerHTML = out || '<p class="muted">Nothing shared with you yet. When a teammate shares a document or BRSR report, it appears here.</p>';
    } catch (e) { $('sharedList').innerHTML = '<p class="muted">' + esc(e.message) + '</p>'; }
  }

  async function loadMyTasks() {
    try {
      const { tasks } = await api('GET', '/api/collab/tasks?mine=1');
      $('taskList').innerHTML = tasks.length ? tasks.map(t => `
        <div class="task ${t.status}">
          <div>
            <strong>${esc(t.title)}</strong>
            ${t.due_date ? `<span class="muted"> · due ${esc(t.due_date)}</span>` : ''}
            <span class="muted"> · by ${esc(t.created_email)}</span>
          </div>
          <select onchange="GC.setTask(${t.id}, this.value)">
            ${['open', 'doing', 'done'].map(s => `<option ${s === t.status ? 'selected' : ''}>${s}</option>`).join('')}
          </select>
        </div>`).join('') : '<p class="muted">No tasks assigned to you.</p>';
    } catch (e) { $('taskList').innerHTML = '<p class="muted">' + esc(e.message) + '</p>'; }
  }

  async function loadTeams(selectId) {
    const { teams: ts } = await api('GET', '/api/collab/teams');
    teams = ts;
    $('teamTabs').innerHTML = ts.length ? ts.map(t =>
      `<button class="team-tab" data-id="${t.id}" onclick="GC.selectTeam(${t.id})">${esc(t.name)} <span class="muted">${t.member_count}</span></button>`).join('')
      : '<span class="muted">No teams yet. Create one to start collaborating.</span>';
    if (ts.length) GC.selectTeam(selectId || ts[0].id);
    else hide($('teamDetail'));
  }

  async function start() {
    if (!token()) { show($('loginGate')); return; }
    try {
      show($('workspace'));
      await loadTeams();
      loadSharedWithMe();
      loadMyTasks();
    } catch (e) {
      if (/auth|token|401/i.test(e.message)) show($('loginGate'));
      else msg(e.message, 'error');
    }
  }

  start();
})();
