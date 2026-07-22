"""
Green Curve — Bookings API  (Calendly-class scheduling, multi-tenant "Rooms")

A Room is a private branded booking space (e.g. "ABC Academy") owned by a
registered Green Curve user. Each room gets a clean shareable link
(/book/{slug}) that can also be embedded on any third-party website.

Compliance posture (DPDP Act 2023 / IT Act SPDI / GDPR-aligned):
  - Explicit, recorded consent (checkbox + timestamp + policy version) before
    any invitee PII is stored. Booking is refused without it.
  - Data minimisation: name, email, optional notes only. No trackers on the
    public booking surface.
  - Invitee rights: secure manage link (access), cancel, and one-click
    erasure of their personal data.
  - Host rights: full JSON export (portability) and room deletion.
  - Automatic PII anonymisation 180 days after the meeting ends.
  - Roles: the room host is the Data Fiduciary for invitee data; Green Curve
    acts as the platform/processor. See /booking-legal.

Endpoints: /api/booking/*  (owner endpoints require the standard JWT bearer)
"""

import logging
import os
import re
import secrets
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo, available_timezones

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field

import mailer
from auth_api import get_current_user
from db import get_conn

logger = logging.getLogger("greencurve.booking")

router = APIRouter(prefix="/api/booking", tags=["booking"])

SITE_URL       = os.environ.get("GC_SITE_URL", "https://greencurve.solutions")
POLICY_VERSION = "GC-BK-1.0 (2026-07-08)"
PII_RETENTION_DAYS = 180          # anonymise invitee PII this long after the meeting
MAX_ROOMS_PER_USER = 5
MAX_EVENT_TYPES_PER_ROOM = 12
MAX_WINDOW_DAYS = 62              # widest slot-search window per request

RESERVED_SLUGS = {
    "api", "book", "bookings", "booking-admin", "booking-legal", "admin",
    "login", "assets", "static", "health", "index", "www", "app", "embed",
    "green-curve", "greencurve", "privacy", "terms", "manage", "new",
}

ACCENTS = {   # curated on-dark palette (all AA against #050e07)
    "curve":   "#22c55e",
    "emerald": "#34d399",
    "gold":    "#d4a843",
    "violet":  "#818cf8",
    "teal":    "#2dd4bf",
    "amber":   "#fbbf24",
}

LOCATION_TYPES = {"video", "phone", "in_person"}
_TZ_SET = available_timezones()


