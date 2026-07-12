"""
Green Curve — ESG Company Data API
Serves all company data from SQLite instead of the static esg_quotient.json file.
Endpoints return the same shape as the original JSON so esg-intelligence.js
needs only one line changed (URL → /api/esg/data).

Admin endpoints are protected by GC_ADMIN_KEY header.
"""

import hashlib
import json
import os
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Optional

import logging

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from db import get_conn, init_db

logger = logging.getLogger(__name__)

router = APIRouter()
BASE_DIR = Path(__file__).parent

# ── Admin auth ────────────────────────────────────────────────────────────────
def require_admin(x_admin_key: str = Header(default="")):
    expected = os.environ.get("GC_ADMIN_KEY", "")
    if not expected or x_admin_key != expected:
        raise HTTPException(403, "Invalid admin key")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _loads(s):
    try:
        return json.loads(s or "null") or {}
    except Exception:
        return {}

def _loads_list(s):
    try:
        v = json.loads(s or "[]")
        return v if isinstance(v, list) else []
    except Exception:
        return []

def _row_to_company(row, lite: bool = False) -> dict:
    """Map a DB row to the company dict the frontend expects.

    When ``lite=True`` the single heaviest field — ``ai_summary`` (≈49% of the
    bulk payload, 1.27 MB across 1,227 companies) — is omitted. It is only ever
    consumed in on-demand contexts (the deep-dive overview and as searchable text
    in global search), never in the screener, charts, or aggregate tabs. The
    frontend lazy-fetches the full record via /api/esg/company/{name} when a
    deep-dive is opened. NOTE: financial_exposure is deliberately *kept* — it
    feeds _dcCoverage()/getConservativeScore() which run over all companies in
    the main view."""
    out = {
        "company_name":       row["company_name"],
        "cin":                row["cin"] or "",
        "nse_symbol":         row["nse_symbol"] or "",
        "sector":             row["sector"] or "",
        "products":           row["products"] or "",
        "revenue_crore":      row["revenue_crore"] or 0,
        "financial_year":     row["financial_year"] or "",
        "esg_risk_score":     row["esg_risk_score"] or 0,
        "risk_tier":          row["risk_tier"] or "Medium",
        "risk_breakdown":     _loads(row["risk_breakdown"]),
        "top_risk_factors":   _loads_list(row["top_risk_factors"]),
        "financial_exposure": _loads(row["financial_exposure"]),
        "supply_chain":       _loads(row["supply_chain"]),
        "governance":         _loads(row["governance"]),
        "double_materiality": _loads(row["double_materiality"]),
        "esg_targets":        _loads_list(row["esg_targets"]),
        "materials_exposed":  _loads_list(row["materials_exposed"]),
        "anomaly_flags":      _loads_list(row["anomaly_flags"]) if "anomaly_flags" in row.keys() else [],
        # XBRL content-upgrade metrics — compact, kept even in lite (feed the
        # screener/NL-query filters + benchmark chips). '.keys()' guard tolerates a
        # DB that hasn't been migrated yet.
        "sector_benchmark":   _loads(row["sector_benchmark"]) if "sector_benchmark" in row.keys() else {},
        "safety_metrics":     _loads(row["safety_metrics"]) if "safety_metrics" in row.keys() else {},
        "energy_mix":         _loads(row["energy_mix"]) if "energy_mix" in row.keys() else {},
        "waste_profile":      _loads(row["waste_profile"]) if "waste_profile" in row.keys() else {},
        "governance_signals": _loads(row["governance_signals"]) if "governance_signals" in row.keys() else {},
        "ghg_intensity_tco2e_per_cr": (row["ghg_intensity"] if "ghg_intensity" in row.keys() else None),
    }
    if not lite:
        out["ai_summary"] = row["ai_summary"] or ""
        # bottleneck_solutions is heavy (advisory text per issue) — full record only.
        out["bottleneck_solutions"] = _loads_list(row["bottleneck_solutions"]) if "bottleneck_solutions" in row.keys() else []
    return out

