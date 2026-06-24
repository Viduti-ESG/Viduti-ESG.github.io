"""
Green Curve — BRSR Workspace API.
Endpoints under /api/brsr/*

Turns BRSR reporting from a one-shot drafting tool into a recurring, account-bound
workflow — the retention play. Every listed company must file BRSR annually, so if
they draft, save, resume and track it inside Green Curve year over year, Green Curve
owns their compliance calendar.

What this adds on top of the existing client-side generator (brsr-simple.html):
  - Reports are saved to the user's account and survive across sessions.
  - One report per financial year; completion %, status and filing deadline tracked.
  - ESG evidence from the Data Room can be attached to a report (ties Pillar 1 ↔ 2).
  - Export the structured report as JSON at any time.

Legal: BRSR is a SEBI public regulation — no licensing needed (only GRI-labelled or
ISSB/SASB text would need a licence; this is neither). The report contains the
customer's own company data, so the same DPDP Data-Fiduciary basis as the Data Room
applies. A filer-liability disclaimer is shown in the UI: this is a drafting aid, not
assurance, and the filer remains responsible for the accuracy of what they submit.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import io

from db import get_conn
from auth_api import get_current_user
from collaboration_api import can_view as _collab_can_view, can_edit as _collab_can_edit

logger = logging.getLogger(__name__)
router = APIRouter()

# ── BRSR schema — single source of truth for the form AND completion scoring ─────
# Pragmatic skeleton of the SEBI BRSR format: Section A (general disclosures),
# Section B (management & process), Section C (9 NGRBC principles). The frontend
# renders this; completion = answered fields / total fields. The free-form
# answers_json can also absorb the full generator's richer field set later.
def _f(key, label, ftype="text", required=False, options=None):
    d = {"key": key, "label": label, "type": ftype, "required": required}
    if options:
        d["options"] = options
    return d

BRSR_SCHEMA = [
    {
        "id": "A", "title": "Section A — General Disclosures", "fields": [
            _f("cin", "Corporate Identity Number (CIN)", "text", True),
            _f("company_name", "Name of the listed entity", "text", True),
            _f("year_of_incorporation", "Year of incorporation", "text"),
            _f("registered_office", "Registered office address", "textarea"),
            _f("email", "Contact email", "text"),
            _f("website", "Website", "text"),
            _f("financial_year", "Financial year reported", "text", True),
            _f("stock_exchanges", "Stock exchange(s) where listed", "text"),
            _f("paid_up_capital", "Paid-up capital (₹)", "number"),
            _f("reporting_boundary", "Reporting boundary", "select", False, ["Standalone", "Consolidated"]),
            _f("business_activities", "Business activities (with % turnover)", "textarea"),
            _f("products_services", "Products / services sold (with % turnover)", "textarea"),
            _f("national_plants", "No. of plants (national)", "number"),
            _f("national_offices", "No. of offices (national)", "number"),
            _f("markets_served_states", "No. of states served", "number"),
            _f("exports_pct", "Exports as % of turnover", "percent"),
            _f("perm_male_employees", "Permanent male employees", "number"),
            _f("perm_female_employees", "Permanent female employees", "number"),
            _f("perm_male_workers", "Permanent male workers", "number"),
            _f("perm_female_workers", "Permanent female workers", "number"),
            _f("women_on_board_pct", "Women on Board (%)", "percent"),
            _f("women_in_kmp_pct", "Women in KMP (%)", "percent"),
            _f("turnover_rate", "Employee turnover rate (%)", "percent"),
            _f("csr_applicable", "Is CSR applicable (Sec 135)?", "select", False, ["Yes", "No"]),
            _f("csr_turnover", "Turnover for CSR (₹)", "number"),
        ],
    },
    {
        "id": "B", "title": "Section B — Management & Process Disclosures", "fields": [
            _f("policies_cover_principles", "Policies covering the 9 NGRBC principles", "textarea"),
            _f("policies_approved_by_board", "Policies approved by the Board?", "select", False, ["Yes", "No"]),
            _f("policies_web_link", "Web link to policies", "text"),
            _f("sdg_targets", "Specific commitments / goals / targets (SDG-linked)", "textarea"),
            _f("review_frequency", "Frequency of performance review by Board", "text"),
            _f("external_assessment", "Independent assessment / evaluation of policies?", "select", False, ["Yes", "No"]),
        ],
    },
    {
        "id": "P1", "title": "Principle 1 — Ethics & Transparency", "fields": [
            _f("anti_corruption_policy", "Anti-corruption / anti-bribery policy in place?", "select", False, ["Yes", "No"]),
            _f("disciplinary_actions", "Disciplinary actions on bribery/corruption", "number"),
            _f("conflict_of_interest", "Complaints re. conflict of interest", "number"),
        ],
    },
    {
        "id": "P2", "title": "Principle 2 — Sustainable & Safe Goods", "fields": [
            _f("rd_capex_sustainability_pct", "R&D / Capex on sustainability (%)", "percent"),
            _f("sustainable_sourcing_pct", "Inputs sourced sustainably (%)", "percent"),
            _f("product_reclaim_process", "Processes to reclaim products at end-of-life", "textarea"),
        ],
    },
    {
        "id": "P3", "title": "Principle 3 — Employee Wellbeing", "fields": [
            _f("health_insurance_pct", "Employees with health insurance (%)", "percent"),
            _f("parental_leave_return_pct", "Return-to-work rate after parental leave (%)", "percent"),
            _f("ltifr", "LTIFR (per million person-hours)", "number"),
            _f("fatalities", "Work-related fatalities", "number"),
            _f("safety_complaints", "Complaints on working conditions", "number"),
        ],
    },
    {
        "id": "P4", "title": "Principle 4 — Stakeholder Engagement", "fields": [
            _f("stakeholder_groups", "Key stakeholder groups identified", "textarea"),
            _f("consultation_process", "Stakeholder consultation process", "textarea"),
        ],
    },
    {
        "id": "P5", "title": "Principle 5 — Human Rights", "fields": [
            _f("min_wage_compliance_pct", "Employees paid at/above minimum wage (%)", "percent"),
            _f("human_rights_training_pct", "Employees trained on human rights (%)", "percent"),
            _f("posh_complaints", "Sexual harassment (POSH) complaints", "number"),
        ],
    },
    {
        "id": "P6", "title": "Principle 6 — Environment", "fields": [
            _f("energy_total_gj", "Total energy consumed (GJ)", "number"),
            _f("water_withdrawal_kl", "Total water withdrawal (KL)", "number"),
            _f("scope1_tco2e", "Scope 1 emissions (tCO2e)", "number"),
            _f("scope2_tco2e", "Scope 2 emissions (tCO2e)", "number"),
            _f("scope3_tco2e", "Scope 3 emissions (tCO2e)", "number"),
            _f("waste_total_mt", "Total waste generated (MT)", "number"),
            _f("waste_recycled_pct", "Waste recycled / recovered (%)", "percent"),
        ],
    },
    {
        "id": "P7", "title": "Principle 7 — Policy Advocacy", "fields": [
            _f("trade_affiliations", "Trade & industry chambers / associations", "textarea"),
            _f("public_policy_positions", "Public policy positions advocated", "textarea"),
        ],
    },
    {
        "id": "P8", "title": "Principle 8 — Inclusive Growth", "fields": [
            _f("social_impact_assessments", "Social Impact Assessments conducted", "number"),
            _f("csr_projects", "CSR projects undertaken", "textarea"),
            _f("csr_spend", "CSR amount spent (₹)", "number"),
        ],
    },
    {
        "id": "P9", "title": "Principle 9 — Consumer Value", "fields": [
            _f("consumer_complaints", "Consumer complaints received", "number"),
            _f("data_breaches", "Data privacy / cyber-security breaches", "number"),
            _f("product_recalls", "Product recalls", "number"),
        ],
    },
]

_ALL_FIELD_KEYS = [f["key"] for sec in BRSR_SCHEMA for f in sec["fields"]]
_TOTAL_FIELDS = len(_ALL_FIELD_KEYS)
_VALID_STATUS = {"draft", "in_review", "final"}


# ── Schema ──────────────────────────────────────────────────────────────────────
def init_brsr_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS brsr_reports (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                title           TEXT    NOT NULL,
                financial_year  TEXT    DEFAULT '',
                status          TEXT    DEFAULT 'draft',   -- draft|in_review|final
                filing_deadline TEXT    DEFAULT '',
                answers_json    TEXT    DEFAULT '{}',
                completion_pct  REAL    DEFAULT 0,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_brsr_reports_user ON brsr_reports(user_id);

            CREATE TABLE IF NOT EXISTS brsr_evidence (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id   INTEGER NOT NULL,
                document_id INTEGER NOT NULL,
                label       TEXT    DEFAULT '',
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (report_id)   REFERENCES brsr_reports(id),
                FOREIGN KEY (document_id) REFERENCES dr_documents(id),
                UNIQUE(report_id, document_id)
            );
            CREATE INDEX IF NOT EXISTS idx_brsr_evidence_report ON brsr_evidence(report_id);
        """)


