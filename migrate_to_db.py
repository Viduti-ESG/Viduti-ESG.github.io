"""
Green Curve — One-time migration: esg_quotient.json → SQLite
Run on the server: python3 migrate_to_db.py

Safe to run multiple times — uses INSERT OR REPLACE so existing rows are updated.
"""

import json
import sys
from pathlib import Path

# Make sure db.py is importable from same directory
sys.path.insert(0, str(Path(__file__).parent))
from db import get_conn, init_db

JSON_PATH = Path(__file__).parent / "assets" / "data" / "esg_quotient.json"


def migrate():
    print(f"Reading {JSON_PATH} ...")
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    companies = data.get("companies", [])
    print(f"Found {len(companies)} companies. Initialising DB ...")
    init_db()

    inserted = updated = 0
    with get_conn() as conn:
        for i, c in enumerate(companies, 1):
            existing = conn.execute(
                "SELECT id FROM companies WHERE company_name=?", (c["company_name"],)
            ).fetchone()

            row_vals = (
                c.get("cin", "") or "",
                c.get("nse_symbol", "") or "",
                c.get("sector", "") or "",
                c.get("products", "") or "",
                c.get("revenue_crore") or 0,
                c.get("financial_year", "") or "",
                c.get("esg_risk_score") or 0,
                c.get("risk_tier", "Medium") or "Medium",
                json.dumps(c.get("risk_breakdown") or {}),
                json.dumps(c.get("top_risk_factors") or []),
                json.dumps(c.get("financial_exposure") or {}),
                json.dumps(c.get("supply_chain") or {}),
                json.dumps(c.get("governance") or {}),
                json.dumps(c.get("double_materiality") or {}),
                json.dumps(c.get("esg_targets") or []),
                json.dumps(c.get("materials_exposed") or []),
                c.get("ai_summary", "") or "",
            )

            if existing:
                conn.execute("""
                    UPDATE companies SET
                      cin=?,nse_symbol=?,sector=?,products=?,revenue_crore=?,financial_year=?,
                      esg_risk_score=?,risk_tier=?,risk_breakdown=?,top_risk_factors=?,
                      financial_exposure=?,supply_chain=?,governance=?,double_materiality=?,
                      esg_targets=?,materials_exposed=?,ai_summary=?,updated_at=CURRENT_TIMESTAMP
                    WHERE company_name=?
                """, row_vals + (c["company_name"],))
                updated += 1
            else:
                conn.execute("""
                    INSERT INTO companies
                      (cin,nse_symbol,sector,products,revenue_crore,financial_year,
                       esg_risk_score,risk_tier,risk_breakdown,top_risk_factors,
                       financial_exposure,supply_chain,governance,double_materiality,
                       esg_targets,materials_exposed,ai_summary,company_name)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, row_vals + (c["company_name"],))
                inserted += 1

            if i % 100 == 0:
                print(f"  {i}/{len(companies)} processed ...")

        # Store meta blobs
        for meta_key, field in [
            ("generated_at",        "generated_at"),
            ("data_as_of",          "data_as_of"),
            ("summary",             "summary"),
            ("regulations",         "regulations"),
            ("factor_matrix",       "factor_matrix"),
            ("supply_chain_global", "supply_chain"),
            ("market_summary",      "market_summary"),
            ("knowledge_base",      "knowledge_base"),
        ]:
            val = data.get(field)
            if val is not None:
                conn.execute(
                    "INSERT INTO esg_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
                    (meta_key, json.dumps(val))
                )
        print(f"  Meta blobs stored.")

    total = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    print(f"\nDone. Inserted: {inserted}, Updated: {updated}, Total in DB: {total}")


if __name__ == "__main__":
    migrate()
