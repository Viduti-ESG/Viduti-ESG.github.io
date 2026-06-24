"""
Methodology v2 — FULL re-score on real data. Non-destructive (console + side file).

Fixes the field-mapping bug and rebuilds the score on signal that actually exists:
  - Carbon       : real Scope 1+2 intensity (re-extracted from XBRL) -> sector percentile rank
  - Transition   : % non-renewable energy mix
  - Water        : water intensity -> percentile rank
  - Waste        : waste / revenue -> percentile rank
  - EPR/Compliance/HR/Governance : reuse current qualitative sub-scores (audit pending)

Each dimension is 0-100 (higher = more risk). Heavy-tailed intensities are normalized by
PERCENTILE RANK (robust to the millions-x spread). Composite is a weighted average over
DISCLOSED dimensions only (missing data lowers Confidence instead of imputing a fake mid).

Outputs: before/after spread, tier distribution, confidence distribution, sample leaders.
"""
import sys, re, json, statistics as st
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, r"c:/Viduti/my-website/cpcb_agent/esg_intelligence")
import company_profiler as cp  # noqa

norm = lambda s: re.sub(r'[^a-z0-9]', '', s.lower())
slim = json.loads(Path(r"c:/Viduti/brsr-generator/backend/data/companies_brsr_slim.json").read_text(encoding="utf-8"))["companies"]
emis = json.loads(Path(r"c:/Viduti/esg-site/tools/emissions_extracted.json").read_text(encoding="utf-8"))

WEIGHTS = {  # revised — carbon now real
    "carbon": 0.25, "transition": 0.10, "water": 0.10, "waste": 0.10,
    "epr": 0.15, "compliance": 0.15, "hr": 0.05, "governance": 0.10,
}

def g(c, *p):
    cur = c
    for k in p:
        if not isinstance(cur, dict): return None
        cur = cur.get(k)
    return cur

def fval(d, *ks):
    if not isinstance(d, dict): return None
    for k in ks:
        v = d.get(k)
        if v is None: continue
        if isinstance(v, list): v = v[0] if v else None
        try: return float(str(v).replace(",", "").strip())
        except: pass
    return None

# ---- gather raw metrics + reuse qualitative sub-scores from the production profiler ----
rows = []
for c in slim:
    prof = cp._score_company(c)
    rev = prof["revenue_crore"]
    p6 = g(c, "section_c", "p6_environment")
    em = emis.get(norm(c["company_name"]), {})
    s1, s2 = em.get("scope1"), em.get("scope2")
    ren = fval(p6, "TotalEnergyConsumedFromRenewableSources")
    nonren = fval(p6, "TotalEnergyConsumedFromNonRenewableSources")
    waste = fval(p6, "TotalWasteGenerated")
    rows.append({
        "name": c["company_name"], "sector": prof["sector"] or "Unknown",
        "base": prof["esg_risk_score"],
        "raw": {
            "carbon": ((s1 or 0) + (s2 or 0)) / rev if (s1 is not None and s2 is not None and rev) else None,
            "transition": (100 * nonren / (ren + nonren)) if (ren is not None and nonren is not None and (ren + nonren) > 0) else None,
            "water": fval(p6, "WaterIntensityPerRupeeOfTurnover"),
            "waste": (waste / rev) if (waste is not None and rev) else None,
        },
        "qual": {  # already 0-10 from profiler, higher = worse
            "epr": prof["risk_breakdown"]["epr_exposure"],
            "compliance": prof["risk_breakdown"]["compliance_risk"],
            "hr": prof["risk_breakdown"]["hr_risk"],
            "governance": prof["risk_breakdown"]["governance_risk"],
        },
    })

# ---- percentile-rank the heavy-tailed intensity dimensions (within universe) ----
def pct_rank_map(key):
    vals = sorted(r["raw"][key] for r in rows if r["raw"][key] is not None)
    n = len(vals)
    def rank(v):
        if v is None: return None
        import bisect
        return 100 * bisect.bisect_left(vals, v) / max(n - 1, 1)
    return rank

