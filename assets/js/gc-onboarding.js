/**
 * Green Curve — First-login onboarding tour
 * Lightweight vanilla-JS tooltip walk-through, no external dependencies.
 * Shows once per account; dismissed state stored in localStorage.
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'gc_tour_done';
  const STEPS = [
    {
      target: null,
      title: "Welcome to Green Curve",
      body: "India's BRSR-native ESG intelligence platform. Let's take a 30-second tour of what you can do here.",
      pos: 'center',
    },
    {
      target: '[data-tab="screener"]',
      title: "ESG Screener",
      body: "Search and filter all 1,221 NSE/BSE-listed companies by ESG score, sector, risk tier, or BRSR filing status.",
      pos: 'bottom',
    },
    {
      target: '[data-tab="watchlist"]',
      title: "Watchlist & Alerts",
      body: "Add companies to your watchlist. You'll be alerted when their risk tier changes or new BRSR filings appear.",
      pos: 'bottom',
    },
    {
      target: '[data-tab="ai-query"]',
      title: "AI-Powered Analysis",
      body: "Ask any ESG question about a listed company — CCTS scores, TCFD gaps, emissions trends — and get instant AI analysis.",
      pos: 'bottom',
    },
    {
      target: '[data-tab="brsr"]',
      title: "BRSR Generator",
      body: "Pre-fill your company profile once. Then generate, preview, and export your BRSR disclosure report in minutes.",
      pos: 'bottom',
    },
    {
      target: null,
      title: "You're all set",
      body: "Explore at your own pace. Need help? Visit our <a href='/learn' style='color:#34d399'>Learning Centre</a> or email us at <a href='mailto:hello@greencurve.solutions' style='color:#34d399'>hello@greencurve.solutions</a>.",
      pos: 'center',
    },
  ];

  let _step = 0;
  let _overlay = null;
  let _tooltip = null;

  function _shouldShow() {
    if (localStorage.getItem(STORAGE_KEY)) return false;
    // Only show for logged-in users who just registered (gc_just_registered flag)
    return !!localStorage.getItem('gc_just_registered');
  }

  function _buildOverlay() {
    _overlay = document.createElement('div');
    _overlay.id = 'gc-tour-overlay';
    Object.assign(_overlay.style, {
      position: 'fixed', inset: '0', background: 'rgba(7,12,20,.7)',
      zIndex: '9000', backdropFilter: 'blur(2px)',
    });
    _overlay.addEventListener('click', function (e) {
      if (e.target === _overlay) _dismiss();
    });

    _tooltip = document.createElement('div');
    _tooltip.id = 'gc-tour-tip';
    Object.assign(_tooltip.style, {
      position: 'fixed', background: '#0e1420',
      border: '1px solid rgba(52,211,153,.3)',
      borderRadius: '16px', padding: '24px 26px',
      maxWidth: '360px', width: '90vw',
      color: '#e2e8f0', fontFamily: "'DM Sans', sans-serif",
      boxShadow: '0 24px 64px rgba(0,0,0,.6)',
      zIndex: '9001',
    });
    _overlay.appendChild(_tooltip);
    document.body.appendChild(_overlay);
  }

  function _positionTooltip(targetEl, pos) {
    const tip = _tooltip;
    if (!targetEl || pos === 'center') {
      tip.style.top = '50%';
      tip.style.left = '50%';
      tip.style.transform = 'translate(-50%,-50%)';
      return;
    }
    tip.style.transform = '';
    const r = targetEl.getBoundingClientRect();
    const tw = tip.offsetWidth || 360;
    const th = tip.offsetHeight || 160;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let top, left;
    if (pos === 'bottom') {
      top  = Math.min(r.bottom + 12, vh - th - 12);
      left = Math.max(12, Math.min(r.left + r.width / 2 - tw / 2, vw - tw - 12));
    } else {
      top  = Math.max(12, r.top - th - 12);
      left = Math.max(12, Math.min(r.left + r.width / 2 - tw / 2, vw - tw - 12));
    }
    tip.style.top  = top + 'px';
    tip.style.left = left + 'px';
  }

  function _highlightTarget(el) {
    document.querySelectorAll('.gc-tour-highlight').forEach(function (e) {
      e.classList.remove('gc-tour-highlight');
      e.style.removeProperty('position');
      e.style.removeProperty('z-index');
      e.style.removeProperty('box-shadow');
    });
    if (!el) return;
    el.classList.add('gc-tour-highlight');
    const cur = getComputedStyle(el).position;
    if (cur === 'static') el.style.position = 'relative';
    el.style.zIndex = '9002';
    el.style.boxShadow = '0 0 0 3px rgba(52,211,153,.5), 0 0 0 6px rgba(52,211,153,.15)';
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function _render() {
    const s = STEPS[_step];
    const isLast = _step === STEPS.length - 1;
    const targetEl = s.target ? document.querySelector(s.target) : null;

    _highlightTarget(targetEl);

    _tooltip.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <span style="font-size:.68rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:rgba(52,211,153,.8)">
          Step ${_step + 1} of ${STEPS.length}
        </span>
        <button onclick="window._gcTourDismiss()" style="background:none;border:none;color:rgba(226,232,240,.4);font-size:1.1rem;cursor:pointer;line-height:1;padding:0">✕</button>
      </div>
      <h3 style="margin:0 0 8px;font-size:1.05rem;font-weight:700;color:#fff">${s.title}</h3>
      <p style="margin:0 0 20px;font-size:.86rem;line-height:1.65;color:rgba(226,232,240,.75)">${s.body}</p>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
        ${_step > 0
          ? `<button onclick="window._gcTourPrev()" style="background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);color:#e2e8f0;padding:8px 18px;border-radius:8px;font-size:.82rem;cursor:pointer;font-family:inherit">← Back</button>`
          : '<span></span>'
        }
        <div style="display:flex;gap:6px;align-items:center">
          ${STEPS.map(function (_, i) {
            return `<span style="width:7px;height:7px;border-radius:50%;background:${i === _step ? '#34d399' : 'rgba(255,255,255,.15)'}"></span>`;
          }).join('')}
        </div>
        ${isLast
          ? `<button onclick="window._gcTourDismiss()" style="background:#34d399;border:none;color:#000;padding:8px 18px;border-radius:8px;font-size:.82rem;font-weight:700;cursor:pointer;font-family:inherit">Let's go!</button>`
          : `<button onclick="window._gcTourNext()" style="background:#34d399;border:none;color:#000;padding:8px 18px;border-radius:8px;font-size:.82rem;font-weight:700;cursor:pointer;font-family:inherit">Next →</button>`
        }
      </div>
    `;

    requestAnimationFrame(function () {
      _positionTooltip(targetEl, s.pos);
    });
  }

  function _dismiss() {
    localStorage.setItem(STORAGE_KEY, '1');
    localStorage.removeItem('gc_just_registered');
    _highlightTarget(null);
    if (_overlay) { _overlay.remove(); _overlay = null; _tooltip = null; }
  }

  window._gcTourNext    = function () { if (_step < STEPS.length - 1) { _step++; _render(); } };
  window._gcTourPrev    = function () { if (_step > 0) { _step--; _render(); } };
  window._gcTourDismiss = _dismiss;

  function _init() {
    if (!_shouldShow()) return;
    _buildOverlay();
    _render();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    // Small delay so the dashboard itself finishes rendering first
    setTimeout(_init, 800);
  }
})();
