/**
 * cookie-consent.js — DPDP Act 2023 compliant cookie consent
 * Manages GA4 analytics_storage consent before any tracking fires.
 * Include AFTER the gtag consent default block, BEFORE </body>.
 */
(function () {
  const KEY = 'gc_cookie_consent';
  const stored = localStorage.getItem(KEY);

  if (stored === 'granted') {
    _gcGrant();
    return;
  }

  // If already denied, keep GA4 blocked — nothing more to do.
  if (stored === 'denied') return;

  // First visit — show banner after DOM is ready.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _gcShowBanner);
  } else {
    _gcShowBanner();
  }

  function _gcGrant() {
    if (typeof gtag === 'function') {
      gtag('consent', 'update', { analytics_storage: 'granted' });
    }
  }

  function _gcShowBanner() {
    if (document.getElementById('gc-cookie-banner')) return;

    const banner = document.createElement('div');
    banner.id = 'gc-cookie-banner';
    banner.setAttribute('role', 'dialog');
    banner.setAttribute('aria-label', 'Cookie consent');
    banner.innerHTML =
      '<div class="gc-cb-inner">' +
        '<div class="gc-cb-text">' +
          'We use Google Analytics to understand how our ESG tools are used — no personal data is sold or shared for advertising. ' +
          '<a href="privacy-policy.html">Privacy Policy</a>' +
        '</div>' +
        '<div class="gc-cb-btns">' +
          '<button class="gc-cb-btn gc-cb-btn--accept" onclick="window.gcCookieAccept()">Accept Analytics</button>' +
          '<button class="gc-cb-btn gc-cb-btn--decline" onclick="window.gcCookieDecline()">Decline</button>' +
        '</div>' +
      '</div>';

    // Inline styles so no separate CSS file is required on every page
    banner.style.cssText =
      'position:fixed;bottom:0;left:0;right:0;z-index:9999;' +
      'background:#0c1629;border-top:1px solid rgba(52,211,153,.25);' +
      'padding:14px 24px;font-family:"DM Sans",sans-serif;';

    const style = document.createElement('style');
    style.textContent =
      '.gc-cb-inner{display:flex;align-items:center;gap:20px;max-width:1200px;margin:0 auto;flex-wrap:wrap;}' +
      '.gc-cb-text{flex:1;font-size:.82rem;color:#94a3b8;line-height:1.5;}' +
      '.gc-cb-text a{color:#34d399;text-decoration:none;}' +
      '.gc-cb-text a:hover{text-decoration:underline;}' +
      '.gc-cb-btns{display:flex;gap:10px;flex-shrink:0;}' +
      '.gc-cb-btn{padding:7px 18px;border-radius:8px;font-size:.8rem;font-weight:600;cursor:pointer;border:none;}' +
      '.gc-cb-btn--accept{background:#34d399;color:#03060d;}' +
      '.gc-cb-btn--accept:hover{background:#4ade80;}' +
      '.gc-cb-btn--decline{background:transparent;color:#64748b;border:1px solid rgba(255,255,255,.12);}' +
      '.gc-cb-btn--decline:hover{color:#94a3b8;}' +
      '@media(max-width:600px){.gc-cb-inner{flex-direction:column;align-items:flex-start;gap:12px;}}';

    document.head.appendChild(style);
    document.body.appendChild(banner);
  }

  window.gcCookieAccept = function () {
    localStorage.setItem(KEY, 'granted');
    _gcGrant();
    _gcRemoveBanner();
  };

  window.gcCookieDecline = function () {
    localStorage.setItem(KEY, 'denied');
    _gcRemoveBanner();
  };

  function _gcRemoveBanner() {
    const b = document.getElementById('gc-cookie-banner');
    if (b) b.remove();
  }
})();
