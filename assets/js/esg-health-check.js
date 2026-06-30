/* =============================================================================
   Green Curve — Free ESG Health Check
   -----------------------------------------------------------------------------
   100% client-side. Nothing the user answers leaves the browser — no data is
   sent to any server, so there is no PII / DPDP exposure. The quiz computes a
   preliminary ESG-readiness score and routes the user to the relevant free
   Green Curve tools. Purely top-of-funnel.
   ============================================================================ */

const HC_QUESTIONS = [
  {
    id: 'applies', pillar: 'route', scored: false,
    q: 'Where does your company sit today?',
    help: 'This tailors the guidance — it is not scored.',
    options: [
      { t: 'Top 150 listed (by market cap)', v: 'top150' },
      { t: 'Top 1,000 listed', v: 'top1000' },
      { t: 'Listed below top 1,000', v: 'listed' },
      { t: 'Unlisted / private — preparing ahead', v: 'unlisted' },
    ],
  },
  {
    id: 'ghg', pillar: 'E', scored: true,
    q: 'Do you measure your Scope 1 & 2 GHG emissions?',
    options: [
      { t: 'Never measured', v: 0 },
      { t: 'Estimated once, roughly', v: 1 },
      { t: 'Calculated every year', v: 2 },
      { t: 'Tracked continuously with evidence', v: 3 },
    ],
  },
  {
    id: 'energy', pillar: 'E', scored: true,
    q: 'Is your electricity & fuel consumption metered and documented?',
    options: [
      { t: 'Not really', v: 0 },
      { t: 'Partially — some bills/meters', v: 1 },
      { t: 'Mostly documented', v: 2 },
      { t: 'Fully — every source has a bill/meter', v: 3 },
    ],
  },
  {
    id: 'waterwaste', pillar: 'E', scored: true,
    q: 'Do you track water withdrawal and waste generation?',
    options: [
      { t: 'Neither', v: 0 },
      { t: 'One of the two', v: 1 },
      { t: 'Both, roughly', v: 2 },
      { t: 'Both, with proper records', v: 3 },
    ],
  },
  {
    id: 'social', pillar: 'S', scored: true,
    q: 'Do you track workforce metrics (gender ratio, safety/LTIFR, training)?',
    options: [
      { t: 'No', v: 0 },
      { t: 'A few, informally', v: 1 },
      { t: 'Most of them', v: 2 },
      { t: 'All, documented and reviewed', v: 3 },
    ],
  },
  {
    id: 'policy', pillar: 'G', scored: true,
    q: 'Do you have board-approved ESG / sustainability policies (NGRBC principles)?',
    options: [
      { t: 'None', v: 0 },
      { t: 'Being drafted', v: 1 },
      { t: 'Some principles covered', v: 2 },
      { t: 'Comprehensive, board-approved', v: 3 },
    ],
  },
  {
    id: 'owner', pillar: 'G', scored: true,
    q: 'Who owns ESG data collection in your organisation?',
    options: [
      { t: 'Nobody specific', v: 0 },
      { t: 'One person, ad-hoc', v: 1 },
      { t: 'A small dedicated team', v: 2 },
      { t: 'Cross-functional, with clear roles', v: 3 },
    ],
  },
  {
    id: 'cadence', pillar: 'G', scored: true,
    q: 'How do you collect ESG data through the year?',
    options: [
      { t: 'A scramble just before filing', v: 0 },
      { t: 'Once a year', v: 1 },
      { t: 'Every quarter', v: 2 },
      { t: 'Continuously, year-round', v: 3 },
    ],
  },
  {
    id: 'valuechain', pillar: 'VC', scored: true,
    q: 'Do you collect ESG data from suppliers / your value chain?',
    options: [
      { t: 'Not at all', v: 0 },
      { t: 'Planning to start', v: 1 },
      { t: 'From some key suppliers', v: 2 },
      { t: 'Structured supplier programme', v: 3 },
    ],
  },
  {
    id: 'assurance', pillar: 'VC', scored: true,
    q: 'Could your ESG data survive third-party assurance (audit trail + evidence)?',
    options: [
      { t: 'No idea', v: 0 },
      { t: 'Unlikely', v: 1 },
      { t: 'Partially', v: 2 },
      { t: 'Yes — audit-ready with evidence', v: 3 },
    ],
  },
];

