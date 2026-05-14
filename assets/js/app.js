/* Viduti ESG Intelligence — Frontend App */

const POSTS_PER_PAGE = 9;
let allPosts   = [];
let filtered   = [];
let currentPage = 1;
let activeFilter = 'all';

const grid       = document.getElementById('posts-grid');
const pagination = document.getElementById('pagination');
const emptyState = document.getElementById('empty-state');
const statPosts  = document.getElementById('stat-posts');
const backdrop   = document.getElementById('modal-backdrop');
const modal      = document.getElementById('modal');
const modalBody  = document.getElementById('modal-body');
const modalClose = document.getElementById('modal-close');

document.getElementById('year').textContent = new Date().getFullYear();

/* ── FETCH POSTS ── */
async function loadPosts() {
  try {
    const res  = await fetch('posts/index.json?t=' + Date.now());
    const data = await res.json();
    allPosts = (data.posts || []).sort((a, b) => new Date(b.date) - new Date(a.date));
    statPosts.textContent = allPosts.length;
    applyFilter(activeFilter);
  } catch {
    grid.innerHTML = '';
    emptyState.classList.remove('hidden');
  }
}

/* ── CATEGORY PILLS ── */
document.querySelectorAll('.pill').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.pill').forEach(p => p.classList.remove('pill--active'));
    btn.classList.add('pill--active');
    activeFilter = btn.dataset.filter;
    currentPage  = 1;
    applyFilter(activeFilter);
  });
});

function applyFilter(f) {
  filtered = f === 'all' ? [...allPosts] : allPosts.filter(p => p.category === f);
  renderPage(currentPage);
}

/* ── RENDER ── */
function renderPage(page) {
  currentPage = page;
  const start = (page - 1) * POSTS_PER_PAGE;
  const slice = filtered.slice(start, start + POSTS_PER_PAGE);

  grid.innerHTML = '';
  if (filtered.length === 0) {
    emptyState.classList.remove('hidden');
    pagination.innerHTML = '';
    return;
  }
  emptyState.classList.add('hidden');
  slice.forEach(post => grid.appendChild(makeCard(post)));
  renderPagination();
}

function catClass(cat) {
  const c = cat.toLowerCase();
  if (c.includes('cpcb') || c.includes('epr')) return 'cat--cpcb';
  if (c.includes('sebi') || c.includes('brsr')) return 'cat--sebi';
  if (c.includes('moef')) return 'cat--moef';
  if (c.includes('issb') || c.includes('ifrs')) return 'cat--issb';
  if (c.includes('csrd') || c.includes('efrag')) return 'cat--csrd';
  if (c.includes('ghg')) return 'cat--ghg';
  return 'cat--digest';
}

function makeCard(post) {
  const card = document.createElement('article');
  card.className = 'post-card';
  card.innerHTML = `
    <div class="post-card__meta">
      <span class="post-card__cat ${catClass(post.category)}">${post.category}</span>
      <span class="post-card__date">${formatDate(post.date)}</span>
    </div>
    <h3 class="post-card__title">${esc(post.title)}</h3>
    <p class="post-card__summary">${esc(post.summary || '')}</p>
    <div class="post-card__footer">
      <span class="post-card__read">Read more →</span>
      <span class="post-card__source">${esc(post.source || '')}</span>
    </div>
  `;
  card.addEventListener('click', () => openModal(post));
  return card;
}

function renderPagination() {
  const total = Math.ceil(filtered.length / POSTS_PER_PAGE);
  if (total <= 1) { pagination.innerHTML = ''; return; }
  pagination.innerHTML = '';
  for (let i = 1; i <= total; i++) {
    const btn = document.createElement('button');
    btn.className = 'page-btn' + (i === currentPage ? ' page-btn--active' : '');
    btn.textContent = i;
    btn.addEventListener('click', () => {
      renderPage(i);
      document.getElementById('insights').scrollIntoView({ behavior: 'smooth' });
    });
    pagination.appendChild(btn);
  }
}

/* ── MODAL ── */
function openModal(post) {
  const sections = post.sections || {};
  let html = `
    <div class="modal__cat">
      <span class="post-card__cat ${catClass(post.category)}">${esc(post.category)}</span>
    </div>
    <h2 class="modal__title">${esc(post.title)}</h2>
    <p class="modal__date">${formatDate(post.date)}${post.source ? ' &bull; ' + esc(post.source) : ''}</p>
  `;

  const sectionOrder = [
    ['Executive Summary',          'summary'],
    ['What Changed',               'what_changed'],
    ['Who Is Affected',            'who_is_affected'],
    ['Key Obligations & Deadlines','key_obligations'],
    ['Climate Transition Angle',   'climate_angle'],
    ['What To Do Now',             'what_to_do'],
    ['Our Take',                   'our_take'],
  ];

  sectionOrder.forEach(([label, key]) => {
    const val = sections[key] || (key === 'summary' ? post.summary : null);
    if (!val) return;
    html += `<p class="modal__section-title">${label}</p>`;
    if (Array.isArray(val)) {
      html += '<ul class="modal__bullets">' + val.map(b => `<li>${esc(b)}</li>`).join('') + '</ul>';
    } else {
      html += `<p class="modal__text">${esc(val)}</p>`;
    }
    html += '<hr class="modal__divider" />';
  });

  if (post.link) {
    html += `<a class="modal__link" href="${esc(post.link)}" target="_blank" rel="noopener">
      View Source Document ↗
    </a>`;
  }

  modalBody.innerHTML = html;
  backdrop.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  backdrop.classList.add('hidden');
  document.body.style.overflow = '';
}

modalClose.addEventListener('click', closeModal);
backdrop.addEventListener('click', e => { if (e.target === backdrop) closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

/* ── HELPERS ── */
function formatDate(d) {
  if (!d) return '';
  try {
    return new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch { return d; }
}

function esc(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ── INIT ── */
loadPosts();
