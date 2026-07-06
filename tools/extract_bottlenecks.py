"""
Extract per-company "bottlenecks" (BRSR self-disclosed material issues) plus the
100%-coverage hard S/E metrics the site never surfaced (safety, energy mix, waste
breakdown) from the raw BRSR XBRL filings.

Keyed by CIN (robust join to esg_quotient.json). Non-destructive: writes a side
file tools/bottlenecks_extracted.json and prints a coverage report. Nothing
touches production.

BRSR facts repeat per reporting period (current vs prior year) and, for safety,
per cohort (employees vs workers). We always take the CURRENT year:
  - duration facts   -> contextRef "DCYMain"      (prior year = "DPYMain")
  - safety facts     -> contextRef "D_Employees" / "D_Workers"  (prior = *_PY)
"""
import re, json, statistics as st
from pathlib import Path
from collections import Counter

XBRL_DIR = Path(r"c:/Viduti/BRSR XBRL PDF/downloads/xbrl")
OUT      = Path(r"c:/Viduti/esg-site/tools/bottlenecks_extracted.json")

# ── low-level fact readers ──────────────────────────────────────────────────
def _facts(text, local):
    """Return list of (contextRef, raw_value) for a leaf tag, in document order."""
    pat = re.compile(
        r'<in-capmkt:' + re.escape(local) +
        r'\b[^>]*contextRef="([^"]+)"[^>]*>([^<]*)</in-capmkt:' + re.escape(local) + r'>'
    )
    return pat.findall(text)

