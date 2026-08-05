"""Mutation tests for the blog review gate (tools/climate_agent.py).

This agent publishes straight to a search-indexed site with no human in the
loop, so the gate is the only thing between a fabricated statistic and a public
Green Curve statement. A gate nobody has shown capable of refusing is
decoration -- so every test here asserts a *refusal*, not just a pass.

No model is called: a fake client returns canned replies. That keeps the suite
free and fast, and it lets us test the cases a real reviewer would rarely
produce on demand (truncation, garbage, self-contradiction).
"""

import json
import sys
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SITE / "tools"))

import climate_agent as ca  # noqa: E402


ITEM = {"source": "ESG Today", "title": "EcoVadis and Novata partner on Scope 3",
        "link": "https://example.com/a", "summary": "A partnership was announced."}
BODY = "EcoVadis and Novata announced a partnership to help companies measure Scope 3 emissions."

CLEAN_POST = {
    "title": "EcoVadis-Novata: what supplier carbon data means for Indian filers",
    "category": "SEBI / BRSR",
    "summary": "A partnership on Scope 3 measurement.",
    "sections": {"what_changed": "Reporting by ESG Today: the two firms announced a partnership.",
                 "who_is_affected": ["listed Indian companies"],
                 "key_obligations": ["BRSR Core value-chain disclosure"],
                 "climate_angle": "In our view this points to supplier data consolidation.",
                 "what_to_do": ["Ask your top suppliers what data they already hold"],
                 "our_take": "We expect this to matter for BRSR value-chain reporting."},
}


class FakeMsg:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [type("B", (), {"text": text})()]
        self.stop_reason = stop_reason
        self.usage = type("U", (), {"output_tokens": 100})()


class FakeClient:
    """Returns queued replies in order; records the prompts it was given."""

    def __init__(self, *replies):
        self._replies = list(replies)
        self.prompts = []
        self.messages = self

    def create(self, **kw):
        self.prompts.append(kw["messages"][-1]["content"])
        if not self._replies:
            raise AssertionError("FakeClient ran out of queued replies")
        r = self._replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def review_reply(verdict, issues=()):
    return FakeMsg(json.dumps({"verdict": verdict, "issues": list(issues),
                               "summary": "test"}))


CRITICAL = {"severity": "critical", "category": "fabricated_specific",
            "location": "sections.what_changed",
            "quote": "a $350 million deal covering 4,000 suppliers",
            "why": "no such figure appears in the source",
            "fix": "delete the figure"}


# ── the gate must refuse ──────────────────────────────────────────────────────

def test_fail_verdict_is_refused():
    with pytest.raises(ca.ReviewRejected):
        ca.review_post(FakeClient(review_reply("FAIL", [CRITICAL])),
                       ITEM, BODY, CLEAN_POST)


def test_critical_issue_overrides_a_pass_verdict():
    """A reviewer that lists a critical problem and still says PASS has
    contradicted itself. The safe reading of a contradiction is the stricter
    one -- otherwise a single mislabelled field publishes a fabrication."""
    with pytest.raises(ca.ReviewRejected):
        ca.review_post(FakeClient(review_reply("PASS", [CRITICAL])),
                       ITEM, BODY, CLEAN_POST)


def test_truncated_review_is_refused_not_assumed_pass():
    with pytest.raises(ca.ReviewRejected, match="truncated"):
        ca.review_post(FakeClient(FakeMsg('{"verdict": "PA', "max_tokens")),
                       ITEM, BODY, CLEAN_POST)


def test_unparseable_review_is_refused():
    with pytest.raises(ca.ReviewRejected, match="unparseable"):
        ca.review_post(FakeClient(FakeMsg("I couldn't complete that request.")),
                       ITEM, BODY, CLEAN_POST)


def test_reviewer_api_error_is_refused_not_swallowed():
    with pytest.raises(ca.ReviewRejected, match="unreachable"):
        ca.review_post(FakeClient(RuntimeError("503 overloaded")),
                       ITEM, BODY, CLEAN_POST)


