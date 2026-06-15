/* Green Curve — Frontend App */

const PER_PAGE   = 9;
const PRIORITY_DOMAINS = ['climateactiontracker.org', 'carbontracker.org'];
let _modalScrollCtrl = null; // tracks the active modal scroll listener so it can be cancelled on re-open
let allPosts     = [];
let filtered     = [];
let page         = 1;
let activeFilter = 'Daily Digest';
let searchQuery  = '';

function _normalizeSourceHost(value) {
  if (!value) return '';
  const text = String(value).trim().toLowerCase();
  try {
    return new URL(text).hostname.replace(/^www\./, '');
  } catch {
    return text.replace(/^www\./, '');
  }
}

function isPrioritySource(post) {
  const host = _normalizeSourceHost(post.link) || _normalizeSourceHost(post.source);
  return PRIORITY_DOMAINS.some(domain => host === domain || host.endsWith('.' + domain));
}

/* DOM refs */
const grid      = document.getElementById('posts-grid');
const pgNav     = document.getElementById('pagination');
const empty     = document.getElementById('empty-state');
const statPosts = document.getElementById('stat-posts');
const filterCnt = document.getElementById('filter-count');
const overlay   = document.getElementById('modal-overlay');
const header    = document.getElementById('site-header');
const progress  = document.getElementById('scroll-progress');
const backTop   = document.getElementById('back-top');
const searchInp = document.getElementById('search-input');

/* ── DATE INIT ── */
document.getElementById('year').textContent = new Date().getFullYear();
document.getElementById('hero-date').textContent =
  new Date().toLocaleDateString('en-IN', { day:'numeric', month:'long', year:'numeric' });

/* ── SCROLL EFFECTS ── */
window.addEventListener('scroll', () => {
  const s = window.scrollY;
  const max = document.documentElement.scrollHeight - window.innerHeight;
  if (progress) progress.style.width = (s / max * 100).toFixed(1) + '%';
  header.classList.toggle('scrolled', s > 10);
  if (backTop) backTop.classList.toggle('visible', s > 500);
}, { passive: true });

if (backTop) backTop.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));

/* ── MOBILE MENU ── */
const burger    = document.getElementById('nav-burger');
const mobileNav = document.getElementById('nav-mobile');
if (burger && mobileNav) {
  burger.addEventListener('click', () => {
    const open = burger.classList.toggle('open');
    mobileNav.classList.toggle('open', open);
    document.body.style.overflow = open ? 'hidden' : '';
  });
  mobileNav.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
    burger.classList.remove('open');
    mobileNav.classList.remove('open');
    document.body.style.overflow = '';
  }));
}

/* ── SEARCH ── */
if (searchInp) {
  searchInp.addEventListener('input', () => {
    searchQuery = searchInp.value.trim().toLowerCase();
    page = 1;
    applyFilter(activeFilter);
  });
  searchInp.addEventListener('keydown', e => {
    if (e.key === 'Escape') { searchInp.value = ''; searchQuery = ''; applyFilter(activeFilter); }
  });
}

/* ── LOAD ── */
async function loadPosts() {
  try {
    const res  = await fetch('posts/index.json?t=' + Date.now());
    const data = await res.json();
    const sorted = (data.posts || []).sort((a, b) => new Date(b.date) - new Date(a.date));
    allPosts = [
      ...sorted.filter(isPrioritySource),
      ...sorted.filter(post => !isPrioritySource(post)),
    ];
    statPosts.textContent = allPosts.length;
    buildBadges();
    applyFilter(activeFilter);
    buildInsightCarousel(allPosts);
  } catch {
    grid.innerHTML = '';
    empty.classList.remove('hidden');
  }
}

/* ── BADGE COUNTS ON PILLS ── */
function buildBadges() {
  document.querySelectorAll('.topic').forEach(btn => {
    const f     = btn.dataset.filter;
    const cats  = TOPIC_MAP[f] || [f];
    const count = f === 'all'
      ? allPosts.length
      : allPosts.filter(p => cats.includes(p.category)).length;

    let badge = btn.querySelector('.topic__count');
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'topic__count';
      btn.appendChild(badge);
    }
    badge.textContent = count;
    if (count === 0 && f !== 'Daily Digest') btn.style.opacity = '0.4';
    else btn.style.opacity = '';
  });
}

