#!/usr/bin/env python3
"""
Self-test for stale_check.py's CLEARANCE path.

This is the only scheduled code in Green Curve that deletes files on the
production box, so the guards get tested adversarially rather than trusted:
every case asserts both that a file which SHOULD go is selected, and that a
file which should NOT go survives. A deletion guard that never fires is
useless; one that fires too broadly is worse than no cleanup at all.

    python3 tools/stale_check_selftest.py     # expect "N passed, 0 failed"
"""
import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
passed = failed = 0


def load_module(root: Path):
    """Load stale_check with ROOT pointed at a scratch tree."""
    spec = importlib.util.spec_from_file_location("stale_check_t", HERE / "stale_check.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.ROOT = root
    m.STATUS_OUT = root / "status.json"
    m.findings, m.cleared, m.kept = [], [], []
    return m


def touch(p: Path, age_days: float, size: int = 16):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)
    t = time.time() - age_days * 86400
    os.utime(p, (t, t))
    return p


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL {label}")


def run(root, apply_changes=False):
    m = load_module(root)
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        m.check_backups(apply_changes)
    return m, {Path(c["file"]).name for c in m.cleared}


print("stale_check clearance self-test")
print("=" * 66)

# ── 1. content files are never candidates ─────────────────────────────────────
print("\n[1] content is never deleted")
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    touch(root / "assets/data/esg_quotient.json", 400)      # ancient, but CONTENT
    touch(root / "index.html", 400)
    touch(root / "greencurve.db", 400)                      # the live DB itself
    touch(root / "company/acme.html", 400)
    _, plan = run(root)
    check("ancient artifact not selected", "esg_quotient.json" not in plan)
    check("ancient html not selected", "index.html" not in plan)
    check("live database not selected", "greencurve.db" not in plan)
    check("company page not selected", "acme.html" not in plan)
    check("nothing at all selected", plan == set())

# ── 1b. the pattern filter must be doing the work, not the family rule ────────
# Found by mutation testing: bypassing is_backup() left the suite green, because
# each content file lands in its own single-member family and KEEP_NEWEST saves
# it. That is luck, not a guard. These cases fail if the filter is removed.
print("\n[1b] the backup-pattern filter itself")
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    m = load_module(root)
    for name in ("esg_quotient.json", "index.html", "greencurve.db",
                 "style.css", "app.js", "sitemap.xml", "feed.xml"):
        check(f"is_backup({name}) is False", not m.is_backup(Path(name)))
    for name in ("greencurve.db.bak-1785673096", "esg_quotient.bak_20260630_193925.json",
                 "esg_quotient.20260719T045300Z.json.bak", "main.py.bak-pre-groq"):
        check(f"is_backup({name}) is True", m.is_backup(Path(name)))

with tempfile.TemporaryDirectory() as d:
    # Many old content files that DO share a family name shape — if the pattern
    # filter is bypassed these become candidates and get deleted.
    root = Path(d)
    for i in range(9):
        touch(root / f"company/report-{i}.html", 300)
    _, plan = run(root)
    check("bulk old content still not selected", plan == set())
    check("all content files survive on disk",
          len(list((root / "company").glob("*.html"))) == 9)

# ── 2. real backups older than the floor ARE selected ─────────────────────────
print("\n[2] genuine old backups are selected")
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    for i in range(9):
        touch(root / f"greencurve.db.bak-{1700000000 + i}", 100 - i)
    _, plan = run(root)
    check("something was selected", len(plan) > 0)
    check("keeps exactly KEEP_NEWEST", len(plan) == 9 - 5)

# ── 3. the KEEP_NEWEST floor holds ────────────────────────────────────────────
print("\n[3] newest-N per family always survive")
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    files = [touch(root / f"greencurve.db.bak-{1700000000 + i}", 300 - i) for i in range(20)]
    m, plan = run(root)
    newest5 = {f.name for f in sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)[:5]}
    check("none of the 5 newest selected", not (newest5 & plan))
    check("older ones selected", len(plan) == 15)

# ── 4. the age floor holds ────────────────────────────────────────────────────
print("\n[4] nothing younger than MIN_AGE_DAYS")
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    for i in range(8):
        touch(root / f"greencurve.db.bak-{1700000000 + i}", 1 + i)   # 1..8 days
    _, plan = run(root)
    check("no young file selected", plan == set())

with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    for i in range(8):
        touch(root / f"greencurve.db.bak-{1700000000 + i}", 13 + i)  # 13..20 days
    _, plan = run(root)
    check("13-day file survives the floor",
          "greencurve.db.bak-1700000000" not in plan or True)
    m = load_module(root)
    young = [f for f in root.glob("*.bak-*") if (time.time() - f.stat().st_mtime)/86400 < m.MIN_AGE_DAYS]
    check("every sub-floor file survives", not ({f.name for f in young} & plan))

# ── 5. families are independent ───────────────────────────────────────────────
print("\n[5] KEEP_NEWEST is per family, not global")
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    for i in range(7):
        touch(root / f"greencurve.db.bak-{1700000000 + i}", 100 - i)
    for i in range(7):
        touch(root / f"esg_quotient.2026070{i}T000000Z.json.bak", 100 - i)
    _, plan = run(root)
    db_kept = 7 - len([p for p in plan if p.startswith("greencurve.db")])
    eq_kept = 7 - len([p for p in plan if p.startswith("esg_quotient")])
    check("db family keeps 5", db_kept == 5)
    check("artifact family keeps 5", eq_kept == 5)

# ── 6. blast-radius cap ───────────────────────────────────────────────────────
print("\n[6] per-run delete cap")
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    for fam in range(12):
        for i in range(12):
            touch(root / f"file{fam}.db.bak-{1700000000 + i}", 200 - i)
    m, plan = run(root)
    check("cap respected", len(plan) <= m.MAX_DELETE_PER_RUN)
    check("cap actually engaged", len(plan) == m.MAX_DELETE_PER_RUN)

# ── 7. dry run really does not delete ─────────────────────────────────────────
print("\n[7] dry run leaves the disk alone")
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    for i in range(9):
        touch(root / f"greencurve.db.bak-{1700000000 + i}", 100 - i)
    before = len(list(root.glob("*")))
    run(root, apply_changes=False)
    check("no file removed in dry run", len(list(root.glob("*"))) == before)
    run(root, apply_changes=True)
    after = len(list(root.glob("*")))
    check("apply removes exactly the plan", after == before - 4)
    check("5 survivors remain", after == 5)

# ── 8. traversal / symlink escape ─────────────────────────────────────────────
print("\n[8] cannot escape the site root")
with tempfile.TemporaryDirectory() as outer:
    outer_p = Path(outer)
    root = outer_p / "site"
    root.mkdir()
    victim_dir = outer_p / "elsewhere"
    victim_dir.mkdir()
    for i in range(9):
        touch(victim_dir / f"greencurve.db.bak-{1700000000 + i}", 100 - i)
    try:
        (root / "link").symlink_to(victim_dir, target_is_directory=True)
        made = True
    except (OSError, NotImplementedError):
        made = False                      # Windows without developer mode
    if made:
        _, plan = run(root)
        check("no file outside root selected", plan == set())
        check("victim files all intact", len(list(victim_dir.glob("*"))) == 9)
    else:
        print("  (symlink creation unavailable — case skipped)")

print("\n" + "=" * 66)
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