def test_missing_verdict_is_refused():
    with pytest.raises(ca.ReviewRejected, match="no usable verdict"):
        ca.review_post(FakeClient(FakeMsg('{"issues": []}')), ITEM, BODY, CLEAN_POST)


# ── the gate must also allow good work through ────────────────────────────────

def test_clean_post_passes():
    out = ca.review_post(FakeClient(review_reply("PASS")), ITEM, BODY, CLEAN_POST)
    assert out["verdict"] == "PASS"


def test_minor_issues_alone_do_not_block():
    """If every wording nit blocked publication the gate would be turned off
    within a week, which is the real failure mode of a strict-but-noisy check."""
    minor = dict(CRITICAL, severity="minor", category="overstated_certainty")
    out = ca.review_post(FakeClient(review_reply("PASS", [minor])),
                         ITEM, BODY, CLEAN_POST)
    assert out["verdict"] == "PASS"


# ── the reviewer must actually be shown the evidence ──────────────────────────

def test_reviewer_receives_both_source_text_and_draft():
    c = FakeClient(review_reply("PASS"))
    ca.review_post(c, ITEM, BODY, CLEAN_POST)
    prompt = c.prompts[0]
    assert BODY in prompt, "reviewer was not given the source article text"
    assert CLEAN_POST["title"] in prompt, "reviewer was not given the draft"
    assert ITEM["link"] in prompt


# ── repair path ───────────────────────────────────────────────────────────────

def test_repair_then_pass_publishes(monkeypatch):
    fixed = json.loads(json.dumps(CLEAN_POST))
    fixed["sections"]["what_changed"] = "Reporting by ESG Today: a partnership."
    c = FakeClient(review_reply("FAIL", [CRITICAL]),      # first review
                   FakeMsg(json.dumps(fixed)),            # repair draft
                   review_reply("PASS"))                  # second review
    monkeypatch.setattr(ca, "_client", lambda: c)
    monkeypatch.setattr(ca, "write_post", lambda i, b: CLEAN_POST)
    post, review = ca.write_and_verify(ITEM, BODY)
    assert review["verdict"] == "PASS"
    assert post["sections"]["what_changed"] == fixed["sections"]["what_changed"]


def test_second_failure_after_repair_does_not_publish(monkeypatch):
    """The repair gets exactly one attempt. A model that cannot ground its
    claims twice is not going to on the third try, and each retry is spend."""
    c = FakeClient(review_reply("FAIL", [CRITICAL]),
                   FakeMsg(json.dumps(CLEAN_POST)),
                   review_reply("FAIL", [CRITICAL]))
    monkeypatch.setattr(ca, "_client", lambda: c)
    monkeypatch.setattr(ca, "write_post", lambda i, b: CLEAN_POST)
    with pytest.raises(ca.ReviewRejected):
        ca.write_and_verify(ITEM, BODY)


def test_no_actionable_findings_means_no_repair_attempt(monkeypatch):
    """With nothing to repair against, re-asking is spend with no target."""
    c = FakeClient(FakeMsg("garbage, not json"))
    monkeypatch.setattr(ca, "_client", lambda: c)
    monkeypatch.setattr(ca, "write_post", lambda i, b: CLEAN_POST)
    with pytest.raises(ca.ReviewRejected):
        ca.write_and_verify(ITEM, BODY)
    assert len(c.prompts) == 1, "a repair was attempted with no findings to fix"


# ── configuration guards ──────────────────────────────────────────────────────

def test_review_gate_constants_are_sane():
    assert ca.MAX_POST_TOKENS >= 8000, "truncation was the original failure mode"
    assert ca.MAX_REVIEW_TOKENS >= 2000
    assert ca.MAX_PER_RUN_DEFAULT >= 1
    assert ca.REVIEW_MODEL in ("claude-sonnet-4-6", "claude-opus-5", "claude-haiku-4-5-20251001")


