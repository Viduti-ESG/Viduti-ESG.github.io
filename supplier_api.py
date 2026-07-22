#!/usr/bin/env python3
"""
Green Curve — BRSR Value-Chain Supplier API
Handles supplier ESG form submissions for SEBI BRSR value-chain disclosure.

Integration (add to your existing FastAPI app):
    from supplier_api import router as supplier_router
    app.include_router(supplier_router)

Standalone (for testing):
    pip install fastapi uvicorn pydantic
    uvicorn supplier_api:app --reload --port 8001

Responses are stored in: assets/data/supplier_responses.json
"""

import json
import logging
import os
import secrets
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import mailer

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, Depends, Header, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
except ImportError:
    print("ERROR: Install dependencies:  pip install fastapi uvicorn pydantic")
    raise

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
DATA_DIR  = BASE_DIR / "assets" / "data"
RESP_FILE = DATA_DIR / "supplier_responses.json"

# ── Router ─────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/api", tags=["supplier"])

# ── File lock — prevents concurrent read-modify-write data loss ────────────────
_file_lock = threading.Lock()

# ── Admin auth ─────────────────────────────────────────────────────────────────

def _require_admin(x_api_key: str = Header(default="")) -> None:
    """Dependency: require GC_ADMIN_KEY header for admin-only endpoints."""
    admin_key = os.environ.get("GC_ADMIN_KEY", "")
    if not admin_key:
        raise HTTPException(status_code=503, detail="Admin key not configured on server.")
    # Constant-time compare so a wrong key can't be recovered via response timing.
    if not secrets.compare_digest(x_api_key or "", admin_key):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Api-Key header.")


# ── Submission rate limiter (per IP) — this endpoint is public, so cap abuse ────
_submit_rl_lock = threading.Lock()
_submit_rl: dict = defaultdict(list)
_SUBMIT_MAX = 10          # max submissions …
_SUBMIT_WINDOW = 600      # … per 10 minutes per IP

