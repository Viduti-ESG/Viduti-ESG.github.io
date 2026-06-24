"""
Methodology v2 PROTOTYPE — non-destructive.
Re-scores all 1,227 companies from the local slim BRSR corpus and prints the
before/after distribution so we can see whether the fixes un-flatten the score.

It does NOT touch the DB, the API, or production. Output is console-only.

v2 changes tested here:
  1. DISCLOSURE-AWARE IMPUTATION: missing GHG/water/waste no longer default to a
     flat 5.0 (the main flattener). Two strategies are compared:
        - peer    : impute missing intensity with the sector median of DISCLOSED peers
        - penalty : impute missing *mandatory* GHG with a high-risk value (anti-greenwashing)
  2. DISCLOSURE CONFIDENCE (0-100): weighted % of the 7 components backed by real data.
  3. SECTOR-RELATIVE PERCENTILE + quintile tiers (the headline metric).
"""
import sys, json, statistics as st
from pathlib import Path
from collections import Counter, defaultdict

# Reuse the production profiler's exact helpers/weights
PROF_DIR = Path(r"c:/Viduti/my-website/cpcb_agent/esg_intelligence")
sys.path.insert(0, str(PROF_DIR))
import company_profiler as cp  # noqa: E402

SLIM = Path(r"c:/Viduti/brsr-generator/backend/data/companies_brsr_slim.json")
recs = json.loads(SLIM.read_text(encoding="utf-8"))
if isinstance(recs, dict):
    recs = recs.get("companies") or list(recs.values())[0]

GHG_MANDATORY_PENALTY = 7.5  # non-disclosure of a mandated metric = high risk


def disclosure_flags(c):
    """Return dict of which components were actually disclosed vs imputed/defaulted."""
    sec_c = c.get("section_c", {}); p6 = sec_c.get("p6_environment", {})
    p1 = sec_c.get("p1_ethics", {}); p3 = sec_c.get("p3_employees", {})
    p2 = sec_c.get("p2_products", {}); sec_b = c.get("section_b", {})
    f = cp._first
    return {
        "ghg_intensity":   bool(f(p6, "ScopeOneGHGEmissions") or f(p6, "ScopeTwoGHGEmissions")),
        "water_intensity": bool(f(p6, "TotalWaterWithdrawal", "TotalWaterConsumption")),
        "waste_intensity": bool(f(p6, "TotalWasteGenerated") or f(p6, "TotalHazardousWasteGenerated")),
        "epr_exposure":    bool(f(p2, "ExtendedProducerResponsibilityApplicability")),
        "compliance_risk": bool(f(p6, "NumberOfShowCauseOrLegalNoticesReceivedFromEnvironmentAuthorities")
                                or f(sec_c.get("p9_consumers", {}), "ConsumerComplaintsReceivedDuringTheYear")),
        "hr_risk":         bool(f(p3, "GrievanceRedressalMechanismInPlace")),
        "governance_risk": bool(f(p1, "DoesTheEntityHaveAnAntiCorruptionOrAntiBriberyPolicy")
                                or f(p1, "DoesTheEntityHaveProcessesInPlaceToAvoidOrManageConflictOfInterestsInvolvingMembersOfTheBoard")),
    }


# 1) Baseline + raw sub-scores + disclosure flags for every company
rows = []
for c in recs:
    prof = cp._score_company(c)
    rows.append({
        "name": prof["company_name"],
        "sector": prof["sector"] or "Unknown",
        "base": prof["esg_risk_score"],
        "sub": prof["risk_breakdown"],
        "disc": disclosure_flags(c),
    })

# 2) Sector medians of DISCLOSED intensity sub-scores (for peer imputation)
sector_disc = defaultdict(lambda: defaultdict(list))
global_disc = defaultdict(list)
for r in rows:
    for k in ("ghg_intensity", "water_intensity", "waste_intensity"):
        if r["disc"][k]:
            sector_disc[r["sector"]][k].append(r["sub"][k])
            global_disc[k].append(r["sub"][k])

def med(lst, fallback):
    return st.median(lst) if lst else fallback

