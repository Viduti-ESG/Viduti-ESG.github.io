"""
Green Curve — CTAP (Climate Transition Action Plan) builder API.
Endpoints under /api/ctap/*

Turns a company's own ESG data into a structured, framework-aligned Climate
Transition Action Plan. This is the productionised counterpart of the
`writing-ctap` skill: the intake field keys here are the SAME keys the skill's
questionnaire uses, so the skill and this feature share one data model.

Design decisions (chosen with Neha, 2026-07-19):
  - v1 is a STRUCTURED BUILDER, not an AI writer. The server assembles the plan
    on the TPT (Transition Plan Taskforce) five-element framework from the
    client's answers + auto-filled BRSR data, and inserts explicit [GAP] markers
    where data is missing. No LLM call → no per-plan cost and, crucially, no
    fabrication: a missing figure becomes a visible gap, never an invented value.
    (An AI narrative can be layered on later behind the review gate.)
  - DELIVERY IS GC-REVIEWED. A client cannot download a plan until Green Curve
    has reviewed and released it. A CTAP is a public, forward-looking climate
    disclosure — a weak or misleading one is a liability for the client and for
    Green Curve — so a human vets every plan before it leaves the door.

Legal framing (mirrors brsr_workspace_api):
  - The plan contains the customer's OWN company data (same DPDP Data-Fiduciary
    basis as the Data Room / BRSR Workspace).
  - Every plan carries a draft/ownership caveat: forward-looking statements are
    the client's commitments, subject to their approval; the plan is not assured
    and is not a statement of regulatory compliance. Green Curve does NOT rate,
    score, or assure the plan (the not-a-rating-agency fence) — the review only
    checks the draft against a credibility checklist before release.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from db import get_conn
from auth_api import get_current_user, require_admin

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Intake field registry ─────────────────────────────────────────────────────
# (key, human label, expected provenance, TPT section id). Provenance:
#   BRSR = auto-fillable from the company's ESG record; SBTi = check the SBTi
#   dashboard; ASK = only the company can supply it. This mirrors the skill's
#   references/intake-questionnaire.md — keep the keys stable so the form, this
#   API, and the writing-ctap skill stay one shared data model.
FIELDS = [
    ("company_name",         "Legal name",                          "BRSR", "meta"),
    ("sector",               "Primary sector / activity",           "BRSR", "meta"),
    ("reporting_boundary",   "Entities / sites covered by the plan", "ASK",  "meta"),
    ("base_year",            "Baseline year for targets",           "ASK",  "meta"),
    ("net_zero_year",        "Net-zero / headline target year",     "SBTi", "1"),
    ("interim_targets",      "Interim targets (year, scope, % cut)", "SBTi", "1"),
    ("baseline_scope1",      "Baseline Scope 1 emissions",          "BRSR", "1"),
    ("baseline_scope2",      "Baseline Scope 2 emissions",          "BRSR", "1"),
    ("baseline_scope3",      "Baseline Scope 3 emissions",          "BRSR", "1"),
    ("scope3_categories",    "Material Scope 3 categories",         "ASK",  "1"),
    ("ambition_alignment",   "Ambition alignment (1.5C / validated by whom)", "SBTi", "1"),
    ("key_assumptions",      "Key assumptions & external factors",  "ASK",  "1"),
    ("levers",               "Planned decarbonization levers",      "ASK",  "2"),
    ("renewable_plan",       "Renewable electricity plan",          "ASK",  "2"),
    ("capex_plan",           "Transition capex plan",               "ASK",  "2"),
    ("internal_carbon_price", "Internal carbon price",              "ASK",  "2"),
    ("rnd_low_carbon",       "Low-carbon R&D / products",           "ASK",  "2"),
    ("supplier_engagement",  "Supplier decarbonization programme",  "ASK",  "3"),
    ("industry_initiatives", "Industry coalitions / standards",     "ASK",  "3"),
    ("policy_engagement",    "Government / public-sector engagement", "ASK", "3"),
    ("tracked_metrics",      "Metrics tracked against the plan",    "BRSR", "4"),
    ("green_revenue",        "Green revenue (if tracked)",          "ASK",  "4"),
    ("credits_strategy",     "Carbon-credit strategy (residual only)", "ASK", "4"),
    ("board_oversight",      "Board oversight of the transition",   "ASK",  "5"),
    ("exec_accountable",     "Accountable executive(s)",            "ASK",  "5"),
    ("remuneration_link",    "Pay linked to climate KPIs",          "ASK",  "5"),
    ("skills_training",      "Climate skills & training",           "ASK",  "5"),
]
FIELD_KEYS = {k for k, _, _, _ in FIELDS}

SECTIONS = [
    ("1", "Foundations"),
    ("2", "Implementation strategy"),
    ("3", "Engagement strategy"),
    ("4", "Metrics & targets"),
    ("5", "Governance"),
]
SECTION_TITLES = dict(SECTIONS)

CAVEAT = (
    "Draft prepared from company-provided data. All forward-looking statements "
    "are the company's commitments, subject to its review and approval and to "
    "change. This plan is not assured and is not a statement of regulatory "
    "compliance."
)

# Per-field cap so a client can't send unbounded blobs (house rule: bound
# everything a user can send). Answers beyond this are truncated with a marker.
_MAX_FIELD_LEN = 4000

# Status machine.
#   draft             — saved by client, not yet submitted
#   submitted         — queued for Green Curve review
#   in_review         — a reviewer has picked it up
#   changes_requested — sent back to the client to fix
#   released          — reviewed & approved; client can download
_CLIENT_EDITABLE = {"draft", "changes_requested"}
_ADMIN_QUEUE = ("submitted", "in_review")
_VALID_STATUSES = {"draft", "submitted", "in_review", "changes_requested", "released"}


def init_ctap_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ctap_drafts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                company_name  TEXT    DEFAULT '',
                cin           TEXT    DEFAULT '',
                sector        TEXT    DEFAULT '',
                answers_json  TEXT    DEFAULT '{}',
                assembled_json TEXT   DEFAULT '{}',
                status        TEXT    DEFAULT 'draft',
                gap_count     INTEGER DEFAULT 0,
                review_note   TEXT    DEFAULT '',
                reviewed_by   INTEGER,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                released_at   DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            -- Every client list query filters by user_id; the admin queue filters
            -- by status. Without these each read is a full-table scan.
            CREATE INDEX IF NOT EXISTS idx_ctap_user   ON ctap_drafts(user_id);
            CREATE INDEX IF NOT EXISTS idx_ctap_status ON ctap_drafts(status);
        """)


