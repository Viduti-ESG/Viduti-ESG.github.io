"""
Full XBRL census — find ALL value-bearing fields across the raw BRSR filings,
so we can see every material ESG signal currently unused by the scorer.
Non-destructive: prints a coverage report grouped by ESG theme.
"""
import re, json
from pathlib import Path
from collections import Counter

XBRL_DIR = Path(r"c:/Viduti/BRSR XBRL PDF/downloads/xbrl")
files = sorted(XBRL_DIR.glob("*.xml"))

# opening tag + leaf text content (non-empty) — document frequency per localname
LEAF = re.compile(r'<in-capmkt:([A-Za-z0-9]+)[^>]*>([^<]+)</in-capmkt:\1>')
docfreq = Counter()
sample = {}
for fp in files:
    text = fp.read_text(encoding="utf-8", errors="ignore")
    seen = set()
    for name, val in LEAF.findall(text):
        if val.strip():
            seen.add(name)
            if name not in sample:
                sample[name] = val.strip()[:48]
    docfreq.update(seen)

N = len(files)
# What the scorer/profiler currently consumes (to flag "unused")
USED = {
    "TotalWasteGenerated","TotalHazardousWasteGenerated","WaterIntensityPerRupeeOfTurnover",
    "TotalEnergyConsumedFromRenewableSources","TotalEnergyConsumedFromNonRenewableSources",
    "EnergyIntensityPerRupeeOfTurnover","TotalScope1Emissions","TotalScope2Emissions",
    "NICCodeOfProductOrServiceSoldByTheEntity","PercentageOfDirectlySourcedFromMSMEsOrSmallProducers",
    "GrievanceRedressalMechanismInPlace","DoesTheEntityHaveAnAntiCorruptionOrAntiBriberyPolicy",
}

THEMES = {
    "GHG / Air emissions": ["scope","emission","ghg","greenhouse","nox","sox","particul","airemission"],
    "Energy": ["energy","fuel","electricit","renewable"],
    "Water": ["water","effluent","discharge"],
    "Waste": ["waste","recycl","hazard","disposed"],
    "Safety / Health (S)": ["safety","fatalit","injur","ltifr","lostTime","accident","occupational","health"],
    "Workforce / Diversity (S)": ["women","female","gender","differentlyabled","diversity","permanentemploy","turnover","retention","wages","minimumwage","training"],
    "Human rights / POSH (S)": ["sexualharass","posh","humanright","childlabour","forcedlabour","discriminat","complaintsfiled"],
    "Fines / Penalties / Ethics (G)": ["fine","penalt","punish","bribery","corrupt","conflictofinterest","legalproceed","disciplinary"],
    "Board / Governance (G)": ["board","independentdirector","director","committee","csr"],
    "Assurance / Disclosure (G)": ["assur","assured","externalagency","reasonableassur","limitedassur"],
    "Green products / Circularity": ["lifecycle","reclaim","recycledinput","sustainablesourc","greenproduct","turnovercontributed"],
}

def matches(name, kws):
    nl = name.lower()
    return any(k in nl for k in kws)

print(f"Census over {N} filings | distinct value-bearing fields: {len(docfreq)}\n")
for theme, kws in THEMES.items():
    hits = [(n, docfreq[n]) for n in docfreq if matches(n, kws) and docfreq[n] >= int(0.30*N)]
    hits.sort(key=lambda x: -x[1])
    if not hits: continue
    print(f"=== {theme} ===")
    for name, df in hits[:12]:
        flag = "  [USED]" if name in USED else "  <-- UNUSED"
        print(f"  {100*df//N:3}%  {name[:60]:60}{flag}")
        # show a value sample for unused high-value ones
    print()
