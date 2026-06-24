import sqlite3, json, collections, sys
db = sys.argv[1] if len(sys.argv) > 1 else "/var/www/greencurve/greencurve.db"
c = sqlite3.connect(db); c.row_factory = sqlite3.Row
for nm in ["SIS Limited", "NTPC LIMITED", "Mastek Limited", "Adani Power Limited", "JSW Steel Limited"]:
    r = c.execute("SELECT esg_risk_score,risk_tier,financial_exposure FROM companies WHERE company_name=?", (nm,)).fetchone()
    if not r:
        print(nm, "-> NOT FOUND"); continue
    fe = json.loads(r["financial_exposure"] or "{}")
    print("%-22s score=%s tier=%s s1=%s s2=%s water=%s" % (
        nm, r["esg_risk_score"], r["risk_tier"],
        fe.get("scope1_emissions_tco2e"), fe.get("scope2_emissions_tco2e"), fe.get("water_withdrawal_m3")))
names = [x[0] for x in c.execute("SELECT company_name FROM companies").fetchall()]
nl = collections.Counter(n.lower() for n in names)
print("total:", len(names), "| case-dup groups:", sum(1 for v in nl.values() if v > 1))
sc = c.execute("SELECT MIN(esg_risk_score),MAX(esg_risk_score),AVG(esg_risk_score) FROM companies").fetchone()
print("score range: %.1f - %.1f | avg %.2f" % (sc[0], sc[1], sc[2]))
