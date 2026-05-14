/* Green Curve — Frontend App */

const PER_PAGE = 9;
let allPosts    = [];
let filtered    = [];
let page        = 1;
let activeFilter = 'all';

/* DOM refs */
const grid       = document.getElementById('posts-grid');
const pgNav      = document.getElementById('pagination');
const empty      = document.getElementById('empty-state');
const statPosts  = document.getElementById('stat-posts');
const filterCount= document.getElementById('filter-count');
const overlay    = document.getElementById('modal-overlay');
const mContent   = document.getElementById('modal-content');
const mClose     = document.getElementById('modal-close');
const header     = document.getElementById('site-header');

/* Misc init */
document.getElementById('year').textContent = new Date().getFullYear();
document.getElementById('hero-date').textContent =
  new Date().toLocaleDateString('en-IN', { day:'numeric', month:'long', year:'numeric' });

window.addEventListener('scroll', () => {
  header.classList.toggle('scrolled', window.scrollY > 10);
}, { passive: true });

/* ── LOAD ── */
async function loadPosts() {
  try {
    const res  = await fetch('posts/index.json?t=' + Date.now());
    const data = await res.json();
    allPosts = (data.posts || []).sort((a, b) => new Date(b.date) - new Date(a.date));
    statPosts.textContent = allPosts.length;
    applyFilter(activeFilter);
  } catch {
    grid.innerHTML = '';
    empty.classList.remove('hidden');
  }
}

/* ── FILTER PILLS ── */
document.querySelectorAll('.topic').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.topic').forEach(t => t.classList.remove('topic--active'));
    btn.classList.add('topic--active');
    activeFilter = btn.dataset.filter;
    page = 1;
    applyFilter(activeFilter);
  });
});

function applyFilter(f) {
  filtered = f === 'all' ? [...allPosts] : allPosts.filter(p => p.category === f);
  filterCount.textContent = filtered.length
    ? `${filtered.length} insight${filtered.length !== 1 ? 's' : ''}`
    : '';
  renderPage(page);
}

/* ── RENDER ── */
function renderPage(p) {
  page = p;
  const start = (p - 1) * PER_PAGE;
  const slice = filtered.slice(start, start + PER_PAGE);

  grid.innerHTML = '';

  if (!filtered.length) {
    empty.classList.remove('hidden');
    pgNav.innerHTML = '';
    return;
  }
  empty.classList.add('hidden');

  slice.forEach((post, i) => {
    const card = makeCard(post, i === 0 && page === 1 && activeFilter === 'all');
    grid.appendChild(card);
  });
  renderPagination();
}

/* ── CARD STYLES PER CATEGORY ── */
const CAT_STYLE = {
  'CPCB / EPR':               { stripe:'#059669', tag:'background:#ecfdf5;color:#065f46' },
  'SEBI / BRSR':              { stripe:'#2563eb', tag:'background:#eff6ff;color:#1e3a8a' },
  'MoEFCC':                   { stripe:'#16a34a', tag:'background:#f0fdf4;color:#14532d' },
  'ISSB / IFRS Sustainability':{ stripe:'#7c3aed', tag:'background:#f5f3ff;color:#4c1d95' },
  'EU CSRD / EFRAG':          { stripe:'#d97706', tag:'background:#fffbeb;color:#78350f' },
  'GHG Protocol':             { stripe:'#dc2626', tag:'background:#fef2f2;color:#7f1d1d' },
  'Daily Digest':             { stripe:'#0891b2', tag:'background:#ecfeff;color:#164e63' },
};
const DEFAULT_STYLE = { stripe:'#6b7280', tag:'background:#f3f4f6;color:#374151' };

function catStyle(cat) {
  return CAT_STYLE[cat] || DEFAULT_STYLE;
}

function makeCard(post, featured = false) {
  const s = catStyle(post.category);
  const card = document.createElement('article');
  card.className = 'card' + (featured ? ' card--featured' : '');

  card.innerHTML = `
    <div class="card__stripe" style="background:${s.stripe}"></div>
    <div class="card__body">
      <div class="card__meta">
        <span class="card__tag" style="${s.tag}">${esc(post.category)}</span>
        <span class="card__date">${fmtDate(post.date)}</span>
      </div>
      <h3 class="card__title">${esc(post.title)}</h3>
      <p class="card__summary">${esc(post.summary || '')}</p>
      <div class="card__footer">
        <span class="card__read">Read insight &rarr;</span>
        <span class="card__source">${esc(post.source || '')}</span>
      </div>
    </div>
  `;
  card.addEventListener('click', () => openModal(post));
  return card;
}

