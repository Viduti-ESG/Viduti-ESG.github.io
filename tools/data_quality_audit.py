"""
Data-quality audit + PUBLISH GATE for the BRSR-derived inputs.

Two jobs:
  1. AUDIT  — surface every implausible value in the raw extraction (unit errors,
     false zeros, magnitude outliers, pay/board parse bugs, duplicates, coverage gaps).
  2. GATE   — verify the shared cleaner in tools/data_clean.py NEUTRALISES every one
     of those flagged values before they can reach a score or a company page.
     Any flagged value that survives cleaning => exit 1 (block publish).

Run after re-extraction and before score_engine / build_fe_backfill:
    python tools/data_quality_audit.py          # report + gate (exit 1 on failure)
    python tools/data_quality_audit.py --report # report only, never fails
"""
import sys, json, statistics as st
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, r"c:/Viduti/my-website/cpcb_agent/esg_intelligence")
import data_clean as dc           # noqa
import company_profiler as cp     # noqa

norm = dc.norm
load = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
REPORT_ONLY = "--report" in sys.argv

slim = load(r"c:/Viduti/brsr-generator/backend/data/companies_brsr_slim.json")["companies"]
emis = load(r"c:/Viduti/esg-site/tools/emissions_extracted.json")
feat = load(r"c:/Viduti/esg-site/tools/raw_features.json")
secs = load(r"c:/Viduti/esg-site/tools/sectors_extracted.json")

failures = []        # gate-blocking findings
print("=" * 78)
print("DATA-QUALITY AUDIT + PUBLISH GATE")
print("=" * 78)

# ── 0. Duplicate companies in source ──────────────────────────────────────────
_, dropped = dc.dedupe_companies(slim)
print(f"\n[0] DUPLICATES in source slim: {len(dropped)}")
for n in dropped:
    print(f"    still-duplicated: {n}")
if dropped:
    failures.append(f"{len(dropped)} duplicate company row(s) remain in companies_brsr_slim.json")

# ── build per-company cleaned view ────────────────────────────────────────────
rows = []
for c in slim:
    k = norm(c["company_name"])
    rev = cp._score_company(c)["revenue_crore"]
    sector = secs.get(k, {}).get("sector", "Unclassified")
    e = emis.get(k, {}); f = feat.get(k, {})
    ce = dc.clean_emissions(f.get("scope1"), f.get("scope2"), e.get("scope3"), rev, sector)
    cf = dc.clean_features(f)
    rows.append({"name": c["company_name"], "k": k, "rev": rev, "sector": sector,
                 "s1": f.get("scope1"), "s2": f.get("scope2"),
                 "ce": ce, "cf": cf,
                 "mwp": f.get("median_worker_pay"), "mbp": f.get("median_board_pay"),
                 "fb": cf["female_board"],
                 "raw_fb": (f.get("female_board_count") / f.get("total_directors"))
                           if (f.get("female_board_count") is not None and f.get("total_directors"))
                           else f.get("pct_female_board")})

# sector-peer carbon outlier mask (same as score_engine / fe_backfill)
carbon_out = dc.sector_intensity_outliers([(r["k"], r["sector"], r["ce"]["ghg_intensity"]) for r in rows])
for r in rows:
    r["ghg_final"] = None if r["k"] in carbon_out else r["ce"]["ghg_intensity"]

# helper: count raw issues, and how many SURVIVE cleaning
def gate(label, raw_pred, survived_pred):
    raw = [r for r in rows if raw_pred(r)]
    survived = [r for r in raw if survived_pred(r)]
    status = "OK" if not survived else "FAIL"
    print(f"\n[{label}] raw-flagged: {len(raw):4}  neutralised: {len(raw)-len(survived):4}  surviving: {len(survived)}  [{status}]")
    for r in survived[:5]:
        print(f"    SURVIVED: {r['name'][:40]}")
    if survived:
        failures.append(f"{len(survived)} {label} value(s) survived cleaning")
    return raw

# ── 1. Emission magnitude outliers ────────────────────────────────────────────
gate("1 EMISSION MAGNITUDE > 5e8 tCO2e",
     lambda r: (r["s1"] or 0) >= dc.EMIS_CEIL or (r["s2"] or 0) >= dc.EMIS_CEIL,
     lambda r: r["ce"]["ghg_intensity"] is not None)

# ── 2. False-zero emitters (rev>500cr, S1+S2==0) ──────────────────────────────
gate("2 FALSE-ZERO emitters (rev>500cr, S1+S2=0)",
     lambda r: r["s1"] == 0 and r["s2"] == 0 and (r["rev"] or 0) > 500,
     lambda r: r["ce"]["ghg_intensity"] is not None)

# ── 3. Sector-peer carbon outliers (replaces self-reference divergence check) ──
gate("3 SECTOR-OUTLIER carbon (vs sector-peer intensity)",
     lambda r: r["k"] in carbon_out,
     lambda r: r["ghg_final"] is not None)

# ── 4. Pay-ratio parse errors ─────────────────────────────────────────────────
def bad_pay(r):
    if not (r["mwp"] and r["mbp"]):
        return False
    return r["mwp"] < dc.MIN_WORKER_PAY or (r["mbp"] / r["mwp"]) > dc.MAX_PAY_RATIO
