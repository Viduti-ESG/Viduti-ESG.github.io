"""
Regression tests for the ESG Quotient scoring path.

Every test here is a bug that was live in production on 2 Aug 2026 (Ops Book
Part 24). They are cheap, need no network and no model call, and they fail
loudly if the same mistake is reintroduced.

`build_features.py` and `score_engine.py` execute their pipeline at import
time, so the helpers are extracted with `ast` and exercised in isolation
rather than imported.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
BUILD_FEATURES = TOOLS / "build_features.py"
SCORE_ENGINE = TOOLS / "score_engine.py"


def _extract_function(path: Path, name: str):
    """Compile a single top-level function out of a script that self-executes."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            mod = ast.Module(body=[node], type_ignores=[])
            ns: dict = {"re": re}
            exec(compile(mod, str(path), "exec"), ns)          # noqa: S102
            return ns[name]
    raise AssertionError(f"{name}() not found in {path.name}")


def _tag(local: str, value: str) -> str:
    return f"<in-capmkt:{local} contextRef='D_Main'>{value}</in-capmkt:{local}>"


# ── the enumeration bug: "Yes Assurance" is a yes ────────────────────────────

@pytest.mark.parametrize("value,expected", [
    ("Yes Assurance", True),      # the real BRSR value that used to read False
    ("Yes Assessment", True),
    ("yes", True),
    ("true", True),
    ("No", False),
    ("NA", False),
    ("", False),
])
def test_text_yes_reads_the_answer_not_the_presence(value, expected):
    text_yes = _extract_function(BUILD_FEATURES, "text_yes")
    el = "WhetherTheCompanyHasUndertakenAssessmentOrAssuranceOfTheBRSRCore"
    assert text_yes(_tag(el, value), el) is expected, \
        f"{value!r} should read as {expected}"


def test_text_yes_is_false_when_the_element_is_absent():
    text_yes = _extract_function(BUILD_FEATURES, "text_yes")
    assert text_yes("<in-capmkt:SomethingElse>Yes</in-capmkt:SomethingElse>",
                    "HasTheEntityImplementedAMechanismForZeroLiquidDischarge") is False


def test_text_present_cannot_distinguish_yes_from_no():
    """Documents WHY text_present must never back a yes/no field.

    This is the bug that published Zero Liquid Discharge for all 1,223
    companies when 295 filings said "no" and 212 said "na".
    """
    text_present = _extract_function(BUILD_FEATURES, "text_present")
    el = "HasTheEntityImplementedAMechanismForZeroLiquidDischarge"
    assert text_present(_tag(el, "No"), el) is True     # <- exactly the problem
    assert text_present(_tag(el, "Yes"), el) is True


# ── source guards: the yes/no fields must not regress to text_present ────────

YES_NO_FIELDS = ["zld", "csr_applicable", "ohs_system", "anti_corruption"]


@pytest.mark.parametrize("field", YES_NO_FIELDS)
def test_yes_no_fields_use_text_yes(field):
    src = BUILD_FEATURES.read_text(encoding="utf-8")
    m = re.search(rf'"{field}":\s*(.+)', src)
    assert m, f"field {field} not found in build_features.py"
    line = m.group(1)
    assert "text_yes(" in line, f"{field} must be read with text_yes()"
    assert not re.search(r'text_present\(\s*t,\s*"Whether|text_present\(\s*t,\s*"Has|'
                         r'text_present\(\s*t,\s*"Does', line), \
        f"{field} reads a yes/no element with text_present() — it cannot tell No from Yes"


def test_no_falsy_zero_fallback_in_score_engine():
    """`wavg(...) or 5.0` replaced a best-possible 0.0 with a middling 5.0."""
    src = SCORE_ENGINE.read_text(encoding="utf-8")
    offenders = re.findall(r'wavg\([^\n]*\)\s+or\s+', src)
    assert not offenders, (
        f"falsy-zero fallback found: {offenders} — a legitimate 0.0 is falsy in "
        "Python; use `x if x is not None else <default>`")


def test_zld_credit_is_applied_to_water_not_energy():
    """ZLD is a water practice and methodology.html says it credits water."""
    src = SCORE_ENGINE.read_text(encoding="utf-8")
    m = re.search(r'if\s+(\w+)\s+is not None and v\["zld"\]', src)
    assert m, "the ZLD credit block was not found in score_engine.py"
    assert m.group(1) == "water", \
        f"ZLD credit is applied to {m.group(1)!r}; it belongs on water intensity"


def test_methodology_documents_the_disclosure_floor():
    page = (Path(__file__).resolve().parent.parent / "methodology.html").read_text(encoding="utf-8")
    assert "Disclosure floor" in page, \
        "the tier floor is in the engine but not described on methodology.html"


# ── artifact-level guards (skip when the build output is absent) ─────────────

def _rescored():
    p = TOOLS / "rescored.json"
    if not p.exists():
        pytest.skip("rescored.json not built")
    return json.loads(p.read_text(encoding="utf-8"))


def test_non_disclosure_cannot_be_rated_low():
    """The headline defect: withholding emissions used to make Low twice as likely."""
    data = _rescored()
    offenders = [n for n, c in data.items()
                 if (c.get("risk_breakdown") or {}).get("ghg_intensity") is None
                 and c.get("risk_tier") == "Low"]
    assert not offenders, (
        f"{len(offenders)} companies rated Low with no disclosed carbon intensity, "
        f"e.g. {offenders[:3]}")


def test_zld_is_not_universally_true():
    """A flag true for every company carries no information and was wrong."""
    data = _rescored()
    zld = [1 for c in data.values()
           if (c.get("risk_breakdown") or {}).get("metrics", {}).get("zld")]
    n = len(data)
    assert 0 < len(zld) < n * 0.95, \
        f"zld true for {len(zld)}/{n} — the text_present bug is back"


def test_sector_percentile_declares_its_basis():
    """124 companies once showed a whole-market rank labelled as a sector rank."""
    data = _rescored()
    missing = [n for n, c in data.items()
               if (c.get("risk_breakdown") or {}).get("sector_percentile") is not None
               and (c.get("risk_breakdown") or {}).get("sector_percentile_basis") is None]
    assert not missing, \
        f"{len(missing)} companies carry a sector_percentile with no basis field"


def test_every_company_declares_why_it_has_its_tier():
    data = _rescored()
    missing = [n for n, c in data.items()
               if (c.get("risk_breakdown") or {}).get("tier_basis") is None]
    assert not missing, f"{len(missing)} companies have no tier_basis"
