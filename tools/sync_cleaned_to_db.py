#!/usr/bin/env python3
"""
Sync the cleaned esg_quotient.json into the production greencurve.db so that the
DB-backed API (/api/esg/*, benchmark, search, admin) matches the static pages.

Updates ONLY the columns touched by the data-quality clean — cin, sector,
revenue_crore, financial_exposure, risk_breakdown — for each company, leaving
scores and everything else intact. Idempotent; backs up the DB first.

Usage (on server):
    /var/www/greencurve/venv/bin/python tools/sync_cleaned_to_db.py \
        /var/www/greencurve/greencurve.db assets/data/esg_quotient.json
"""
import json
import shutil
import sqlite3
import sys
import time

db_path, json_path = sys.argv[1], sys.argv[2]
companies = json.loads(open(json_path, encoding="utf-8").read()).get("companies", [])

bak = f"{db_path}.bak-{int(time.time())}"
shutil.copy2(db_path, bak)
print("backup:", bak)

conn = sqlite3.connect(db_path)
cur = conn.cursor()
matched = unmatched = 0
miss = []
for c in companies:
    name = c["company_name"]
    res = cur.execute(
        """UPDATE companies SET
               cin=?, sector=?, revenue_crore=?,
               financial_exposure=?, risk_breakdown=?,
               updated_at=CURRENT_TIMESTAMP
           WHERE company_name=?""",
        (c.get("cin", ""), c.get("sector", ""), c.get("revenue_crore"),
         json.dumps(c.get("financial_exposure", {})),
         json.dumps(c.get("risk_breakdown", {})),
         name),
    )
    if res.rowcount:
        matched += 1
    else:
        unmatched += 1
        miss.append(name)
conn.commit()
print(f"synced {matched} | unmatched {unmatched}")
if miss[:10]:
    print("first unmatched:", miss[:10])

# sanity: the headline fixes must be neutralised in the DB too
for probe in ("AMRUTANJAN HEALTH CARE LIMITED", "SIS Limited", "JSW Steel Limited"):
    row = cur.execute("SELECT sector, financial_exposure FROM companies WHERE company_name=?", (probe,)).fetchone()
    if row:
        fe = json.loads(row[1] or "{}")
        print(f"  {probe}: sector={row[0]} s1={fe.get('scope1_emissions_tco2e')} "
              f"water={fe.get('water_withdrawal_m3')} waste={fe.get('waste_tonnes')}")
conn.close()