def _get_meta(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM esg_meta WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return default


def _compute_sector_averages(companies: list) -> dict:
    """Pre-compute E/S/G and ESG risk averages per sector for client-side blending."""
    sector_data: dict = defaultdict(lambda: {"esg": [], "e": [], "s": [], "g": []})
    for c in companies:
        sec = (c.get("sector") or "").strip()
        if not sec:
            continue
        rb = c.get("risk_breakdown") or {}
        sector_data[sec]["esg"].append(c.get("esg_risk_score") or 0)
        if rb.get("environmental") is not None:
            sector_data[sec]["e"].append(rb["environmental"])
        if rb.get("social") is not None:
            sector_data[sec]["s"].append(rb["social"])
        if rb.get("governance") is not None:
            sector_data[sec]["g"].append(rb["governance"])

    averages = {}
    for sec, vals in sector_data.items():
        averages[sec] = {
            "esg_avg": round(statistics.mean(vals["esg"]), 2) if vals["esg"] else None,
            "esg_stdev": round(statistics.stdev(vals["esg"]), 2) if len(vals["esg"]) >= 2 else 0,
            "e_avg": round(statistics.mean(vals["e"]), 2) if vals["e"] else None,
            "s_avg": round(statistics.mean(vals["s"]), 2) if vals["s"] else None,
            "g_avg": round(statistics.mean(vals["g"]), 2) if vals["g"] else None,
            "count": len(vals["esg"]),
        }
    return averages


# ── Response cache (in-memory, invalidated when DB changes) ───────────────────
# "body" holds the SERIALIZED JSON string, not the dict: JSONResponse would
# re-run json.dumps on ~3.8 MB of payload for every warm-cache hit, and the
# dict form of the payload costs several times more RAM than the string —
# both matter on the 1 GB prod VM (x2 uvicorn workers).
_esg_data_cache: dict = {"etag": None, "body": None}

def _invalidate_esg_cache():
    _esg_data_cache["etag"] = None
    _esg_data_cache["body"] = None


# ── Public read endpoints ─────────────────────────────────────────────────────

@router.get("/api/esg/data")
def get_full_data(request: Request):
    """Returns the same JSON shape as the original esg_quotient.json.
    esg-intelligence.js calls this URL instead of the static file.
    Includes ETag-based caching: unchanged data returns 304 Not Modified."""

    # Serve from in-memory cache if ETag matches. Cloudflare re-compresses
    # responses and downgrades the strong ETag to a weak one (W/"..."), so
    # browsers echo back the W/ form — strip it before comparing or the 304
    # path never fires for visitors behind the CDN.
    client_etag = request.headers.get("if-none-match", "").strip()
    if client_etag.startswith("W/"):
        client_etag = client_etag[2:]
    if _esg_data_cache["etag"] and _esg_data_cache["etag"] == client_etag:
        return JSONResponse(status_code=304, content=None)

    if _esg_data_cache["body"] and _esg_data_cache["etag"]:
        # Cache is warm but client doesn't have it — serve the pre-serialized body
        return Response(
            content=_esg_data_cache["body"],
            media_type="application/json",
            headers={
                "Cache-Control": "public, max-age=3600",
                "ETag": _esg_data_cache["etag"],
            },
        )

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM companies ORDER BY esg_risk_score DESC"
        ).fetchall()

    companies = [_row_to_company(r, lite=True) for r in rows]

    total  = len(companies)
    high   = sum(1 for c in companies if c["risk_tier"] == "High")
    medium = sum(1 for c in companies if c["risk_tier"] == "Medium")
    low    = sum(1 for c in companies if c["risk_tier"] == "Low")
    avg    = round(sum(c["esg_risk_score"] for c in companies) / total, 2) if total else 0

    stored_summary = _get_meta("summary", {})
    summary = {
        **stored_summary,
        "total_companies":       total,
        "high_risk_companies":   high,
        "medium_risk_companies": medium,
        "low_risk_companies":    low,
        "avg_esg_risk_score":    avg,
    }

    payload = {
        "generated_at":   _get_meta("generated_at", ""),
        "data_as_of":     _get_meta("data_as_of", ""),
        "summary":        summary,
        "companies":      companies,
        "regulations":    _get_meta("regulations", []),
        "factor_matrix":  _get_meta("factor_matrix", []),
        "supply_chain":   _get_meta("supply_chain_global", {}),
        "market_summary": _get_meta("market_summary", {}),
        "knowledge_base": _get_meta("knowledge_base", {}),
        "sector_averages": _compute_sector_averages(companies),
    }

    body_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    etag     = '"' + hashlib.md5(body_str.encode()).hexdigest() + '"'

    _esg_data_cache["etag"] = etag
    _esg_data_cache["body"] = body_str

    return Response(
        content=body_str,
        media_type="application/json",
        headers={
            "Cache-Control": "public, max-age=3600",
            "ETag": etag,
        },
    )