/* ── PAGINATION ── */
function renderPagination() {
  const total = Math.ceil(filtered.length / PER_PAGE);
  pgNav.innerHTML = '';
  if (total <= 1) return;
  for (let i = 1; i <= total; i++) {
    const btn = document.createElement('button');
    btn.className = 'pg-btn' + (i === page ? ' pg-btn--active' : '');
    btn.textContent = i;
    btn.addEventListener('click', () => {
      renderPage(i);
      document.getElementById('insights').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    pgNav.appendChild(btn);
  }
}

/* ── MODAL ── */
const SECTION_ORDER = [
  ['Executive Summary',           'summary'],
  ['What Changed',                'what_changed'],
  ['Who Is Affected',             'who_is_affected'],
  ['Key Obligations & Deadlines', 'key_obligations'],
  ['Climate Transition Angle',    'climate_angle'],
  ['What To Do Now',              'what_to_do'],
  ['Our Take',                    'our_take'],
];

function openModal(post) {
  const s = catStyle(post.category);
  const secs = post.sections || {};

  let html = `
    <div class="modal-stripe" style="background:${s.stripe}"></div>
    <div class="modal-content">
      <div class="modal-cat">
        <span class="card__tag" style="${s.tag}">${esc(post.category)}</span>
      </div>
      <h2 class="modal-title">${esc(post.title)}</h2>
      <p class="modal-date">${fmtDate(post.date)}${post.source ? ' &bull; ' + esc(post.source) : ''}</p>
  `;

  SECTION_ORDER.forEach(([label, key]) => {
    const val = secs[key] || (key === 'summary' ? post.summary : null);
    if (!val) return;
    html += `<p class="modal-label">${label}</p>`;
    if (Array.isArray(val)) {
      html += '<ul class="modal-bullets">' + val.map(b => `<li>${esc(b)}</li>`).join('') + '</ul>';
    } else {
      html += `<p class="modal-para">${esc(val)}</p>`;
    }
    html += '<hr class="modal-hr"/>';
  });

  if (post.link) {
    html += `<a class="modal-source-btn" href="${esc(post.link)}" target="_blank" rel="noopener">
      View source document &nearr;
    </a>`;
  }

  html += '</div>';

  /* inject stripe outside modal-content */
  const box = document.getElementById('modal-box');
  box.innerHTML = `
    <button class="modal-x" id="modal-close-btn" aria-label="Close">&times;</button>
    <div class="modal-stripe" style="background:${s.stripe}; border-radius:28px 28px 0 0;"></div>
    <div class="modal-content" id="modal-inner"></div>
  `;
  document.getElementById('modal-inner').innerHTML = `
    <div class="modal-cat">
      <span class="card__tag" style="${s.tag}">${esc(post.category)}</span>
    </div>
    <h2 class="modal-title">${esc(post.title)}</h2>
    <p class="modal-date">${fmtDate(post.date)}${post.source ? ' &bull; ' + esc(post.source) : ''}</p>
    ${buildSections(secs, post.summary)}
    ${post.link ? `<a class="modal-source-btn" href="${esc(post.link)}" target="_blank" rel="noopener">View source document &nearr;</a>` : ''}
  `;
  document.getElementById('modal-close-btn').addEventListener('click', closeModal);

  overlay.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  box.scrollTop = 0;
}

function buildSections(secs, fallbackSummary) {
  let out = '';
  SECTION_ORDER.forEach(([label, key]) => {
    const val = secs[key] || (key === 'summary' ? fallbackSummary : null);
    if (!val) return;
    out += `<p class="modal-label">${label}</p>`;
    if (Array.isArray(val)) {
      out += '<ul class="modal-bullets">' + val.map(b => `<li>${esc(b)}</li>`).join('') + '</ul>';
    } else {
      out += `<p class="modal-para">${esc(val)}</p>`;
    }
    out += '<hr class="modal-hr"/>';
  });
  return out;
}

function closeModal() {
  overlay.classList.add('hidden');
  document.body.style.overflow = '';
}

overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

/* ── HELPERS ── */
function fmtDate(d) {
  if (!d) return '';
  try {
    return new Date(d).toLocaleDateString('en-IN', { day:'numeric', month:'short', year:'numeric' });
  } catch { return d; }
}

function esc(s) {
  return String(s || '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ── INIT ── */
loadPosts();
