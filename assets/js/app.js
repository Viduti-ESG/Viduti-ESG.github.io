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

  const canFeature = filtered.length >= 3;
  grid.classList.toggle('posts-grid--two', !canFeature && filtered.length === 2);

  slice.forEach((post, i) => {
    const card = makeCard(post, canFeature && i === 0 && page === 1 && activeFilter === 'all');
    grid.appendChild(card);
  });
  renderPagination();
}

/* ── ACCENT COLOUR PER CATEGORY ── */
const ACCENT = {
  'CPCB / EPR':                '#34d399',
  'E-Waste Rules':             '#34d399',
  'Battery Waste Rules':       '#34d399',
  'Plastic Waste Rules':       '#34d399',
  'Urgent Notice / EPR':       '#34d399',
  'Portal Announcement':       '#38bdf8',
  'SEBI / BRSR':               '#60a5fa',
  'MoEFCC':                    '#4ade80',
  'BEE / Energy Efficiency':   '#f97316',
  'ISSB / IFRS Sustainability': '#c084fc',
  'EU CSRD / EFRAG':           '#fbbf24',
  'GHG Protocol':              '#f87171',
  'GRI':                       '#06b6d4',
  'CDP':                       '#818cf8',
  'SBTi':                      '#a3e635',
  'TNFD':                      '#2dd4bf',
  'Daily Digest':              '#38bdf8',
};
function accent(cat) { return ACCENT[cat] || '#94a3b8'; }

function makeCard(post, featured = false) {
  const ac   = accent(post.category);
  const tag  = `style="color:${ac};background:${ac}1a;border:1px solid ${ac}33"`;
  const card = document.createElement('article');
  card.className = 'card' + (featured ? ' card--featured' : '');
  card.style.setProperty('--accent', ac);

  if (featured) {
    card.innerHTML = `
      <div class="card__panel"></div>
      <div style="display:flex;flex-direction:column;flex:1;min-width:0;overflow:hidden">
        <div class="card__body">
          <div class="card__eyebrow">Featured insight</div>
          <div class="card__meta">
            <span class="card__tag" ${tag}>${esc(post.category)}</span>
            <span class="card__date">${fmtDate(post.date)}</span>
          </div>
          <h3 class="card__title">${esc(post.title)}</h3>
          <p class="card__summary">${esc(post.summary || '')}</p>
        </div>
        <div class="card__footer">
          <span class="card__read">Read full insight</span>
          <span class="card__source">${esc(post.source || '')}</span>
        </div>
      </div>
    `;
  } else {
    card.innerHTML = `
      <div class="card__body">
        <div class="card__meta">
          <span class="card__tag" ${tag}>${esc(post.category)}</span>
          <span class="card__date">${fmtDate(post.date)}</span>
        </div>
        <h3 class="card__title">${esc(post.title)}</h3>
        <p class="card__summary">${esc(post.summary || '')}</p>
      </div>
      <div class="card__footer">
        <span class="card__read">Read insight</span>
        <span class="card__source">${esc(post.source || '')}</span>
      </div>
    `;
  }

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
  const ac   = accent(post.category);
  const secs = post.sections || {};

  const box = document.getElementById('modal-box');
  box.style.setProperty('--accent', ac);
  box.innerHTML = `
    <button class="modal-x" id="modal-close-btn" aria-label="Close">&times;</button>
    <div class="modal-stripe" style="background:${ac}; border-radius:28px 28px 0 0;"></div>
    <div class="modal-content" id="modal-inner"></div>
  `;

  document.getElementById('modal-inner').innerHTML = `
    <div class="modal-cat">
      <span class="card__tag" style="color:${ac};background:${ac}1a;border:1px solid ${ac}33">${esc(post.category)}</span>
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
