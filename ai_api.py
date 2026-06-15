#!/usr/bin/env python3
"""
Green Curve — AI API (P3 features)
Endpoints:
  POST /api/ccts-scorecard  — CCTS Carbon Credit Trading Scheme scorecard (Claude Haiku)
  POST /api/tcfd-gap        — TCFD disclosure gap analysis (Claude Haiku)
  POST /api/nl-query        — Natural language ESG query → filter params (Claude Haiku)

Integration (add to main FastAPI app):
    from ai_api import router as ai_router
    app.include_router(ai_router)

Standalone:
    pip install fastapi uvicorn pydantic anthropic python-multipart
    ANTHROPIC_API_KEY=sk-... uvicorn ai_api:app --reload --port 8002

Costs (Haiku ~₹0.43/1k tokens; Sonnet ~₹4.8/1k tokens):
  - CCTS scorecard: ~800 tokens  → ≈₹0.35/call (Haiku)
  - TCFD gap:       ~700 tokens  → ≈₹0.30/call (Haiku)
  - NL query:       ~250 tokens  → ≈₹0.11/call (Haiku)
  - TCFD PDF check: ~6000 tokens → ≈₹1.50/call (Sonnet)
  - Weekly digest:  ~2200 tokens → ≈₹0.95/call (Haiku)
"""

import base64
import json
import os
import time
import threading
from collections import defaultdict
from typing import Any, Optional

try:
    from fastapi import APIRouter, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
except ImportError:
    print("ERROR: pip install fastapi uvicorn pydantic")
    raise

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

# ── Router ─────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/api", tags=["ai"])

# ── Per-IP rate limiter ────────────────────────────────────────────────────────
# Haiku endpoints: 30 req/min per IP. Sonnet endpoint (tcfd-pdf): 5 req/min per IP.
_rl_lock   = threading.Lock()
_rl_counts: dict[str, list[float]] = defaultdict(list)

def _rate_limit(request: Request, limit: int, window: int = 60) -> None:
    ip  = request.client.host if request.client else "unknown"
    key = f"{ip}:{request.url.path}"
    now = time.monotonic()
    with _rl_lock:
        timestamps = _rl_counts[key]
        _rl_counts[key] = [t for t in timestamps if now - t < window]
        if len(_rl_counts[key]) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: max {limit} requests per {window}s from this IP.",
            )
        _rl_counts[key].append(now)

# ── Claude client (lazy, initialised once at first request) ───────────────────
_client      = None
_client_lock = threading.Lock()

def _claude():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:  # double-checked locking
                if not _ANTHROPIC_AVAILABLE:
                    raise RuntimeError("anthropic package not installed. pip install anthropic")
                key = os.environ.get("ANTHROPIC_API_KEY", "")
                if not key:
                    raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")
                _client = anthropic.Anthropic(api_key=key)
    return _client


def _ask_haiku(system: str, user: str, max_tokens: int = 600) -> str:
    msg = _claude().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


# ── Pydantic models ────────────────────────────────────────────────────────────

class CCTSRequest(BaseModel):
    company_name:    str
    sector:          str = ""
    products:        str = ""
    scope1_emissions: Optional[float] = None
    scope2_emissions: Optional[float] = None
    brsr_assurance:  str = "None"
    compliance_risk: Optional[float] = None
    ghg_intensity:   Optional[float] = None
    revenue_crore:   Optional[float] = None
    esg_targets:     list[dict] = []


class TCFDRequest(BaseModel):
    company_name:          str
    sector:                str = ""
    scope1_emissions:      Optional[float] = None
    scope2_emissions:      Optional[float] = None
    scope3_emissions:      Optional[float] = None
    brsr_assurance:        str = "None"
    compliance_risk:       Optional[float] = None
    governance_risk:       Optional[float] = None
    anti_corruption_policy: str = "Unknown"
    esg_targets:           list[dict] = []


class NLQueryRequest(BaseModel):
    query: str = Field(..., max_length=500)


# ── CCTS Scorecard ─────────────────────────────────────────────────────────────