def test_publish_path_goes_through_the_gate():
    """Guards against someone reintroducing a direct write_post call in main().
    The gate is only a gate if there is no way around it."""
    src = (SITE / "tools" / "climate_agent.py").read_text(encoding="utf-8")
    main_src = src[src.index("def main("):]
    assert "write_and_verify(" in main_src
    assert "write_post(" not in main_src, \
        "main() calls write_post directly — that bypasses the review gate"


# ── characterisation drift: the 1-2 Aug 2026 escape class ─────────────────────
# Numbers correct, verb wrong. The gate caught fabrication but let these through,
# so both halves are now tested: the deterministic flagger AND the prompt.

def test_strength_flags_catch_stance_verb_drift():
    """'82% oppose' where the source says 'low or no support'."""
    flags = ca.strength_flags(
        "GHG Protocol consultation: 82% of companies oppose mandatory hourly matching.",
        "Only 12% of companies said they support hourly matching, and 82% "
        "indicated low or no support.")
    assert any(f["why"] == "stance verb" for f in flags), \
        "'oppose' against a source that never says it must be flagged"


def test_strength_flags_catch_transaction_status_drift():
    """'completed acquisition' where the source says 'agreed to acquire'."""
    flags = ca.strength_flags(
        "Schneider Electric announced the completed acquisition of AiDASH.",
        "Schneider Electric has agreed to acquire AiDASH, subject to regulatory "
        "approval and customary closing conditions.")
    assert any(f["why"] == "transaction status" for f in flags)


def test_strength_flags_stay_quiet_when_source_uses_the_same_word():
    """A legitimate paraphrase must not be flagged, or the signal is noise."""
    flags = ca.strength_flags(
        "The rule mandates disclosure from FY2026-27.",
        "The regulator mandates disclosure for the top 1,000 from FY2026-27.")
    assert not any(f["why"] == "obligation status" for f in flags)


def test_strength_flags_are_injected_into_the_review_prompt(monkeypatch):
    """A flag the reviewer never sees cannot be adjudicated."""
    drifted = dict(CLEAN_POST)
    drifted["summary"] = "82% of companies oppose the proposal."
    c = FakeClient(FakeMsg('{"verdict":"PASS","issues":[],"summary":"ok"}'))
    monkeypatch.setattr(ca, "_client", lambda: c)
    ca.review_post(c, ITEM, "82% indicated low or no support.", drifted)
    assert "MECHANICAL FLAGS" in c.prompts[0], "flags were computed but not sent"
    assert "oppos" in c.prompts[0].lower()


def test_review_prompt_names_characterisation_drift():
    assert "CHARACTERISATION DRIFT" in ca.REVIEW_SYSTEM_PROMPT
    assert "characterisation_drift" in ca.REVIEW_SYSTEM_PROMPT
    assert "agreed vs completed" in ca.REVIEW_SYSTEM_PROMPT


# ── durable run record ────────────────────────────────────────────────────────

def test_status_write_is_never_fatal(monkeypatch, tmp_path):
    """A failed log write must not stop a good post publishing."""
    monkeypatch.setattr(ca, "STATUS_DIR", tmp_path / "nope" / "deeper")
    monkeypatch.setattr(ca, "STATUS_PATH", tmp_path / "nope" / "deeper" / "x.json")
    ca.write_run_status({"ran_at": "now"})          # must not raise


def test_status_record_round_trips(monkeypatch, tmp_path):
    import json as _json
    monkeypatch.setattr(ca, "STATUS_DIR", tmp_path)
    monkeypatch.setattr(ca, "STATUS_PATH", tmp_path / "blog_review.json")
    ca.write_run_status({"ran_at": "2026-08-04T05:30:00+00:00", "published": 1,
                         "refused": 0, "items": [{"outcome": "published"}]})
    data = _json.loads((tmp_path / "blog_review.json").read_text(encoding="utf-8"))
    assert data["published"] == 1 and data["items"][0]["outcome"] == "published"


def test_main_writes_a_status_record_on_every_path():
    """Including the quiet-day path — a stale file must mean a failed run."""
    src = (SITE / "tools" / "climate_agent.py").read_text(encoding="utf-8")
    main_src = src[src.index("def main("):]
    assert main_src.count("write_run_status(") >= 2, \
        "the no-fresh-news path must also stamp the status file"


