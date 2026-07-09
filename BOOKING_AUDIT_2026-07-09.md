# Green Curve Bookings — Security & Quality Audit
**Date:** 2026-07-09 · **Scope:** booking_api.py, book/booking-admin/bookings/booking-legal/app.html, gc-booking.js, booking-sw.js, main.py wiring, deploy/nginx.conf · **Status: all findings fixed & regression-tested (14 new checks + original 18-check E2E pass)**

## Findings fixed in this audit

| # | Severity | Finding | Fix |
|---|----------|---------|-----|
| 1 | **Critical (functional)** | nginx `/book/` location had no `add_header`, so it **inherited `X-Frame-Options: SAMEORIGIN`** — every third-party embed (iframe/widget) would have been blocked in production. | `/book/` now declares its own headers incl. `Content-Security-Policy: frame-ancestors *` and deliberately no XFO. Comment added so it isn't "fixed" back. |
| 2 | **Critical (integrity)** | Double-booking race: clash-check SELECT + INSERT ran in a deferred SQLite transaction; two concurrent requests could both pass the check and both insert. | `BEGIN IMMEDIATE` before the check (write lock up front) + explicit commit/rollback. Verified with a 2-thread live race test → exactly `[201, 409]`. |
| 3 | **High (stored XSS)** | Host-supplied `meeting_link` was rendered as `href` to invitees; a `javascript:` URI would execute in the invitee's browser. | Server-side validation: link must match `^https?://` with no whitespace/quotes; client-side render guard as defense-in-depth. |
| 4 | **High (email header injection)** | Host-controlled strings (room name, event title) and invitee name flow into SMTP subjects/bodies; CR/LF could inject headers (e.g. `Bcc:`). | `_clean_text()` strips control chars at every write boundary; `_send_mail()` additionally flattens CR/LF in subject and takes only the first line of the To address. |
| 5 | **Medium (500 crash)** | Deleting a session type with any booking history hit the FK on `booking_bookings.event_type_id` → 500. | Archive (`is_active=0`) when history exists, delete only when clean; Studio shows the explanation. Room deletion now deletes children in explicit order (bookings → event types → availability → blackouts → room) to avoid cascade-order FK trips. |
| 6 | **Medium (DoS/memory)** | In-memory rate-limit buckets were never pruned (unbounded growth on the 1 GB VM); `/slots` (the costliest public endpoint) had no throttle. | 5-minute sweep of idle buckets; `/slots` limited to 40/min/IP (verified: 429 fires under burst). |
| 7 | **Medium (validation)** | `contact_email` accepted any string — booking notifications could be misdirected/undeliverable. | Email-format validation on create and patch; falls back to owner's account email. |
| 8 | **Low (correctness)** | Overlapping availability windows emitted duplicate slots. | Slot engine dedupes by start time and returns sorted slots (regression-tested). |
| 9 | **Low (compliance)** | 180-day PII purge only ran on new public bookings — a quiet room might never purge. Also `time.monotonic()` gate could skip the first purge just after boot. | Purge now also runs from host booking-list views, gated to hourly, with a `None` sentinel for the first run. Verified: pre-2026 booking anonymised to `(erased)` / `erased@retention.local`. |
| 10 | **Low (a11y — WCAG)** | `--text-40` (40 % alpha) small print measured ≈ 3.0:1 contrast on `--void` — fails WCAG AA 4.5:1. Same failure class as the 2026-06-30 gated-pages incident. | Token raised to 55 % alpha (≈ 4.9:1) on all four new pages; hierarchy preserved. |
| 11 | **Low (CORS)** | Studio uses `PUT`/`PATCH` but CORS allow-list only had GET/POST/DELETE — would break for a user on the `www.` origin. | `PUT`, `PATCH` added to `allow_methods`. |

## Verified clean (no action needed)

- **SQL injection:** every query parameterised; no string-built SQL.
- **IDOR / authorization:** all owner endpoints resolve the room through `WHERE owner_user_id=?`; manage/erasure/ICS run off a 24-byte `secrets.token_urlsafe` (192-bit) token; export and host booking lists never expose `manage_token`.
- **XSS in the four new pages:** all dynamic values pass through `esc()` (textContent-based); embed snippets rendered via `textContent`; accent hex comes from a server-side whitelist.
- **Consent gate:** booking without both consents is refused server-side (not just UI); consent timestamp + policy version stored per booking.
- **PII hygiene:** no personal data in server logs; erasure deletes the row; export is the host's own data only; public room endpoint leaks no contact email.
- **Tracker-free claim:** `book.html` and `app.html` load no analytics — matches the legal notice (important: the marketing claim is itself a compliance commitment).
- **Service worker:** never caches `/api/*`; navigations network-first, so stale slots can't be shown offline.
- **Spam/abuse:** honeypot swallows bots silently; booking POST 5/min/IP; room creation 5/min + 5-room/user cap; 12 event types/room cap.
- **Brand:** wordmark accompanies the mark on every page (per brand rule); DM Serif/DM Sans + site palette throughout.

## Recommendations (not blockers, for later)

1. **SMTP**: when configuring `SMTP_*` on the VM, set up SPF/DKIM for the sending domain or confirmations will land in spam.
2. **Cloudflare edge rate-limit rule** on `/api/booking/public/*` as belt-and-braces above the in-process limiter (which is per-worker and resets on restart).
3. `greencurve.db` now holds invitee PII — confirm `deploy/backup_db.sh` cron is active and backups are retained securely.
4. The base `icon-512.png`/`apple-touch-icon.png` are flattened on white; app icons were regenerated with proper alpha, but the site's own icons could use the same treatment eventually.