CCTS_SYSTEM = """You are an expert on India's Carbon Credit Trading Scheme (CCTS 2023) and BEE energy regulations.
Given company ESG data, return a JSON scorecard for their CCTS compliance readiness.

Return ONLY valid JSON with this exact structure:
{
  "narrative": "2-3 sentence plain-English summary of the company's CCTS position",
  "obligations": [
    {
      "id": "registration",
      "label": "Phase I Registration",
      "deadline": "31 Dec 2026",
      "status": "compliant|partial|gap|na",
      "status_label": "Compliant|Partial|Action needed|N/A",
      "detail": "1-sentence specific action or observation"
    }
  ],
  "actions": ["Prioritised action item 1", "Prioritised action item 2", "...up to 5"]
}

Obligations to assess (use these IDs):
- registration: Phase I Registration on BEE Carbon Credit Trading platform (31 Dec 2026)
- inventory: GHG Inventory Submission — verified Scope 1 to BEE portal (30 Sep 2026)
- verification: Third-party GHG verification by BEE-accredited body (30 Sep 2026)
- target_setting: GHG Intensity reduction target agreed with BEE (31 Mar 2027)
- brsr_core: BRSR Core 3rd-party assurance (mandatory top 250, FY2026-27)
- scope2_report: Scope 2 market-based + location-based reported separately (FY2026-27)

Phase I CCTS sectors: cement, aluminium, iron & steel, petrochemicals, chlor-alkali, paper & pulp, power generation.
Non-Phase-I sectors: mark all CCTS obligations as 'na'. BRSR Core obligations still apply.
Use 'na' status only for CCTS obligations when company is outside Phase I."""

@router.post("/ccts-scorecard")
async def ccts_scorecard(request: Request, payload: CCTSRequest):
    _rate_limit(request, limit=30)
    data_summary = f"""Company: {payload.company_name}
Sector: {payload.sector}
Products: {payload.products}
Scope 1 emissions: {payload.scope1_emissions or 'Not disclosed'} tCO2e
Scope 2 emissions: {payload.scope2_emissions or 'Not disclosed'} tCO2e
BRSR assurance level: {payload.brsr_assurance}
Compliance risk score: {payload.compliance_risk or 'N/A'} / 10
GHG intensity score: {payload.ghg_intensity or 'N/A'} / 10
Revenue: {payload.revenue_crore or 'N/A'} crore INR
ESG targets: {json.dumps([t.get('metric','') for t in payload.esg_targets[:5]])}"""

    try:
        raw = _ask_haiku(CCTS_SYSTEM, data_summary, max_tokens=700)
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {e}")


# ── TCFD Gap Analysis ──────────────────────────────────────────────────────────

TCFD_SYSTEM = """You are an expert in TCFD (Task Force on Climate-related Financial Disclosures) and SEBI's climate disclosure mandates for Indian listed companies.
Given company ESG data from their BRSR filing, assess alignment with the 4 TCFD pillars.

Return ONLY valid JSON with this exact structure:
{
  "summary": "2-3 sentence plain-English summary of overall TCFD alignment",
  "pillars": [
    {
      "id": "governance|strategy|risk_mgmt|metrics",
      "score": 0-100,
      "elements": [
        {
          "id": "board_oversight|mgmt_role|physical_risks|transition_risks|scenario_analysis|risk_id_process|risk_integration|scope1|scope2|scope3|climate_target",
          "label": "Human-readable label",
          "status": "disclosed|partial|gap",
          "note": "1-sentence specific observation or recommendation"
        }
      ]
    }
  ],
  "gaps": ["Top gap 1", "Top gap 2", "Top gap 3 (up to 5)"]
}

TCFD pillars and elements:
Governance: board_oversight (Board oversight of climate risks), mgmt_role (Management role in climate assessment)
Strategy: physical_risks (Physical climate risks identified), transition_risks (Transition risks & opportunities), scenario_analysis (Scenario analysis 1.5°C/2°C)
Risk Management: risk_id_process (Process for identifying climate risks), risk_integration (Integration into overall risk management)
Metrics & Targets: scope1 (Scope 1 GHG disclosed), scope2 (Scope 2 GHG disclosed), scope3 (Scope 3 GHG disclosed), climate_target (Climate target with year)

Mark 'disclosed' only when there is strong evidence. Mark 'partial' when signal exists but incomplete. Mark 'gap' when absent."""

