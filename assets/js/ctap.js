/**
 * Green Curve — Climate Transition Plan (CTAP) builder.
 * v1: structured builder (no AI) with a Green-Curve review gate before release.
 * The field registry below MIRRORS ctap_api.py FIELDS and the writing-ctap
 * skill's questionnaire — one shared data model across form, API and skill.
 */
(function () {
  'use strict';

  // key, label, provenance (BRSR|SBTi|ASK), section, long(textarea)
  const FIELDS = [
    ['company_name', 'Legal name', 'BRSR', 'meta', false],
    ['sector', 'Primary sector / activity', 'BRSR', 'meta', false],
    ['reporting_boundary', 'Entities / sites covered by the plan', 'ASK', 'meta', false],
    ['base_year', 'Baseline year for targets', 'ASK', 'meta', false],
    ['net_zero_year', 'Net-zero / headline target year', 'SBTi', '1', false],
    ['interim_targets', 'Interim targets (year, scope, % cut)', 'SBTi', '1', true],
    ['baseline_scope1', 'Baseline Scope 1 emissions', 'BRSR', '1', false],
    ['baseline_scope2', 'Baseline Scope 2 emissions', 'BRSR', '1', false],
    ['baseline_scope3', 'Baseline Scope 3 emissions', 'BRSR', '1', false],
    ['scope3_categories', 'Material Scope 3 categories', 'ASK', '1', true],
    ['ambition_alignment', 'Ambition alignment (1.5C / validated by whom)', 'SBTi', '1', false],
    ['key_assumptions', 'Key assumptions & external factors', 'ASK', '1', true],
    ['levers', 'Planned decarbonization levers', 'ASK', '2', true],
    ['renewable_plan', 'Renewable electricity plan', 'ASK', '2', true],
    ['capex_plan', 'Transition capex plan', 'ASK', '2', true],
    ['internal_carbon_price', 'Internal carbon price', 'ASK', '2', false],
    ['rnd_low_carbon', 'Low-carbon R&D / products', 'ASK', '2', true],
    ['supplier_engagement', 'Supplier decarbonization programme', 'ASK', '3', true],
    ['industry_initiatives', 'Industry coalitions / standards', 'ASK', '3', true],
    ['policy_engagement', 'Government / public-sector engagement', 'ASK', '3', true],
    ['tracked_metrics', 'Metrics tracked against the plan', 'BRSR', '4', true],
    ['green_revenue', 'Green revenue (if tracked)', 'ASK', '4', false],
    ['credits_strategy', 'Carbon-credit strategy (residual only)', 'ASK', '4', true],
    ['board_oversight', 'Board oversight of the transition', 'ASK', '5', true],
    ['exec_accountable', 'Accountable executive(s)', 'ASK', '5', false],
    ['remuneration_link', 'Pay linked to climate KPIs', 'ASK', '5', false],
    ['skills_training', 'Climate skills & training', 'ASK', '5', true],
  ];
  const SECTIONS = [
    ['meta', 'Company & boundary', 'Who and what the plan covers.'],
    ['1', '1. Foundations', 'Your ambition and where you’re starting from.'],
    ['2', '2. Implementation strategy', 'What you’ll actually do to decarbonize.'],
    ['3', '3. Engagement strategy', 'Decarbonizing beyond your own operations.'],
    ['4', '4. Metrics & targets', 'How you’ll measure progress.'],
    ['5', '5. Governance', 'Who is accountable for delivery.'],
  ];
  const SECTION_TITLE = Object.fromEntries(SECTIONS.map(s => [s[0], s[1]]));
  const CAVEAT = 'Draft prepared from company-provided data. All forward-looking ' +
    'statements are the company’s commitments, subject to review and approval ' +
    'and to change. Not assured; not a statement of regulatory compliance.';

  let currentId = null;
  let currentStatus = null;

  const $ = id => document.getElementById(id);

  function apiBase() { return localStorage.getItem('gc_api_base') || ''; }

  async function api(method, path, body) {
    const headers = { 'Content-Type': 'application/json' };
    const t = gcAuth.getToken();
    if (t) headers['Authorization'] = 'Bearer ' + t;
    const opts = { method, headers };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(apiBase() + path, opts);
    if (res.status === 401) { gcAuth.logout(); return null; }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.message || 'Request failed');
    return data;
  }

  function toast(text, kind) {
    const m = $('msg');
    m.textContent = text;
    m.className = 'msg show ' + (kind || 'success');
    if (kind !== 'error') setTimeout(() => { m.className = 'msg'; }, 4000);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ── Views ──────────────────────────────────────────────────────────────────
  function show(view) {
    ['listView', 'editorView', 'reviewView'].forEach(v => $(v).classList.add('hidden'));
    $(view).classList.remove('hidden');
  }

  // ── Form ───────────────────────────────────────────────────────────────────
  function buildForm() {
    const host = $('formSections');
    host.innerHTML = '';
    SECTIONS.forEach(([sid, title, note]) => {
      const sec = document.createElement('div');
      sec.className = 'fsec';
      sec.innerHTML = '<h3>' + esc(title) + '</h3><p class="fsec-note">' + esc(note) + '</p>';
      const grid = document.createElement('div');
      FIELDS.filter(f => f[3] === sid).forEach(([key, label, prov, , long]) => {
        const wrap = document.createElement('div');
        wrap.innerHTML =
          '<label for="f_' + key + '">' + esc(label) +
          '<span class="prov ' + prov + '">' + prov + '</span></label>' +
          (long
            ? '<textarea id="f_' + key + '"></textarea>'
            : '<input id="f_' + key + '" type="text" />');
        grid.appendChild(wrap);
      });
      sec.appendChild(grid);
      host.appendChild(sec);
    });
    host.addEventListener('input', renderPreview);
  }

  function fillForm(answers) {
    FIELDS.forEach(([key]) => {
      const el = $('f_' + key);
      if (el) el.value = (answers && answers[key] != null) ? answers[key] : '';
    });
  }

  function collect() {
    const out = {};
    FIELDS.forEach(([key]) => {
      const el = $('f_' + key);
      if (el && el.value.trim()) out[key] = el.value.trim();
    });
    return out;
  }

  // ── Preview (mirrors server assemble) ───────────────────────────────────────
  function renderPreview() {
    const a = collect();
    const company = a.company_name || '[GAP: company_name]';
    let html = '<h3 style="margin-top:0;">' + esc(company) + ' — Climate Transition Action Plan</h3>';
    html += '<p class="pv-prov" style="font-style:italic;">' + esc(CAVEAT) + '</p>';
    const gaps = [];
    SECTIONS.forEach(([sid, title]) => {
      html += '<h3>' + esc(sid === 'meta' ? 'Company & boundary' : title) + '</h3>';
      FIELDS.filter(f => f[3] === sid).forEach(([key, label, prov]) => {
        const v = a[key];
        if (v) {
          html += '<div class="pv-item"><b>' + esc(label) + ':</b> ' + esc(v) +
            ' <span class="pv-prov">(' + prov + ')</span></div>';
        } else {
          html += '<div class="pv-item pv-gap">[GAP: ' + key + '] — ' + esc(label) + '</div>';
          gaps.push([key, label]);
        }
      });
    });
    $('previewBox').innerHTML = html;

    let gs = '';
    if (gaps.length) {
      gs = '<b style="font-size:.86rem;color:#b42318;">' + gaps.length +
        ' open item' + (gaps.length > 1 ? 's' : '') + '</b> to complete before this plan is final:<br>';
      gs += gaps.map(g => '<span class="gapchip">' + esc(g[0]) + '</span>').join('');
    } else {
      gs = '<b style="color:#1f7a4d;">No open items — ready to submit for review.</b>';
    }
    $('gapSummary').innerHTML = gs;
  }

  function updateActions() {
    const editable = currentStatus === null || currentStatus === 'draft' || currentStatus === 'changes_requested';
    const released = currentStatus === 'released';
    $('btnSaveDraft').classList.toggle('hidden', !editable);
    $('btnSubmit').classList.toggle('hidden', !editable);
    $('btnDownloadMd').classList.toggle('hidden', !released);
    $('btnDownloadHtml').classList.toggle('hidden', !released);
    // Disable form inputs when not editable (in review / released = read-only).
    FIELDS.forEach(([key]) => { const el = $('f_' + key); if (el) el.disabled = !editable; });
    $('btnPrefill').disabled = !editable;

    const nb = $('noteBanner');
    nb.innerHTML = '';
    if (currentStatus === 'changes_requested' && lastNote) {
      nb.innerHTML = '<div class="note-banner changes"><b>Changes requested by Green Curve:</b> ' + esc(lastNote) + '</div>';
    } else if (currentStatus === 'in_review' || currentStatus === 'submitted') {
      nb.innerHTML = '<div class="note-banner changes" style="background:#fff3e0;color:#8a5a00;border-color:#f0d98a;">This plan is with Green Curve for review. You’ll be able to edit or download it once the review is complete.</div>';
    } else if (released) {
      nb.innerHTML = '<div class="note-banner released"><b>Released.</b> Green Curve has reviewed this plan. You can download it below. Remember: the forward-looking commitments in it are your company’s to own.' + (lastNote ? ' Reviewer note: ' + esc(lastNote) : '') + '</div>';
    }
  }

  let lastNote = '';

  // ── CRUD ────────────────────────────────────────────────────────────────────
  async function openEditor(id) {
    currentId = id || null;
    currentStatus = null;
    lastNote = '';
    buildForm();
    $('prefillMsg').className = 'msg';
    $('prefillCompany').value = '';
    if (id) {
      const d = await api('GET', '/api/ctap/' + id);
      if (!d) return;
      currentStatus = d.status;
      lastNote = d.review_note || '';
      fillForm(d.answers);
      $('editorTitle').textContent = (d.company_name || 'Transition plan') + ' — ' + prettyStatus(d.status);
    } else {
      fillForm({});
      $('editorTitle').textContent = 'New transition plan';
    }
    renderPreview();
    updateActions();
    show('editorView');
  }

  async function save(submit) {
    const answers = collect();
    const body = {
      company_name: answers.company_name || '',
      sector: answers.sector || '',
      answers, submit: !!submit,
    };
    try {
      let d;
      if (currentId) d = await api('PUT', '/api/ctap/' + currentId, body);
      else d = await api('POST', '/api/ctap', body);
      if (!d) return;
      currentId = d.id;
      currentStatus = d.status;
      $('previewBox') && renderServerPreview(d.assembled);
      updateActions();
      toast(submit
        ? 'Submitted to Green Curve for review. You’ll be notified once it’s released.'
        : 'Draft saved.', 'success');
      await loadDrafts();
    } catch (e) { toast(e.message, 'error'); }
  }

  function renderServerPreview(a) {
    if (!a || !a.sections) return renderPreview();
    let html = '<h3 style="margin-top:0;">' + esc(a.title) + '</h3>';
    html += '<p class="pv-prov" style="font-style:italic;">' + esc(a.caveat) + '</p>';
    html += sectionHtml('Company & boundary', a.meta);
    (a.sections || []).forEach(s => { html += sectionHtml(s.id + '. ' + s.title, s.items); });
    $('previewBox').innerHTML = html;
    const gaps = a.gaps || [];
    $('gapSummary').innerHTML = gaps.length
      ? '<b style="font-size:.86rem;color:#b42318;">' + gaps.length + ' open item' + (gaps.length > 1 ? 's' : '') + '</b> remaining:<br>' + gaps.map(g => '<span class="gapchip">' + esc(g.key) + '</span>').join('')
      : '<b style="color:#1f7a4d;">No open items.</b>';
  }
  function sectionHtml(title, items) {
    let h = '<h3>' + esc(title) + '</h3>';
    (items || []).forEach(it => {
      if (it.value) h += '<div class="pv-item"><b>' + esc(it.label) + ':</b> ' + esc(it.value) + ' <span class="pv-prov">(' + esc(it.provenance) + ')</span></div>';
      else h += '<div class="pv-item pv-gap">[GAP: ' + esc(it.key) + '] — ' + esc(it.label) + '</div>';
    });
    return h;
  }

  async function prefill() {
    const name = $('prefillCompany').value.trim();
    if (!name) return;
    const pm = $('prefillMsg');
    try {
      const d = await api('GET', '/api/ctap/prefill?company=' + encodeURIComponent(name));
      if (!d) return;
      // Only fill empty fields — never clobber what the user already typed.
      Object.entries(d.prefill || {}).forEach(([k, v]) => {
        const el = $('f_' + k);
        if (el && !el.value.trim()) el.value = v;
      });
      renderPreview();
      const n = Object.keys(d.prefill || {}).length;
      pm.textContent = n
        ? 'Pulled ' + n + ' field(s) from ' + d.company_name + '’s BRSR data. Absolute Scope 1/2/3 aren’t in our dataset — enter those from your filing.'
        : 'Found ' + d.company_name + ' but no auto-fillable fields.';
      pm.className = 'msg show success';
    } catch (e) {
      pm.textContent = e.message;
      pm.className = 'msg show error';
    }
  }

  async function download(fmt) {
    if (!currentId) return;
    try {
      const d = await api('GET', '/api/ctap/' + currentId + '/download?format=' + fmt);
      if (!d) return;
      const blob = new Blob([d.content], { type: d.content_type });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = d.filename;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) { toast(e.message, 'error'); }
  }

  // ── List ────────────────────────────────────────────────────────────────────
  function prettyStatus(s) {
    return { draft: 'Draft', submitted: 'Submitted', in_review: 'In review', changes_requested: 'Changes requested', released: 'Released' }[s] || s;
  }
  async function loadDrafts() {
    const d = await api('GET', '/api/ctap');
    if (!d) return;
    const host = $('draftList');
    if (!d.drafts.length) {
      host.innerHTML = '<p style="color:#789;font-size:.9rem;">No plans yet. Start one with <b>+ New plan</b>.</p>';
      return;
    }
    host.innerHTML = '<div class="rgrid">' + d.drafts.map(r =>
      '<div class="rcard">' +
      '<div style="display:flex;justify-content:space-between;gap:8px;align-items:flex-start;">' +
      '<h4>' + esc(r.company_name || 'Untitled plan') + '</h4>' +
      '<span class="pill ' + r.status + '">' + prettyStatus(r.status) + '</span></div>' +
      '<div class="rmeta">' + esc(r.sector || '—') + ' · ' + r.gap_count + ' open item' + (r.gap_count === 1 ? '' : 's') + '</div>' +
      '<div class="rmeta">Updated ' + esc((r.updated_at || '').slice(0, 10)) + '</div>' +
      '<div class="rcard-actions">' +
      '<button class="btn btn-ghost btn-sm" data-open="' + r.id + '">Open</button>' +
      '<button class="rdel" data-del="' + r.id + '">Delete</button></div>' +
      '</div>'
    ).join('') + '</div>';
    host.querySelectorAll('[data-open]').forEach(b => b.onclick = () => openEditor(+b.dataset.open));
    host.querySelectorAll('[data-del]').forEach(b => b.onclick = () => del(+b.dataset.del));
  }
  async function del(id) {
    if (!confirm('Delete this transition plan? This cannot be undone.')) return;
    try { await api('DELETE', '/api/ctap/' + id); await loadDrafts(); toast('Plan deleted.'); }
    catch (e) { toast(e.message, 'error'); }
  }

  // ── Admin review ────────────────────────────────────────────────────────────
  let reviewId = null;
  async function loadQueue() {
    const d = await api('GET', '/api/ctap/admin/queue');
    if (!d) return;
    $('queueCount').textContent = d.queue.length;
    const host = $('adminQueue');
    if (!d.queue.length) { host.innerHTML = '<p style="color:#789;font-size:.9rem;">Nothing waiting for review.</p>'; return; }
    host.innerHTML = '<div class="rgrid">' + d.queue.map(r =>
      '<div class="rcard"><div style="display:flex;justify-content:space-between;gap:8px;">' +
      '<h4>' + esc(r.company_name || 'Untitled') + '</h4><span class="pill ' + r.status + '">' + prettyStatus(r.status) + '</span></div>' +
      '<div class="rmeta">' + esc(r.user_email) + '</div>' +
      '<div class="rmeta">' + r.gap_count + ' open items · ' + esc((r.updated_at || '').slice(0, 10)) + '</div>' +
      '<div class="rcard-actions"><button class="btn btn-primary btn-sm" data-review="' + r.id + '">Review</button></div></div>'
    ).join('') + '</div>';
    host.querySelectorAll('[data-review]').forEach(b => b.onclick = () => openReview(+b.dataset.review));
  }
  async function openReview(id) {
    reviewId = id;
    const d = await api('GET', '/api/ctap/admin/' + id);
    if (!d) return;
    $('reviewTitle').textContent = (d.company_name || 'Untitled') + ' — ' + prettyStatus(d.status);
    $('reviewMeta').textContent = 'Submitted by ' + d.user_email + ' · ' + d.gap_count + ' open items';
    const a = d.assembled || {};
    $('reviewGaps').innerHTML = (a.gaps || []).length
      ? '<b style="color:#b42318;font-size:.85rem;">Open items:</b> ' + a.gaps.map(g => '<span class="gapchip">' + esc(g.key) + '</span>').join('')
      : '<b style="color:#1f7a4d;">No open items.</b>';
    let html = '<p class="pv-prov" style="font-style:italic;">' + esc(a.caveat || '') + '</p>';
    html += sectionHtml('Company & boundary', a.meta);
    (a.sections || []).forEach(s => { html += sectionHtml(s.id + '. ' + s.title, s.items); });
    $('reviewPreview').innerHTML = html;
    $('reviewNote').value = d.review_note || '';
    show('reviewView');
  }
  async function review(action) {
    const note = $('reviewNote').value.trim();
    if (action === 'request_changes' && !note) { toast('Add a note for the client before requesting changes.', 'error'); return; }
    try {
      await api('POST', '/api/ctap/admin/' + reviewId + '/review', { action, note });
      toast('Done.');
      await loadQueue();
      show('listView');
    } catch (e) { toast(e.message, 'error'); }
  }

  // ── Init ────────────────────────────────────────────────────────────────────
  function bind() {
    $('btnNew').onclick = () => openEditor(null);
    $('btnBack').onclick = () => { show('listView'); loadDrafts(); };
    $('btnSaveDraft').onclick = () => save(false);
    $('btnSubmit').onclick = () => save(true);
    $('btnPrefill').onclick = prefill;
    $('btnDownloadMd').onclick = () => download('md');
    $('btnDownloadHtml').onclick = () => download('html');
    $('btnReviewBack').onclick = () => show('listView');
    $('btnStart').onclick = () => review('start');
    $('btnRequestChanges').onclick = () => review('request_changes');
    $('btnRelease').onclick = () => review('release');
    $('prefillCompany').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); prefill(); } });
  }

  async function init() {
    if (!gcAuth.isLoggedIn()) {
      $('loginGate').classList.remove('hidden');
      return;
    }
    $('app').classList.remove('hidden');
    bind();
    show('listView');
    await loadDrafts();
    const user = gcAuth.getUser();
    if (user && user.role === 'admin') {
      $('adminPanel').classList.remove('hidden');
      await loadQueue();
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
