"""
Green Curve — shared data-quality cleaner.

Single source of truth for the guards that keep bad BRSR-extracted values out of
both the SCORES (score_engine.py) and the DISPLAYED emissions (build_fe_backfill.py).
Previously these guards were duplicated/inconsistent across those two scripts and
absent from the displayed-emissions path; centralising them here means a value the
audit flags is neutralised identically everywhere, and data_quality_audit.py can
assert (and gate on) that neutralisation.

All functions are pure and side-effect free. "Neutralise" == return None so the
value is treated as *not disclosed* rather than as a real zero/figure.
"""
import re

norm = lambda s: re.sub(r'[^a-z0-9]', '', (s or "").lower())

# tCO2e — above NTPC's ~327 Mt (India's largest single emitter). Anything larger
# is a unit/parse error (e.g. figure entered in kg, or digits duplicated).
EMIS_CEIL = 5e8
# ₹ crore — revenue above this outside finance/energy is a parse error, which in
# turn makes every per-revenue intensity derived from it untrustworthy.
REV_CEIL = 400000
REV_OK_SECTORS = {
    "Banking & Finance", "Insurance", "Financial Support Services",
    "Coke & Refined Petroleum", "Oil & Gas Extraction", "Power & Utilities",
}
# Genuine unit errors are caught by comparing a company's carbon intensity to its
# SECTOR PEERS (see sector_intensity_outliers), NOT to its own disclosed-intensity
# field — that field is itself unreliably extracted (garbage for ~130 firms), so
# using it as the arbiter wrongly discarded ~82 companies of good carbon data.
# A scope intensity outside [median/SECTOR_LO_FACTOR? , median*SECTOR_HI_FACTOR] of
# its sector is treated as a magnitude/unit error.
SECTOR_LO_FACTOR = 0.02    # below 2% of the sector median intensity
SECTOR_HI_FACTOR = 50.0    # above 50x the sector median intensity
SECTOR_MIN_PEERS = 8       # need this many peers to trust a sector median

# m³ — no single company withdraws more than India's entire ~760 billion m³/yr
# national total; above this is a unit/parse error (e.g. litres entered as m³).
WATER_CEIL = 1e11

# tonnes — a single company generating >100 Mt of waste a year is implausible for
# any non-mining sector (India's *entire* municipal solid waste is ~62 Mt/yr).
# Mining overburden can exceed this but is reported separately, not as ESG "waste",
# so a figure above the ceiling is treated as a unit/parse error (e.g. kg as tonnes).
WASTE_CEIL = 1e8

# ₹ crore — revenue at/below this on a listed company is a parse artefact (a
# sub-figure or a unit slip): 0 / 0.1 cr "revenue" is never real. Only near-zero
# revenue is unambiguous, so that is all we null here. A revenue that is merely
# "too small for how big the company clearly is" (e.g. SAIL at ₹98.6 cr) is NOT
# detectable without an external truth source — instead the extreme intensity it
# produces is caught by the sector-outlier pass, which nulls the EMISSIONS. (An
# earlier version also nulled revenue when emissions were large; that wrongly
# discarded Amrutanjan's real ₹451 cr revenue and, by removing the denominator,
# stopped the intensity guard from catching its impossible 149 Mt emissions.)
REV_FLOOR = 1.0

# Sector-relative magnitude guard for DISPLAYED emissions. Deliberately far looser
# than the scoring threshold (SECTOR_HI_FACTOR=50): a 50× rule wrongly nulls
# legitimate heavy emitters in heterogeneous sectors (NTPC ~74× its "Power" median),
# so for display we only neutralise egregious magnitude errors (e.g. Amrutanjan at
# ~15,700× the pharma median, Prime Focus at ~3,100×) and keep real outliers.
DISPLAY_SECTOR_HI_FACTOR = 500.0

# pay ratio guards
MIN_WORKER_PAY = 1000      # ₹ — below this the worker-pay cell is a parse artefact
MAX_PAY_RATIO = 500        # board/worker ratio above this is a unit mismatch


def clean_water(v):
    """Null implausibly large water-withdrawal figures (parse/unit errors)."""
    return v if (v is not None and 0 <= v < WATER_CEIL) else None


