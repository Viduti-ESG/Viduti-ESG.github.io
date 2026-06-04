"""
Green Curve — BRSR Anomaly Detection
Adds anomaly_flags to each company in esg_quotient.json.
Two signals:
  1. sector_risk_outlier  — ESG risk score >= 1 std dev above sector mean
  2. waste_intensity_outlier — waste_tonnes/revenue_crore is IQR outlier vs sector
"""

import json, statistics
from collections import defaultdict

DATA_FILE = 'assets/data/esg_quotient.json'

with open(DATA_FILE, encoding='utf-8') as f:
    data = json.load(f)

companies = data['companies']

# ── Signal 1: sector risk score outlier ───────────────────────────────────────
sector_scores = defaultdict(list)
for c in companies:
    sec = (c.get('sector') or '').strip()
    sector_scores[sec].append(c.get('esg_risk_score', 0))

sector_stats = {}
for sec, scores in sector_scores.items():
    if len(scores) >= 3:
        mean = statistics.mean(scores)
        stdev = statistics.stdev(scores) if len(scores) >= 2 else 0
        sector_stats[sec] = (mean, stdev)

# ── Signal 2: waste intensity outlier (sector-relative IQR) ───────────────────
sector_waste = defaultdict(list)
for c in companies:
    wt = c.get('financial_exposure', {}).get('waste_tonnes')
    rev = c.get('revenue_crore')
    if wt and rev and rev > 0:
        sec = (c.get('sector') or '').strip()
        sector_waste[sec].append((c['company_name'], wt / rev))

waste_fence = {}
for sec, vals in sector_waste.items():
    if len(vals) < 4:
        continue
    sv = sorted(v for _, v in vals)
    n = len(sv)
    q1, q3 = sv[n // 4], sv[(3 * n) // 4]
    iqr = q3 - q1
    if iqr > 0:
        waste_fence[sec] = q3 + 1.5 * iqr

# ── Apply flags ────────────────────────────────────────────────────────────────
for c in companies:
    flags = []
    sec = (c.get('sector') or '').strip()
    score = c.get('esg_risk_score', 0)

    if sec in sector_stats:
        mean, stdev = sector_stats[sec]
        if stdev > 0:
            z = (score - mean) / stdev
            if z >= 1.0:
                flags.append({
                    'type': 'sector_risk_outlier',
                    'label': 'Sector Risk Outlier',
                    'detail': f'ESG risk {score} is {z:.1f}σ above sector mean ({mean:.1f})',
                    'severity': 'high' if z >= 2 else 'medium',
                })

    wt = c.get('financial_exposure', {}).get('waste_tonnes')
    rev = c.get('revenue_crore')
    if wt and rev and rev > 0 and sec in waste_fence:
        intensity = wt / rev
        upper = waste_fence[sec]
        if intensity > upper:
            flags.append({
                'type': 'waste_intensity_outlier',
                'label': 'Waste Intensity Outlier',
                'detail': f'Waste intensity {intensity:.1f} t/₹Cr vs sector ceiling {upper:.1f} t/₹Cr',
                'severity': 'medium',
            })

    c['anomaly_flags'] = flags

flagged = sum(1 for c in companies if c.get('anomaly_flags'))
print(f'Flagged {flagged} / {len(companies)} companies')
print(f'  sector_risk_outlier:    {sum(1 for c in companies if any(f["type"] == "sector_risk_outlier" for f in c.get("anomaly_flags", [])))}')
print(f'  waste_intensity_outlier:{sum(1 for c in companies if any(f["type"] == "waste_intensity_outlier" for f in c.get("anomaly_flags", [])))}')

with open(DATA_FILE, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

print(f'Updated {DATA_FILE}')
