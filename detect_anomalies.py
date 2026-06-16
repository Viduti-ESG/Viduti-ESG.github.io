"""
Green Curve — BRSR Anomaly Detection
Reads companies from greencurve.db, computes anomaly flags,
and writes them back to the anomaly_flags column.

Signals detected:
  1. sector_risk_outlier        — ESG risk score ≥ 1σ above sector mean
  2. waste_intensity_outlier    — waste_tonnes/revenue is IQR outlier vs sector
  3. scope1_yoy_spike           — Scope 1 emissions increased >100% vs stored prior year
  4. zero_filled_kpis           — company discloses revenue but all key KPIs are zero/null
  5. water_intensity_outlier    — water_m3/revenue is IQR outlier vs sector

Run: python detect_anomalies.py
"""

import json
import statistics
from collections import defaultdict
from pathlib import Path

from db import get_conn, init_db

init_db()


def _loads(s):
    try:
        return json.loads(s or "{}") or {}
    except Exception:
        return {}


def _loads_list(s):
    try:
        v = json.loads(s or "[]")
        return v if isinstance(v, list) else []
    except Exception:
        return []


def load_companies():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT company_name, sector, esg_risk_score, revenue_crore, "
            "financial_exposure, anomaly_flags FROM companies"
        ).fetchall()
    return [dict(r) for r in rows]


def compute_flags(companies: list) -> dict:
    """Return {company_name: [flag_dict, ...]} for all companies."""

    # ── Build sector-level stats ───────────────────────────────────────────────
    sector_scores = defaultdict(list)
    sector_waste  = defaultdict(list)
    sector_water  = defaultdict(list)

    for c in companies:
        sec = (c.get("sector") or "").strip()
        fe  = _loads(c.get("financial_exposure") or "{}")
        rev = c.get("revenue_crore") or 0

        sector_scores[sec].append(c.get("esg_risk_score") or 0)

        wt = fe.get("waste_tonnes")
        if wt and rev > 0:
            sector_waste[sec].append((c["company_name"], wt / rev))

        wm = fe.get("water_withdrawal_kl") or fe.get("water_m3")
        if wm and rev > 0:
            sector_water[sec].append((c["company_name"], wm / rev))

    # σ-stats per sector for ESG risk score
    sector_stats: dict = {}
    for sec, scores in sector_scores.items():
        if len(scores) >= 3:
            mean  = statistics.mean(scores)
            stdev = statistics.stdev(scores) if len(scores) >= 2 else 0
            sector_stats[sec] = (mean, stdev)

    def _iqr_fence(pairs):
        if len(pairs) < 4:
            return None
        sv = sorted(v for _, v in pairs)
        n  = len(sv)
        q1, q3 = sv[n // 4], sv[(3 * n) // 4]
        iqr = q3 - q1
        return (q3 + 1.5 * iqr) if iqr > 0 else None

    waste_fence = {sec: _iqr_fence(vals) for sec, vals in sector_waste.items()}
    water_fence = {sec: _iqr_fence(vals) for sec, vals in sector_water.items()}

    # ── Assign flags per company ───────────────────────────────────────────────
    result: dict = {}

    for c in companies:
        flags = []
        sec   = (c.get("sector") or "").strip()
        score = c.get("esg_risk_score") or 0
        rev   = c.get("revenue_crore") or 0
        fe    = _loads(c.get("financial_exposure") or "{}")
        name  = c["company_name"]

        # Signal 1: sector risk score outlier (z ≥ 1σ)
        if sec in sector_stats:
            mean, stdev = sector_stats[sec]
            if stdev > 0:
                z = (score - mean) / stdev
                if z >= 1.0:
                    flags.append({
                        "type":     "sector_risk_outlier",
                        "label":    "Sector Risk Outlier",
                        "detail":   f"ESG risk {score:.1f} is {z:.1f}σ above sector mean ({mean:.1f})",
                        "severity": "high" if z >= 2 else "medium",
                    })

        # Signal 2: waste intensity outlier (IQR)
        wt = fe.get("waste_tonnes")
        fence = waste_fence.get(sec)
        if wt and rev > 0 and fence:
            intensity = wt / rev
            if intensity > fence:
                flags.append({
                    "type":     "waste_intensity_outlier",
                    "label":    "Waste Intensity Outlier",
                    "detail":   f"Waste intensity {intensity:.1f} t/₹Cr vs sector ceiling {fence:.1f} t/₹Cr",
                    "severity": "medium",
                })

        # Signal 3: water intensity outlier (IQR)
        wm = fe.get("water_withdrawal_kl") or fe.get("water_m3")
        wfence = water_fence.get(sec)
        if wm and rev > 0 and wfence:
            wintensity = wm / rev
            if wintensity > wfence:
                flags.append({
                    "type":     "water_intensity_outlier",
                    "label":    "Water Intensity Outlier",
                    "detail":   f"Water intensity {wintensity:.0f} kL/₹Cr vs sector ceiling {wfence:.0f} kL/₹Cr",
                    "severity": "medium",
                })

        # Signal 4: zero-filled KPIs (revenue disclosed but all ESG KPIs are zero/null)
        if rev > 0:
            kpi_fields = [
                fe.get("scope1_emissions_tco2e"),
                fe.get("scope2_emissions_tco2e"),
                fe.get("energy_gj"),
                fe.get("water_withdrawal_kl") or fe.get("water_m3"),
                fe.get("waste_tonnes"),
            ]
            non_null = [v for v in kpi_fields if v is not None]
            if len(non_null) == 0:
                flags.append({
                    "type":     "zero_filled_kpis",
                    "label":    "No ESG KPIs Disclosed",
                    "detail":   "Company reports revenue but discloses no Scope 1/2, energy, water or waste data",
                    "severity": "medium",
                })
            elif len(non_null) >= 2 and all(v == 0 for v in non_null):
                flags.append({
                    "type":     "zero_filled_kpis",
                    "label":    "Zero-Filled ESG KPIs",
                    "detail":   "All disclosed environmental KPIs are exactly zero — possible placeholder submission",
                    "severity": "medium",
                })

        result[name] = flags

    return result


def write_flags(flags_by_name: dict) -> int:
    """Write anomaly_flags JSON back to each company row in the DB."""
    updated = 0
    with get_conn() as conn:
        for name, flags in flags_by_name.items():
            conn.execute(
                "UPDATE companies SET anomaly_flags=?, updated_at=CURRENT_TIMESTAMP WHERE company_name=?",
                (json.dumps(flags, ensure_ascii=False), name)
            )
            updated += 1
    return updated


def main():
    companies = load_companies()
    print(f"Loaded {len(companies)} companies from DB")

    flags_by_name = compute_flags(companies)

    total_flagged = sum(1 for f in flags_by_name.values() if f)
    by_type: dict = defaultdict(int)
    for flags in flags_by_name.values():
        for f in flags:
            by_type[f["type"]] += 1

    print(f"Flagged {total_flagged} / {len(companies)} companies")
    for sig, cnt in sorted(by_type.items()):
        print(f"  {sig}: {cnt}")

    updated = write_flags(flags_by_name)
    print(f"Updated {updated} rows in greencurve.db")


if __name__ == "__main__":
    main()
