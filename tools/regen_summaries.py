#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regenerate AI risk summaries for companies whose revenue was corrected from the
BRSR XBRL (see project_xbrl_revenue_fix). The old ai_summary text was written from
the pre-fix data and now quotes stale revenue (e.g. Axis "Rs 14,461 cr" vs the
corrected Rs 1,47,934 cr). This rebuilds those summaries from the CURRENT data.

PUBLIC BRSR data -> routed to Groq (free, no-train, commercial-OK) per the project's
AI-vendor rules. Uses the same httpx call as ai_api.py; no new dependency.

Usage:
    GROQ_API_KEY=gsk_... python tools/regen_summaries.py            # regen changed cos
    GROQ_API_KEY=gsk_... python tools/regen_summaries.py --all      # regen every company
    python tools/regen_summaries.py --dry-run                       # build prompts, no API
    ...--limit N   cap number processed (testing)

After it finishes:  python generate_company_pages.py
"""
import os, io, re, sys, json, glob, time, shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "assets" / "data" / "esg_quotient.json"
BACKUP_DIR = ROOT / "_dq_backups"
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

SYSTEM = (
    "You are an ESG financial-risk analyst writing for Green Curve, an Indian ESG "
    "intelligence platform. You write one concise risk summary per company using ONLY "
    "the structured data provided. Rules:\n"
    "- 120-160 words, single flowing analytical paragraph.\n"
    "- Start with a bold markdown header: **<COMPANY NAME> - Financial Risk Summary**.\n"
    "- Reference the figures given: revenue, compliance-risk score, EPR exposure, the "
    "estimated remediation-cost band, and top risk factors. Quote numbers exactly as given.\n"
    "- If emissions are 'Not disclosed', say the company did not report absolute Scope 1/2 "
    "emissions in its BRSR and treat this as a disclosure gap - NEVER imply zero or "
    "carbon-neutral.\n"
    "- Ground it in SEBI BRSR / EPR / CCTS context. Factual and measured; no investment "
    "advice, no invented facts, no data not provided.\n"
    "- End with an 'Immediate priority:' sentence.\n"
    "- Output ONLY the summary text (no preamble, no JSON)."
)

def money(v):
    if v is None: return "Not disclosed"
    return f"Rs {v:,.1f} crore"

def emis(v):
    return "Not disclosed" if not v else f"{v:,.0f} tCO2e"

def build_user(c):
    rb = c.get("risk_breakdown", {}) or {}
    fe = c.get("financial_exposure", {}) or {}
    d = {
        "company": c.get("company_name"),
        "sector": c.get("sector"),
        "financial_year": c.get("financial_year"),
        "revenue": money(c.get("revenue_crore")),
        "esg_risk_score_out_of_10": c.get("esg_risk_score"),
        "risk_tier": c.get("risk_tier"),
        "compliance_risk_out_of_10": rb.get("compliance_risk"),
        "epr_exposure_out_of_10": rb.get("epr_exposure"),
        "ghg_intensity_out_of_10": rb.get("ghg_intensity"),
        "water_intensity_out_of_10": rb.get("water_intensity"),
        "waste_intensity_out_of_10": rb.get("waste_intensity"),
        "top_risk_factors": c.get("top_risk_factors"),
        "estimated_compliance_cost_band": fe.get("estimated_compliance_cost_band"),
        "epr_applicable": fe.get("epr_applicable"),
        "scope1_emissions": emis(fe.get("scope1_emissions_tco2e")),
        "scope2_emissions": emis(fe.get("scope2_emissions_tco2e")),
        "disclosure_confidence_pct": rb.get("disclosure_confidence"),
    }
    return "Company data (JSON):\n" + json.dumps(d, ensure_ascii=False, indent=1)

def groq(system, user, key, max_tokens=420):
    import httpx
    r = httpx.post(GROQ_URL, timeout=90,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": GROQ_MODEL, "max_tokens": max_tokens, "temperature": 0.3,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

def changed_cins():
    """CINs whose revenue differs from the most recent pre-fix backup."""
    baks = sorted(glob.glob(str(DATA).replace(".json", ".bak_*.json")))
    if not baks:
        print("!! no esg_quotient.bak_*.json found; use --all to regen everything.")
        return set()
    old = json.load(io.open(baks[0], encoding="utf-8"))     # earliest bak = true original
    om = {c.get("cin"): c.get("revenue_crore") for c in old["companies"] if c.get("cin")}
    cur = json.load(io.open(DATA, encoding="utf-8"))
    out = set()
    for c in cur["companies"]:
        o, n = om.get(c.get("cin")), c.get("revenue_crore")
        if o == n: continue
        if (isinstance(n,(int,float)) and isinstance(o,(int,float)) and o
                and abs(n-o) <= max(1.0, 0.05*n)): continue
        out.add(c.get("cin"))
    print(f"using backup {Path(baks[0]).name}; {len(out)} revenue-changed companies")
    return out

def main():
    dry   = "--dry-run" in sys.argv
    doall = "--all" in sys.argv
    limit = None
    for a in sys.argv:
        if a.startswith("--limit"):
            limit = int(a.split("=")[-1]) if "=" in a else int(sys.argv[sys.argv.index(a)+1])

    doc = json.load(io.open(DATA, encoding="utf-8"))
    comps = doc["companies"]
    target = None if doall else changed_cins()
    todo = [c for c in comps if doall or c.get("cin") in target]
    if limit: todo = todo[:limit]
    print(f"companies to regenerate: {len(todo)}  (model={GROQ_MODEL}, dry={dry})")

    key = os.environ.get("GROQ_API_KEY")
    if dry or not key:
        if not key and not dry:
            print("\n!! GROQ_API_KEY not set. Showing a sample prompt; no API calls made.")
        print("\n===== SAMPLE PROMPT (first company) =====")
        if todo:
            print(build_user(todo[0])[:1400])
        print("\n[no changes written]")
        return 0

    shutil.copy2(DATA, BACKUP_DIR / f"esg_quotient.presummary_{datetime.now():%Y%m%dT%H%M%S}.json.bak")
    done = fail = 0
    for i, c in enumerate(todo, 1):
        try:
            txt = groq(SYSTEM, build_user(c), key)
            # guard: keep only if it looks like a real summary and doesn't reintroduce Rs0-0
            if len(txt.split()) >= 60 and "0-0 crore" not in txt and "0–0 crore" not in txt:
                c["ai_summary"] = txt
                done += 1
            else:
                fail += 1; print(f"  [skip weak output] {c['company_name']}")
        except Exception as e:
            fail += 1; print(f"  [error] {c['company_name']}: {e}")
        if i % 10 == 0:
            print(f"  {i}/{len(todo)} (ok={done} fail={fail})")
            json.dump(doc, io.open(DATA, "w", encoding="utf-8"), ensure_ascii=False)  # checkpoint
        time.sleep(0.5)   # gentle on the free tier
    doc["data_cleaned_at"] = datetime.now().date().isoformat()
    json.dump(doc, io.open(DATA, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\nDONE: regenerated {done}, failed/skipped {fail}.")
    print("NEXT: python generate_company_pages.py")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
