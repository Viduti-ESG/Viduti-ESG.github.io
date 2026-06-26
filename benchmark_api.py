"""
Green Curve — Peer Benchmarking API.
Endpoints under /api/benchmark/*

Pillar 6 of the retention ecosystem: "you vs your peers" sector-relative
benchmarking. The value compounds with coverage (more companies → sharper
percentiles) and can't be cheaply replicated, so it's a quiet but durable moat.

Reads the companies table (Green Curve's own scores derived from public BRSR
filings). esg_risk_score is a RISK score — LOWER is better — so percentiles are
framed as "lower risk than X% of the sector".

Read endpoints are PUBLIC (this is public BRSR-derived data already shown on the
company pages) — which also makes the benchmark pages an SEO/discovery asset.

Legal: simple, transparent percentiles over Green Curve's OWN single score — no
multi-agency consensus weighting (steers clear of the CSRHub patent). Output is
labelled as Green Curve's analysis, not a SEBI-registered ESG rating.
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from db import get_conn

logger = logging.getLogger(__name__)
router = APIRouter()

# Sub-dimensions in risk_breakdown that are RISK scores (lower = better).
SUBDIMS = [
    ("environmental", "Environmental"),
    ("social", "Social"),
    ("governance", "Governance"),
    ("ghg_intensity", "GHG Intensity"),
    ("energy_transition", "Energy Transition"),
    ("water_intensity", "Water Intensity"),
    ("waste_intensity", "Waste Intensity"),
    ("epr_exposure", "EPR Exposure"),
    ("hr_risk", "Human Capital"),
    ("compliance_risk", "Compliance"),
]

DISCLAIMER = ("Percentiles are Green Curve's own analysis of public SEBI BRSR filings — "
              "not a rating issued by a SEBI-registered ESG Rating Provider. Lower risk = better.")


# ── Helpers ──────────────────────────────────────────────────────────────────────
def _num(v):
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None


def _quantile(sorted_vals: list, q: float):
    """Linear-interpolation quantile on a pre-sorted list."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 2)
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    hi = min(lo + 1, len(sorted_vals) - 1)
    return round(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac, 2)


def _dist(vals: list) -> dict:
    s = sorted(v for v in vals if v is not None)
    if not s:
        return {"count": 0}
    return {
        "count": len(s),
        "min": round(s[0], 2),
        "p25": _quantile(s, 0.25),
        "median": _quantile(s, 0.50),
        "p75": _quantile(s, 0.75),
        "max": round(s[-1], 2),
        "avg": round(sum(s) / len(s), 2),
    }


def _pct_lower_risk(value: float, cohort: list) -> Optional[float]:
    """% of the cohort (excluding self) that this value has LOWER risk than."""
    others = [v for v in cohort if v is not None]
    if len(others) <= 1:
        return None
    higher = sum(1 for v in others if v > value)
    return round(100.0 * higher / (len(others) - 1), 0)


