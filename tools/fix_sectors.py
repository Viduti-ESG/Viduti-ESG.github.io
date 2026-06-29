#!/usr/bin/env python3
"""
Green Curve — correct a small set of clearly-misclassified company sectors.

Sector drives peer benchmarking, percentiles and the sector-median used by the
data-quality outlier guard, so a steel maker filed under "Electrical Equipment"
pollutes all of those. This remap is intentionally CONSERVATIVE and hand-verified:
only companies whose assigned sector is nonsensical for their own `products` are
corrected. Defensible edge cases are deliberately left alone — steel *forgings*
stay "Fabricated Metal", iron-ore *miners* stay "Metal Ore Mining", railway rolling
stock stays "Other Transport Equipment" — to avoid trading one error for another.

Run, then re-run clean_published.py (medians change) and generate_company_pages.py.
"""
import json
from pathlib import Path

DATA = Path(__file__).parent.parent / "assets" / "data" / "esg_quotient.json"

# company_name -> corrected sector (canonical labels already present in the dataset)
REMAP = {
    "JSW Steel Limited":                 "Basic Metals",   # was Architecture & Engineering
    "GODAWARI POWER AND ISPAT LIMITED":  "Basic Metals",   # was Electrical Equipment (iron/steel)
    "Mukand Limited":                    "Basic Metals",   # was Electrical Equipment (alloy steel)
    "HI-TECH PIPES LIMITED":             "Basic Metals",   # was Electrical Equipment (steel pipes)
    "JTL Industries Limited":            "Basic Metals",   # was Electrical Equipment (iron & steel)
    "Lloyds Metals And Energy Ltd":      "Basic Metals",   # was Architecture & Engineering
    "JK CEMENT LIMITED":                 "Cement & Non-Metallic Minerals",  # was Other Manufacturing
}


def main() -> int:
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    changed = 0
    for c in doc.get("companies", []):
        new = REMAP.get(c.get("company_name"))
        if new and c.get("sector") != new:
            print(f"  {c['company_name']}: {c.get('sector')!r} -> {new!r}")
            c["sector"] = new
            changed += 1
    DATA.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    print(f"reclassified {changed} company sector(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