/* ── FILTER PILLS ── */
document.querySelectorAll('.topic').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.topic').forEach(t => t.classList.remove('topic--active'));
    btn.classList.add('topic--active');
    activeFilter = btn.dataset.filter;
    page = 1;
    if (searchInp) { searchInp.value = ''; searchQuery = ''; }
    applyFilter(activeFilter);
  });
  btn.setAttribute('role', 'tab');
  btn.setAttribute('tabindex', '0');
  btn.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); btn.click(); }
  });
});

function applyFilter(f) {
  const cats = TOPIC_MAP[f] || [f];
  let base = f === 'all' ? [...allPosts] : allPosts.filter(p => cats.includes(p.category));
  if (searchQuery) {
    base = base.filter(p =>
      (p.title    || '').toLowerCase().includes(searchQuery) ||
      (p.summary  || '').toLowerCase().includes(searchQuery) ||
      (p.category || '').toLowerCase().includes(searchQuery) ||
      (p.source   || '').toLowerCase().includes(searchQuery)
    );
  }
  filtered = base;
  filterCnt.textContent = filtered.length
    ? `${filtered.length} insight${filtered.length !== 1 ? 's' : ''}`
    : (searchQuery ? '0 results' : '');
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

  const canFeature = filtered.length >= 3 && !searchQuery;
  grid.classList.toggle('posts-grid--two', !canFeature && filtered.length === 2);

  slice.forEach((post, i) => {
    const card = makeCard(post, canFeature && i === 0 && page === 1);
    card.style.animationDelay = `${i * 60}ms`;
    card.classList.add('card--appear');
    grid.appendChild(card);
  });
  renderPagination();
}

/* ── TOPIC → CATEGORY MAPPING ── */
const TOPIC_MAP = {
  'CPCB / EPR': [
    'CPCB / EPR', 'Plastic Waste Rules', 'E-Waste Rules',
    'Battery Waste Rules', 'Urgent Notice / EPR', 'Portal Announcement',
    'EPR / E-Waste Compliance',
  ],
  'SEBI / BRSR':               ['SEBI / BRSR'],
  'MoEFCC':                    ['MoEFCC'],
  'BEE / Energy Efficiency':   ['BEE / Energy Efficiency'],
  'ISSB / IFRS Sustainability': ['ISSB / IFRS Sustainability'],
  'EU CSRD / EFRAG':           ['EU CSRD / EFRAG'],
  'GHG Protocol':              ['GHG Protocol'],
  'GRI':                       ['GRI'],
  'CDP':                       ['CDP'],
  'SBTi':                      ['SBTi'],
  'TNFD':                      ['TNFD'],
  'Daily Digest':              ['Daily Digest'],
};

/* ── ACCENT COLOUR PER CATEGORY ── */
const ACCENT = {
  'CPCB / EPR':                 '#34d399',
  'E-Waste Rules':              '#34d399',
  'Battery Waste Rules':        '#34d399',
  'Plastic Waste Rules':        '#34d399',
  'Urgent Notice / EPR':        '#34d399',
  'Portal Announcement':        '#38bdf8',
  'SEBI / BRSR':                '#60a5fa',
  'MoEFCC':                     '#4ade80',
  'BEE / Energy Efficiency':    '#f97316',
  'ISSB / IFRS Sustainability':  '#c084fc',
  'EU CSRD / EFRAG':            '#fbbf24',
  'GHG Protocol':               '#f87171',
  'GRI':                        '#06b6d4',
  'CDP':                        '#818cf8',
  'SBTi':                       '#a3e635',
  'TNFD':                       '#2dd4bf',
  'Daily Digest':               '#38bdf8',
};
function accent(cat) { return ACCENT[cat] || '#94a3b8'; }

function isNew(dateStr) {
  if (!dateStr) return false;
  return (Date.now() - new Date(dateStr)) / 86400000 < 3;
}

function makeCard(post, featured = false) {
  const ac      = accent(post.category);
  const tag     = `style="color:${ac};background:${ac}1a;border:1px solid ${ac}33"`;
  const newBadge = isNew(post.date) ? `<span class="card__new">New</span>` : '';
  const card    = document.createElement('article');
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
            ${newBadge}
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
          ${newBadge}
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

  // Link to static post page (crawlable, shareable, AI-readable)
  const postUrl = `posts/${post.id}.html`;
  card.style.cursor = 'pointer';
  card.addEventListener('click', (e) => {
    // If static page exists, navigate to it; else fall back to modal
    fetch(postUrl, { method: 'HEAD' })
      .then(r => r.ok ? window.location.href = postUrl : openModal(post))
      .catch(() => openModal(post));
  });
  return card;
}

