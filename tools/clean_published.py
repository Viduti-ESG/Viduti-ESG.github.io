#!/usr/bin/env python3
"""
Green Curve — clean the PUBLISHED display artifact (assets/data/esg_quotient.json).

This is the pipeline step that was missing: data_clean.py's guards were wired into
scoring (score_engine) and the cleaned-emissions backfill (build_fe_backfill) but
NEVER into the artifact the website and the 1,200+ company pages actually read.
That let physically-impossible values reach production (e.g. a security-services
firm shown withdrawing 4x India's entire water supply) while the publish gate —
which inspected only the cleaned intermediate — stayed green.

Running this applies the SAME guards to the displayed financial_exposure + metrics,
in place, with a timestamped backup. Re-run generate_company_pages.py afterwards so
the per-company pages pick up the cleaned figures.

Usage:
    python tools/clean_published.py            # clean assets/data/esg_quotient.json
    python tools/clean_published.py --dry-run  # report only, write nothing
"""
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import data_clean as dc

ROOT = Path(__file__).parent.parent
DATA = ROOT / "assets" / "data" / "esg_quotient.json"
BACKUP_DIR = ROOT / "_dq_backups"

PCT_FIELDS = ("renewable_pct", "waste_recovery_pct", "female_board_pct", "female_kmp_pct")


def main(dry_run: bool = False) -> int:
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    companies = doc.get("companies", [])
    changes = {"scope": 0, "water": 0, "waste": 0, "revenue": 0, "pct": 0, "sector_outlier": 0}
    notable = []

    # ── Pass 1: per-company guards ────────────────────────────────────────────
    intensity_items = []  # (idx, sector, intensity) for the sector-outlier pass
    for i, c in enumerate(companies):
        fe = c.get("financial_exposure") or {}
        sector = c.get("sector") or ""
        rev = c.get("revenue_crore")
        s1 = fe.get("scope1_emissions_tco2e")
        s2 = fe.get("scope2_emissions_tco2e")
        s3 = fe.get("scope3_emissions_tco2e")

        # Lower-bound revenue: null a parse-artefact revenue BEFORE deriving anything
        # from it, so a bad denominator can't manufacture a fake intensity.
        if dc.revenue_suspect_low(rev, s1, s2):
            if rev is not None:
                notable.append(f"  revenue  {c['company_name']}: {rev} -> null (suspect-low)")
                c["revenue_crore"] = None
                rev = None
                changes["revenue"] += 1

        # Emissions magnitude + false-zero (per-company, absolute)
        res = dc.clean_emissions(s1, s2, s3, rev, sector)
        for raw, key in ((s1, "scope1_emissions_tco2e"),
                         (s2, "scope2_emissions_tco2e"),
                         (s3, "scope3_emissions_tco2e")):
            cleaned = res["scope1"] if key.startswith("scope1") else \
                      res["scope2"] if key.startswith("scope2") else res["scope3"]
            if raw != cleaned:
                fe[key] = cleaned
                changes["scope"] += 1
                if raw and raw > dc.EMIS_CEIL:
                    notable.append(f"  emission {c['company_name']}: {key}={raw:,.0f} -> null (>ceil)")

        # Water + waste ceilings
        w = fe.get("water_withdrawal_m3")
        cw = dc.clean_water(w)
        if w != cw:
            fe["water_withdrawal_m3"] = cw
            changes["water"] += 1
            notable.append(f"  water    {c['company_name']}: {w:,.0f} m3 -> null")
        wt = fe.get("waste_tonnes")
        cwt = dc.clean_waste(wt)
        if wt != cwt:
            fe["waste_tonnes"] = cwt
            changes["waste"] += 1
            notable.append(f"  waste    {c['company_name']}: {wt:,.0f} t -> null")

        # Percentage clamps (0..100)
        rb = c.get("risk_breakdown") or {}
        metrics = rb.get("metrics") or {}
        for f in PCT_FIELDS:
            if f in metrics:
                cv = dc.clean_pct(metrics[f])
                if cv != metrics[f]:
                    notable.append(f"  pct      {c['company_name']}: {f}={metrics[f]} -> null")
                    metrics[f] = cv
                    changes["pct"] += 1

        c["financial_exposure"] = fe
        # intensity candidate for the sector-outlier pass (only with trustworthy rev)
        intensity_items.append((i, sector, res["ghg_intensity"]))

    # ── Pass 2: display sector-outlier (loose threshold — keeps real heavy emitters)
    import statistics as st
    from collections import defaultdict
    by_sec = defaultdict(list)
    allv = []
    for _, sec, inten in intensity_items:
        if inten and inten > 0:
            by_sec[sec].append(inten); allv.append(inten)
    med = {s: st.median(v) for s, v in by_sec.items() if len(v) >= dc.SECTOR_MIN_PEERS}
    overall = st.median(allv) if allv else None
    for idx, sec, inten in intensity_items:
        if not inten or inten <= 0:
            continue
        m = med.get(sec, overall)
        if m and inten > dc.DISPLAY_SECTOR_HI_FACTOR * m:
            c = companies[idx]
            fe = c["financial_exposure"]
            ratio = inten / m
            notable.append(f"  outlier  {c['company_name']}: intensity {inten:,.0f} "
                           f"({ratio:,.0f}x {sec} median) -> emissions nulled")
            fe["scope1_emissions_tco2e"] = None
            fe["scope2_emissions_tco2e"] = None
            changes["sector_outlier"] += 1

    total = sum(changes.values())
    print("=" * 70)
    print(f"clean_published — {len(companies)} companies, {total} field(s) neutralised")
    print(f"  scope-emissions: {changes['scope']}   sector-outlier: {changes['sector_outlier']}")
    print(f"  water: {changes['water']}   waste: {changes['waste']}   "
          f"revenue: {changes['revenue']}   pct: {changes['pct']}")
    print("=" * 70)
    for line in notable[:80]:
        print(line)
    if len(notable) > 80:
        print(f"  … and {len(notable) - 80} more")

    if dry_run:
        print("\n[dry-run] no files written.")
        return 0

    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_DIR / f"esg_quotient.{stamp}.json.bak"
    shutil.copy2(DATA, backup)
    doc["data_cleaned_at"] = datetime.now(timezone.utc).date().isoformat()
    DATA.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    print(f"\nbacked up -> {backup.name}")
    print(f"written   -> {DATA.relative_to(ROOT)}")
    print("NEXT: python generate_company_pages.py   (regenerate pages from cleaned data)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(dry_run="--dry-run" in sys.argv))
