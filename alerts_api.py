"""
Green Curve — Monitoring & Alerts API.
Endpoints under /api/alerts/*

Pillar 5 of the retention ecosystem: turn annual usage into a weekly habit. A
logged-in user gets one personal feed that answers "what changed / what's due?"
aggregated from sources Green Curve already owns or that are official & public:

  - score_change   : a watchlisted company's ESG risk score / tier moved vs the
                     user's acknowledged baseline (Green Curve's own data).
  - high_risk      : a watchlisted company sits in a High/Critical risk tier.
  - regulatory     : SEBI/BEE/CPCB etc. events from assets/data/esg_events.json
                     that touch the user's watchlist sectors/companies.
  - filing_deadline: the user's BRSR reports due soon or overdue (not yet final).
  - task_due       : collaboration tasks assigned to the user, due soon/overdue.

LEGAL (defamation guardrail): alerts only surface facts from official/public
sources (SEBI/BEE/CPCB filings & Green Curve's own scores), state them neutrally,
and link to the source. No adverse-media scraping, no editorialising — the same
discipline that kept the Adverse Media Monitor out of scope.
"""

import json
import logging
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import get_conn
from auth_api import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

BASE_DIR = Path(__file__).parent
EVENTS_FILE = BASE_DIR / "assets" / "data" / "esg_events.json"

DEADLINE_SOON_DAYS = 30   # BRSR filing deadline window
TASK_SOON_DAYS     = 7    # task due window
EVENT_RECENT_DAYS  = 75   # how far back regulatory events stay in the feed

DEFAULT_PREFS = {
    "score_change": True, "high_risk": True, "regulatory": True,
    "filing_deadline": True, "task_due": True,
    "digest_email": False, "digest_freq": "weekly",   # weekly|daily
}


# ── Schema ──────────────────────────────────────────────────────────────────────
def init_alerts_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS alert_prefs (
                user_id      INTEGER PRIMARY KEY,
                prefs_json   TEXT     DEFAULT '{}',
                last_seen_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            -- Acknowledged baseline of each watched company's score/tier, so a
            -- change is alerted once and cleared when the user acknowledges it.
            CREATE TABLE IF NOT EXISTS alert_baseline (
                user_id        INTEGER NOT NULL,
                company_name   TEXT    NOT NULL,
                esg_risk_score REAL    DEFAULT 0,
                risk_tier      TEXT    DEFAULT '',
                captured_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, company_name),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)


init_alerts_db()


# ── Helpers ──────────────────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).date() if "T" in s or " " in s else datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _get_prefs(conn, user_id: int) -> dict:
    row = conn.execute("SELECT prefs_json, last_seen_at FROM alert_prefs WHERE user_id=?", (user_id,)).fetchone()
    prefs = dict(DEFAULT_PREFS)
    last_seen = None
    if row:
        try:
            prefs.update(json.loads(row["prefs_json"] or "{}"))
        except Exception:
            pass
        last_seen = row["last_seen_at"]
    return prefs, last_seen


_events_cache = {"mtime": 0, "events": []}

