"""
ESG Quotient v2 — 3-pillar scoring engine on verified BRSR data.
Produces rescored.json mapping company_name -> {sector, esg_risk_score, risk_tier, risk_breakdown}
ready to UPDATE the production DB (keeps existing risk_breakdown keys, adds pillars + new fields).
All sub-scores 0-10, higher = more risk. Heavy-tailed metrics -> percentile rank.
"""
import sys, re, json, bisect, statistics as st
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, r"c:/Viduti/my-website/cpcb_agent/esg_intelligence")
sys.path.insert(0, str(Path(__file__).parent))
import company_profiler as cp  # noqa
import data_clean as dc  # noqa — centralised data-quality guards
norm = dc.norm
load = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))

slim = load(r"c:/Viduti/brsr-generator/backend/data/companies_brsr_slim.json")["companies"]
feat = load(r"c:/Viduti/esg-site/tools/raw_features.json")
emis = load(r"c:/Viduti/esg-site/tools/emissions_extracted.json")
secs = load(r"c:/Viduti/esg-site/tools/sectors_extracted.json")

# company_profiler still carries the old revenue unit bug (e.g. SAIL 98.6 vs the
# XBRL-correct 102,097 cr). Intensities divide by revenue, so we override the
# profiler's revenue with the corrected values already in production esg_quotient.json
# (keyed by CIN, then normalised name). Without this the rescore would re-introduce
# the very revenue error the XBRL fix removed.
_eq = load(r"c:/Viduti/esg-site/assets/data/esg_quotient.json")["companies"]
CORR_REV_BY_CIN  = {(_c.get("cin") or "").upper(): _c.get("revenue_crore")
                    for _c in _eq if _c.get("cin")}
CORR_REV_BY_NAME = {norm(_c["company_name"]): _c.get("revenue_crore") for _c in _eq}
def corrected_rev(prof, name):
    r = CORR_REV_BY_CIN.get((prof.get("cin") or "").upper())
    if r is None:
        r = CORR_REV_BY_NAME.get(norm(name))
    return r if r is not None else prof.get("revenue_crore")

def clamp(x, lo=0.0, hi=10.0): return max(lo, min(hi, x))

# ── pass 1: raw dimension values per company ──────────────────────────────────
# Data-quality guards (dedupe, emission magnitude/zero/unit-divergence/suspect-rev,
# pay-ratio, female-board parse bug) are centralised in tools/data_clean.py so they
# stay identical between the scores here and the displayed emissions in fe_backfill.
rows = []
seen = set()
for c in slim:
    k = norm(c["company_name"])
    if k in seen:               # belt-and-suspenders: slim is deduped at source too
        continue
    seen.add(k)
    prof = cp._score_company(c); rev = corrected_rev(prof, c["company_name"])
    f = feat.get(k, {}); sec = secs.get(k, {}); sector = sec.get("sector", "Unclassified")
    em = emis.get(k, {})
    ren, nonren = f.get("energy_renew"), f.get("energy_nonrenew")
    waste, disp, rec = f.get("waste_total"), f.get("waste_disposed"), f.get("waste_recovered")

    rev_suspect = dc.revenue_suspect(rev, sector)
    ghg = dc.clean_emissions(f.get("scope1"), f.get("scope2"), em.get("scope3"),
                             rev, sector)["ghg_intensity"]
    cleaned_feat = dc.clean_features(f)
    pay_ratio = cleaned_feat["pay_ratio"]
    female_board = cleaned_feat["female_board"]

    rows.append({
        "name": c["company_name"], "cin": prof["cin"], "nse_symbol": prof["nse_symbol"],
        "products": prof["products"], "revenue_crore": rev, "financial_year": prof["financial_year"],
        "sector": sector,
        "v": {
            "ghg":   ghg,
            "water": f.get("water_intensity"),
            "waste": (waste/rev) if (waste is not None and rev and not rev_suspect) else None,
            "transition": (nonren/(ren+nonren)) if (ren is not None and nonren is not None and (ren+nonren) > 0) else None,
            "recovery": (rec/(rec+disp)) if (rec and disp and (rec+disp) > 0) else None,
            "ltifr": f.get("ltifr"),
            "fatalities": f.get("fatalities"),
            "female_board": female_board,
            "female_kmp": f.get("pct_female_kmp"),
            "pay_ratio": pay_ratio,
            "fines": (f.get("fines_amount")/rev) if (f.get("fines_amount") and rev) else (0.0 if rev else None),
            "assured": f.get("brsr_assured"), "anti_corrupt": f.get("anti_corruption"),
            "ohs": f.get("ohs_system"), "zld": f.get("zld"),
        },
    })

