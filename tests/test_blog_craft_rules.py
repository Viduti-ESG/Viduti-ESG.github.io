"""Craft-rule tests for the blog writer (tools/climate_agent.py).

Context: measuring the 179-post live corpus on 2026-08-01 found a system with a
strict truth gate and no craft gate at all -- median title 122 characters
against a ~60-character render width, median lede 36 words, 47% of ledes
opening by crediting the source instead of stating the news, and 28% carrying a
bare URL inside the first sentence.

Two things were changed, and this file guards both:

  1. NEWS_SYSTEM_PROMPT now states the rules. Prompt text is the only place
     these constraints are expressed to the model, so a silent edit that drops
     one would quietly restore the defect. These tests pin the constraints.
  2. craft_warnings() reports breaches at publish time. It is deliberately
     NON-BLOCKING -- craft is not truth, and a 74-character title is not worth
     spending the day's budget to suppress. Refusal stays reserved for
     fabrication (test_blog_review_gate.py).

No model is called, so this suite is free.
"""

import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SITE / "tools"))

import climate_agent as ca  # noqa: E402


GOOD_POST = {
    "title": "India's index funds face a EUR100bn benchmark shift",
    "sections": {
        "what_changed": (
            "Nordea expanded its Paris-aligned benchmark range on 31 July. "
            "ESG Today first reported the change. Indian index funds tracking "
            "European benchmarks inherit the methodology.\n"
            "Source: https://www.esgtoday.com/some-article/"
        ),
    },
}


# ── the prompt must actually carry the rules ──────────────────────────────────
def test_prompt_states_the_title_budget():
    p = ca.NEWS_SYSTEM_PROMPT
    assert "70 characters" in p, "title character limit dropped from the prompt"
    assert "60 characters" in p, "India-hook truncation rule dropped from the prompt"


def test_prompt_demands_a_news_first_lede():
    p = ca.NEWS_SYSTEM_PROMPT.lower()
    assert "what changed" in p
    assert "never open with who reported it" in p, "lede-first rule dropped"


def test_prompt_forbids_bare_urls_in_prose():
    p = ca.NEWS_SYSTEM_PROMPT
    assert "NEVER paste a bare URL inside a sentence" in p, "URL placement rule dropped"
    assert "Source: " in p, "the Source: line convention dropped"


def test_prompt_carries_the_banned_word_list():
    p = ca.NEWS_SYSTEM_PROMPT.lower()
    for word in ("significant", "robust", "landmark", "holistic", "ecosystem"):
        assert word in p, f"banned word {word!r} dropped from the prompt"


def test_prompt_no_longer_gives_one_attribution_example():
    """79 of 179 posts opened with the word 'Reporting' because the prompt gave
    exactly one example of attribution and the model read it as the format.
    Never give a single example of something that should vary."""
    assert "'Reporting by ESG Today...'" not in ca.NEWS_SYSTEM_PROMPT, (
        "the single attribution example is back; it hardened into a corpus-wide tic"
    )


def test_prompt_asks_for_sentence_rhythm():
    assert "median sentence under 24 words" in ca.NEWS_SYSTEM_PROMPT


# ── craft_warnings must catch each breach ────────────────────────────────────
def _warn(post):
    return " | ".join(ca.craft_warnings(post))


def test_clean_post_produces_no_warnings():
    assert ca.craft_warnings(GOOD_POST) == [], _warn(GOOD_POST)


def test_overlong_title_is_reported():
    post = {**GOOD_POST, "title": "India's Index Funds And The European Benchmark "
                                  "Consolidation That Reshapes Passive Allocation In 2026"}
    assert "chars (limit 70)" in _warn(post)


def test_late_india_hook_is_reported():
    post = {**GOOD_POST,
            "title": "A Long Global Benchmark Development Discussed First: What It Means for India"}
    assert "cut off in search results" in _warn(post)


def test_missing_india_hook_is_reported():
    post = {**GOOD_POST, "title": "Nordea expands its benchmark range"}
    assert "no India/regulator hook" in _warn(post)


def test_overlong_lede_is_reported():
    post = {**GOOD_POST, "sections": {"what_changed":
            "Nordea has now expanded its Paris-aligned benchmark range in a move that "
            "affects every European asset manager tracking the methodology as well as "
            "the Indian index funds that inherit it through their own passive mandates "
            "and their SEBI disclosure obligations. Short follow-up."}}
    assert "lede is" in _warn(post) and "limit 30" in _warn(post)


def test_attribution_first_lede_is_reported():
    post = {**GOOD_POST, "sections": {"what_changed":
            "Reporting by ESG Today, Nordea expanded its range. It matters for India."}}
    assert "attribution instead of the news" in _warn(post)


def test_bare_url_in_lede_is_reported():
    post = {**GOOD_POST, "sections": {"what_changed":
            "Nordea (https://www.esgtoday.com/a-very-long-article-path/) expanded "
            "its range. It matters for Indian filers."}}
    assert "bare URL" in _warn(post)


def test_trailing_source_line_is_not_mistaken_for_the_lede():
    """The prompt requires a 'Source: <url>' line at the end of what_changed.
    That line must not itself be read as prose, or the URL rule would fire on
    every correctly-written post."""
    assert "bare URL" not in _warn(GOOD_POST)
    assert ca.craft_warnings(GOOD_POST) == []


# ── the guarantee that makes this safe to run in production ──────────────────
def test_craft_warnings_never_raises_on_malformed_input():
    for bad in ({}, {"title": None}, {"sections": None},
                {"title": "x", "sections": {"what_changed": None}},
                {"title": "x", "sections": {}}):
        ca.craft_warnings(bad)   # must not raise


def test_craft_warnings_is_not_wired_into_the_refusal_path():
    """Craft must never block publication. ReviewRejected is raised only by the
    review gate; craft_warnings returns strings and is called for its output."""
    src = (SITE / "tools" / "climate_agent.py").read_text(encoding="utf-8")
    fn = src[src.index("def craft_warnings"):src.index("def write_and_verify")]
    # A `raise` STATEMENT, not the word inside the docstring.
    assert not re.search(r"^\s+raise\b", fn, re.M), "craft_warnings must never raise"
    assert "ReviewRejected" not in fn, "craft must not reach the refusal path"
    # and it must actually be called, or the rules are unverified again
    assert re.search(r"for w in craft_warnings\(post\)", src), "craft check not wired in"
