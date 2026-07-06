"""
Shared canonical-sector map. Single source of truth for bucketing the free-text
BRSR "sector" string into ~21 canonical sectors, used by both the sector roll-up
pages (generate_company_pages.py) and the peer-benchmark engine
(build_sector_benchmarks.py). Keep this list in sync — do not fork it.
"""
import re

SECTOR_RULES = [
    ("Banking & Financial Services", ["bank","nbfc","financial","finance","credit","leasing","brokerage","capital market","lending","loans","housing finance","microfinance","asset reconstruction","payment","fintech"]),
    ("Insurance",                     ["insurance"]),
    ("Asset & Fund Management",       ["fund management","asset management","mutual fund","wealth","investment manage"]),
    ("IT, Software & Services",       ["computer programming","software","information technology","it services","consultancy and related","data processing","internet"]),
    ("Pharmaceuticals & Healthcare",  ["pharma","medicinal","drug","healthcare","hospital","medical","biotech","diagnostic","life science"]),
    ("Chemicals",                     ["chemical","fertilis","fertiliz","agrochem","petrochem","dyes","paint"]),
    ("Metals & Mining",               ["metal","steel","iron","mining","aluminium","aluminum","zinc","copper","ore","ferro"]),
    ("Cement & Construction Materials",["cement","clinker","concrete","construction material","ceramic","tiles"]),
    ("Automobiles & Components",      ["auto","vehicle","motor","tyre","tire","automobile","two wheeler","bearings"]),
    ("Power & Utilities",             ["power generation","electric power","electricity","utilit","renewable","solar","wind power","transmission and distribution"]),
    ("Oil, Gas & Fuels",             ["oil","gas","petroleum","refiner","lng","city gas","fuel","coal"]),
    ("FMCG, Food & Beverages",        ["fmcg","fast moving","food","beverage","tobacco","dairy","agro product","consumer goods","sugar","tea","coffee"]),
    ("Textiles & Apparel",            ["textile","apparel","garment","yarn","fabric","cotton","leather","footwear"]),
    ("Real Estate & Infrastructure",  ["real estate","realty","property","infrastructure","construction","roads","highway"]),
    ("Telecom & Media",               ["telecom","communication","media","broadcasting","entertainment","publishing"]),
    ("Retail & Trading",              ["retail","wholesale","trading","e-commerce","distribution"]),
    ("Capital Goods & Machinery",     ["machinery","electrical equipment","engineering","capital goods","industrial equipment","general purpose","special purpose","electronic"]),
    ("Logistics & Transport",         ["transport","logistics","shipping","port","airline","aviation","courier","tour operator","travel agency","parcel","freight","warehous"]),
    ("Hospitality & Tourism",         ["hotel","hospitality","resort","tourism","restaurant"]),
    ("Plastics, Rubber & Packaging",  ["plastic","rubber","packaging","polymer"]),
    ("Paper & Forest Products",       ["paper","pulp","forest","wood"]),
]

_KW_CACHE = {}

def _kw_pattern(kw):
    # Word-boundary *prefix* match: '\biron' matches "iron"/"ironworks" but NOT
    # "environment"; '\bore' matches "ore" but NOT "core"/"store"/"more".
    # Keeps prefix intent ('pharma' -> "pharmaceutical") while killing the
    # substring false-positives that mis-bucketed logistics/fintech into Metals.
    p = _KW_CACHE.get(kw)
    if p is None:
        p = _KW_CACHE[kw] = re.compile(r'\b' + re.escape(kw))
    return p

def classify_sector(sector_text):
    """Map a raw BRSR sector string to a canonical sector, or None if unclassifiable."""
    t = (sector_text or "").lower()
    for name, kws in SECTOR_RULES:
        if any(_kw_pattern(k).search(t) for k in kws):
            return name
    return None
