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
    python deal_radar.py --once --claude   # Claude-written digest (needs ANTHROPIC_API_KEY)
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

VERSION = "0.2.0"
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

# Claude integration (optional). Uses the Anthropic Messages API directly —
# stdlib only, no SDK needed. Verify current model IDs at
# https://docs.anthropic.com/en/docs/about-claude/models/overview
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-5-5"


def get_anthropic_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print(
            "ERROR: --claude needs ANTHROPIC_API_KEY.\n"
            "Get one at https://console.anthropic.com/ then run:\n"
            '  export ANTHROPIC_API_KEY="sk-ant-..."',
            file=sys.stderr,
        )
        sys.exit(2)
    return key


def claude_complete(api_key, model, system, user_text, max_tokens=1500):
    """One Anthropic Messages API call. Returns text or raises RuntimeError."""
    payload = json.dumps(
        {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user_text}],
        }
    ).encode()
    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.load(resp)
        return "".join(
            b.get("text", "")
            for b in data.get("content", [])
            if b.get("type") == "text"
        ).strip()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:300]
        raise RuntimeError(f"Claude API -> HTTP {exc.code}: {body}")


def claude_digest(hits, api_key, model):
    """Turn raw hits into a human analyst-style digest via Claude."""
    lines = [
        f"- [r/{h['subreddit']}] {h['title']} ({h['url']}) "
        f"[matched: {', '.join(h['matched_keywords'])}]"
        for h in hits
    ]
    user_text = (
        "Here are today's deal-feed hits. Write a short morning-brief digest: "
        "group by theme, flag the genuinely free or high-value ones, skip the "
        "junk. Keep it tight, no fluff.\n\n" + "\n".join(lines)
    )
    return claude_complete(
        api_key,
        model,
        "You are a sharp deal analyst writing a morning brief for bargain "
        "hunters. Terse, opinionated, honest about what is actually worth clicking.",
        user_text,
    )


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
    ap.add_argument("--claude", action="store_true",
                    help="Summarize hits into a Claude-written digest (needs ANTHROPIC_API_KEY).")
    ap.add_argument("--claude-model", default=DEFAULT_CLAUDE_MODEL,
                    help=f"Claude model for --claude (default {DEFAULT_CLAUDE_MODEL}).")
    args = ap.parse_args()

    subreddits = [s.strip() for s in args.subreddits.split(",") if s.strip()]
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    if not subreddits or not keywords:
        ap.error("need at least one subreddit and one keyword")

    claude_key = get_anthropic_key() if args.claude else None

    def report(hits):
        if not hits:
            print("No matches this pass.")
            return
        print_hits(hits, args.json)
        if claude_key:
            print("\n--- Claude digest ---\n")
            try:
                print(claude_digest(hits, claude_key, args.claude_model))
            except RuntimeError as exc:
                print(f"[!] Claude digest failed: {exc}", file=sys.stderr)
                print("[!] Showing raw hits only.", file=sys.stderr)

    seen = set()
    if args.once or not args.watch:
        report(scan(subreddits, keywords, seen))
        return

    print(f"[*] Watching {len(subreddits)} subs every {args.interval}s — Ctrl+C to stop.")
    try:
        while True:
            hits = scan(subreddits, keywords, seen)
            if hits:
                print(f"\n=== {datetime.now(timezone.utc).isoformat()} — {len(hits)} hit(s) ===")
                report(hits)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[*] Stopped.")


if __name__ == "__main__":
    main()
