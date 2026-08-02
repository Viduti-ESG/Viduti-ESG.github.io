#!/usr/bin/env python3
"""
Green Curve — DAILY PRODUCT SYNC CHECK (read-only).

Answers one question every morning: are the four copies of Green Curve's data
still the same data?

    published artifact  ->  esg_quotient.json   (what the pipeline produced)
    company pages       ->  company/*.html      (what a visitor reads)
    database            ->  greencurve.db       (what /api/esg/* serves)
    live API            ->  127.0.0.1:8000      (what the running process holds)

They drift independently and every past incident lived in a gap between two of
them: pages cleaned but the DB not synced; the DB synced but the service not
restarted; a tier column skipped so a page said "Low" while the API said "High".
Nothing was watching, so the gap was always found by a person, late.

READ-ONLY BY DESIGN. It reports and exits non-zero; it never edits data. Fixing
a sync gap means re-running the pipeline, which is a decision, not a cron job.

    python3 tools/sync_check.py                 # human-readable, exit 1 on FAIL
    python3 tools/sync_check.py --json          # machine-readable
    python3 tools/sync_check.py --report        # never exit 1

Stdlib only.
"""
import argparse
import collections
import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("/var/www/greencurve")
if not ROOT.exists():                       # laptop / dev
    ROOT = Path(r"c:/Viduti/esg-site")

ARTIFACT = ROOT / "assets/data/esg_quotient.json"
PAGES = ROOT / "company"
DB = ROOT / "greencurve.db"
API = "http://127.0.0.1:8000"
STATUS_OUT = Path("/var/log/greencurve/sync_check.json")

# A sample is enough to prove the API is serving the current artifact; pulling
# all 1,221 rows through the API on every run is wasteful and slower than the
# thing it is checking.
API_SAMPLE = 25
NON_COMPANY_PAGES = {"index", "sectors"}

findings = []


def add(level, check, msg):
    findings.append({"level": level, "check": check, "message": msg})


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")


def load_artifact():
    doc = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    return doc, doc.get("companies", [])


# ── [1] ARTIFACT ↔ PAGES ──────────────────────────────────────────────────────
def check_pages(recs):
    print("\n[1] ARTIFACT <-> COMPANY PAGES")
    if not PAGES.exists():
        add("FAIL", "pages", f"no company page directory at {PAGES}")
        print(f"    MISSING: {PAGES}")
        return
    have = {p.stem for p in PAGES.glob("*.html")} - NON_COMPANY_PAGES
    want = {slug(r.get("company_name")) for r in recs}
    missing, orphan = want - have, have - want
    print(f"    records={len(recs)}  pages={len(have)}  missing={len(missing)}  orphan={len(orphan)}")
    if missing:
        add("FAIL", "pages",
            f"{len(missing)} published record(s) have no page — the data says the "
            f"company exists and the site 404s it (e.g. {sorted(missing)[:3]})")
    if orphan:
        add("FAIL", "pages",
            f"{len(orphan)} page(s) have no record — they serve whatever data they "
            f"were last generated with (e.g. {sorted(orphan)[:3]})")
    if not missing and not orphan:
        print("    [OK] every record has a page and every page has a record")


# ── [2] ARTIFACT ↔ DATABASE ───────────────────────────────────────────────────
def check_db(recs):
    print("\n[2] ARTIFACT <-> DATABASE")
    if not DB.exists():
        add("WARN", "db", f"database check SKIPPED: no database at {DB}")
        print(f"    SKIPPED — no database at {DB}")
        return
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = {r[0]: r for r in conn.execute(
            "SELECT company_name, esg_risk_score, risk_tier, cin FROM companies")}
    finally:
        conn.close()
    art = {r["company_name"]: r for r in recs}
    only_art = sorted(set(art) - set(rows))
    only_db = sorted(set(rows) - set(art))
    drift = []
    for name, r in art.items():
        row = rows.get(name)
        if not row:
            continue
        if row[1] != r.get("esg_risk_score") or row[2] != r.get("risk_tier"):
            drift.append(f"{name}: db=({row[1]},{row[2]}) artifact="
                         f"({r.get('esg_risk_score')},{r.get('risk_tier')})")
        if (row[3] or "") != (r.get("cin") or ""):
            drift.append(f"{name}: cin db={row[3]!r} artifact={r.get('cin')!r}")
    print(f"    artifact={len(art)}  db={len(rows)}  artifact-only={len(only_art)}  "
          f"db-only={len(only_db)}  value drift={len(drift)}")
    if only_art:
        add("FAIL", "db",
            f"{len(only_art)} published company(ies) are not in the database, so "
            f"/api/esg/* cannot serve them (e.g. {only_art[:3]}). "
            f"sync_cleaned_to_db.py is UPDATE-only and exits 0 on unmatched rows.")
    if only_db:
        add("WARN", "db",
            f"{len(only_db)} database row(s) are no longer published; the API can "
            f"still serve them (e.g. {only_db[:3]})")
    for d in drift[:5]:
        print(f"    DRIFT {d}")
    if drift:
        add("FAIL", "db",
            f"{len(drift)} row(s) disagree with the artifact on score, tier or CIN — "
            f"the page and the API are showing different things for the same company")
    if not (only_art or only_db or drift):
        print("    [OK] database matches the published artifact")


