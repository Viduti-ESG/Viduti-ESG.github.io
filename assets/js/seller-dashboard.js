/* Green Curve Marketplace — seller dashboard */
(function () {
  const API = (window._gcApiBase || '');
  const $ = id => document.getElementById(id);
  function token() { return localStorage.getItem('gc_auth_token'); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

  function show(el) { el.classList.remove('hidden'); }
  function hide(el) { el.classList.add('hidden'); }
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

  const GC = {
    async createSeller() {
      const name = $('biz_name').value.trim();
      if (!name) return msg('Business name is required', 'error');
      try {
        await api('POST', '/api/market/seller', {
          business_name: name,
          gstin: $('biz_gstin').value.trim(),
          contact_phone: $('biz_phone').value.trim(),
          address: $('biz_address').value.trim(),
          description: $('biz_desc').value.trim(),
        });
        msg('Seller profile created! Your account is pending KYC review.', 'success');
        boot();
      } catch (e) { msg(e.message, 'error'); }
    },

    async addProduct() {
      const name = $('p_name').value.trim();
      if (!name) return msg('Product name is required', 'error');
      const attrs = $('p_attrs').value.split(',').map(s => s.trim()).filter(Boolean);
      try {
        await api('POST', '/api/market/seller/products', {
          name,
          description: $('p_desc').value.trim(),
          price: parseFloat($('p_price').value) || 0,
          category_id: parseInt($('p_category').value) || null,
          sustainability_attrs: attrs,
        });
        msg('Product added as a draft. Submit it for listing once ready.', 'success');
        $('p_name').value = $('p_desc').value = $('p_price').value = $('p_attrs').value = '';
        loadProducts();
      } catch (e) { msg(e.message, 'error'); }
    },

    async submitProduct(id) {
      try {
        await api('POST', '/api/market/seller/products/' + id + '/submit');
        msg('Submitted for listing approval.', 'success');
        loadProducts();
      } catch (e) { msg(e.message, 'error'); }
    },

    async uploadImage(id, input) {
      if (!input.files[0]) return;
      const fd = new FormData(); fd.append('file', input.files[0]);
      try { await upload('/api/market/seller/products/' + id + '/image', fd); msg('Image uploaded.', 'success'); loadProducts(); }
      catch (e) { msg(e.message, 'error'); }
    },

    async uploadCert() {
      const file = $('c_file').files[0];
      if (!file) return msg('Choose a certificate file', 'error');
      const fd = new FormData();
      fd.append('cert_type_id', $('c_type').value);
      fd.append('cert_number', $('c_number').value.trim());
      fd.append('issuer', $('c_issuer').value.trim());
      fd.append('issue_date', $('c_issue').value);
      fd.append('expiry_date', $('c_expiry').value);
      if ($('c_product').value) fd.append('product_id', $('c_product').value);
      fd.append('file', file);
      try {
        await upload('/api/market/seller/certificates', fd);
        msg('Certificate uploaded — pending Green Curve verification.', 'success');
        $('c_file').value = $('c_number').value = '';
        loadCerts();
      } catch (e) { msg(e.message, 'error'); }
    },
  };
  window.GC = GC;

  async function loadProducts() {
    try {
      const { products } = await api('GET', '/api/market/seller/products');
      const sel = $('c_product');
      sel.innerHTML = '<option value="">All my products (whole business)</option>' +
        products.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
      $('productList').innerHTML = products.length ? products.map(p => {
        const canSubmit = p.status === 'draft' || p.status === 'rejected';
        return `<div class="item">
          <h4>${esc(p.name)} <span class="pill ${p.status}">${p.status}</span></h4>
          <div class="meta">₹${Number(p.price).toLocaleString('en-IN')}${p.category ? ' · ' + esc(p.category) : ''}</div>
          ${p.reviewer_notes ? `<div class="meta" style="color:#b42318">Note: ${esc(p.reviewer_notes)}</div>` : ''}
          <div style="margin-top:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            ${canSubmit ? `<button class="btn btn-primary btn-sm" onclick="GC.submitProduct(${p.id})">Submit for listing</button>` : ''}
            <label class="btn btn-ghost btn-sm" style="margin:0">Add image<input type="file" accept=".png,.jpg,.jpeg,.webp" class="hidden" onchange="GC.uploadImage(${p.id}, this)"></label>
          </div>
        </div>`;
      }).join('') : '<p style="color:#789">No products yet.</p>';
    } catch (e) { $('productList').innerHTML = '<p style="color:#b42318">' + esc(e.message) + '</p>'; }
  }

  async function loadCerts() {
    try {
      const { certificates } = await api('GET', '/api/market/seller/certificates');
      $('certList').innerHTML = certificates.length ? certificates.map(c => `<div class="item">
        <h4>${esc(c.cert_type_name)} <span class="pill ${c.status}">${c.status}</span></h4>
        <div class="meta">${c.cert_number ? 'No. ' + esc(c.cert_number) + ' · ' : ''}${c.issuer ? esc(c.issuer) : ''}${c.expiry_date ? ' · expires ' + esc(c.expiry_date) : ''}</div>
        ${c.reviewer_notes ? `<div class="meta">Reviewer: ${esc(c.reviewer_notes)}</div>` : ''}
      </div>`).join('') : '<p style="color:#789">No certificates uploaded yet.</p>';
    } catch (e) { $('certList').innerHTML = '<p style="color:#b42318">' + esc(e.message) + '</p>'; }
  }

  async function loadCategories() {
    const { categories: cats } = await (await fetch(API + '/api/market/categories')).json();
    categories = cats;
    $('p_category').innerHTML = cats.map(c => `<option value="${c.id}">${esc(c.name)}${c.cert_required ? ' (cert required)' : ''}</option>`).join('');
    const { cert_types } = await (await fetch(API + '/api/market/cert-types')).json();
    $('c_type').innerHTML = cert_types.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join('');
  }

  async function boot() {
    if (!token()) { show($('loginGate')); return; }
    try {
      const { seller } = await api('GET', '/api/market/seller/me');
      if (!seller) { show($('onboard')); hide($('workspace')); return; }
      hide($('onboard')); show($('workspace'));
      const banner = $('kycBanner');
      if (seller.kyc_status !== 'approved') {
        banner.textContent = seller.kyc_status === 'rejected'
          ? 'Your seller KYC was not approved. Contact support to resolve this.'
          : 'Your seller account is pending KYC review. You can add products and certificates now; listings go live once approved.';
        show(banner);
      } else { hide(banner); }
      await loadCategories();
      loadProducts();
      loadCerts();
    } catch (e) {
      if (/auth|token|401/i.test(e.message)) { show($('loginGate')); }
      else msg(e.message, 'error');
    }
  }

  boot();
})();