@router.get("/api/esg/company/{company_name}")
def get_company(company_name: str):
    """Look up by CIN first, then fall back to company_name for backwards compatibility."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM companies WHERE cin=?", (company_name,)).fetchone()
    if not row:
        row = conn.execute("SELECT * FROM companies WHERE company_name=?", (company_name,)).fetchone()
    if not row:
        raise HTTPException(404, "Company not found")
    return _row_to_company(row)


@router.get("/api/esg/by-cin/{cin}")
def get_company_by_cin(cin: str):
    """Look up a company by its CIN (Company Identification Number)."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM companies WHERE cin=?", (cin.upper(),)).fetchone()
    if not row:
        raise HTTPException(404, "Company not found")
    return _row_to_company(row)


@router.get("/api/esg/sectors")
def get_sectors():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT sector FROM companies WHERE sector != '' ORDER BY sector"
        ).fetchall()
    return {"sectors": [r["sector"] for r in rows]}


@router.get("/api/esg/stats")
def get_stats():
    with get_conn() as conn:
        total  = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        high   = conn.execute("SELECT COUNT(*) FROM companies WHERE risk_tier='High'").fetchone()[0]
        medium = conn.execute("SELECT COUNT(*) FROM companies WHERE risk_tier='Medium'").fetchone()[0]
        low    = conn.execute("SELECT COUNT(*) FROM companies WHERE risk_tier='Low'").fetchone()[0]
    return {"total": total, "high": high, "medium": medium, "low": low}


# ── Admin CRUD endpoints ──────────────────────────────────────────────────────

class CompanyIn(BaseModel):
    company_name:       str
    cin:                str = ""
    nse_symbol:         str = ""
    sector:             str = ""
    products:           str = ""
    revenue_crore:      float = 0
    financial_year:     str = ""
    esg_risk_score:     float = 0
    risk_tier:          str = "Medium"
    risk_breakdown:     dict = {}
    top_risk_factors:   list = []
    financial_exposure: dict = {}
    supply_chain:       dict = {}
    governance:         dict = {}
    double_materiality: dict = {}
    esg_targets:        list = []
    materials_exposed:  list = []
    ai_summary:         str = ""


@router.get("/api/admin/companies")
def admin_list_companies(
    search: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    risk_tier: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    _=Depends(require_admin),
):
    offset = (page - 1) * limit
    conditions = []
    params = []
    if search:
        conditions.append("(company_name LIKE ? OR cin LIKE ? OR nse_symbol LIKE ?)")
        q = f"%{search}%"
        params.extend([q, q, q])
    if sector:
        conditions.append("sector = ?")
        params.append(sector)
    if risk_tier:
        conditions.append("risk_tier = ?")
        params.append(risk_tier)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM companies {where}", params).fetchone()[0]
        rows  = conn.execute(
            f"SELECT id, company_name, cin, sector, esg_risk_score, risk_tier, updated_at FROM companies {where} ORDER BY company_name LIMIT ? OFFSET ?",
            params + [limit, offset]
        ).fetchall()
    return {
        "total": total,
        "page":  page,
        "pages": (total + limit - 1) // limit,
        "companies": [dict(r) for r in rows],
    }


@router.post("/api/admin/companies", status_code=201)
def admin_create_company(body: CompanyIn, _=Depends(require_admin)):
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO companies
                  (company_name,cin,nse_symbol,sector,products,revenue_crore,financial_year,
                   esg_risk_score,risk_tier,risk_breakdown,top_risk_factors,financial_exposure,
                   supply_chain,governance,double_materiality,esg_targets,materials_exposed,ai_summary)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                body.company_name, body.cin, body.nse_symbol, body.sector,
                body.products, body.revenue_crore, body.financial_year,
                body.esg_risk_score, body.risk_tier,
                json.dumps(body.risk_breakdown), json.dumps(body.top_risk_factors),
                json.dumps(body.financial_exposure), json.dumps(body.supply_chain),
                json.dumps(body.governance), json.dumps(body.double_materiality),
                json.dumps(body.esg_targets), json.dumps(body.materials_exposed),
                body.ai_summary,
            ))
    except Exception as e:
        raise HTTPException(409, f"Company already exists or DB error: {e}")
    _invalidate_esg_cache()
    return {"ok": True}