const PILLAR_NAMES = { E: 'Environment', S: 'Social', G: 'Governance', VC: 'Value chain & assurance' };

// recommendation map: pillar/area → CTA
const RECO = {
  E:  { txt: 'Start measuring Scope 1, 2 & 3 with India CEA + DEFRA factors.', cta: 'Open the GHG Calculator', href: 'calculator.html' },
  S:  { txt: 'Capture workforce diversity, safety and training metrics systematically.', cta: 'See BRSR social KPIs', href: 'learn.html' },
  G:  { txt: 'Move from annual scramble to a year-round process with clear owners.', cta: 'Open the BRSR Workspace', href: '/brsr-workspace' },
  VC: { txt: 'Collect supplier ESG data and build an audit-ready evidence trail.', cta: 'Open the Value-Chain tool', href: 'value-chain.html' },
};

const state = { idx: 0, answers: {} };

function el(id) { return document.getElementById(id); }

function renderQuestion() {
  const total = HC_QUESTIONS.length;
  const q = HC_QUESTIONS[state.idx];
  el('hc-progress-bar').style.width = ((state.idx) / total * 100) + '%';
  el('hc-step').textContent = `Question ${state.idx + 1} of ${total}`;

  const chosen = state.answers[q.id];
  el('hc-card').innerHTML = `
    <h2 class="hc-q">${q.q}</h2>
    ${q.help ? `<p class="hc-help">${q.help}</p>` : ''}
    <div class="hc-options">
      ${q.options.map((o, i) => `
        <button class="hc-opt${chosen !== undefined && chosen === o.v ? ' hc-opt--sel' : ''}" data-val="${o.v}">
          <span class="hc-opt__dot"></span><span>${o.t}</span>
        </button>`).join('')}
    </div>
    <div class="hc-nav">
      <button class="hc-back" ${state.idx === 0 ? 'disabled' : ''}>&larr; Back</button>
    </div>`;

  el('hc-card').querySelectorAll('.hc-opt').forEach(btn => {
    btn.addEventListener('click', () => {
      const raw = btn.dataset.val;
      state.answers[q.id] = q.scored ? Number(raw) : raw;
      if (state.idx < HC_QUESTIONS.length - 1) { state.idx++; renderQuestion(); }
      else { renderResult(); }
    });
  });
  const back = el('hc-card').querySelector('.hc-back');
  if (back) back.addEventListener('click', () => { if (state.idx > 0) { state.idx--; renderQuestion(); } });
}

function computeScore() {
  const scored = HC_QUESTIONS.filter(q => q.scored);
  let total = 0; const max = scored.length * 3;
  const pillar = {}; const pillarMax = {};
  scored.forEach(q => {
    const v = state.answers[q.id] || 0;
    total += v;
    pillar[q.pillar] = (pillar[q.pillar] || 0) + v;
    pillarMax[q.pillar] = (pillarMax[q.pillar] || 0) + 3;
  });
  return { total, max, pct: Math.round(total / max * 100), pillar, pillarMax };
}

function band(pct) {
  if (pct < 34) return { name: 'Just Starting', cls: 'low', blurb: 'You\'re at the beginning — the priority is getting basic, consistent data in place. Aim for "rough but repeatable" first; precision comes later.' };
  if (pct < 67) return { name: 'Developing', cls: 'mid', blurb: 'You have real foundations. The gap to filing-ready is process: clear ownership, year-round collection, and an evidence trail.' };
  return { name: 'Audit-Ready', cls: 'high', blurb: 'You\'re in strong shape. Focus now on assurance robustness, value-chain depth, and turning data into performance improvement.' };
}