# ── India regulatory ground truth ─────────────────────────────────────────────
# The model review is judged against the SOURCE ARTICLE, which can say nothing
# about Indian regulation. On 5 Aug 2026 a post published under the new gate
# still put the top 1,000 in BRSR Core from FY2024-25 and cited a circular
# number that does not exist. These facts are checked mechanically instead.

def test_wrong_glide_path_year_is_critical():
    out = ca.regulatory_facts_check(
        "BRSR Core, mandatory for the top 150 from FY2023-24 and extended to "
        "the top 1,000 from FY2024-25, requires assured disclosures.")
    assert any("top 1000" in i["why"] for i in out)
    assert all(i["severity"] == "critical" for i in out)


def test_correct_glide_path_does_not_flag():
    """A true statement must pass, or the check gets switched off."""
    assert ca.regulatory_facts_check(
        "BRSR Core applies to the top 150 from FY2023-24, the top 250 from "
        "FY2024-25, the top 500 from FY2025-26 and the top 1,000 from FY2026-27."
    ) == []


def test_limited_assurance_on_brsr_core_is_critical():
    out = ca.regulatory_facts_check(
        "Engage your limited assurance provider on BRSR Core before filing.")
    assert any("REASONABLE assurance" in i["why"] for i in out)


def test_physical_risk_attributed_to_brsr_core_is_critical():
    out = ca.regulatory_facts_check(
        "BRSR Core mandates physical climate risk disclosure for large filers.")
    assert any("nine assured" in i["why"] for i in out)


def test_unknown_sebi_circular_number_is_critical():
    out = ca.regulatory_facts_check(
        "See SEBI circular SEBI/HO/CFD/CMD-2/CIR/P/2023/122 for the format.")
    assert any(i["location"] == "SEBI circular reference" for i in out)


def test_the_real_circular_number_is_allowed():
    assert ca.regulatory_facts_check(
        "See SEBI/HO/CFD/CFD-SEC-2/P/CIR/2023/122 dated 12 July 2023.") == []


def test_facts_check_blocks_a_post_the_model_review_passed(monkeypatch):
    """The exact 5 Aug 2026 escape: reviewer says PASS, facts say no."""
    bad = dict(CLEAN_POST)
    bad["summary"] = ("BRSR Core is mandatory for the top 1,000 listed entities "
                      "from FY2024-25.")
    # 3 replies: first review PASS, the repair, then the re-review PASS. The
    # model is happy throughout - only our own facts stop it.
    c = FakeClient(FakeMsg('{"verdict":"PASS","issues":[],"summary":"clean"}'),
                   FakeMsg(json.dumps(bad)),
                   FakeMsg('{"verdict":"PASS","issues":[],"summary":"clean"}'))
    monkeypatch.setattr(ca, "_client", lambda: c)
    monkeypatch.setattr(ca, "write_post", lambda i, b: bad)
    with pytest.raises(ca.ReviewRejected) as e:
        ca.write_and_verify(ITEM, BODY)
    assert "ground truth" in str(e.value)


def test_facts_check_runs_again_after_repair(monkeypatch):
    """A repair that reintroduces the error must not publish."""
    bad = dict(CLEAN_POST)
    bad["summary"] = "BRSR Core covers the top 500 from FY2029-30."
    c = FakeClient(FakeMsg('{"verdict":"PASS","issues":[],"summary":"clean"}'),
                   FakeMsg('{"verdict":"PASS","issues":[],"summary":"clean"}'))
    monkeypatch.setattr(ca, "_client", lambda: c)
    monkeypatch.setattr(ca, "write_post", lambda i, b: bad)
    monkeypatch.setattr(ca, "repair_post", lambda *a, **k: bad)   # repair no-ops
    with pytest.raises(ca.ReviewRejected) as e:
        ca.write_and_verify(ITEM, BODY)
    assert "survived repair" in str(e.value)
