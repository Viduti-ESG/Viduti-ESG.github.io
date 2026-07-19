"""
Skill-drift guard: verify that facts the Green Curve skills ASSERT about this
codebase still match the code and the published artifact.

Why: the 2026-07-19 audit found the skills citing RECOVERY_MAX_FACTOR 1.001
and a SAIL ground truth the pipeline no longer produced — the skills and the
code had silently diverged, so every future session would have been steered by
stale facts. Skills are documentation with authority; drift here is a bug.

Checked (per skill copy in c:/Viduti/.claude/skills AND c:/Viduti/skills):
  * publishing-esg-data: RECOVERY_MAX_FACTOR must equal data_clean.py's value;
    the CEA India Scope 2 factor it cites must appear in ghg-calculator.js.
  * qa-greencurve: the /api/esg/stats total it expects must equal the company
    count in assets/data/esg_quotient.json; SAIL spot-check values (revenue,
    Scope 1) must match the published artifact.

Runs as part of data_quality_audit.py (gate). Skips silently on hosts that
don't have the skills directories (e.g. the prod box). Exit 1 on mismatch.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import data_clean as dc  # noqa

ROOT = Path(__file__).resolve().parent.parent
SKILL_BASES = [Path(r"c:/Viduti/.claude/skills"), Path(r"c:/Viduti/skills")]

failures = []


def check(label, ok):
    print(f"  [{'OK' if ok else 'DRIFT'}] {label}")
    if not ok:
        failures.append(label)


def main() -> int:
    bases = [b for b in SKILL_BASES if b.exists()]
    if not bases:
        print("skill-constants: no skills directories on this host — skipped")
        return 0

    eq = json.loads((ROOT / "assets/data/esg_quotient.json").read_text(encoding="utf-8"))
    comps = eq["companies"]
    sail = next((c for c in comps if "steel authority" in c["company_name"].lower()), None)
    ghg_js = (ROOT / "assets/js/ghg-calculator.js").read_text(encoding="utf-8")

    for base in bases:
        pub = (base / "publishing-esg-data/SKILL.md")
        qa = (base / "qa-greencurve/SKILL.md")
        tag = base.name if base.name != "skills" else str(base)

        if pub.exists():
            t = pub.read_text(encoding="utf-8")
            m = re.search(r"RECOVERY_MAX_FACTOR\s+([\d.]+)", t)
            check(f"{tag}/publishing: RECOVERY_MAX_FACTOR cited={m.group(1) if m else '?'} "
                  f"code={dc.RECOVERY_MAX_FACTOR}",
                  bool(m) and float(m.group(1)) == float(dc.RECOVERY_MAX_FACTOR))
            m = re.search(r"CEA\s+([\d.]+)\s*kg/kWh", t)
            check(f"{tag}/publishing: CEA factor cited={m.group(1) if m else '?'} in ghg-calculator.js",
                  bool(m) and m.group(1) in ghg_js)

        if qa.exists():
            t = qa.read_text(encoding="utf-8")
            m = re.search(r"total=(\d+)", t)
            check(f"{tag}/qa: expected stats total={m.group(1) if m else '?'} "
                  f"artifact={len(comps)}",
                  bool(m) and int(m.group(1)) == len(comps))
            if sail:
                fe = sail.get("financial_exposure") or {}
                m = re.search(r"revenue\s*₹([\d,]+)\s*cr", t)
                cited_rev = float(m.group(1).replace(",", "")) if m else None
                check(f"{tag}/qa: SAIL revenue cited={cited_rev} artifact={sail.get('revenue_crore')}",
                      cited_rev is not None and cited_rev == sail.get("revenue_crore"))
                m = re.search(r"Scope 1\s*=\s*([\d,]+)\s*tCO2e", t)
                cited_s1 = float(m.group(1).replace(",", "")) if m else None
                check(f"{tag}/qa: SAIL Scope1 cited={cited_s1} artifact={fe.get('scope1_emissions_tco2e')}",
                      cited_s1 is not None and cited_s1 == fe.get("scope1_emissions_tco2e"))

    if failures:
        print(f"\nskill-constants: {len(failures)} DRIFTED fact(s) — update the SKILL.md "
              "(both copies) or the code, whichever is wrong.")
        return 1
    print("skill-constants: all cited facts match the code and published artifact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