init_brsr_db()


# ── Helpers ──────────────────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _completion(answers: dict) -> float:
    if not _TOTAL_FIELDS:
        return 0.0
    filled = sum(
        1 for k in _ALL_FIELD_KEYS
        if str(answers.get(k, "")).strip() not in ("", "None")
    )
    return round(100.0 * filled / _TOTAL_FIELDS, 1)


def _owned_report(conn, report_id: int, user_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM brsr_reports WHERE id=? AND user_id=?", (report_id, user_id)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Report not found")
    return dict(row)


def _viewable_report(conn, report_id: int, user_id: int) -> dict:
    """Owner OR a team member the report has been shared with (any permission)."""
    row = conn.execute("SELECT * FROM brsr_reports WHERE id=?", (report_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Report not found")
    d = dict(row)
    if d["user_id"] == user_id or _collab_can_view(conn, user_id, "brsr_report", report_id):
        return d
    raise HTTPException(404, "Report not found")


def _editable_report(conn, report_id: int, user_id: int) -> dict:
    """Owner OR a team member with an 'edit' share (co-authoring)."""
    row = conn.execute("SELECT * FROM brsr_reports WHERE id=?", (report_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Report not found")
    d = dict(row)
    if d["user_id"] == user_id or _collab_can_edit(conn, user_id, "brsr_report", report_id):
        return d
    if _collab_can_view(conn, user_id, "brsr_report", report_id):
        raise HTTPException(403, "You have view-only access to this report")
    raise HTTPException(404, "Report not found")


# ── Pydantic models ───────────────────────────────────────────────────────────────
class ReportCreateIn(BaseModel):
    title:           str
    financial_year:  str = ""
    filing_deadline: str = ""

class ReportUpdateIn(BaseModel):
    title:           Optional[str] = None
    financial_year:  Optional[str] = None
    filing_deadline: Optional[str] = None
    status:          Optional[str] = None
    answers:         Optional[dict] = None

class EvidenceIn(BaseModel):
    document_id: int
    label:       str = ""


# ════════════════════════════════════════════════════════════════════════════════
#  SCHEMA
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/brsr/schema")
def get_schema():
    return {"sections": BRSR_SCHEMA, "total_fields": _TOTAL_FIELDS}


# ════════════════════════════════════════════════════════════════════════════════
#  REPORTS
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/brsr/reports")
def list_reports(user=Depends(get_current_user)):
    rows = get_conn().execute(
        """SELECT id, title, financial_year, status, filing_deadline, completion_pct,
                  created_at, updated_at
           FROM brsr_reports WHERE user_id=? ORDER BY updated_at DESC""",
        (user["id"],),
    ).fetchall()
    return {"reports": [dict(r) for r in rows]}


@router.post("/api/brsr/reports", status_code=201)
def create_report(body: ReportCreateIn, user=Depends(get_current_user)):
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "Title is required")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO brsr_reports (user_id, title, financial_year, filing_deadline, answers_json, completion_pct)
               VALUES (?,?,?,?,?,0)""",
            (user["id"], title, body.financial_year.strip(), body.filing_deadline.strip(), "{}"),
        )
        rid = cur.lastrowid
    return {"ok": True, "report_id": rid}


@router.get("/api/brsr/reports/{report_id}")
def get_report(report_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    rep = _viewable_report(conn, report_id, user["id"])
    try:
        rep["answers"] = json.loads(rep.pop("answers_json") or "{}")
    except Exception:
        rep["answers"] = {}
    ev = conn.execute(
        """SELECT e.id, e.document_id, e.label, d.title AS doc_title, d.category
           FROM brsr_evidence e JOIN dr_documents d ON d.id = e.document_id
           WHERE e.report_id=? ORDER BY e.created_at""",
        (report_id,),
    ).fetchall()
    rep["evidence"] = [dict(r) for r in ev]
    return {"report": rep}


@router.put("/api/brsr/reports/{report_id}")
def update_report(report_id: int, body: ReportUpdateIn, user=Depends(get_current_user)):
    """Autosave endpoint — answers, metadata and status."""
    conn = get_conn()
    rep = _editable_report(conn, report_id, user["id"])

    title    = body.title.strip() if body.title is not None else rep["title"]
    fy       = body.financial_year.strip() if body.financial_year is not None else rep["financial_year"]
    deadline = body.filing_deadline.strip() if body.filing_deadline is not None else rep["filing_deadline"]
    status   = rep["status"]
    if body.status is not None:
        if body.status not in _VALID_STATUS:
            raise HTTPException(400, f"status must be one of {sorted(_VALID_STATUS)}")
        status = body.status

    if body.answers is not None:
        answers_json = json.dumps(body.answers)
        completion = _completion(body.answers)
    else:
        answers_json = rep["answers_json"]
        completion = rep["completion_pct"]

    with conn:
        # Authorisation already enforced by _editable_report; scope by id (owner may differ
        # from the acting co-author).
        conn.execute(
            """UPDATE brsr_reports SET title=?, financial_year=?, filing_deadline=?, status=?,
                   answers_json=?, completion_pct=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (title, fy, deadline, status, answers_json, completion, report_id),
        )
    return {"ok": True, "completion_pct": completion, "status": status}


@router.delete("/api/brsr/reports/{report_id}")
def delete_report(report_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    _owned_report(conn, report_id, user["id"])
    with conn:
        conn.execute("DELETE FROM brsr_evidence WHERE report_id=?", (report_id,))
        conn.execute("DELETE FROM brsr_reports WHERE id=? AND user_id=?", (report_id, user["id"]))
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════════════
#  EVIDENCE  (link Data Room documents to a report — reinforces the Pillar 1 moat)
# ════════════════════════════════════════════════════════════════════════════════
@router.post("/api/brsr/reports/{report_id}/evidence", status_code=201)
def attach_evidence(report_id: int, body: EvidenceIn, user=Depends(get_current_user)):
    conn = get_conn()
    _editable_report(conn, report_id, user["id"])
    # The Data Room document must belong to the person attaching it.
    doc = conn.execute(
        "SELECT id, title FROM dr_documents WHERE id=? AND user_id=?",
        (body.document_id, user["id"]),
    ).fetchone()
    if not doc:
        raise HTTPException(404, "Data Room document not found")
    try:
        with conn:
            conn.execute(
                "INSERT INTO brsr_evidence (report_id, document_id, label) VALUES (?,?,?)",
                (report_id, body.document_id, body.label.strip() or doc["title"]),
            )
    except Exception:
        raise HTTPException(409, "That document is already attached")
    return {"ok": True}


@router.delete("/api/brsr/reports/{report_id}/evidence/{evidence_id}")
def detach_evidence(report_id: int, evidence_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    _editable_report(conn, report_id, user["id"])
    with conn:
        conn.execute(
            "DELETE FROM brsr_evidence WHERE id=? AND report_id=?", (evidence_id, report_id)
        )
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════════════
#  EXPORT
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/brsr/reports/{report_id}/export")
def export_report(report_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    rep = _viewable_report(conn, report_id, user["id"])
    try:
        answers = json.loads(rep["answers_json"] or "{}")
    except Exception:
        answers = {}

    # Build a structured, section-organised export keyed by human labels.
    sections_out = []
    for sec in BRSR_SCHEMA:
        sections_out.append({
            "section": sec["title"],
            "responses": {f["label"]: answers.get(f["key"], "") for f in sec["fields"]},
        })
    payload = {
        "report":     {"title": rep["title"], "financial_year": rep["financial_year"],
                       "status": rep["status"], "completion_pct": rep["completion_pct"]},
        "disclaimer": ("Drafted with Green Curve as a BRSR preparation aid. This is not "
                       "an assurance or audit. The filing entity remains responsible for "
                       "the accuracy and completeness of its BRSR submission to SEBI."),
        "exported_at": _now(),
        "sections":    sections_out,
    }
    buf = io.BytesIO(json.dumps(payload, indent=2).encode("utf-8"))
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in rep["title"])[:50].strip() or "brsr-report"
    fname = f"{safe}.json"
    return StreamingResponse(
        buf, media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
