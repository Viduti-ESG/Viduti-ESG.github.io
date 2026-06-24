"""
Extract NIC industrial codes from raw XBRL -> build a clean sector taxonomy.
Non-destructive: writes a side file + prints the division distribution.
NIC 2008: first 2 digits = division; we use the division as the ESG peer group
(carbon intensity varies hugely *within* manufacturing, so division is the right
granularity), with a human-readable label.
"""
import re, json
from pathlib import Path
from collections import Counter

XBRL_DIR = Path(r"c:/Viduti/BRSR XBRL PDF/downloads/xbrl")
OUT = Path(r"c:/Viduti/esg-site/tools/sectors_extracted.json")
norm = lambda s: re.sub(r'[^a-z0-9]', '', s.lower())

# NIC 2008 two-digit division -> readable label (only divisions likely in a listed universe)
DIVISION = {
    "01":"Agriculture","02":"Forestry","03":"Fishing","05":"Coal Mining","06":"Oil & Gas Extraction",
    "07":"Metal Ore Mining","08":"Other Mining","09":"Mining Support",
    "10":"Food Products","11":"Beverages","12":"Tobacco","13":"Textiles","14":"Apparel","15":"Leather",
    "16":"Wood Products","17":"Paper","18":"Printing","19":"Coke & Refined Petroleum","20":"Chemicals",
    "21":"Pharmaceuticals","22":"Rubber & Plastics","23":"Cement & Non-Metallic Minerals","24":"Basic Metals",
    "25":"Fabricated Metal","26":"Electronics & Optical","27":"Electrical Equipment","28":"Machinery",
    "29":"Motor Vehicles","30":"Other Transport Equipment","31":"Furniture","32":"Other Manufacturing","33":"Repair/Installation",
    "35":"Power & Utilities","36":"Water Supply","37":"Sewerage","38":"Waste Management","39":"Remediation",
    "41":"Building Construction","42":"Civil Engineering","43":"Specialized Construction",
    "45":"Vehicle Trade","46":"Wholesale Trade","47":"Retail Trade",
    "49":"Land Transport","50":"Water Transport","51":"Air Transport","52":"Warehousing","53":"Postal/Courier",
    "55":"Accommodation","56":"Food & Beverage Service",
    "58":"Publishing","59":"Media Production","60":"Broadcasting","61":"Telecom","62":"IT Services","63":"Information Services",
    "64":"Banking & Finance","65":"Insurance","66":"Financial Support Services",
    "68":"Real Estate",
    "69":"Legal & Accounting","70":"Head Office/Consulting","71":"Architecture & Engineering","72":"R&D",
    "73":"Advertising","74":"Other Professional","75":"Veterinary",
    "77":"Rental & Leasing","78":"Employment","79":"Travel","80":"Security","81":"Facilities","82":"Business Support",
    "84":"Public Admin","85":"Education","86":"Health","87":"Residential Care","88":"Social Work",
    "90":"Arts","91":"Libraries & Museums","92":"Gambling","93":"Sports & Recreation",
    "94":"Membership Orgs","95":"Repair","96":"Other Personal Services",
}

def extract_nic(text):
    pat = re.compile(
        r'<in-capmkt:NICCodeOfProductOrServiceSoldByTheEntity\b[^>]*contextRef="(D_ProductServiceSold\d+)"[^>]*>([^<]+)</in-capmkt:NICCodeOfProductOrServiceSoldByTheEntity>'
    )
    hits = pat.findall(text)
    codes = []
    for ctx, val in sorted(hits):  # D_ProductServiceSold1 first = primary
        digits = re.sub(r'\D', '', val)
        if len(digits) >= 2:
            codes.append(digits)
    return codes

results = {}
for fp in sorted(XBRL_DIR.glob("*.xml")):
    company = re.sub(r'_FY\d{2}-\d{2}$', '', fp.stem)
    codes = extract_nic(fp.read_text(encoding="utf-8", errors="ignore"))
    div = codes[0][:2] if codes else None
    results[norm(company)] = {
        "company_name": company,
        "nic": codes[0] if codes else None,
        "division": div,
        "sector": DIVISION.get(div, f"NIC-{div}" if div else "Unclassified"),
    }
OUT.write_text(json.dumps(results, indent=0), encoding="utf-8")

# report against the scored universe
uni = json.loads(Path(r"c:/Viduti/brsr-generator/backend/data/companies_brsr_slim.json").read_text(encoding="utf-8"))["companies"]
uni_secs = Counter()
matched = unclass = 0
for c in uni:
    r = results.get(norm(c["company_name"]))
    if r and r["division"]:
        uni_secs[r["sector"]] += 1; matched += 1
    else:
        unclass += 1
print(f"universe {len(uni)} | NIC-classified {matched} | unclassified {unclass}")
print(f"clean sectors: {len(uni_secs)} (was 1,096 free-text strings)")
big = sum(1 for v in uni_secs.values() if v >= 10)
print(f"sectors with >=10 cos: {big} | >=5: {sum(1 for v in uni_secs.values() if v>=5)}")
print("\n--- sector distribution (NIC division) ---")
for s, n in uni_secs.most_common():
    bar = "#" * (n // 3)
    print(f"  {n:4}  {s:32} {bar}")
