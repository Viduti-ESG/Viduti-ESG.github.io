#!/usr/bin/env python3
"""Re-submit all sitemap URLs to IndexNow (Bing/Yandex/DuckDuckGo + AI search).

Run after deploying new/changed pages so they get indexed near-instantly
instead of waiting for the next crawl. Run from the site root (where
sitemap.xml and the <key>.txt file live):

    python3 tools/indexnow_ping.py
    python3 tools/indexnow_ping.py https://greencurve.solutions/new-page.html  # one URL

Key file (16f485c162fd4f660abd757205cee3e0.txt) must stay published at the
site root for verification. Google ignores IndexNow but crawls the sitemap.
"""
import re, sys, json, urllib.request, urllib.error

KEY = "16f485c162fd4f660abd757205cee3e0"
HOST = "greencurve.solutions"
ENDPOINTS = ["https://api.indexnow.org/indexnow", "https://www.bing.com/indexnow"]


def urls():
    if len(sys.argv) > 1:
        return sys.argv[1:]
    xml = open("sitemap.xml", encoding="utf-8").read()
    return [u.strip() for u in re.findall(r"<loc>(.*?)</loc>", xml) if u.strip()]


def main():
    locs = urls()[:10000]
    payload = {
        "host": HOST,
        "key": KEY,
        "keyLocation": f"https://{HOST}/{KEY}.txt",
        "urlList": locs,
    }
    body = json.dumps(payload).encode()
    print(f"Submitting {len(locs)} URL(s) to IndexNow...")
    for ep in ENDPOINTS:
        req = urllib.request.Request(
            ep, data=body, headers={"Content-Type": "application/json; charset=utf-8"}
        )
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                print(f"  {ep} -> {r.status} OK")
        except urllib.error.HTTPError as e:
            print(f"  {ep} -> {e.code} {e.read().decode()[:120]}")
        except Exception as e:
            print(f"  {ep} -> ERR {e}")


if __name__ == "__main__":
    main()