function renderResult() {
  el('hc-progress-bar').style.width = '100%';
  el('hc-step').textContent = 'Your result';
  const s = computeScore();
  const b = band(s.pct);
  const applies = state.answers.applies;
  const appliesMsg = {
    top150:  'As a <strong>top-150</strong> company, BRSR Core assurance/assessment already applies to you.',
    top1000: 'As a <strong>top-1,000</strong> company, BRSR is mandatory and BRSR Core ramps up to you by FY2026-27.',
    listed:  'BRSR isn\'t mandatory for you yet, but value-chain requests and voluntary filing are rising — preparing early pays off.',
    unlisted:'You\'re not in scope yet, but customers and lenders increasingly ask for ESG data — a head start is an advantage.',
  }[applies] || '';

  // weakest pillars → recommendations
  const weak = Object.keys(s.pillar)
    .map(p => ({ p, ratio: s.pillar[p] / s.pillarMax[p] }))
    .sort((a, b) => a.ratio - b.ratio)
    .slice(0, 3)
    .filter(x => RECO[x.p]);

  const pillarBars = Object.keys(PILLAR_NAMES).filter(p => s.pillarMax[p]).map(p => {
    const pc = Math.round(s.pillar[p] / s.pillarMax[p] * 100);
    return `<div class="hc-pbar">
      <div class="hc-pbar__top"><span>${PILLAR_NAMES[p]}</span><span>${pc}%</span></div>
      <div class="hc-pbar__track"><div class="hc-pbar__fill hc-pbar__fill--${pc < 34 ? 'low' : pc < 67 ? 'mid' : 'high'}" style="width:${pc}%"></div></div>
    </div>`;
  }).join('');

  el('hc-card').innerHTML = `
    <div class="hc-result hc-result--${b.cls}">
      <div class="hc-score-ring">
        <div class="hc-score-num">${s.pct}<span>%</span></div>
        <div class="hc-score-band">${b.name}</div>
      </div>
      <p class="hc-result__blurb">${b.blurb}</p>
    </div>
    ${appliesMsg ? `<p class="hc-applies">${appliesMsg}</p>` : ''}
    <h3 class="hc-sub">Where you stand by pillar</h3>
    <div class="hc-pbars">${pillarBars}</div>
    <h3 class="hc-sub">Your top 3 next moves</h3>
    <div class="hc-recos">
      ${weak.map(({ p }) => `
        <div class="hc-reco">
          <div class="hc-reco__pill">${PILLAR_NAMES[p]}</div>
          <p>${RECO[p].txt}</p>
          <a href="${RECO[p].href}">${RECO[p].cta} &rarr;</a>
        </div>`).join('')}
    </div>
    <div class="hc-result-cta">
      <p>Keep every deadline in sight while you build your data.</p>
      <a class="hc-btn-primary" href="compliance-calendar.html">Open the Compliance Calendar</a>
      <button class="hc-btn-ghost" id="hc-restart">Retake the check</button>
    </div>
    <p class="hc-disc">This is a preliminary self-assessment for guidance only — not a compliance opinion or assurance. Your answers stay in your browser and are never sent anywhere.</p>`;

  const rs = el('hc-restart');
  if (rs) rs.addEventListener('click', () => { state.idx = 0; state.answers = {}; renderQuestion(); });

  if (window.gtag) gtag('event', 'esg_health_check_complete', { score: s.pct, band: b.name });
}

function startCheck() {
  el('hc-intro').hidden = true;
  el('hc-quiz').hidden = false;
  state.idx = 0; state.answers = {};
  renderQuestion();
}

document.addEventListener('DOMContentLoaded', () => {
  const start = el('hc-start');
  if (start) start.addEventListener('click', startCheck);
});