def v2_composite(r, strategy):
    sub = dict(r["sub"]); disc = r["disc"]
    for k in ("ghg_intensity", "water_intensity", "waste_intensity"):
        if not disc[k]:
            if strategy == "penalty" and k == "ghg_intensity":
                sub[k] = GHG_MANDATORY_PENALTY
            else:  # peer-median imputation
                sub[k] = med(sector_disc[r["sector"]][k], med(global_disc[k], 5.0))
    return round(sum(sub[x] * cp.WEIGHTS[x] for x in cp.WEIGHTS), 2)

def confidence(r):
    return round(100 * sum(cp.WEIGHTS[k] for k, v in r["disc"].items() if v), 0)

for strat in ("peer", "penalty"):
    for r in rows:
        r[f"v2_{strat}"] = v2_composite(r, strat)
for r in rows:
    r["conf"] = confidence(r)

# 3) Sector-relative percentile + quintile tiers on the peer-imputed score
by_sector = defaultdict(list)
for r in rows:
    by_sector[r["sector"]].append(r)
for sec, group in by_sector.items():
    g = sorted(group, key=lambda r: r["v2_peer"])  # lower risk = better = lower percentile
    n = len(g)
    for i, r in enumerate(g):
        pct = 100 * i / max(n - 1, 1)
        r["sector_pct"] = round(pct, 0)
        r["sector_n"] = n

QUINTILE = [(20, "Leader"), (40, "Above Avg"), (60, "Average"), (80, "Below Avg"), (101, "Laggard")]
def tier_from_pct(p):
    for thr, name in QUINTILE:
        if p < thr:
            return name
    return "Laggard"

# ---- REPORT ----
def stats(key):
    v = sorted(r[key] for r in rows)
    n = len(v)
    q = lambda p: v[int(p * (n - 1))]
    return f"min {v[0]:.2f}  p25 {q(.25):.2f}  median {q(.5):.2f}  p75 {q(.75):.2f}  max {v[-1]:.2f}  | mean {st.mean(v):.2f}  STDEV {st.pstdev(v):.2f}"

def hist(key, step=0.5):
    h = Counter(round(r[key] / step) * step for r in rows)
    return "  ".join(f"{k:.1f}:{c}" for k, c in sorted(h.items()))

print("=" * 78)
print(f"UNIVERSE: {len(rows)} companies")
print("=" * 78)
print("\n--- ESG RISK SCORE: spread comparison ---")
print(f"BASELINE (current) : {stats('base')}")
print(f"V2 peer-imputed    : {stats('v2_peer')}")
print(f"V2 ghg-penalty     : {stats('v2_penalty')}")
print("\nBaseline histogram :", hist("base"))
print("V2 peer histogram  :", hist("v2_peer"))

print("\n--- DISCLOSURE CONFIDENCE (new metric) ---")
cv = sorted(r["conf"] for r in rows)
print(f"confidence: min {cv[0]:.0f}  median {cv[len(cv)//2]:.0f}  max {cv[-1]:.0f}  | mean {st.mean(cv):.0f}")
cb = Counter((int(r['conf']) // 20) * 20 for r in rows)
print("conf bands :", "  ".join(f"{k}-{k+19}%:{cb[k]}" for k in sorted(cb)))

print("\n--- TIERS ---")
old_t = Counter(("High" if r["base"] >= 6.5 else "Medium" if r["base"] >= 4.0 else "Low") for r in rows)
new_t = Counter(tier_from_pct(r["sector_pct"]) for r in rows)
print("OLD absolute tiers :", dict(old_t))
print("NEW sector quintile:", dict(new_t))

print("\n--- TIE PROBLEM (how many companies share the single most common score) ---")
print(f"baseline most common score holds {max(Counter(r['base'] for r in rows).values())} companies")
print(f"v2 peer  most common score holds {max(Counter(r['v2_peer'] for r in rows).values())} companies")

print("\n--- SAMPLE: new 'Top ESG Performers' headline (lowest sector percentile, decent confidence) ---")
elig = [r for r in rows if r["sector_n"] >= 5]
for r in sorted(elig, key=lambda r: (r["sector_pct"], -r["conf"]))[:8]:
    print(f"  {r['name'][:42]:42} | {r['sector'][:26]:26} | risk {r['v2_peer']:.1f} | sector top {r['sector_pct']:.0f}% | conf {r['conf']:.0f}%")
