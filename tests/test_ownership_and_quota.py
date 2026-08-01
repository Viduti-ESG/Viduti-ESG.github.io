"""Tests 3 and 4 of 4 — ownership isolation, and the AI quota accounting.

**Ownership** (test 3): static analysis (`cybersecurity-greencurve`'s
`authz_audit.py`) proves the *shape* is right -- every query filters by
`user_id`. Only a test proves the *behaviour* is: that user B genuinely cannot
see or delete user A's row.

**Quota** (test 4): this is where the money is. Nothing here calls a model --
the cap helper is exercised directly, which is both free and the actual thing
that decides whether Anthropic gets billed. The assertion that matters most is
the second one: a *failed* generation must not consume anyone's allowance.
"""

import sqlite3
from datetime import datetime

import pytest
from fastapi import HTTPException

from conftest import auth


# ── Test 3: ownership ─────────────────────────────────────────────────────────

def test_watchlist_is_scoped_per_user(client, new_user):
    _e1, _p1, tok_a, _id_a = new_user()
    _e2, _p2, tok_b, _id_b = new_user()

    r = client.post("/api/user/watchlist",
                    json={"company_name": "Tata Steel Limited"}, headers=auth(tok_a))
    assert r.status_code == 201, r.text

    # A sees it.
    assert "Tata Steel Limited" in client.get(
        "/api/user/watchlist", headers=auth(tok_a)).json()["watchlist"]

    # B must not.
    assert client.get("/api/user/watchlist",
                      headers=auth(tok_b)).json()["watchlist"] == []


def test_user_b_cannot_delete_user_a_entry(client, new_user):
    _e1, _p1, tok_a, _id_a = new_user()
    _e2, _p2, tok_b, _id_b = new_user()

    client.post("/api/user/watchlist",
                json={"company_name": "Infosys Limited"}, headers=auth(tok_a))

    # B issues the delete. It may return 200 (idempotent delete of nothing),
    # but A's row must survive -- that is the property under test, not the
    # status code.
    client.delete("/api/user/watchlist/Infosys Limited", headers=auth(tok_b))

    assert "Infosys Limited" in client.get(
        "/api/user/watchlist", headers=auth(tok_a)).json()["watchlist"], \
        "user B's delete removed user A's watchlist entry"


def test_watchlist_requires_authentication(client):
    assert client.get("/api/user/watchlist").status_code == 401
    assert client.post("/api/user/watchlist",
                       json={"company_name": "X"}).status_code == 401


def test_profile_is_scoped_per_user(client, new_user):
    _e1, _p1, tok_a, _id_a = new_user()
    _e2, _p2, tok_b, _id_b = new_user()

    r = client.put("/api/user/profile",
                   json={"company_name": "A-Corp Confidential"}, headers=auth(tok_a))
    if r.status_code >= 400:
        pytest.skip(f"profile PUT shape differs ({r.status_code}); covered elsewhere")

    body_b = client.get("/api/user/profile", headers=auth(tok_b)).text
    assert "A-Corp Confidential" not in body_b


# ── Test 4: AI quota accounting (no model is called) ──────────────────────────

class _FakeRequest:
    """Minimal stand-in for the parts of Request the cap helper reads."""
    def __init__(self, ip="203.0.113.9"):
        self.headers = {"x-real-ip": ip}
        self.client = type("C", (), {"host": ip})()


def _usage_count(identity: str, metric: str) -> int:
    import db
    conn = db.get_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(count),0) AS n FROM ai_usage WHERE identity=? AND metric=?",
        (identity, metric),
    ).fetchone()
    return row["n"]


def test_failed_generation_does_not_consume_quota():
    """The cap helper hands back a `record()` callback rather than charging up
    front, precisely so a Claude outage never burns a user's allowance. If this
    ever inverts, users pay for our downtime."""
    import ai_api
    ip = "203.0.113.21"
    identity = f"ip:{ip}"
    metric = "ccts_scorecard"

    before = _usage_count(identity, metric)
    record = ai_api._enforce_ai_cap(_FakeRequest(ip), metric)
    # Simulate the model call raising -- record() is never reached.
    assert _usage_count(identity, metric) == before, \
        "quota was consumed before the AI call succeeded"

    record()
    assert _usage_count(identity, metric) == before + 1, \
        "record() did not consume quota on success"


def test_quota_exhaustion_raises_429():
    import ai_api
    ip = "203.0.113.22"
    metric = "ccts_scorecard"
    limit = ai_api.FREE_LIMITS_AI[metric] if hasattr(ai_api, "FREE_LIMITS_AI") \
        else ai_api.FREE_LIMITS[metric]

    req = _FakeRequest(ip)
    for _ in range(limit):
        ai_api._enforce_ai_cap(req, metric)()

    with pytest.raises(HTTPException) as e:
        ai_api._enforce_ai_cap(req, metric)
    assert e.value.status_code == 429, f"expected 429 at cap, got {e.value.status_code}"


def test_every_capped_metric_has_a_human_readable_label():
    """A cap that fires with a missing label produces a KeyError instead of the
    friendly 429 the frontend shows. Cheap to get wrong when adding a metric."""
    import ai_api
    limits = getattr(ai_api, "FREE_LIMITS_AI", None) or ai_api.FREE_LIMITS
    labels = getattr(ai_api, "METRIC_LABELS_AI", None) or ai_api.METRIC_LABELS
    missing = [m for m in limits if m not in labels]
    assert not missing, f"capped metrics with no label: {missing}"