@router.post("/tcfd-gap")
async def tcfd_gap(request: Request, payload: TCFDRequest):
    _rate_limit(request, limit=30)
    targets_str = ", ".join([t.get("metric", "") for t in payload.esg_targets[:5]]) or "None"
    data_summary = f"""Company: {payload.company_name}
Sector: {payload.sector}
Scope 1: {payload.scope1_emissions or 'Not disclosed'} tCO2e
Scope 2: {payload.scope2_emissions or 'Not disclosed'} tCO2e
Scope 3: {payload.scope3_emissions or 'Not disclosed'} tCO2e
BRSR assurance: {payload.brsr_assurance}
Anti-corruption policy: {payload.anti_corruption_policy}
Compliance risk score: {payload.compliance_risk or 'N/A'} / 10
Governance risk score: {payload.governance_risk or 'N/A'} / 10
ESG targets stated: {targets_str}"""

    try:
        raw = _ask_haiku(TCFD_SYSTEM, data_summary, max_tokens=800)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {e}")


# ── Natural Language ESG Query ─────────────────────────────────────────────────

NL_SYSTEM = """You are an ESG data query parser for a database of 1,227 Indian listed companies.
Parse a plain-English query into a JSON filter specification.

Return ONLY valid JSON with this exact structure (omit fields not relevant):
{
  "explanation": "One sentence explaining what you understood and what filters were applied",
  "filters": {
    "sector": "sector keyword substring (optional)",
    "risk_tier": "High|Medium|Low (optional)",
    "min_esg": 0.0,
    "max_esg": 10.0,
    "min_ghg": 0.0,
    "min_water": 0.0,
    "min_compliance": 0.0,
    "has_scope1": true|false,
    "has_assurance": true,
    "sort": "esg_desc|water_intensity_desc",
    "limit": 10
  }
}

Available filter fields:
- sector: substring match on sector name (e.g. "cement", "pharma", "steel", "power", "it", "banking")
- risk_tier: "High", "Medium", or "Low"
- min_esg / max_esg: ESG risk score thresholds (0–10, higher = more risk)
- min_ghg: minimum GHG intensity score (0–10)
- min_water: minimum water intensity score (0–10)
- min_compliance: minimum compliance risk score (0–10)
- has_scope1: true = only companies with Scope 1 disclosed; false = only those WITHOUT
- has_assurance: true = only companies with BRSR 3rd-party assurance
- sort: "esg_desc" (default), "water_intensity_desc"
- limit: max rows to return (default 50, max 100)

Only include fields the user asked about. If the query is vague, return reasonable defaults."""

@router.post("/nl-query")
async def nl_query(request: Request, payload: NLQueryRequest):
    _rate_limit(request, limit=30)
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query is empty")
    try:
        raw = _ask_haiku(NL_SYSTEM, payload.query, max_tokens=300)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI parsing failed: {e}")


# ── P4-E: PDF / TCFD Gap Checker (Claude Sonnet) ──────────────────────────────

TCFD_PDF_SYSTEM = """You are a TCFD (Task Force on Climate-related Financial Disclosures) expert and sustainability reporting analyst.
A user has uploaded a corporate sustainability or annual report. Analyse the document text and assess TCFD alignment across all 4 pillars.

Return ONLY valid JSON with this structure:
{
  "company_name": "Inferred company name or 'Unknown'",
  "document_type": "Sustainability Report / Annual Report / BRSR / Other",
  "overall_score": 0-100,
  "summary": "3-4 sentence plain-English assessment of TCFD alignment",
  "pillars": [
    {
      "id": "governance|strategy|risk_mgmt|metrics",
      "label": "Governance|Strategy|Risk Management|Metrics & Targets",
      "score": 0-100,
      "status": "strong|partial|weak",
      "elements": [
        {
          "id": "element_id",
          "label": "Element label",
          "status": "disclosed|partial|gap",
          "evidence": "Quote or observation from the document",
          "recommendation": "Specific improvement recommendation"
        }
      ]
    }
  ],
  "top_gaps": ["Gap 1 (actionable)", "Gap 2", "Gap 3", "Gap 4", "Gap 5"],
  "strengths": ["Strength 1", "Strength 2", "Strength 3"]
}

Be specific: quote actual passages where evidence is found. Mark 'gap' when genuinely absent.
TCFD elements to assess:
- Governance: board_oversight (Board oversight of climate risks), mgmt_role (Management climate processes)
- Strategy: physical_risks, transition_risks, scenario_analysis (1.5°C / 2°C / BAU scenarios)
- Risk Management: risk_id_process (Climate risk identification), risk_integration (Enterprise risk integration)
- Metrics & Targets: scope1 (Scope 1 GHG), scope2 (Scope 2 GHG), scope3 (Scope 3 GHG), climate_target (Net-zero or reduction target with year)"""


