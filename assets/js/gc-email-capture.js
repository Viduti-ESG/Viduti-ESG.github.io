/**
 * Green Curve — Email Capture Widget
 * Shows a non-intrusive bottom banner after a tool result is displayed.
 * Not shown to logged-in users or to users who already dismissed or subscribed.
 *
 * Usage:
 *   GcEmailCapture.show({ title: '...', body: '...', delay: 4000 });
 *   GcEmailCapture.triggerOnEvent(eventName); // fires show() when that DOM event fires
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'gc_email_cap_done';
  const API_PATH    = '/api/auth/waitlist'; // gracefully handled even if not implemented

  function _isDone() {
    return !!localStorage.getItem(STORAGE_KEY);
  }

  function _isLoggedIn() {
    try {
      return typeof gcAuth !== 'undefined' && gcAuth.isLoggedIn();
    } catch { return false; }
  }

  function _buildBanner(opts) {
    const el = document.createElement('div');
    el.id = 'gc-email-cap';
    Object.assign(el.style, {
      position: 'fixed', bottom: '0', left: '0', right: '0',
      background: '#0e1420',
      borderTop: '1px solid rgba(52,211,153,.25)',
      padding: '14px 20px',
      display: 'flex', alignItems: 'center', gap: '14px',
      zIndex: '8500',
      fontFamily: "'DM Sans', sans-serif",
      boxShadow: '0 -8px 32px rgba(0,0,0,.5)',
      flexWrap: 'wrap',
      transform: 'translateY(100%)',
      transition: 'transform .35s cubic-bezier(.22,1,.36,1)',
    });

    el.innerHTML = `
      <div style="flex:1;min-width:200px">
        <strong style="display:block;font-size:.88rem;color:#e2e8f0;margin-bottom:2px">${opts.title}</strong>
        <span style="font-size:.78rem;color:rgba(226,232,240,.6)">${opts.body}</span>
      </div>
      <form id="gc-cap-form" style="display:flex;gap:8px;flex-shrink:0" onsubmit="return false">
        <input id="gc-cap-email" type="email" placeholder="your@email.com" required
          style="padding:8px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.06);color:#e2e8f0;font-size:.82rem;width:210px;font-family:inherit"/>
        <button id="gc-cap-btn" type="submit"
          style="background:#34d399;color:#000;border:none;padding:8px 16px;border-radius:8px;font-size:.82rem;font-weight:700;cursor:pointer;white-space:nowrap;font-family:inherit">
          Notify Me
        </button>
      </form>
      <button onclick="window.GcEmailCapture.dismiss()" aria-label="Close"
        style="background:none;border:none;color:rgba(226,232,240,.4);font-size:1.1rem;cursor:pointer;padding:4px;line-height:1;flex-shrink:0">✕</button>
    `;

    document.body.appendChild(el);
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        el.style.transform = 'translateY(0)';
      });
    });

    document.getElementById('gc-cap-form').addEventListener('submit', function () {
      const email = document.getElementById('gc-cap-email').value.trim();
      if (!email) return;
      const btn = document.getElementById('gc-cap-btn');
      btn.textContent = '...';
      btn.disabled = true;

      fetch(API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, source: opts.source || document.title }),
      }).catch(function () {})
        .finally(function () {
          localStorage.setItem(STORAGE_KEY, '1');
          const form = document.getElementById('gc-cap-form');
          if (form) form.innerHTML = '<span style="color:#34d399;font-size:.85rem;font-weight:600">✓ Saved! We\'ll keep you posted.</span>';
          setTimeout(function () { window.GcEmailCapture.dismiss(); }, 2800);
        });
    });

    return el;
  }

  let _timer = null;

  const GcEmailCapture = {
    show: function (opts) {
      if (_isDone() || _isLoggedIn()) return;
      if (document.getElementById('gc-email-cap')) return;
      opts = opts || {};
      opts.title  = opts.title  || 'Like what you see? Get ESG updates for your sector.';
      opts.body   = opts.body   || 'Weekly digest of ESG scores, BRSR filings, and regulatory alerts.';
      opts.delay  = opts.delay  || 4000;
      if (opts.delay > 0) {
        _timer = setTimeout(function () { _buildBanner(opts); }, opts.delay);
      } else {
        _buildBanner(opts);
      }
    },

    triggerOnEvent: function (eventName, opts) {
      document.addEventListener(eventName, function handler() {
        document.removeEventListener(eventName, handler);
        clearTimeout(_timer);
        opts = opts || {};
        opts.delay = 1200;
        GcEmailCapture.show(opts);
      }, { once: true });
    },

    dismiss: function () {
      localStorage.setItem(STORAGE_KEY, '1');
      clearTimeout(_timer);
      const el = document.getElementById('gc-email-cap');
      if (!el) return;
      el.style.transform = 'translateY(100%)';
      setTimeout(function () { el.remove(); }, 380);
    },
  };

  window.GcEmailCapture = GcEmailCapture;
})();
