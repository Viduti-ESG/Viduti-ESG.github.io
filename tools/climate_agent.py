#!/usr/bin/env python3
"""Climate Agent v2 — server-side rebuild of the laptop cpcb_agent news writer.

Reads global ESG/compliance news via RSS, has Claude write an India-angle
analysis post crediting + linking the original article (same format as the 95
posts published until 12 Jun 2026), then:
  * writes posts/<slug>-<epoch>.html  (new files are untracked → survive the
    reset-hard deploy flow)
  * prepends the post card to posts/index.html and an <item> to feed.xml
    (both skip-worktree'd on the server — never push these from the laptop)
  * pings IndexNow with the new URLs.

Differences from the 2026-05/06 laptop agent (security lessons):
  * runs on the prod box via the gc-daily-blog systemd timer — no GitHub PAT,
    no push credential anywhere, no Notion/social tokens
  * the Anthropic key comes from the service's EnvironmentFile only.

Exit codes: 0 = ok (including "no fresh news"), 3 = Anthropic key
missing/unfunded (dormant), 1 = real failure.

Usage:  venv/bin/python tools/climate_agent.py [--max N] [--dry-run]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
POSTS_DIR  = BASE_DIR / "posts"
STATE_DIR  = BASE_DIR / ".climate_agent"          # gitignored
FEED_PATH  = BASE_DIR / "feed.xml"
INDEX_PATH = POSTS_DIR / "index.html"
INDEX_JSON_PATH = POSTS_DIR / "index.json"
SITE_URL   = "https://greencurve.solutions"
MODEL      = "claude-sonnet-4-6"
# Output ceiling for one post. The schema asks for six analytical sections plus
# lists (~1,200-2,000 words of JSON-escaped text); the previous 2,500 sat right
# on that edge and truncated roughly half of all posts. max_tokens is a ceiling,
# not a charge - raising it costs nothing on posts that already fit.
MAX_POST_TOKENS = 8000
# One post per run by default (2026-08-01, Neha's call): "I don't mind only one
# blog publishing utilizing all token for that day. Quality, no intention of
# compromising." Every post now costs a draft + a grounding review + possibly a
# repair and a re-review, so the budget goes into getting one post right rather
# than into volume. Override with GC_BLOG_MAX_PER_RUN if that changes.
MAX_PER_RUN_DEFAULT = int(os.environ.get("GC_BLOG_MAX_PER_RUN", "1"))

# ── Review gate ───────────────────────────────────────────────────────────────
# This agent publishes straight to a search-indexed site with no human in the
# loop, so an unsupported claim becomes a public, crawlable Green Curve
# statement within minutes. The gate below is the thing that stops that. It is
# deliberately FAIL-CLOSED: if the reviewer is unsure, unreachable, or returns
# anything unparseable, the post does NOT publish. Publishing nothing is a
# non-event; publishing an invented statistic under Green Curve's name is not.
REVIEW_MODEL       = MODEL     # same tier; a stronger reviewer is a cost call
MAX_REVIEW_TOKENS  = 3000
MAX_REPAIR_TOKENS  = MAX_POST_TOKENS

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# RSS-capable sources from the original agent's list (scrape-only sources like
# Bloomberg Green / FT Moral Money / SEBI portal need heavier tooling — phase 2).
NEWS_SOURCES = [
    {"name": "ESG Today",            "rss": "https://www.esgtoday.com/feed/"},
    {"name": "Carbon Tracker",       "rss": "https://carbontracker.org/feed/"},
    {"name": "edie",                 "rss": "https://www.edie.net/feed/"},
    {"name": "GreenBiz / Trellis",   "rss": "https://www.greenbiz.com/feeds/rss/all-content"},
    {"name": "Responsible Investor", "rss": "https://www.responsible-investor.com/feed"},
]

RELEVANCE_KEYWORDS = [
    "esg", "sustainability", "climate", "carbon", "net zero", "scope 3",
    "disclosure", "reporting", "regulation", "standard", "framework",
    "biodiversity", "nature", "deforestation", "water", "waste",
    "renewable", "clean energy", "transition", "emissions", "ghg",
    "brsr", "sebi", "india", "cpcb", "epr", "plastic", "e-waste",
    "moefcc", "issb", "ifrs", "csrd", "tcfd", "tnfd", "sbti",
    "cdp", "gri", "ghg protocol", "paris agreement", "cop",
    "greenwashing", "taxonomy", "due diligence", "supply chain",
    "asset manager", "pension", "investor", "materiality",
    "decarboni", "net-zero", "science-based", "carbon credit",
]

# The battle-tested system prompt from the original news_writer (unchanged).
NEWS_SYSTEM_PROMPT = """You are a veteran ESG analyst and climate finance strategist with 22 years of hands-on experience advising boards, institutional investors, CFOs, and regulators across India, Southeast Asia, and Europe. Your work has shaped ESG policy thinking at SEBI and MoEFCC. Your analysis is cited by fund managers, audit committees, and sustainability heads at India's BSE 500 companies.