def clean_waste(v):
    """Null implausibly large waste-generation figures (parse/unit errors)."""
    return v if (v is not None and 0 <= v < WASTE_CEIL) else None


def clean_pct(v):
    """Null percentage-field values outside the only possible range, 0–100.
    Catches field-mapping / scaling errors (e.g. female_kmp_pct = 26,920,000)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if 0 <= f <= 100 else None


def revenue_suspect(rev, sector) -> bool:
    """True when revenue is implausibly large for the sector (parse error)."""
    return bool(rev and rev > REV_CEIL and sector not in REV_OK_SECTORS)


def revenue_suspect_low(rev, s1=None, s2=None) -> bool:
    """True when revenue is at/below REV_FLOOR — a near-zero parse artefact (0 / 0.1
    cr on a listed company is never real, e.g. HCL shown at ₹0). The caller nulls the
    *revenue* only; emissions are kept and judged separately by the intensity guard.
    (s1/s2 are accepted for signature stability but no longer used — see REV_FLOOR.)"""
    return rev is not None and rev <= REV_FLOOR


def clean_emissions(s1, s2, s3, rev, sector):
    """Return cleaned (display-safe) emissions plus a candidate carbon intensity.

    Per-company guards only (magnitude, false-zero, suspect-revenue). Unit/magnitude
    errors that are only detectable relative to peers are handled separately by
    sector_intensity_outliers() over the whole population — call that next and null
    ghg_intensity / scopes where it flags a company.

    Parameters
    ----------
    s1, s2, s3 : raw Scope 1/2/3 tCO2e (any may be None)
    rev : revenue in ₹ crore (or None)
    sector : sector label, used for the revenue-plausibility check

    Returns dict:
      scope1, scope2, scope3 : cleaned values (None where untrustworthy) — for DISPLAY
      ghg_intensity : (S1+S2)/rev in per-crore terms, or None — candidate for SCORING
      flags : list[str] of every issue neutralised (for the audit)
    """
    flags = []
    rev_suspect = revenue_suspect(rev, sector)

    # 1. magnitude outliers — null the individual offending scope
    if s1 is not None and s1 >= EMIS_CEIL:
        s1 = None; flags.append("s1_magnitude")
    if s2 is not None and s2 >= EMIS_CEIL:
        s2 = None; flags.append("s2_magnitude")
    if s3 is not None and (s3 >= EMIS_CEIL or s3 < 0):
        s3 = None; flags.append("s3_magnitude")
    if s3 == 0:                                  # false zero — Scope 3 not disclosed
        s3 = None; flags.append("s3_zero_nondisclosure")

    pair_ok = s1 is not None and s2 is not None

    # 2. false zero — both disclosed but sum is 0 == "not disclosed", not "carbon-neutral"
    if pair_ok and (s1 + s2) == 0:
        s1 = s2 = None; pair_ok = False; flags.append("zero_nondisclosure")

    # carbon intensity candidate (sector-outlier check applied by caller)
    ghg_intensity = None
    if pair_ok and rev and not rev_suspect:
        ghg_intensity = (s1 + s2) / rev
    elif pair_ok and rev_suspect:
        flags.append("rev_suspect")

    return {"scope1": s1, "scope2": s2, "scope3": s3,
            "ghg_intensity": ghg_intensity, "flags": flags}


def sector_intensity_outliers(items):
    """Flag carbon intensities that are implausible *relative to sector peers*.

    Parameters
    ----------
    items : iterable of (key, sector, ghg_intensity) — ghg_intensity may be None

    Returns a set of keys whose intensity is a sector outlier (likely a unit error).
    Sector medians are robust to outliers; sectors with too few peers fall back to
    the overall median so no-peer companies still get a sanity check.
    """
    import statistics as st
    from collections import defaultdict
    by_sec = defaultdict(list)
    allv = []
    for _, sec, inten in items:
        if inten is not None and inten > 0:
            by_sec[sec].append(inten); allv.append(inten)
    med = {s: st.median(v) for s, v in by_sec.items() if len(v) >= SECTOR_MIN_PEERS}
    overall = st.median(allv) if allv else None
    out = set()
    for key, sec, inten in items:
        if inten is None or inten <= 0:
            continue
        m = med.get(sec, overall)
        if m and not (SECTOR_LO_FACTOR * m <= inten <= SECTOR_HI_FACTOR * m):
            out.add(key)
    return out


# A company cannot recover more waste than it generated in the same period — it is a
# mass-balance impossibility. We allow only a 0.1% float/rounding tolerance; beyond
# that the recovery split is a disclosure error and is treated as not-disclosed
# rather than shown as an impossible >100%-of-generation figure. A trusted ESG
# platform must NEVER display "recovered > generated" to an analyst.
RECOVERY_MAX_FACTOR = 1.001


def clean_recovery(recovered, disposed, generated):
    """Return (recovered, disposed), nulled together when recovered grossly exceeds
    generation. Keeps score and displayed recovery bounded and physically sane."""
    if (recovered is not None and generated
            and recovered > RECOVERY_MAX_FACTOR * generated):
        return None, None
    return recovered, disposed


def clean_features(f: dict):
    """Clean governance/diversity features prone to parse errors.

    Returns dict: pay_ratio, female_board (fraction 0-1), flags.
    """
    flags = []
    mwp, mbp = f.get("median_worker_pay"), f.get("median_board_pay")
    fbc, td = f.get("female_board_count"), f.get("total_directors")

    # pay ratio — reject parse-artefact worker pay and impossible ratios
    pay_ratio = None
    if mwp and mbp:
        if mwp < MIN_WORKER_PAY:
            flags.append("worker_pay_parse")
        else:
            pr = mbp / mwp
            if pr > MAX_PAY_RATIO:
                flags.append("pay_ratio_extreme")
            else:
                pay_ratio = pr

    # female board — prefer count/total (robust to the 0%-percentage parse bug)
    female_board = (fbc / td) if (fbc is not None and td) else f.get("pct_female_board")
    if female_board == 0:
        # SEBI mandates >=1 woman director on listed boards -> 0 is a parse failure
        female_board = None
        flags.append("female_board_zero")

    return {"pay_ratio": pay_ratio, "female_board": female_board, "flags": flags}


def select_canonical_filings(paths, prefer_fy="FY24-25"):
    """One XBRL filing per company, so every extractor reads the SAME reporting year.

    Some companies filed more than one year (e.g. an early FY25-26 alongside the
    standard FY24-25). If different pipelines pick different files the score and the
    displayed figures silently disagree. We prefer the canonical BRSR cycle
    (FY24-25); where it is absent we fall back to the latest available year.

    paths: iterable of pathlib.Path (…/COMPANY_FYxx-yy.xml). Returns a filtered list.
    """
    import re as _re
    from pathlib import Path as _Path
    best = {}   # norm(company) -> (is_non_preferred 0/1, fy_string, path_str)
    for p in paths:
        stem = _Path(p).stem
        company = _re.sub(r'_FY\d{2}-\d{2}$', '', stem)
        m = _re.search(r'_FY(\d{2}-\d{2})$', stem)
        fy = ("FY" + m.group(1)) if m else ""
        cand = (0 if fy == prefer_fy else 1, fy, str(p))
        cur = best.get(norm(company))
        # prefer the canonical year (rank 0); within the same rank keep the latest fy
        if cur is None or (cand[0] < cur[0]) or (cand[0] == cur[0] and cand[1] > cur[1]):
            best[norm(company)] = cand
    return [_Path(v[2]) for v in best.values()]


def dedupe_companies(companies, name_key="company_name"):
    """Collapse case-variant duplicate company rows, keeping the most complete.

    Most complete == largest serialised record; ties broken by original order.
    Returns (deduped_list, dropped_list_of_names).
    """
    import json
    best = {}            # norm -> (completeness, original_index, record)
    order = []           # norm in first-seen order
    dropped = []
    for i, c in enumerate(companies):
        k = norm(c.get(name_key, ""))
        comp = len(json.dumps(c, ensure_ascii=False))
        if k not in best:
            best[k] = (comp, i, c); order.append(k)
        else:
            prev_comp, prev_i, prev_c = best[k]
            if comp > prev_comp:
                dropped.append(prev_c.get(name_key, ""))
                best[k] = (comp, i, c)
            else:
                dropped.append(c.get(name_key, ""))
    return [best[k][2] for k in order], dropped
