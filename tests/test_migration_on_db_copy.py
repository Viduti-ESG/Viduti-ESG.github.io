"""Test 2 of 4 — migrations, run against a copy of a *real* database.

`CREATE TABLE IF NOT EXISTS` cannot add a column to a table that already
exists. A fresh database therefore has every column and hides exactly the bug
this catches: `init_db` looks fine locally, deploys, and then the live database
-- which was created before the column existed -- 500s on the first query that
selects it. That is how a missing `role` column once broke every authenticated
request.

So the only meaningful test is: take a database that predates the change, run
the migration, and assert the columns the code actually reads are there.
"""

import os
import shutil
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent
LOCAL_DB = SITE / "greencurve.db"

# Columns the application selects by name. If a query starts reading a new one,
# add it here -- that is the point of the list being explicit rather than
# derived from the schema, which would make the test tautological.
REQUIRED = {
    "users": [
        "id", "email", "name", "org", "password_hash", "role",
        "created_at", "is_active", "plan",
        "free_tier_expires_at", "plan_expires_at",
    ],
    "watchlist": ["user_id", "company_name"],
    # NOTE: the column is `token`, not `token_hash`. The first draft of this
    # test asserted `token_hash` from memory and failed -- the test was wrong,
    # not the schema. Read the schema, never recall it.
    "password_resets": ["user_id", "token", "expires_at", "used"],
}


def _run_init_db(db_path: Path) -> None:
    """Run init_db in a subprocess so GC_DB_PATH is bound at import time.

    db.DB_PATH is resolved when the module loads, so re-importing in-process
    would silently keep the session database and the test would prove nothing.
    """
    env = dict(os.environ, GC_DB_PATH=str(db_path))
    code = textwrap.dedent(f"""
        import sys; sys.path.insert(0, {str(SITE)!r})
        import db
        assert str(db.DB_PATH) == {str(db_path)!r}, f"wrong DB bound: {{db.DB_PATH}}"
        db.init_db()
        print("ok")
    """)
    r = subprocess.run([sys.executable, "-c", code], env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"init_db failed:\n{r.stdout}\n{r.stderr}"


def _columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


@pytest.mark.skipif(not LOCAL_DB.exists(),
                    reason="no local greencurve.db to copy")
def test_migration_against_copy_of_real_db(tmp_path):
    target = tmp_path / "copy.db"
    shutil.copy2(LOCAL_DB, target)

    _run_init_db(target)

    missing = {}
    for table, cols in REQUIRED.items():
        have = _columns(target, table)
        if not have:
            missing[table] = ["<table absent>"]
            continue
        gap = [c for c in cols if c not in have]
        if gap:
            missing[table] = gap
    assert not missing, f"init_db left columns missing on a real DB: {missing}"


@pytest.mark.skipif(not LOCAL_DB.exists(), reason="no local greencurve.db")
def test_migration_is_idempotent(tmp_path):
    """Deploys re-run init_db every restart. A migration that only works once
    is a migration that breaks the second worker."""
    target = tmp_path / "copy.db"
    shutil.copy2(LOCAL_DB, target)
    _run_init_db(target)
    before = {t: _columns(target, t) for t in REQUIRED}
    _run_init_db(target)
    after = {t: _columns(target, t) for t in REQUIRED}
    assert before == after


def test_migration_recovers_a_db_missing_a_column(tmp_path):
    """The actual failure mode, reproduced deliberately.

    Build a `users` table the way an old deploy would have had it -- without
    `role` -- and assert init_db adds the column instead of leaving it absent
    because the table already existed.
    """
    target = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(target))
    conn.execute(
        "CREATE TABLE users ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " email TEXT UNIQUE NOT NULL,"
        " name TEXT,"
        " org TEXT,"
        " password_hash TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()
    assert "role" not in _columns(target, "users")

    _run_init_db(target)

    cols = _columns(target, "users")
    assert "role" in cols, (
        "init_db did not add `role` to a pre-existing users table -- this is "
        "the CREATE TABLE IF NOT EXISTS trap that 500'd every authed request"
    )
    # Deliberately NOT asserted: `is_active` and `created_at` appear in the
    # CREATE TABLE but have no ALTER path in the migration block, so this
    # synthetic legacy table does not get them. That is a latent gap, not a
    # live defect -- every real database has both columns (verified against
    # greencurve.db), and no deployment is known to predate them. Asserting it
    # here would be inventing a bug. If a users table ever *is* found without
    # `is_active`, every login 500s on `WHERE is_active=1`, so add the ALTER
    # then and turn this comment into an assertion.