# ── sector-peer carbon outlier removal (robust replacement for self-reference) ─
_carbon_out = dc.sector_intensity_outliers([(i, r["sector"], r["v"]["ghg"]) for i, r in enumerate(rows)])
for i, r in enumerate(rows):
    if i in _carbon_out:
        r["v"]["ghg"] = None

# ── percentile-rank helpers (0-10) ────────────────────────────────────────────
def make_rank(key, invert=False):
    vals = sorted(r["v"][key] for r in rows if r["v"][key] is not None)
    n = len(vals)
    def rank(v):
        if v is None: return None
        p = bisect.bisect_left(vals, v) / max(n-1, 1)
        return round(10*(1-p) if invert else 10*p, 1)
    return rank
R = {k: make_rank(k) for k in ("ghg","water","waste","pay_ratio","fines")}
R["female_board"] = make_rank("female_board", invert=True)   # more women -> less risk
R["female_kmp"]   = make_rank("female_kmp", invert=True)
R["ltifr"]        = make_rank("ltifr")

def wavg(pairs):  # pairs of (score, weight), skip None
    ps = [(s, w) for s, w in pairs if s is not None]
    if not ps: return None
    return round(sum(s*w for s, w in ps)/sum(w for _, w in ps), 1)

# ── pass 2: sub-scores, pillars, composite ────────────────────────────────────
DIMS_FOR_CONF = ["ghg","water","waste","transition","safety","diversity","governance"]
for r in rows:
    v = r["v"]
    ghg, water = R["ghg"](v["ghg"]), R["water"](v["water"])
    waste = R["waste"](v["waste"])
    if waste is not None and v["recovery"] is not None:
        waste = clamp(waste - 3*v["recovery"])          # credit circular waste handling
    transition = round(v["transition"]*10, 1) if v["transition"] is not None else None
    if transition is not None and v["zld"]:
        transition = clamp(transition - 0.5)

    # SOCIAL: safety + diversity
    safety = None
    if v["ltifr"] is not None or v["fatalities"] is not None:
        base = R["ltifr"](v["ltifr"]) if v["ltifr"] is not None else 3.0
        if v["fatalities"]: base = clamp(base + min(3*v["fatalities"], 5))
        if v["ohs"]: base = clamp(base - 0.5)
        safety = round(base, 1)
    diversity = wavg([(R["female_board"](v["female_board"]), 0.65), (R["female_kmp"](v["female_kmp"]), 0.35)])
    hr_risk = wavg([(safety, 0.6), (diversity, 0.4)])

    # GOVERNANCE: pay equity + assurance + anti-corruption + fines
    pay = R["pay_ratio"](v["pay_ratio"])
    assurance_risk = (3.0 if v["assured"] else 6.5) if v["assured"] is not None else None
    ethics_risk = 2.0 if v["anti_corrupt"] else 7.0
    governance_risk = wavg([(pay, 0.40), (assurance_risk, 0.30), (ethics_risk, 0.30)])
    compliance_risk = R["fines"](v["fines"]) if v["fines"] is not None else None
    if compliance_risk is None: compliance_risk = 2.0

    # EPR / circularity (keep legacy key, now real: poor recovery + non-renewable)
    epr_exposure = wavg([(transition, 0.5), (R["waste"](v["waste"]), 0.5)]) or 5.0

    # pillars
    environmental = wavg([(ghg, 0.40), (water, 0.25), (waste, 0.20), (transition, 0.15)])
    social = hr_risk
    governance = wavg([(governance_risk, 0.6), (compliance_risk, 0.4)])
    esg = wavg([(environmental, 0.45), (social, 0.30), (governance, 0.25)])

    present = sum(1 for d, val in [("ghg",ghg),("water",water),("waste",waste),("transition",transition),
                                   ("safety",safety),("diversity",diversity),("governance",governance_risk)] if val is not None)
    conf = round(100*present/len(DIMS_FOR_CONF))

    r["score"] = esg if esg is not None else 5.0
    # real disclosed display metrics (only keep present ones)
    metrics_all = {
        "renewable_pct":      round((1 - v["transition"]) * 100, 1) if v["transition"] is not None else None,
        "waste_recovery_pct": round(v["recovery"] * 100, 1) if v["recovery"] is not None else None,
        "zld":                True if v["zld"] else None,
        "ltifr":              v["ltifr"],
        "fatalities":         int(v["fatalities"]) if v["fatalities"] is not None else None,
        "female_board_pct":   round(v["female_board"] * 100, 1) if v["female_board"] is not None else None,
        "female_kmp_pct":     round(v["female_kmp"] * 100, 1) if v["female_kmp"] is not None else None,
        "pay_ratio":          round(v["pay_ratio"], 1) if v["pay_ratio"] is not None else None,
        "assured":            True if v["assured"] else None,
        "ohs_system":         True if v["ohs"] else None,
    }
    metrics = {k: val for k, val in metrics_all.items() if val is not None}
    r["impact"] = wavg([(environmental, 0.65), (social, 0.35)]) or r["score"]
    r["rb"] = {
        "ghg_intensity": ghg, "water_intensity": water, "waste_intensity": waste,
        "epr_exposure": round(epr_exposure,1), "energy_transition": transition,
        "compliance_risk": round(compliance_risk,1), "hr_risk": hr_risk, "governance_risk": governance_risk,
        "environmental": environmental, "social": social, "governance": governance,
        "disclosure_confidence": conf, "metrics": metrics,
    }
    r["top"] = [lbl for lbl,sv in sorted(
        [("GHG Intensity",ghg),("Water Intensity",water),("Waste",waste),("Energy Transition",transition),
         ("Workforce Safety",safety),("Board Diversity",diversity),("Pay Equity",pay),("Compliance",compliance_risk)],
        key=lambda x:(x[1] is None, -(x[1] or 0)))[:3] if sv is not None and sv >= 5.5]

