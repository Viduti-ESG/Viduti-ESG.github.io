"""
Merge XBRL-extracted bottlenecks + S/E hard metrics into esg_quotient.json.

Joins by CIN (name-normalised fallback). Idempotent and re-runnable: rewrites the
enrichment keys each time. For each company it attaches:

  bottleneck_solutions : de-duplicated list (Risks first) of disclosed material
                         issues, each paired with the curated global best-fit
                         solution + the company's own mitigation text.
  safety_metrics       : fatalities / recordable injuries / worst LTIFR (current yr)
  energy_mix           : renewable vs non-renewable + renewable share %
  waste_profile        : plastic / e-waste / battery / bio-medical / total / recycled

Non-destructive to existing keys. Writes back to assets/data/esg_quotient.json and
keeps a .bak of the pre-merge file.
"""
import json, re, shutil
from pathlib import Path
from collections import OrderedDict

import bottleneck_solutions as BS   # same tools/ dir

SITE = Path(r"c:/Viduti/esg-site")
QFILE = SITE / "assets/data/esg_quotient.json"
EXTRACT = SITE / "tools/bottlenecks_extracted.json"

def norm(name):
    return re.sub(r'[^a-z0-9]', '', (name or "").lower())

extract = json.loads(EXTRACT.read_text(encoding="utf-8"))
by_cin = {k.upper(): v for k, v in extract.items()}
by_name = {norm(v["company_name"]): v for v in extract.values()}

doc = json.loads(QFILE.read_text(encoding="utf-8"))
companies = doc["companies"]

MAX_CARDS = 6

def build_solutions(rec):
    """Collapse disclosed issues -> distinct solution cards, Risks first."""
    rows = rec.get("bottlenecks", [])
    # rank: Risk (incl Risk & Opportunity) before pure Opportunity, keep filing order within
    def risk_rank(b):
        t = (b.get("type") or "").lower()
        return 0 if "risk" in t else 1
    rows = sorted(rows, key=risk_rank)
    seen = OrderedDict()
    for b in rows:
        cat = BS.classify(b["issue"])
        if not cat or cat in seen:
            continue
        sol = BS.SOLUTIONS[cat]
        seen[cat] = {
            "issue": b["issue"],
            "category": cat,
            "type": b.get("type") or "Risk",
            "financial_implication": b.get("financial_implication") or "",
            "company_mitigation": b.get("company_mitigation") or "",
            "solution": sol["solution"],
            "standards": sol["standards"],
            "sources": sol["sources"],
        }
        if len(seen) >= MAX_CARDS:
            break
    return list(seen.values())

matched = 0
stats = {"solutions": 0, "safety": 0, "energy": 0, "waste": 0}
for c in companies:
    cin = (c.get("cin") or "").upper()
    rec = by_cin.get(cin) or by_name.get(norm(c.get("company_name")))
    if not rec:
        # clear stale enrichment if unmatched
        for k in ("bottleneck_solutions", "safety_metrics", "energy_mix",
                  "waste_profile", "governance_signals", "ghg_intensity_tco2e_per_cr"):
            c.pop(k, None)
        continue
    matched += 1
    sols = build_solutions(rec)
    c["bottleneck_solutions"] = sols
    c["safety_metrics"] = rec.get("safety_metrics")
    c["energy_mix"] = rec.get("energy_mix")
    c["waste_profile"] = rec.get("waste_profile")
    c["governance_signals"] = rec.get("governance_signals")

    # Emissions intensity — computed from the site's already-cleaned ABSOLUTE
    # Scope 1+2 and revenue, NOT the disclosed per-rupee field (which is badly
    # unit-divergent). Internally consistent + comparable across companies.
    fe = c.get("financial_exposure", {}) or {}
    s1 = fe.get("scope1_emissions_tco2e"); s2 = fe.get("scope2_emissions_tco2e")
    rev = c.get("revenue_crore")
    if s1 and s2 and rev and rev > 0:
        c["ghg_intensity_tco2e_per_cr"] = round((s1 + s2) / rev, 2)
    else:
        c.pop("ghg_intensity_tco2e_per_cr", None)
    if sols: stats["solutions"] += 1
    if rec.get("safety_metrics") and any(v is not None for v in rec["safety_metrics"].values()): stats["safety"] += 1
    if rec.get("energy_mix", {}).get("renewable_share_pct") is not None: stats["energy"] += 1
    if rec.get("waste_profile") and any(v is not None for v in rec["waste_profile"].values()): stats["waste"] += 1

shutil.copy2(QFILE, QFILE.with_suffix(".json.bak"))
QFILE.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

N = len(companies)
print(f"companies: {N} | CIN/name-matched to XBRL: {matched}")
print(f"  with bottleneck solutions : {stats['solutions']} ({100*stats['solutions']//N}%)")
print(f"  with safety metrics       : {stats['safety']} ({100*stats['safety']//N}%)")
print(f"  with energy mix           : {stats['energy']} ({100*stats['energy']//N}%)")
print(f"  with waste profile        : {stats['waste']} ({100*stats['waste']//N}%)")
# sample
ex = next(c for c in companies if c.get("bottleneck_solutions"))
print(f"\nsample: {ex['company_name']} -> {len(ex['bottleneck_solutions'])} solution cards")
for s in ex["bottleneck_solutions"][:3]:
    print(f"  [{s['type']}] {s['issue']}  =>  {', '.join(s['standards'][:2])}")
