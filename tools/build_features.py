"""
ONE-PASS XBRL feature extraction for the 3-pillar ESG Quotient rebuild.
Pulls every raw E/S/G signal we need from the 1,254 raw filings -> raw_features.json
Non-destructive.
"""
import re, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import data_clean as dc  # shared canonical-filing selector

XBRL_DIR = Path(r"c:/Viduti/BRSR XBRL PDF/downloads/xbrl")
OUT = Path(r"c:/Viduti/esg-site/tools/raw_features.json")
norm = lambda s: re.sub(r'[^a-z0-9]', '', s.lower())

def pairs(text, local):
    """All (contextRef, float_value) for a localname."""
    out = []
    for m in re.finditer(r'<in-capmkt:' + re.escape(local) + r'\b[^>]*contextRef="([^"]+)"[^>]*>([^<]+)</in-capmkt:' + re.escape(local) + r'>', text):
        try: out.append((m.group(1), float(m.group(2).replace(",", "").strip())))
        except: pass
    return out

def is_cy(ctx):  # current year = NOT a prior-year context
    c = ctx.lower()
    # BRSR encodes the prior year as "DPYMain" (the P in D-PY-Main), a trailing
    # "_py" (e.g. D_Employees_PY), or the literal word "prior". Current-year
    # contexts (DCYMain, D_Employees, D_Workers, ...) match none of these.
    # NB: the previous test ('py' in c.split('_')[-1:]) never matched "DPYMain"
    # because that segment is "dpymain", not "py" — so prior-year data leaked into
    # every sum_cy/max_cy field (waste_recovered doubled, fines/coi inflated).
    return not (c.startswith("dpy") or c.endswith("_py") or "prior" in c)

def main_val(text, local):
    p = pairs(text, local)
    for ctx, v in p:
        if ctx == "DCYMain": return v
    cy = [v for ctx, v in p if is_cy(ctx)]
    return cy[0] if cy else (p[0][1] if p else None)

def sum_ctx(text, local, ctxs):
    p = pairs(text, local)
    vals = [v for ctx, v in p if ctx in ctxs]
    return sum(vals) if vals else None

def max_cy(text, local):
    p = [v for ctx, v in pairs(text, local) if is_cy(ctx)]
    return max(p) if p else None

def sum_cy(text, local):
    p = [v for ctx, v in pairs(text, local) if is_cy(ctx)]
    return sum(p) if p else None

def text_present(text, local):
    m = re.search(r'<in-capmkt:' + re.escape(local) + r'\b[^>]*>([^<]+)</in-capmkt:' + re.escape(local) + r'>', text)
    return bool(m and m.group(1).strip())

def text_yes(text, local):
    """True only when the filing's ANSWER is affirmative.

    BRSR yes/no elements are not a clean boolean enumeration. The assurance
    question answers "Yes Assurance" / "Yes Assessment" / "No", so an exact
    match on ("true","yes") matched ZERO of the 1,254 filings and every
    "assured" company was arriving via the external-agency fallback below —
    102 companies that filed "No" were coded assured and 20 that filed
    "Yes Assurance" were not (Coal India, Central Bank of India among them).
    Match on the affirmative prefix instead, and never on mere presence:
    `text_present` cannot tell "No" from "Yes" and must not be used for a
    yes/no question.
    """
    m = re.search(r'<in-capmkt:' + re.escape(local) + r'\b[^>]*>([^<]+)</in-capmkt:' + re.escape(local) + r'>', text)
    if not m:
        return False
    v = m.group(1).strip().lower()
    return v in ("true", "1") or v.startswith("yes")

EW = {"D_Employees", "D_Workers"}  # current-year employee + worker split

