"""
PROPER PATH — re-extract real Scope 1/2/3 GHG emissions from the raw BRSR XBRL
filings (the data the JSON extraction dropped). Non-destructive: writes a side
file and prints coverage + spread. Nothing touches production.
"""
import re, json, statistics as st
from pathlib import Path
from collections import Counter

XBRL_DIR = Path(r"c:/Viduti/BRSR XBRL PDF/downloads/xbrl")
OUT = Path(r"c:/Viduti/esg-site/tools/emissions_extracted.json")

TAGS = {
    "scope1": "TotalScope1Emissions",
    "scope2": "TotalScope2Emissions",
    "scope3": "TotalScope3Emissions",
    "s12_intensity": "TotalScope1AndScope2EmissionsIntensityPerRupeeOfTurnover",
}

def extract_tag(text, local):
    # all (contextRef, value) pairs for this tag
    pat = re.compile(
        r'<in-capmkt:' + re.escape(local) + r'\b[^>]*contextRef="([^"]+)"[^>]*>([^<]+)</in-capmkt:' + re.escape(local) + r'>'
    )
    hits = pat.findall(text)
    if not hits:
        return None
    # prefer current-year duration context (DCYMain), else any starting DCY, else first
    def pick(pred):
        for ctx, val in hits:
            if pred(ctx):
                return val
        return None
    raw = pick(lambda c: c == "DCYMain") or pick(lambda c: c.startswith("DCY")) or hits[0][1]
    try:
        return float(str(raw).replace(",", "").strip())
    except ValueError:
        return None

def norm(name):
    return re.sub(r'[^a-z0-9]', '', name.lower())

results = {}
files = sorted(XBRL_DIR.glob("*.xml"))
for fp in files:
    company = re.sub(r'_FY\d{2}-\d{2}$', '', fp.stem)
    text = fp.read_text(encoding="utf-8", errors="ignore")
    rec = {k: extract_tag(text, tag) for k, tag in TAGS.items()}
    results[norm(company)] = {"company_name": company, **rec}

OUT.write_text(json.dumps(results, indent=0), encoding="utf-8")

# ---- coverage + spread report ----
def cov(k):
    return sum(1 for v in results.values() if v[k] is not None)
def spread(k):
    vals = sorted(v[k] for v in results.values() if v[k] is not None and v[k] == v[k])
    if len(vals) < 10:
        return "insufficient"
    n = len(vals); q = lambda p: vals[int(p*(n-1))]
    m = st.mean(vals); cvv = st.pstdev(vals)/m if m else 0
    return f"p10={q(.1):.4g} median={q(.5):.4g} p90={q(.9):.4g} | CoV={cvv:.2f}"

print(f"parsed {len(files)} XBRL filings\n")
print("--- REAL emissions coverage (of parsed filings) ---")
for k in TAGS:
    print(f"  {k:14} disclosed by {cov(k):4}  | spread: {spread(k)}")

# match against the scored universe
uni = json.loads(Path(r"c:/Viduti/brsr-generator/backend/data/companies_brsr_slim.json").read_text(encoding="utf-8"))["companies"]
uni_norm = {norm(c["company_name"]): c for c in uni}
matched = sum(1 for nm in uni_norm if nm in results)
both_s12 = sum(1 for nm, c in uni_norm.items() if nm in results and results[nm]["scope1"] is not None and results[nm]["scope2"] is not None)
print(f"\nuniverse companies: {len(uni)}  | name-matched to XBRL: {matched}  | with Scope1+2: {both_s12}")
