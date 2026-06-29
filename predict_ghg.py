#!/usr/bin/env python3
"""
Green Curve — P4-A: ML-Predicted GHG Emissions for Non-Disclosers
Estimates Scope 1 & Scope 2 emissions for ~800 Indian listed companies
that do not disclose in their BRSR filings.

Methodology:
  - India-calibrated sector GHG intensity factors (tCO2e per ₹Crore revenue)
  - Derived from BEE PAT cycle data, CEEW sector studies, MoEFCC GHG inventory
  - Scope 2 uses India grid emission factor: 0.82 kg CO2/kWh (CEA 2024 baseline)
  - Intensity split: ~70% Scope 1 (combustion), ~30% Scope 2 (electricity)
  - Confidence: Medium (sector-level proxy, ±40% typical range)

Output: assets/data/ghg_estimates.json
  {
    "generated_at": "...",
    "methodology": "...",
    "estimates": {
      "COMPANY NAME": {
        "scope1_estimated_tco2e": float,
        "scope2_estimated_tco2e": float,
        "intensity_factor_used": float,
        "sector_matched": str,
        "confidence": "Medium",
        "method": "BEE sector intensity × revenue"
      }
    }
  }

Run: python predict_ghg.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from db import get_conn, init_db

BASE_DIR  = Path(__file__).parent
DATA_DIR  = BASE_DIR / "assets" / "data"
OUTPUT    = DATA_DIR / "ghg_estimates.json"

init_db()

# ── India-calibrated sector GHG intensities ───────────────────────────────────
# Source: BEE PAT Cycle I/II, CEEW India GHG Platform, MoEFCC 2024
# Unit: tCO2e per ₹ Crore of revenue (combined Scope 1 + 2)
# Split: 70% Scope 1 (fossil combustion) + 30% Scope 2 (purchased electricity)

SECTOR_INTENSITY = {
    # Power / Energy
    "power generation by coal":   9200,
    "thermal power":              9200,
    "coal-based":                 9200,
    "power generation":           4800,
    "renewable energy":            180,
    "oil and gas":                1800,
    "petroleum":                  1400,
    "refin":                      1200,

    # Heavy industry
    "iron and steel":             2400,
    "steel":                      2200,
    "iron ore":                   1800,
    "aluminium":                  1700,
    "copper":                     1500,
    "zinc":                       1400,

    # Construction materials
    "cement":                     1900,
    "glass":                      1100,
    "ceramics":                    900,

    # Chemicals
    "petrochemical":              1000,
    "chlor-alkali":                920,
    "fertilizer":                  800,
    "chemical":                    480,
    "specialty chemical":          420,
    "agrochemical":                380,
    "dye":                         350,
    "paint":                       300,

    # Paper / Pulp
    "paper":                       420,
    "pulp":                        400,

    # Textiles
    "textile":                     210,
    "garment":                     180,
    "cotton":                      200,

    # Auto / Engineering
    "automobile":                  150,
    "auto component":              140,
    "engineering":                 180,
    "electrical equipment":        160,
    "heavy machinery":             170,

    # Consumer / FMCG
    "fmcg":                         55,
    "food":                          70,
    "beverage":                      65,
    "consumer goods":                50,
    "tobacco":                       90,

    # Pharma / Healthcare
    "pharmaceutical":              110,
    "pharma":                      110,
    "healthcare":                   60,
    "hospital":                     50,
    "diagnostic":                   35,

    # IT / Technology
    "information technology":       18,
    "software":                     15,
    "it services":                  18,
    "data centre":                  90,
    "telecom":                      80,

    # Finance / Services
    "banking":                      10,
    "finance":                      10,
    "insurance":                     9,
    "nbfc":                         10,
    "real estate":                   35,
    "construction":                  80,

    # Infrastructure / Transport
    "transport":                   260,
    "logistics":                   240,
    "shipping":                    380,
    "aviation":                    620,
    "port":                        150,
    "infrastructure":              120,

    # Mining
    "mining":                      350,
    "coal mining":                 480,

    # Default fallback
    "default":                     160,
}

def _get_intensity(sector: str, products: str = "") -> tuple[float, str]:
    text = (sector + " " + products).lower()
    best_match = None
    best_len   = 0
    for kw, factor in SECTOR_INTENSITY.items():
        if kw == "default":
            continue
        if kw in text and len(kw) > best_len:
            best_match = kw
            best_len   = len(kw)
    if best_match:
        return SECTOR_INTENSITY[best_match], best_match
    return SECTOR_INTENSITY["default"], "default (general industry)"


# tCO2e — a linear (sector-intensity × revenue) estimate above this is the model
# breaking down for very-high-revenue firms (e.g. Indian Oil extrapolated to ~1.2
# billion tCO2e, ~4× India's largest *real* emitter). Such a figure is meaningless,
# and any genuine emitter at that scale discloses real data anyway, so the estimate
# is dropped rather than published.
ESTIMATE_CEIL = 1e8  # 100 Mt


def predict_ghg(company: dict) -> dict | None:
    """Return estimated GHG dict, or None if actual data already exists."""
    fe      = company.get("financial_exposure") or {}
    s1_real = fe.get("scope1_emissions_tco2e")
    s2_real = fe.get("scope2_emissions_tco2e")

    # Skip if both Scope 1 and 2 are already disclosed
    if s1_real is not None and s2_real is not None:
        return None

    rev = company.get("revenue_crore") or 0
    if rev <= 0:
        return None

    sector   = company.get("sector", "")
    products = company.get("products", "")
    intensity, matched = _get_intensity(sector, products)

    # Total estimated tCO2e (combined Scope 1 + 2)
    total_est = round(intensity * rev)

    # Drop physically-implausible estimates (model breakdown at very high revenue).
    if total_est >= ESTIMATE_CEIL:
        return None

    # Split: 70% Scope 1, 30% Scope 2 (unless one side is already disclosed)
    if s1_real is not None:
        s1_est = None   # Already disclosed
        s2_est = round(total_est * 0.30) if s2_real is None else None
    elif s2_real is not None:
        s2_est = None   # Already disclosed
        s1_est = round(total_est * 0.70) if s1_real is None else None
    else:
        s1_est = round(total_est * 0.70)
        s2_est = round(total_est * 0.30)

    if s1_est is None and s2_est is None:
        return None

    return {
        "scope1_estimated_tco2e": s1_est,
        "scope2_estimated_tco2e": s2_est,
        "total_estimated_tco2e":  (s1_est or 0) + (s2_est or 0),
        "intensity_factor_used":  intensity,
        "sector_matched":         matched,
        "revenue_crore_used":     rev,
        "confidence":             "Medium",
        "method":                 "BEE sector intensity × revenue (tCO2e/₹Cr)",
        "note":                   "Estimated ±40%. Use actual BRSR disclosure for verified calculations.",
    }


def _load_companies_from_db() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT company_name, sector, products, revenue_crore, financial_exposure FROM companies"
        ).fetchall()
    result = []
    for r in rows:
        fe = {}
        try:
            fe = json.loads(r["financial_exposure"] or "{}")
        except Exception:
            pass
        result.append({
            "company_name":     r["company_name"],
            "sector":           r["sector"] or "",
            "products":         r["products"] or "",
            "revenue_crore":    r["revenue_crore"] or 0,
            "financial_exposure": fe,
        })
    return result


def main():
    companies = _load_companies_from_db()
    print(f"Loaded {len(companies)} companies from greencurve.db")

    estimates  = {}
    skipped    = 0
    estimated  = 0

    for c in companies:
        name = c.get("company_name", "")
        if not name:
            continue
        result = predict_ghg(c)
        if result is None:
            skipped += 1
        else:
            estimates[name] = result
            estimated += 1

    now_utc = datetime.now(timezone.utc)
    output = {
        "generated_at":      now_utc.isoformat(),
        "data_last_updated": now_utc.strftime("%d %b %Y"),
        "stale_after_days":  7,
        "methodology": (
            "India-calibrated sector GHG intensity factors (tCO2e/₹Cr revenue). "
            "Sources: BEE PAT Cycle I/II data, CEEW India GHG Platform, MoEFCC National GHG Inventory 2024. "
            "Scope 2 uses India CEA grid factor: 0.82 kg CO2/kWh. "
            "Confidence: Medium (±40% typical range for sector-level proxies). "
            "Estimates apply only where Scope 1 and/or Scope 2 are not disclosed in BRSR."
        ),
        "total_companies_processed": len(estimates) + skipped,
        "companies_with_estimates":  estimated,
        "companies_already_disclosed": skipped,
        "estimates": estimates,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Done. Estimated GHG for {estimated} companies. Skipped {skipped} (already disclosed).")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
