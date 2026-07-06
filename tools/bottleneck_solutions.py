"""
Curated bottleneck -> best-fit global solution taxonomy.

Deterministic, zero-runtime-cost, zero-hallucination. Each canonical bottleneck a
company self-discloses (BRSR "MaterialIssueIdentified") is mapped to the globally
recognised, authoritative solution/standard/playbook that best addresses it, with
source links. This is the advisory layer that turns a scorecard into guidance.

Every "standard" cited is a real, named, published framework; every source URL is
the issuing body's canonical page. Nothing here is model-generated.

Public API:
    classify(issue_text) -> category_key | None
    SOLUTIONS[category_key] -> dict
"""
import re

# ── canonical bottleneck -> solution ────────────────────────────────────────
# order matters: classify() takes the first category whose keywords match, so
# specific themes are listed before generic ones.
SOLUTIONS = {
    "climate_ghg": {
        "label": "Climate change & GHG emissions",
        "solution": "Set a Science Based Target (SBTi), measure with the GHG Protocol, and decarbonise via RE100-style renewable sourcing and TCFD/IFRS-S2 climate-risk scenario analysis.",
        "standards": ["SBTi", "GHG Protocol", "RE100", "TCFD / IFRS S2"],
        "sources": [
            {"name": "Science Based Targets initiative", "url": "https://sciencebasedtargets.org/"},
            {"name": "GHG Protocol", "url": "https://ghgprotocol.org/"},
            {"name": "RE100", "url": "https://www.there100.org/"},
        ],
    },
    "energy_efficiency": {
        "label": "Energy management & efficiency",
        "solution": "Adopt an ISO 50001 energy-management system and pursue certified efficiency gains; in India, align to BEE's PAT (Perform-Achieve-Trade) scheme for ESCert value.",
        "standards": ["ISO 50001", "BEE PAT scheme"],
        "sources": [
            {"name": "ISO 50001 Energy management", "url": "https://www.iso.org/iso-50001-energy-management.html"},
            {"name": "BEE PAT Scheme", "url": "https://beeindia.gov.in/en/programmes/perform-achieve-and-trade-pat"},
        ],
    },
    "water": {
        "label": "Water security & effluents",
        "solution": "Commit to the UN CEO Water Mandate and certify sites to the Alliance for Water Stewardship (AWS) Standard; deploy Zero Liquid Discharge (ZLD) and closed-loop recycling in water-stressed basins.",
        "standards": ["CEO Water Mandate", "AWS Standard", "Zero Liquid Discharge"],
        "sources": [
            {"name": "UN CEO Water Mandate", "url": "https://ceowatermandate.org/"},
            {"name": "Alliance for Water Stewardship", "url": "https://a4ws.org/the-aws-standard-2-0/"},
        ],
    },
    "waste_circularity": {
        "label": "Waste & circular economy",
        "solution": "Apply Ellen MacArthur Foundation circular-economy design, target Zero Waste to Landfill (UL 2799 validation), and meet India's Extended Producer Responsibility (EPR) obligations for plastic/e-waste/battery.",
        "standards": ["Ellen MacArthur CE", "UL 2799 Zero Waste to Landfill", "India EPR"],
        "sources": [
            {"name": "Ellen MacArthur Foundation", "url": "https://www.ellenmacarthurfoundation.org/"},
            {"name": "CPCB EPR (India)", "url": "https://cpcb.nic.in/plastic-waste/"},
        ],
    },
    "air_emissions": {
        "label": "Air emissions (non-GHG)",
        "solution": "Install Continuous Emission Monitoring Systems (CEMS) and abatement to CPCB norms; manage under an ISO 14001 environmental-management system.",
        "standards": ["CPCB CEMS norms", "ISO 14001"],
        "sources": [
            {"name": "CPCB Emission Standards", "url": "https://cpcb.nic.in/emission-standards/"},
            {"name": "ISO 14001", "url": "https://www.iso.org/iso-14001-environmental-management.html"},
        ],
    },
    "biodiversity": {
        "label": "Biodiversity & land use",
        "solution": "Assess and disclose nature-related risk with the TNFD framework, set Science Based Targets for Nature (SBTN), and apply a No Net Loss / mitigation-hierarchy approach.",
        "standards": ["TNFD", "SBTN", "No Net Loss"],
        "sources": [
            {"name": "TNFD", "url": "https://tnfd.global/"},
            {"name": "Science Based Targets Network", "url": "https://sciencebasedtargetsnetwork.org/"},
        ],
    },
    "occupational_safety": {
        "label": "Occupational health & safety",
        "solution": "Certify to ISO 45001 and drive an interdependent safety culture using the DuPont Bradley Curve and behaviour-based safety; track leading indicators, not just LTIFR.",
        "standards": ["ISO 45001", "DuPont Bradley Curve", "Behaviour-Based Safety"],
        "sources": [
            {"name": "ISO 45001 OH&S", "url": "https://www.iso.org/iso-45001-occupational-health-and-safety.html"},
        ],
    },
    "human_rights": {
        "label": "Human rights",
        "solution": "Operationalise the UN Guiding Principles on Business & Human Rights (UNGPs) via human-rights due diligence and grievance mechanisms; certify labour sites to SA8000.",
        "standards": ["UN Guiding Principles (UNGPs)", "SA8000", "HR Due Diligence"],
        "sources": [
            {"name": "UN Guiding Principles", "url": "https://www.ohchr.org/en/publications/reference-publications/guiding-principles-business-and-human-rights"},
            {"name": "SA8000 Standard", "url": "https://sa-intl.org/programs/sa8000/"},
        ],
    },
    "diversity_inclusion": {
        "label": "Diversity, equity & inclusion",
        "solution": "Adopt the UN Women's Empowerment Principles (WEPs), report against GRI 405, and set board/leadership representation targets with pay-equity audits.",
        "standards": ["UN WEPs", "GRI 405", "Pay-equity audit"],
        "sources": [
            {"name": "Women's Empowerment Principles", "url": "https://www.weps.org/"},
            {"name": "GRI 405 Diversity", "url": "https://www.globalreporting.org/standards/"},
        ],
    },
    "labour_practices": {
        "label": "Labour practices & fair wage",
        "solution": "Align to the ILO core conventions and pay a benchmarked living wage (Anker methodology / Fair Wage Network); formalise collective-bargaining and freedom-of-association.",
        "standards": ["ILO Core Conventions", "Living Wage (Anker)", "Fair Wage Network"],
        "sources": [
            {"name": "ILO Core Conventions", "url": "https://www.ilo.org/international-labour-standards"},
            {"name": "Global Living Wage Coalition", "url": "https://www.globallivingwage.org/"},
        ],
    },
    "talent_development": {
        "label": "Talent development & engagement",
        "solution": "Report human-capital metrics under ISO 30414, tie L&D to competency frameworks, and track engagement/retention as a board-level KPI.",
        "standards": ["ISO 30414 Human Capital", "Competency frameworks"],
        "sources": [
            {"name": "ISO 30414 Human Capital Reporting", "url": "https://www.iso.org/standard/69338.html"},
        ],
    },
    "business_ethics": {
        "label": "Business ethics & anti-corruption",
        "solution": "Certify an anti-bribery management system to ISO 37001, commit to the UN Global Compact's 10th principle, and run a protected whistleblower channel with independent oversight.",
        "standards": ["ISO 37001", "UN Global Compact", "Whistleblower mechanism"],
        "sources": [
            {"name": "ISO 37001 Anti-bribery", "url": "https://www.iso.org/iso-37001-anti-bribery-management.html"},
            {"name": "UN Global Compact", "url": "https://unglobalcompact.org/what-is-gc/mission/principles/principle-10"},
        ],
    },
    "data_privacy_cyber": {
        "label": "Data privacy & cybersecurity",
        "solution": "Certify information security to ISO/IEC 27001, run a NIST Cybersecurity Framework programme, and build India DPDP Act 2023 compliance into data flows.",
        "standards": ["ISO/IEC 27001", "NIST CSF", "India DPDP Act 2023"],
        "sources": [
            {"name": "ISO/IEC 27001", "url": "https://www.iso.org/standard/27001"},
            {"name": "NIST Cybersecurity Framework", "url": "https://www.nist.gov/cyberframework"},
        ],
    },
    "supply_chain": {
        "label": "Supply chain & responsible sourcing",
        "solution": "Rate suppliers with EcoVadis, enforce a Supplier Code of Conduct with SA8000-style social audits, and build traceability for responsible sourcing.",
        "standards": ["EcoVadis", "Supplier Code of Conduct", "SA8000 audits"],
        "sources": [
            {"name": "EcoVadis", "url": "https://ecovadis.com/"},
            {"name": "Responsible Business Alliance", "url": "https://www.responsiblebusiness.org/"},
        ],
    },
    "product_stewardship": {
        "label": "Product stewardship & innovation",
        "solution": "Quantify product footprint with ISO 14040/14044 Life Cycle Assessment, pursue credible eco-labels (Type I / EPD), and design for durability and recyclability.",
        "standards": ["ISO 14040/44 LCA", "Environmental Product Declaration", "Eco-design"],
        "sources": [
            {"name": "ISO 14040 LCA", "url": "https://www.iso.org/standard/37456.html"},
            {"name": "EPD International", "url": "https://www.environdec.com/"},
        ],
    },
    "customer_wellbeing": {
        "label": "Customer wellbeing & product quality",
        "solution": "Run an ISO 9001 quality-management system with transparent product labelling and a closed-loop complaint-resolution process feeding design.",
        "standards": ["ISO 9001", "Transparent labelling"],
        "sources": [
            {"name": "ISO 9001 Quality management", "url": "https://www.iso.org/iso-9001-quality-management.html"},
        ],
    },
    "community_csr": {
        "label": "Community & social impact",
        "solution": "Measure programme impact with Social Return on Investment (SROI), align spend to Companies Act Sec. 135 CSR rules, and target SDG-linked outcomes.",
        "standards": ["SROI", "Companies Act Sec. 135 CSR", "SDG alignment"],
        "sources": [
            {"name": "Social Value International (SROI)", "url": "https://www.socialvalueint.org/"},
        ],
    },
    "governance_general": {
        "label": "Corporate governance",
        "solution": "Strengthen board independence and oversight to ISO 37000 governance principles and SEBI LODR requirements; separate chair/CEO and disclose against a recognised code.",
        "standards": ["ISO 37000", "SEBI LODR"],
        "sources": [
            {"name": "ISO 37000 Governance", "url": "https://www.iso.org/standard/65036.html"},
            {"name": "SEBI LODR", "url": "https://www.sebi.gov.in/"},
        ],
    },
    "regulatory_compliance": {
        "label": "Regulatory compliance",
        "solution": "Deploy a compliance-management system (ISO 37301) with a live regulatory register, automated obligation tracking, and periodic assurance.",
        "standards": ["ISO 37301 Compliance management"],
        "sources": [
            {"name": "ISO 37301", "url": "https://www.iso.org/standard/75080.html"},
        ],
    },
}

