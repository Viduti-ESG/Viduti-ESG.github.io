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
    "You are an ESG financial-risk analyst at Green Curve (India). Write ONE risk summary "
    "from ONLY the given data. Rules:\n"
    "- 120-150 words, one paragraph; open with bold header **<Company> - Financial Risk Summary**.\n"
    "- Quote the revenue, EPR exposure, remediation-cost band and top risks exactly as given.\n"
    "- SCORE DIRECTION (critical): all *_out_of_10 scores are RISK scores where HIGHER = WORSE. "
    "A compliance-risk score near 0 means STRONG regulatory compliance / LOW risk; near 10 means "
    "WEAK compliance / HIGH risk. Never invert this.\n"
    "- EMISSIONS: each scope value is either a number (already DISCLOSED — state it as reported) "
    "or the words 'Not disclosed'. Only describe a BRSR disclosure gap for a scope literally marked "
    "'Not disclosed'. If a tCO2e number is given, report it as disclosed and do NOT call it a gap "
    "or imply zero.\n"
    "- Ground in SEBI BRSR / EPR / CCTS context; factual, no invented facts, no investment advice.\n"
    "- End with an 'Immediate priority:' sentence. Write figures as plain text WITHOUT "
    "surrounding quotation marks. Output only the summary."
)

def money(v):
    if v is None: return "Not disclosed"
    return f"₹{v:,.1f} crore"   # ₹ — match the house style used elsewhere

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
        "top_risk_factors": c.get("top_risk_factors"),
        "estimated_compliance_cost_band": fe.get("estimated_compliance_cost_band"),
        "epr_applicable": fe.get("epr_applicable"),
        "scope1_emissions": emis(fe.get("scope1_emissions_tco2e")),
        "scope2_emissions": emis(fe.get("scope2_emissions_tco2e")),
    }
    return "Company data (JSON):\n" + json.dumps(d, ensure_ascii=False)

def groq(system, user, key, max_tokens=300, retries=3):
    """POST to Groq with retry/backoff on 429 (free-tier rate limit) and 5xx."""
    import httpx
    for attempt in range(retries):
        r = httpx.post(GROQ_URL, timeout=90,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": GROQ_MODEL, "max_tokens": max_tokens, "temperature": 0.3,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}]})
        if r.status_code == 429 or r.status_code >= 500:
            # honour Retry-After if given (e.g. "7.5s" / "7.5"), else exponential backoff
            ra = r.headers.get("retry-after", "")
            try:
                wait = float(re.sub(r"[^\d.]", "", ra)) if ra else 0
            except ValueError:
                wait = 0
            wait = min(max(wait, 2 ** attempt * 2), 15)
            print(f"    …rate-limited, waiting {wait:.0f}s (attempt {attempt+1}/{retries})")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    raise RuntimeError("rate-limited after retries")


_REV_RE = re.compile(r"(?:revenue|turnover)\D{0,25}?(?:₹|Rs\.?\s*)([\d,]+\.?\d*)\s*crore", re.I)

def is_stale(c):
    """True if the current ai_summary is missing or cites a revenue figure that
    contradicts the corrected revenue (so re-runs only retry what still needs it)."""
    if c.get("_summary_regen"):          # reliably-tracked: already regenerated
        return False
    s = c.get("ai_summary") or ""
    if not s:
        return True
    if "0–0 crore" in s or "0-0 crore" in s:
        return True
    rev = c.get("revenue_crore")
    for m in _REV_RE.findall(s):
        v = float(m.replace(",", ""))
        if v > 50 and rev and (v > 3 * rev or v < rev / 3):
            return True
        if v > 50 and rev is None:          # summary asserts a revenue we've since nulled
            return True
    return False

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

def has_glitch(c):
    """Detect the two 8b failure modes: inverted score direction, and calling a
    DISCLOSED Scope 1/2 a 'disclosure gap'."""
    s = c.get("ai_summary") or ""
    if re.search(r"0(\.0)? out of 10[^.]{0,45}high risk of non-compl", s, re.I):
        return True
    fe = c.get("financial_exposure", {}) or {}
    if fe.get("scope1_emissions_tco2e") or fe.get("scope2_emissions_tco2e"):
        sl = s.lower()
        if (re.search(r"scope 1 and (scope )?2[^.]{0,30}(not disclosed|disclosure gap)", sl)
                or re.search(r"(not disclosed|disclosure gap)[^.]{0,30}scope 1", sl)):
            return True
    return False

def main():
    dry   = "--dry-run" in sys.argv
    doall = "--all" in sys.argv
    limit = None
    for a in sys.argv:
        if a.startswith("--limit"):
            limit = int(a.split("=")[-1]) if "=" in a else int(sys.argv[sys.argv.index(a)+1])

    doc = json.load(io.open(DATA, encoding="utf-8"))
    comps = doc["companies"]
    if "--fix-glitches" in sys.argv:
        todo = [c for c in comps if has_glitch(c)]      # redo only the glitchy ones
        print(f"glitch-fix mode: {len(todo)} companies with detectable summary glitches")
    else:
        target = None if doall else changed_cins()
        todo = [c for c in comps if doall or c.get("cin") in target]
        # resume by the completion flag: skip only companies already regenerated in a
        # prior run. Reliable (unlike text-matching) and cheap after an interruption.
        if "--force" not in sys.argv:
            before = len(todo)
            todo = [c for c in todo if not c.get("_summary_regen")]
            print(f"{before - len(todo)} already regenerated, skipping them")
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
                c["_summary_regen"] = GROQ_MODEL   # mark done so re-runs skip it reliably
                done += 1
                if len(todo) <= 5 or "--show" in sys.argv:   # test mode: show the text
                    print(f"\n----- {c['company_name']} -----\n{txt}\n")
            else:
                fail += 1; print(f"  [skip weak output] {c['company_name']}")
        except Exception as e:
            fail += 1; print(f"  [error] {c['company_name']}: {e}")
        if i % 5 == 0:
            print(f"  {i}/{len(todo)} (ok={done} fail={fail})")
            json.dump(doc, io.open(DATA, "w", encoding="utf-8"), ensure_ascii=False)  # checkpoint
        time.sleep(6)   # ~10 req/min — respects 8b-instant's ~6k tokens/min free limit
    doc["data_cleaned_at"] = datetime.now().date().isoformat()
    json.dump(doc, io.open(DATA, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\nDONE: regenerated {done}, failed/skipped {fail}.")
    print("NEXT: python generate_company_pages.py")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
