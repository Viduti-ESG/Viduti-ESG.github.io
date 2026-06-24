"""
Build financial_exposure backfill: real Scope 1/2/3 + water withdrawal per company,
keyed by DB company_name. Non-destructive -> fe_backfill.json
"""
import re, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, r"c:/Viduti/my-website/cpcb_agent/esg_intelligence")
import data_clean as dc          # noqa — centralised data-quality guards
import company_profiler as cp    # noqa — for revenue (needed by suspect-rev / divergence guards)

norm = dc.norm
XBRL_DIR = Path(r"c:/Viduti/BRSR XBRL PDF/downloads/xbrl")
emis = json.loads(Path(r"c:/Viduti/esg-site/tools/emissions_extracted.json").read_text(encoding="utf-8"))
secs = json.loads(Path(r"c:/Viduti/esg-site/tools/sectors_extracted.json").read_text(encoding="utf-8"))
slim = json.loads(Path(r"c:/Viduti/brsr-generator/backend/data/companies_brsr_slim.json").read_text(encoding="utf-8"))["companies"]

def water_withdrawal(text):
    for local in ("TotalVolumeOfWaterWithdrawal", "TotalWaterWithdrawal"):
        for m in re.finditer(r'<in-capmkt:' + local + r'\b[^>]*contextRef="([^"]+)"[^>]*>([^<]+)<', text):
            if m.group(1) == "DCYMain" or m.group(1).startswith("DCY"):
                try: return float(m.group(2).replace(",", "").strip())
                except: pass
    return None

# water withdrawal per normalized company
water = {}
for fp in XBRL_DIR.glob("*.xml"):
    k = norm(re.sub(r'_FY\d{2}-\d{2}$', '', fp.stem))
    water[k] = water_withdrawal(fp.read_text(encoding="utf-8", errors="ignore"))

# pass 1: per-company cleaning (same guards as scoring)
recs = []
seen = set()
for c in slim:
    name = c["company_name"]; k = norm(name)
    if k in seen:                       # skip case-variant duplicates (also deduped at source)
        continue
    seen.add(k)
    e = emis.get(k, {})
    rev = cp._score_company(c)["revenue_crore"]
    sector = secs.get(k, {}).get("sector", "Unclassified")
    ce = dc.clean_emissions(e.get("scope1"), e.get("scope2"), e.get("scope3"), rev, sector)
    recs.append({"name": name, "k": k, "sector": sector, "ce": ce})

# pass 2: sector-peer carbon outlier removal (same logic as score_engine) — a scope
# magnitude that is a sector outlier is a unit error, so null it for display too.
carbon_out = dc.sector_intensity_outliers([(r["k"], r["sector"], r["ce"]["ghg_intensity"]) for r in recs])

out = {}
for r in recs:
    ce = r["ce"]; s1, s2 = ce["scope1"], ce["scope2"]
    if r["k"] in carbon_out:
        s1 = s2 = None
    rec = {}
    # always emit scope keys (value or null) so stale/implausible DB values get overwritten
    rec["scope1_emissions_tco2e"] = round(s1, 1) if s1 is not None else None
    rec["scope2_emissions_tco2e"] = round(s2, 1) if s2 is not None else None
    rec["scope3_emissions_tco2e"] = round(ce["scope3"], 1) if ce["scope3"] is not None else None
    w = dc.clean_water(water.get(r["k"]))
    if w is not None: rec["water_withdrawal_m3"] = round(w, 1)
    out[r["name"]] = rec

Path(r"c:/Viduti/esg-site/tools/fe_backfill.json").write_text(json.dumps(out), encoding="utf-8")
print(f"fe_backfill: {len(out)} companies")
for k in ("scope1_emissions_tco2e","scope2_emissions_tco2e","scope3_emissions_tco2e","water_withdrawal_m3"):
    print(f"  {k}: {sum(1 for v in out.values() if k in v)}")