/* ── PAGINATION ── */
function renderPagination() {
  const total = Math.ceil(filtered.length / PER_PAGE);
  pgNav.innerHTML = '';
  if (total <= 1) return;

  const go = pg => {
    renderPage(pg);
    document.getElementById('insights').scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const mkBtn = (html, pg, disabled = false, active = false, extra = '') => {
    const btn = document.createElement('button');
    btn.className = 'pg-btn' + (active ? ' pg-btn--active' : '') + (extra ? ' ' + extra : '');
    btn.innerHTML  = html;
    btn.disabled   = disabled;
    if (!disabled) btn.addEventListener('click', () => go(pg));
    return btn;
  };

  pgNav.appendChild(mkBtn('&#8592; Prev', page - 1, page === 1, false, 'pg-btn--arrow'));

  paginationRange(page, total).forEach(p => {
    if (p === '…') {
      const el = document.createElement('span');
      el.className = 'pg-ellipsis';
      el.textContent = '…';
      pgNav.appendChild(el);
    } else {
      pgNav.appendChild(mkBtn(p, p, false, p === page));
    }
  });

  pgNav.appendChild(mkBtn('Next &#8594;', page + 1, page === total, false, 'pg-btn--arrow'));
}

function paginationRange(cur, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  if (cur <= 4)   return [1, 2, 3, 4, 5, '…', total];
  if (cur >= total - 3) return [1, '…', total-4, total-3, total-2, total-1, total];
  return [1, '…', cur-1, cur, cur+1, '…', total];
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

function _injectArticleSchema(post) {
  const existing = document.getElementById('ld-article');
  if (existing) existing.remove();
  const schema = {
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": post.title,
    "description": post.summary || '',
    "datePublished": post.date,
    "dateModified": post.date,
    "author": { "@type": "Organization", "name": "Green Curve Research" },
    "publisher": {
      "@type": "Organization",
      "name": "Green Curve",
      "logo": { "@type": "ImageObject", "url": "https://viduti-esg.github.io/assets/img/logo.png" }
    },
    "mainEntityOfPage": { "@type": "WebPage", "@id": "https://viduti-esg.github.io/" },
    "keywords": post.category + ", ESG India, climate compliance",
    "articleSection": post.category
  };
  const el = document.createElement('script');
  el.type = 'application/ld+json';
  el.id   = 'ld-article';
  el.textContent = JSON.stringify(schema);
  document.head.appendChild(el);
}

function _updateMeta(name, content, prop) {
  const sel = prop ? `meta[property="${name}"]` : `meta[name="${name}"]`;
  let el = document.querySelector(sel);
  if (!el) { el = document.createElement('meta'); prop ? el.setAttribute('property', name) : el.setAttribute('name', name); document.head.appendChild(el); }
  el.setAttribute('content', content);
}

function openModal(post) {
  _injectArticleSchema(post);
  _updateMeta('description', (post.summary || '').slice(0, 160));
  _updateMeta('og:title',       post.title, true);
  _updateMeta('og:description', (post.summary || '').slice(0, 200), true);
  _updateMeta('twitter:title',       post.title, true);
  _updateMeta('twitter:description', (post.summary || '').slice(0, 200), true);

  const ac   = accent(post.category);
  const secs = post.sections || {};
  const box  = document.getElementById('modal-box');

  box.style.setProperty('--accent', ac);
  box.innerHTML = `
    <div class="modal-read-bar" id="modal-read-bar"></div>
    <button class="modal-x" id="modal-close-btn" aria-label="Close">&times;</button>
    <div class="modal-stripe" style="background:linear-gradient(90deg,${ac},${ac}88); border-radius:28px 28px 0 0;"></div>
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
    <div class="modal-share">
      <span class="modal-share__label">Share</span>
      <a class="modal-share__btn modal-share__btn--li"
         href="https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(post.link||location.href)}&title=${encodeURIComponent(post.title)}"
         target="_blank" rel="noopener" aria-label="Share on LinkedIn">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
        LinkedIn
      </a>
      <button class="modal-share__btn" id="modal-copy-btn" aria-label="Copy link">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        Copy link
      </button>
    </div>
  `;

  if (_modalScrollCtrl) _modalScrollCtrl.abort();
  _modalScrollCtrl = new AbortController();
  box.addEventListener('scroll', () => {
    const pct = box.scrollTop / (box.scrollHeight - box.clientHeight) * 100;
    const bar = document.getElementById('modal-read-bar');
    if (bar) bar.style.width = pct.toFixed(1) + '%';
  }, { passive: true, signal: _modalScrollCtrl.signal });

  document.getElementById('modal-copy-btn').addEventListener('click', function () {
    const url = post.link || location.href;
    navigator.clipboard.writeText(url).then(() => {
      this.textContent = 'Copied!';
      setTimeout(() => this.textContent = 'Copy link', 2000);
    }).catch(() => {
      this.textContent = 'Copy failed';
      setTimeout(() => this.textContent = 'Copy link', 2000);
    });
  });

  document.getElementById('modal-close-btn').addEventListener('click', closeModal);
  overlay.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  box.scrollTop = 0;

  /* trap focus */
  box.setAttribute('tabindex', '-1');
  box.focus();
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
  const ldArt = document.getElementById('ld-article');
  if (ldArt) ldArt.remove();
  _updateMeta('description', 'Green Curve delivers daily ESG and climate transition intelligence for Indian businesses — CPCB EPR, SEBI BRSR, MoEFCC, BEE, ISSB IFRS S1/S2, EU CSRD, GHG Protocol, GRI, CDP, SBTi and TNFD. Expert analysis every morning.');
  _updateMeta('og:title',       'Green Curve — ESG & Climate Compliance Intelligence for India', true);
  _updateMeta('og:description', 'Daily ESG and climate compliance intelligence for Indian businesses. Expert analysis across 13+ regulatory sources.', true);
  _updateMeta('twitter:title',       'Green Curve — ESG & Climate Compliance Intelligence for India', true);
  _updateMeta('twitter:description', 'Daily ESG and climate compliance intelligence for Indian businesses. Expert analysis across 13+ regulatory sources.', true);
}

overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

/* ── HELPERS ── */
function fmtDate(d) {
  if (!d) return '';
  try { return new Date(d).toLocaleDateString('en-IN', { day:'numeric', month:'short', year:'numeric' }); }
  catch { return d; }
}

function esc(s) {
  return String(s || '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ── TRENDING CAROUSEL (imagine.art "What's New" pattern) ────────────────── */
function buildInsightCarousel(posts) {
  const track = document.getElementById('insightCarousel');
  if (!track || !posts || !posts.length) return;

  // Use top 12 most recent posts for the carousel
  const recent = posts.slice(0, 12);

  // Tag → accent color mapping
  const tagColors = {
    'CPCB / EPR':            'var(--emerald)',
    'SEBI / BRSR':           'var(--cyan)',
    'MoEFCC':                '#4ade80',
    'BEE / Energy Efficiency':'#f97316',
    'ISSB / IFRS Sustainability': 'var(--violet)',
    'EU CSRD / EFRAG':       'var(--amber)',
    'GHG Protocol':          '#f87171',
    'GRI':                   '#06b6d4',
    'CDP':                   'var(--violet)',
    'SBTi':                  '#a3e635',
    'TNFD':                  '#2dd4bf',
    'Daily Digest':          '#38bdf8',
  };

  const cards = recent.map((p, i) => {
    const accent  = tagColors[p.category] || 'var(--cyan)';
    const dateStr = fmtDate(p.date);
    const el = document.createElement('div');
    el.className = 'gc-insight-card';
    el.style.setProperty('--ic-accent', accent);
    el.setAttribute('role', 'button');
    el.setAttribute('tabindex', '0');
    el.setAttribute('data-carousel-idx', i);
    el.innerHTML = `<div class="gc-insight-card__tag">${esc(p.category || '')}</div>
      <div class="gc-insight-card__title">${esc(p.title)}</div>
      <div class="gc-insight-card__date">${dateStr}</div>`;
    el.addEventListener('click', () => openModal(p));
    return el;
  });
  track.innerHTML = '';
  cards.forEach(c => track.appendChild(c));

  // Carousel nav buttons
  const prev = document.getElementById('carouselPrev');
  const next = document.getElementById('carouselNext');
  const scrollBy = 300;

  function updateBtns() {
    if (prev) prev.disabled = track.scrollLeft < 10;
    if (next) next.disabled = track.scrollLeft + track.clientWidth >= track.scrollWidth - 10;
  }

  if (prev) prev.addEventListener('click', () => { track.scrollLeft -= scrollBy; setTimeout(updateBtns, 350); });
  if (next) next.addEventListener('click', () => { track.scrollLeft += scrollBy; setTimeout(updateBtns, 350); });
  track.addEventListener('scroll', updateBtns, { passive: true });
  setTimeout(updateBtns, 100);

  // Keyboard navigation on cards
  track.querySelectorAll('.gc-insight-card').forEach(card => {
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') card.click(); });
  });
}

/* ── INIT ── */
loadPosts();