rankers = {k: pct_rank_map(k) for k in ("carbon", "water", "waste")}

for r in rows:
    dim = {}
    dim["carbon"] = rankers["carbon"](r["raw"]["carbon"])
    dim["water"] = rankers["water"](r["raw"]["water"])
    dim["waste"] = rankers["waste"](r["raw"]["waste"])
    dim["transition"] = r["raw"]["transition"]  # already 0-100 (% non-renewable)
    for k in ("epr", "compliance", "hr", "governance"):
        dim[k] = r["qual"][k] * 10  # 0-10 -> 0-100
    r["dim"] = dim
    # composite over DISCLOSED dims, renormalized weights
    present = {k: v for k, v in dim.items() if v is not None}
    wsum = sum(WEIGHTS[k] for k in present)
    r["v2"] = round(sum(present[k] * WEIGHTS[k] for k in present) / wsum, 1) if wsum else None
    r["conf"] = round(100 * wsum, 0)  # weighted fraction of dims with real data

scored = [r for r in rows if r["v2"] is not None]

# ---- sector-relative percentile + tiers (headline) ----
by_sec = defaultdict(list)
for r in scored: by_sec[r["sector"]].append(r)
for sec, grp in by_sec.items():
    gs = sorted(grp, key=lambda r: r["v2"]); n = len(gs)
    for i, r in enumerate(gs):
        r["sector_pct"] = round(100 * i / max(n - 1, 1), 0); r["sector_n"] = n

def tier(p):
    return "Leader" if p < 20 else "Above Avg" if p < 40 else "Average" if p < 60 else "Below Avg" if p < 80 else "Laggard"

# ---- REPORT ----
def stats(key, src=rows):
    v = sorted(r[key] for r in src if r.get(key) is not None); n = len(v); q = lambda p: v[int(p*(n-1))]
    return f"min {v[0]:.1f}  p25 {q(.25):.1f}  median {q(.5):.1f}  p75 {q(.75):.1f}  max {v[-1]:.1f}  | STDEV {st.pstdev(v):.2f}"

print("=" * 80)
print(f"UNIVERSE {len(rows)} | scored {len(scored)} | (un-scorable = no disclosed dims)")
print("=" * 80)
print("\n--- SPREAD: the whole point ---")
print(f"BASELINE (0-10 scale) : {stats('base')}")
print(f"V2       (0-100 scale): {stats('v2', scored)}")
print("  ^ compare STDEV relative to scale: baseline 0.38/10 = 3.8% of range; V2 below should be far wider")

import bisect
hb = Counter(min(int(r['v2'] // 10) * 10, 90) for r in scored)
print("\nV2 histogram (10-pt bins):", "  ".join(f"{k}-{k+9}:{hb[k]}" for k in sorted(hb)))

print("\n--- DISCLOSURE CONFIDENCE (now varies!) ---")
cb = Counter(int(r['conf'] // 20) * 20 for r in scored)
print("conf bands:", "  ".join(f"{k}-{k+19}%:{cb[k]}" for k in sorted(cb)))

print("\n--- TIERS ---")
print("OLD absolute:", dict(Counter(("High" if r["base"]>=6.5 else "Medium" if r["base"]>=4.0 else "Low") for r in rows)))
print("V2 sector quintile:", dict(Counter(tier(r["sector_pct"]) for r in scored)))

print("\n--- SAMPLE: real Top ESG Performers (lowest sector %, confidence >=60%) ---")
elig = [r for r in scored if r["sector_n"] >= 5 and r["conf"] >= 60]
for r in sorted(elig, key=lambda r: (r["sector_pct"], -r["conf"]))[:10]:
    print(f"  {r['name'][:38]:38} | {r['sector'][:22]:22} | risk {r['v2']:5.1f} | top {r['sector_pct']:.0f}% in sector | conf {r['conf']:.0f}%")
