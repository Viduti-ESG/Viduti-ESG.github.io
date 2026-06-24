"""
Build meta_backfill.json: per-company top-level fields that score_engine/update_db
do NOT set — financial_year (from the XBRL filename's _FYxx-yy tag, 100% coverage)
and nse_symbol (from the XBRL <in-capmkt:NSESymbol> tag, ~5% — only where the filer
disclosed it, to avoid injecting wrong tickers). Keyed by DB company_name.
"""
import re, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from data_clean import norm

XBRL = Path(r"c:/Viduti/BRSR XBRL PDF/downloads/xbrl")
slim = json.loads(Path(r"c:/Viduti/brsr-generator/backend/data/companies_brsr_slim.json").read_text(encoding="utf-8"))["companies"]

fy, sym = {}, {}
for fp in XBRL.glob("*.xml"):
    k = norm(re.sub(r"_FY\d{2}-\d{2}$", "", fp.stem))
    m = re.search(r"_FY(\d{2})-(\d{2})$", fp.stem)
    if m and k not in fy:
        fy[k] = "20%s-20%s" % (m.group(1), m.group(2))
    if k not in sym:
        sm = re.search(r"<in-capmkt:NSESymbol[^>]*>([^<]+)<", fp.read_text(encoding="utf-8", errors="ignore"))
        if sm:
            v = sm.group(1).strip()
            if v and any(ch.isalpha() for ch in v):
                sym[k] = v

out = {}
for c in slim:
    name = c["company_name"]; k = norm(name)
    rec = {}
    if k in fy:
        rec["financial_year"] = fy[k]
    if k in sym:
        rec["nse_symbol"] = sym[k]
    if rec:
        out[name] = rec

Path(r"c:/Viduti/esg-site/tools/meta_backfill.json").write_text(json.dumps(out), encoding="utf-8")
print(f"meta_backfill: {len(out)} companies")
print(f"  financial_year: {sum(1 for v in out.values() if 'financial_year' in v)}")
print(f"  nse_symbol:     {sum(1 for v in out.values() if 'nse_symbol' in v)}")