# ── classifier ──────────────────────────────────────────────────────────────
# first matching rule wins; specific before generic.
_RULES = [
    ("data_privacy_cyber", ["data privacy", "data protection", "cyber", "information security", "data security", "privacy"]),
    ("occupational_safety", ["occupational", "health and safety", "health & safety", "workplace safety", "safety", "ohs"]),
    ("human_rights",        ["human right", "child labour", "child labor", "forced labour", "forced labor", "modern slavery"]),
    ("water",               ["water", "effluent", "wastewater"]),
    ("waste_circularity",   ["waste", "circular", "recycl", "plastic", "hazardous material", "resource efficiency", "resource use", "resource management", "materials", "chemical management", "chemical safety"]),
    ("air_emissions",       ["air emission", "air quality", "air pollut", "nox", "sox", "particulate"]),
    ("biodiversity",        ["biodiversit", "ecolog", "land use", "deforest", "nature", "natural capital"]),
    ("energy_efficiency",   ["energy efficiency", "energy management", "energy conservation", "energy consumption"]),
    ("climate_ghg",         ["climate", "carbon", "ghg", "greenhouse", "emission", "net zero", "decarbon", "global warming", "renewable energy", "energy transition", "energy"]),
    ("diversity_inclusion", ["diversity", "inclusion", "gender", "equity", "equal opportunit", "women"]),
    ("labour_practices",    ["labour", "labor", "wage", "collective bargain", "freedom of association", "working condition", "fair pay"]),
    ("talent_development",  ["talent", "employee development", "employee engagement", "training", "learning", "retention", "skill", "capacity building", "human capital", "employee well", "employee welfare", "employment", "human resource", "workforce", "people", "attract"]),
    ("supply_chain",        ["supply chain", "supplier", "sourcing", "procurement", "value chain", "raw material", "vendor"]),
    ("business_ethics",     ["ethic", "anti-corruption", "anti corruption", "bribery", "corrupt", "integrity", "transparen", "conflict of interest", "whistleblow", "fair market", "responsible business", "code of conduct", "fair business", "anti-competitive"]),
    ("product_stewardship", ["product responsibilit", "product stewardship", "life cycle", "lifecycle", "product innovation", "innovation", "eco-design", "sustainable product", "r&d", "r & d", "research and development", "product design"]),
    ("customer_wellbeing",  ["customer", "consumer", "product quality", "product safety", "client satisf", "service quality"]),
    ("community_csr",       ["community", "communit", "csr", "social impact", "social responsibilit", "philanthrop", "livelihood", "local development", "financial literacy", "financial inclusion", "social develop"]),
    ("regulatory_compliance", ["compliance", "regulatory", "statutory"]),
    ("governance_general",  ["governance", "board", "risk management", "risk and crisis", "crisis management", "business continuit", "resilience", "stakeholder", "shareholder", "esg", "sustainab", "reputation", "disclosure", "economic performance", "financial performance", "economic value", "responsible invest", "materiality", "digital", "technolog", "innovation and technolog", "business continuity"]),
]

def classify(issue_text):
    if not issue_text:
        return None
    t = issue_text.lower()
    for key, kws in _RULES:
        if any(k in t for k in kws):
            return key
    return None


if __name__ == "__main__":
    # quick self-test against the real corpus
    import json
    from pathlib import Path
    from collections import Counter
    data = json.loads(Path(r"c:/Viduti/esg-site/tools/bottlenecks_extracted.json").read_text(encoding="utf-8"))
    hit = miss = 0
    cats = Counter()
    misses = Counter()
    for v in data.values():
        for b in v["bottlenecks"]:
            k = classify(b["issue"])
            if k:
                hit += 1; cats[k] += 1
            else:
                miss += 1; misses[b["issue"][:40]] += 1
    tot = hit + miss
    print(f"classified {hit}/{tot} disclosed issues = {100*hit/tot:.1f}% matched to a solution")
    print("\ntop categories:")
    for k, c in cats.most_common(12):
        print(f"  {c:5}  {k:22} -> {SOLUTIONS[k]['standards'][0]}")
    print("\ntop unmatched issue strings:")
    for s, c in misses.most_common(15):
        print(f"  {c:4}  {s}")