class TCFDPDFRequest(BaseModel):
    text:     str = Field(..., max_length=20000)  # enforced before body hits the handler
    filename: str = Field(default="", max_length=255)


def _ask_sonnet(system: str, user: str, max_tokens: int = 2000) -> str:
    msg = _claude().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


@router.post("/tcfd-pdf")
async def tcfd_pdf(request: Request, payload: TCFDPDFRequest):
    _rate_limit(request, limit=5)  # Sonnet is ~10× more expensive
    if not payload.text or len(payload.text.strip()) < 200:
        raise HTTPException(status_code=400, detail="Document text too short. Please upload a valid sustainability or annual report.")
    text_excerpt = payload.text[:15000]  # Cap at ~15k chars
    user_msg = f"File: {payload.filename or 'uploaded document'}\n\n--- DOCUMENT TEXT ---\n{text_excerpt}\n--- END ---\n\nAssess this document for TCFD alignment."
    try:
        raw = _ask_sonnet(TCFD_PDF_SYSTEM, user_msg, max_tokens=2000)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        return result
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"AI returned invalid JSON: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TCFD PDF analysis failed: {e}")


# ── P4-F: Weekly ESG Digest (Claude Haiku) ────────────────────────────────────

DIGEST_SYSTEM = """You are Green Curve's ESG analyst. Generate a concise personalised weekly ESG digest for an Indian corporate sustainability professional.
The digest should be engaging, data-driven, and actionable.

Return ONLY valid JSON with this structure:
{
  "subject": "Weekly ESG Digest — [date range]",
  "greeting": "Brief personalised greeting (1 sentence)",
  "sections": [
    {
      "title": "Section title",
      "content": "2-4 sentences of substantive content. Be specific, mention real regulatory deadlines or trends."
    }
  ],
  "action_items": ["Action 1 with deadline", "Action 2", "Action 3"],
  "quote": "Motivational or insight quote relevant to ESG/sustainability",
  "footer": "Green Curve Weekly ESG Digest · Unsubscribe | View in browser"
}

Sections to include (tailor to the company context provided):
1. Regulatory Spotlight — upcoming Indian ESG deadline or recent circular
2. Portfolio Risk Insight — key risk observation for the sector
3. Best Practice Highlight — what leading peers are doing
4. Data Quality Tip — one BRSR data improvement recommendation"""


class DigestRequest(BaseModel):
    email:          str
    company_name:   str = ""
    sector:         str = ""
    watchlist:      list[str] = []
    esg_risk_score: Optional[float] = None
    week_of:        str = ""  # ISO date string


@router.post("/generate-digest")
async def generate_digest(request: Request, payload: DigestRequest):
    _rate_limit(request, limit=10)  # digest is per-subscriber, lower limit
    context = f"""Subscriber: {payload.email}
Company: {payload.company_name or 'Not specified'}
Sector: {payload.sector or 'Not specified'}
ESG Risk Score: {payload.esg_risk_score or 'Not provided'} / 10
Watchlist companies: {', '.join(payload.watchlist[:10]) or 'None set'}
Week of: {payload.week_of or 'Current week'}"""

    try:
        raw = _ask_haiku(DIGEST_SYSTEM, context, max_tokens=800)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        return result
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"AI returned invalid JSON: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Digest generation failed: {e}")


# ── Standalone app ─────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI

    app = FastAPI(
        title="Green Curve — AI API",
        description="P3 AI features: CCTS scorecard, TCFD gap analysis, NL ESG query",
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8000"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(router)

    @app.get("/")
    async def root():
        return {
            "service": "Green Curve AI API",
            "endpoints": [
                "POST /api/ccts-scorecard  (Haiku — CCTS compliance scorecard)",
                "POST /api/tcfd-gap        (Haiku — TCFD gap analysis from BRSR data)",
                "POST /api/nl-query        (Haiku — NL ESG query to filter params)",
                "POST /api/tcfd-pdf        (Sonnet — PDF/TCFD gap checker, P4-E)",
                "POST /api/generate-digest (Haiku — weekly ESG digest, P4-F)",
            ],
            "anthropic_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        }
except Exception:
    pass
