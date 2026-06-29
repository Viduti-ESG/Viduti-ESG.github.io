#!/usr/bin/env python3
"""
Green Curve — validate and repair company CINs in the published dataset.

Three defects, three actions:
  • casing typo  (e.g. PG Electroplast 'L32109Dl2003PLC119416') -> upper-case the
    string; if it then validates, keep it (real CIN, just mis-cased).
  • fabricated placeholders for statutory bodies that have no MCA CIN (PSU banks,
    LIC, etc. — 'A99999AA9999AAA999999', 'U12345KA1234KAA123456', …) -> blank, so
    the profile shows no CIN rather than a fake one. NOTE: 'L99999…' is NOT itself
    fabricated — 99999 is a legitimate "activity n.e.c." MCA code (L&T, Atul, …).
  • a CIN shared by two different companies (Cemindia Projects carries ITD
    Cementation's real CIN) -> blank it on the non-owner.

A CIN is accepted iff it matches the MCA structure AND has a plausible incorporation
year AND a recognised company-class code. Everything else is blanked (never invented).
"""
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

DATA = Path(__file__).parent.parent / "assets" / "data" / "esg_quotient.json"

CIN_RE = re.compile(r'^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$')
# MCA company-class codes (positions 12:15). 'PSU' (seen on UCO Bank) is NOT one.
CLASS_CODES = {"PLC", "PTC", "GOI", "GAP", "GAT", "SGC", "NPL",
               "OPC", "FLC", "FTC", "ULL", "ULT"}
THIS_YEAR = date.today().year

# Different companies that must not share a CIN — blank it on the listed non-owner.
SHARED_CIN_NONOWNER = {"Cemindia Projects Limited"}  # CIN belongs to ITD Cementation


def cin_valid(cin: str) -> bool:
    if not CIN_RE.match(cin):
        return False
    year = int(cin[8:12])
    if not (1850 <= year <= THIS_YEAR):
        return False
    return cin[12:15] in CLASS_CODES


def main() -> int:
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    companies = doc.get("companies", [])
    fixed_case = blanked = blanked_shared = 0

    for c in companies:
        cin = (c.get("cin") or "").strip()
        if not cin:
            continue
        if c.get("company_name") in SHARED_CIN_NONOWNER:
            print(f"  shared-CIN  {c['company_name']}: {cin!r} -> '' (belongs to another company)")
            c["cin"] = ""
            blanked_shared += 1
            continue
        up = cin.upper()
        if cin_valid(up):
            if up != cin:
                print(f"  casing      {c['company_name']}: {cin!r} -> {up!r}")
                fixed_case += 1
            c["cin"] = up
        else:
            print(f"  fabricated  {c['company_name']}: {cin!r} -> '' (invalid/placeholder)")
            c["cin"] = ""
            blanked += 1

    # Report any *remaining* duplicate CINs for manual review (should be none).
    seen = defaultdict(list)
    for c in companies:
        if c.get("cin"):
            seen[c["cin"]].append(c["company_name"])
    dups = {k: v for k, v in seen.items() if len(v) > 1}
    if dups:
        print("\n  WARNING — CINs still shared by multiple companies (review manually):")
        for k, v in dups.items():
            print(f"    {k}: {v}")

    DATA.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    print(f"\ncasing-fixed: {fixed_case}   fabricated-blanked: {blanked}   "
          f"shared-blanked: {blanked_shared}   remaining-dupes: {len(dups)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
