"""
add_market_data.py — Fetches market_cap_crore and return_1y_pct for companies
with known NSE symbols using yfinance, then writes back to esg_quotient.json.

Run: python tools/add_market_data.py
"""
import json, time
from pathlib import Path
import yfinance as yf

DATA = Path(__file__).parent.parent / "assets" / "data" / "esg_quotient.json"

blob = json.loads(DATA.read_text(encoding="utf-8"))
cos  = blob["companies"]

# Build index: nse_symbol -> list index
sym_map = {}
for i, c in enumerate(cos):
    sym = c.get("nse_symbol")
    if sym:
        sym_map[sym] = i

print(f"Fetching market data for {len(sym_map)} companies with NSE symbols...")

updated = 0
failed  = []

for sym, idx in sym_map.items():
    try:
        ticker = yf.Ticker(f"{sym}.NS")
        info   = ticker.info

        # yfinance returns marketCap in INR for .NS tickers
        market_cap     = info.get("marketCap")
        week52_change  = info.get("52WeekChange")

        market_cap_crore = round(market_cap / 1e7, 1) if market_cap else None
        return_1y_pct    = round(week52_change * 100, 1) if week52_change is not None else None

        if market_cap_crore or return_1y_pct is not None:
            cos[idx]["market_data"] = {
                "market_cap_crore": market_cap_crore,
                "return_1y_pct":    return_1y_pct,
            }
            updated += 1
            print(f"  OK  {sym:20s} cap={market_cap_crore}Cr  ret1y={return_1y_pct}%")
        else:
            failed.append(sym)
            print(f"  --  {sym}: no data returned")

        time.sleep(0.4)

    except Exception as e:
        failed.append(sym)
        print(f"  ERR {sym}: {e}")

DATA.write_text(json.dumps(blob, ensure_ascii=False, indent=None), encoding="utf-8")
print(f"\nDone. {updated}/{len(sym_map)} updated | {len(failed)} failed: {failed}")
