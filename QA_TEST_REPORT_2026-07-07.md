# Green Curve — Data & Tools QA Test Report
**Date:** 2026-07-07  **Tester role:** Senior QA (formulas, data quality, embedded tools)
**Ground truth:** 1,222 BRSR XBRL filings in `C:\Viduti\BRSR XBRL PDF\downloads\xbrl`

---

## Verdict
The scoring **formulas** and the **GHG calculator** are sound. The **XBRL extraction layer has one systemic bug** that corrupts waste-recovery (and, to a lesser degree, fines / conflict-of-interest / LTIFR) for the majority of companies, and the **data-quality audit gate has a blind spot** that let it through. Plus a set of medium/low content-consistency issues.

---

## CRITICAL

### C1. Prior-year data leaks into "current-year" extraction (`is_cy` bug)
- **File:** `tools/build_features.py:21-23`
- `is_cy("DPYMain")` returns **True**. The prior-year marker in BRSR contexts is the *P* inside `D**P**YMain`, but the function only looks for a `_py` suffix / a `"py"` split-segment. So every field built with `sum_cy()` / `max_cy()` silently **adds the previous reporting year**.
- **Proven:** SAIL `waste_recovered` = 29,735,603 t = 15,365,364 (FY24-25) **+** 14,370,239 (FY23-24). XBRL current-year total is 15,365,364.
- **Population impact (vs XBRL):**
  - **517 companies** now show `waste_recovered > waste_generated` — physically impossible.
  - **640 companies** inflated >1.5× the true current-year figure.
- **Consequences:**
  1. `waste_recovery_pct` display metric overstated (SAIL shows 96.8%).
  2. **Waste sub-score corrupted:** `waste = clamp(waste − 3·recovery)` over-credits circularity → understates waste/environmental risk for those 517+ companies.
  3. `fines_amount` (461 cos) and `coi_complaints` double-count prior-year → overstated compliance risk.
  4. `ltifr` uses `max_cy` → can pick the prior year's higher rate.
- **Fix:** correct `is_cy` to treat any context containing `dpy`/`_py`/`prior` (and the `DPYMain` form) as prior-year, e.g. exclude when `'dpy' in c or c.endswith('_py') or 'prior' in c`. Then rebuild `raw_features.json` → rescore → regenerate pages. **Affects live data.**

### C2. Two contradictory waste-recovery numbers on the same company page
- The ESG-Quotient block shows **Waste Recovered 96.8%** (`rescored.json`, inflated per C1), while the "Waste Recovery Rate" bar shows **13.2%** (`waste_profile`, computed as *recycled-only ÷ generated*). For SAIL both appear on one page.
- Neither is defensible: true current-year recovered (15.37 Mt) already exceeds generated (14.14 Mt) in the *source* filing. Need one reconciled, sanity-checked definition (and cap recovery ≤ generated).

---

## HIGH

### H1. DQ audit gate has no waste-plausibility check
- `tools/data_quality_audit.py` **PASSES** (exit 0) yet never validates `recovered ≤ generated` or recovery-percent bounds — which is exactly why C1 slipped through. Add a gated check: flag/neutralise any company where `waste_recovered > waste_generated` (with tolerance) and where recovery% > 100.

### H2. India grid factor inconsistency across the product
- Calculator (authoritative): **CEA All-India 0.7117 kg CO₂e/kWh** (V21.0, FY24-25) — correct and well-implemented.
- `assets/data/ghg_estimates.json` methodology text still states **"India CEA grid factor: 0.82 kg CO₂/kWh."**
- Same platform, two different India grid factors. Reconcile `ghg_estimates.json` to 0.7117 (or clearly state the older vintage and why).

---

## MEDIUM

### M1. Unrounded scores rendered to users
- **658 / 1,221** companies expose a raw float `waste_intensity` (e.g. `6.794706069389472`, `3.051060380926651`) in `risk_breakdown` because `clamp(waste − 3·recovery)` is never rounded (`score_engine.py:117`). Every sibling score is rounded to 1 dp. Round it.

### M2. Source-data female-board extraction gaps
- 31 companies have `female_board_count = 0` / `pct_female_board = 0` (e.g. SAIL), impossible under SEBI's ≥1-woman-director mandate — a parse miss. The guard correctly *nulls* these (so scores aren't wrong), but the underlying diversity signal is simply missing for those firms. Consider a secondary extraction path.

---

