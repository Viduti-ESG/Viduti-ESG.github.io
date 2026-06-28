"""
expand_nse_symbols.py — Matches company names in esg_quotient.json against the
NSE equity list (downloaded live), assigns nse_symbol where missing, then fetches
market_cap_crore and return_1y_pct for newly mapped companies.

Run: python tools/expand_nse_symbols.py
"""
import json, re, time, io, csv
from pathlib import Path
from difflib import SequenceMatcher
import requests, yfinance as yf

DATA = Path(__file__).parent.parent / "assets" / "data" / "esg_quotient.json"

# ── 1. Download NSE equity list ───────────────────────────────────────────────
print("Downloading NSE equity list...")
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
session.get("https://www.nseindia.com", timeout=15)
r = session.get(
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv", timeout=30
)
r.raise_for_status()

nse_map = {}   # normalised_name -> NSE symbol
reader = csv.DictReader(io.StringIO(r.text))
for row in reader:
    sym  = row.get("SYMBOL", "").strip()
    name = row.get("NAME OF COMPANY", "").strip()
    if sym and name:
        nse_map[sym] = name

print(f"NSE equity list: {len(nse_map)} symbols")

# ── 2. Name normalisation ─────────────────────────────────────────────────────
_STOP = re.compile(
    r"\b(limited|ltd|private|pvt|llp|company|co|india|industries|"
    r"enterprises|holdings|group|solutions|services|technologies|"
    r"manufacturing|corporation|corp)\b",
    re.I,
)
_PUNCT = re.compile(r"[^a-z0-9 ]")

def norm(s: str) -> str:
    s = s.lower()
    s = _STOP.sub(" ", s)
    s = _PUNCT.sub(" ", s)
    return " ".join(s.split())

# Pre-build normalised NSE lookup
nse_norm = {norm(name): sym for sym, name in nse_map.items()}

# ── 3. Load esg_quotient.json ─────────────────────────────────────────────────
blob = json.loads(DATA.read_text(encoding="utf-8"))
cos  = blob["companies"]

already = sum(1 for c in cos if c.get("nse_symbol"))
print(f"Companies already with nse_symbol: {already}")

# ── 4. Fuzzy match ────────────────────────────────────────────────────────────
EXACT_THRESHOLD = 0.92
new_symbols = {}   # idx -> symbol

for i, c in enumerate(cos):
    if c.get("nse_symbol"):
        continue
    cname_norm = norm(c["company_name"])
    if not cname_norm:
        continue

    # Exact lookup first
    if cname_norm in nse_norm:
        new_symbols[i] = nse_norm[cname_norm]
        continue

    # Fuzzy scan — only score against plausible candidates (first-word prefix filter)
    first_word = cname_norm.split()[0] if cname_norm.split() else ""
    candidates = {
        n: s for n, s in nse_norm.items()
        if n.startswith(first_word[:3]) if first_word
    }
    best_score, best_sym = 0.0, None
    for nname, nsym in candidates.items():
        score = SequenceMatcher(None, cname_norm, nname).ratio()
        if score > best_score:
            best_score, best_sym = score, nsym

    if best_score >= EXACT_THRESHOLD and best_sym:
        new_symbols[i] = best_sym

print(f"Fuzzy match found {len(new_symbols)} new symbols")

# Assign symbols
for idx, sym in new_symbols.items():
    cos[idx]["nse_symbol"] = sym

# ── 5. Fetch market data for newly mapped companies ───────────────────────────
print(f"\nFetching market data for {len(new_symbols)} newly mapped companies...")
updated, failed = 0, []

for idx, sym in new_symbols.items():
    try:
        ticker = yf.Ticker(f"{sym}.NS")
        info   = ticker.info
        market_cap    = info.get("marketCap")
        week52_change = info.get("52WeekChange")

        market_cap_crore = round(market_cap / 1e7, 1) if market_cap else None
        return_1y_pct    = round(week52_change * 100, 1) if week52_change is not None else None

        if market_cap_crore or return_1y_pct is not None:
            cos[idx]["market_data"] = {
                "market_cap_crore": market_cap_crore,
                "return_1y_pct":    return_1y_pct,
            }
            updated += 1
            print(f"  OK  {sym:16s} {cos[idx]['company_name'][:40]}")
        else:
            failed.append(sym)
            print(f"  --  {sym}: no data")

        time.sleep(0.3)

    except Exception as e:
        failed.append(sym)
        print(f"  ERR {sym}: {e}")

# ── 6. Write back ─────────────────────────────────────────────────────────────
DATA.write_text(json.dumps(blob, ensure_ascii=False, indent=None), encoding="utf-8")

total_with_mkt = sum(1 for c in cos if c.get("market_data"))
total_with_sym = sum(1 for c in cos if c.get("nse_symbol"))
print(f"\nDone.")
print(f"  nse_symbol coverage: {total_with_sym}/{len(cos)}")
print(f"  market_data coverage: {total_with_mkt}/{len(cos)}")
print(f"  New market data added: {updated}")
if failed:
    print(f"  Failed ({len(failed)}): {failed[:20]}")
