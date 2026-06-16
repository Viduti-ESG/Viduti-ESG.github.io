#!/usr/bin/env python3
"""
Green Curve — static asset build step.

Minifies every assets/js/*.js and assets/css/*.css into a parallel
``build/assets/`` tree using the SAME filenames. Because the deploy uploads
these over /var/www/greencurve/assets/, no HTML <script>/<link> references need
to change — the minified file simply replaces the readable source at the same
path in the deploy artifact. Source files in the repo stay un-minified.

Usage:
    pip install rjsmin rcssmin        # one-time, pure-Python, no Node required
    python build_assets.py            # writes ./build/assets/{js,css}/...

Deploy (example):
    python build_assets.py
    rsync -av build/assets/ user@server:/var/www/greencurve/assets/

If rjsmin/rcssmin are not installed the script copies files through unchanged
and prints an install hint, so a deploy never breaks for lack of the tools.
"""

import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
SRC = BASE / "assets"
OUT = BASE / "build" / "assets"

try:
    from rjsmin import jsmin
    from rcssmin import cssmin
    _HAVE_MINIFIERS = True
except ImportError:
    _HAVE_MINIFIERS = False
    def jsmin(s: str) -> str:   # type: ignore
        return s
    def cssmin(s: str) -> str:  # type: ignore
        return s


def _build(kind: str, ext: str, minify) -> tuple[int, int]:
    src_dir = SRC / kind
    out_dir = OUT / kind
    out_dir.mkdir(parents=True, exist_ok=True)
    total_in = total_out = 0
    for f in sorted(src_dir.glob(f"*.{ext}")):
        if f.name.endswith(f".min.{ext}"):
            continue
        raw = f.read_text(encoding="utf-8")
        out = minify(raw)
        (out_dir / f.name).write_text(out, encoding="utf-8")
        total_in += len(raw)
        total_out += len(out)
        pct = (1 - len(out) / len(raw)) * 100 if raw else 0
        print(f"  {kind}/{f.name:<32} {len(raw):>8,} -> {len(out):>8,}  ({pct:4.1f}% smaller)")
    return total_in, total_out


def main() -> int:
    if not _HAVE_MINIFIERS:
        print("WARNING: rjsmin/rcssmin not installed — copying assets unchanged.")
        print("         Run: pip install rjsmin rcssmin\n")

    if OUT.exists():
        shutil.rmtree(OUT)

    print("Minifying JavaScript:")
    js_in, js_out = _build("js", "js", jsmin)
    print("\nMinifying CSS:")
    css_in, css_out = _build("css", "css", cssmin)

    # Copy non-minifiable asset folders (data, img, fonts) through verbatim so
    # build/assets/ is a complete, deployable mirror.
    for sub in ("data", "img", "fonts"):
        s = SRC / sub
        if s.exists():
            shutil.copytree(s, OUT / sub, dirs_exist_ok=True)

    tot_in, tot_out = js_in + css_in, js_out + css_out
    saved = (1 - tot_out / tot_in) * 100 if tot_in else 0
    print(f"\nTotal JS+CSS: {tot_in:,} -> {tot_out:,} bytes ({saved:.1f}% smaller, pre-gzip)")
    print(f"Output: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
