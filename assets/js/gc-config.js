/*
 * Green Curve — global frontend config. MUST load before any app script.
 *
 * Single source of truth for the AI backend (brsr-generator) base URL.
 * Previously every call site fell back to '' when localStorage.gc_api_base was
 * unset, which meant AI features were broken-by-default for normal visitors and
 * only worked after manually pointing localStorage at an ephemeral tunnel URL.
 *
 * Now the default is the page's own origin. nginx fans each /api/ request out
 * to the correct backend by path (AI-only endpoints → :8001, the rest → :8000),
 * so a same-origin base "just works" for every AI feature with no CORS. Using
 * the absolute origin (rather than '') also keeps the value truthy, so the many
 * `if (apiBase) { ...call AI... }` guards across the app actually fire instead
 * of silently skipping. localStorage still wins so developers can point at
 * http://localhost:8002 etc. during local dev.
 */
(function () {
  var override = '';
  try { override = localStorage.getItem('gc_api_base') || ''; } catch (_) {}
  // window._gcApiBase is what nearly every call site reads first.
  window._gcApiBase = override || window.location.origin;
  // Helper for any code that wants the resolved base explicitly.
  window.gcApiBase = function () { return window._gcApiBase; };
})();