# ── Assembly (server-side port of the skill's ctap_scaffold.py) ────────────────
def _clean(v: Any) -> Optional[str]:
    """Normalise an answer value to a bounded string, or None if empty."""
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        v = "; ".join(str(x) for x in v if str(x).strip())
    s = str(v).strip()
    if not s:
        return None
    if len(s) > _MAX_FIELD_LEN:
        s = s[:_MAX_FIELD_LEN] + " …[truncated]"
    return s


def assemble(answers: Dict[str, Any]) -> Dict[str, Any]:
    """Build the structured, TPT-framework CTAP from intake answers.

    Returns a dict the frontend renders and the download endpoints serialise:
    { title, caveat, meta:[...], sections:[{id,title,items:[...],narrative_hint}],
      gaps:[{key,label,expected_source}], gap_count }.
    Missing fields become gaps + [GAP] items — never invented values.
    """
    company = _clean(answers.get("company_name")) or "[GAP: company_name]"
    meta_items: List[dict] = []
    section_items: Dict[str, List[dict]] = {sid: [] for sid, _ in SECTIONS}
    gaps: List[dict] = []

    for key, label, prov, sec in FIELDS:
        value = _clean(answers.get(key))
        item = {"key": key, "label": label, "provenance": prov, "value": value}
        if value is None:
            gaps.append({"key": key, "label": label, "expected_source": prov})
        (meta_items if sec == "meta" else section_items[sec]).append(item)

    sections = []
    for sid, title in SECTIONS:
        sections.append({
            "id": sid,
            "title": title,
            "items": section_items[sid],
            "narrative_hint": (
                f"Expand each point into {company}'s own voice; ground levers in "
                f"the sector; label every figure filed / stated / estimated / "
                f"illustrative."
            ),
        })

    return {
        "title": f"{company} Climate Transition Action Plan",
        "caveat": CAVEAT,
        "meta": meta_items,
        "sections": sections,
        "gaps": gaps,
        "gap_count": len(gaps),
        "framework": "Transition Plan Taskforce (TPT) five-element framework, "
                     "aligned to IFRS S2; emissions on the GHG Protocol basis.",
    }


