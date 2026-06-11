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
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from fastapi import APIRouter, HTTPException
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
    scope1_tco2e:             Optional[float] = None
    scope1_not_disclosed:     bool  = False
    scope2_tco2e:             Optional[float] = None
    scope2_not_disclosed:     bool  = False
    water_m3:                 Optional[float] = None
    water_not_disclosed:      bool  = False
    waste_tonnes:             Optional[float] = None
    waste_not_disclosed:      bool  = False

    # Section C — Social
    total_employees:          int   = 0
    has_hr_policy:            bool  = False
    safety_incidents:         int   = 0
    women_pct:                float = 0.0

    # Section D — Governance
    has_brsr_disclosure:      bool  = False
    has_code_of_conduct:      bool  = False
    regulatory_violations:    int   = 0

    # Computed by client; server can recompute to verify
    esg_risk_score:           Optional[float] = None


class SupplierResponseOut(BaseModel):
    status:         str
    id:             str
    esg_risk_score: float


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load() -> dict:
    if RESP_FILE.exists():
        try:
            return json.loads(RESP_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_updated": None, "total_responses": 0, "responses": []}


def _save(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESP_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


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
async def submit_supplier_response(payload: SupplierResponseIn):
    """Receive a supplier ESG form submission and persist it."""
    db     = _load()
    record = payload.dict()

    # Server-side risk score (authoritative)
    record["esg_risk_score"] = _compute_risk(payload)
    record["id"]             = f"resp_{uuid.uuid4().hex[:8]}"

    if not record.get("submitted_at"):
        record["submitted_at"] = datetime.now(timezone.utc).isoformat()

    db["responses"].append(record)
    db["total_responses"] = len(db["responses"])
    db["last_updated"]    = datetime.now(timezone.utc).isoformat()
    _save(db)

    return SupplierResponseOut(
        status="ok",
        id=record["id"],
        esg_risk_score=record["esg_risk_score"],
    )


@router.get("/supplier-responses")
async def get_supplier_responses(
    company_cin:  str = "",
    company_name: str = "",
    limit:        int = 200,
):
    """
    Return all supplier responses, optionally filtered by mandating company.

    Params:
        company_cin   — filter by exact mandating_company_cin
        company_name  — filter by partial mandating_company_name (case-insensitive)
        limit         — max records to return (default 200)
    """
    db        = _load()
    responses = db.get("responses", [])

    if company_cin:
        responses = [r for r in responses if r.get("mandating_company_cin") == company_cin]
    elif company_name:
        name_lc = company_name.lower()
        responses = [
            r for r in responses
            if name_lc in (r.get("mandating_company_name") or "").lower()
        ]

    responses = sorted(responses, key=lambda r: r.get("submitted_at", ""), reverse=True)

    return {
        "total":       len(responses),
        "responses":   responses[:limit],
        "last_updated": db.get("last_updated"),
    }


@router.delete("/supplier-response/{response_id}")
async def delete_supplier_response(response_id: str):
    """Delete a specific supplier response by ID (admin use)."""
    db        = _load()
    before    = len(db["responses"])
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
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
