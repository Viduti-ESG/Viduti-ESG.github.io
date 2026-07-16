#!/usr/bin/env python3
"""
Green Curve — AI API (P3 features)
Endpoints:
  POST /api/ccts-scorecard  — CCTS Carbon Credit Trading Scheme scorecard (Claude Haiku)
  POST /api/epr-scorecard   — EPR obligation remediation plan (Claude Haiku)
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
import logging
import os
import time
import threading
from collections import defaultdict
from typing import Any, Optional

logger = logging.getLogger(__name__)

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
_rl_lock        = threading.Lock()
_rl_counts: dict = defaultdict(list)
_rl_last_prune  = time.monotonic()
_RL_PRUNE_EVERY = 300  # prune stale keys every 5 minutes

def _prune_rl_cache(now: float, window: int) -> None:
    """Evict IP keys whose most-recent timestamp is older than 2× the window."""
    global _rl_last_prune
    if now - _rl_last_prune < _RL_PRUNE_EVERY:
        return
    _rl_last_prune = now
    stale = [k for k, ts in _rl_counts.items() if not ts or now - max(ts) > window * 2]
    for k in stale:
        del _rl_counts[k]

def _rate_limit(request: Request, limit: int, window: int = 60) -> None:
    ip  = request.client.host if request.client else "unknown"
    key = f"{ip}:{request.url.path}"
    now = time.monotonic()
    with _rl_lock:
        _prune_rl_cache(now, window)
        _rl_counts[key] = [t for t in _rl_counts[key] if now - t < window]
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


HAIKU  = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

# ── LLM provider routing ──────────────────────────────────────────────────────
# Two privacy-safe, commercial-OK lanes (see memory feedback_ai_vendor_constraints):
#   • groq      — free, no card, does NOT train on inputs, ZDR opt-in. Used for
#                 PUBLIC-company analysis. Open models (Llama-class).
#   • anthropic — frontier quality; does NOT train; ZDR/DPA for client data.
# GC_LLM_PROVIDER = auto (default) | groq | anthropic.
#   auto → try Groq first (free, works even when the Claude balance is empty),
#          then fall back to Claude if a key is configured.
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


def _providers_in_order() -> list[str]:
    pref       = os.environ.get("GC_LLM_PROVIDER", "auto").lower()
    have_groq  = bool(os.environ.get("GROQ_API_KEY"))
    have_claude = bool(os.environ.get("ANTHROPIC_API_KEY")) and _ANTHROPIC_AVAILABLE
    if pref == "groq":
        order = ["groq"]
    elif pref in ("anthropic", "claude"):
        order = ["anthropic"]
    else:  # auto — prefer the free/no-credit-needed provider first
        order = ["groq", "anthropic"]
    avail = {"groq": have_groq, "anthropic": have_claude}
    return [p for p in order if avail[p]]


def _groq_ask_json(system: str, user: str, max_tokens: int) -> Any:
    """Call Groq's OpenAI-compatible chat API and return parsed JSON.

    Uses httpx (already a dependency of the anthropic SDK), so no new package is
    needed on the server. JSON mode keeps the reply parseable; _parse_json still
    strips fences defensively."""
    import httpx
    key = os.environ["GROQ_API_KEY"]
    resp = httpx.post(
        GROQ_URL,
        timeout=60,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
    )
    resp.raise_for_status()
    return _parse_json(resp.json()["choices"][0]["message"]["content"])


def _parse_json(text: str) -> Any:
    """Parse model output into JSON, tolerating ``` fences and trailing prose."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Salvage the outermost {...} object if the model added stray text.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _ask_json(model: str, system: str, user: str, max_tokens: int = 600) -> Any:
    """Call Claude and return parsed JSON.

    The assistant turn is prefilled with ``{`` so the model continues a JSON
    object directly — it cannot wrap the reply in a markdown code fence, which
    removes the most common cause of parse failures. _parse_json still strips
    fences/prose defensively in case a model ignores the prefill.

    Routes across configured providers (Groq → Claude by default) so the AI
    features keep working on the free Groq lane even when the Claude balance is
    empty. Prompt caching note: caching the system prompt was evaluated and is
    NOT worth enabling on the Claude path — every system prompt here is ~270–440
    tokens, below the Anthropic cache minimums (1024 Sonnet / 2048 Haiku), so
    cache_control would be silently ignored.
    """
    providers = _providers_in_order()
    if not providers:
        raise RuntimeError(
            "No LLM provider configured. Set GROQ_API_KEY (free, no card) "
            "or ANTHROPIC_API_KEY."
        )
    last_err: Optional[Exception] = None
    for provider in providers:
        try:
            if provider == "groq":
                return _groq_ask_json(system, user, max_tokens)
            # Anthropic: prefill the assistant turn with "{" so it continues a
            # JSON object directly (can't wrap the reply in a code fence).
            msg = _claude().messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": "{"},
                ],
            )
            return _parse_json("{" + msg.content[0].text)
        except Exception as e:  # noqa: BLE001 — try the next provider
            last_err = e
            continue
    raise last_err if last_err else RuntimeError("All LLM providers failed")


# ── Pydantic models ────────────────────────────────────────────────────────────

class CCTSRequest(BaseModel):
    # Length caps bound any prompt-injection payload in free-text fields that are
    # interpolated into the LLM prompt (defense-in-depth; see review finding 4).
    company_name:    str = Field(..., max_length=200)
    sector:          str = Field("", max_length=120)
    products:        str = Field("", max_length=1000)
    scope1_emissions: Optional[float] = None
    scope2_emissions: Optional[float] = None
    brsr_assurance:  str = Field("None", max_length=50)
    compliance_risk: Optional[float] = None
    ghg_intensity:   Optional[float] = None
    revenue_crore:   Optional[float] = None
    esg_targets:     list[dict] = Field(default_factory=list, max_length=20)


class TCFDRequest(BaseModel):
    company_name:          str = Field(..., max_length=200)
    sector:                str = Field("", max_length=120)
    scope1_emissions:      Optional[float] = None
    scope2_emissions:      Optional[float] = None
    scope3_emissions:      Optional[float] = None
    brsr_assurance:        str = Field("None", max_length=50)
    compliance_risk:       Optional[float] = None
    governance_risk:       Optional[float] = None
    anti_corruption_policy: str = Field("Unknown", max_length=50)
    esg_targets:           list[dict] = Field(default_factory=list, max_length=20)


class EPRRequest(BaseModel):
    stream:        str = Field(..., max_length=40)   # plastic | ewaste | battery | tyre
    category:      str = Field("", max_length=200)    # human-readable category label
    qty_tonnes:    float          # quantity placed on market (t/yr)
    target_pct:    float          # recycling/collection target (%)
    done_tonnes:   float = 0.0    # already collected/recycled (t)
    shortfall_t:   float = 0.0    # tonnes still to cover
    cost_inr:      float = 0.0    # indicative procurement cost (₹)
    ec_inr:        float = 0.0    # indicative environmental compensation if unaddressed (₹)
    fy:            str = Field("", max_length=20)


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
ESG targets: {json.dumps([str(t.get('metric',''))[:100] for t in payload.esg_targets[:5]])}"""

    try:
        return _ask_json(HAIKU, CCTS_SYSTEM, data_summary, max_tokens=700)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {e}")


# ── EPR Obligation Remediation Plan ──────────────────────────────────────────────

EPR_SYSTEM = """You are an expert on India's Extended Producer Responsibility (EPR) regime administered by the CPCB, covering plastic packaging, e-waste, batteries and tyres.
Given a company's EPR position for one waste stream, return a JSON remediation plan that helps them meet their obligation cost-effectively.

Return ONLY valid JSON with this exact structure:
{
  "obligations": [
    {
      "name": "Short obligation name",
      "detail": "1-sentence specific, quantified observation or action for THIS company's numbers",
      "status": "met|attention|gap"
    }
  ],
  "priority": "high|medium|low",
  "actions": ["Prioritised, specific action 1", "action 2", "... up to 5"],
  "disclaimer": "One-sentence reminder that figures are indicative and to verify against CPCB notifications."
}

Assess obligations relevant to the stream, e.g.: registration on the correct CPCB portal; meeting the recycling/collection target; procuring category-specific certificates for the shortfall; certificate traceability and GST-compliant invoicing (CPCB flagged fake certificates); annual return filing; for plastic, the 2026 mandatory recycled-content ramp (30%→60% rigid by FY2028-29) and the withdrawal of End-of-Life (EOL) certificates.
Be specific and quantified: reference the company's shortfall in tonnes, the procurement cost vs the higher environmental-compensation cost, and the Jan–Mar price-spike (advise procuring early). If shortfall is zero, mark targets 'met' and focus actions on documentation and forward planning.
Set priority 'high' when there is a material shortfall and the procurement cost is large, 'medium' for moderate gaps, 'low' when largely on track."""

@router.post("/epr-scorecard")
async def epr_scorecard(request: Request, payload: EPRRequest):
    _rate_limit(request, limit=30)
    data_summary = f"""Waste stream: {payload.stream}
Category: {payload.category or 'Not specified'}
Financial year: {payload.fy or 'Not specified'}
Quantity placed on market: {payload.qty_tonnes} tonnes/year
Recycling/collection target: {payload.target_pct}%
Already collected/recycled: {payload.done_tonnes} tonnes
Shortfall still to cover: {payload.shortfall_t} tonnes
Indicative certificate procurement cost: ₹{payload.cost_inr:,.0f}
Indicative Environmental Compensation if unaddressed: ₹{payload.ec_inr:,.0f}"""

    try:
        return _ask_json(HAIKU, EPR_SYSTEM, data_summary, max_tokens=700)
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
    targets_str = ", ".join([str(t.get("metric", ""))[:100] for t in payload.esg_targets[:5]]) or "None"
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
        return _ask_json(HAIKU, TCFD_SYSTEM, data_summary, max_tokens=800)
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
    "min_renewable": 0.0,
    "max_ghg_intensity": 0.0,
    "has_fatalities": true|false,
    "sort": "esg_desc|water_intensity_desc|renewable_desc|ghg_intensity_asc",
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
- min_renewable: minimum renewable share of energy, PERCENT 0–100 (e.g. "companies with over 50% renewable energy" -> min_renewable: 50)
- max_ghg_intensity: maximum GHG intensity in tCO2e per ₹crore of revenue (e.g. "low-carbon-intensity companies" -> a small value like 5); lower = cleaner
- has_fatalities: true = only companies that reported workplace fatalities; false = only those with zero fatalities
- sort: "esg_desc" (default), "water_intensity_desc", "renewable_desc" (greenest first), "ghg_intensity_asc" (lowest carbon intensity first)
- limit: max rows to return (default 50, max 100)

Map intent to these fields, e.g. "greenest IT companies" -> {sector:"it", sort:"renewable_desc"};
"chemical companies with any workplace fatalities" -> {sector:"chemical", has_fatalities:true}.
Only include fields the user asked about. If the query is vague, return reasonable defaults."""

@router.post("/nl-query")
async def nl_query(request: Request, payload: NLQueryRequest):
    _rate_limit(request, limit=30)
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query is empty")
    try:
        return _ask_json(HAIKU, NL_SYSTEM, payload.query, max_tokens=300)
    except Exception:
        logger.exception("nl-query parsing failed")
        raise HTTPException(status_code=500, detail="Could not parse that query. Please rephrase and try again.")


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


@router.post("/tcfd-pdf")
async def tcfd_pdf(request: Request, payload: TCFDPDFRequest):
    _rate_limit(request, limit=5)  # Sonnet is ~10× more expensive
    if not payload.text or len(payload.text.strip()) < 200:
        raise HTTPException(status_code=400, detail="Document text too short. Please upload a valid sustainability or annual report.")
    text_excerpt = payload.text[:15000]  # Cap at ~15k chars
    user_msg = f"File: {payload.filename or 'uploaded document'}\n\n--- DOCUMENT TEXT ---\n{text_excerpt}\n--- END ---\n\nAssess this document for TCFD alignment."
    try:
        return _ask_json(SONNET, TCFD_PDF_SYSTEM, user_msg, max_tokens=2000)
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
    email:          str = Field(..., max_length=254)
    company_name:   str = Field("", max_length=200)
    sector:         str = Field("", max_length=120)
    watchlist:      list[str] = Field(default_factory=list, max_length=50)
    esg_risk_score: Optional[float] = None
    week_of:        str = Field("", max_length=20)  # ISO date string


@router.post("/generate-digest")
async def generate_digest(request: Request, payload: DigestRequest):
    _rate_limit(request, limit=10)  # digest is per-subscriber, lower limit
    context = f"""Subscriber: {payload.email}
Company: {payload.company_name or 'Not specified'}
Sector: {payload.sector or 'Not specified'}
ESG Risk Score: {payload.esg_risk_score or 'Not provided'} / 10
Watchlist companies: {', '.join(w[:100] for w in payload.watchlist[:10]) or 'None set'}
Week of: {payload.week_of or 'Current week'}"""

    try:
        return _ask_json(HAIKU, DIGEST_SYSTEM, context, max_tokens=800)
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
                "POST /api/epr-scorecard   (Haiku — EPR obligation remediation plan)",
                "POST /api/tcfd-gap        (Haiku — TCFD gap analysis from BRSR data)",
                "POST /api/nl-query        (Haiku — NL ESG query to filter params)",
                "POST /api/tcfd-pdf        (Sonnet — PDF/TCFD gap checker, P4-E)",
                "POST /api/generate-digest (Haiku — weekly ESG digest, P4-F)",
            ],
            "anthropic_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "groq_configured": bool(os.environ.get("GROQ_API_KEY")),
            "llm_providers": _providers_in_order(),
        }
except Exception:
    pass
