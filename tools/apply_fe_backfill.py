"""
Apply fe_backfill_deploy.json to the production DB's financial_exposure column.
Runs ON THE SERVER. Merges scope1/2/3 + water into each company's existing
financial_exposure JSON (preserving other keys like epr_applicable / cost band).

  * scope1/2/3_emissions_tco2e  -> set to backfill value (including null, to clear
    stale/implausible figures such as false zeros).
  * water_withdrawal_m3         -> set if present; DELETED if absent in backfill
    (clears implausible values like SIS's 3.2e12 m³).

Backs up the DB first; single transaction.
Usage: python3 apply_fe_backfill.py /var/www/greencurve/greencurve.db fe_backfill_deploy.json
"""
import sys, json, sqlite3, shutil, time

db_path, json_path = sys.argv[1], sys.argv[2]
data = json.loads(open(json_path, encoding="utf-8").read())

bak = f"{db_path}.bak-febackfill-{int(time.time())}"
shutil.copy2(db_path, bak)
print("backup:", bak)

conn = sqlite3.connect(db_path); conn.row_factory = sqlite3.Row
cur = conn.cursor()

SCOPE_KEYS = ("scope1_emissions_tco2e", "scope2_emissions_tco2e", "scope3_emissions_tco2e")
matched = unmatched = changed = 0
miss = []
conn.execute("BEGIN")
for name, rec in data.items():
    row = cur.execute("SELECT financial_exposure FROM companies WHERE company_name=?", (name,)).fetchone()
    if not row:
        unmatched += 1; miss.append(name); continue
    matched += 1
    try:
        fe = json.loads(row["financial_exposure"] or "{}")
    except Exception:
        fe = {}
    if not isinstance(fe, dict):
        fe = {}
    before = json.dumps(fe, sort_keys=True)
    for k in SCOPE_KEYS:
        fe[k] = rec.get(k)                      # set (may be null)
    if "water_withdrawal_m3" in rec:
        fe["water_withdrawal_m3"] = rec["water_withdrawal_m3"]
    else:
        fe.pop("water_withdrawal_m3", None)     # clear implausible water
    after = json.dumps(fe, sort_keys=True)
    if after != before:
        cur.execute("UPDATE companies SET financial_exposure=?, updated_at=CURRENT_TIMESTAMP WHERE company_name=?",
                    (json.dumps(fe), name))
        changed += 1
conn.commit()
print(f"matched {matched} | unmatched {unmatched} | changed {changed}")
if miss[:10]:
    print("first unmatched:", miss[:10])
conn.close()