def _render_markdown(a: Dict[str, Any]) -> str:
    out = [f"# {a['title']}", "", f"> {a['caveat']}", ""]
    out.append(f"_Structured on the {a['framework']}_")
    out.append("")
    out.append("## Company & boundary")
    for it in a["meta"]:
        out.append(_md_item(it))
    out.append("")
    for sec in a["sections"]:
        out.append(f"## {sec['id']}. {sec['title']}")
        for it in sec["items"]:
            out.append(_md_item(it))
        out.append("")
        out.append(f"_{sec['narrative_hint']}_")
        out.append("")
    out.append("## Data provenance & open items")
    if a["gaps"]:
        out.append(f"**{a['gap_count']} open item(s)** to complete before this "
                   "plan is final:")
        for g in a["gaps"]:
            out.append(f"- `[GAP]` {g['label']} (`{g['key']}`) — expected source: "
                       f"{g['expected_source']}")
    else:
        out.append("No open items — confirm each value's provenance before finalising.")
    return "\n".join(out)


def _md_item(it: dict) -> str:
    if it["value"] is None:
        return f"- **{it['label']}:** `[GAP: {it['key']}]` _(expected source: {it['provenance']})_"
    return f"- **{it['label']}:** {it['value']} _({it['provenance']})_"


# ── Request models ─────────────────────────────────────────────────────────────
class DraftIn(BaseModel):
    company_name: str = Field("", max_length=200)
    cin:          str = Field("", max_length=25)
    sector:       str = Field("", max_length=120)
    answers:      Dict[str, Any] = Field(default_factory=dict)
    submit:       bool = False

    def clean_answers(self) -> Dict[str, str]:
        # Keep only known keys; bound each value. Unknown keys are dropped.
        out: Dict[str, str] = {}
        for k, v in (self.answers or {}).items():
            if k in FIELD_KEYS:
                cv = _clean(v)
                if cv is not None:
                    out[k] = cv
        return out


class ReviewIn(BaseModel):
    action: str = Field(..., pattern="^(start|release|request_changes)$")
    note:   str = Field("", max_length=2000)


# ── Helpers ────────────────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _owned(conn, draft_id: int, user_id: int):
    """Fetch a draft only if it belongs to the user — IDOR-safe by construction."""
    return conn.execute(
        "SELECT * FROM ctap_drafts WHERE id=? AND user_id=?",
        (draft_id, user_id),
    ).fetchone()


def _summary(row) -> dict:
    return {
        "id":           row["id"],
        "company_name": row["company_name"],
        "sector":       row["sector"],
        "status":       row["status"],
        "gap_count":    row["gap_count"],
        "review_note":  row["review_note"],
        "created_at":   row["created_at"],
        "updated_at":   row["updated_at"],
        "released_at":  row["released_at"],
    }


# ── BRSR auto-fill ─────────────────────────────────────────────────────────────
@router.get("/api/ctap/prefill")
def ctap_prefill(company: str = Query(..., min_length=2, max_length=200),
                 user=Depends(get_current_user)):
    """Pre-fill the intake form from the company's ESG record.

    Only fills fields we can source RELIABLY from the companies table
    (sector, revenue, financial year, GHG intensity, renewable share, disclosed
    targets). Absolute Scope 1/2/3 are NOT in that table, so they are left for
    the client to enter from their BRSR filing — we never estimate absolute
    scopes from intensity and present them as filed.
    """
    key = company.strip()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT company_name, cin, sector, revenue_crore, financial_year, "
            "ghg_intensity, energy_mix, esg_targets FROM companies "
            "WHERE cin=? OR company_name=? COLLATE NOCASE LIMIT 1",
            (key.upper(), key),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Company not found in the Green Curve ESG dataset. "
                                 "You can still fill the plan in manually.")

    prefill: Dict[str, str] = {}
    prov: Dict[str, str] = {}
    if row["company_name"]:
        prefill["company_name"] = row["company_name"]; prov["company_name"] = "filed"
    if row["sector"]:
        prefill["sector"] = row["sector"]; prov["sector"] = "filed"
    if row["financial_year"]:
        prefill["base_year"] = row["financial_year"]; prov["base_year"] = "filed"

    # Renewable share from the energy_mix JSON blob, if present.
    try:
        emix = json.loads(row["energy_mix"] or "{}")
    except (ValueError, TypeError):
        emix = {}
    ren = emix.get("renewable_pct") if isinstance(emix, dict) else None
    if ren is not None:
        prefill["renewable_plan"] = f"Current renewable electricity share: {ren}% (from BRSR). Plan: [to complete]"
        prov["renewable_plan"] = "filed"

    if row["ghg_intensity"] is not None:
        # Context only — an intensity, explicitly NOT an absolute Scope figure.
        prefill["key_assumptions"] = (
            f"Disclosed GHG intensity ≈ {row['ghg_intensity']} tCO2e per ₹cr "
            f"(revenue ≈ ₹{row['revenue_crore']} cr). Absolute Scope 1/2/3 to be "
            f"entered from the BRSR filing."
        )
        prov["key_assumptions"] = "filed"

    try:
        targets = json.loads(row["esg_targets"] or "[]")
    except (ValueError, TypeError):
        targets = []
    if targets:
        prefill["interim_targets"] = "; ".join(str(t) for t in targets[:6])
        prov["interim_targets"] = "filed"

    return {"company_name": row["company_name"], "cin": row["cin"] or "",
            "prefill": prefill, "provenance": prov}