@router.put("/api/admin/companies/{company_name}")
def admin_update_company(company_name: str, body: CompanyIn, _=Depends(require_admin)):
    with get_conn() as conn:
        cur = conn.execute("""
            UPDATE companies SET
              cin=?,nse_symbol=?,sector=?,products=?,revenue_crore=?,financial_year=?,
              esg_risk_score=?,risk_tier=?,risk_breakdown=?,top_risk_factors=?,
              financial_exposure=?,supply_chain=?,governance=?,double_materiality=?,
              esg_targets=?,materials_exposed=?,ai_summary=?,
              updated_at=CURRENT_TIMESTAMP
            WHERE company_name=?
        """, (
            body.cin, body.nse_symbol, body.sector, body.products,
            body.revenue_crore, body.financial_year,
            body.esg_risk_score, body.risk_tier,
            json.dumps(body.risk_breakdown), json.dumps(body.top_risk_factors),
            json.dumps(body.financial_exposure), json.dumps(body.supply_chain),
            json.dumps(body.governance), json.dumps(body.double_materiality),
            json.dumps(body.esg_targets), json.dumps(body.materials_exposed),
            body.ai_summary, company_name,
        ))
        if cur.rowcount == 0:
            raise HTTPException(404, "Company not found")
    _invalidate_esg_cache()
    return {"ok": True}


@router.delete("/api/admin/companies/{company_name}")
def admin_delete_company(company_name: str, _=Depends(require_admin)):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM companies WHERE company_name=?", (company_name,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Company not found")
    _invalidate_esg_cache()
    return {"ok": True}


# ── Admin: daily blog generator (Anthropic-billed) ───────────────────────────
@router.post("/api/admin/blog/generate")
def admin_blog_generate(_=Depends(require_admin)):
    """Run the Climate Agent now — same script the gc-daily-blog timer runs."""
    import subprocess
    import sys as _sys
    try:
        proc = subprocess.run(
            [_sys.executable, str(BASE_DIR / "tools" / "climate_agent.py")],
            cwd=BASE_DIR, capture_output=True, text=True, timeout=240,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Blog generation timed out")
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-800:]
    if proc.returncode == 3:
        raise HTTPException(503, f"Blog generator dormant: {tail}")
    if proc.returncode != 0:
        raise HTTPException(500, f"Blog generation failed: {tail}")
    return {"ok": True, "output": tail}


# ── Admin: user plans & free-tier windows (AI usage caps) ────────────────────
# Plans gate the Claude-billed AI endpoints served by gcai (:8001), which reads
# the users table from this DB. free = 14-day trial window + weekly caps;
# admin can extend any account's window to 25 days (from signup) in one click.

def _plan_row(conn, email: str):
    row = conn.execute(
        "SELECT id, email, name, org, plan, role, created_at, free_tier_expires_at "
        "FROM users WHERE email=?", (email.strip().lower(),)
    ).fetchone()
    if not row:
        raise HTTPException(404, "No account with that email")
    return row