results = {}
files = sorted(dc.select_canonical_filings(XBRL_DIR.glob("*.xml")))
for fp in files:
    company = re.sub(r'_FY\d{2}-\d{2}$', '', fp.stem)
    t = fp.read_text(encoding="utf-8", errors="ignore")
    f = {
        # E
        "scope1": main_val(t, "TotalScope1Emissions"),
        "scope2": main_val(t, "TotalScope2Emissions"),
        "energy_renew": main_val(t, "TotalEnergyConsumedFromRenewableSources"),
        "energy_nonrenew": main_val(t, "TotalEnergyConsumedFromNonRenewableSources"),
        "energy_intensity": main_val(t, "EnergyIntensityPerRupeeOfTurnover"),
        "water_intensity": main_val(t, "WaterIntensityPerRupeeOfTurnover"),
        "waste_total": main_val(t, "TotalWasteGenerated"),
        "waste_recovered": (sum_cy(t, "WasteRecoveredThroughReUsed") or 0) + (sum_cy(t, "WasteRecoveredThroughRecycled") or 0) + (sum_cy(t, "WasteRecoveredThroughOtherRecoveryOperations") or 0),
        "waste_disposed": main_val(t, "TotalWasteDisposed"),
        # text_present here meant "the company answered the ZLD question at all",
        # so all 1,223 companies were published as having ZLD — 295 filings say
        # "no" and 212 say "na". It is displayed on company pages, so this was a
        # false environmental claim about named companies, not just a bad score.
        "zld": text_yes(t, "HasTheEntityImplementedAMechanismForZeroLiquidDischarge"),
        # S — safety
        "fatalities": sum_ctx(t, "NumberOfFatalities", EW),
        "recordable_injuries": sum_ctx(t, "TotalRecordableWorkRelatedInjuries", EW),
        "ltifr": max_cy(t, "LostTimeInjuryFrequencyRatePerOneMillionPersonHoursWorked"),
        "ohs_system": text_yes(t, "WhetherAnOccupationalHealthAndSafetyManagementSystemHasBeenImplementedByTheEntity"),
        # S — diversity / wages
        "pct_female_board": main_val(t, "PercentageOfFemaleBoardOfDirectors"),
        "female_board_count": main_val(t, "NumberOfFemaleBoardOfDirectors"),
        "pct_female_kmp": main_val(t, "PercentageOfFemaleKeyManagementPersonnel"),
        "median_worker_pay": main_val(t, "MedianOfRemunerationOrSalaryOrWagesOfWorkers"),
        "median_board_pay": main_val(t, "MedianOfRemunerationOrSalaryOrWagesOfBoardOfDirectors"),
        # G — board / ethics / assurance
        "total_directors": main_val(t, "TotalNumberOfBoardOfDirectors"),
        "fines_amount": sum_cy(t, "AmountOfFinesOrPenalties"),
        "coi_complaints": (sum_cy(t, "NumberOfComplaintsReceivedInRelationToIssuesOfConflictOfInterestOfTheDirectors") or 0) + (sum_cy(t, "NumberOfComplaintsReceivedInRelationToIssuesOfConflictOfInterestOfTheKMPs") or 0),
        "anti_corruption": text_yes(t, "DoesTheEntityHaveAnAntiCorruptionOrAntiBriberyPolicy"),
        "brsr_assured": text_yes(t, "WhetherTheCompanyHasUndertakenAssessmentOrAssuranceOfTheBRSRCore") or text_present(t, "NameOfTheExternalAgencyThatUndertookIndependentAssessmentOrEvaluationOrAssuranceForGreenHouseGasEmissionsExplanatoryTextBlock"),
        # same text_present bug as zld (86 filings say "false"); currently
        # written and never read, fixed before anything starts reading it
        "csr_applicable": text_yes(t, "WhetherCSRIsApplicableAsPerSection135OfCompaniesAct2013"),
    }
    results[norm(company)] = f

OUT.write_text(json.dumps(results), encoding="utf-8")

# coverage report
def cov(k): return sum(1 for v in results.values() if v.get(k) not in (None, False))
print(f"extracted {len(results)} companies -> {OUT.name}\n{'feature':22} coverage")
for k in list(next(iter(results.values())).keys()):
    print(f"  {k:22} {cov(k):4} ({100*cov(k)//len(results)}%)")