def _num(raw):
    try:
        return float(str(raw).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None

def scalar(text, local, prefer=("DCYMain",), startswith=("DCY",)):
    """Single current-year numeric fact."""
    hits = _facts(text, local)
    if not hits:
        return None
    for want in prefer:
        for ctx, val in hits:
            if ctx == want:
                return _num(val)
    for pre in startswith:
        for ctx, val in hits:
            if ctx.startswith(pre):
                return _num(val)
    return _num(hits[0][1])

def safety_current(text, local, agg="sum"):
    """Current-year safety fact across employee + worker cohorts (exclude *_PY)."""
    vals = []
    for ctx, val in _facts(text, local):
        if ctx.endswith("_PY"):
            continue
        if ctx in ("D_Employees", "D_Workers"):
            n = _num(val)
            if n is not None:
                vals.append(n)
    if not vals:
        return None
    return sum(vals) if agg == "sum" else max(vals)

def texts(text, local):
    """All string values for a repeating text tag, in document order."""
    out = []
    for _ctx, val in _facts(text, local):
        v = re.sub(r'\s+', ' ', val).strip()
        v = (v.replace('&amp;', '&').replace('&lt;', '<')
               .replace('&gt;', '>').replace('&#160;', ' '))
        if v:
            out.append(v)
    return out

def get_cin(text):
    m = re.search(r'<xbrli:identifier[^>]*>([^<]+)</xbrli:identifier>', text)
    return m.group(1).strip() if m else None

# ── material-issue block (the "bottlenecks") ────────────────────────────────
RO_MAP = {"r": "Risk", "o": "Opportunity", "r&o": "Risk & Opportunity",
          "r and o": "Risk & Opportunity", "risk": "Risk", "opportunity": "Opportunity"}

def material_issues(text):
    issues  = texts(text, "MaterialIssueIdentified")
    ro      = texts(text, "IndicateWhetherRiskOrOpportunity")
    rat     = texts(text, "RationaleForIdentifyingTheRiskOpportunity")
    mit     = texts(text, "InCaseOfRiskApproachToAdaptOrMitigate")
    fin     = texts(text, "FinancialImplicationsOfTheRiskOrOpportunity")
    n = len(issues)
    if not n:
        return []
    def at(arr, i):
        return arr[i] if i < len(arr) else ""
    rows = []
    for i in range(n):
        r = at(ro, i).strip().lower().replace('.', '')
        mit_txt = at(mit, i)
        if mit_txt.lower().strip() in ("not applicable", "not aplplicable", "na", "n/a", "-", ""):
            mit_txt = ""
        rows.append({
            "issue": issues[i],
            "type": RO_MAP.get(r, "Risk" if r.startswith("r") else "Opportunity" if r.startswith("o") else ""),
            "rationale": at(rat, i)[:600],
            "company_mitigation": mit_txt[:600],
            "financial_implication": at(fin, i),
        })
    return rows

# ── main loop ───────────────────────────────────────────────────────────────
results = {}
files = sorted(XBRL_DIR.glob("*.xml"))
for fp in files:
    company = re.sub(r'_FY\d{2}-\d{2}$', '', fp.stem)
    text = fp.read_text(encoding="utf-8", errors="ignore")
    cin = get_cin(text)
    if not cin:
        continue

    energy = {
        "elec_renewable":      scalar(text, "TotalElectricityConsumptionFromRenewableSources"),
        "elec_nonrenewable":   scalar(text, "TotalElectricityConsumptionFromNonRenewableSources"),
        "fuel_renewable":      scalar(text, "TotalFuelConsumptionFromRenewableSources"),
        "fuel_nonrenewable":   scalar(text, "TotalFuelConsumptionFromNonRenewableSources"),
        "total_energy":        scalar(text, "TotalEnergyConsumedFromRenewableAndNonRenewableSources"),
    }
    ren = sum(v for k, v in energy.items() if k.endswith("renewable") and not k.endswith("nonrenewable") and v)
    tot = energy["total_energy"] or (sum(v for v in energy.values() if v) - (energy["total_energy"] or 0))
    energy["renewable_share_pct"] = round(100 * ren / tot, 1) if tot else None

    waste = {
        "plastic":        scalar(text, "PlasticWaste"),
        "e_waste":        scalar(text, "EWaste"),
        "battery":        scalar(text, "BatteryWaste"),
        "bio_medical":    scalar(text, "BioMedicalWaste"),
        "total":          scalar(text, "TotalWasteGenerated"),
        "recovered_recycled": scalar(text, "WasteRecoveredThroughRecycled"),
    }

    safety = {
        "fatalities":         safety_current(text, "NumberOfFatalities", "sum"),
        "recordable_injuries": safety_current(text, "TotalRecordableWorkRelatedInjuries", "sum"),
        "ltifr_worst":        safety_current(text, "LostTimeInjuryFrequencyRatePerOneMillionPersonHoursWorked", "max"),
    }

    # Emissions intensity — a normalised benchmark (per rupee of turnover) that is
    # comparable across companies, unlike absolute tonnes. 87% disclose S1+S2.
    intensity = {
        "s12_per_turnover": scalar(text, "TotalScope1AndScope2EmissionsIntensityPerRupeeOfTurnover"),
        "scope3":           scalar(text, "TotalScope3Emissions"),
    }

    # Governance integrity — disciplinary actions on bribery/corruption + conflict
    # -of-interest complaints. 0 is a meaningful (clean) value; None = not disclosed.
    def _sum(*tags):
        vals = [scalar(text, t) for t in tags]
        vals = [v for v in vals if v is not None]
        return sum(vals) if vals else None
    governance = {
        "disciplinary_actions": _sum(
            "NumberOfEmployeesAgainstWhomDisciplinaryActionWasTaken",
            "NumberOfWorkersAgainstWhomDisciplinaryActionWasTaken",
            "NumberOfKMPsAgainstWhomDisciplinaryActionWasTaken",
            "NumberOfDirectorsAgainstWhomDisciplinaryActionWasTaken"),
        "coi_complaints": _sum(
            "NumberOfComplaintsReceivedInRelationToIssuesOfConflictOfInterestOfTheKMPs",
            "NumberOfComplaintsReceivedInRelationToIssuesOfConflictOfInterestOfTheDirectors"),
    }

    results[cin] = {
        "company_name": company,
        "bottlenecks": material_issues(text),
        "energy_mix": energy,
        "waste_profile": waste,
        "safety_metrics": safety,
        "emissions_intensity": intensity,
        "governance_signals": governance,
    }

OUT.write_text(json.dumps(results, indent=0, ensure_ascii=False), encoding="utf-8")

# ── coverage report ─────────────────────────────────────────────────────────
N = len(results)
def pct(cond):
    return f"{100*sum(1 for v in results.values() if cond(v))//N:3}%"
print(f"parsed {len(files)} filings -> {N} keyed by CIN\n")
print("coverage (of CIN-keyed filings):")
print(f"  bottlenecks (>=1 material issue)  {pct(lambda v: len(v['bottlenecks'])>0)}")
print(f"  with mitigation text              {pct(lambda v: any(b['company_mitigation'] for b in v['bottlenecks']))}")
print(f"  energy renewable share            {pct(lambda v: v['energy_mix']['renewable_share_pct'] is not None)}")
print(f"  safety (any of fatalities/inj/ltifr){pct(lambda v: any(x is not None for x in v['safety_metrics'].values()))}")
print(f"  waste breakdown (>=1 stream)      {pct(lambda v: any(x is not None for x in v['waste_profile'].values()))}")
print(f"  S1+S2 emissions intensity         {pct(lambda v: v['emissions_intensity']['s12_per_turnover'] is not None)}")
print(f"  governance integrity signals      {pct(lambda v: any(x is not None for x in v['governance_signals'].values()))}")
counts = Counter(len(v["bottlenecks"]) for v in results.values())
print("\nmaterial-issues per company (count -> #companies):",
      dict(sorted(counts.items())))
avg = st.mean(len(v["bottlenecks"]) for v in results.values())
print(f"avg material issues per company: {avg:.1f}")
