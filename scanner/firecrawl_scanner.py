"""Scan for trending topics via Firecrawl search across platforms."""

import os
import json
import time
import yaml
from firecrawl import FirecrawlApp
from dotenv import load_dotenv

load_dotenv()

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
CACHE_TTL_SECONDS = 3 * 24 * 3600  # matches scanner.run_every_days default

PLATFORM_DOMAINS = {
    "twitter":  ["x.com", "twitter.com"],
    "reddit":   ["reddit.com"],
    "hn":       ["news.ycombinator.com"],
    "linkedin": ["linkedin.com"],
    "web":      [],
}

RECENCY_MAP = {
    "hour":  "qdr:h",
    "day":   "qdr:d",
    "week":  "qdr:w",
    "month": "qdr:m",
}


def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def scan_trends(use_cache: bool = True) -> list[dict]:
    """Run Firecrawl searches for all seed keywords × platforms. Returns raw trend hits.
    Caches results locally for CACHE_TTL_SECONDS so repeated dev/test runs don't
    re-burn Firecrawl credits within the same scan window."""
    cache_file = os.path.join(CACHE_DIR, "last_scan.json")
    if use_cache and os.path.exists(cache_file):
        age = time.time() - os.path.getmtime(cache_file)
        if age < CACHE_TTL_SECONDS:
            with open(cache_file) as f:
                trends = json.load(f)
            print(f"[scanner] Loaded {len(trends)} trend hits from cache (age {int(age/3600)}h)")
            print("[scanner] Delete scanner/cache/last_scan.json to force a fresh Firecrawl scan.")
            return trends

    cfg = load_config()
    scanner_cfg = cfg["scanner"]
    app = FirecrawlApp(api_key=os.environ["FIRECRAWL_API_KEY"])

    tbs = RECENCY_MAP.get(scanner_cfg["recency"], "qdr:w")
    limit = scanner_cfg["results_per_query"]
    platforms = scanner_cfg["platforms"]
    keywords = cfg["seed_keywords"]

    trends = []
    total_credits = 0

    for keyword in keywords:
        for platform in platforms:
            domains = PLATFORM_DOMAINS.get(platform, [])
            search_kwargs = {"limit": limit, "tbs": tbs}
            if domains:
                search_kwargs["include_domains"] = domains
            try:
                result = app.search(keyword, **search_kwargs)
                hits = getattr(result, "web", None) or getattr(result, "data", None) or []
                for hit in hits:
                    if hasattr(hit, "url"):
                        trends.append({
                            "keyword": keyword,
                            "platform": platform,
                            "title": getattr(hit, "title", "") or "",
                            "url": getattr(hit, "url", "") or "",
                            "description": getattr(hit, "description", "") or "",
                        })
                    else:
                        trends.append({
                            "keyword": keyword,
                            "platform": platform,
                            "title": hit.get("title", ""),
                            "url": hit.get("url", ""),
                            "description": hit.get("description", ""),
                        })
                    total_credits += 1
            except Exception as e:
                print(f"  [scanner] Error for '{keyword}' on {platform}: {e}")

    print(f"[scanner] {len(trends)} trend hits | ~{total_credits} Firecrawl credits used")

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(trends, f)

    return trends


def dedupe_trends(trends: list[dict]) -> list[dict]:
    """Collapse duplicate URLs, return one entry per unique post/page found."""
    seen_urls = set()
    unique = []
    for t in trends:
        if t["url"] not in seen_urls and t["title"]:
            seen_urls.add(t["url"])
            unique.append(t)
    return unique


def group_by_keyword(trends: list[dict]) -> list[dict]:
    """Collapse all hits for the same keyword into one group.
    This is what prevents one keyword generating 7-9 near-identical outlines --
    every real post found under a keyword becomes a 'source' for a single outline
    instead of its own outline."""
    groups: dict[str, dict] = {}
    for t in trends:
        key = t["keyword"]
        if key not in groups:
            groups[key] = {"keyword": key, "sources": []}
        groups[key]["sources"].append({
            "platform": t["platform"],
            "title": t["title"],
            "url": t["url"],
            "description": t["description"],
        })
    return list(groups.values())


if __name__ == "__main__":
    raw = scan_trends()
    unique = dedupe_trends(raw)
    print(f"\n{len(unique)} unique trend signals:")
    for t in unique[:10]:
        print(f"  [{t['platform']}] {t['keyword']} → {t['title'][:60]}")
