"""
Apply fe_backfill_deploy.json to the STATIC display artifact
assets/data/esg_quotient.json (the source for generated company pages), mirroring
apply_fe_backfill.py's DB logic so the static pages and the DB agree.

Merges scope1/2/3 + water into each company's financial_exposure (preserving
other keys). scope keys set to backfill value (incl null, to clear false zeros);
water set if present, else deleted (clears implausible values).

Run BEFORE merge_bottlenecks.py so ghg_intensity can be computed from real
absolute Scope 1+2. Idempotent. Keeps a .bak.
"""
import json, shutil
from pathlib import Path

QFILE = Path(r"c:/Viduti/esg-site/assets/data/esg_quotient.json")
BF    = Path(r"c:/Viduti/esg-site/tools/fe_backfill_deploy.json")

bf = json.loads(BF.read_text(encoding="utf-8"))
doc = json.loads(QFILE.read_text(encoding="utf-8"))

SCOPE_KEYS = ("scope1_emissions_tco2e", "scope2_emissions_tco2e", "scope3_emissions_tco2e")
matched = changed = 0
for c in doc["companies"]:
    rec = bf.get(c["company_name"])
    if not rec:
        continue
    matched += 1
    fe = c.get("financial_exposure")
    if not isinstance(fe, dict):
        fe = {}
    before = json.dumps(fe, sort_keys=True)
    for k in SCOPE_KEYS:
        fe[k] = rec.get(k)
    if "water_withdrawal_m3" in rec:
        fe["water_withdrawal_m3"] = rec["water_withdrawal_m3"]
    else:
        fe.pop("water_withdrawal_m3", None)
    if json.dumps(fe, sort_keys=True) != before:
        c["financial_exposure"] = fe
        changed += 1

shutil.copy2(QFILE, QFILE.with_suffix(".json.bak"))
QFILE.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"matched {matched} | changed {changed}")
both = sum(1 for c in doc["companies"]
           if (c.get("financial_exposure") or {}).get("scope1_emissions_tco2e") is not None
           and (c.get("financial_exposure") or {}).get("scope2_emissions_tco2e") is not None)
print(f"companies now with absolute Scope 1+2: {both}")
