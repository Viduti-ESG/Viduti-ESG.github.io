"""
Apply meta_backfill_deploy.json to the production DB. Runs ON THE SERVER.
Sets only financial_year / nse_symbol per company (top-level columns that
update_db.py leaves untouched). Backs up the DB; single transaction; only writes
a column when the backfill has a value and it differs from what's stored.
Usage: python3 apply_meta.py /var/www/greencurve/greencurve.db meta_backfill_deploy.json
"""
import sys, json, sqlite3, shutil, time

db_path, json_path = sys.argv[1], sys.argv[2]
data = json.loads(open(json_path, encoding="utf-8").read())

bak = f"{db_path}.bak-meta-{int(time.time())}"
shutil.copy2(db_path, bak)
print("backup:", bak)

conn = sqlite3.connect(db_path); conn.row_factory = sqlite3.Row
cur = conn.cursor()
matched = unmatched = fy_set = sym_set = 0
conn.execute("BEGIN")
for name, rec in data.items():
    row = cur.execute("SELECT financial_year, nse_symbol FROM companies WHERE company_name=?", (name,)).fetchone()
    if not row:
        unmatched += 1; continue
    matched += 1
    sets, vals = [], []
    fy = rec.get("financial_year")
    if fy and (row["financial_year"] or "").strip("-") != fy:
        sets.append("financial_year=?"); vals.append(fy); fy_set += 1
    sym = rec.get("nse_symbol")
    if sym and not (row["nse_symbol"] or "").strip():
        sets.append("nse_symbol=?"); vals.append(sym); sym_set += 1
    if sets:
        vals.append(name)
        cur.execute(f"UPDATE companies SET {', '.join(sets)}, updated_at=CURRENT_TIMESTAMP WHERE company_name=?", vals)
conn.commit()
print(f"matched {matched} | unmatched {unmatched} | financial_year set {fy_set} | nse_symbol set {sym_set}")
conn.close()
