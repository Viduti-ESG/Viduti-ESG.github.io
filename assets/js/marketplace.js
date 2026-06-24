/* Green Curve Marketplace — public browse page */
(function () {
  const API = (window._gcApiBase || '');
  const grid = document.getElementById('grid');
  const searchEl = document.getElementById('search');
  const catEl = document.getElementById('category');
  const verEl = document.getElementById('verifiedOnly');
  let debounce;

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
  function money(p, c) { return (c || 'INR') === 'INR' ? '₹' + Number(p).toLocaleString('en-IN') : (c + ' ' + p); }

  function badgeHtml(b) {
    const state = b.state === 'verified' ? 'verified' : (b.state === 'expired' ? 'expired' : 'pending');
    const tick = state === 'verified' ? '✓ ' : '';
    return `<span class="badge ${state}" title="${esc(b.issuer || '')}">${tick}${esc(b.label)}</span>`;
  }

  function cardHtml(p) {
    const img = p.image_url
      ? `<div class="card__img" style="background-image:url('${esc(p.image_url)}')"></div>`
      : `<div class="card__img">No image</div>`;
    const badges = (p.badges || []).filter(b => b.state === 'verified').slice(0, 3).map(badgeHtml).join('');
    return `<div class="card" onclick="window.__openProduct(${p.id})">
      ${img}
      <div class="card__body">
        <div class="badges">${badges}</div>
        <div class="card__name">${esc(p.name)}</div>
        <div class="card__seller">by ${esc(p.seller)}${p.category ? ' · ' + esc(p.category) : ''}</div>
        <div class="card__price">${money(p.price, p.currency)}</div>
      </div>
    </div>`;
  }

  async function load() {
    const params = new URLSearchParams();
    if (catEl.value) params.set('category', catEl.value);
    if (searchEl.value.trim()) params.set('q', searchEl.value.trim());
    if (verEl.checked) params.set('verified_only', '1');
    grid.innerHTML = '<div class="empty">Loading…</div>';
    try {
      const res = await fetch(API + '/api/market/products?' + params.toString());
      const data = await res.json();
      const products = data.products || [];
      grid.innerHTML = products.length
        ? products.map(cardHtml).join('')
        : '<div class="empty">No products found. Be the first to <a href="/seller-dashboard">list one</a>.</div>';
    } catch (e) {
      grid.innerHTML = '<div class="empty">Could not load products.</div>';
    }
  }

  async function loadCategories() {
    try {
      const res = await fetch(API + '/api/market/categories');
      const data = await res.json();
      (data.categories || []).forEach(c => {
        const o = document.createElement('option');
        o.value = c.slug; o.textContent = c.name;
        catEl.appendChild(o);
      });
    } catch (_) {}
  }

  window.__openProduct = async function (id) {
    const modalBg = document.getElementById('modalBg');
    const modal = document.getElementById('modal');
    modal.innerHTML = '<div class="modal__body">Loading…</div>';
    modalBg.classList.add('open');
    try {
      const res = await fetch(API + '/api/market/products/' + id);
      const { product: p } = await res.json();
      const img = p.image_url
        ? `<div class="modal__img" style="background-image:url('${esc(p.image_url)}')"></div>` : '';
      const badges = (p.badges || []).map(badgeHtml).join('') || '<span class="card__seller">No certificates yet</span>';
      const attrs = (p.sustainability_attrs || []).map(a => `<li>${esc(a)}</li>`).join('');
      modal.innerHTML = `${img}
        <div class="modal__body">
          <button class="modal__close" onclick="window.__closeModal()">×</button>
          <div class="badges" style="margin-bottom:10px">${badges}</div>
          <h2 style="font-family:'DM Serif Display',serif;margin:0 0 4px">${esc(p.name)}</h2>
          <div class="card__seller">by ${esc(p.seller)}${p.category ? ' · ' + esc(p.category) : ''}</div>
          <div class="card__price" style="font-size:1.3rem;margin:12px 0">${money(p.price, p.currency)}</div>
          <p style="color:#456">${esc(p.description) || ''}</p>
          ${attrs ? `<ul style="color:#456;padding-left:18px">${attrs}</ul>` : ''}
          <div class="trust-note">🌱 Sustainability claims shown with a green ✓ badge have had their certificate reviewed by Green Curve. Badges marked “pending” are awaiting verification.</div>
        </div>`;
    } catch (e) {
      modal.innerHTML = '<div class="modal__body">Could not load this product. <button class="modal__close" onclick="window.__closeModal()">×</button></div>';
    }
  };
  window.__closeModal = () => document.getElementById('modalBg').classList.remove('open');
  window.closeModal = window.__closeModal;

  searchEl.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(load, 300); });
  catEl.addEventListener('change', load);
  verEl.addEventListener('change', load);

  loadCategories();
  load();
})();
