#!/usr/bin/env python3
"""Interactive CLI to search recent social/web mentions via Firecrawl."""

import os
import sys
import json
import urllib.request

SEARCH_URL = "https://api.firecrawl.dev/v2/search"

PLATFORMS = {
    "1": ("Twitter/X", "site:x.com OR site:twitter.com"),
    "2": ("LinkedIn", "site:linkedin.com"),
    "3": ("Reddit", "site:reddit.com"),
    "4": ("Hacker News", "site:news.ycombinator.com"),
    "5": ("All web (no site restriction)", ""),
}

RECENCY = {
    "1": ("Past hour", "qdr:h"),
    "2": ("Past day", "qdr:d"),
    "3": ("Past week", "qdr:w"),
    "4": ("Past month", "qdr:m"),
}


def get_api_key():
    key = os.environ.get("FIRECRAWL_API_KEY")
    if key:
        return key
    key = input("Enter your Firecrawl API key (fc-...): ").strip()
    if not key:
        print("API key is required.")
        sys.exit(1)
    return key


def choose(prompt, options, allow_multi=False):
    print(prompt)
    for k, (label, _) in options.items():
        print(f"  {k}. {label}")
    raw = input("Choice" + (" (comma-separated for multiple)" if allow_multi else "") + ": ").strip()
    if allow_multi:
        keys = [c.strip() for c in raw.split(",") if c.strip() in options]
        if not keys:
            print("No valid choice, defaulting to all.")
            keys = list(options.keys())
        return keys
    return raw if raw in options else list(options.keys())[0]


def search(api_key, query, tbs, limit):
    body = json.dumps({"query": query, "limit": limit, "tbs": tbs}).encode()
    req = urllib.request.Request(
        SEARCH_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main():
    api_key = get_api_key()

    topic = input("\nWhat topic/keywords do you want to search for? ").strip()
    if not topic:
        print("Topic is required.")
        sys.exit(1)

    platform_keys = choose("\nWhich platform(s)?", PLATFORMS, allow_multi=True)
    recency_key = choose("\nHow recent?", RECENCY)
    _, tbs = RECENCY[recency_key]

    try:
        limit = int(input("\nHow many results per platform? (default 5): ").strip() or "5")
    except ValueError:
        limit = 5

    for pk in platform_keys:
        label, site_filter = PLATFORMS[pk]
        query = f"{topic} {site_filter}".strip()
        print(f"\n=== {label} ===")
        try:
            data = search(api_key, query, tbs, limit)
        except Exception as e:
            print(f"Error: {e}")
            continue

        results = data.get("data", {}).get("web", [])
        if not results:
            print("No results found.")
            continue

        for i, r in enumerate(results, 1):
            print(f"{i}. {r.get('title')}")
            print(f"   {r.get('url')}")
            desc = r.get("description", "")
            if desc:
                print(f"   {desc[:150]}")
            print()


if __name__ == "__main__":
    main()
