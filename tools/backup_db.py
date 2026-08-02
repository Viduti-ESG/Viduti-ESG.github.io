#!/usr/bin/env python3
"""
Green Curve — DAILY DATABASE BACKUP, verified.

greencurve.db is the only irreplaceable thing on the production box. Everything
else — pages, the ESG artifact, the company corpus — can be regenerated from
git and the XBRL filings. The database cannot: user accounts, watchlists,
password resets, CAP progress and AI-usage counters exist nowhere else.

Until now its only backups were the incidental `greencurve.db.bak-<epoch>`
copies that `sync_cleaned_to_db.py` drops before a data load — accidental,
irregular, never verified, never pruned.

Three rules this script exists to enforce:

1. **Copy it the safe way.** A live SQLite file copied with `cp` while a write
   is in flight yields a torn database. This uses SQLite's online backup API,
   which takes a transactionally consistent snapshot of a database being
   written to.

2. **An unverified backup is a hypothesis.** Every backup is re-opened,
   `PRAGMA integrity_check`ed, and row-counted against the source before it is
   allowed to count as a backup. A file that fails is deleted, not kept — a
   corrupt backup is worse than no backup, because it looks like protection.

3. **Retention is bounded.** Daily backups for DAILY_KEEP days, then one per
   month for MONTHLY_KEEP months. Old ones are pruned so the free-tier disk
   cannot fill.

    python3 tools/backup_db.py                 # back up + verify + prune
    python3 tools/backup_db.py --verify-only   # re-verify existing backups
    python3 tools/backup_db.py --json

Stdlib only. Exits non-zero if a backup could not be made AND verified.
"""
import argparse
import datetime as dt
import gzip
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path("/var/www/greencurve")
if not ROOT.exists():
    ROOT = Path(r"c:/Viduti/esg-site")

DB = ROOT / "greencurve.db"
BACKUP_DIR = ROOT / "_db_backups"
STATUS_OUT = Path("/var/log/greencurve/backup_db.json")

DAILY_KEEP = 14        # keep every daily backup for this many days
MONTHLY_KEEP = 6       # then keep one per month for this many months
# Tables whose row counts must match between source and backup. Chosen because
# losing any of them is unrecoverable; `companies` is excluded on purpose — it
# is rebuilt from the artifact by sync_cleaned_to_db.py.
CRITICAL = ("users", "watchlist", "user_profiles", "cap_progress", "ai_usage")

findings = []


def add(level, msg):
    findings.append({"level": level, "message": msg})