# ── sector-relative percentile + absolute tier ────────────────────────────────
by_sec = defaultdict(list)
for r in rows: by_sec[r["sector"]].append(r)
overall = sorted(r["score"] for r in rows); N = len(overall)
for sec, grp in by_sec.items():
    if len(grp) >= 8:
        gs = sorted(grp, key=lambda r: r["score"]); n = len(gs)
        for i, r in enumerate(gs): r["rb"]["sector_percentile"] = round(100*i/max(n-1,1))
    else:
        for r in grp: r["rb"]["sector_percentile"] = round(100*bisect.bisect_left(overall, r["score"])/max(N-1,1))

# absolute tier bands calibrated to distribution terciles
cut1, cut2 = overall[N//3], overall[2*N//3]
def tier(s): return "Low" if s < cut1 else "High" if s >= cut2 else "Medium"
for r in rows: r["tier"] = tier(r["score"])

# ── write output ──────────────────────────────────────────────────────────────
out = {r["name"]: {"sector": r["sector"], "esg_risk_score": r["score"], "risk_tier": r["tier"],
                   "risk_breakdown": r["rb"], "top_risk_factors": r["top"] or ["Data insufficient"],
                   "impact_materiality": r["impact"]}
       for r in rows}
Path(r"c:/Viduti/esg-site/tools/rescored.json").write_text(json.dumps(out), encoding="utf-8")

# ── validation report ─────────────────────────────────────────────────────────
sc = [r["score"] for r in rows]
print(f"scored {len(rows)} | tier cuts: Low<{cut1} / High>={cut2}")
print(f"score: min {min(sc)} median {st.median(sc)} max {max(sc)} STDEV {st.pstdev(sc):.2f}")
print("tiers:", dict(Counter(r["tier"] for r in rows)))
print("pillar coverage: E", sum(1 for r in rows if r['rb']['environmental'] is not None),
      "S", sum(1 for r in rows if r['rb']['social'] is not None),
      "G", sum(1 for r in rows if r['rb']['governance'] is not None))
cf = [r['rb']['disclosure_confidence'] for r in rows]
print("confidence: median", st.median(cf), "min", min(cf), "max", max(cf))
print("\nface-validity — leaders (lowest sector %) in 3 sectors:")
for tgt in ("Power & Utilities","Banking & Finance","Pharmaceuticals"):
    g = sorted([r for r in rows if r["sector"]==tgt], key=lambda r:r["rb"]["sector_percentile"])[:3]
    print(f"  [{tgt}]:", ", ".join(f"{r['name'][:24]}({r['score']})" for r in g))
