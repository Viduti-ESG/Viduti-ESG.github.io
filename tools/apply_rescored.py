"""
Publish the v2 ESG-Quotient scores into the display/source-of-truth artifact.

Applies tools/rescored.json (output of score_engine.py) into
assets/data/esg_quotient.json, the file migrate_to_db.py rebuilds the production
DB from. Mirrors what update_db.py does to the server DB, but for the static JSON:

  * dedupes case-variant company rows (keeps the most complete),
  * matches by NORMALISED name, and updates ONLY the score-related keys
    (sector, esg_risk_score, risk_tier, risk_breakdown, top_risk_factors,
     impact_materiality + double_materiality quadrant),
  * preserves every other key (financial_exposure, waste_profile, ai_summary, ...).

Idempotent. Writes a timestamped backup. Run AFTER score_engine.py and BEFORE
merge_bottlenecks.py / build_sector_benchmarks.py / clean_published.py.
"""
import json, shutil, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import data_clean as dc

ROOT = Path(__file__).resolve().parent.parent
QFILE = ROOT / "assets" / "data" / "esg_quotient.json"
RESCORED = Path(__file__).resolve().parent / "rescored.json"
BACKUP_DIR = ROOT / "_dq_backups"

doc = json.loads(QFILE.read_text(encoding="utf-8"))
companies = doc.get("companies", [])
rescored = json.loads(RESCORED.read_text(encoding="utf-8"))
by_norm = {dc.norm(name): rec for name, rec in rescored.items()}

# 1) dedupe case-variant rows so each company appears once
companies, dropped = dc.dedupe_companies(companies)
if dropped:
    print(f"deduped {len(dropped)} case-variant row(s): {dropped}")

# 2) apply v2 scores by normalised name (preserve all other keys)
matched = unmatched = 0
miss = []
for c in companies:
    rec = by_norm.get(dc.norm(c.get("company_name", "")))
    if not rec:
        unmatched += 1
        miss.append(c.get("company_name"))
        continue
    c["sector"] = rec["sector"]
    c["esg_risk_score"] = rec["esg_risk_score"]
    c["risk_tier"] = rec["risk_tier"]
    c["risk_breakdown"] = rec["risk_breakdown"]
    c["top_risk_factors"] = rec["top_risk_factors"]
    # reconciled revenue from score_engine/company_profiler — keeps the
    # displayed revenue identical to the intensity denominator (SAIL was
    # published at ₹98.6 cr against a ₹1.02-lakh-cr filing before this)
    if rec.get("revenue_crore") is not None:
        c["revenue_crore"] = rec["revenue_crore"]
    im = rec.get("impact_materiality")
    fm = rec["esg_risk_score"]
    if im is None:
        im = fm
    # keep double_materiality consistent with the refreshed scores
    dm = c.get("double_materiality")
    if not isinstance(dm, dict):
        dm = {}
    dm["financial_materiality"] = fm
    dm["impact_materiality"] = im
    dm["quadrant"] = ("Dual Materiality" if fm >= 5 and im >= 5 else
                      "Financially Material" if fm >= 5 else
                      "Impact Material" if im >= 5 else "Watch List")
    c["double_materiality"] = dm
    matched += 1

doc["companies"] = companies

# backup + write
BACKUP_DIR.mkdir(exist_ok=True)
ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
shutil.copy2(QFILE, BACKUP_DIR / f"esg_quotient.{ts}.json.bak")
QFILE.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

print(f"applied v2 scores: matched {matched} | unmatched {unmatched} | total rows {len(companies)}")
if miss:
    print("unmatched (kept with existing scores):", miss[:10])
