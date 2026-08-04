"""Free, no-LLM triage sweep over every published post.

Splits the unreviewed corpus into 'no risky pattern, leave it' and 'worth
spending a review on'. Does not decide truth - it decides where truth is worth
checking. Detectors are deliberately tightened so a CORRECT statement of the
BRSR Core glide path does not get flagged.
"""
import html
import json
import re
import sys
from pathlib import Path
from collections import Counter

import os
POSTS = Path(os.environ.get('GC_POSTS_DIR',
                            str(Path(__file__).resolve().parent.parent / 'posts')))

# Ground truth for the BRSR Core reasonable-assurance glide path.
CORRECT_START = {'150': '2023-24', '250': '2024-25', '500': '2025-26', '1000': '2026-27'}
TOPN = re.compile(r'top[\s-]+(150|250|500|1,?000)\b', re.I)
FY = re.compile(r'FY[\s-]?(20)?(\d{2}[-–]\d{2})', re.I)


def _norm_fy(raw):
    """FY23-24, FY2023-24, 2023-24 -> 2023-24."""
    raw = raw.replace(chr(8211), '-')
    a, b = raw.split('-')
    if len(a) == 2:
        a = '20' + a
    return a + '-' + b


def check_glide_path(t):
    """Flag ONLY where a top-N tier is given a start year that is not its real one."""
    out = []
    for m in TOPN.finditer(t):
        tier = m.group(1).replace(',', '')
        fy = FY.search(t[m.end():m.end() + 70])
        if not fy:
            continue
        got = _norm_fy(fy.group(2))
        want = CORRECT_START[tier]
        if got != want:
            out.append((f'top {tier} given FY{got}, real start is FY{want}',
                        t[max(0, m.start() - 70):m.end() + 90].strip()[:230]))
    return out


def check_core_scope(t):
    """BRSR Core's nine attributes claimed to cover something they do not."""
    out = []
    for m in re.finditer(r'BRSR Core', t):
        win = t[m.start():m.start() + 260]
        # must be an OBLIGATION verb, not a bare mention in a list of frameworks
        if not re.search(r'\b(mandat\w+|requir\w+|must|shall|obligat\w+)\b', win, re.I):
            continue
        # HARD only where I have verified the attribute list excludes it.
        # Scope 3 / transition plans are arguable via the value-chain
        # comply-or-explain limb, so they are RISK, adjudicated separately.
        if re.search(r'physical (climate )?risk', win, re.I):
            out.append(('BRSR Core stated as mandating physical climate risk - '
                        'not one of the nine attributes', win.strip()[:230]))
    return out


def check_core_scope_soft(t):
    """Arguable: Scope 3 / transition plans attributed to BRSR Core."""
    out = []
    for m in re.finditer(r'BRSR Core', t):
        win = t[m.start():m.start() + 260]
        if not re.search(r'\b(mandat\w+|requir\w+|must|shall)\b', win, re.I):
            continue
        for topic, label in [(r'\bScope 3\b', 'Scope 3'),
                             (r'transition plan', 'transition plans')]:
            if re.search(topic, win, re.I):
                out.append((f'BRSR Core tied to {label} - not an assured attribute; '
                            f'arguable only via value-chain comply-or-explain',
                            win.strip()[:230]))
                break
    return out