# ── Schema ────────────────────────────────────────────────────────────────────
def _ensure_tables():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS booking_rooms (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL,
                name          TEXT    NOT NULL,
                slug          TEXT    UNIQUE NOT NULL,
                tagline       TEXT    DEFAULT '',
                welcome       TEXT    DEFAULT '',
                accent        TEXT    DEFAULT 'curve',
                timezone      TEXT    DEFAULT 'Asia/Kolkata',
                contact_email TEXT    DEFAULT '',
                is_active     INTEGER DEFAULT 1,
                created_at    TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY (owner_user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS booking_event_types (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id             INTEGER NOT NULL,
                title               TEXT    NOT NULL,
                description         TEXT    DEFAULT '',
                duration_minutes    INTEGER NOT NULL DEFAULT 30,
                location_type       TEXT    DEFAULT 'video',
                meeting_link        TEXT    DEFAULT '',
                buffer_minutes      INTEGER DEFAULT 10,
                min_notice_hours    INTEGER DEFAULT 12,
                max_advance_days    INTEGER DEFAULT 60,
                cancellation_policy TEXT    DEFAULT '',
                is_active           INTEGER DEFAULT 1,
                sort_order          INTEGER DEFAULT 0,
                created_at          TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY (room_id) REFERENCES booking_rooms(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS booking_availability (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id     INTEGER NOT NULL,
                day_of_week INTEGER NOT NULL,      -- 0=Mon … 6=Sun
                start_min   INTEGER NOT NULL,      -- minutes from midnight, room tz
                end_min     INTEGER NOT NULL,
                FOREIGN KEY (room_id) REFERENCES booking_rooms(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS booking_blackouts (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                day     TEXT    NOT NULL,          -- YYYY-MM-DD in room tz
                reason  TEXT    DEFAULT '',
                FOREIGN KEY (room_id) REFERENCES booking_rooms(id) ON DELETE CASCADE,
                UNIQUE(room_id, day)
            );

            CREATE TABLE IF NOT EXISTS booking_bookings (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id      TEXT    UNIQUE NOT NULL,
                manage_token   TEXT    UNIQUE NOT NULL,
                room_id        INTEGER NOT NULL,
                event_type_id  INTEGER NOT NULL,
                event_title    TEXT    NOT NULL,
                starts_at_utc  TEXT    NOT NULL,   -- ISO 8601 UTC
                ends_at_utc    TEXT    NOT NULL,
                invitee_name   TEXT    NOT NULL,
                invitee_email  TEXT    NOT NULL,
                invitee_notes  TEXT    DEFAULT '',
                status         TEXT    DEFAULT 'confirmed',   -- confirmed|cancelled
                consent_privacy INTEGER NOT NULL,
                consent_terms   INTEGER NOT NULL,
                consent_at      TEXT   NOT NULL,
                policy_version  TEXT   NOT NULL,
                created_at     TEXT    DEFAULT (datetime('now')),
                cancelled_at   TEXT,
                cancelled_by   TEXT,               -- host|invitee
                pii_erased     INTEGER DEFAULT 0,
                FOREIGN KEY (room_id) REFERENCES booking_rooms(id) ON DELETE CASCADE,
                FOREIGN KEY (event_type_id) REFERENCES booking_event_types(id)
            );

            CREATE INDEX IF NOT EXISTS idx_bk_room_start
                ON booking_bookings(room_id, starts_at_utc);
        """)


_ensure_tables()


# ── Rate limiting (per-IP sliding window) ─────────────────────────────────────
_rl_lock = threading.Lock()
_rl_hits: dict = defaultdict(list)
_rl_last_sweep = 0.0

def _rate_limit(request: Request, key: str, max_hits: int, window_s: int = 60):
    global _rl_last_sweep
    ip = request.client.host if request.client else "unknown"
    bucket = f"{key}:{ip}"
    now = time.monotonic()
    with _rl_lock:
        # periodic sweep so idle buckets don't accumulate forever (1 GB VM)
        if now - _rl_last_sweep > 300:
            _rl_last_sweep = now
            for k in [k for k, v in _rl_hits.items() if not v or now - v[-1] > 600]:
                del _rl_hits[k]
        _rl_hits[bucket] = [t for t in _rl_hits[bucket] if now - t < window_s]
        if len(_rl_hits[bucket]) >= max_hits:
            raise HTTPException(429, "Too many requests. Please try again shortly.")
        _rl_hits[bucket].append(now)


# ── Helpers ───────────────────────────────────────────────────────────────────
_slug_re = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$")

def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    return s

_email_re = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_url_re   = re.compile(r"^https?://[^\s<>\"']+$")

def _clean_text(s: str, max_len: int) -> str:
    """Collapse control characters out of user text before it can reach email
    headers, ICS fields or logs (CR/LF header-injection guard)."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", s).strip()[:max_len]

def _validate_meeting_link(link: str) -> str:
    link = link.strip()
    if link and not _url_re.match(link):
        raise HTTPException(400, "Meeting link must be a plain https:// or http:// URL.")
    return link

def _validate_contact_email(email: str) -> str:
    email = email.strip().lower()
    if email and not _email_re.match(email):
        raise HTTPException(400, "Notification email doesn't look like a valid email address.")
    return email

def _validate_slug(slug: str):
    if not _slug_re.match(slug) or slug in RESERVED_SLUGS:
        raise HTTPException(400, "Link name must be 3-40 chars (a-z, 0-9, hyphens) and not a reserved word.")

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _parse_utc(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

def _room_or_404(conn, slug: str):
    row = conn.execute(
        "SELECT * FROM booking_rooms WHERE slug=? AND is_active=1", (slug,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "This booking room does not exist or is paused.")
    return row

def _owned_room(conn, room_id: int, user_id: int):
    row = conn.execute(
        "SELECT * FROM booking_rooms WHERE id=? AND owner_user_id=?", (room_id, user_id)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Room not found.")
    return row


_purge_gate_lock = threading.Lock()
_purge_last: Optional[float] = None

def _purge_expired_pii():
    """Anonymise invitee PII for meetings that ended > PII_RETENTION_DAYS ago.
    Opportunistic call from read+write endpoints (at most hourly) — keeps the
    retention promise even for quiet rooms, without needing a cron."""
    global _purge_last
    with _purge_gate_lock:
        now = time.monotonic()
        if _purge_last is not None and now - _purge_last < 3600:
            return
        _purge_last = now
    cutoff = _iso(_utc_now() - timedelta(days=PII_RETENTION_DAYS))
    try:
        with get_conn() as conn:
            conn.execute(
                """UPDATE booking_bookings
                   SET invitee_name='(erased)', invitee_email='erased@retention.local',
                       invitee_notes='', pii_erased=1
                   WHERE pii_erased=0 AND ends_at_utc < ?""",
                (cutoff,),
            )
    except Exception:
        logger.exception("PII retention purge failed")


# ── ICS + calendar links ──────────────────────────────────────────────────────
def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

def _build_ics(b: dict, room: dict) -> str:
    start = _parse_utc(b["starts_at_utc"]).strftime("%Y%m%dT%H%M%SZ")
    end   = _parse_utc(b["ends_at_utc"]).strftime("%Y%m%dT%H%M%SZ")
    stamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    desc  = f"Booked via Green Curve Bookings — {room['name']}."
    if b.get("meeting_link"):
        desc += f"\\nJoin: {b['meeting_link']}"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Green Curve//Bookings//EN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{b['public_id']}@greencurve.solutions",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{start}",
        f"DTEND:{end}",
        f"SUMMARY:{_ics_escape(b['event_title'])} — {_ics_escape(room['name'])}",
        f"DESCRIPTION:{desc}",
        f"LOCATION:{_ics_escape(b.get('meeting_link') or room['name'])}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"

def _google_cal_url(b: dict, room: dict) -> str:
    start = _parse_utc(b["starts_at_utc"]).strftime("%Y%m%dT%H%M%SZ")
    end   = _parse_utc(b["ends_at_utc"]).strftime("%Y%m%dT%H%M%SZ")
    title = quote(f"{b['event_title']} — {room['name']}")
    details = quote("Booked via Green Curve Bookings.")
    return (f"https://calendar.google.com/calendar/render?action=TEMPLATE"
            f"&text={title}&dates={start}/{end}&details={details}")


# ── Email (Resend — see mailer.py) ─────────────────────────────────────────────
def _send_mail(to_addr: str, subject: str, body: str, ics: Optional[str] = None):
    mailer.send_mail(to_addr, subject, body, ics=ics)


def _fmt_local(b_start_utc: str, tzname: str) -> str:
    dt = _parse_utc(b_start_utc).astimezone(ZoneInfo(tzname))
    return dt.strftime("%A, %d %B %Y at %I:%M %p (%Z)")


def _notify_booked(b: dict, room: dict, host_email: str):
    ics = _build_ics(b, room)
    when = _fmt_local(b["starts_at_utc"], room["timezone"])
    manage = f"{SITE_URL}/book/{room['slug']}?manage={b['manage_token']}"
    _send_mail(
        b["invitee_email"],
        f"Confirmed: {b['event_title']} with {room['name']}",
        f"""Hello {b['invitee_name']},

Your booking is confirmed.

  {b['event_title']} — {room['name']}
  {when}

Manage (view / cancel / reschedule / delete your data):
  {manage}

A calendar invite is attached.

This is a transactional message sent because you booked this slot.
Privacy notice: {SITE_URL}/booking-legal
— Green Curve Bookings""",
        ics=ics,
    )
    _send_mail(
        host_email,
        f"[{room['name']}] New booking: {b['event_title']}",
        f"""New booking in your room "{room['name']}".

  {b['event_title']}
  {when}
  Invitee: {b['invitee_name']} <{b['invitee_email']}>
  Notes:   {b['invitee_notes'] or '—'}

Manage your room: {SITE_URL}/booking-admin
— Green Curve Bookings""",
        ics=ics,
    )


def _notify_cancelled(b: dict, room: dict, host_email: str, by: str):
    when = _fmt_local(b["starts_at_utc"], room["timezone"])
    note = "by the host" if by == "host" else "by the invitee"
    for addr in {b["invitee_email"], host_email}:
        _send_mail(
            addr,
            f"Cancelled: {b['event_title']} — {room['name']}",
            f"""The booking below was cancelled {note}.

  {b['event_title']} — {room['name']}
  {when}

Book a new time: {SITE_URL}/book/{room['slug']}
— Green Curve Bookings""",
        )


# ── Slot engine ───────────────────────────────────────────────────────────────
def _compute_slots(conn, room, et, from_day: date, days: int) -> list:
    """Free slots for one event type, respecting weekly windows, blackouts,
    buffers, minimum notice, advance limit and existing confirmed bookings."""
    tz = ZoneInfo(room["timezone"])
    duration = timedelta(minutes=et["duration_minutes"])
    buffer   = timedelta(minutes=et["buffer_minutes"])
    step     = duration + buffer if buffer.total_seconds() else duration
    min_start = _utc_now() + timedelta(hours=et["min_notice_hours"])
    last_day  = min(
        from_day + timedelta(days=days - 1),
        datetime.now(tz).date() + timedelta(days=et["max_advance_days"]),
    )

    windows = defaultdict(list)   # weekday -> [(start_min, end_min)]
    for w in conn.execute(
        "SELECT day_of_week, start_min, end_min FROM booking_availability WHERE room_id=?",
        (room["id"],),
    ):
        windows[w["day_of_week"]].append((w["start_min"], w["end_min"]))

    blackouts = {
        r["day"] for r in conn.execute(
            "SELECT day FROM booking_blackouts WHERE room_id=?", (room["id"],)
        )
    }

    win_lo = _iso(datetime.combine(from_day, datetime.min.time(), tz) - timedelta(days=1))
    win_hi = _iso(datetime.combine(last_day, datetime.max.time(), tz) + timedelta(days=1))
    busy = [
        (_parse_utc(r["starts_at_utc"]), _parse_utc(r["ends_at_utc"]))
        for r in conn.execute(
            """SELECT starts_at_utc, ends_at_utc FROM booking_bookings
               WHERE room_id=? AND status='confirmed'
                 AND starts_at_utc < ? AND ends_at_utc > ?""",
            (room["id"], win_hi, win_lo),
        )
    ]

    slots, seen = [], set()
    d = from_day
    while d <= last_day:
        if d.isoformat() not in blackouts:
            for start_min, end_min in sorted(windows.get(d.weekday(), [])):
                cursor = datetime.combine(d, datetime.min.time(), tz) + timedelta(minutes=start_min)
                window_end = datetime.combine(d, datetime.min.time(), tz) + timedelta(minutes=end_min)
                while cursor + duration <= window_end:
                    s_utc, e_utc = cursor.astimezone(timezone.utc), (cursor + duration).astimezone(timezone.utc)
                    key = _iso(s_utc)
                    if key not in seen and s_utc >= min_start and not any(
                        s_utc < b_end + buffer and e_utc + buffer > b_start
                        for b_start, b_end in busy
                    ):
                        seen.add(key)   # overlapping windows must not emit duplicates
                        slots.append({"start": key, "end": _iso(e_utc)})
                    cursor += step
        d += timedelta(days=1)
    slots.sort(key=lambda s: s["start"])
    return slots


# ── Pydantic models ───────────────────────────────────────────────────────────
class RoomIn(BaseModel):
    name:     str = Field(min_length=2, max_length=80)
    slug:     str = ""
    tagline:  str = Field(default="", max_length=140)
    welcome:  str = Field(default="", max_length=500)
    accent:   str = "curve"
    timezone: str = "Asia/Kolkata"
    contact_email: str = ""

class RoomPatch(BaseModel):
    name:     Optional[str] = Field(default=None, min_length=2, max_length=80)
    tagline:  Optional[str] = Field(default=None, max_length=140)
    welcome:  Optional[str] = Field(default=None, max_length=500)
    accent:   Optional[str] = None
    timezone: Optional[str] = None
    contact_email: Optional[str] = None
    is_active: Optional[bool] = None

class EventTypeIn(BaseModel):
    title:            str = Field(min_length=2, max_length=80)
    description:      str = Field(default="", max_length=500)
    duration_minutes: int = Field(default=30, ge=10, le=480)
    location_type:    str = "video"
    meeting_link:     str = Field(default="", max_length=300)
    buffer_minutes:   int = Field(default=10, ge=0, le=120)
    min_notice_hours: int = Field(default=12, ge=0, le=336)
    max_advance_days: int = Field(default=60, ge=1, le=365)
    cancellation_policy: str = Field(default="", max_length=600)
    is_active:        bool = True

class AvailabilityWindow(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_min:   int = Field(ge=0, le=1439)
    end_min:     int = Field(ge=1, le=1440)

class AvailabilityIn(BaseModel):
    windows:   list[AvailabilityWindow] = Field(max_length=42)
    blackouts: list[str] = Field(default=[], max_length=120)

class BookIn(BaseModel):
    event_type_id: int
    start:         str                        # UTC ISO from the slots API
    name:          str = Field(min_length=2, max_length=100)
    email:         EmailStr
    notes:         str = Field(default="", max_length=1000)
    consent_privacy: bool
    consent_terms:   bool
    website:       str = ""                   # honeypot — humans leave it empty

class CancelIn(BaseModel):
    reason: str = Field(default="", max_length=300)


def _room_out(r, counts: Optional[dict] = None) -> dict:
    out = {
        "id": r["id"], "name": r["name"], "slug": r["slug"],
        "tagline": r["tagline"], "welcome": r["welcome"],
        "accent": r["accent"], "accent_hex": ACCENTS.get(r["accent"], ACCENTS["curve"]),
        "timezone": r["timezone"], "contact_email": r["contact_email"],
        "is_active": bool(r["is_active"]), "created_at": r["created_at"],
        "url": f"{SITE_URL}/book/{r['slug']}",
    }
    if counts:
        out.update(counts)
    return out

def _et_out(e) -> dict:
    return {
        "id": e["id"], "title": e["title"], "description": e["description"],
        "duration_minutes": e["duration_minutes"], "location_type": e["location_type"],
        "meeting_link": e["meeting_link"], "buffer_minutes": e["buffer_minutes"],
        "min_notice_hours": e["min_notice_hours"], "max_advance_days": e["max_advance_days"],
        "cancellation_policy": e["cancellation_policy"], "is_active": bool(e["is_active"]),
    }


# ══ Owner endpoints ═══════════════════════════════════════════════════════════
@router.post("/rooms", status_code=201)
def create_room(request: Request, body: RoomIn, user=Depends(get_current_user)):
    _rate_limit(request, "room_create", 5)
    slug = body.slug.strip().lower() or _slugify(body.name)
    _validate_slug(slug)
    if body.accent not in ACCENTS:
        raise HTTPException(400, "Unknown accent.")
    if body.timezone not in _TZ_SET:
        raise HTTPException(400, "Unknown timezone.")
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) c FROM booking_rooms WHERE owner_user_id=?", (user["id"],)
    ).fetchone()["c"]
    if n >= MAX_ROOMS_PER_USER:
        raise HTTPException(400, f"Room limit reached ({MAX_ROOMS_PER_USER}).")
    if conn.execute("SELECT 1 FROM booking_rooms WHERE slug=?", (slug,)).fetchone():
        raise HTTPException(409, "That link name is already taken.")
    contact_email = _validate_contact_email(body.contact_email) or user["email"]
    with conn:
        cur = conn.execute(
            """INSERT INTO booking_rooms
               (owner_user_id, name, slug, tagline, welcome, accent, timezone, contact_email)
               VALUES (?,?,?,?,?,?,?,?)""",
            (user["id"], _clean_text(body.name, 80), slug, _clean_text(body.tagline, 140),
             _clean_text(body.welcome, 500), body.accent, body.timezone,
             contact_email),
        )
        room_id = cur.lastrowid
        # sensible defaults so the link works the moment it is created
        for dow in range(5):   # Mon–Fri 10:00–17:00
            conn.execute(
                "INSERT INTO booking_availability (room_id, day_of_week, start_min, end_min) VALUES (?,?,?,?)",
                (room_id, dow, 600, 1020),
            )
        conn.execute(
            """INSERT INTO booking_event_types (room_id, title, description, duration_minutes)
               VALUES (?, '30-minute consultation', 'An introductory conversation.', 30)""",
            (room_id,),
        )
    row = conn.execute("SELECT * FROM booking_rooms WHERE id=?", (room_id,)).fetchone()
    logger.info("Room created: %s (user %s)", slug, user["id"])
    return {"room": _room_out(row)}


@router.get("/rooms")
def list_rooms(user=Depends(get_current_user)):
    conn = get_conn()
    rooms = []
    for r in conn.execute(
        "SELECT * FROM booking_rooms WHERE owner_user_id=? ORDER BY created_at", (user["id"],)
    ):
        counts = conn.execute(
            """SELECT
                 SUM(CASE WHEN status='confirmed' AND starts_at_utc >= ? THEN 1 ELSE 0 END) upcoming,
                 COUNT(*) total
               FROM booking_bookings WHERE room_id=?""",
            (_iso(_utc_now()), r["id"]),
        ).fetchone()
        rooms.append(_room_out(r, {"upcoming": counts["upcoming"] or 0, "total_bookings": counts["total"]}))
    return {"rooms": rooms, "accents": ACCENTS, "policy_version": POLICY_VERSION}


@router.get("/rooms/{room_id}")
def get_room(room_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    r = _owned_room(conn, room_id, user["id"])
    ets = [ _et_out(e) for e in conn.execute(
        "SELECT * FROM booking_event_types WHERE room_id=? ORDER BY sort_order, id", (room_id,)
    )]
    windows = [
        {"day_of_week": w["day_of_week"], "start_min": w["start_min"], "end_min": w["end_min"]}
        for w in conn.execute(
            "SELECT * FROM booking_availability WHERE room_id=? ORDER BY day_of_week, start_min", (room_id,)
        )
    ]
    blackouts = [b["day"] for b in conn.execute(
        "SELECT day FROM booking_blackouts WHERE room_id=? ORDER BY day", (room_id,)
    )]
    return {"room": _room_out(r), "event_types": ets, "windows": windows, "blackouts": blackouts}


@router.patch("/rooms/{room_id}")
def update_room(room_id: int, body: RoomPatch, user=Depends(get_current_user)):
    conn = get_conn()
    r = _owned_room(conn, room_id, user["id"])
    fields, vals = [], []
    _maxlens = {"name": 80, "tagline": 140, "welcome": 500, "contact_email": 200}
    for col in ("name", "tagline", "welcome", "contact_email"):
        v = getattr(body, col)
        if v is not None:
            if col == "contact_email":
                v = _validate_contact_email(v) or r["contact_email"]
            fields.append(f"{col}=?"); vals.append(_clean_text(v, _maxlens[col]))
    if body.accent is not None:
        if body.accent not in ACCENTS:
            raise HTTPException(400, "Unknown accent.")
        fields.append("accent=?"); vals.append(body.accent)
    if body.timezone is not None:
        if body.timezone not in _TZ_SET:
            raise HTTPException(400, "Unknown timezone.")
        fields.append("timezone=?"); vals.append(body.timezone)
    if body.is_active is not None:
        fields.append("is_active=?"); vals.append(1 if body.is_active else 0)
    if fields:
        with conn:
            conn.execute(f"UPDATE booking_rooms SET {', '.join(fields)} WHERE id=?", (*vals, room_id))
    row = conn.execute("SELECT * FROM booking_rooms WHERE id=?", (room_id,)).fetchone()
    return {"room": _room_out(row)}


@router.delete("/rooms/{room_id}")
def delete_room(room_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    _owned_room(conn, room_id, user["id"])
    # Delete children before parents explicitly: bookings reference event types
    # without CASCADE, so relying on the room cascade alone can trip that FK.
    with conn:
        conn.execute("DELETE FROM booking_bookings WHERE room_id=?", (room_id,))
        conn.execute("DELETE FROM booking_event_types WHERE room_id=?", (room_id,))
        conn.execute("DELETE FROM booking_availability WHERE room_id=?", (room_id,))
        conn.execute("DELETE FROM booking_blackouts WHERE room_id=?", (room_id,))
        conn.execute("DELETE FROM booking_rooms WHERE id=?", (room_id,))
    logger.info("Room %s deleted by user %s", room_id, user["id"])
    return {"ok": True}


@router.post("/rooms/{room_id}/event-types", status_code=201)
def create_event_type(room_id: int, body: EventTypeIn, user=Depends(get_current_user)):
    conn = get_conn()
    _owned_room(conn, room_id, user["id"])
    if body.location_type not in LOCATION_TYPES:
        raise HTTPException(400, "Unknown location type.")
    meeting_link = _validate_meeting_link(body.meeting_link)
    n = conn.execute(
        "SELECT COUNT(*) c FROM booking_event_types WHERE room_id=?", (room_id,)
    ).fetchone()["c"]
    if n >= MAX_EVENT_TYPES_PER_ROOM:
        raise HTTPException(400, f"Event-type limit reached ({MAX_EVENT_TYPES_PER_ROOM}).")
    with conn:
        cur = conn.execute(
            """INSERT INTO booking_event_types
               (room_id, title, description, duration_minutes, location_type, meeting_link,
                buffer_minutes, min_notice_hours, max_advance_days, cancellation_policy, is_active)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (room_id, _clean_text(body.title, 80), _clean_text(body.description, 500),
             body.duration_minutes, body.location_type, meeting_link, body.buffer_minutes,
             body.min_notice_hours, body.max_advance_days,
             _clean_text(body.cancellation_policy, 600),
             1 if body.is_active else 0),
        )
    row = conn.execute("SELECT * FROM booking_event_types WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"event_type": _et_out(row)}


@router.put("/rooms/{room_id}/event-types/{et_id}")
def update_event_type(room_id: int, et_id: int, body: EventTypeIn, user=Depends(get_current_user)):
    conn = get_conn()
    _owned_room(conn, room_id, user["id"])
    if body.location_type not in LOCATION_TYPES:
        raise HTTPException(400, "Unknown location type.")
    meeting_link = _validate_meeting_link(body.meeting_link)
    with conn:
        cur = conn.execute(
            """UPDATE booking_event_types SET
                 title=?, description=?, duration_minutes=?, location_type=?, meeting_link=?,
                 buffer_minutes=?, min_notice_hours=?, max_advance_days=?, cancellation_policy=?, is_active=?
               WHERE id=? AND room_id=?""",
            (_clean_text(body.title, 80), _clean_text(body.description, 500),
             body.duration_minutes, body.location_type, meeting_link, body.buffer_minutes,
             body.min_notice_hours, body.max_advance_days,
             _clean_text(body.cancellation_policy, 600),
             1 if body.is_active else 0, et_id, room_id),
        )
    if cur.rowcount == 0:
        raise HTTPException(404, "Event type not found.")
    row = conn.execute("SELECT * FROM booking_event_types WHERE id=?", (et_id,)).fetchone()
    return {"event_type": _et_out(row)}


@router.delete("/rooms/{room_id}/event-types/{et_id}")
def delete_event_type(room_id: int, et_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    _owned_room(conn, room_id, user["id"])
    # Bookings keep a foreign key to their event type (the audit trail needs it),
    # so a type with any booking history is archived instead of deleted.
    has_bookings = conn.execute(
        "SELECT 1 FROM booking_bookings WHERE event_type_id=? LIMIT 1", (et_id,)
    ).fetchone()
    with conn:
        if has_bookings:
            cur = conn.execute(
                "UPDATE booking_event_types SET is_active=0 WHERE id=? AND room_id=?",
                (et_id, room_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(404, "Event type not found.")
            return {"ok": True, "archived": True,
                    "message": "This session has booking history, so it was closed for new bookings instead of deleted."}
        cur = conn.execute(
            "DELETE FROM booking_event_types WHERE id=? AND room_id=?", (et_id, room_id)
        )
    if cur.rowcount == 0:
        raise HTTPException(404, "Event type not found.")
    return {"ok": True}


@router.put("/rooms/{room_id}/availability")
def set_availability(room_id: int, body: AvailabilityIn, user=Depends(get_current_user)):
    conn = get_conn()
    _owned_room(conn, room_id, user["id"])
    for w in body.windows:
        if w.end_min <= w.start_min:
            raise HTTPException(400, "A window must end after it starts.")
    day_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for d in body.blackouts:
        if not day_re.match(d):
            raise HTTPException(400, f"Bad blackout date: {d}")
    with conn:
        conn.execute("DELETE FROM booking_availability WHERE room_id=?", (room_id,))
        conn.execute("DELETE FROM booking_blackouts WHERE room_id=?", (room_id,))
        for w in body.windows:
            conn.execute(
                "INSERT INTO booking_availability (room_id, day_of_week, start_min, end_min) VALUES (?,?,?,?)",
                (room_id, w.day_of_week, w.start_min, w.end_min),
            )
        for d in body.blackouts:
            conn.execute(
                "INSERT OR IGNORE INTO booking_blackouts (room_id, day) VALUES (?,?)", (room_id, d)
            )
    return {"ok": True}


@router.get("/rooms/{room_id}/bookings")
def list_bookings(room_id: int, scope: str = "upcoming", user=Depends(get_current_user)):
    _purge_expired_pii()   # retention holds even if no new bookings arrive
    conn = get_conn()
    _owned_room(conn, room_id, user["id"])
    now = _iso(_utc_now())
    if scope == "upcoming":
        q, args = ("status='confirmed' AND starts_at_utc >= ?", (now,))
    elif scope == "past":
        q, args = ("status='confirmed' AND starts_at_utc < ?", (now,))
    elif scope == "cancelled":
        q, args = ("status='cancelled'", ())
    else:
        q, args = ("1=1", ())
    rows = conn.execute(
        f"""SELECT public_id, event_title, starts_at_utc, ends_at_utc, invitee_name,
                   invitee_email, invitee_notes, status, created_at, cancelled_at,
                   cancelled_by, consent_at, policy_version, pii_erased
            FROM booking_bookings WHERE room_id=? AND {q}
            ORDER BY starts_at_utc {'DESC' if scope in ('past', 'cancelled') else 'ASC'} LIMIT 500""",
        (room_id, *args),
    ).fetchall()
    return {"bookings": [dict(r) for r in rows]}


@router.post("/rooms/{room_id}/bookings/{public_id}/cancel")
def host_cancel(room_id: int, public_id: str, body: CancelIn,
                background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    conn = get_conn()
    room = _owned_room(conn, room_id, user["id"])
    b = conn.execute(
        "SELECT * FROM booking_bookings WHERE public_id=? AND room_id=? AND status='confirmed'",
        (public_id, room_id),
    ).fetchone()
    if not b:
        raise HTTPException(404, "Booking not found or already cancelled.")
    with conn:
        conn.execute(
            "UPDATE booking_bookings SET status='cancelled', cancelled_at=?, cancelled_by='host' WHERE id=?",
            (_iso(_utc_now()), b["id"]),
        )
    background_tasks.add_task(_notify_cancelled, dict(b), dict(room), room["contact_email"], "host")
    return {"ok": True}


@router.get("/rooms/{room_id}/export")
def export_room(room_id: int, user=Depends(get_current_user)):
    """DPDP portability — full machine-readable export of the room's data."""
    conn = get_conn()
    data = get_room(room_id, user)          # reuses ownership check
    rows = conn.execute(
        "SELECT * FROM booking_bookings WHERE room_id=? ORDER BY starts_at_utc", (room_id,)
    ).fetchall()
    data["bookings"] = [
        {k: r[k] for k in r.keys() if k not in ("id", "manage_token")} for r in rows
    ]
    data["exported_at"] = _iso(_utc_now())
    data["policy_version"] = POLICY_VERSION
    return data


# ══ Public endpoints (no auth — the booking surface) ══════════════════════════
@router.get("/public/{slug}")
def public_room(slug: str):
    conn = get_conn()
    room = _room_or_404(conn, slug)
    ets = [ _et_out(e) for e in conn.execute(
        "SELECT * FROM booking_event_types WHERE room_id=? AND is_active=1 ORDER BY sort_order, id",
        (room["id"],),
    )]
    return {
        "room": {
            "name": room["name"], "slug": room["slug"], "tagline": room["tagline"],
            "welcome": room["welcome"], "accent": room["accent"],
            "accent_hex": ACCENTS.get(room["accent"], ACCENTS["curve"]),
            "timezone": room["timezone"],
        },
        "event_types": [
            {k: v for k, v in e.items() if k != "meeting_link"} for e in ets
        ],
        "policy_version": POLICY_VERSION,
    }


@router.get("/public/{slug}/slots")
def public_slots(request: Request, slug: str, event_type_id: int, start: str = "", days: int = 31):
    _rate_limit(request, "slots", 40)   # CPU guard — slot computation is the costliest public call
    conn = get_conn()
    room = _room_or_404(conn, slug)
    et = conn.execute(
        "SELECT * FROM booking_event_types WHERE id=? AND room_id=? AND is_active=1",
        (event_type_id, room["id"]),
    ).fetchone()
    if not et:
        raise HTTPException(404, "Event type not found.")
    try:
        from_day = date.fromisoformat(start) if start else datetime.now(ZoneInfo(room["timezone"])).date()
    except ValueError:
        raise HTTPException(400, "start must be YYYY-MM-DD")
    days = max(1, min(days, MAX_WINDOW_DAYS))
    return {
        "timezone": room["timezone"],
        "slots": _compute_slots(conn, room, et, from_day, days),
    }


@router.post("/public/{slug}/book", status_code=201)
def public_book(slug: str, request: Request, body: BookIn, background_tasks: BackgroundTasks):
    _rate_limit(request, "book", 5)
    if body.website.strip():                      # honeypot tripped — swallow silently
        return {"booking": {"public_id": "ok"}}
    if not (body.consent_privacy and body.consent_terms):
        raise HTTPException(
            400, "Consent to the privacy notice and booking terms is required to book."
        )
    conn = get_conn()
    room = _room_or_404(conn, slug)
    et = conn.execute(
        "SELECT * FROM booking_event_types WHERE id=? AND room_id=? AND is_active=1",
        (body.event_type_id, room["id"]),
    ).fetchone()
    if not et:
        raise HTTPException(404, "Event type not found.")
    try:
        start_utc = _parse_utc(body.start)
    except ValueError:
        raise HTTPException(400, "start must be UTC ISO (YYYY-MM-DDTHH:MM:SSZ)")
    end_utc = start_utc + timedelta(minutes=et["duration_minutes"])

    # the requested slot must be one the engine would offer right now
    tz = ZoneInfo(room["timezone"])
    day_local = start_utc.astimezone(tz).date()
    offered = _compute_slots(conn, room, et, day_local, 1)
    if _iso(start_utc) not in {s["start"] for s in offered}:
        raise HTTPException(409, "That slot is no longer available. Please pick another time.")

    now_iso = _iso(_utc_now())
    invitee_name  = _clean_text(body.name, 100)
    invitee_notes = _clean_text(body.notes, 1000)
    # BEGIN IMMEDIATE takes SQLite's write lock *before* the clash check, so two
    # concurrent requests for the same slot serialize instead of both passing
    # the SELECT and both inserting (deferred transactions lock only on write).
    conn.execute("BEGIN IMMEDIATE")
    try:
        clash = conn.execute(
            """SELECT 1 FROM booking_bookings
               WHERE room_id=? AND status='confirmed'
                 AND starts_at_utc < ? AND ends_at_utc > ?""",
            (room["id"], _iso(end_utc), _iso(start_utc)),
        ).fetchone()
        if clash:
            raise HTTPException(409, "That slot was just taken. Please pick another time.")
        public_id    = secrets.token_urlsafe(9)
        manage_token = secrets.token_urlsafe(24)
        conn.execute(
            """INSERT INTO booking_bookings
               (public_id, manage_token, room_id, event_type_id, event_title,
                starts_at_utc, ends_at_utc, invitee_name, invitee_email, invitee_notes,
                consent_privacy, consent_terms, consent_at, policy_version)
               VALUES (?,?,?,?,?,?,?,?,?,?,1,1,?,?)""",
            (public_id, manage_token, room["id"], et["id"], et["title"],
             _iso(start_utc), _iso(end_utc), invitee_name, str(body.email).lower(),
             invitee_notes, now_iso, POLICY_VERSION),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    logger.info("Booking %s created in room %s", public_id, slug)   # no PII in logs
    _purge_expired_pii()

    b = {
        "public_id": public_id, "manage_token": manage_token,
        "event_title": et["title"], "starts_at_utc": _iso(start_utc),
        "ends_at_utc": _iso(end_utc), "invitee_name": invitee_name,
        "invitee_email": str(body.email).lower(), "invitee_notes": invitee_notes,
        "meeting_link": et["meeting_link"],
    }
    background_tasks.add_task(_notify_booked, b, dict(room), room["contact_email"])
    return {
        "booking": {
            "public_id": public_id, "manage_token": manage_token,
            "event_title": et["title"], "starts_at_utc": _iso(start_utc),
            "ends_at_utc": _iso(end_utc), "timezone": room["timezone"],
            "room_name": room["name"],
            "ics_url": f"/api/booking/ics/{manage_token}",
            "google_calendar_url": _google_cal_url(b, dict(room)),
            "policy_version": POLICY_VERSION,
        }
    }


def _booking_by_token(conn, manage_token: str):
    b = conn.execute(
        "SELECT * FROM booking_bookings WHERE manage_token=?", (manage_token,)
    ).fetchone()
    if not b:
        raise HTTPException(404, "Booking not found.")
    room = conn.execute("SELECT * FROM booking_rooms WHERE id=?", (b["room_id"],)).fetchone()
    return b, room


@router.get("/manage/{manage_token}")
def manage_view(manage_token: str):
    conn = get_conn()
    b, room = _booking_by_token(conn, manage_token)
    et = conn.execute(
        "SELECT meeting_link, cancellation_policy FROM booking_event_types WHERE id=?",
        (b["event_type_id"],),
    ).fetchone()
    return {
        "booking": {
            "public_id": b["public_id"], "event_title": b["event_title"],
            "starts_at_utc": b["starts_at_utc"], "ends_at_utc": b["ends_at_utc"],
            "invitee_name": b["invitee_name"], "status": b["status"],
            "timezone": room["timezone"], "room_name": room["name"],
            "room_slug": room["slug"],
            "meeting_link": (et["meeting_link"] if et and b["status"] == "confirmed" else ""),
            "cancellation_policy": (et["cancellation_policy"] if et else ""),
            "consent_at": b["consent_at"], "policy_version": b["policy_version"],
            "ics_url": f"/api/booking/ics/{manage_token}",
        }
    }


@router.post("/manage/{manage_token}/cancel")
def manage_cancel(manage_token: str, body: CancelIn, background_tasks: BackgroundTasks):
    conn = get_conn()
    b, room = _booking_by_token(conn, manage_token)
    if b["status"] != "confirmed":
        raise HTTPException(400, "This booking is already cancelled.")
    with conn:
        conn.execute(
            "UPDATE booking_bookings SET status='cancelled', cancelled_at=?, cancelled_by='invitee' WHERE id=?",
            (_iso(_utc_now()), b["id"]),
        )
    background_tasks.add_task(_notify_cancelled, dict(b), dict(room), room["contact_email"], "invitee")
    return {"ok": True}


@router.delete("/manage/{manage_token}/data")
def manage_erase(manage_token: str):
    """DPDP right to erasure — invitee removes their personal data entirely."""
    conn = get_conn()
    b, _room = _booking_by_token(conn, manage_token)
    with conn:
        if b["status"] == "confirmed" and _parse_utc(b["starts_at_utc"]) > _utc_now():
            conn.execute(
                "UPDATE booking_bookings SET status='cancelled', cancelled_at=?, cancelled_by='invitee' WHERE id=?",
                (_iso(_utc_now()), b["id"]),
            )
        conn.execute("DELETE FROM booking_bookings WHERE id=?", (b["id"],))
    logger.info("Erasure request honoured for booking %s", b["public_id"])
    return {"ok": True, "message": "Your booking and personal data have been deleted."}


@router.get("/ics/{manage_token}")
def ics_download(manage_token: str):
    conn = get_conn()
    b, room = _booking_by_token(conn, manage_token)
    et = conn.execute(
        "SELECT meeting_link FROM booking_event_types WHERE id=?", (b["event_type_id"],)
    ).fetchone()
    bd = dict(b)
    bd["meeting_link"] = et["meeting_link"] if et else ""
    return Response(
        content=_build_ics(bd, dict(room)),
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="invite.ics"'},
    )
