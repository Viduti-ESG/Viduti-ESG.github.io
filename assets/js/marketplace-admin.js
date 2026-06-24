/* Green Curve Marketplace — admin verification console */
(function () {
  const API = (window._gcApiBase || '');
  const $ = id => document.getElementById(id);
  function token() { return localStorage.getItem('gc_auth_token'); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

  async function api(method, path, body) {
    const headers = { 'Authorization': 'Bearer ' + token() };
    const opts = { method, headers };
    if (body !== undefined) { headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    const res = await fetch(API + path, opts);
    if (res.status === 401 || res.status === 403) throw new Error('forbidden');
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.message || 'Request failed');
    return data;
  }

  const ADM = {
    tab(name) {
      document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
      document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + name));
      if (name === 'certs') loadCerts();
      if (name === 'kyc') loadKyc();
      if (name === 'products') loadProducts();
    },

    async aiReview(certId, btn) {
      btn.disabled = true; btn.textContent = 'Reading certificate…';
      try {
        const { ai } = await api('POST', '/api/market/admin/certificates/' + certId + '/ai-review');
        const box = $('ai-' + certId);
        const ex = ai.extracted || {};
        box.style.display = 'block';
        box.innerHTML = `
          <div>AI recommendation: <span class="ai-rec ${esc(ai.recommendation)}">${esc(ai.recommendation)}</span>
            ${ai.confidence != null ? '· confidence ' + Math.round(ai.confidence * 100) + '%' : ''}</div>
          <div class="meta">Extracted — issuer: ${esc(ex.issuer || '—')}, no.: ${esc(ex.cert_number || '—')}, holder: ${esc(ex.holder || '—')}, issued: ${esc(ex.issue_date || '—')}, expires: ${esc(ex.expiry_date || '—')}</div>
          <div class="meta">Matches claim: ${ai.matches_claim ? 'yes' : 'no'} · Expired: ${ai.is_expired ? 'yes' : 'no'}</div>
          ${(ai.reasons || []).length ? '<ul style="margin:6px 0 0;padding-left:18px">' + ai.reasons.map(r => '<li>' + esc(r) + '</li>').join('') + '</ul>' : ''}`;
      } catch (e) {
        alert('AI review failed: ' + e.message + '\n\nYou can still review the document manually.');
      } finally { btn.disabled = false; btn.textContent = '🤖 AI review'; }
    },

    async decideCert(certId, decision) {
      const notes = ($('notes-' + certId) || {}).value || '';
      try { await api('POST', '/api/market/admin/certificates/' + certId + '/decision', { decision, notes }); loadCerts(); }
      catch (e) { alert(e.message); }
    },

    async decideKyc(sellerId, decision) {
      try { await api('POST', '/api/market/admin/sellers/' + sellerId + '/kyc', { decision }); loadKyc(); }
      catch (e) { alert(e.message); }
    },

    async decideProduct(productId, decision) {
      const notes = ($('pnotes-' + productId) || {}).value || '';
      try { await api('POST', '/api/market/admin/products/' + productId + '/decision', { decision, notes }); loadProducts(); }
      catch (e) { alert(e.message); }
    },
  };
  window.ADM = ADM;

  async function loadCerts() {
    const el = $('panel-certs');
    try {
      const { queue } = await api('GET', '/api/market/admin/verification-queue');
      el.innerHTML = queue.length ? queue.map(c => `
        <div class="item">
          <h3>${esc(c.cert_type_name)} <span class="pill">${esc(c.seller)}</span></h3>
          <div class="meta">${c.cert_number ? 'No. ' + esc(c.cert_number) + ' · ' : ''}${c.issuer ? esc(c.issuer) + ' · ' : ''}${c.expiry_date ? 'expires ' + esc(c.expiry_date) : 'no expiry given'}</div>
          <div class="meta">${c.product_name ? 'Product: ' + esc(c.product_name) : 'Applies to whole business'}</div>
          <a class="btn-link" href="${API}/api/market/seller/certificates/${c.id}/file" target="_blank" onclick="event.preventDefault(); window.ADM.openDoc(${c.id})">📄 View document</a>
          <div class="ai-box" id="ai-${c.id}" style="display:none"></div>
          <textarea class="notes" id="notes-${c.id}" placeholder="Reviewer notes (shown to seller if rejected)"></textarea>
          <div class="actions">
            <button class="btn btn-ai" onclick="ADM.aiReview(${c.id}, this)">🤖 AI review</button>
            <button class="btn btn-approve" onclick="ADM.decideCert(${c.id}, 'approve')">✓ Verify</button>
            <button class="btn btn-reject" onclick="ADM.decideCert(${c.id}, 'reject')">✕ Reject</button>
          </div>
        </div>`).join('') : '<div class="empty">No certificates awaiting review. 🎉</div>';
    } catch (e) { gate(e); }
  }

  // Open the private cert document with the auth header (can't link directly).
  ADM.openDoc = async function (certId) {
    try {
      const res = await fetch(API + '/api/market/seller/certificates/' + certId + '/file', { headers: { 'Authorization': 'Bearer ' + token() } });
      if (!res.ok) throw new Error('Could not load document');
      const blob = await res.blob();
      window.open(URL.createObjectURL(blob), '_blank');
    } catch (e) { alert(e.message); }
  };

  async function loadKyc() {
    const el = $('panel-kyc');
    try {
      const { sellers } = await api('GET', '/api/market/admin/sellers');
      el.innerHTML = sellers.length ? sellers.map(s => `
        <div class="item">
          <h3>${esc(s.business_name)} <span class="pill">${esc(s.kyc_status)}</span></h3>
          <div class="meta">${esc(s.email)}${s.gstin ? ' · GSTIN ' + esc(s.gstin) : ''}${s.contact_phone ? ' · ' + esc(s.contact_phone) : ''}</div>
          <div class="meta">${esc(s.address || '')}</div>
          <div class="meta">${esc(s.description || '')}</div>
          ${s.kyc_status !== 'approved' ? `<div class="actions">
            <button class="btn btn-approve" onclick="ADM.decideKyc(${s.id}, 'approve')">✓ Approve KYC</button>
            <button class="btn btn-reject" onclick="ADM.decideKyc(${s.id}, 'reject')">✕ Reject</button></div>` : ''}
        </div>`).join('') : '<div class="empty">No sellers yet.</div>';
    } catch (e) { gate(e); }
  }

  async function loadProducts() {
    const el = $('panel-products');
    try {
      const { products } = await api('GET', '/api/market/admin/products/pending');
      el.innerHTML = products.length ? products.map(p => `
        <div class="item">
          <h3>${esc(p.name)} <span class="pill">${esc(p.seller)}</span></h3>
          <div class="meta">₹${Number(p.price).toLocaleString('en-IN')}${p.category ? ' · ' + esc(p.category) : ''}</div>
          <div class="meta">${esc(p.description || '')}</div>
          <textarea class="notes" id="pnotes-${p.id}" placeholder="Reviewer notes (shown to seller if rejected)"></textarea>
          <div class="actions">
            <button class="btn btn-approve" onclick="ADM.decideProduct(${p.id}, 'approve')">✓ List it</button>
            <button class="btn btn-reject" onclick="ADM.decideProduct(${p.id}, 'reject')">✕ Reject</button>
          </div>
        </div>`).join('') : '<div class="empty">No products awaiting listing approval.</div>';
    } catch (e) { gate(e); }
  }

  function gate(e) {
    if (e.message === 'forbidden') { $('gate').style.display = 'block'; $('app').style.display = 'none'; }
  }

  // Boot
  if (!token()) { $('gate').style.display = 'block'; }
  else { $('app').style.display = 'block'; loadCerts(); }
})();