# ── [3] LIVE API ↔ ARTIFACT ───────────────────────────────────────────────────
def fetch(path, timeout=20):
    req = urllib.request.Request(API + path, headers={"User-Agent": "gc-sync-check"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def check_api(recs, doc_ref=None):
    print("\n[3] LIVE API <-> ARTIFACT")
    try:
        code, _ = fetch("/health", timeout=10)
        print(f"    /health -> {code}")
        if code != 200:
            add("FAIL", "api", f"/health returned {code}")
            return
    except Exception as e:
        add("FAIL", "api", f"the API is not answering on {API} ({e.__class__.__name__}) — "
                           f"the site's static pages may still look fine while every "
                           f"dynamic feature is down")
        print(f"    UNREACHABLE: {e}")
        return
    try:
        code, body = fetch("/api/esg/data?limit=5000", timeout=60)
        payload = json.loads(body)
    except Exception as e:
        add("WARN", "api", f"/api/esg/data could not be read ({e.__class__.__name__}); "
                           f"artifact-vs-API comparison skipped")
        print(f"    /api/esg/data unreadable: {e}")
        return
    served = payload.get("companies") if isinstance(payload, dict) else payload
    if not isinstance(served, list):
        add("WARN", "api", "/api/esg/data returned an unexpected shape; comparison skipped")
        return
    by_name = {r.get("company_name"): r for r in served if isinstance(r, dict)}
    print(f"    API rows={len(by_name)}  artifact rows={len(recs)}")
    if abs(len(by_name) - len(recs)) > 0:
        add("FAIL", "api",
            f"the API serves {len(by_name)} companies, the artifact has {len(recs)} — "
            f"a sync ran without a restart, or the sync did not cover every row")
    # The header block is served from esg_meta, NOT computed from the rows, so a
    # per-company comparison passes while the headline numbers are nonsense.
    # Missed on the first version of this check: the API was serving
    # "1227 companies / 36 High / 1190 Medium / 1 Low" against an artifact of
    # 1221 / 418 / 530 / 273, and every sampled company still matched.
    if isinstance(payload, dict):
        art_sum = (doc_ref.get("summary") or {}) if doc_ref else {}
        api_sum = payload.get("summary") or {}
        bad = {k: (api_sum.get(k), art_sum.get(k))
               for k in art_sum if api_sum.get(k) != art_sum.get(k)}
        for k in ("generated_at", "data_as_of"):
            if doc_ref and payload.get(k) != doc_ref.get(k):
                bad[k] = (payload.get(k), doc_ref.get(k))
        print(f"    header block: {'matches artifact' if not bad else 'DRIFTED'}")
        for k, (got, want) in list(bad.items())[:6]:
            print(f"      {k}: api={got!r} artifact={want!r}")
        if bad:
            add("FAIL", "api",
                f"{len(bad)} header field(s) differ between the API and the artifact "
                f"({', '.join(list(bad)[:4])}). The API reads esg_meta, which is only "
                f"written by sync_cleaned_to_db.py — re-run it, then restart.")

    mismatch = []
    for r in recs[:API_SAMPLE]:
        s = by_name.get(r["company_name"])
        if not s:
            mismatch.append(f"{r['company_name']}: absent from API")
        elif s.get("risk_tier") != r.get("risk_tier"):
            mismatch.append(f"{r['company_name']}: API tier={s.get('risk_tier')} "
                            f"artifact={r.get('risk_tier')}")
    for m in mismatch[:5]:
        print(f"    MISMATCH {m}")
    if mismatch:
        add("FAIL", "api",
            f"{len(mismatch)} of the first {API_SAMPLE} companies differ between the "
            f"live API and the artifact — restart greencurve-api after a DB sync")
    else:
        print(f"    [OK] sampled {min(API_SAMPLE, len(recs))} companies, API matches artifact")


# ── [4] SERVICES ──────────────────────────────────────────────────────────────
def check_services():
    print("\n[4] SERVICES")
    for unit in ("greencurve-api", "gcai"):
        try:
            out = subprocess.run(["systemctl", "is-active", unit],
                                 capture_output=True, text=True, timeout=15)
            state = out.stdout.strip() or out.stderr.strip()
        except Exception as e:
            state = f"unknown ({e.__class__.__name__})"
        print(f"    {unit:18} {state}")
        if state != "active":
            add("FAIL", "services", f"systemd unit {unit} is {state}")


# ── [5] GIT: DEPLOYED vs ORIGIN ───────────────────────────────────────────────
def check_git():
    print("\n[5] GIT (deployed tree vs origin)")
    def git(*a):
        return subprocess.run(["git", "-C", str(ROOT), *a],
                              capture_output=True, text=True, timeout=90)
    try:
        git("fetch", "origin", "main", "-q")
        behind = git("rev-list", "--count", "HEAD..origin/main").stdout.strip() or "?"
        head = git("log", "--oneline", "-1").stdout.strip()
        drift = git("diff", "--ignore-all-space", "--name-only", "HEAD").stdout.split()
    except Exception as e:
        add("WARN", "git", f"git check skipped ({e.__class__.__name__})")
        print(f"    skipped: {e}")
        return
    print(f"    HEAD: {head}")
    print(f"    commits behind origin/main: {behind}")
    print(f"    tracked files differing from HEAD (ignoring whitespace): {len(drift)}")
    if behind.isdigit() and int(behind) > 0:
        add("WARN", "git",
            f"the deployed tree is {behind} commit(s) behind origin/main — pushed work "
            f"is not live. Most are usually automated BRSR-URL commits; check before "
            f"assuming a fix shipped.")
    if len(drift) > 50:
        add("WARN", "git",
            f"{len(drift)} tracked files differ from HEAD beyond whitespace — a "
            f"`git pull` will conflict; deploy surgically with "
            f"`git checkout origin/main -- <paths>`")


# ── [6] SELF-CONSISTENCY + IDENTITY REGRESSION GUARD ──────────────────────────
CIN_RE = re.compile(r"^([LU])(\d{5})([A-Z]{2})(\d{4})([A-Z]{3})(\d{6})$")
CIN_CLASSES = {"PLC", "PTC", "FLC", "GAP", "SGC", "NPL", "GAT", "OPC", "ULL",
               "ULT", "FTC", "GOI"}


def check_internal(doc, recs):
    print("\n[6] ARTIFACT SELF-CONSISTENCY + IDENTITY")
    summary = doc.get("summary", {})
    tiers = collections.Counter((r.get("risk_tier") or "") for r in recs)
    for key, claimed, actual in (
        ("total_companies", summary.get("total_companies"), len(recs)),
        ("high_risk_companies", summary.get("high_risk_companies"), tiers.get("High", 0)),
        ("medium_risk_companies", summary.get("medium_risk_companies"), tiers.get("Medium", 0)),
        ("low_risk_companies", summary.get("low_risk_companies"), tiers.get("Low", 0)),
    ):
        ok = claimed == actual
        print(f"    {key:24} summary={claimed} actual={actual} [{'OK' if ok else 'STALE'}]")
        if not ok:
            add("FAIL", "counters",
                f"summary.{key} says {claimed}, the array holds {actual} — the "
                f"published counter is stale")

    # Regression guard for the 2026-08-02 CIN-join incident.
    counts = collections.Counter((r.get("cin") or "").strip() for r in recs if r.get("cin"))
    dupes = {c: n for c, n in counts.items() if n > 1}
    bad = []
    for c in counts:
        m = CIN_RE.match(c)
        if not m or not (1850 <= int(m.group(4)) <= dt.date.today().year) \
                or m.group(5) not in CIN_CLASSES:
            bad.append(c)
    print(f"    CINs: distinct={len(counts)}  duplicated={len(dupes)}  malformed={len(bad)}")
    if dupes:
        add("FAIL", "identity",
            f"{len(dupes)} CIN(s) are shared by more than one company ({list(dupes)[:2]}). "
            f"CIN is used as a join key upstream — a shared CIN publishes one company's "
            f"ESG content on another's page. Run tools/fix_cins.py.")
    if bad:
        add("FAIL", "identity",
            f"{len(bad)} published CIN(s) cannot be real ({bad[:2]}). Read the company's "
            f"raw BRSR filing before calling it a pipeline bug — filers submit "
            f"placeholders — then blank it with tools/fix_cins.py.")
    if not dupes and not bad:
        print("    [OK] no duplicate or malformed CINs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--report", action="store_true", help="never exit 1")
    a = ap.parse_args()

    if not a.json:
        print("=" * 74)
        print(f"PRODUCT SYNC CHECK  {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M UTC}")
        print(f"root: {ROOT}")
        print("=" * 74)

    try:
        doc, recs = load_artifact()
    except Exception as e:
        add("FAIL", "artifact", f"the published artifact could not be read: {e}")
        recs, doc = [], {}

    if recs:
        check_pages(recs)
        check_db(recs)
        check_api(recs, doc)
    check_services()
    check_git()
    if recs:
        check_internal(doc, recs)

    fails = [f for f in findings if f["level"] == "FAIL"]
    warns = [f for f in findings if f["level"] == "WARN"]
    result = {
        "ran_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "fail": len(fails), "warn": len(warns), "findings": findings,
    }
    try:
        STATUS_OUT.parent.mkdir(parents=True, exist_ok=True)
        STATUS_OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except Exception:
        pass                                    # never let reporting break the check

    if a.json:
        print(json.dumps(result, indent=2))
    else:
        print("\n" + "=" * 74)
        print(f"VERDICT: {len(fails)} FAIL, {len(warns)} WARN")
        for f in findings:
            print(f"  [{f['level']}] {f['check']}: {f['message']}")
        print("=" * 74)
    return 1 if (fails and not a.report) else 0


if __name__ == "__main__":
    sys.exit(main())
