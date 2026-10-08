#!/usr/bin/env python3
"""
CuriousScan Deal Radar
======================
An open-source keyword watcher for deal hunters.

Polls public deal communities (Reddit RSS feeds) for the keywords you care
about ("free", "promo code", "giveaway", ...) and prints matching posts as
they appear. Stdlib only — no dependencies, no accounts, no keys.

Usage:
    python deal_radar.py --once --keywords free,giveaway,"promo code"
    python deal_radar.py --watch --interval 300 --subreddits deals,buildapcsales
    python deal_radar.py --once --json > hits.json
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

VERSION = "0.1.0"
USER_AGENT = f"curiousscan-deal-radar/{VERSION} (open-source keyword watcher)"
ATOM_NS = "{http://www.w3.org/2005/Atom}"

DEFAULT_SUBREDDITS = [
    "buildapcsales",
    "deals",
    "FreeEBOOKS",
    "GameDeals",
    "frugalmalefashion",
]

DEFAULT_KEYWORDS = ["free", "giveaway", "promo code", "coupon", "100% off"]


def fetch_new(subreddit):
    """Fetch the newest posts from a subreddit via its public RSS feed."""
    url = f"https://www.reddit.com/r/{subreddit}/new/.rss"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        tree = ET.parse(resp)
    posts = []
    for entry in tree.getroot().findall(f"{ATOM_NS}entry"):
        link_el = entry.find(f"{ATOM_NS}link")
        content_el = entry.find(f"{ATOM_NS}content")
        posts.append(
            {
                "id": entry.findtext(f"{ATOM_NS}id", default=""),
                "title": entry.findtext(f"{ATOM_NS}title", default=""),
                "url": link_el.get("href", "") if link_el is not None else "",
                "body": re.sub(r"<[^>]+>", " ", content_el.text or "")
                if content_el is not None
                else "",
                "updated": entry.findtext(f"{ATOM_NS}updated", default=""),
            }
        )
    return posts


def matching_keywords(post, keywords):
    """Return the subset of keywords found in the post title/body."""
    text = (post["title"] + " " + post["body"]).lower()
    return [k for k in keywords if k.lower() in text]


def scan(subreddits, keywords, seen):
    """One scan pass across all subreddits. Returns list of hit dicts."""
    hits = []
    for sub in subreddits:
        try:
            posts = fetch_new(sub)
        except Exception as exc:  # network hiccup, bad subreddit, blocked
            print(f"[!] r/{sub}: {exc}", file=sys.stderr)
            continue
        for post in posts:
            if post["id"] in seen:
                continue
            seen.add(post["id"])
            ks = matching_keywords(post, keywords)
            if ks:
                hits.append(
                    {
                        "subreddit": sub,
                        "title": post["title"],
                        "url": post["url"],
                        "matched_keywords": ks,
                        "updated": post["updated"],
                    }
                )
    return hits


def print_hits(hits, as_json):
    if as_json:
        print(json.dumps(hits, indent=2))
        return
    for h in hits:
        print(f"[r/{h['subreddit']}] {h['title']}")
        print(f"  matched: {', '.join(h['matched_keywords'])}")
        print(f"  {h['url']}\n")
    if not hits:
        print("No matches this pass.")


def main():
    ap = argparse.ArgumentParser(
        description="CuriousScan Deal Radar — keyword watcher for deal communities."
    )
    ap.add_argument("--subreddits", default=",".join(DEFAULT_SUBREDDITS),
                    help="Comma-separated subreddits to watch.")
    ap.add_argument("--keywords", default=",".join(DEFAULT_KEYWORDS),
                    help="Comma-separated keywords to match (case-insensitive).")
    ap.add_argument("--once", action="store_true",
                    help="Run a single scan pass and exit.")
    ap.add_argument("--watch", action="store_true",
                    help="Poll continuously until Ctrl+C.")
    ap.add_argument("--interval", type=int, default=300,
                    help="Seconds between passes in --watch mode (default 300).")
    ap.add_argument("--json", action="store_true", help="Emit hits as JSON.")
    args = ap.parse_args()

    subreddits = [s.strip() for s in args.subreddits.split(",") if s.strip()]
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    if not subreddits or not keywords:
        ap.error("need at least one subreddit and one keyword")

    seen = set()
    if args.once or not args.watch:
        print_hits(scan(subreddits, keywords, seen), args.json)
        return

    print(f"[*] Watching {len(subreddits)} subs every {args.interval}s — Ctrl+C to stop.")
    try:
        while True:
            hits = scan(subreddits, keywords, seen)
            if hits:
                print(f"\n=== {datetime.now(timezone.utc).isoformat()} — {len(hits)} hit(s) ===")
                print_hits(hits, args.json)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[*] Stopped.")


if __name__ == "__main__":
    main()