gate("4 PAY-RATIO parse errors",
     bad_pay, lambda r: r["cf"]["pay_ratio"] is not None)

# ── 5. False-zero female board (SEBI mandates >=1 woman director) ──────────────
gate("5 FALSE-ZERO female board (0%)",
     lambda r: r["raw_fb"] == 0,
     lambda r: r["cf"]["female_board"] == 0)

# ── 6. Coverage gaps (informational, not gating) ──────────────────────────────
print("\n[6] COVERAGE (informational — not gated)")
n = len(rows)
print(f"  carbon usable after cleaning: {sum(1 for r in rows if r['ghg_final'] is not None)}/{n}")
print(f"  scope3 present:               {sum(1 for r in rows if r['ce']['scope3'] is not None)}/{n}")
print(f"  female board present:         {sum(1 for r in rows if r['fb'] is not None)}/{n}")
print(f"  pay ratio usable:            {sum(1 for r in rows if r['cf']['pay_ratio'] is not None)}/{n}")
revs = [r["rev"] for r in rows if r["rev"]]
print(f"  revenue present:             {len(revs)}/{n}  (median Rs {st.median(revs):.0f}cr)")

# ── 7. Displayed-artifact verification (fe_backfill.json output) ───────────────
fe_path = Path(r"c:/Viduti/esg-site/tools/fe_backfill.json")
if fe_path.exists():
    fe = json.loads(fe_path.read_text(encoding="utf-8"))
    # Only magnitude/negative is an error here. A single disclosed zero (e.g. an
    # asset-light services firm with 0 Scope 1 but real Scope 2) is legitimate;
    # the all-zero non-disclosure case is already nulled upstream.
    bad_scope = [n for n, r in fe.items()
                 for kk in ("scope1_emissions_tco2e", "scope2_emissions_tco2e", "scope3_emissions_tco2e")
                 if r.get(kk) is not None and (r[kk] >= dc.EMIS_CEIL or r[kk] < 0)]
    bad_water = [n for n, r in fe.items()
                 if r.get("water_withdrawal_m3") is not None
                 and (r["water_withdrawal_m3"] >= dc.WATER_CEIL or r["water_withdrawal_m3"] < 0)]
    print(f"\n[7] DISPLAYED fe_backfill.json — bad scope: {len(bad_scope)}  bad water: {len(bad_water)}")
    for n in (bad_scope + bad_water)[:5]:
        print(f"    BAD: {n}")
    if bad_scope:
        failures.append(f"{len(bad_scope)} implausible scope value(s) in fe_backfill.json")
    if bad_water:
        failures.append(f"{len(bad_water)} implausible water value(s) in fe_backfill.json")
else:
    print("\n[7] fe_backfill.json not found — skipping displayed-artifact check")

# ── 8. PUBLISHED artifact verification (the file the website + 1,200 pages READ) ─
# This is the gate that was missing: steps 1–7 prove the cleaner CAN neutralise bad
# values, but the website serves assets/data/esg_quotient.json, not fe_backfill.json.
# If clean_published.py was not run before deploy, absurd figures reach production
# while the gate stays green. Verifying the published file closes that gap.
pub_path = Path(r"c:/Viduti/esg-site/assets/data/esg_quotient.json")
if pub_path.exists():
    pub = json.loads(pub_path.read_text(encoding="utf-8")).get("companies", [])
    bad = []
    for c in pub:
        fe = c.get("financial_exposure") or {}
        nm = c.get("company_name", "?")
        for kk in ("scope1_emissions_tco2e", "scope2_emissions_tco2e", "scope3_emissions_tco2e"):
            v = fe.get(kk)
            if v is not None and (v >= dc.EMIS_CEIL or v < 0):
                bad.append(f"{nm}:{kk}={v:,.0f}")
        w = fe.get("water_withdrawal_m3")
        if w is not None and (w >= dc.WATER_CEIL or w < 0):
            bad.append(f"{nm}:water={w:,.0f}")
        wt = fe.get("waste_tonnes")
        if wt is not None and (wt >= dc.WASTE_CEIL or wt < 0):
            bad.append(f"{nm}:waste={wt:,.0f}")
        rev = c.get("revenue_crore")
        if rev is not None and rev <= dc.REV_FLOOR:
            bad.append(f"{nm}:revenue={rev}")
        metrics = (c.get("risk_breakdown") or {}).get("metrics") or {}
        for pf in ("renewable_pct", "waste_recovery_pct", "female_board_pct", "female_kmp_pct"):
            pv = metrics.get(pf)
            if pv is not None and not (0 <= pv <= 100):
                bad.append(f"{nm}:{pf}={pv}")
    print(f"\n[8] PUBLISHED esg_quotient.json — surviving implausible values: {len(bad)}")
    for b in bad[:8]:
        print(f"    BAD: {b}")
    if bad:
        failures.append(f"{len(bad)} implausible value(s) in PUBLISHED esg_quotient.json "
                        f"(run: python tools/clean_published.py && python generate_company_pages.py)")
else:
    print("\n[8] esg_quotient.json not found — skipping published-artifact check")

# ── verdict ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 78)
if failures:
    print("GATE: FAIL")
    for f_ in failures:
        print("  - " + f_)
    if not REPORT_ONLY:
        sys.exit(1)
else:
    print("GATE: PASS — every flagged value is neutralised by tools/data_clean.py")
print("=" * 78)