CHECKS = [
    ('HARD', 'brsr_core_limited_assurance',
     lambda t: [(m.group(0)[:60], t[max(0, m.start() - 70):m.end() + 70].strip()[:230])
                for m in re.finditer(r'BRSR Core[^.]{0,200}limited assurance|'
                                     r'limited assurance[^.]{0,200}BRSR Core', t, re.I)],
     'BRSR Core requires REASONABLE assurance, never limited'),
    ('HARD', 'brsr_core_glide_path', check_glide_path,
     'a BRSR Core tier tied to the wrong first year'),
    ('HARD', 'brsr_core_scope', check_core_scope,
     'BRSR Core stated as mandating something outside its nine attributes'),

    ('RISK', 'brsr_core_scope_soft', check_core_scope_soft,
     'BRSR Core tied to Scope 3 / transition plans - arguable, verify scope'),
    ('RISK', 'invented_citation_shape',
     lambda t: [(m.group(0)[:60], t[max(0, m.start() - 70):m.end() + 70].strip()[:200])
                for m in re.finditer(r'Essential Indicator\s*[:,]|'
                                     r'\b(Clause|Regulation|Section|Rule)\s+\d+[A-Z]?\(', t)],
     'a named clause/indicator - verify it exists and says this'),
    ('RISK', 'deal_status_verb',
     lambda t: [(m.group(0)[:60], t[max(0, m.start() - 70):m.end() + 70].strip()[:200])
                for m in re.finditer(r'\b(completed|closed|finalised|finalized) (the )?acquisition|'
                                     r'\bhas acquired\b|\bfull acquisition\b', t, re.I)],
     'M&A stated as done - most announcements are agreed and pending approval'),
    ('RISK', 'stance_verb',
     lambda t: [(m.group(0)[:60], t[max(0, m.start() - 70):m.end() + 70].strip()[:200])
                for m in re.finditer(r'\b\d{1,3}%[^.]{0,60}\b(oppose[sd]?|reject\w*|are against)\b', t, re.I)],
     'a percentage attached to a stance verb - check the source wording'),
    ('RISK', 'named_co_obligation',
     lambda t: [(m.group(0)[:60], t[max(0, m.start() - 70):m.end() + 70].strip()[:200])
                for m in re.finditer(r'\b(NTPC|Adani[\w ]*|Tata Power|Coal India|ONGC|JSW[\w ]*|'
                                     r'Vedanta|CESC|Torrent Power)\b[^.]{0,110}'
                                     r'\b(must |facing |are required to |obligation)', t)],
     'a named listed company tied to an obligation'),
]


def text_of(p):
    s = p.read_text(encoding='utf-8', errors='ignore')
    s = re.sub(r'<script.*?</script>', ' ', s, flags=re.S)
    s = re.sub(r'<style.*?</style>', ' ', s, flags=re.S)
    s = re.sub(r'<[^>]+>', ' ', s)
    return html.unescape(re.sub(r'\s+', ' ', s))


def main():
    files = sorted(f for f in POSTS.glob('*.html') if f.name != 'index.html')
    rows, tally = [], Counter()
    for f in files:
        t = text_of(f)
        hits = []
        for level, name, fn, why in CHECKS:
            for label, quote in fn(t):
                hits.append({'level': level, 'check': name, 'detail': label,
                             'why': why, 'quote': quote})
                tally[name] += 1
        if hits:
            rows.append({'post': f.name,
                         'hard': sum(1 for h in hits if h['level'] == 'HARD'),
                         'risk': sum(1 for h in hits if h['level'] == 'RISK'),
                         'hits': hits})

    hard = [r for r in rows if r['hard']]
    risk = [r for r in rows if not r['hard'] and r['risk']]
    print('posts on disk        : %d' % len(files))
    print('clean (no pattern)   : %d' % (len(files) - len(rows)))
    print('HARD (wrong on face) : %d posts' % len(hard))
    print('RISK (worth a look)  : %d posts' % len(risk))
    print()
    print('hits by check:')
    for k, v in tally.most_common():
        print('  %-28s %d' % (k, v))
    print()
    for r in hard[:14]:
        print('HARD %s' % r['post'][:66])
        for h in r['hits']:
            if h['level'] == 'HARD':
                print('      %s' % h['detail'][:110])
    POSTS.parent / "post_sweep.json".write_text(
        json.dumps({'scanned': len(files), 'hard': len(hard), 'risk': len(risk),
                    'rows': rows}, indent=1))
    print('\nfull detail: /tmp/post_sweep.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
