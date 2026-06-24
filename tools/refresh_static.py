"""
Runs ON THE SERVER. (1) backfills financial_exposure with real Scope1/2/3 + water,
(2) exports a fresh esg_quotient.json from the DB for the static page generators.
Usage: python3 refresh_static.py /var/www/greencurve/greencurve.db fe_backfill.json /var/www/greencurve/assets/data/esg_quotient.json
"""
import json, sqlite3, sys, time, shutil, statistics
from collections import defaultdict

db, febk, out_json = sys.argv[1], sys.argv[2], sys.argv[3]
fe_data = json.loads(open(febk, encoding="utf-8").read())
shutil.copy2(db, f"{db}.bak-fe-{int(time.time())}")

conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row; cur = conn.cursor()

# 1) backfill financial_exposure (merge, keep existing keys)
upd = 0
for row in cur.execute("SELECT company_name, financial_exposure FROM companies").fetchall():
    name = row["company_name"]
    if name not in fe_data: continue
    try: fe = json.loads(row["financial_exposure"] or "{}")
    except Exception: fe = {}
    if not isinstance(fe, dict): fe = {}
    fe.update(fe_data[name])
    conn.execute("UPDATE companies SET financial_exposure=? WHERE company_name=?", (json.dumps(fe), name))
    upd += 1
conn.commit()
print("financial_exposure updated:", upd)

# 2) export esg_quotient.json (full company rows, JSON fields parsed)
JSONF = {"risk_breakdown","top_risk_factors","financial_exposure","supply_chain",
         "governance","double_materiality","esg_targets","materials_exposed","anomaly_flags"}
comps = []
for row in cur.execute("SELECT * FROM companies").fetchall():
    d = dict(row)
    for f in JSONF:
        if f in d:
            try: d[f] = json.loads(d[f] or "null")
            except Exception: pass
    comps.append(d)

scores = [c["esg_risk_score"] for c in comps if isinstance(c["esg_risk_score"], (int, float))]
avg = round(statistics.mean(scores), 2) if scores else 0
sec = defaultdict(list)
for c in comps: sec[(c.get("sector") or "").strip()].append(c.get("esg_risk_score") or 0)
cands = [(s, statistics.mean(v)) for s, v in sec.items() if s and len(v) >= 8]
most = max(cands, key=lambda x: x[1])[0] if cands else ""
summary = {"avg_esg_risk_score": avg, "most_at_risk_sector": most, "total": len(comps),
           "high": sum(1 for c in comps if c.get("risk_tier") == "High"),
           "medium": sum(1 for c in comps if c.get("risk_tier") == "Medium"),
           "low": sum(1 for c in comps if c.get("risk_tier") == "Low")}
today = time.strftime("%Y-%m-%d")
out = {"generated_at": today, "data_as_of": today, "total_companies": len(comps),
       "summary": summary, "companies": comps}
open(out_json, "w", encoding="utf-8").write(json.dumps(out))
print(f"exported {len(comps)} -> {out_json} | avg {avg} | most_at_risk '{most}'")
conn.close()
