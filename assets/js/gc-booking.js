/*!
 * Green Curve Bookings — embed widget
 * https://greencurve.solutions/bookings
 *
 * Inline embed:
 *   <div data-gc-booking="your-room" style="min-height:640px"></div>
 *   <script src="https://greencurve.solutions/assets/js/gc-booking.js" async></script>
 *
 * Floating button:
 *   <script src="https://greencurve.solutions/assets/js/gc-booking.js" async
 *           data-gc-booking-popup="your-room" data-label="Book a time"></script>
 *
 * Privacy: this script loads no trackers and stores no cookies. The booking
 * surface it embeds is served tracker-free by greencurve.solutions.
 */
(function () {
  "use strict";
  if (window.__gcBookingLoaded) return;
  window.__gcBookingLoaded = true;

  var ORIGIN = "https://greencurve.solutions";
  try {
    // allow self-hosted/staging origins when the script is loaded from one
    var cur = document.currentScript;
    if (cur && cur.src) ORIGIN = new URL(cur.src).origin;
  } catch (e) {}

  function roomUrl(slug) {
    return ORIGIN + "/book/" + encodeURIComponent(slug) + "?embed=1";
  }

  function makeIframe(slug) {
    var f = document.createElement("iframe");
    f.src = roomUrl(slug);
    f.title = "Book a time";
    f.loading = "lazy";
    f.style.cssText = "width:100%;height:100%;min-height:inherit;border:0;border-radius:16px;background:#050e07;";
    f.allow = "clipboard-write";
    return f;
  }

  // ── inline embeds ───────────────────────────────────────────
  function mountInline() {
    var nodes = document.querySelectorAll("[data-gc-booking]:not([data-gc-mounted])");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      el.setAttribute("data-gc-mounted", "1");
      if (!el.style.minHeight) el.style.minHeight = "640px";
      el.appendChild(makeIframe(el.getAttribute("data-gc-booking")));
    }
  }

  // ── floating button + slide-over panel ──────────────────────
  function mountPopup(slug, label) {
    var css = document.createElement("style");
    css.textContent =
      ".gcbk-btn{position:fixed;right:24px;bottom:24px;z-index:99990;display:inline-flex;align-items:center;gap:9px;" +
      "padding:14px 24px;border:none;border-radius:32px;cursor:pointer;background:#22c55e;color:#04110a;" +
      "font:600 15px/1 'DM Sans',system-ui,sans-serif;box-shadow:0 8px 32px rgba(4,17,10,.45),0 0 24px rgba(34,197,94,.35);" +
      "transition:transform .2s cubic-bezier(.22,.61,.36,1),box-shadow .2s}" +
      ".gcbk-btn:hover{transform:translateY(-2px);box-shadow:0 12px 40px rgba(4,17,10,.5),0 0 34px rgba(34,197,94,.5)}" +
      ".gcbk-overlay{position:fixed;inset:0;z-index:99991;background:rgba(2,8,4,.65);backdrop-filter:blur(3px);" +
      "opacity:0;transition:opacity .25s;pointer-events:none}" +
      ".gcbk-overlay.open{opacity:1;pointer-events:auto}" +
      ".gcbk-panel{position:fixed;top:0;right:0;bottom:0;z-index:99992;width:min(460px,100vw);background:#050e07;" +
      "box-shadow:-16px 0 60px rgba(0,0,0,.55);transform:translateX(102%);transition:transform .3s cubic-bezier(.22,.61,.36,1);" +
      "display:flex;flex-direction:column}" +
      ".gcbk-panel.open{transform:none}" +
      ".gcbk-close{position:absolute;top:14px;right:14px;z-index:2;width:34px;height:34px;border-radius:50%;border:1px solid rgba(255,255,255,.15);" +
      "background:rgba(5,14,7,.8);color:#dde4f0;font-size:17px;cursor:pointer;line-height:1}" +
      ".gcbk-panel iframe{flex:1;border:0;width:100%}";
    document.head.appendChild(css);

    var btn = document.createElement("button");
    btn.className = "gcbk-btn";
    btn.type = "button";
    btn.innerHTML =
      '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">' +
      '<rect x="3" y="4" width="18" height="18" rx="3"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>' +
      (label || "Book a time");

    var overlay = document.createElement("div");
    overlay.className = "gcbk-overlay";
    var panel = document.createElement("div");
    panel.className = "gcbk-panel";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", label || "Book a time");
    var close = document.createElement("button");
    close.className = "gcbk-close";
    close.setAttribute("aria-label", "Close");
    close.innerHTML = "&times;";
    panel.appendChild(close);

    var loaded = false;
    function open() {
      if (!loaded) { panel.appendChild(makeIframe(slug)); loaded = true; }
      overlay.classList.add("open");
      panel.classList.add("open");
    }
    function shut() {
      overlay.classList.remove("open");
      panel.classList.remove("open");
    }
    btn.addEventListener("click", open);
    close.addEventListener("click", shut);
    overlay.addEventListener("click", shut);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") shut(); });

    document.body.appendChild(btn);
    document.body.appendChild(overlay);
    document.body.appendChild(panel);
  }

  // capture script attrs now (currentScript is null after async load completes)
  var self = document.currentScript;
  var popupSlug = self && self.getAttribute("data-gc-booking-popup");
  var popupLabel = self && self.getAttribute("data-label");

  function run() {
    mountInline();
    if (popupSlug) mountPopup(popupSlug, popupLabel);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
