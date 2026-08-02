"""
Regression tests for the DEPLOY path.

The seven scoring defects of 2 Aug 2026 were found by auditing the scoring
code. Three more were found only by running the deploy, and they lived in the
steps between "the artifact is correct" and "the user sees it":

  1. sync_cleaned_to_db.py wrote risk_breakdown but not esg_risk_score /
     risk_tier, so the API served 124 companies as "Low" beside a tier_basis
     saying they had been floored — a record that asserts and denies the
     same thing.
  2. clean_published.py never recomputed the summary counters, and the audit
     compared only total_companies, so three of four public counters were
     stale while the gate stayed green.
  3. build_embeddings.py defaults to bge-small while production runs bge-base.
     search_api.py reads the model out of the npz metadata, so rebuilding with
     the default would have swapped the search model with nothing erroring.

These are source-level guards. They are cheap, need no DB, no network and no
model, and they fail if any of the three regressions is reintroduced.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
SYNC = TOOLS / "sync_cleaned_to_db.py"
CLEAN = TOOLS / "clean_published.py"
AUDIT = TOOLS / "data_quality_audit.py"
EMBED = TOOLS / "build_embeddings.py"


def src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ── Bug 1: the DB sync must write the columns the page renders ──────────────

@pytest.mark.parametrize("column", ["esg_risk_score", "risk_tier",
                                    "risk_breakdown", "revenue_crore", "sector"])
def test_sync_writes_every_published_column(column):
    """A column the page shows but the sync skips = pages and API disagree."""
    m = re.search(r"UPDATE companies SET(.+?)WHERE", src(SYNC), re.S)
    assert m, "the UPDATE statement was not found in sync_cleaned_to_db.py"
    assert f"{column}=?" in m.group(1), (
        f"sync_cleaned_to_db.py does not write {column}; the DB-backed API will "
        f"serve a different value than the static pages")


def test_sync_gates_on_self_contradiction():
    """The sync must refuse to leave a Low tier next to a floored tier_basis."""
    s = src(SYNC)
    assert "floored_undisclosed_material_dimension" in s, \
        "sync_cleaned_to_db.py no longer checks for contradictory tiers"
    assert re.search(r"sys\.exit\(", s), \
        "the contradiction check must exit non-zero, not just print"


def test_sync_gates_on_drift_from_the_artifact():
    s = src(SYNC)
    assert "drift" in s.lower(), \
        "sync_cleaned_to_db.py no longer verifies the DB matches the artifact"


# ── Bug 2: the summary counters, and the gate that checks them ──────────────

@pytest.mark.parametrize("counter", ["total_companies", "high_risk_companies",
                                     "medium_risk_companies", "low_risk_companies"])
def test_clean_published_recomputes_every_counter(counter):
    assert f'summary["{counter}"]' in src(CLEAN), (
        f"clean_published.py does not recompute summary.{counter}; it will go "
        f"stale the next time scoring moves")


@pytest.mark.parametrize("counter", ["total_companies", "high_risk_companies",
                                     "medium_risk_companies", "low_risk_companies"])
def test_audit_checks_every_counter(counter):
    """Checking one of four counters passes three-quarters of the time by luck."""
    assert counter in src(AUDIT), \
        f"data_quality_audit.py does not verify summary.{counter}"


def test_audit_checks_tier_against_its_stated_basis():
    assert "floored_undisclosed_material_dimension" in src(AUDIT), \
        "the audit no longer fails on a Low tier that its own basis contradicts"


def test_clean_published_does_not_borrow_refresh_static_schema():
    """refresh_static.py emits `high`, the frontend reads `high_risk_companies`."""
    s = src(CLEAN)
    assert 'summary["high"]' not in s and "summary['high']" not in s, \
        "clean_published.py is writing refresh_static.py's schema; the frontend " \
        "reads *_risk_companies and would silently show nothing"


# ── Bug 3: a data refresh must not change the search model ──────────────────

def test_embeddings_model_defaults_to_the_existing_index():
    """--model must default to None so the existing index's model is inherited."""
    m = re.search(r'add_argument\(\s*["\']--model["\'](.*?)\)', src(EMBED), re.S)
    assert m, "--model argument not found in build_embeddings.py"
    assert re.search(r"default\s*=\s*None", m.group(1)), (
        "build_embeddings.py --model has a hardcoded default again; a routine "
        "rebuild will silently replace the production index with a different model")


def test_embeddings_refuses_a_silent_model_change():
    s = src(EMBED)
    assert "--allow-model-change" in s, \
        "the explicit opt-in for changing the embedding model is gone"
    assert "refusing to replace an index" in s, \
        "build_embeddings.py no longer refuses a model swap"
    # Anchor on the guard branch itself, not the --help text mentioning the flag.
    guard = re.search(r"if not args\.allow_model_change:([\s\S]*?)\n(?=\s{0,8}\S)", s)
    assert guard, "the `if not args.allow_model_change:` branch is gone"
    assert "return 1" in guard.group(1), \
        "the model-change guard must return non-zero, not just warn"


def test_embeddings_reads_existing_metadata_before_building():
    s = src(EMBED)
    assert "existing_model" in s, \
        "build_embeddings.py no longer inspects the existing index's model"


def test_search_api_still_takes_its_model_from_the_index():
    """The guard above only matters because the server trusts this metadata."""
    api = ROOT / "search_api.py"
    if not api.exists():
        pytest.skip("search_api.py not present")
    assert re.search(r'TextEmbedding\(\s*model_name\s*=\s*meta\[', src(api)), (
        "search_api.py no longer reads the model from the npz metadata — "
        "re-check whether build_embeddings.py's guard is still the right shape")
