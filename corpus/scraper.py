"""Scrape blog articles via Firecrawl and chunk them for embedding."""

import os
import re
import json
import time
import hashlib
import yaml
from firecrawl import FirecrawlApp
from dotenv import load_dotenv

load_dotenv()

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")

def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def _cache_path(blog_url: str) -> str:
    key = hashlib.md5(blog_url.encode()).hexdigest()[:10]
    return os.path.join(CACHE_DIR, f"{key}.json")


def scrape_blog(blog_url: str, max_articles: int, use_cache: bool = True) -> list[dict]:
    """Crawl blog index and scrape each article. Returns list of article dicts.
    Caches results locally so re-runs during dev don't re-burn Firecrawl credits."""
    cache_file = _cache_path(blog_url)
    if use_cache and os.path.exists(cache_file):
        with open(cache_file) as f:
            articles = json.load(f)
        print(f"[corpus] Loaded {len(articles)} articles from cache ({cache_file})")
        print("[corpus] Delete this file (or pass use_cache=False) to force a fresh Firecrawl crawl.")
        return articles

    app = FirecrawlApp(api_key=os.environ["FIRECRAWL_API_KEY"])

    print(f"[corpus] Crawling blog index: {blog_url}")
    result = app.crawl(
        blog_url,
        limit=max_articles,
        formats=["markdown"],
        only_main_content=True,
        poll_interval=5,
    )

    articles = []
    pages = result.data if hasattr(result, "data") else result.get("data", [])
    for page in pages:
        if hasattr(page, "metadata"):
            meta = page.metadata
            url = getattr(meta, "url", None) or getattr(meta, "source_url", "") or ""
            title = getattr(meta, "title", url) or url
        else:
            meta = page.get("metadata", {})
            url = meta.get("url") or meta.get("sourceURL", "")
            title = meta.get("title", url)
        markdown = getattr(page, "markdown", None) or page.get("markdown", "") if not hasattr(page, "metadata") else getattr(page, "markdown", "")

        if not markdown or len(markdown) < 200:
            continue

        articles.append({
            "url": url,
            "title": title,
            "content": markdown,
        })
        print(f"  ✓ {title[:70]}")

    print(f"[corpus] {len(articles)} articles scraped")

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(articles, f)
    print(f"[corpus] Cached to {cache_file}")

    return articles


def chunk_article(article: dict, chunk_size: int = 500) -> list[dict]:
    """Split article content into overlapping word chunks."""
    words = article["content"].split()
    chunks = []
    step = chunk_size - 50  # 50-word overlap
    for i in range(0, len(words), step):
        chunk_words = words[i : i + chunk_size]
        if len(chunk_words) < 50:
            break
        chunks.append({
            "url": article["url"],
            "title": article["title"],
            "chunk_index": len(chunks),
            "text": " ".join(chunk_words),
        })
    return chunks


def build_chunks(articles: list[dict]) -> list[dict]:
    all_chunks = []
    for article in articles:
        all_chunks.extend(chunk_article(article))
    print(f"[corpus] {len(all_chunks)} chunks from {len(articles)} articles")
    return all_chunks


if __name__ == "__main__":
    cfg = load_config()
    articles = scrape_blog(cfg["blog"]["url"], cfg["blog"]["max_articles"])
    chunks = build_chunks(articles)
    print(f"\nSample chunk:\n{chunks[0]['text'][:300]}" if chunks else "No chunks generated")
