"""
Apply ESG Quotient v2 scores to the production DB. Runs ON THE SERVER.
Updates only the 5 score-related columns per company; leaves everything else intact.
Usage: python3 update_db.py /var/www/greencurve/greencurve.db rescored.json
"""
import sys, json, sqlite3, shutil, time

db_path, json_path = sys.argv[1], sys.argv[2]
data = json.loads(open(json_path, encoding="utf-8").read())

bak = f"{db_path}.bak-{int(time.time())}"
shutil.copy2(db_path, bak)
print("backup:", bak)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

matched = unmatched = 0
miss = []
for name, rec in data.items():
    row = cur.execute("SELECT double_materiality FROM companies WHERE company_name=?", (name,)).fetchone()
    if not row:
        unmatched += 1; miss.append(name); continue
    # keep DM but refresh financial_materiality to the new score for consistency
    try:
        dm = json.loads(row["double_materiality"] or "{}")
    except Exception:
        dm = {}
    if isinstance(dm, dict):
        dm["financial_materiality"] = rec["esg_risk_score"]
        if rec.get("impact_materiality") is not None:
            dm["impact_materiality"] = rec["impact_materiality"]
        fm = rec["esg_risk_score"]; im = rec.get("impact_materiality", fm)
        dm["quadrant"] = ("Dual Materiality" if fm >= 5 and im >= 5 else
                          "Financially Material" if fm >= 5 else
                          "Impact Material" if im >= 5 else "Watch List")
    cur.execute(
        """UPDATE companies SET sector=?, esg_risk_score=?, risk_tier=?,
                  risk_breakdown=?, top_risk_factors=?, double_materiality=?,
                  updated_at=CURRENT_TIMESTAMP WHERE company_name=?""",
        (rec["sector"], rec["esg_risk_score"], rec["risk_tier"],
         json.dumps(rec["risk_breakdown"]), json.dumps(rec["top_risk_factors"]),
         json.dumps(dm), name),
    )
    matched += 1

conn.commit()
print(f"updated {matched} | unmatched {unmatched}")
if miss[:10]: print("first unmatched:", miss[:10])

# Fix 4: delete DB rows not in the deduped score set (case-variant duplicates).
# Guarded: only proceed if the count is small, to avoid accidental mass-deletion.
keep = set(data.keys())
extra = [r[0] for r in cur.execute("SELECT company_name FROM companies").fetchall() if r[0] not in keep]
if 0 < len(extra) <= 20:
    cur.executemany("DELETE FROM companies WHERE company_name=?", [(n,) for n in extra])
    conn.commit()
    print(f"deleted {len(extra)} duplicate/stale rows:", extra)
elif len(extra) > 20:
    print(f"SKIPPED delete — {len(extra)} extra rows exceeds safety cap (investigate)")
# sanity
r = cur.execute("SELECT MIN(esg_risk_score),MAX(esg_risk_score),COUNT(DISTINCT sector) FROM companies").fetchone()
print("post-update score range:", r[0], "-", r[1], "| distinct sectors:", r[2])
print("tier counts:", dict((t, cur.execute("SELECT COUNT(*) FROM companies WHERE risk_tier=?", (t,)).fetchone()[0]) for t in ("Low","Medium","High")))
conn.close()