def _load_events() -> list:
    try:
        mtime = EVENTS_FILE.stat().st_mtime
        if mtime != _events_cache["mtime"]:
            with open(EVENTS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            _events_cache["events"] = data.get("events", data) if isinstance(data, dict) else data
            _events_cache["mtime"] = mtime
    except Exception:
        logger.warning("Could not load esg_events.json")
        return []
    return _events_cache["events"]


def _watchlist(conn, user_id: int) -> list:
    rows = conn.execute("SELECT company_name FROM watchlist WHERE user_id=?", (user_id,)).fetchall()
    return [r["company_name"] for r in rows]


def _company_map(conn, names: list) -> dict:
    if not names:
        return {}
    qmarks = ",".join("?" * len(names))
    rows = conn.execute(
        f"SELECT company_name, sector, esg_risk_score, risk_tier FROM companies WHERE company_name IN ({qmarks})",
        names,
    ).fetchall()
    return {r["company_name"]: dict(r) for r in rows}


# ── Alert builders ────────────────────────────────────────────────────────────────
def _build_feed(conn, user: dict, prefs: dict) -> list:
    uid = user["id"]
    alerts = []
    watch = _watchlist(conn, uid)
    cmap = _company_map(conn, watch)

    # baselines for change detection
    base_rows = conn.execute(
        "SELECT company_name, esg_risk_score, risk_tier FROM alert_baseline WHERE user_id=?", (uid,)
    ).fetchall()
    baselines = {r["company_name"]: dict(r) for r in base_rows}

    # 1) score / tier changes vs acknowledged baseline
    if prefs.get("score_change"):
        for name in watch:
            c = cmap.get(name)
            if not c:
                continue
            b = baselines.get(name)
            if not b:
                continue  # first sight establishes baseline on /ack — no alert yet
            cur_s, cur_t = round(float(c["esg_risk_score"] or 0), 1), (c["risk_tier"] or "")
            old_s, old_t = round(float(b["esg_risk_score"] or 0), 1), (b["risk_tier"] or "")
            if cur_s != old_s or cur_t != old_t:
                # esg_risk_score is a RISK score: higher = worse.
                worsened = cur_s > old_s or (cur_t != old_t and _tier_rank(cur_t) > _tier_rank(old_t))
                alerts.append({
                    "id": f"score:{name}",
                    "type": "score_change",
                    "severity": "high" if worsened else "info",
                    "title": f"{name}: ESG risk {'rose' if worsened else 'eased'}",
                    "detail": (f"Risk score {old_s} → {cur_s}"
                               + (f", tier {old_t} → {cur_t}" if old_t != cur_t else "")
                               + ". Based on Green Curve's analysis of public BRSR filings."),
                    "company": name,
                    "source": "Green Curve",
                    "reference": "",
                    "date": _today().isoformat(),
                    "link": f"/esg-intelligence?company={_slug(name)}",
                })

    # 2) high-risk watchlist companies
    if prefs.get("high_risk"):
        for name in watch:
            c = cmap.get(name)
            if c and (c["risk_tier"] or "") in ("High", "Critical", "Severe"):
                alerts.append({
                    "id": f"highrisk:{name}",
                    "type": "high_risk",
                    "severity": "medium",
                    "title": f"{name} is in the {c['risk_tier']} risk tier",
                    "detail": f"Current ESG risk score {round(float(c['esg_risk_score'] or 0),1)} ({c.get('sector','')}).",
                    "company": name,
                    "source": "Green Curve",
                    "reference": "",
                    "date": _today().isoformat(),
                    "link": f"/esg-intelligence?company={_slug(name)}",
                })

    # 3) regulatory / official events relevant to the user
    if prefs.get("regulatory"):
        watch_sectors = {(cmap[n]["sector"] or "") for n in watch if n in cmap}
        cutoff = _today()
        for e in _load_events():
            ed = _parse_date(e.get("date", ""))
            if ed and (cutoff - ed).days > EVENT_RECENT_DAYS:
                continue
            sectors = e.get("affected_sectors", []) or []
            companies = e.get("companies", []) or []
            relevant = ("All" in sectors
                        or bool(watch_sectors & set(sectors))
                        or bool(set(watch) & set(companies))
                        or not watch)  # no watchlist → show market-wide events
            if not relevant:
                continue
            alerts.append({
                "id": f"event:{e.get('id','')}",
                "type": "regulatory",
                "severity": (e.get("severity", "") or "info").lower(),
                "title": e.get("title", "Regulatory update"),
                "detail": e.get("summary", ""),
                "company": (companies[0] if companies else ""),
                "source": e.get("source", "Official"),
                "reference": e.get("reference", ""),
                "date": e.get("date", ""),
                "link": "/esg-intelligence#controversy",
            })

    # 4) BRSR filing deadlines (the user's own reports)
    if prefs.get("filing_deadline"):
        rows = conn.execute(
            "SELECT id, title, financial_year, filing_deadline, status FROM brsr_reports WHERE user_id=?",
            (uid,),
        ).fetchall()
        for r in rows:
            if (r["status"] or "") == "final":
                continue
            dd = _parse_date(r["filing_deadline"] or "")
            if not dd:
                continue
            days = (dd - _today()).days
            if days > DEADLINE_SOON_DAYS:
                continue
            overdue = days < 0
            alerts.append({
                "id": f"deadline:{r['id']}",
                "type": "filing_deadline",
                "severity": "high" if (overdue or days <= 7) else "medium",
                "title": (f"BRSR overdue: {r['title']}" if overdue
                          else f"BRSR due in {days}d: {r['title']}"),
                "detail": (f"Filing deadline {r['filing_deadline']}"
                           + (f" — {-days} day(s) overdue" if overdue else f" — {days} day(s) left")
                           + f". Status: {r['status']}."),
                "company": "",
                "source": "Your BRSR Workspace",
                "reference": "",
                "date": r["filing_deadline"],
                "link": f"/brsr-workspace?report={r['id']}",
            })

    # 5) tasks assigned to the user
    if prefs.get("task_due"):
        rows = conn.execute(
            "SELECT id, title, due_date, status, resource_type, resource_id FROM collab_tasks "
            "WHERE lower(assignee_email)=lower(?) AND status!='done'",
            (user["email"],),
        ).fetchall()
        for r in rows:
            dd = _parse_date(r["due_date"] or "")
            if not dd:
                continue
            days = (dd - _today()).days
            if days > TASK_SOON_DAYS:
                continue
            overdue = days < 0
            link = "/team"
            if r["resource_type"] == "brsr_report" and r["resource_id"]:
                link = f"/brsr-workspace?report={r['resource_id']}"
            alerts.append({
                "id": f"task:{r['id']}",
                "type": "task_due",
                "severity": "high" if overdue else "medium",
                "title": (f"Task overdue: {r['title']}" if overdue else f"Task due in {days}d: {r['title']}"),
                "detail": f"Due {r['due_date']}. Status: {r['status']}.",
                "company": "",
                "source": "Collaboration",
                "reference": "",
                "date": r["due_date"],
                "link": link,
            })

    _SEV = {"high": 0, "critical": 0, "medium": 1, "info": 2, "low": 2, "": 3}
    alerts.sort(key=lambda a: (_SEV.get(a["severity"], 3), a["date"] or "", a["title"]), reverse=False)
    # within severity, newest first
    alerts.sort(key=lambda a: (_SEV.get(a["severity"], 3), _neg_date(a["date"])))
    return alerts


def _neg_date(s: str):
    d = _parse_date(s)
    return -(d.toordinal()) if d else 0


def _tier_rank(t: str) -> int:
    return {"Low": 1, "Medium": 2, "Moderate": 2, "High": 3, "Critical": 4, "Severe": 4}.get(t, 0)


def _slug(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


# ── Pydantic ───────────────────────────────────────────────────────────────────────
class PrefsIn(BaseModel):
    prefs: dict


# ════════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/alerts/feed")
def alerts_feed(user=Depends(get_current_user)):
    conn = get_conn()
    prefs, last_seen = _get_prefs(conn, user["id"])
    feed = _build_feed(conn, user, prefs)
    ls = _parse_date(last_seen) if last_seen else None
    new_count = 0
    for a in feed:
        ad = _parse_date(a["date"])
        a["is_new"] = bool(ls is None or (ad and ad >= ls) or a["type"] in ("score_change",))
        if a["is_new"]:
            new_count += 1
    return {"alerts": feed, "count": len(feed), "new_count": new_count, "last_seen": last_seen}


@router.get("/api/alerts/prefs")
def get_alert_prefs(user=Depends(get_current_user)):
    prefs, last_seen = _get_prefs(get_conn(), user["id"])
    return {"prefs": prefs, "last_seen": last_seen}


@router.put("/api/alerts/prefs")
def set_alert_prefs(body: PrefsIn, user=Depends(get_current_user)):
    merged = dict(DEFAULT_PREFS)
    merged.update({k: v for k, v in body.prefs.items() if k in DEFAULT_PREFS})
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO alert_prefs (user_id, prefs_json) VALUES (?,?)
               ON CONFLICT(user_id) DO UPDATE SET prefs_json=excluded.prefs_json""",
            (user["id"], json.dumps(merged)),
        )
    return {"ok": True, "prefs": merged}


@router.post("/api/alerts/ack")
def acknowledge(user=Depends(get_current_user)):
    """Mark the feed as seen and snapshot current watchlist scores as the new
    baseline, so resolved score changes stop alerting."""
    conn = get_conn()
    uid = user["id"]
    watch = _watchlist(conn, uid)
    cmap = _company_map(conn, watch)
    with conn:
        conn.execute(
            """INSERT INTO alert_prefs (user_id, prefs_json, last_seen_at)
               VALUES (?, '{}', ?)
               ON CONFLICT(user_id) DO UPDATE SET last_seen_at=excluded.last_seen_at""",
            (uid, _now()),
        )
        for name, c in cmap.items():
            conn.execute(
                """INSERT INTO alert_baseline (user_id, company_name, esg_risk_score, risk_tier, captured_at)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(user_id, company_name)
                   DO UPDATE SET esg_risk_score=excluded.esg_risk_score,
                                 risk_tier=excluded.risk_tier, captured_at=excluded.captured_at""",
                (uid, name, float(c["esg_risk_score"] or 0), c["risk_tier"] or "", _now()),
            )
    return {"ok": True, "baselined": len(cmap)}


@router.get("/api/alerts/digest")
def digest(user=Depends(get_current_user)):
    """Compact digest payload (for an email/cron later). Email delivery is not
    yet wired; this returns the content so it can be sent when it is."""
    conn = get_conn()
    prefs, _ = _get_prefs(conn, user["id"])
    feed = _build_feed(conn, user, prefs)
    high = [a for a in feed if a["severity"] in ("high", "critical")]
    lines = [f"Green Curve — your ESG alerts ({_today().isoformat()})",
             f"{len(feed)} active alert(s), {len(high)} high priority.", ""]
    for a in feed[:20]:
        lines.append(f"[{a['severity'].upper()}] {a['title']} — {a['source']}")
    return {"subject": f"Green Curve ESG alerts — {len(high)} need attention",
            "text": "\n".join(lines), "count": len(feed), "high": len(high)}
