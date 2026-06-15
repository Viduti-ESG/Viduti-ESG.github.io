"""
Green Curve — ESG Company Data API
Serves all company data from SQLite instead of the static esg_quotient.json file.
Endpoints return the same shape as the original JSON so esg-intelligence.js
needs only one line changed (URL → /api/esg/data).

Admin endpoints are protected by GC_ADMIN_KEY header.
"""

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel

from db import get_conn, init_db

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

def _row_to_company(row) -> dict:
    return {
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
        "ai_summary":         row["ai_summary"] or "",
    }

def _get_meta(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM esg_meta WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return default


# ── Public read endpoints ─────────────────────────────────────────────────────

@router.get("/api/esg/data")
def get_full_data():
    """Returns the same JSON shape as the original esg_quotient.json.
    esg-intelligence.js calls this URL instead of the static file."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM companies ORDER BY esg_risk_score DESC"
        ).fetchall()

    companies = [_row_to_company(r) for r in rows]

    # Rebuild summary from live DB counts
    total = len(companies)
    high   = sum(1 for c in companies if c["risk_tier"] == "High")
    medium = sum(1 for c in companies if c["risk_tier"] == "Medium")
    low    = sum(1 for c in companies if c["risk_tier"] == "Low")
    avg    = round(sum(c["esg_risk_score"] for c in companies) / total, 2) if total else 0

    # Pull stored meta blobs; fall back to empty defaults
    stored_summary    = _get_meta("summary", {})
    regulations       = _get_meta("regulations", [])
    factor_matrix     = _get_meta("factor_matrix", [])
    supply_chain      = _get_meta("supply_chain_global", {})
    market_summary    = _get_meta("market_summary", {})
    knowledge_base    = _get_meta("knowledge_base", {})
    generated_at      = _get_meta("generated_at", "")
    data_as_of        = _get_meta("data_as_of", "")

    summary = {
        **stored_summary,
        "total_companies":    total,
        "high_risk_companies": high,
        "medium_risk_companies": medium,
        "low_risk_companies": low,
        "avg_esg_risk_score": avg,
    }

    return {
        "generated_at":  generated_at,
        "data_as_of":    data_as_of,
        "summary":       summary,
        "companies":     companies,
        "regulations":   regulations,
        "factor_matrix": factor_matrix,
        "supply_chain":  supply_chain,
        "market_summary": market_summary,
        "knowledge_base": knowledge_base,
    }


@router.get("/api/esg/company/{company_name}")
def get_company(company_name: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM companies WHERE company_name=?", (company_name,)
        ).fetchone()
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
    return {"ok": True}


@router.delete("/api/admin/companies/{company_name}")
def admin_delete_company(company_name: str, _=Depends(require_admin)):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM companies WHERE company_name=?", (company_name,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Company not found")
    return {"ok": True}


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

    return {"ok": True, "inserted": inserted, "updated": updated, "total": inserted + updated}