def table_counts(path: Path):
    """Row counts for every table present, read-only."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'")]
        return {n: conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]
                for n in names}
    finally:
        conn.close()


def make_backup():
    """Online-backup the live DB to a temp file, verify it, then gzip it."""
    if not DB.exists():
        add("FAIL", f"no database at {DB}")
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final = BACKUP_DIR / f"greencurve.{stamp}.db.gz"

    src_counts = table_counts(DB)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(BACKUP_DIR), suffix=".partial")
    os.close(tmp_fd)
    tmp = Path(tmp_name)

    try:
        # Rule 1: online backup API, not a file copy.
        src = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        dst = sqlite3.connect(str(tmp))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()

        # Rule 2: verify before it counts as a backup.
        v = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
        try:
            integrity = v.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            v.close()
        if integrity != "ok":
            add("FAIL", f"backup failed integrity_check ({integrity}) — discarded")
            tmp.unlink(missing_ok=True)
            return None

        bak_counts = table_counts(tmp)
        drift = [f"{t}: source={src_counts.get(t)} backup={bak_counts.get(t)}"
                 for t in CRITICAL
                 if t in src_counts and src_counts.get(t) != bak_counts.get(t)]
        if drift:
            add("FAIL", f"backup row counts differ from source ({'; '.join(drift)}) "
                        f"— discarded")
            tmp.unlink(missing_ok=True)
            return None

        with open(tmp, "rb") as fi, gzip.open(final, "wb", compresslevel=6) as fo:
            shutil.copyfileobj(fi, fo)
        tmp.unlink(missing_ok=True)

        raw = DB.stat().st_size
        gz = final.stat().st_size
        print(f"    source     : {raw/1e6:.1f} MB  ({sum(src_counts.values())} rows "
              f"across {len(src_counts)} tables)")
        print(f"    backup     : {final.name}  {gz/1e6:.1f} MB "
              f"({100*gz/raw:.0f}% of source)")
        print(f"    integrity  : ok")
        print(f"    row check  : {len(CRITICAL)} critical table(s) match")
        return final
    except Exception as e:
        add("FAIL", f"backup failed: {e.__class__.__name__}: {e}")
        tmp.unlink(missing_ok=True)
        return None


def verify_existing():
    """Re-open every stored backup and prove it still restores."""
    print("\n[2] VERIFY STORED BACKUPS")
    files = sorted(BACKUP_DIR.glob("greencurve.*.db.gz")) if BACKUP_DIR.exists() else []
    if not files:
        print("    none stored yet")
        return []
    ok, bad = [], []
    for f in files:
        tmp = None
        try:
            # mkstemp returns an OPEN descriptor; close it or Windows keeps the
            # file locked and the cleanup unlink raises WinError 32.
            fd, name = tempfile.mkstemp(suffix=".verify")
            os.close(fd)
            tmp = Path(name)
            with gzip.open(f, "rb") as fi, open(tmp, "wb") as fo:
                shutil.copyfileobj(fi, fo)
            c = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
            try:
                res = c.execute("PRAGMA integrity_check").fetchone()[0]
                n = c.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]
            finally:
                c.close()
            (ok if res == "ok" and n > 0 else bad).append(f)
        except Exception:
            bad.append(f)
        finally:
            if tmp:
                tmp.unlink(missing_ok=True)
    print(f"    verified restorable: {len(ok)}/{len(files)}")
    for f in bad:
        print(f"    CORRUPT: {f.name}")
        add("FAIL", f"stored backup {f.name} does not restore — it is not a backup")
    return ok


def prune():
    """Daily for DAILY_KEEP days, then monthly for MONTHLY_KEEP months."""
    print("\n[3] RETENTION")
    if not BACKUP_DIR.exists():
        print("    nothing to prune")
        return
    files = sorted(BACKUP_DIR.glob("greencurve.*.db.gz"))
    now = dt.datetime.now(dt.timezone.utc)
    keep, drop, seen_months = set(), [], set()
    for f in sorted(files, reverse=True):                  # newest first
        try:
            stamp = f.name.split(".")[1]
            when = dt.datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=dt.timezone.utc)
        except (IndexError, ValueError):
            keep.add(f)                                     # unparseable: never delete
            continue
        age_days = (now - when).days
        if age_days <= DAILY_KEEP:
            keep.add(f)
        elif age_days <= MONTHLY_KEEP * 31:
            key = (when.year, when.month)
            if key not in seen_months:                      # first (newest) of month
                seen_months.add(key)
                keep.add(f)
            else:
                drop.append(f)
        else:
            drop.append(f)
    # Never leave zero backups, whatever the arithmetic says.
    if not keep and files:
        keep.add(sorted(files)[-1])
        drop = [f for f in drop if f not in keep]
    freed = 0
    for f in drop:
        try:
            freed += f.stat().st_size
            f.unlink()
            print(f"    pruned {f.name}")
        except OSError as e:
            add("WARN", f"could not prune {f.name}: {e}")
    print(f"    kept {len(keep)}  pruned {len(drop)}  freed {freed/1e6:.1f} MB")
    if not keep:
        add("FAIL", "no backups remain after pruning")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not a.json:
        print("=" * 74)
        print(f"DATABASE BACKUP  {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M UTC}")
        print(f"db: {DB}")
        print("=" * 74)

    made = None
    if not a.verify_only:
        print("\n[1] SNAPSHOT")
        made = make_backup()
    ok = verify_existing()
    if not a.verify_only:
        prune()

    fails = [f for f in findings if f["level"] == "FAIL"]
    if not a.verify_only and not made:
        add("FAIL", "no verified backup was produced on this run")
        fails = [f for f in findings if f["level"] == "FAIL"]
    if not ok and not made:
        add("FAIL", "there is no verified restorable backup of greencurve.db")
        fails = [f for f in findings if f["level"] == "FAIL"]

    result = {
        "ran_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "backup": made.name if made else None,
        "verified_restorable": len(ok),
        "fail": len(fails),
        "findings": findings,
    }
    try:
        STATUS_OUT.parent.mkdir(parents=True, exist_ok=True)
        STATUS_OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except Exception:
        pass

    if a.json:
        print(json.dumps(result, indent=2))
    else:
        print("\n" + "=" * 74)
        print(f"VERDICT: {len(fails)} FAIL | verified restorable backups: {len(ok)}")
        for f in findings:
            print(f"  [{f['level']}] {f['message']}")
        print("=" * 74)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
