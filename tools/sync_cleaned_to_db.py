#!/usr/bin/env python3
"""
Sync the cleaned esg_quotient.json into the production greencurve.db so that the
DB-backed API (/api/esg/*, benchmark, search, admin) matches the static pages.

Updates the columns the published artifact is authoritative for — cin, sector,
revenue_crore, financial_exposure, risk_breakdown, and the headline
esg_risk_score / risk_tier — leaving everything else intact. Idempotent; backs
up the DB first.

esg_risk_score and risk_tier were deliberately excluded when this tool only had
to ship a data-quality clean, on the reasoning that a clean does not move
scores. That stopped being true the moment a methodology change shipped through
the same path: on 2026-08-02 the disclosure floor moved 140 companies between
tiers, the pages rendered the new tier and the API kept serving the old one.
The failure was not cosmetic — a company showed "Low Risk" beside a
risk_breakdown.tier_basis of "floored_undisclosed_material_dimension", which is
a self-contradicting record. This tool's contract is that the DB matches the
pages, and it cannot honour that while skipping the two columns that decide
what the page says.

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
               esg_risk_score=?, risk_tier=?,
               updated_at=CURRENT_TIMESTAMP
           WHERE company_name=?""",
        (c.get("cin", ""), c.get("sector", ""), c.get("revenue_crore"),
         json.dumps(c.get("financial_exposure", {})),
         json.dumps(c.get("risk_breakdown", {})),
         c.get("esg_risk_score"), c.get("risk_tier"),
         name),
    )
    if res.rowcount:
        matched += 1
    else:
        unmatched += 1
        miss.append(name)
conn.commit()
print(f"synced {matched} | unmatched {unmatched}")

# ── esg_meta ─────────────────────────────────────────────────────────────────
# /api/esg/data does NOT compute its header block from the companies table — it
# reads esg_meta (esg_api.py: _get_meta("data_as_of"), _get_meta("summary"), …).
# Nothing had ever synced that table, so it drifted from the artifact for weeks:
# on 2026-08-02 it was still serving generated_at 2026-07-06 and a summary of
# 1227 companies / 36 High / 1190 Medium / 1 Low against an artifact holding
# 1221 / 418 / 530 / 273. Every row was correct and the headline numbers were
# nonsense. Syncing the rows without the meta is only half a sync.
doc = json.loads(open(json_path, encoding="utf-8").read())
META_KEYS = [
    ("generated_at", "generated_at"),
    ("data_as_of", "data_as_of"),
    ("summary", "summary"),
    ("regulations", "regulations"),
    ("factor_matrix", "factor_matrix"),
    ("supply_chain_global", "supply_chain"),
    ("market_summary", "market_summary"),
    ("knowledge_base", "knowledge_base"),
]
meta_written = []
for meta_key, field in META_KEYS:
    if field not in doc:
        continue
    val = doc[field]
    cur.execute(
        "INSERT INTO esg_meta (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
        "updated_at=CURRENT_TIMESTAMP",
        (meta_key, json.dumps(val)),
    )
    meta_written.append(meta_key)
conn.commit()
print(f"esg_meta refreshed: {len(meta_written)} key(s) -> {', '.join(meta_written)}")

# GATE: the meta the API will serve must match the artifact it came from.
_summary_db = cur.execute("SELECT value FROM esg_meta WHERE key='summary'").fetchone()
if _summary_db:
    _db_sum = json.loads(_summary_db[0])
    _art_sum = doc.get("summary", {})
    _bad = {k: (_db_sum.get(k), _art_sum.get(k))
            for k in _art_sum if _db_sum.get(k) != _art_sum.get(k)}
    if _bad:
        conn.close()
        sys.exit(f"FAILED: esg_meta.summary does not match the artifact after sync: {_bad}")
    print(f"consistency: esg_meta.summary matches artifact "
          f"(total={_art_sum.get('total_companies')})")
if miss[:10]:
    print("first unmatched:", miss[:10])

# GATE: the DB must not contradict itself or the artifact it was synced from.
# A tier of "Low" beside a tier_basis of "floored_undisclosed_material_dimension"
# is the exact record that shipped on 2026-08-02 when this tool skipped the tier
# column. Exit non-zero rather than leave it live.
bad_tier = cur.execute(
    "SELECT COUNT(*) FROM companies WHERE risk_tier='Low' AND "
    "risk_breakdown LIKE '%floored_undisclosed_material_dimension%'").fetchone()[0]
drift = 0
for c in companies:
    row = cur.execute("SELECT esg_risk_score, risk_tier FROM companies WHERE company_name=?",
                      (c["company_name"],)).fetchone()
    if row and (row[0] != c.get("esg_risk_score") or row[1] != c.get("risk_tier")):
        drift += 1
print(f"consistency: contradictory Low tiers={bad_tier}, score/tier drift vs artifact={drift}")
if bad_tier or drift:
    conn.close()
    sys.exit(f"FAILED: DB does not match the published artifact "
             f"({bad_tier} contradictory tiers, {drift} rows adrift)")

# sanity: the headline fixes must be neutralised in the DB too
for probe in ("AMRUTANJAN HEALTH CARE LIMITED", "SIS Limited", "JSW Steel Limited"):
    row = cur.execute("SELECT sector, financial_exposure FROM companies WHERE company_name=?", (probe,)).fetchone()
    if row:
        fe = json.loads(row[1] or "{}")
        print(f"  {probe}: sector={row[0]} s1={fe.get('scope1_emissions_tco2e')} "
              f"water={fe.get('water_withdrawal_m3')} waste={fe.get('waste_tonnes')}")
conn.close()
