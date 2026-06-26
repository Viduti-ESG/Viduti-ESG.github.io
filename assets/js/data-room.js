/* Green Curve — ESG Data Room
 * Private workspace for storing, versioning and organising a customer's own ESG evidence.
 * DPDP: consent gate before first upload, audit-log view, full export, hard delete.
 */
(function () {
  const API = (window._gcApiBase || '');
  const $ = id => document.getElementById(id);
  function token() { return localStorage.getItem('gc_auth_token'); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
  function show(el) { el && el.classList.remove('hidden'); }
  function hide(el) { el && el.classList.add('hidden'); }
  function fmtSize(b) {
    if (!b) return '0 B';
    const u = ['B', 'KB', 'MB', 'GB']; let i = 0; let n = b;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return n.toFixed(n < 10 && i > 0 ? 1 : 0) + ' ' + u[i];
  }
  function msg(text, type) {
    const m = $('msg');
    m.textContent = text;
    m.className = 'msg show ' + (type || 'success');
    if (type === 'success') setTimeout(() => m.classList.remove('show'), 4000);
  }

  async function api(method, path, body) {
    const headers = { 'Authorization': 'Bearer ' + token() };
    const opts = { method, headers };
    if (body !== undefined) { headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    const res = await fetch(API + path, opts);
    if (res.status === 401) { localStorage.removeItem('gc_auth_token'); localStorage.removeItem('gc_auth_user'); location.href = '/login?next=/data-room'; throw new Error('Not authenticated'); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.message || 'Request failed');
    return data;
  }
  async function upload(path, formData) {
    const res = await fetch(API + path, { method: 'POST', headers: { 'Authorization': 'Bearer ' + token() }, body: formData });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.message || 'Upload failed');
    return data;
  }

  let categories = [];
  let folders = [];
  let myTeams = [];
  let currentFolder = null;   // null = all documents
  let deepLinkDoc = null;

  const GC = {
    async acceptConsent() {
      try {
        await api('POST', '/api/dataroom/consent', { accept: true });
        hide($('consentGate'));
        show($('workspace'));
        boot();
      } catch (e) { msg(e.message, 'error'); }
    },

    async createFolder() {
      const name = $('f_name').value.trim();
      if (!name) return msg('Folder name is required', 'error');
      try {
        await api('POST', '/api/dataroom/folders', { name, category: $('f_category').value });
        $('f_name').value = '';
        msg('Folder created.', 'success');
        await loadFolders();
      } catch (e) { msg(e.message, 'error'); }
    },

    async deleteFolder(id) {
      if (!confirm('Delete this folder? It must be empty.')) return;
      try { await api('DELETE', '/api/dataroom/folders/' + id); await loadFolders(); loadDocuments(); }
      catch (e) { msg(e.message, 'error'); }
    },

    selectFolder(id) {
      currentFolder = id;
      document.querySelectorAll('.folder-item').forEach(el => el.classList.toggle('active', String(el.dataset.id) === String(id)));
      $('uploadFolder').value = id == null ? '' : id;
      loadDocuments();
    },

    async uploadDoc() {
      const file = $('d_file').files[0];
      if (!file) return msg('Choose a file to upload', 'error');
      const fd = new FormData();
      fd.append('title', $('d_title').value.trim());
      fd.append('category', $('d_category').value);
      fd.append('reporting_year', $('d_year').value.trim());
      fd.append('note', $('d_note').value.trim());
      if ($('uploadFolder').value) fd.append('folder_id', $('uploadFolder').value);
      fd.append('file', file);
      try {
        await upload('/api/dataroom/documents', fd);
        $('d_file').value = $('d_title').value = $('d_note').value = '';
        msg('Document uploaded.', 'success');
        await loadFolders();
        loadDocuments();
      } catch (e) { msg(e.message, 'error'); }
    },

    async addVersion(docId, input) {
      if (!input.files[0]) return;
      const fd = new FormData();
      fd.append('file', input.files[0]);
      try { await upload('/api/dataroom/documents/' + docId + '/versions', fd); msg('New version added.', 'success'); loadDocuments(); }
      catch (e) { msg(e.message, 'error'); }
    },

    download(versionId) {
      // Authed fetch → blob (cannot use a plain <a href> because of the Bearer header).
      fetch(API + '/api/dataroom/versions/' + versionId + '/file', { headers: { 'Authorization': 'Bearer ' + token() } })
        .then(r => { if (!r.ok) throw new Error('Download failed'); const cd = r.headers.get('Content-Disposition') || ''; const m = /filename="?([^"]+)"?/.exec(cd); return r.blob().then(b => ({ b, name: m ? m[1] : 'file' })); })
        .then(({ b, name }) => { const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = name; a.click(); URL.revokeObjectURL(u); })
        .catch(e => msg(e.message, 'error'));
    },

    async deleteDoc(docId) {
      if (!confirm('Permanently delete this document and ALL its versions? This cannot be undone.')) return;
      try { await api('DELETE', '/api/dataroom/documents/' + docId); msg('Document deleted.', 'success'); await loadFolders(); loadDocuments(); }
      catch (e) { msg(e.message, 'error'); }
    },

    toggleShare(docId) {
      const box = $('share_' + docId);
      if (!box) return;
      box.classList.toggle('hidden');
      if (!box.classList.contains('hidden')) GC.loadShares(docId);
    },

    async loadShares(docId) {
      try {
        const { shares } = await api('GET', `/api/collab/resource-shares?resource_type=dataroom_doc&resource_id=${docId}`);
        const list = $('shares_' + docId);
        list.innerHTML = shares.length
          ? shares.map(s => `<span class="ver-chip">👥 ${esc(s.team)} · ${esc(s.permission)} <button onclick="GC.unshare(${docId},${s.team_id})">×</button></span>`).join('')
          : '<span style="color:#789;font-size:.8rem">Not shared yet.</span>';
      } catch (e) { /* non-owner */ }
    },

    async shareDoc(docId) {
      const teamId = parseInt($('shareteam_' + docId).value);
      if (!teamId) return msg('Create a team first on the Team page.', 'error');
      try {
        await api('POST', '/api/collab/share', { team_id: teamId, resource_type: 'dataroom_doc', resource_id: docId, permission: $('shareperm_' + docId).value });
        msg('Shared with team.', 'success');
        GC.loadShares(docId);
      } catch (e) { msg(e.message, 'error'); }
    },

    async unshare(docId, teamId) {
      try { await api('DELETE', `/api/collab/share?team_id=${teamId}&resource_type=dataroom_doc&resource_id=${docId}`); GC.loadShares(docId); }
      catch (e) { msg(e.message, 'error'); }
    },

    exportAll() {
      msg('Preparing your export…', 'success');
      fetch(API + '/api/dataroom/export', { headers: { 'Authorization': 'Bearer ' + token() } })
        .then(r => { if (!r.ok) throw new Error('Export failed'); return r.blob(); })
        .then(b => { const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = 'green-curve-dataroom-export.zip'; a.click(); URL.revokeObjectURL(u); msg('Export downloaded.', 'success'); })
        .catch(e => msg(e.message, 'error'));
    },

    async toggleAudit() {
      const box = $('auditBox');
      if (!box.classList.contains('hidden')) { hide(box); return; }
      try {
        const { entries } = await api('GET', '/api/dataroom/audit-log?limit=100');
        box.innerHTML = entries.length
          ? '<table class="audit"><tr><th>When (UTC)</th><th>Action</th><th>Detail</th><th>IP</th></tr>' +
            entries.map(e => `<tr><td>${esc(e.created_at)}</td><td>${esc(e.action)}</td><td>${esc(e.detail)}</td><td>${esc(e.ip)}</td></tr>`).join('') +
            '</table>'
          : '<p style="color:#789">No activity yet.</p>';
        show(box);
      } catch (e) { msg(e.message, 'error'); }
    },
  };
  window.GC = GC;

  function catName(slug) { const c = categories.find(x => x.slug === slug); return c ? c.name : slug; }
  function teamOptions() {
    return myTeams.length ? myTeams.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join('')
      : '<option value="">No teams — create one on the Team page</option>';
  }
  async function loadMyTeams() {
    try { const { teams } = await api('GET', '/api/collab/teams'); myTeams = teams; } catch (e) { myTeams = []; }
  }

  async function loadCategories() {
    const { categories: cats } = await (await fetch(API + '/api/dataroom/categories')).json();
    categories = cats;
    const opts = cats.map(c => `<option value="${c.slug}">${esc(c.name)}</option>`).join('');
    $('d_category').innerHTML = opts;
    $('f_category').innerHTML = opts;
  }

  async function loadFolders() {
    const { folders: fs } = await api('GET', '/api/dataroom/folders');
    folders = fs;
    const sel = $('uploadFolder');
    sel.innerHTML = '<option value="">No folder (loose)</option>' +
      fs.map(f => `<option value="${f.id}">${esc(f.name)}</option>`).join('');
    if (currentFolder != null) sel.value = currentFolder;
    $('folderList').innerHTML =
      `<div class="folder-item ${currentFolder == null ? 'active' : ''}" data-id="" onclick="GC.selectFolder(null)">📁 All documents</div>` +
      fs.map(f => `<div class="folder-item ${String(currentFolder) === String(f.id) ? 'active' : ''}" data-id="${f.id}" onclick="GC.selectFolder(${f.id})">
          📂 ${esc(f.name)} <span class="count">${f.doc_count}</span>
          <button class="x" title="Delete folder" onclick="event.stopPropagation();GC.deleteFolder(${f.id})">×</button>
        </div>`).join('');
  }

  async function loadDocuments() {
    try {
      let path = '/api/dataroom/documents';
      if (currentFolder != null) path += '?folder_id=' + currentFolder;
      const { documents } = await api('GET', path);
      if (!documents.length) { $('docList').innerHTML = '<p style="color:#789">No documents here yet. Upload your first piece of ESG evidence above.</p>'; return; }
      $('docList').innerHTML = documents.map(d => {
        const latest = d.versions[0];
        const history = d.versions.map(v =>
          `<div class="ver">
             <span>v${v.version_no} · ${esc(v.orig_name)} · ${fmtSize(v.size_bytes)} · ${esc((v.uploaded_at || '').slice(0, 10))}${v.note ? ' · ' + esc(v.note) : ''}</span>
             <button class="btn btn-ghost btn-sm" onclick="GC.download(${v.id})">Download</button>
           </div>`).join('');
        return `<div class="item">
          <div class="item-head">
            <h4>${esc(d.title)}</h4>
            <span class="pill cat">${esc(catName(d.category))}</span>
            ${d.reporting_year ? `<span class="pill year">FY ${esc(d.reporting_year)}</span>` : ''}
            <span class="pill ver-pill">${d.version_count} version${d.version_count > 1 ? 's' : ''}</span>
          </div>
          <div class="vers">${history}</div>
          <div class="item-actions">
            <label class="btn btn-ghost btn-sm" style="margin:0">Upload new version<input type="file" class="hidden" onchange="GC.addVersion(${d.id}, this)"></label>
            <button class="btn btn-ghost btn-sm" onclick="GC.toggleShare(${d.id})">Share</button>
            <button class="btn btn-danger btn-sm" onclick="GC.deleteDoc(${d.id})">Delete</button>
          </div>
          <div class="share-box hidden" id="share_${d.id}">
            <div id="shares_${d.id}" style="margin-bottom:6px"></div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
              <select id="shareteam_${d.id}" style="flex:1;min-width:120px">${teamOptions()}</select>
              <select id="shareperm_${d.id}" style="width:auto"><option value="view">View only</option><option value="edit">Can edit</option></select>
              <button class="btn btn-ghost btn-sm" onclick="GC.shareDoc(${d.id})">Share</button>
            </div>
          </div>
        </div>`;
      }).join('');
      if (deepLinkDoc) {
        const el = document.getElementById('share_' + deepLinkDoc);
        if (el) { el.closest('.item').scrollIntoView({ behavior: 'smooth', block: 'center' }); el.closest('.item').style.outline = '2px solid var(--gc-green)'; }
        deepLinkDoc = null;
      }
    } catch (e) { $('docList').innerHTML = '<p style="color:#b42318">' + esc(e.message) + '</p>'; }
  }

  async function boot() {
    deepLinkDoc = new URLSearchParams(location.search).get('doc');
    await loadCategories();
    await loadMyTeams();
    await loadFolders();
    loadDocuments();
  }

  async function start() {
    if (!token()) { show($('loginGate')); return; }
    try {
      const c = await api('GET', '/api/dataroom/consent');
      if (!c.consented) {
        $('consentText').textContent = c.consent_text;
        show($('consentGate'));
        return;
      }
      show($('workspace'));
      boot();
    } catch (e) {
      if (/auth|token|401/i.test(e.message)) show($('loginGate'));
      else msg(e.message, 'error');
    }
  }

  start();
})();