def _plan_payload(row) -> dict:
    from datetime import datetime, timedelta
    created = row["created_at"] or ""
    explicit = row["free_tier_expires_at"]
    effective = explicit
    if not effective and created:
        try:
            dt = datetime.fromisoformat(created.replace(" ", "T"))
            effective = (dt + timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            effective = None
    return {
        "email": row["email"], "name": row["name"], "org": row["org"],
        "plan": row["plan"] or "free", "role": row["role"],
        "created_at": created,
        "free_tier_expires_at": effective,
        "free_tier_extended": bool(explicit),
    }


class PlanIn(BaseModel):
    email: str
    plan: str = ""


@router.get("/api/admin/users/plan")
def admin_user_plan(email: str = Query(...), _=Depends(require_admin)):
    with get_conn() as conn:
        return _plan_payload(_plan_row(conn, email))


@router.post("/api/admin/users/extend-free-tier")
def admin_extend_free_tier(body: PlanIn, _=Depends(require_admin)):
    """One-click: extend the account's free-tier window to 25 days from signup."""
    from datetime import datetime, timedelta
    with get_conn() as conn:
        row = _plan_row(conn, body.email)
        try:
            created = datetime.fromisoformat((row["created_at"] or "").replace(" ", "T"))
        except ValueError:
            raise HTTPException(500, "Account has no valid created_at date")
        new_expiry = (created + timedelta(days=25)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE users SET free_tier_expires_at=? WHERE id=?",
                     (new_expiry, row["id"]))
        return _plan_payload(_plan_row(conn, body.email))


@router.post("/api/admin/users/set-plan")
def admin_set_plan(body: PlanIn, _=Depends(require_admin)):
    if body.plan not in ("free", "paid"):
        raise HTTPException(400, "plan must be 'free' or 'paid'")
    with get_conn() as conn:
        row = _plan_row(conn, body.email)
        conn.execute("UPDATE users SET plan=? WHERE id=?", (body.plan, row["id"]))
        return _plan_payload(_plan_row(conn, body.email))


@router.post("/api/admin/reimport")
def admin_reimport(_=Depends(require_admin)):
    """Re-run the JSON → SQLite migration from the current esg_quotient.json on disk."""
    json_path = BASE_DIR / "assets" / "data" / "esg_quotient.json"
    if not json_path.exists():
        raise HTTPException(404, "esg_quotient.json not found on server")
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(500, f"JSON parse error: {e}")

    companies = data.get("companies", [])
    inserted = updated = 0
    with get_conn() as conn:
        for c in companies:
            existing = conn.execute(
                "SELECT id FROM companies WHERE company_name=?", (c["company_name"],)
            ).fetchone()
            row = (
                c.get("cin",""), c.get("nse_symbol",""), c.get("sector",""),
                c.get("products",""), c.get("revenue_crore") or 0,
                c.get("financial_year",""), c.get("esg_risk_score") or 0,
                c.get("risk_tier","Medium"),
                json.dumps(c.get("risk_breakdown") or {}),
                json.dumps(c.get("top_risk_factors") or []),
                json.dumps(c.get("financial_exposure") or {}),
                json.dumps(c.get("supply_chain") or {}),
                json.dumps(c.get("governance") or {}),
                json.dumps(c.get("double_materiality") or {}),
                json.dumps(c.get("esg_targets") or []),
                json.dumps(c.get("materials_exposed") or []),
                c.get("ai_summary","") or "",
            )
            if existing:
                conn.execute("""
                    UPDATE companies SET
                      cin=?,nse_symbol=?,sector=?,products=?,revenue_crore=?,financial_year=?,
                      esg_risk_score=?,risk_tier=?,risk_breakdown=?,top_risk_factors=?,
                      financial_exposure=?,supply_chain=?,governance=?,double_materiality=?,
                      esg_targets=?,materials_exposed=?,ai_summary=?,updated_at=CURRENT_TIMESTAMP
                    WHERE company_name=?
                """, row + (c["company_name"],))
                updated += 1
            else:
                conn.execute("""
                    INSERT INTO companies
                      (cin,nse_symbol,sector,products,revenue_crore,financial_year,
                       esg_risk_score,risk_tier,risk_breakdown,top_risk_factors,
                       financial_exposure,supply_chain,governance,double_materiality,
                       esg_targets,materials_exposed,ai_summary,company_name)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, row + (c["company_name"],))
                inserted += 1

        # Store meta blobs
        for meta_key, field in [
            ("generated_at",    "generated_at"),
            ("data_as_of",      "data_as_of"),
            ("summary",         "summary"),
            ("regulations",     "regulations"),
            ("factor_matrix",   "factor_matrix"),
            ("supply_chain_global", "supply_chain"),
            ("market_summary",  "market_summary"),
            ("knowledge_base",  "knowledge_base"),
        ]:
            val = data.get(field)
            if val is not None:
                conn.execute(
                    "INSERT INTO esg_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
                    (meta_key, json.dumps(val))
                )

    _invalidate_esg_cache()
    return {"ok": True, "inserted": inserted, "updated": updated, "total": inserted + updated}


# ── AI Feedback ───────────────────────────────────────────────────────────────
class FeedbackIn(BaseModel):
    ai_type: str = ""
    company: str = ""
    helpful: int = -1


@router.post("/api/feedback")
def submit_feedback(body: FeedbackIn, request: Request):
    ip = request.client.host if request.client else "unknown"
    logger.info(
        "AI_FEEDBACK ai_type=%s company=%r helpful=%s ip=%s",
        body.ai_type, body.company, body.helpful, ip
    )
    return {"ok": True}


# ── Email waitlist ─────────────────────────────────────────────────────────────
class WaitlistIn(BaseModel):
    email: str = ""
    source: str = ""


@router.post("/api/auth/waitlist")
def join_waitlist(body: WaitlistIn, request: Request):
    ip = request.client.host if request.client else "unknown"
    logger.info("WAITLIST email=%r source=%r ip=%s", body.email, body.source, ip)
    return {"ok": True}
