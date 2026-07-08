#!/usr/bin/env python3
"""
Content Engine — end-to-end pipeline:
  1. Build/update article corpus in ChromaDB  (--build-corpus)
  2. Scan for trending topics via Firecrawl   (--scan)
  3. Group hits by keyword (one outline per keyword, not per post)
  4. RAG: classify each keyword group vs existing articles
  5. Generate one outline per group via Groq
  6. Save to review/ folder as markdown

Usage:
  python main.py --build-corpus   # run once to index your blog
  python main.py --scan           # run once to get new outlines
  python main.py --all            # build corpus then scan
  python main.py --daemon         # run --scan on a loop, every `scanner.run_every_days`
"""

import argparse
import sys
import time
from dotenv import load_dotenv

load_dotenv()


def build_corpus():
    print("\n=== STEP 1: Building article corpus ===")
    from corpus.scraper import load_config, scrape_blog, build_chunks
    from memory.store import MemoryStore

    cfg = load_config()
    articles = scrape_blog(cfg["blog"]["url"], cfg["blog"]["max_articles"])
    if not articles:
        print("[main] No articles scraped. Check your blog URL and Firecrawl key.")
        return

    chunks = build_chunks(articles)
    store = MemoryStore()
    store.add_articles(chunks)
    print(f"[main] Corpus ready: {store.articles.count()} chunks in ChromaDB\n")


def scan_and_generate():
    print("\n=== STEP 2: Scanning for trends ===")
    from scanner.firecrawl_scanner import scan_trends, dedupe_trends, group_by_keyword
    from rag.retriever import run_rag
    from outline.generator import generate_all_outlines
    from review.queue import save_all_outlines
    from memory.store import MemoryStore

    store = MemoryStore()

    if store.articles.count() == 0:
        print("[main] WARNING: Corpus is empty. Run --build-corpus first for interlink suggestions.")
        print("[main] Continuing in 'new pillar only' mode...\n")

    raw_trends = scan_trends()
    trends = dedupe_trends(raw_trends)
    print(f"[main] {len(trends)} unique trend signals\n")

    if not trends:
        print("[main] No trends found. Try broadening seed keywords or recency window.")
        return

    groups = group_by_keyword(trends)
    print(f"[main] Collapsed into {len(groups)} keyword groups (one outline each, not one per post)\n")

    print("\n=== STEP 3: RAG classification ===")
    rag_results = run_rag(groups, store)

    if not rag_results:
        print("[main] All keywords already seen in topic history. Nothing new to generate.")
        return

    import yaml
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    cap = cfg["scanner"].get("max_outlines_per_run", len(rag_results))
    if len(rag_results) > cap:
        print(f"[main] Capping outline generation to {cap} (of {len(rag_results)} classified) to conserve LLM credits")
        rag_results = rag_results[:cap]

    print("\n=== STEP 4: Generating outlines ===")
    outlines = generate_all_outlines(rag_results, store=store)

    print("\n=== STEP 5: Saving to review queue ===")
    paths = save_all_outlines(outlines)

    print(f"\n✓ Done. {len(paths)} outline(s) saved to review/")
    print("  Open the markdown files, review, edit, then publish.\n")
    for p in paths:
        print(f"  → {p}")


def run_daemon():
    """Loop --scan forever, sleeping `scanner.run_every_days` between runs.
    Ctrl+C to stop. Errors in one cycle don't kill the daemon -- it logs and retries next cycle."""
    import yaml
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    interval_seconds = cfg["scanner"]["run_every_days"] * 24 * 3600

    print(f"[daemon] Starting. Will scan every {cfg['scanner']['run_every_days']} day(s).")
    print("[daemon] Press Ctrl+C to stop.\n")

    while True:
        try:
            scan_and_generate()
        except Exception as e:
            print(f"[daemon] Cycle failed: {e}")

        next_run = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + interval_seconds))
        print(f"\n[daemon] Sleeping until next run at {next_run}...\n")
        time.sleep(interval_seconds)


def main():
    parser = argparse.ArgumentParser(description="Content Engine")
    parser.add_argument("--build-corpus", action="store_true", help="Scrape blog and index into ChromaDB")
    parser.add_argument("--scan", action="store_true", help="Scan trends and generate outlines (once)")
    parser.add_argument("--all", action="store_true", help="Build corpus then scan")
    parser.add_argument("--daemon", action="store_true", help="Run --scan on a repeating schedule (see config.yaml: scanner.run_every_days)")
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        sys.exit(0)

    if args.build_corpus or args.all:
        build_corpus()

    if args.scan or args.all:
        scan_and_generate()

    if args.daemon:
        run_daemon()


if __name__ == "__main__":
    main()
