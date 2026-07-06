"""
Sector peer-benchmark engine. Turns each company's disclosed metrics into
competitive context: percentile + quartile vs canonical-sector peers.

Runs AFTER merge_bottlenecks.py (needs energy_mix / safety_metrics / waste_profile
/ ghg_intensity) and BEFORE generate_company_pages.py. Idempotent: rewrites the
`sector_benchmark` key each run. Percentiles are polarity-aware — a "Top 25%"
badge ALWAYS means good, whether the underlying metric is higher-better
(renewable share) or lower-better (injury rate).
"""
import json, statistics as st
from pathlib import Path

from sector_map import classify_sector

QFILE = Path(r"c:/Viduti/esg-site/assets/data/esg_quotient.json")
MIN_PEERS = 8   # need a real distribution before we claim a percentile

# metric_key -> (label, unit, higher_is_better, extractor)
def _rev_rate(c):
    w = c.get("waste_profile") or {}
    tot, rec = w.get("total"), w.get("recovered_recycled")
    if tot and rec is not None and tot > 0:
        return round(min(100.0, 100 * rec / tot), 1)
    return None

METRICS = {
    "renewable_share": ("Renewable Energy Share", "%", True,
        lambda c: (c.get("energy_mix") or {}).get("renewable_share_pct")),
    "waste_recovery":  ("Waste Recovery Rate", "%", True, _rev_rate),
    "safety_ltifr":    ("Lost-Time Injury Rate", "", False,
        lambda c: (c.get("safety_metrics") or {}).get("ltifr_worst")),
    "ghg_intensity":   ("GHG Intensity", " tCO₂e/₹Cr", False,
        lambda c: c.get("ghg_intensity_tco2e_per_cr")),
}

def quartile_label(pctile):
    # pctile is 0..100 where 100 = best (polarity already applied)
    if pctile >= 75: return ("Top 25%", "#34d399")
    if pctile >= 50: return ("Above median", "#a3e635")
    if pctile >= 25: return ("Below median", "#fbbf24")
    return ("Bottom 25%", "#f87171")

doc = json.loads(QFILE.read_text(encoding="utf-8"))
companies = doc["companies"]

# assign canonical sector + gather per-sector metric distributions
for c in companies:
    c["_sec"] = classify_sector(c.get("sector"))

dists = {}   # (sector, metric_key) -> [values]
for c in companies:
    sec = c["_sec"]
    if not sec:
        continue
    for mk, (_l, _u, _hb, fn) in METRICS.items():
        v = fn(c)
        if v is not None:
            dists.setdefault((sec, mk), []).append(v)

def pct_rank(values, x, higher_is_better):
    """Percentile of x within values, 0..100 where 100 = best."""
    n = len(values)
    below = sum(1 for v in values if v < x)
    equal = sum(1 for v in values if v == x)
    # mid-rank percentile (fraction scoring worse-or-tied-below)
    p = 100.0 * (below + 0.5 * equal) / n
    return round(p if higher_is_better else 100 - p, 1)

stats = {"companies": 0, "metrics": 0}
for c in companies:
    sec = c.pop("_sec")
    if not sec:
        c.pop("sector_benchmark", None)
        continue
    peers_by_metric = {}
    out = {}
    for mk, (label, unit, hb, fn) in METRICS.items():
        vals = dists.get((sec, mk), [])
        v = fn(c)
        if v is None or len(vals) < MIN_PEERS:
            continue
        p = pct_rank(vals, v, hb)
        qlabel, qcol = quartile_label(p)
        out[mk] = {
            "label": label, "unit": unit, "value": v,
            "percentile": p, "quartile": qlabel, "color": qcol,
            "sector_median": round(st.median(vals), 2),
            "higher_better": hb,
        }
        stats["metrics"] += 1
        peers_by_metric[mk] = len(vals)
    if out:
        c["sector_benchmark"] = {
            "sector": sec,
            "peer_count": max(peers_by_metric.values()),
            "metrics": out,
        }
        stats["companies"] += 1
    else:
        c.pop("sector_benchmark", None)

QFILE.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

N = len(companies)
print(f"companies: {N}")
print(f"  with a sector benchmark : {stats['companies']} ({100*stats['companies']//N}%)")
print(f"  total benchmarked metrics: {stats['metrics']}")
# per-metric availability
for mk, (label, *_ ) in METRICS.items():
    n = sum(1 for c in companies if (c.get('sector_benchmark') or {}).get('metrics', {}).get(mk))
    print(f"    {label:24} {n}")
# sample
ex = next((c for c in companies if c.get("sector_benchmark")), None)
if ex:
    sb = ex["sector_benchmark"]
    print(f"\nsample: {ex['company_name']} — {sb['sector']} ({sb['peer_count']} peers)")
    for mk, m in sb["metrics"].items():
        print(f"  {m['label']:24} {m['value']}{m['unit']}  →  {m['quartile']} (p{m['percentile']}, sector median {m['sector_median']})")
