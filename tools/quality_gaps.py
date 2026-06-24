import sqlite3, json, collections, sys
c = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1 else "/var/www/greencurve/greencurve.db")
c.row_factory = sqlite3.Row
rows = c.execute("SELECT company_name,sector,esg_risk_score,risk_breakdown,top_risk_factors,financial_exposure,financial_year,cin,nse_symbol FROM companies").fetchall()
n = len(rows); print("total companies:", n)
conf = []; ins = 0; nosec = 0; noscope3 = 0; nocarbon = 0; nofy = 0; nowater = 0; nocin = 0; nosym = 0
fy = collections.Counter()
for r in rows:
    rb = json.loads(r["risk_breakdown"] or "{}"); fe = json.loads(r["financial_exposure"] or "{}")
    if rb.get("disclosure_confidence") is not None: conf.append(rb["disclosure_confidence"])
    if "Data insufficient" in (r["top_risk_factors"] or ""): ins += 1
    if not r["sector"] or r["sector"] == "Unclassified": nosec += 1
    if fe.get("scope3_emissions_tco2e") is None: noscope3 += 1
    if rb.get("ghg_intensity") is None: nocarbon += 1
    if fe.get("water_withdrawal_m3") is None: nowater += 1
    if not r["cin"]: nocin += 1
    if not r["nse_symbol"]: nosym += 1
    yr = (r["financial_year"] or "").strip("-")
    if not yr: nofy += 1
    fy[r["financial_year"]] += 1
cc = sorted(conf)
print("disclosure_confidence: min %s median %s" % (cc[0], cc[len(cc)//2]))
print("confidence bands:", dict(sorted(collections.Counter((x//20*20) for x in cc).items())))
print("conf < 60:", sum(1 for x in cc if x < 60))
print("'Data insufficient' top factors:", ins)
print("Unclassified sector:", nosec)
print("no carbon intensity:", nocarbon)
print("no scope3 displayed:", noscope3)
print("no water displayed:", nowater)
print("missing CIN:", nocin, "| missing NSE symbol:", nosym)
print("no/empty financial_year:", nofy)
print("financial_year distribution (top 6):", dict(fy.most_common(6)))
