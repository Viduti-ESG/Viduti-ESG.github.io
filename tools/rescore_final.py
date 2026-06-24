"""
Methodology v2 — FINAL local build. Non-destructive.
Scores on VERIFIED-signal dimensions only; NIC sector-relative percentile tiers.

Dimensions (0-100, higher = more risk):
  carbon     - real Scope1+2 intensity (XBRL)         -> percentile rank
  transition - % non-renewable energy mix
  water      - water intensity                          -> percentile rank
  waste      - waste / revenue                          -> percentile rank
  governance - anti-corruption/conflict (coarse, real)
  hr         - grievance/union (coarse, real)
DEFERRED to Phase 1b XBRL re-extraction: EPR applicability, fines/penalties (json-blind).

Headline = NIC sector-relative percentile (fallback to overall if sector n<8).
Plus: Disclosure Confidence + absolute band.
"""
import sys, re, json, bisect, statistics as st
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, r"c:/Viduti/my-website/cpcb_agent/esg_intelligence")
import company_profiler as cp  # noqa
norm = lambda s: re.sub(r'[^a-z0-9]', '', s.lower())
load = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))

slim = load(r"c:/Viduti/brsr-generator/backend/data/companies_brsr_slim.json")["companies"]
emis = load(r"c:/Viduti/esg-site/tools/emissions_extracted.json")
secs = load(r"c:/Viduti/esg-site/tools/sectors_extracted.json")

WEIGHTS = {"carbon":0.35,"transition":0.12,"water":0.12,"waste":0.12,"governance":0.18,"hr":0.11}
MIN_SECTOR_N = 8

def g(c,*p):
    cur=c
    for k in p:
        if not isinstance(cur,dict): return None
        cur=cur.get(k)
    return cur
def fval(d,*ks):
    if not isinstance(d,dict): return None
    for k in ks:
        v=d.get(k)
        if v is None: continue
        if isinstance(v,list): v=v[0] if v else None
        try: return float(str(v).replace(",","").strip())
        except: pass
    return None

rows=[]
for c in slim:
    prof=cp._score_company(c); rev=prof["revenue_crore"]; p6=g(c,"section_c","p6_environment")
    em=emis.get(norm(c["company_name"]),{}); s1,s2=em.get("scope1"),em.get("scope2")
    ren=fval(p6,"TotalEnergyConsumedFromRenewableSources"); nonren=fval(p6,"TotalEnergyConsumedFromNonRenewableSources")
    waste=fval(p6,"TotalWasteGenerated"); sec=secs.get(norm(c["company_name"]),{})
    rows.append({
        "name":c["company_name"], "sector":sec.get("sector","Unclassified"), "base":prof["esg_risk_score"],
        "raw":{"carbon":((s1 or 0)+(s2 or 0))/rev if (s1 is not None and s2 is not None and rev) else None,
               "water":fval(p6,"WaterIntensityPerRupeeOfTurnover"),
               "waste":(waste/rev) if (waste is not None and rev) else None},
        "transition":(100*nonren/(ren+nonren)) if (ren is not None and nonren is not None and (ren+nonren)>0) else None,
        "governance":prof["risk_breakdown"]["governance_risk"]*10,
        "hr":prof["risk_breakdown"]["hr_risk"]*10,
    })

def ranker(key):
    vals=sorted(r["raw"][key] for r in rows if r["raw"][key] is not None); n=len(vals)
    return lambda v: None if v is None else 100*bisect.bisect_left(vals,v)/max(n-1,1)
R={k:ranker(k) for k in ("carbon","water","waste")}

for r in rows:
    dim={"carbon":R["carbon"](r["raw"]["carbon"]),"water":R["water"](r["raw"]["water"]),
         "waste":R["waste"](r["raw"]["waste"]),"transition":r["transition"],
         "governance":r["governance"],"hr":r["hr"]}
    present={k:v for k,v in dim.items() if v is not None}
    wsum=sum(WEIGHTS[k] for k in present)
    r["v2"]=round(sum(present[k]*WEIGHTS[k] for k in present)/wsum,1) if wsum else None
    r["conf"]=round(100*wsum,0)
scored=[r for r in rows if r["v2"] is not None]

# sector-relative percentile (fallback to overall if sector too small)
by_sec=defaultdict(list)
for r in scored: by_sec[r["sector"]].append(r)
overall=sorted(r["v2"] for r in scored); N=len(overall)
for sec,grp in by_sec.items():
    if len(grp)>=MIN_SECTOR_N:
        gs=sorted(grp,key=lambda r:r["v2"]); n=len(gs)
        for i,r in enumerate(gs): r["pct"]=round(100*i/max(n-1,1),0); r["basis"]="sector"; r["peer_n"]=n
    else:
        for r in grp: r["pct"]=round(100*bisect.bisect_left(overall,r["v2"])/max(N-1,1),0); r["basis"]="overall"; r["peer_n"]=N
def tier(p): return "Leader" if p<20 else "Above Avg" if p<40 else "Average" if p<60 else "Below Avg" if p<80 else "Laggard"

def stats(key,src):
    v=sorted(r[key] for r in src if r.get(key) is not None); n=len(v); q=lambda p:v[int(p*(n-1))]
    return f"min {v[0]:.1f}  p25 {q(.25):.1f}  median {q(.5):.1f}  p75 {q(.75):.1f}  max {v[-1]:.1f}  STDEV {st.pstdev(v):.2f}"

print("="*82)
print(f"FINAL v2 | universe {len(rows)} | scored {len(scored)} | sectors used for ranking: {sum(1 for g_ in by_sec.values() if len(g_)>=MIN_SECTOR_N)}")
print("="*82)
print(f"\nBASELINE 0-10 : {stats('base',rows)}")
print(f"V2 0-100      : {stats('v2',scored)}")
hb=Counter(min(int(r['v2']//10)*10,90) for r in scored)
print("V2 histogram  :", "  ".join(f"{k}-{k+9}:{hb[k]}" for k in sorted(hb)))
print("\n--- TIERS (now correctly ~20% each = working sector percentiles) ---")
print("V2 quintile:", dict(Counter(tier(r["pct"]) for r in scored)))
print("ranking basis:", dict(Counter(r["basis"] for r in scored)))
ab=Counter(("Low" if r["v2"]<40 else "High" if r["v2"]>65 else "Medium") for r in scored)
print("V2 absolute band (Low<40 / Med / High>65):", dict(ab))
print("\n--- DISCLOSURE CONFIDENCE ---")
print("bands:", dict(sorted(Counter(int(r['conf']//20)*20 for r in scored).items())))
print("\n--- SAMPLE: Leaders in 4 major sectors (lowest sector %, conf>=70) ---")
for target in ("Chemicals","Banking & Finance","Basic Metals","Power & Utilities"):
    grp=sorted([r for r in scored if r["sector"]==target and r["conf"]>=70], key=lambda r:r["pct"])[:3]
    print(f"  [{target}]")
    for r in grp:
        print(f"     {r['name'][:34]:34} risk {r['v2']:5.1f} | top {r['pct']:.0f}% of {r['peer_n']} peers | conf {r['conf']:.0f}%")
