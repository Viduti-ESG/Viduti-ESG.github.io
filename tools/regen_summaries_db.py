"""
Incremental AI-summary refresh — writes straight to the DB (companies.ai_summary).

Runs on the SERVER as a daily systemd timer (gc-summary-regen). Deliberately does
NOT touch git-tracked files (esg_quotient.json / company pages) so it never creates
git drift that would break `git pull --ff-only` deploys. The app + API serve
summaries from the DB, so refreshed text appears in company deep-dives, search and
screener immediately. (Static SEO pages catch up on the next full laptop deploy.)

Self-tracking via companies.summary_regen: only rows still '' are processed, and a
row is marked ONLY on success — so failures (e.g. Groq rate-limit) are retried next
run. Stops early after repeated rate-limits to avoid burning the daily free budget.

Usage (server):  GROQ_API_KEY set in env; run as www-data
    python3 tools/regen_summaries_db.py --limit 150
"""
import os, sys, time, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import esg_api                         # _row_to_company (DB row -> unified dict)
import db                              # get_conn / init_db (ensures columns exist)
from regen_summaries import build_user, SYSTEM, groq, GROQ_MODEL  # shared prompt

def parse_limit(default=150):
    for a in sys.argv:
        if a.startswith("--limit"):
            return int(a.split("=")[-1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])
    return default

def main():
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        print("!! GROQ_API_KEY not set"); return 1
    limit = parse_limit()
    db.init_db()  # idempotent — guarantees summary_regen + metric columns exist

    with db.get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM companies WHERE COALESCE(summary_regen,'')='' ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
        remaining = conn.execute(
            "SELECT COUNT(*) FROM companies WHERE COALESCE(summary_regen,'')=''"
        ).fetchone()[0]

    print(f"[{time.strftime('%Y-%m-%d %H:%M')}] to refresh this run: {len(rows)} "
          f"(model={GROQ_MODEL}, still pending overall: {remaining})")

    done = fail = ratelimited = 0
    for r in rows:
        c = esg_api._row_to_company(r, lite=False)  # unified dict incl. new metrics
        try:
            txt = groq(SYSTEM, build_user(c), key)
            if len(txt.split()) >= 60 and "0-0 crore" not in txt and "0–0 crore" not in txt:
                with db.get_conn() as conn:
                    conn.execute(
                        "UPDATE companies SET ai_summary=?, summary_regen=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (txt, GROQ_MODEL, r["id"]),
                    )
                done += 1
            else:
                fail += 1  # weak output — leave unmarked, retried next run
        except Exception as e:
            msg = str(e).lower()
            if "rate" in msg or "429" in msg or "limit" in msg:
                ratelimited += 1
                if ratelimited >= 5:
                    print(f"  stopping early: {ratelimited} consecutive rate-limits (daily cap). "
                          f"Remaining retried tomorrow.")
                    break
            else:
                fail += 1
                print(f"  [error] {c.get('company_name')}: {e}")
            time.sleep(10)
            continue
        ratelimited = 0
        time.sleep(6)  # ~10 req/min — respect Groq free-tier limits

    # invalidate the API's in-memory cache so refreshed summaries serve immediately
    try:
        esg_api._invalidate_esg_cache()
    except Exception:
        pass
    print(f"[{time.strftime('%Y-%m-%d %H:%M')}] done={done} fail/weak={fail} "
          f"rate-limited-stops={ratelimited}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