## PASSED / VERIFIED CLEAN (positives)
- **Scope 1 & Scope 2 extraction:** 0 mismatches across 1,223 companies vs XBRL (`main_val` correctly prefers `DCYMain`).
- **Fatalities / recordable injuries:** correct — use explicit CY-only contexts (`sum_ctx`), unaffected by C1. SAIL = 1 employee + 5 workers = 6 ✓.
- **Revenue fix (SAIL etc.):** correct — platform uses `TotalRevenueOfTheCompany` (₹1,02,478 cr), not the company's mis-scaled `RevenueFromOperations` (₹98.57 cr). Confirmed against XBRL.
- **GHG calculator arithmetic:** correct — kg→tonnes `/1000`, CEA `tCO₂/MWh ≡ kg/kWh` handled with an explicit correct comment, commute round-trip applied, spend-estimator avoids double-division.
- **GHG factor library:** DEFRA 2021 values verified (Butane 0.2224 / 1.74529 etc.); licence provenance clean (DEFRA-OGL / IFI / Cornell only).
- **Existing data-clean guards:** emission magnitude, false-zero, sector-outlier, pay-ratio, female-board-zero all fire and are gated correctly (audit shows every flagged value neutralised).
- **Company pages** correctly label undisclosed values "Not disclosed" and do not blend estimates into disclosed figures.

---

## 🔴🔴 BIGGEST FINDING (discovered during fix) — the LIVE site runs the OLD broken scoring
While wiring in the fixes I discovered the corrected v2 engine (`score_engine.py` → `tools/rescored.json`) **was never published**. The live source of truth, `assets/data/esg_quotient.json` (which `migrate_to_db.py` rebuilds the production DB from), still holds the **old flat-score methodology** for **all 1,227 companies**:
- 0 / 1,227 have the v2 pillars (environmental/social/governance) or the metrics dict.
- `waste_intensity` is a flat default for most firms: **551 companies = exactly 1.0**, 156 = 5.0, 49 = 10.0 — the field-mapping bug (`project_scoring_methodology_v2`).
- So the ESG Quotient scores shown publicly today are largely **placeholder/flat**, not real percentile scoring.

The `is_cy` bug (C1) therefore currently corrupts only the **unpublished** v2 pipeline — my fix ensures v2 is correct **when** it is published. But the live scores being flat is the real trust gap.

**Decision required (large, outward-facing, hard to reverse):** publish the corrected v2 scoring. This changes ~1,195 companies' public ESG scores (mean Δ≈1.5, max≈5.1). Recommended, but needs sign-off before deploy.

## ✅ DEPLOYED TO PRODUCTION — 2026-07-07 (commit 8f0aeb72)
- Pushed to GitHub → VM `git pull --ff-only` → DB backup → `chown www-data` → `migrate_to_db.py` (rebuilt DB, 1,221 updated) → deleted 6 stale case-variant rows (DB 1227 → 1,221) → restarted `greencurve-api`.
- **Verified live via Cloudflare:** homepage 200; `/api/esg/stats` → `{total:1221, high:410, medium:425, low:386}`; SAIL page serves score 7.5/High with "Waste Recovered → Not disclosed" (mass-balance guard live).
- **Owner call:** `RECOVERY_MAX_FACTOR` set to 1.001 — zero companies can display recovered > generated.

## Fix status (code — DONE)
- ✅ C1 `is_cy` fixed; verified: SAIL waste_recovered 29.74M → 15.37M (exact XBRL); impossible recovered>generated 517 → 44 (residual = genuine source inconsistencies, now nulled by `clean_recovery`).
- ✅ M1 scores rounded (658 → 0 unrounded).
- ✅ C2 recovery reconciled to one definition (recovered ÷ (recovered+disposed), capped) across score + benchmark + page.
- ✅ H1 audit gate added (`[5b]` waste-recovery regression guard).
- ✅ H2 India grid factor text aligned to CEA 0.7117 (`predict_ghg.py` + `ghg_estimates.json`).
- ✅ Bonus: nulled a female-KMP parse artefact (Nandan Denim 269200%) that skewed diversity rank/display.

## Suggested fix order
1. **C1** `is_cy` (root cause) → rebuild features → rescore → regenerate pages.
2. **H1** add waste-plausibility gate so C1-class errors can't recur.
3. **C2** reconcile the two recovery numbers + cap recovery ≤ generated.
4. **M1** round `waste_intensity`; **H2**/**M2** cleanups.