# ── Client CRUD ────────────────────────────────────────────────────────────────
@router.post("/api/ctap", status_code=201)
def create_draft(body: DraftIn, user=Depends(get_current_user)):
    answers = body.clean_answers()
    # company_name/sector on the row default from the top-level fields or answers.
    company = (body.company_name or answers.get("company_name") or "").strip()
    sector = (body.sector or answers.get("sector") or "").strip()
    if company and "company_name" not in answers:
        answers["company_name"] = company
    if sector and "sector" not in answers:
        answers["sector"] = sector
    assembled = assemble(answers)
    status = "submitted" if body.submit else "draft"
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO ctap_drafts (user_id, company_name, cin, sector, "
            "answers_json, assembled_json, status, gap_count) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (user["id"], company, body.cin.strip(), sector,
             json.dumps(answers), json.dumps(assembled), status,
             assembled["gap_count"]),
        )
        conn.commit()
        draft_id = cur.lastrowid
    return {"id": draft_id, "status": status, "assembled": assembled,
            "gap_count": assembled["gap_count"]}


@router.get("/api/ctap")
def list_drafts(user=Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM ctap_drafts WHERE user_id=? ORDER BY updated_at DESC",
            (user["id"],),
        ).fetchall()
    return {"drafts": [_summary(r) for r in rows]}


@router.get("/api/ctap/{draft_id}")
def get_draft(draft_id: int, user=Depends(get_current_user)):
    with get_conn() as conn:
        row = _owned(conn, draft_id, user["id"])
    if not row:
        raise HTTPException(404, "Plan not found.")
    return {
        **_summary(row),
        "cin":       row["cin"],
        "answers":   json.loads(row["answers_json"] or "{}"),
        "assembled": json.loads(row["assembled_json"] or "{}"),
        "can_edit":  row["status"] in _CLIENT_EDITABLE,
        "can_download": row["status"] == "released",
    }


@router.put("/api/ctap/{draft_id}")
def update_draft(draft_id: int, body: DraftIn, user=Depends(get_current_user)):
    with get_conn() as conn:
        row = _owned(conn, draft_id, user["id"])
        if not row:
            raise HTTPException(404, "Plan not found.")
        if row["status"] not in _CLIENT_EDITABLE:
            raise HTTPException(
                409, "This plan is in review and can't be edited right now.")
        answers = body.clean_answers()
        company = (body.company_name or answers.get("company_name") or "").strip()
        sector = (body.sector or answers.get("sector") or "").strip()
        if company:
            answers["company_name"] = company
        if sector:
            answers["sector"] = sector
        assembled = assemble(answers)
        status = "submitted" if body.submit else "draft"
        conn.execute(
            "UPDATE ctap_drafts SET company_name=?, cin=?, sector=?, answers_json=?, "
            "assembled_json=?, status=?, gap_count=?, review_note=?, updated_at=? "
            "WHERE id=? AND user_id=?",
            (company, body.cin.strip(), sector, json.dumps(answers),
             json.dumps(assembled), status, assembled["gap_count"],
             "" if body.submit else row["review_note"], _now(),
             draft_id, user["id"]),
        )
        conn.commit()
    return {"id": draft_id, "status": status, "assembled": assembled,
            "gap_count": assembled["gap_count"]}


@router.delete("/api/ctap/{draft_id}")
def delete_draft(draft_id: int, user=Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM ctap_drafts WHERE id=? AND user_id=?",
                           (draft_id, user["id"]))
        conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "Plan not found.")
    return {"ok": True}


@router.get("/api/ctap/{draft_id}/download")
def download_draft(draft_id: int, format: str = Query("md", pattern="^(md|html)$"),
                   user=Depends(get_current_user)):
    with get_conn() as conn:
        row = _owned(conn, draft_id, user["id"])
    if not row:
        raise HTTPException(404, "Plan not found.")
    if row["status"] != "released":
        raise HTTPException(
            403, "This plan is still being reviewed by Green Curve. You can "
                 "download it once it's released.")
    assembled = json.loads(row["assembled_json"] or "{}")
    md = _render_markdown(assembled)
    if format == "md":
        return {"filename": _fname(row, "md"), "content": md,
                "content_type": "text/markdown"}
    return {"filename": _fname(row, "html"), "content": _render_html(assembled),
            "content_type": "text/html"}


