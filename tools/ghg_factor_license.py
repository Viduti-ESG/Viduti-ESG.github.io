"""
GHG emission-factor LICENCE GATE.

The GHG calculator (assets/data/ghg-factors.json) must only ever ship emission
factors that are FREE TO USE COMMERCIALLY. This script hardcodes that restriction:

  1. ALLOWLIST  — only the sources below are permitted. Each is free-licensed and
     verified (see licence + url). Anything else (ecoinvent, GaBi/Sphera, MSCI,
     CDP, commercial DEFRA repackagers, etc.) is a licence trap and is blocked.
  2. GATE       — scan ghg-factors.json; any factor whose `source` is not on the
     allowlist (or is missing) => exit 1 (block publish).
  3. ATTRIBUTION — print the exact credit lines the open licences REQUIRE us to
     display on the GHG page (OGL v3.0 / IFI / Cornell all require attribution).

Run before deploying any change to ghg-factors.json:
    python tools/ghg_factor_license.py            # gate (exit 1 on failure)
    python tools/ghg_factor_license.py --report   # report only, never fails

To add a NEW source: add it here with its licence + url + attribution FIRST, only
after confirming the licence permits free commercial use. Never add the source by
editing the JSON alone — that is exactly the drift this gate exists to stop.
"""
import sys, json
from pathlib import Path
from collections import Counter

FACTORS = Path(__file__).parent.parent / "assets" / "data" / "ghg-factors.json"
REPORT_ONLY = "--report" in sys.argv

# ── HARDCODED ALLOWLIST — free-to-use-commercially sources only ───────────────
ALLOWED = {
    "DEFRA": {
        "licence": "UK Open Government Licence v3.0",
        "url": "https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting",
        "attribution": "Contains public sector information licensed under the Open "
                       "Government Licence v3.0. UK Government GHG Conversion Factors "
                       "for Company Reporting (DEFRA/DESNZ).",
        "note": "Universal fuel chemistry OK worldwide; UK grid/Scope 2 is UK-specific "
                "— use IFI 'India' for Indian electricity.",
    },
    "IFI": {
        "licence": "IFI Technical Working Group — freely publishable",
        "url": "https://unfccc.int/sites/default/files/resource/Harmonized_IFI_Default_Grid_Factors_2021_v3.1.pdf",
        "attribution": "Grid emission factors from the IFI Dataset of Default Grid "
                       "Factors (International Financial Institutions Technical Working "
                       "Group on GHG Accounting).",
        "note": "Per-country Scope 2 electricity, incl. India.",
    },
    "CORNELL": {
        "licence": "Cornell Hotel Sustainability Benchmarking (CHSB) — free to use",
        "url": "https://greenview.sg/services/chsb-index/",
        "attribution": "Hotel-stay factors from the Cornell Hotel Sustainability "
                       "Benchmarking (CHSB) Index.",
        "note": "Scope 3 business-travel hotel nights.",
    },
}

# Sources known to be LICENCE TRAPS — never permitted (informational; the gate
# blocks anything not on ALLOWED, this list just gives a clearer error message).
BANNED_HINT = {
    "ECOINVENT", "GABI", "SPHERA", "MSCI", "CDP", "SUSTAINALYTICS",
    "THINKSTEP", "QUANTIS", "SIMA", "SIMAPRO",
}


def main():
    if not FACTORS.exists():
        print(f"FAIL: {FACTORS} not found")
        sys.exit(1)

    data = json.loads(FACTORS.read_text(encoding="utf-8"))

    # Placeholder rows (dropdown prompts) carry no numeric factor — they ship no
    # emission value, so they are not a licence concern. Police real factors only.
    real = [r for r in data if r.get("factor") is not None]
    placeholders = len(data) - len(real)
    counts = Counter((row.get("source") or "<MISSING>") for row in real)

    print("=" * 70)
    print("GHG EMISSION-FACTOR LICENCE GATE")
    print("=" * 70)
    print(f"factors: {len(data)}   with-value: {len(real)}   "
          f"placeholders skipped: {placeholders}")
    print(f"sources: {dict(counts)}\n")

    failures = []
    for src, n in counts.items():
        if src in ALLOWED:
            print(f"  OK    {src:<10} {n:>5}  — {ALLOWED[src]['licence']}")
        else:
            key = (src or "").upper()
            why = "LICENCE TRAP" if key in BANNED_HINT else "NOT ON ALLOWLIST"
            failures.append((src, n, why))
            print(f"  BLOCK {str(src):<10} {n:>5}  — {why}")

    print("\n" + "-" * 70)
    print("REQUIRED ATTRIBUTION (must be visible on the GHG page):")
    for src in counts:
        if src in ALLOWED:
            print(f"  • {ALLOWED[src]['attribution']}")

    if failures:
        print("\n" + "=" * 70)
        print(f"GATE FAILED: {len(failures)} disallowed source(s).")
        for src, n, why in failures:
            print(f"  - {src}: {n} factor(s) [{why}]")
        print("Remove these factors, or add the source to ALLOWED in this file")
        print("ONLY after confirming its licence permits free commercial use.")
        print("=" * 70)
        if not REPORT_ONLY:
            sys.exit(1)
    else:
        print("\nGATE PASSED: every factor is free-licensed.")


if __name__ == "__main__":
    main()
