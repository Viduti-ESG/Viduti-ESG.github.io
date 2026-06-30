/* =============================================================================
   Green Curve — India ESG / Environmental Compliance Calendar
   -----------------------------------------------------------------------------
   100% client-side. The dataset below is PUBLIC regulatory information (statutory
   recurring deadlines under Indian environmental & SEBI law). Dates can change by
   notification and several are entity-specific (tied to your AGM, consent
   validity, or PAT cycle) — the page shows a prominent "verify with the official
   source" disclaimer. No user data is collected or sent anywhere.
   ============================================================================ */

const COMPLIANCE_ITEMS = [
  {
    id: 'form-v',
    title: 'Environmental Statement (Form-V)',
    authority: 'SPCB',
    freq: 'annual',
    due: [{ m: 9, d: 30 }],
    law: 'Environment (Protection) Rules, 1986 — Rule 14',
    appliesTo: 'Industries operating under a consent/authorisation',
    desc: 'Annual environmental statement for the financial year ending 31 March, submitted to the State Pollution Control Board.',
    sourceLabel: 'CPCB / SPCB',
    sourceUrl: 'https://cpcb.nic.in/',
  },
  {
    id: 'hw-form4',
    title: 'Hazardous & Other Wastes — Annual Return (Form 4)',
    authority: 'CPCB',
    freq: 'annual',
    due: [{ m: 6, d: 30 }],
    law: 'Hazardous & Other Wastes (M&TM) Rules, 2016',
    appliesTo: 'Occupiers handling hazardous waste',
    desc: 'Annual return of hazardous waste generated, stored, recycled, disposed — filed for the preceding financial year.',
    sourceLabel: 'CPCB',
    sourceUrl: 'https://cpcb.nic.in/',
  },
  {
    id: 'ec-halfyearly',
    title: 'Environmental Clearance — Compliance Report',
    authority: 'MoEFCC',
    freq: 'half-yearly',
    due: [{ m: 6, d: 1 }, { m: 12, d: 1 }],
    law: 'EIA Notification, 2006',
    appliesTo: 'Projects holding an Environmental Clearance',
    desc: 'Half-yearly compliance report on EC conditions, submitted to the MoEFCC Regional Office / SEIAA (1 June and 1 December).',
    sourceLabel: 'PARIVESH / MoEFCC',
    sourceUrl: 'https://parivesh.nic.in/',
  },
  {
    id: 'epr-plastic',
    title: 'Plastic Waste EPR — Annual Return',
    authority: 'CPCB',
    freq: 'annual',
    due: [{ m: 6, d: 30 }],
    law: 'Plastic Waste Management Rules (EPR Guidelines, 2022)',
    appliesTo: 'Producers, Importers & Brand-Owners (PIBOs)',
    desc: 'Annual return on the CPCB EPR portal reconciling plastic introduced vs. EPR obligation fulfilled.',
    sourceLabel: 'CPCB EPR Portal (Plastic)',
    sourceUrl: 'https://eprplastic.cpcb.gov.in/',
    note: 'Filing window is set on the CPCB portal and has been revised by notification — confirm the live date before filing.',
  },
  {
    id: 'epr-ewaste',
    title: 'E-Waste EPR — Annual Return',
    authority: 'CPCB',
    freq: 'annual',
    due: [{ m: 6, d: 30 }],
    law: 'E-Waste (Management) Rules, 2022',
    appliesTo: 'Producers & Manufacturers of EEE',
    desc: 'Annual return on the CPCB EPR portal against your e-waste collection / recycling target.',
    sourceLabel: 'CPCB EPR Portal (E-Waste)',
    sourceUrl: 'https://eprewastecpcb.in/',
    note: 'Confirm the live filing window on the portal — CPCB revises these dates.',
  },
  {
    id: 'epr-battery',
    title: 'Battery Waste EPR — Annual Return',
    authority: 'CPCB',
    freq: 'annual',
    due: [{ m: 6, d: 30 }],
    law: 'Battery Waste Management Rules, 2022',
    appliesTo: 'Producers of batteries',
    desc: 'Annual return on the CPCB EPR portal against your battery collection / refurbishment / recycling obligation.',
    sourceLabel: 'CPCB EPR Portal (Battery)',
    sourceUrl: 'https://eprbatterycpcb.in/',
    note: 'Confirm the live filing window on the portal.',
  },
  {
    id: 'brsr',
    title: 'BRSR — Business Responsibility & Sustainability Report',
    authority: 'SEBI',
    freq: 'entity',
    due: [],
    law: 'SEBI LODR Regulations',
    appliesTo: 'Top 1,000 listed companies by market cap',
    desc: 'Filed as part of the Annual Report. The exact date is tied to your AGM cycle (the annual report is submitted to the exchanges within the LODR timeline of the AGM).',
    sourceLabel: 'SEBI',
    sourceUrl: 'https://www.sebi.gov.in/',
    note: 'Entity-specific — set your target from your AGM / annual-report date.',
  },
  {
    id: 'brsr-core',
    title: 'BRSR Core — Assurance / Assessment',
    authority: 'SEBI',
    freq: 'entity',
    due: [],
    law: 'SEBI BRSR Core (Jul 2023 + Dec 2024 Industry Standards)',
    appliesTo: 'Top 150 → 250 → 500 → 1,000 (phased FY24-FY27)',
    desc: 'Independent assurance OR assessment of the ~49 BRSR Core KPIs, filed alongside the BRSR. From FY2024-25 entities may choose assurance or an equivalent assessment.',
    sourceLabel: 'SEBI',
    sourceUrl: 'https://www.sebi.gov.in/',
    note: 'Entity-specific — aligns with your BRSR / annual-report date.',
  },
  {
    id: 'bee-pat',
    title: 'BEE PAT — Annual Reporting (Form-A / Form-1)',
    authority: 'BEE',
    freq: 'cycle',
    due: [],
    law: 'Energy Conservation Act — PAT Scheme',
    appliesTo: 'Designated Consumers in notified sectors',
    desc: 'Annual energy-performance reporting via the PATNet portal; energy audit by an Accredited Energy Auditor at the cycle close.',
    sourceLabel: 'Bureau of Energy Efficiency',
    sourceUrl: 'https://beeindia.gov.in/',
    note: 'Cycle-based timeline notified by BEE — verify your sector cycle.',
  },
  {
    id: 'ccts',
    title: 'CCTS — Carbon Credit Trading Scheme Compliance',
    authority: 'BEE',
    freq: 'cycle',
    due: [],
    law: 'Energy Conservation (Amendment) Act, 2022',
    appliesTo: 'Obligated entities in notified sectors',
    desc: 'Meet the notified greenhouse-gas emission-intensity target for the compliance year; surrender / acquire Carbon Credit Certificates as required.',
    sourceLabel: 'BEE / Grid Controller of India (ICX)',
    sourceUrl: 'https://beeindia.gov.in/',
    note: 'New scheme — targets and timelines are being notified per sector; verify current status.',
  },
  {
    id: 'cto-renewal',
    title: 'Consent to Operate (CTO) — Renewal',
    authority: 'SPCB',
    freq: 'entity',
    due: [],
    law: 'Water Act 1974 & Air Act 1981',
    appliesTo: 'All consented industries',
    desc: 'Renew the Consent to Operate before expiry. Validity (typically 5–15 years) depends on your industry category (Red / Orange / Green / White).',
    sourceLabel: 'State PCB',
    sourceUrl: 'https://cpcb.nic.in/',
    note: 'Entity-specific — track your own consent expiry date.',
  },
];

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const AUTH_META = {
  SEBI:   { label: 'SEBI',   cls: 'sebi' },
  CPCB:   { label: 'CPCB',   cls: 'cpcb' },
  BEE:    { label: 'BEE',    cls: 'bee' },
  MoEFCC: { label: 'MoEFCC', cls: 'moefcc' },
  SPCB:   { label: 'SPCB',   cls: 'spcb' },
};

