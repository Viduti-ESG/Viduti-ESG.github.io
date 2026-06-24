"""
ONE-PASS XBRL feature extraction for the 3-pillar ESG Quotient rebuild.
Pulls every raw E/S/G signal we need from the 1,254 raw filings -> raw_features.json
Non-destructive.
"""
import re, json
from pathlib import Path

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

def is_cy(ctx):  # current year = not prior-year
    c = ctx.lower()
    return not ("py" in c.split("_")[-1:] or "prior" in c) and not c.endswith("_py")

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
    m = re.search(r'<in-capmkt:' + re.escape(local) + r'\b[^>]*>([^<]+)</in-capmkt:' + re.escape(local) + r'>', text)
    return bool(m and m.group(1).strip().lower() in ("true", "yes"))

EW = {"D_Employees", "D_Workers"}  # current-year employee + worker split

results = {}
files = sorted(XBRL_DIR.glob("*.xml"))
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
        "zld": text_present(t, "HasTheEntityImplementedAMechanismForZeroLiquidDischarge"),
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
        "csr_applicable": text_present(t, "WhetherCSRIsApplicableAsPerSection135OfCompaniesAct2013"),
    }
    results[norm(company)] = f

OUT.write_text(json.dumps(results), encoding="utf-8")

# coverage report
def cov(k): return sum(1 for v in results.values() if v.get(k) not in (None, False))
print(f"extracted {len(results)} companies -> {OUT.name}\n{'feature':22} coverage")
for k in list(next(iter(results.values())).keys()):
    print(f"  {k:22} {cov(k):4} ({100*cov(k)//len(results)}%)")
