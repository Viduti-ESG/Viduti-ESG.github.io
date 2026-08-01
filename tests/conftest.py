"""Test scaffolding for the Green Curve API.

Design goals, in priority order:

1. **Never touch production.** Every test runs against a temporary SQLite file
   created per-session via `GC_DB_PATH`. The env var is set *before* `db` or
   `main` is imported, because `db.DB_PATH` is resolved at import time.
2. **Never bill Anthropic.** Nothing in this suite calls a model. The quota
   tests exercise the cap bookkeeping directly, which is where the money logic
   actually lives.
3. **Fast.** The ERP suite takes 15m33s and therefore gets skipped; a
   regression net that nobody runs is worth nothing.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SITE))

# Must be set before importing db/main -- DB_PATH is bound at import time.
_TMPDIR = tempfile.mkdtemp(prefix="gc_tests_")
os.environ["GC_DB_PATH"] = str(Path(_TMPDIR) / "test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-not-a-real-key")
os.environ.pop("GC_ENV", None)          # never let a test think it is production
os.environ.pop("GOOGLE_CLIENT_ID", None)

import db                                # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import main                              # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    db.init_db()
    yield
    shutil.rmtree(_TMPDIR, ignore_errors=True)


@pytest.fixture()
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    """The register/login limiter is per-IP and every test shares 'testclient'.

    Without this, tests pass or fail depending on how many ran before them --
    the worst kind of flake, because it looks like a real regression.
    """
    import auth_api
    with auth_api._login_rl_lock:
        auth_api._login_rl_counts.clear()
    yield


_counter = {"n": 0}


@pytest.fixture()
def new_user(client):
    """Register a fresh user and return (email, password, token, user_id)."""
    def _make(password: str = "correct-horse-battery"):
        _counter["n"] += 1
        email = f"user{_counter['n']}@example.com"
        r = client.post("/api/auth/register", json={
            "email": email, "name": "Test User", "org": "Test Org",
            "password": password,
        })
        assert r.status_code == 201, r.text
        body = r.json()
        return email, password, body["token"], body["user"]["id"]
    return _make


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