// ── next-occurrence + countdown ──────────────────────────────────────────────
function nextOccurrence(item, now) {
  if (!item.due || !item.due.length) return null; // entity/cycle — no fixed date
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  let best = null;
  item.due.forEach(({ m, d }) => {
    for (const yr of [now.getFullYear(), now.getFullYear() + 1]) {
      const cand = new Date(yr, m - 1, d);
      if (cand >= today && (best === null || cand < best)) best = cand;
    }
  });
  return best;
}

function daysUntil(date, now) {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((date - today) / 86400000);
}

function urgencyClass(days) {
  if (days == null) return 'entity';
  if (days <= 14) return 'urgent';
  if (days <= 45) return 'soon';
  return 'ok';
}

// ── render ───────────────────────────────────────────────────────────────────
let _activeFilter = 'all';

function renderCalendar() {
  const now = new Date();
  const grid = document.getElementById('cc-grid');
  if (!grid) return;

  const rows = COMPLIANCE_ITEMS.map(item => {
    const next = nextOccurrence(item, now);
    const days = next ? daysUntil(next, now) : null;
    return { item, next, days };
  });

  // Sort: dated items by soonest first, entity/cycle items last
  rows.sort((a, b) => {
    if (a.days == null && b.days == null) return 0;
    if (a.days == null) return 1;
    if (b.days == null) return -1;
    return a.days - b.days;
  });

  const visible = rows.filter(({ item }) =>
    _activeFilter === 'all' || item.authority === _activeFilter);

  grid.innerHTML = visible.map(({ item, next, days }) => {
    const u = urgencyClass(days);
    const am = AUTH_META[item.authority] || { label: item.authority, cls: 'spcb' };
    const dateStr = next
      ? `${next.getDate()} ${MONTHS[next.getMonth()]} ${next.getFullYear()}`
      : 'Entity-specific';
    const countdown = days == null
      ? '<span class="cc-count cc-count--entity">Set your own date</span>'
      : days === 0
        ? '<span class="cc-count cc-count--urgent">Due today</span>'
        : `<span class="cc-count cc-count--${u}">${days} day${days === 1 ? '' : 's'} left</span>`;
    const freqLabel = { annual: 'Annual', 'half-yearly': 'Half-yearly', cycle: 'Cycle-based', entity: 'Entity-specific' }[item.freq] || item.freq;
    const note = item.note ? `<p class="cc-note">⚠ ${item.note}</p>` : '';

    return `
      <article class="cc-card cc-card--${u}" data-auth="${item.authority}">
        <div class="cc-card__top">
          <span class="cc-badge cc-badge--${am.cls}">${am.label}</span>
          <span class="cc-freq">${freqLabel}</span>
        </div>
        <h3 class="cc-card__title">${item.title}</h3>
        <div class="cc-card__date">
          <span class="cc-date">${dateStr}</span>
          ${countdown}
        </div>
        <p class="cc-card__desc">${item.desc}</p>
        <div class="cc-card__meta">
          <span><strong>Applies to:</strong> ${item.appliesTo}</span>
          <span><strong>Under:</strong> ${item.law}</span>
        </div>
        ${note}
        <a class="cc-card__src" href="${item.sourceUrl}" target="_blank" rel="noopener">Verify on ${item.sourceLabel} ↗</a>
      </article>`;
  }).join('');

  // Headline stat: nearest dated deadline
  const nearest = rows.find(r => r.days != null);
  const head = document.getElementById('cc-next');
  if (head && nearest) {
    head.textContent = nearest.days === 0 ? 'Due today'
      : nearest.days === 1 ? '1 day' : `${nearest.days} days`;
    const lbl = document.getElementById('cc-next-label');
    if (lbl) lbl.textContent = nearest.item.title;
  }
}

function initFilters() {
  document.querySelectorAll('.cc-filter').forEach(btn => {
    btn.addEventListener('click', () => {
      _activeFilter = btn.dataset.filter;
      document.querySelectorAll('.cc-filter').forEach(b =>
        b.classList.toggle('cc-filter--active', b === btn));
      renderCalendar();
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  renderCalendar();
  initFilters();
});
