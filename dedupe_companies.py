"""
Green Curve — one-off maintenance: remove duplicate company rows.

Some companies were ingested twice under different casing of `company_name`
(e.g. "ADANI POWER LIMITED" vs "Adani Power Limited"). Because the UNIQUE
constraint on companies.company_name is case-SENSITIVE in SQLite, both rows
were allowed. This collapses each case-insensitive duplicate group down to one
canonical row, safely repoints any user data that referenced the dropped
variant, and recomputes the esg_meta summary counts.

SAFE BY DESIGN:
  * Dry-run by default — prints exactly what it WOULD do and changes nothing.
    Pass --apply to actually write.
  * Makes a timestamped backup copy of the DB file before applying.
  * Runs inside a single transaction (all-or-nothing).
  * Repoints watchlist / cap_progress / watchlist_snapshots / user_profiles
    references from the dropped name to the kept name BEFORE deleting, so no
    user loses a watched company or action-plan progress.

Canonical row per group = the one with the most complete data (longest
combined ai_summary + JSON fields); ties broken by lowest id. Its existing
company_name string is kept as the canonical name.

Usage:
    python dedupe_companies.py            # dry-run, no changes
    python dedupe_companies.py --apply    # back up + apply
    GC_DB_PATH=/path/to/greencurve.db python dedupe_companies.py --apply
"""
import json
import shutil
import sqlite3
import sys
from datetime import datetime

from db import DB_PATH  # reuse the same DB path resolution as the app

# Tables that reference a company by its name string, and the unique/PK columns
# that could collide when we repoint a dropped name to the kept name.
#   table -> tuple of columns forming the row-identity (besides company_name)
_REF_TABLES = {
    "watchlist":            ("user_id",),
    "cap_progress":         ("user_id", "rec_id"),
    "watchlist_snapshots":  (),          # no uniqueness; plain UPDATE is safe
    "user_profiles":        (),          # company_name is informational here
}


def _completeness(row: sqlite3.Row) -> int:
    """Higher = more complete. Used to choose which duplicate to keep."""
    fields = ("ai_summary", "risk_breakdown", "financial_exposure", "governance",
              "supply_chain", "double_materiality", "esg_targets",
              "materials_exposed", "anomaly_flags", "cin", "nse_symbol")
    return sum(len(str(row[f] or "")) for f in fields)


def _repoint_refs(conn, drop_name: str, keep_name: str, apply: bool) -> list[str]:
    """Move any references from drop_name to keep_name without violating PK/UNIQUE."""
    actions = []
    for table, key_cols in _REF_TABLES.items():
        # Does the table exist? (older DBs may not have all of them)
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            continue
        n = conn.execute(
            f"SELECT COUNT(*) AS c FROM {table} WHERE company_name=?", (drop_name,)
        ).fetchone()["c"]
        if not n:
            continue
        if key_cols:
            # UPDATE OR IGNORE moves rows that won't collide; survivors (a row
            # already exists for keep_name with same key) are then deleted.
            if apply:
                conn.execute(
                    f"UPDATE OR IGNORE {table} SET company_name=? WHERE company_name=?",
                    (keep_name, drop_name),
                )
                conn.execute(
                    f"DELETE FROM {table} WHERE company_name=?", (drop_name,)
                )
            actions.append(f"    repoint {n} row(s) in {table} (collision-safe)")
        else:
            if apply:
                conn.execute(
                    f"UPDATE {table} SET company_name=? WHERE company_name=?",
                    (keep_name, drop_name),
                )
            actions.append(f"    repoint {n} row(s) in {table}")
    return actions


def _recompute_summary(conn, apply: bool) -> str:
    """Refresh total/high/medium/low/avg in the esg_meta 'summary' blob."""
    rows = conn.execute(
        "SELECT risk_tier, esg_risk_score FROM companies"
    ).fetchall()
    total = len(rows)
    tiers = {"High": 0, "Medium": 0, "Low": 0}
    for r in rows:
        tiers[r["risk_tier"]] = tiers.get(r["risk_tier"], 0) + 1
    scores = [r["esg_risk_score"] for r in rows if r["esg_risk_score"] is not None]
    avg = round(sum(scores) / len(scores), 2) if scores else 0

    meta = conn.execute(
        "SELECT value FROM esg_meta WHERE key='summary'"
    ).fetchone()
    summary = json.loads(meta["value"]) if meta else {}
    summary.update({
        "total_companies":        total,
        "high_risk_companies":    tiers.get("High", 0),
        "medium_risk_companies":  tiers.get("Medium", 0),
        "low_risk_companies":     tiers.get("Low", 0),
        "avg_esg_risk_score":     avg,
    })
    if apply and meta is not None:
        conn.execute(
            "UPDATE esg_meta SET value=?, updated_at=CURRENT_TIMESTAMP WHERE key='summary'",
            (json.dumps(summary),),
        )
    return (f"  summary -> total={total} high={tiers.get('High',0)} "
            f"medium={tiers.get('Medium',0)} low={tiers.get('Low',0)} avg={avg}")


def main() -> int:
    apply = "--apply" in sys.argv
    if not DB_PATH.exists():
        print(f"[dedupe] DB not found at {DB_PATH}. "
              f"Run this on the server, or set GC_DB_PATH.")
        return 1

    if apply:
        backup = DB_PATH.with_name(
            f"{DB_PATH.stem}.backup-{datetime.now():%Y%m%d-%H%M%S}{DB_PATH.suffix}")
        shutil.copy2(DB_PATH, backup)
        print(f"[dedupe] Backup written: {backup}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    rows = conn.execute("SELECT * FROM companies").fetchall()
    groups: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        groups.setdefault((r["company_name"] or "").strip().upper(), []).append(r)
    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}

    print(f"[dedupe] {len(rows)} company rows, "
          f"{len(groups)} distinct (case-insensitive), "
          f"{len(dup_groups)} duplicate group(s).")
    if not dup_groups:
        print("[dedupe] Nothing to do.")
        return 0

    try:
        conn.execute("BEGIN")
        for key, members in dup_groups.items():
            members_sorted = sorted(members, key=lambda r: (-_completeness(r), r["id"]))
            keep = members_sorted[0]
            drops = members_sorted[1:]
            print(f"\n  group '{key}': keep id={keep['id']} "
                  f"name='{keep['company_name']}' (score {keep['esg_risk_score']})")
            for d in drops:
                print(f"    drop id={d['id']} name='{d['company_name']}'")
                for line in _repoint_refs(conn, d["company_name"], keep["company_name"], apply):
                    print(line)
                if apply:
                    conn.execute("DELETE FROM companies WHERE id=?", (d["id"],))

        print("\n" + _recompute_summary(conn, apply))

        if apply:
            conn.execute("COMMIT")
            print("\n[dedupe] APPLIED. Restart the API so it reloads from the DB.")
        else:
            conn.execute("ROLLBACK")
            print("\n[dedupe] DRY-RUN only — no changes written. "
                  "Re-run with --apply to commit.")
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"[dedupe] ERROR, rolled back: {e}")
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