def _check_submit_rate(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _submit_rl_lock:
        _submit_rl[ip] = [t for t in _submit_rl[ip] if now - t < _SUBMIT_WINDOW]
        if len(_submit_rl[ip]) >= _SUBMIT_MAX:
            raise HTTPException(429, "Too many submissions from this IP. Please try again later.")
        _submit_rl[ip].append(now)


# ── Pydantic models ────────────────────────────────────────────────────────────

class SupplierResponseIn(BaseModel):
    # Context
    token:                    str   = ""
    mandating_company_name:   str   = ""
    mandating_company_cin:    str   = ""
    submitted_at:             str   = ""

    # Section A — Identity
    supplier_name:            str
    supplier_gstin:           str   = ""
    supplier_cin:             str   = ""
    annual_revenue_band:      str   = ""
    is_msme:                  bool  = False

    # Section B — Environmental
    has_environmental_policy: bool  = False
    scope1_tco2e:             Optional[float] = Field(None, ge=0)
    scope1_not_disclosed:     bool  = False
    scope2_tco2e:             Optional[float] = Field(None, ge=0)
    scope2_not_disclosed:     bool  = False
    water_m3:                 Optional[float] = Field(None, ge=0)
    water_not_disclosed:      bool  = False
    waste_tonnes:             Optional[float] = Field(None, ge=0)
    waste_not_disclosed:      bool  = False

    # Section C — Social
    total_employees:          int   = Field(0, ge=0)
    has_hr_policy:            bool  = False
    safety_incidents:         int   = Field(0, ge=0)
    women_pct:                float = Field(0.0, ge=0, le=100)

    # Section D — Governance
    has_brsr_disclosure:      bool  = False
    has_code_of_conduct:      bool  = False
    regulatory_violations:    int   = Field(0, ge=0)

    # Computed by client; server can recompute to verify
    esg_risk_score:           Optional[float] = None


class SupplierResponseOut(BaseModel):
    status:         str
    id:             str
    esg_risk_score: float


# ── Email notification helper ──────────────────────────────────────────────────

def _send_supplier_notification(record: dict) -> None:
    """Send a new-supplier-response email to the notification address via
    Resend (see mailer.py). GC_NOTIFY_EMAIL defaults to
    kneha2381@gmail.com. If the mailer isn't configured, logs and returns.
    """
    notify_to = os.environ.get("GC_NOTIFY_EMAIL", "kneha2381@gmail.com")

    if not mailer.ready():
        logger.info(
            "New supplier response [%s] from %s for %s — mailer not configured, skipping email",
            record.get("id"), record.get("supplier_name"), record.get("mandating_company_name"),
        )
        return

    score = record.get("esg_risk_score", "—")
    tier  = "High" if (score or 0) >= 6.5 else "Medium" if (score or 0) >= 3.5 else "Low"
    body  = (
        f"A new supplier has submitted their ESG profile on Green Curve.\n\n"
        f"Supplier    : {record.get('supplier_name', '—')}\n"
        f"For Company : {record.get('mandating_company_name', '—')}\n"
        f"ESG Score   : {score} ({tier} Risk)\n"
        f"MSME        : {'Yes' if record.get('is_msme') else 'No'}\n"
        f"Submitted   : {record.get('submitted_at', '—')}\n"
        f"Response ID : {record.get('id', '—')}\n\n"
        f"Log in to the Green Curve dashboard to view the full response.\n"
        f"https://greencurve.solutions/esg-intelligence\n"
    )
    subject = f"[Green Curve] New Supplier Response — {record.get('supplier_name', 'Unknown')}"
    if mailer.send_mail(notify_to, subject, body):
        logger.info("Supplier notification email sent to %s for response %s", notify_to, record.get("id"))
    else:
        logger.warning("Failed to send supplier notification email")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load() -> dict:
    """Load supplier responses. Raises RuntimeError if the file exists but is corrupted
    so that a subsequent _save() cannot silently overwrite valid data with an empty store."""
    if RESP_FILE.exists():
        raw = RESP_FILE.read_text(encoding="utf-8")
        try:
            return json.loads(raw)
        except Exception as e:
            logger.error("supplier_responses.json is corrupted — manual recovery needed: %s", e)
            raise RuntimeError(
                f"supplier_responses.json is corrupted and cannot be read safely: {e}"
            ) from e
    return {"last_updated": None, "total_responses": 0, "responses": []}


def _save(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Write to a temp file first, then atomically rename to avoid partial writes
    tmp = RESP_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(RESP_FILE)


def _compute_risk(d: SupplierResponseIn) -> float:
    """Mirror of the client-side computeSupplierEsgRisk() in supplier-form.js."""
    score = 5.0
    if not d.has_environmental_policy: score += 1.0
    if d.scope1_not_disclosed:         score += 0.5
    if d.scope2_not_disclosed:         score += 0.5
    if d.water_not_disclosed:          score += 0.2
    if d.waste_not_disclosed:          score += 0.2
    if not d.has_hr_policy:            score += 0.5
    if d.safety_incidents > 0:         score += min(1.0, d.safety_incidents * 0.3)
    if not d.has_code_of_conduct:      score += 0.5
    if d.regulatory_violations > 0:    score += min(2.0, d.regulatory_violations * 0.8)
    if d.has_brsr_disclosure:          score -= 1.0
    if d.has_environmental_policy:     score -= 0.3
    if d.is_msme:                      score -= 0.2
    return round(max(1.0, min(9.5, score)), 1)


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/supplier-response", response_model=SupplierResponseOut)
async def submit_supplier_response(payload: SupplierResponseIn, request: Request):
    """Receive a supplier ESG form submission and persist it."""
    _check_submit_rate(request)
    record = payload.dict()

    # Server-side risk score is authoritative; ignore any client-supplied value
    record["esg_risk_score"] = _compute_risk(payload)
    record["id"]             = f"resp_{uuid.uuid4().hex[:8]}"

    if not record.get("submitted_at"):
        record["submitted_at"] = datetime.now(timezone.utc).isoformat()

    with _file_lock:
        db = _load()
        db["responses"].append(record)
        db["total_responses"] = len(db["responses"])
        db["last_updated"]    = datetime.now(timezone.utc).isoformat()
        _save(db)

    # Non-blocking: notify buyer in a background thread (non-fatal if it fails)
    threading.Thread(target=_send_supplier_notification, args=(record,), daemon=True).start()

    return SupplierResponseOut(
        status="ok",
        id=record["id"],
        esg_risk_score=record["esg_risk_score"],
    )


@router.get("/supplier-responses", dependencies=[Depends(_require_admin)])
async def get_supplier_responses(
    company_cin:  str = "",
    company_name: str = "",
    limit:        int = 200,
):
    """
    Return supplier responses filtered by mandating company.
    Either company_cin or company_name is required to prevent full-dataset dumps.

    Params:
        company_cin   — filter by exact mandating_company_cin (preferred)
        company_name  — filter by partial mandating_company_name (case-insensitive)
        limit         — max records to return (default 200, max 500)
    """
    if not company_cin and not company_name:
        raise HTTPException(
            status_code=400,
            detail="Provide company_cin or company_name to filter results.",
        )

    limit = min(limit, 500)

    db        = _load()
    responses = db.get("responses", [])

    if company_cin:
        responses = [r for r in responses if r.get("mandating_company_cin") == company_cin]
    else:
        name_lc = company_name.lower()
        responses = [
            r for r in responses
            if name_lc in (r.get("mandating_company_name") or "").lower()
        ]

    responses = sorted(responses, key=lambda r: r.get("submitted_at", ""), reverse=True)

    return {
        "total":        len(responses),
        "responses":    responses[:limit],
        "last_updated": db.get("last_updated"),
    }


@router.delete("/supplier-response/{response_id}", dependencies=[Depends(_require_admin)])
async def delete_supplier_response(response_id: str):
    """Delete a specific supplier response by ID. Requires X-Api-Key: <GC_ADMIN_KEY>."""
    with _file_lock:
        db     = _load()
        before = len(db["responses"])
        db["responses"] = [r for r in db["responses"] if r.get("id") != response_id]
        if len(db["responses"]) == before:
            raise HTTPException(status_code=404, detail="Response not found")
        db["total_responses"] = len(db["responses"])
        db["last_updated"]    = datetime.now(timezone.utc).isoformat()
        _save(db)
    return {"status": "deleted", "id": response_id}


# ── Standalone app (for local testing) ────────────────────────────────────────
# Run: uvicorn supplier_api:app --reload --port 8001

try:
    from fastapi import FastAPI

    app = FastAPI(
        title="Green Curve — Supplier ESG API",
        description="BRSR value-chain supplier form backend",
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8000"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-Api-Key"],
    )
    app.include_router(router)

    @app.get("/")
    async def root():
        return {
            "service": "Green Curve Supplier ESG API",
            "endpoints": [
                "POST /api/supplier-response",
                "GET  /api/supplier-responses",
                "DEL  /api/supplier-response/{id}",
            ],
        }
except Exception:
    pass  # router is still importable even if FastAPI app fails
