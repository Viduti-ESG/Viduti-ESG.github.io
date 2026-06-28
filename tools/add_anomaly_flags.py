"""
add_anomaly_flags.py — Computes anomaly_flags for every company in esg_quotient.json
and writes them back in-place.

Anomaly types match _ANOMALY_MAP in esg-intelligence.js:
  ghg_anomaly, water_anomaly, waste_intensity_anomaly,
  compliance_outlier, epr_gap, sector_risk_outlier

Run: python tools/add_anomaly_flags.py
"""
import json, statistics
from pathlib import Path
from collections import defaultdict

DATA  = Path(__file__).parent.parent / "assets" / "data" / "esg_quotient.json"

blob  = json.loads(DATA.read_text(encoding="utf-8"))
cos   = blob["companies"]

# ── per-dimension thresholds ──────────────────────────────────────────────────
# High = top ~15% of distribution  |  Medium = top 30-15%
# Derived empirically from actual score distributions (0-10 scale).
DIM_FLAGS = [
    ("ghg_intensity",    "ghg_anomaly",            "GHG Intensity Anomaly",      8.0, 6.5),
    ("water_intensity",  "water_anomaly",           "Water Intensity Anomaly",    8.0, 6.5),
    ("waste_intensity",  "waste_intensity_anomaly", "Waste Intensity Anomaly",    8.0, 6.5),
    ("compliance_risk",  "compliance_outlier",      "Compliance Gap Detected",    7.5, 6.0),
    ("epr_exposure",     "epr_gap",                 "EPR Compliance Gap",         7.5, 6.0),
]

# Sector-risk-outlier: high sector percentile AND high absolute score
SEC_HIGH_PCT  = 85   # sector_percentile >= this
SEC_MED_PCT   = 75
SEC_HIGH_SCORE = 6.5
SEC_MED_SCORE  = 5.5

total_flagged = 0

for c in cos:
    rb    = c.get("risk_breakdown") or {}
    flags = []

    # Dimension-level anomalies
    for dim_key, flag_type, label, hi_thresh, med_thresh in DIM_FLAGS:
        val = rb.get(dim_key)
        if val is None:
            continue
        if val >= hi_thresh:
            flags.append({"type": flag_type, "severity": "high",
                          "label": label,
                          "detail": f"{dim_key.replace('_',' ').title()} {val:.1f}/10 — high-risk outlier"})
        elif val >= med_thresh:
            flags.append({"type": flag_type, "severity": "medium",
                          "label": label,
                          "detail": f"{dim_key.replace('_',' ').title()} {val:.1f}/10 — elevated risk"})

    # Sector-risk outlier
    pct   = rb.get("sector_percentile")
    score = c.get("esg_risk_score") or 0
    if pct is not None:
        if pct >= SEC_HIGH_PCT and score >= SEC_HIGH_SCORE:
            flags.append({"type": "sector_risk_outlier", "severity": "high",
                          "label": "Sector Risk Outlier",
                          "detail": f"Sector percentile {pct} — worst {100-pct}% in sector"})
        elif pct >= SEC_MED_PCT and score >= SEC_MED_SCORE:
            flags.append({"type": "sector_risk_outlier", "severity": "medium",
                          "label": "Sector Risk Outlier",
                          "detail": f"Sector percentile {pct} — bottom quartile in sector"})

    # Dedupe: keep highest severity per type
    best = {}
    for f in flags:
        t = f["type"]
        if t not in best or (f["severity"] == "high" and best[t]["severity"] != "high"):
            best[t] = f
    c["anomaly_flags"] = list(best.values())
    if c["anomaly_flags"]:
        total_flagged += 1

DATA.write_text(json.dumps(blob, ensure_ascii=False, indent=None), encoding="utf-8")

total_flags = sum(len(c.get("anomaly_flags", [])) for c in cos)
print(f"Done. {total_flagged} companies flagged | {total_flags} total signals")
print("Breakdown:")
from collections import Counter
ctr = Counter(f["type"] for c in cos for f in c.get("anomaly_flags", []))
for k, v in ctr.most_common():
    print(f"  {k}: {v}")
