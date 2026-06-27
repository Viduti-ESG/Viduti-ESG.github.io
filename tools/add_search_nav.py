#!/usr/bin/env python3
"""
One-off, idempotent nav propagation: add a "Semantic Search" link to the
ESG Quotient dropdown (desktop) and the ESG Quotient mobile group, on every
page that already carries the Peer Benchmarking nav entry.

Anchored on the existing Benchmarking lines so it slots in right after them and
inherits each page's own indentation. Safe to re-run — skips pages that already
link to /search.

  python tools/add_search_nav.py            # apply
  python tools/add_search_nav.py --dry-run  # preview only
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# (anchor regex, inserted line template).  {i} = captured leading indentation.
DESKTOP_ANCHOR = re.compile(
    r'^(?P<i>[ \t]*)<li><a href="/benchmark">Peer Benchmarking <span class="nav-new">NEW</span></a></li>[ \t]*$',
    re.M,
)
DESKTOP_INSERT = '{i}<li><a href="/search">Semantic Search <span class="nav-new">NEW</span></a></li>'

MOBILE_ANCHOR = re.compile(
    r'^(?P<i>[ \t]*)<a href="/benchmark">Peer Benchmarking</a>[ \t]*$',
    re.M,
)
MOBILE_INSERT = '{i}<a href="/search">Semantic Search</a>'


def patch(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []
    if 'href="/search"' in text:
        return text, changes  # already present anywhere -> treat page as done

    def _desktop(m: re.Match) -> str:
        changes.append("desktop")
        return m.group(0) + "\n" + DESKTOP_INSERT.format(i=m.group("i"))

    def _mobile(m: re.Match) -> str:
        changes.append("mobile")
        return m.group(0) + "\n" + MOBILE_INSERT.format(i=m.group("i"))

    # Only replace the first occurrence of each (nav appears once per page).
    text = DESKTOP_ANCHOR.sub(_desktop, text, count=1)
    text = MOBILE_ANCHOR.sub(_mobile, text, count=1)
    return text, changes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    total = 0
    for html in sorted(BASE.glob("*.html")):
        original = html.read_text(encoding="utf-8")
        patched, changes = patch(original)
        if changes:
            total += 1
            tag = "+".join(changes)
            print(f"{'[dry] ' if args.dry_run else ''}{html.name:28} -> added: {tag}")
            if not args.dry_run:
                html.write_text(patched, encoding="utf-8")
    print(f"\n{total} page(s) {'would be' if args.dry_run else ''} updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