def _fname(row, ext: str) -> str:
    base = (row["company_name"] or "company").lower().replace(" ", "-")
    return f"ctap-{base}.{ext}"


def _render_html(a: Dict[str, Any]) -> str:
    # Self-contained printable HTML (client saves as PDF). No external assets.
    def esc(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{esc(a['title'])}</title>",
        "<style>body{font-family:Georgia,serif;max-width:820px;margin:40px auto;"
        "padding:0 24px;color:#1a2b22;line-height:1.55}h1{color:#12331f}"
        "h2{color:#155e3a;border-bottom:1px solid #e3e8e3;padding-bottom:4px;"
        "margin-top:28px}.caveat{background:#fff8e6;border:1px solid #f0d98a;"
        "padding:10px 14px;border-radius:8px;font-size:.9em}.gap{color:#b42318;"
        "font-family:monospace}li{margin:3px 0}.prov{color:#789;font-size:.85em}"
        "</style></head><body>",
        f"<h1>{esc(a['title'])}</h1>",
        f"<p class='caveat'>{esc(a['caveat'])}</p>",
        f"<p><em>Structured on the {esc(a['framework'])}</em></p>",
        "<h2>Company &amp; boundary</h2><ul>",
    ]
    for it in a["meta"]:
        parts.append(_html_item(it, esc))
    parts.append("</ul>")
    for sec in a["sections"]:
        parts.append(f"<h2>{esc(sec['id'])}. {esc(sec['title'])}</h2><ul>")
        for it in sec["items"]:
            parts.append(_html_item(it, esc))
        parts.append("</ul>")
    parts.append("<h2>Data provenance &amp; open items</h2><ul>")
    for g in a["gaps"]:
        parts.append(f"<li><span class='gap'>[GAP]</span> {esc(g['label'])} "
                     f"<span class='prov'>(expected: {esc(g['expected_source'])})</span></li>")
    if not a["gaps"]:
        parts.append("<li>No open items.</li>")
    parts.append("</ul></body></html>")
    return "".join(parts)


def _html_item(it: dict, esc) -> str:
    if it["value"] is None:
        return (f"<li><b>{esc(it['label'])}:</b> <span class='gap'>[GAP: "
                f"{esc(it['key'])}]</span> <span class='prov'>(expected: "
                f"{esc(it['provenance'])})</span></li>")
    return (f"<li><b>{esc(it['label'])}:</b> {esc(it['value'])} "
            f"<span class='prov'>({esc(it['provenance'])})</span></li>")


# ── Admin review flow ──────────────────────────────────────────────────────────
@router.get("/api/ctap/admin/queue")
def admin_queue(_=Depends(require_admin)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT d.*, u.email AS user_email FROM ctap_drafts d "
            "JOIN users u ON u.id = d.user_id "
            "WHERE d.status IN (?, ?) ORDER BY d.updated_at ASC",
            _ADMIN_QUEUE,
        ).fetchall()
    return {"queue": [{**_summary(r), "user_email": r["user_email"]} for r in rows]}


@router.get("/api/ctap/admin/{draft_id}")
def admin_get(draft_id: int, _=Depends(require_admin)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT d.*, u.email AS user_email FROM ctap_drafts d "
            "JOIN users u ON u.id = d.user_id WHERE d.id=?", (draft_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Plan not found.")
    return {
        **_summary(row), "user_email": row["user_email"], "cin": row["cin"],
        "answers":   json.loads(row["answers_json"] or "{}"),
        "assembled": json.loads(row["assembled_json"] or "{}"),
    }


@router.post("/api/ctap/admin/{draft_id}/review")
def admin_review(draft_id: int, body: ReviewIn, admin=Depends(require_admin)):
    if body.action == "request_changes" and not body.note.strip():
        raise HTTPException(400, "A note is required when requesting changes.")
    with get_conn() as conn:
        row = conn.execute("SELECT status FROM ctap_drafts WHERE id=?",
                           (draft_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Plan not found.")
        if body.action == "start":
            new_status, released = "in_review", None
        elif body.action == "release":
            new_status, released = "released", _now()
        else:  # request_changes
            new_status, released = "changes_requested", None
        conn.execute(
            "UPDATE ctap_drafts SET status=?, review_note=?, reviewed_by=?, "
            "released_at=COALESCE(?, released_at), updated_at=? WHERE id=?",
            (new_status, body.note.strip(), admin["id"], released, _now(), draft_id),
        )
        conn.commit()
    return {"id": draft_id, "status": new_status}


# Create tables on import (matches init_brsr_db / init_dataroom_db pattern).
init_ctap_db()
