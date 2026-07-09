/* Green Curve Bookings — service worker
 * Scope: "/" (served from origin root). Gives the app an install banner on the
 * web and a graceful offline screen. Deliberately network-first: the booking
 * data must always be live, so we never serve stale slots or bookings.
 */
const VERSION = "gcbk-v1";
const SHELL = "gcbk-shell-" + VERSION;

// Static app-shell assets safe to pre-cache (never API responses).
const SHELL_ASSETS = [
  "/app",
  "/offline",
  "/assets/img/app-icon-192.png",
  "/assets/img/app-icon-512.png",
  "/assets/img/favicon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL).then((c) => c.addAll(SHELL_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Never cache API, auth or booking data — always go to network.
  if (url.pathname.startsWith("/api/") || url.pathname === "/health") return;

  // Navigations: network-first, fall back to cached shell / offline page.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() =>
        caches.match(req).then((hit) => hit || caches.match("/offline"))
      )
    );
    return;
  }

  // Same-origin static assets: cache-first with background refresh.
  if (url.origin === self.location.origin && /\.(png|svg|css|js|webmanifest|woff2?)$/.test(url.pathname)) {
    event.respondWith(
      caches.match(req).then((hit) => {
        const net = fetch(req)
          .then((res) => {
            if (res && res.status === 200) {
              const copy = res.clone();
              caches.open(SHELL).then((c) => c.put(req, copy));
            }
            return res;
          })
          .catch(() => hit);
        return hit || net;
      })
    );
  }
});