def _load_companies(conn) -> list:
    rows = conn.execute(
        "SELECT company_name, cin, nse_symbol, sector, esg_risk_score, risk_tier, "
        "risk_breakdown FROM companies"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["_rb"] = json.loads(d.get("risk_breakdown") or "{}")
        except Exception:
            d["_rb"] = {}
        d["esg_risk_score"] = _num(d.get("esg_risk_score"))
        out.append(d)
    return out


def _find(companies: list, name: str = "", cin: str = ""):
    if cin:
        for c in companies:
            if (c.get("cin") or "").lower() == cin.lower():
                return c
    if name:
        nl = name.lower().strip()
        for c in companies:
            if (c.get("company_name") or "").lower() == nl:
                return c
        for c in companies:                       # fall back to contains-match
            if nl in (c.get("company_name") or "").lower():
                return c
    return None


# ════════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/benchmark/sectors")
def sectors():
    companies = _load_companies(get_conn())
    by_sector: dict = {}
    for c in companies:
        by_sector.setdefault(c.get("sector") or "Unclassified", []).append(c["esg_risk_score"])
    out = []
    for sec, vals in by_sector.items():
        d = _dist(vals)
        if d["count"]:
            out.append({"sector": sec, **d})
    out.sort(key=lambda x: -x["count"])
    return {"sectors": out, "total_companies": len(companies), "disclaimer": DISCLAIMER}


@router.get("/api/benchmark/company")
def company_benchmark(name: str = "", cin: str = ""):
    if not name and not cin:
        raise HTTPException(400, "Provide name or cin")
    companies = _load_companies(get_conn())
    target = _find(companies, name, cin)
    if not target:
        raise HTTPException(404, "Company not found")

    sector = target.get("sector") or "Unclassified"
    cohort = [c for c in companies if (c.get("sector") or "Unclassified") == sector]
    cohort_scores = [c["esg_risk_score"] for c in cohort]
    all_scores = [c["esg_risk_score"] for c in companies]
    tscore = target["esg_risk_score"]

    # overall + sector percentile (lower risk than X% of peers)
    sector_pct = _pct_lower_risk(tscore, cohort_scores) if tscore is not None else None
    overall_pct = _pct_lower_risk(tscore, all_scores) if tscore is not None else None

    # sector rank (1 = lowest risk)
    ranked = sorted([c for c in cohort if c["esg_risk_score"] is not None],
                    key=lambda c: c["esg_risk_score"])
    rank = next((i + 1 for i, c in enumerate(ranked) if c["company_name"] == target["company_name"]), None)

    # nearest peers: window of ±4 around the company in the sector ranking
    peers = []
    if rank:
        i = rank - 1
        for c in ranked[max(0, i - 4): i + 5]:
            peers.append({
                "company_name": c["company_name"],
                "esg_risk_score": c["esg_risk_score"],
                "risk_tier": c["risk_tier"],
                "is_target": c["company_name"] == target["company_name"],
            })

    # sub-dimension percentiles within sector
    subdims = []
    for key, label in SUBDIMS:
        tval = _num(target["_rb"].get(key))
        if tval is None:
            continue
        cohort_vals = [_num(c["_rb"].get(key)) for c in cohort]
        cohort_vals = [v for v in cohort_vals if v is not None]
        if len(cohort_vals) < 2:
            continue
        subdims.append({
            "key": key, "label": label, "value": round(tval, 2),
            "sector_median": _quantile(sorted(cohort_vals), 0.50),
            "pct_lower_risk": _pct_lower_risk(tval, cohort_vals),
        })

    return {
        "company": {
            "company_name": target["company_name"], "cin": target.get("cin"),
            "nse_symbol": target.get("nse_symbol"), "sector": sector,
            "esg_risk_score": tscore, "risk_tier": target.get("risk_tier"),
        },
        "sector": sector,
        "sector_size": len(cohort),
        "sector_rank": rank,
        "sector_percentile": sector_pct,     # lower risk than X% of sector
        "overall_percentile": overall_pct,
        "sector_distribution": _dist(cohort_scores),
        "overall_distribution": _dist(all_scores),
        "peers": peers,
        "subdimensions": subdims,
        "disclaimer": DISCLAIMER,
    }


@router.get("/api/benchmark/compare")
def compare(names: str = ""):
    """Compare up to 6 companies (names separated by | or ,)."""
    raw = [n.strip() for n in names.replace("|", ",").split(",") if n.strip()]
    if not raw:
        raise HTTPException(400, "Provide names (separated by | or ,)")
    raw = raw[:6]
    companies = _load_companies(get_conn())
    all_scores = [c["esg_risk_score"] for c in companies]

    result = []
    for n in raw:
        t = _find(companies, n)
        if not t:
            result.append({"query": n, "found": False})
            continue
        sector = t.get("sector") or "Unclassified"
        cohort_scores = [c["esg_risk_score"] for c in companies
                         if (c.get("sector") or "Unclassified") == sector]
        row = {
            "query": n, "found": True,
            "company_name": t["company_name"], "sector": sector,
            "esg_risk_score": t["esg_risk_score"], "risk_tier": t.get("risk_tier"),
            "sector_percentile": _pct_lower_risk(t["esg_risk_score"], cohort_scores) if t["esg_risk_score"] is not None else None,
            "overall_percentile": _pct_lower_risk(t["esg_risk_score"], all_scores) if t["esg_risk_score"] is not None else None,
            "subdimensions": {},
        }
        for key, label in SUBDIMS[:6]:
            v = _num(t["_rb"].get(key))
            if v is not None:
                row["subdimensions"][label] = round(v, 2)
        result.append(row)
    return {"companies": result, "disclaimer": DISCLAIMER}