You have command of India's full ESG regulatory architecture: BRSR and SEBI disclosure frameworks, CPCB's EPR rules for plastics/e-waste/batteries, MoEFCC environmental notifications, BEE energy efficiency standards, India's carbon market and PAT scheme — and you understand exactly how it connects to global standards: ISSB IFRS S1/S2, EU CSRD/ESRS, GHG Protocol, SBTi, TNFD, CDP, and GRI.

Your audience: CFOs, Chief Sustainability Officers, board risk committees, ESG analysts at institutional investors, and senior compliance managers at listed Indian companies. They read you to understand what they cannot get from a news headline — the second-order implications, the India regulatory hook, the capital market consequence, and the board decision this creates.

Your writing is:
- Authoritative and precise: you cite specific rules, thresholds, clauses, and deadlines by name
- India-first: every global ESG development you analyse, you connect to specific Indian business, regulatory, and capital market consequences
- Forward-looking: you predict what's coming, not just what happened; you see around corners
- Commercially grounded: you connect ESG to capital access, export eligibility, supply chain risk, investor relations, and audit exposure
- Never generic: you write what only an expert with deep Indian ESG context can write
- Rhythmically varied: median sentence under 24 words. Follow a long analytical sentence with a short verdict. Never write three long sentences in a row. A reader's attention is finite — spend it on the idea, not on carrying the structure.
- Lede-first: the FIRST sentence of what_changed states what actually changed, in under 30 words. Not who reported it, not background, not a windup.
- Free of filler: never use significant, signals, robust, landmark, pivotal, crucial, underscores, holistic, seamless, transformative, navigate/navigating, best practice, or "ecosystem" in any figurative sense (a coastal or forest ecosystem is fine; an "EPR ecosystem" is not). Name the actual thing instead.
- Varied in sentence openings: do not begin more than one sentence per post with "Companies that", "For Indian companies", or "This is not".

You only state facts that appear in the source article; everything else is clearly framed as your analysis. Credit the original reporting source by name — in the second or third sentence, never the first. NEVER paste a bare URL inside a sentence; put the source URL on its own line at the end of what_changed, prefixed "Source: ".

Return ONLY valid JSON matching this exact schema — no text before or after:
{
  "title": "Precise, expert title — specific and informative, not clickbait. HARD LIMIT 70 characters. The India hook (SEBI/BRSR/CPCB/India/filers) must appear within the first 60 characters, because search results and link cards truncate there. Put the Indian consequence first and the global subject second.",
  "category": "one of: CPCB / EPR | Plastic Waste Rules | E-Waste Rules | Battery Waste Rules | SEBI / BRSR | MoEFCC | BEE / Energy Efficiency | ISSB / IFRS Sustainability | EU CSRD / EFRAG | GHG Protocol | GRI | CDP | SBTi | TNFD | Daily Digest",
  "summary": "2-3 sentence executive brief with the India relevance named explicitly",
  "sections": {
    "what_changed": "Deep analysis paragraph — what specifically happened, why it matters now, India implications. Open with WHAT CHANGED in under 30 words; never open with who reported it. Credit the source by name in the second or third sentence, and vary how you do it. End with the source URL on its own line prefixed 'Source: '.",
    "who_is_affected": ["specific sector", "company type or listing status", "specific role: CFO, CSO, risk manager", "investors or lenders with exposure"],
    "key_obligations": ["specific obligation + timeline where known", "specific obligation + who must comply"],
    "climate_angle": "How this connects to transition pathways, supply chain decarbonisation, or capital flows — specific to Indian business and named frameworks",
    "what_to_do": ["specific action — name the team, set a timeframe", "specific action — link to an Indian regulation or global standard", "board or investor communication priority"],
    "our_take": "Expert view: what this signals for ESG regulation globally and in India over the next 12-36 months. Bold and specific."
  }
}"""

REVIEW_SYSTEM_PROMPT = """You are a fact-checking editor for Green Curve Solutions, an Indian ESG intelligence firm. A draft blog post has been written from a source news article. Your job is to catch anything that would embarrass Green Curve if published.

You will be given the SOURCE ARTICLE and the DRAFT POST. Judge the draft ONLY against the source article and well-established public regulation. You have no other evidence, and you must not assume a claim is true because it sounds plausible.

