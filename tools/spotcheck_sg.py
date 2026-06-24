"""Spot-check that marquee Social/Governance XBRL fields have usable spread."""
import re, statistics as st
from pathlib import Path
XBRL_DIR = Path(r"c:/Viduti/BRSR XBRL PDF/downloads/xbrl")

def vals_for(text, local):
    # all numeric values for a localname (any context); return list of floats
    out = []
    for m in re.finditer(r'<in-capmkt:' + re.escape(local) + r'\b[^>]*>([^<]+)</in-capmkt:' + re.escape(local) + r'>', text):
        try: out.append(float(m.group(1).replace(",", "").strip()))
        except: pass
    return out

FIELDS = {  # (localname, aggregate) -> aggregate: 'first','sum','max'
    "% Female Board":   ("PercentageOfFemaleBoardOfDirectors", "max"),
    "Total Directors":  ("TotalNumberOfBoardOfDirectors", "max"),
    "% Female KMP":     ("PercentageOfFemaleKeyManagementPersonnel", "max"),
    "LTIFR (safety)":   ("LostTimeInjuryFrequencyRatePerOneMillionPersonHoursWorked", "max"),
    "Fatalities":       ("NumberOfFatalities", "sum"),
    "Recordable injuries": ("TotalRecordableWorkRelatedInjuries", "sum"),
    "Median worker pay": ("MedianOfRemunerationOrSalaryOrWagesOfWorkers", "max"),
    "Median board pay":  ("MedianOfRemunerationOrSalaryOrWagesOfBoardOfDirectors", "max"),
    "CoI complaints":    ("NumberOfComplaintsReceivedInRelationToIssuesOfConflictOfInterestOfDirectors", "sum"),
}
AGG = {"max": max, "sum": sum, "first": lambda x: x[0]}

files = sorted(XBRL_DIR.glob("*.xml"))
data = {k: [] for k in FIELDS}
for fp in files:
    t = fp.read_text(encoding="utf-8", errors="ignore")
    for label, (local, agg) in FIELDS.items():
        v = vals_for(t, local)
        if v:
            data[label].append(AGG[agg](v))

N = len(files)
print(f"Spot-check over {N} filings\n{'FIELD':22} {'coverage':>9}  spread")
for label, vals in data.items():
    vals = [x for x in vals if x == x]
    if len(vals) < 10:
        print(f"{label:22} {len(vals):>9}  (sparse)"); continue
    vs = sorted(vals); n = len(vs); q = lambda p: vs[int(p*(n-1))]
    print(f"{label:22} {n:>5} ({100*n//N:2}%)  p10={q(.1):g}  median={q(.5):g}  p90={q(.9):g}")

# derived pay-equity ratio
wp = {fp: None for fp in files}
ratios = []
for fp in files:
    t = fp.read_text(encoding="utf-8", errors="ignore")
    w = vals_for(t, "MedianOfRemunerationOrSalaryOrWagesOfWorkers")
    b = vals_for(t, "MedianOfRemunerationOrSalaryOrWagesOfBoardOfDirectors")
    if w and b and max(w) > 0:
        ratios.append(max(b) / max(w))
if ratios:
    rs = sorted(ratios); n = len(rs); q = lambda p: rs[int(p*(n-1))]
    print(f"\nDerived BOARD:WORKER pay ratio  n={n}  p10={q(.1):.1f}x  median={q(.5):.1f}x  p90={q(.9):.1f}x  (inequality signal)")