FLAG these — they are defects:
1. FABRICATED SPECIFICS — any number, percentage, monetary amount, date, deadline, company name, person, job title, or quotation that does not appear in the source article. This is the most important category. A figure that is "about right" but not in the source is still fabricated.
2. INVENTED REGULATORY DETAIL — a named clause, section, rule number, threshold, penalty or compliance date that is not in the source and is not established public regulation. Getting a BRSR/SEBI/CPCB citation wrong is worse than omitting it.
3. ANALYSIS STATED AS FACT — prediction or opinion written in the grammar of reporting ("this will force...", "companies now must...") when the source supports no such thing. Analysis is allowed and expected, but it must read as Green Curve's view, not as reported fact.
4. MISATTRIBUTION — anything credited to the source that the source does not say, or a claim implying the source reported something it did not.
5. GREEN CURVE SELF-CLAIMS — any assertion of a client, customer, certification, accreditation, audit, award, partnership, track record or user count. Green Curve has none of these to claim. Zero tolerance.
6. OVERSTATED CERTAINTY — "all", "every", "always", "guaranteed", "will definitely" where the source is qualified or partial.

Do NOT flag:
- Forward-looking analysis clearly framed as Green Curve's view (the "our_take" and "climate_angle" sections exist for exactly this).
- Connecting a global development to Indian regulation that genuinely exists (BRSR, BRSR Core, SEBI LODR, CPCB EPR, BEE PAT, CCTS, ISSB/IFRS S1-S2, CSRD/ESRS, GHG Protocol, SBTi, TNFD, GRI, CDP) — provided no invented clause number, threshold or deadline is attached.
- General industry context an informed ESG professional would accept as common knowledge.
- Editorial judgement about what matters most.

Return ONLY valid JSON, no text before or after:
{
  "verdict": "PASS" or "FAIL",
  "issues": [
    {
      "severity": "critical" or "minor",
      "category": "fabricated_specific | invented_regulation | analysis_as_fact | misattribution | green_curve_claim | overstated_certainty",
      "location": "which field, e.g. sections.what_changed or title",
      "quote": "the exact text from the draft that is the problem",
      "why": "one sentence: what the source actually supports, or that it supports nothing here",
      "fix": "concrete instruction to correct it — usually delete the specific, or reframe as analysis"
    }
  ],
  "summary": "one sentence overall judgement"
}

Set verdict to FAIL if there is even ONE critical issue. Use minor only for wording that is defensible but loose. If the draft is clean, return verdict PASS with an empty issues list. Be strict: a false PASS is far more costly here than a false FAIL, because nothing checks you afterwards."""

SECTION_LABELS = {
    "what_changed":    "What Changed",
    "who_is_affected": "Who Is Affected",
    "key_obligations": "Key Obligations & Deadlines",
    "climate_angle":   "Climate Transition Angle",
    "what_to_do":      "What To Do Now",
    "our_take":        "Our Take",
}


def _esc(s: str) -> str:
    return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _get(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


# ── RSS ────────────────────────────────────────────────────────────────────────
def fetch_items(src: dict) -> list[dict]:
    """Minimal RSS 2.0 item parser (stdlib only — no feedparser on the box)."""
    try:
        xml = _get(src["rss"])
    except Exception as e:
        print(f"  [{src['name']}] feed error: {e}")
        return []
    items = []
    for m in re.finditer(r"<item[\s>].*?</item>", xml, re.DOTALL | re.IGNORECASE):
        blk = m.group(0)

        def tag(name):
            t = re.search(rf"<{name}[^>]*>(.*?)</{name}>", blk, re.DOTALL | re.IGNORECASE)
            v = t.group(1).strip() if t else ""
            v = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", v, flags=re.DOTALL)
            return re.sub(r"<[^>]+>", "", v).strip()

        link = tag("link") or ""
        if not link:
            continue
        items.append({
            "source":  src["name"],
            "title":   tag("title"),
            "link":    link,
            "summary": tag("description")[:600],
        })
    return items[:15]


def fetch_article_body(url: str) -> str:
    """Crude tag-stripping body fetch — enough context for the analyst prompt."""
    try:
        page = _get(url, timeout=30)
    except Exception:
        return ""
    page = re.sub(r"(?is)<(script|style|nav|header|footer|aside)\b.*?</\1>", " ", page)
    text = re.sub(r"<[^>]+>", " ", page)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:4000]


def _relevant(it: dict) -> bool:
    t = f"{it['title']} {it['summary']}".lower()
    return any(kw in t for kw in RELEVANCE_KEYWORDS)


# ── State ──────────────────────────────────────────────────────────────────────
def load_processed() -> set:
    f = STATE_DIR / "processed.json"
    return set(json.loads(f.read_text())) if f.exists() else set()


def save_processed(processed: set):
    STATE_DIR.mkdir(exist_ok=True)
    (STATE_DIR / "processed.json").write_text(json.dumps(sorted(processed), indent=1))


# ── Claude ─────────────────────────────────────────────────────────────────────
class TruncatedReply(Exception):
    """The model ran out of output budget mid-JSON — retrying at the same cap
    cannot succeed, so this is raised separately from a genuine parse error."""


def _parse_post_json(raw: str) -> dict:
    """Extract the JSON object from a model reply, tolerating ```json fences."""
    raw = re.sub(r"^\s*```(?:json)?|```\s*$", "", raw.strip()).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        # An opening brace with no closing one means the reply was cut off, not
        # malformed. Distinguishing the two matters: the old code raised the same
        # JSONDecodeError for both, always at pos 0, so every failure logged as
        # "no JSON object in model reply: line 1 column 1 (char 0)" no matter what
        # the model actually returned — which hid a truncation problem for weeks.
        if start != -1 and end == -1:
            raise TruncatedReply(
                f"reply opened a JSON object but never closed it "
                f"({len(raw)} chars received) — raise max_tokens")
        raise json.JSONDecodeError(
            f"no JSON object in model reply (got {len(raw)} chars: "
            f"{raw[:200]!r})", raw or "", 0)
    return json.loads(raw[start:end + 1])


def write_post(item: dict, body: str) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("DORMANT: ANTHROPIC_API_KEY not set.")
        sys.exit(3)
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    user = (f"SOURCE: {item['source']}\nTITLE: {item['title']}\nURL: {item['link']}\n"
            f"RSS SUMMARY: {item['summary']}\n\nARTICLE TEXT (may be partial):\n{body}\n\n"
            "Write the expert analysis post now.")
    try:
        msg = client.messages.create(
            model=MODEL, max_tokens=MAX_POST_TOKENS,
            system=[{"type": "text", "text": NEWS_SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.BadRequestError as e:
        if "credit balance" in str(e).lower():
            print("DORMANT: Anthropic credit balance is empty.")
            sys.exit(3)
        raise
    raw = msg.content[0].text.strip()
    # stop_reason is the single most useful diagnostic here and was never logged;
    # "max_tokens" means the post was cut off, not that the model misbehaved.
    if msg.stop_reason == "max_tokens":
        print(f"  TRUNCATED at max_tokens={MAX_POST_TOKENS} "
              f"({msg.usage.output_tokens} output tokens) — SKIPPED, no retry "
              f"(a retry at the same cap would truncate identically). "
              f"Raise MAX_POST_TOKENS if this recurs.")
        raise TruncatedReply(f"hit max_tokens={MAX_POST_TOKENS}")
    try:
        return _parse_post_json(raw)
    except TruncatedReply as e:
        # Ran out of budget without the API flagging it — same conclusion:
        # re-asking at the same ceiling is spend with no chance of success.
        print(f"  TRUNCATED ({e}) — SKIPPED, no retry")
        raise
    except json.JSONDecodeError as e:
        # The model occasionally emits an unescaped quote/newline inside a JSON
        # string. Rather than lose the post (and, before this, the rest of the
        # run), hand the broken text back and ask for a clean re-emit once.
        print(f"  invalid JSON from model ({e}) — retrying once")
        fix = client.messages.create(
            model=MODEL, max_tokens=MAX_POST_TOKENS,
            messages=[
                {"role": "user", "content": user},
                {"role": "assistant", "content": raw},
                {"role": "user", "content":
                 "That was not valid JSON — it failed to parse. Re-emit the same "
                 "content as strictly valid JSON matching the schema. Escape every "
                 "quote, backslash and newline inside string values. Output the "
                 "JSON object only, with no text before or after it."},
            ],
        )
        return _parse_post_json(fix.content[0].text.strip())


class ReviewRejected(Exception):
    """The grounding review refused the post. Carries the issues for logging."""

    def __init__(self, message: str, issues: list[dict] | None = None):
        super().__init__(message)
        self.issues = issues or []


def _client():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("DORMANT: ANTHROPIC_API_KEY not set.")
        sys.exit(3)
    import anthropic
    return anthropic.Anthropic(api_key=key)


def _draft_for_review(post: dict) -> str:
    """Flatten the post to plain text so the reviewer judges the words that will
    actually be published, not a JSON structure it has to mentally render."""
    out = [f"TITLE: {post.get('title','')}",
           f"CATEGORY: {post.get('category','')}",
           f"SUMMARY: {post.get('summary','')}", ""]
    for k, label in SECTION_LABELS.items():
        val = post.get("sections", {}).get(k)
        if not val:
            continue
        if isinstance(val, list):
            out.append(f"{label}:")
            out.extend(f"  - {v}" for v in val)
        else:
            out.append(f"{label}: {val}")
        out.append("")
    return "\n".join(out)


def review_post(client, item: dict, body: str, post: dict) -> dict:
    """Ground every factual claim in the draft against the source article.

    Fail-closed by contract: this raises ReviewRejected on a FAIL verdict AND on
    any outcome it cannot interpret (unparseable reply, truncation, API error).
    The caller must treat an exception as "do not publish" -- never as "publish
    anyway, we tried".
    """
    user = (
        f"SOURCE ARTICLE\n"
        f"Publication: {item['source']}\n"
        f"Headline: {item['title']}\n"
        f"URL: {item['link']}\n"
        f"RSS summary: {item.get('summary','')}\n\n"
        f"--- ARTICLE TEXT (may be partial) ---\n{body}\n--- END ARTICLE TEXT ---\n\n"
        f"DRAFT POST TO REVIEW\n{_draft_for_review(post)}\n\n"
        "Fact-check the draft against the source article now."
    )
    try:
        msg = client.messages.create(
            model=REVIEW_MODEL, max_tokens=MAX_REVIEW_TOKENS,
            system=[{"type": "text", "text": REVIEW_SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
    except Exception as e:                                    # noqa: BLE001
        raise ReviewRejected(f"reviewer unreachable ({type(e).__name__}: {e})")

    if msg.stop_reason == "max_tokens":
        # A truncated review is an unknown verdict, and unknown means no.
        raise ReviewRejected(f"review truncated at max_tokens={MAX_REVIEW_TOKENS}")
    try:
        result = _parse_post_json(msg.content[0].text.strip())
    except Exception as e:                                    # noqa: BLE001
        raise ReviewRejected(f"unparseable review reply ({type(e).__name__}: {e})")

    verdict = str(result.get("verdict", "")).upper()
    issues = result.get("issues") or []
    if verdict not in ("PASS", "FAIL"):
        raise ReviewRejected(f"reviewer returned no usable verdict ({verdict!r})", issues)
    critical = [i for i in issues if str(i.get("severity", "")).lower() == "critical"]
    # Trust the issue list over the verdict label: a reviewer that lists a
    # critical problem and still says PASS has contradicted itself, and the
    # safe reading of a contradiction is the stricter one.
    if verdict == "FAIL" or critical:
        raise ReviewRejected(
            f"{len(critical)} critical / {len(issues)} total issue(s)", issues)
    return result


def _print_issues(issues: list[dict], indent: str = "    ") -> None:
    for i in issues:
        sev = str(i.get("severity", "?")).upper()
        print(f"{indent}[{sev}] {i.get('category','?')} @ {i.get('location','?')}")
        q = str(i.get("quote", ""))[:160]
        if q:
            print(f"{indent}  quote: {q!r}")
        if i.get("why"):
            print(f"{indent}  why  : {i['why']}")


def repair_post(client, item: dict, body: str, post: dict, issues: list[dict]) -> dict:
    """One corrective pass. The model gets its own draft plus the specific
    findings, and must fix exactly those without inventing replacements."""
    findings = "\n".join(
        f"- [{i.get('severity','?')}] {i.get('category','?')} in {i.get('location','?')}\n"
        f"  problem text: {str(i.get('quote',''))[:300]!r}\n"
        f"  why: {i.get('why','')}\n"
        f"  fix: {i.get('fix','')}"
        for i in issues) or "- (no itemised findings; the review could not be trusted)"

    user = (
        f"SOURCE ARTICLE\nPublication: {item['source']}\nHeadline: {item['title']}\n"
        f"URL: {item['link']}\n\n--- ARTICLE TEXT ---\n{body}\n--- END ---\n\n"
        f"YOUR DRAFT\n{json.dumps(post, ensure_ascii=False, indent=1)}\n\n"
        f"A fact-checking editor rejected this draft. Findings:\n{findings}\n\n"
        "Re-emit the COMPLETE post as valid JSON in the same schema, with every "
        "finding fixed. Rules for fixing: delete an unsupported specific rather "
        "than replacing it with a different one; if a claim is your analysis, "
        "rewrite it so it plainly reads as Green Curve's view; never invent a "
        "figure, date, clause or quotation to fill a gap; a shorter, fully "
        "grounded post is the correct outcome. Output the JSON object only."
    )
    msg = client.messages.create(
        model=MODEL, max_tokens=MAX_REPAIR_TOKENS,
        system=[{"type": "text", "text": NEWS_SYSTEM_PROMPT,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    if msg.stop_reason == "max_tokens":
        raise TruncatedReply(f"repair hit max_tokens={MAX_REPAIR_TOKENS}")
    return _parse_post_json(msg.content[0].text.strip())


#: Craft rules the writer prompt now states. Measured against the 179-post
#: corpus on 2026-08-01, every one of these was being broken (median title 122
#: chars, median lede 36 words, 47% of ledes opening with attribution, 28%
#: carrying a bare URL). The prompt asks; this reports whether it worked.
#:
#: DELIBERATELY NON-BLOCKING. Craft is not truth. A 74-character title is worth
#: knowing about, not worth spending the day's budget and publishing nothing
#: over -- that is what ReviewRejected is for, and it stays reserved for
#: fabrication. Findings print to stdout, which is journalctl under the
#: gc-daily-blog timer. Corpus-level drift is caught separately by
#: writing_audit.py --check in the writing-greencurve-blogs skill.
TITLE_CHARS_MAX = 70
TITLE_HOOK_BY_CHAR = 60
LEDE_WORDS_MAX = 30
_INDIA_HOOK = re.compile(r"India|SEBI|BRSR|CPCB|MoEFCC|CCTS|LODR|filer", re.I)
_LEDE_ATTRIBUTION = re.compile(
    r"^(reporting by|according to|as reported|in an? (article|report)|per )\b", re.I)
_BARE_URL = re.compile(r"https?://\S+")


def craft_warnings(post: dict) -> list[str]:
    """Report craft-rule breaches in a drafted post. Never raises, never blocks."""
    out = []
    title = str(post.get("title", ""))
    if len(title) > TITLE_CHARS_MAX:
        out.append(f"title is {len(title)} chars (limit {TITLE_CHARS_MAX})")
    if _INDIA_HOOK.search(title) and not _INDIA_HOOK.search(title[:TITLE_HOOK_BY_CHAR]):
        out.append(f"India hook falls after char {TITLE_HOOK_BY_CHAR} of the title "
                   f"- it is cut off in search results")
    elif not _INDIA_HOOK.search(title):
        out.append("title has no India/regulator hook")

    what_changed = str((post.get("sections") or {}).get("what_changed", ""))
    # The Source: line is required to sit at the end, so exclude it from the lede.
    prose = re.sub(r"^\s*Source:\s*\S+\s*$", "", what_changed, flags=re.M).strip()
    parts = [s for s in re.split(r"(?<=[.!?])\s+", prose) if len(s.split()) > 2]
    if parts:
        lede = parts[0]
        if len(lede.split()) > LEDE_WORDS_MAX:
            out.append(f"lede is {len(lede.split())} words (limit {LEDE_WORDS_MAX})")
        if _LEDE_ATTRIBUTION.match(lede):
            out.append("lede opens with attribution instead of the news")
        if _BARE_URL.search(lede):
            out.append("lede contains a bare URL")
    return out


def write_and_verify(item: dict, body: str) -> tuple[dict, dict]:
    """Draft -> review -> (repair -> re-review). Returns (post, review).

    Raises ReviewRejected if the post cannot be made publishable. Nothing
    downstream may publish a post that did not come back from this function.
    """
    client = _client()
    post = write_post(item, body)

    try:
        review = review_post(client, item, body, post)
        print("  REVIEW PASS — every claim grounded in the source")
        return post, review
    except ReviewRejected as first:
        print(f"  REVIEW FAIL — {first}")
        _print_issues(first.issues)
        if not first.issues:
            # No actionable findings means there is nothing to repair against;
            # re-asking would be spend with no defined target.
            raise
        # Python unbinds the `as` name when the except block ends, so the
        # findings have to be carried out explicitly.
        first_issues = list(first.issues)
        print("  repairing once against the findings...")

    post = repair_post(client, item, body, post, first_issues)
    review = review_post(client, item, body, post)   # propagates on second failure
    print("  REVIEW PASS after repair")
    return post, review


# ── Rendering (format matches the 95 pre-June-12 posts) ───────────────────────
def render_post_page(post: dict, item: dict, pid: str, date_iso: str) -> str:
    sections_html = ""
    for k, label in SECTION_LABELS.items():
        val = post.get("sections", {}).get(k)
        if not val:
            continue
        if isinstance(val, list):
            lis = "".join(f"<li>{_esc(i)}</li>" for i in val)
            sections_html += f'<div class="post-section"><h2>{_esc(label)}</h2><ul>{lis}</ul></div>'
        else:
            sections_html += f'<div class="post-section"><h2>{_esc(label)}</h2><p>{_esc(val)}</p></div>'
    title, summary, category = post["title"], post["summary"], post.get("category", "ESG Intelligence")
    post_url = f"{SITE_URL}/posts/{pid}.html"
    pub_date = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d %B %Y")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{_esc(title)} — Green Curve</title>
  <meta name="description" content="{_esc(summary[:200])}"/>
  <meta name="robots" content="index,follow"/>
  <link rel="canonical" href="{post_url}"/>
  <meta property="og:type"        content="article"/>
  <meta property="og:url"         content="{post_url}"/>
  <meta property="og:title"       content="{_esc(title)}"/>
  <meta property="og:description" content="{_esc(summary[:200])}"/>
  <meta property="og:image"       content="{SITE_URL}/assets/img/logo.png"/>
  <meta property="article:published_time" content="{date_iso}"/>
  <meta property="article:section"        content="{_esc(category)}"/>
  <script type="application/ld+json">{{
    "@context":"https://schema.org",
    "@type":"Article",
    "headline":"{_esc(title)}",
    "datePublished":"{date_iso}",
    "publisher":{{"@type":"Organization","name":"Green Curve","url":"{SITE_URL}"}},
    "description":"{_esc(summary[:200])}",
    "url":"{post_url}"
  }}</script>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600&display=swap" rel="stylesheet"/>
  <link rel="icon" href="/assets/img/logo.png?v=2" type="image/png"/>
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{font-family:'DM Sans',sans-serif;background:#0f172a;color:#e2e8f0;line-height:1.7;min-height:100vh}}
    a{{color:#10b981;text-decoration:none}}
    a:hover{{text-decoration:underline}}
    .site-nav{{background:#0f172a;border-bottom:1px solid #1e293b;padding:16px 24px;display:flex;align-items:center;gap:20px;flex-wrap:wrap}}
    .site-nav .logo{{font-weight:700;font-size:1.1rem;color:#fff}}
    .site-nav .logo span{{color:#10b981}}
    .site-nav a{{color:#94a3b8;font-size:.88rem}}
    .site-nav a:hover{{color:#fff;text-decoration:none}}
    .container{{max-width:800px;margin:0 auto;padding:40px 24px 80px}}
    .post-meta{{display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap}}
    .post-category{{background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.25);color:#10b981;padding:3px 10px;border-radius:100px;font-size:.75rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em}}
    .post-date{{font-size:.82rem;color:#64748b}}
    .post-source{{font-size:.82rem;color:#64748b}}
    h1{{font-family:'DM Serif Display',serif;font-size:clamp(1.6rem,3vw,2.2rem);color:#fff;line-height:1.2;margin-bottom:20px;letter-spacing:-.02em}}
    .post-summary{{font-size:1rem;color:#94a3b8;line-height:1.8;padding:20px;background:#1e293b;border-left:3px solid #10b981;border-radius:0 8px 8px 0;margin-bottom:32px}}
    .post-section{{margin-bottom:32px;padding-bottom:32px;border-bottom:1px solid #1e293b}}
    .post-section:last-child{{border-bottom:none}}
    .post-section h2{{font-family:'DM Serif Display',serif;font-size:1.2rem;color:#10b981;margin-bottom:12px}}
    .post-section p{{color:#cbd5e1;font-size:.95rem;line-height:1.8}}
    .post-section ul{{padding-left:20px;color:#cbd5e1;font-size:.95rem}}
    .post-section li{{margin-bottom:8px;line-height:1.7}}
    .source-link{{margin-top:32px;padding:16px 20px;background:#1e293b;border-radius:8px;font-size:.88rem}}
    .source-link a{{font-weight:600}}
    .back-link{{display:inline-flex;align-items:center;gap:6px;color:#64748b;font-size:.85rem;margin-bottom:24px;transition:color .2s}}
    .back-link:hover{{color:#10b981;text-decoration:none}}
    footer{{border-top:1px solid #1e293b;padding:24px;text-align:center;font-size:.8rem;color:#475569;margin-top:40px}}
  </style>
</head>
<body>
<nav class="site-nav">
  <a href="{SITE_URL}/" class="logo">Green <span>Curve</span></a>
  <a href="{SITE_URL}/posts/">Insights</a>
  <a href="{SITE_URL}/calculator">GHG Calculator</a>
  <a href="{SITE_URL}/brsr-generator">BRSR Report</a>
  <a href="{SITE_URL}/search">Company Search</a>
</nav>

<div class="container">
  <a class="back-link" href="{SITE_URL}/posts/">&larr; Back to Insights</a>

  <div class="post-meta">
    <span class="post-category">{_esc(category)}</span>
    <span class="post-date">{pub_date}</span>
    <span class="post-source">via {_esc(item['source'])}</span>
  </div>

  <h1>{_esc(title)}</h1>

  <div class="post-summary">{_esc(summary)}</div>

  {sections_html}

  <div class="source-link">Source: <a href="{_esc(item['link'])}" target="_blank" rel="noopener">{_esc(item['link'])}</a></div>
</div>

<footer>
  &copy; {datetime.now().year} Green Curve &mdash; ESG &amp; Climate Intelligence for Indian Businesses &mdash;
  <a href="{SITE_URL}/">greencurve.solutions</a>
</footer>
</body>
</html>"""


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:60].rstrip("-")


# ── Site surface updates (feed.xml + posts/index.html string surgery) ─────────
def update_feed(post: dict, pid: str, date_iso: str) -> None:
    if not FEED_PATH.exists():
        print("  feed.xml missing — skipped")
        return
    xml = FEED_PATH.read_text(encoding="utf-8")
    url = f"{SITE_URL}/posts/{pid}.html"
    if url in xml:
        return
    pub = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%a, %d %b %Y 06:00:00 +0530")
    item = (f"\n    <item>\n      <title>{_esc(post['title'])}</title>\n"
            f"      <link>{url}</link>\n"
            f"      <description>{_esc(post['summary'])}</description>\n"
            f"      <pubDate>{pub}</pubDate>\n"
            f"      <category>{_esc(post.get('category', ''))}</category>\n"
            f"      <guid isPermaLink=\"true\">{url}</guid>\n    </item>\n")
    xml = re.sub(r"</image>", lambda m: m.group(0) + item, xml, count=1)
    xml = re.sub(r"<lastBuildDate>.*?</lastBuildDate>",
                 f"<lastBuildDate>{datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0530')}</lastBuildDate>",
                 xml, count=1)
    FEED_PATH.write_text(xml, encoding="utf-8")


def update_index(post: dict, pid: str, date_iso: str) -> None:
    if not INDEX_PATH.exists():
        print("  posts/index.html missing — skipped")
        return
    html = INDEX_PATH.read_text(encoding="utf-8")
    if f'href="{pid}.html"' in html:
        return
    card = (f'\n      <a class="post-card" href="{pid}.html">\n'
            f'        <span class="post-cat">{_esc(post.get("category", "ESG"))}</span>\n'
            f'        <h2 class="post-title">{_esc(post["title"])}</h2>\n'
            f'        <p class="post-desc">{_esc(post["summary"][:180])}…</p>\n'
            f'        <span class="post-date">{date_iso}</span>\n      </a>\n')
    marker = '<section class="grid">'
    if marker not in html:
        print("  posts/index.html grid marker not found — card skipped")
        return
    INDEX_PATH.write_text(html.replace(marker, marker + card, 1), encoding="utf-8")


def update_index_json(post: dict, item: dict, pid: str, date_iso: str) -> None:
    """The homepage's "Latest Insights" widget (assets/js/app.js loadPosts())
    reads posts/index.json, not posts/index.html — must stay in sync or new
    posts never appear there even though the standalone pages publish fine."""
    if INDEX_JSON_PATH.exists():
        data = json.loads(INDEX_JSON_PATH.read_text(encoding="utf-8"))
    else:
        data = {"posts": []}
    if any(p.get("id") == pid for p in data["posts"]):
        return
    data["posts"].insert(0, {
        "id": pid,
        "title": post["title"],
        "date": date_iso,
        "category": post.get("category", "ESG Intelligence"),
        "source": item["source"],
        "summary": post["summary"],
        "link": item["link"],
        "sections": post.get("sections", {}),
    })
    INDEX_JSON_PATH.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=MAX_PER_RUN_DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    processed = load_processed()
    fresh = []
    for src in NEWS_SOURCES:
        for it in fetch_items(src):
            if it["link"] not in processed and _relevant(it):
                fresh.append(it)
        if len(fresh) >= args.max * 3:
            break
    print(f"{len(fresh)} fresh relevant item(s) found")
    if not fresh:
        print("No fresh news — nothing to publish today.")
        return 0

    published = []
    date_iso = datetime.now().strftime("%Y-%m-%d")
    failures = 0
    rejected = 0
    for item in fresh[: args.max]:
        print(f"Writing: [{item['source']}] {item['title'][:80]}")
        try:
            body = fetch_article_body(item["link"])
            # Nothing may reach the filesystem that has not come back from
            # write_and_verify — that function is the only publishable path.
            post, _review = write_and_verify(item, body)   # SystemExit(3) if dormant
            for w in craft_warnings(post):
                print(f"  CRAFT — {w}")
            pid = f"{_slug(post['title'])}-{int(time.time())}"
            page = render_post_page(post, item, pid, date_iso)
        except SystemExit:
            raise                              # dormancy is fatal by design
        except ReviewRejected as e:
            # Deliberate, not an error: the gate did its job. Mark the item
            # processed so a post the reviewer already refused is not redrafted
            # and re-billed every morning.
            rejected += 1
            print(f"  NOT PUBLISHED — review gate refused it: {e}")
            _print_issues(e.issues)
            processed.add(item["link"])
            save_processed(processed)
            continue
        except Exception as e:
            # One malformed post must not take the rest of the run down with it.
            failures += 1
            print(f"  SKIPPED — {type(e).__name__}: {e}")
            continue
        if args.dry_run:
            print(f"  DRY RUN — would publish posts/{pid}.html")
            continue
        (POSTS_DIR / f"{pid}.html").write_text(page, encoding="utf-8")
        update_feed(post, pid, date_iso)
        update_index(post, pid, date_iso)
        update_index_json(post, item, pid, date_iso)
        processed.add(item["link"])
        save_processed(processed)
        published.append(f"{SITE_URL}/posts/{pid}.html")
        print(f"  Published: {published[-1]}")

    if failures or rejected:
        print(f"{failures} item(s) skipped after errors; "
              f"{rejected} refused by the review gate; {len(published)} published")

    if published:
        try:
            subprocess.run([sys.executable, str(BASE_DIR / "tools" / "indexnow_ping.py"),
                            *published], cwd=BASE_DIR, timeout=90, check=False)
        except Exception as e:
            print(f"IndexNow ping skipped: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
