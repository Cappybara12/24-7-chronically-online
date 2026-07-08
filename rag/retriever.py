"""RAG retrieval: match keyword groups against article corpus, classify novelty."""

import yaml
from memory.store import MemoryStore


def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def classify_group(group: dict, store: MemoryStore) -> dict:
    """
    For one keyword group (all real posts/pages found for that keyword),
    retrieve nearest corpus articles and classify:
      - 'interlink'  : similar article exists -> suggest linking
      - 'new_pillar' : nothing close -> suggest fresh article
    """
    cfg = load_config()
    threshold = cfg["rag"]["novelty_threshold"]
    top_k = cfg["rag"]["top_k"]

    # build one aggregate query from the keyword + up to 3 representative source titles
    sample_titles = " ".join(s["title"] for s in group["sources"][:3])
    query = f"{group['keyword']} {sample_titles}"
    hits = store.search_articles(query, top_k=top_k)

    classification = "new_pillar"
    related_articles = []

    if hits:
        top_score = hits[0]["score"]
        if top_score >= threshold:
            classification = "interlink"
        related_articles = [
            {"title": h["title"], "url": h["url"], "similarity": round(h["score"], 3)}
            for h in hits
        ]

    return {
        "group": group,
        "classification": classification,
        "top_similarity": round(hits[0]["score"], 3) if hits else 0.0,
        "related_articles": related_articles,
    }


def run_rag(groups: list[dict], store: MemoryStore) -> list[dict]:
    """Classify all keyword groups. Skips groups already seen in topic history.
    Note: does NOT mark topics as seen here -- that only happens once an outline
    is actually generated and saved (see outline/generator.py), so a failed/rate-limited
    generation gets retried on the next run instead of being silently skipped forever."""
    results = []
    skipped = 0

    for group in groups:
        topic_text = group["keyword"]
        if store.topic_already_seen(topic_text):
            skipped += 1
            continue

        result = classify_group(group, store)
        results.append(result)

    print(f"[rag] {len(results)} new keyword groups classified | {skipped} skipped (already seen)")

    new_pillars = [r for r in results if r["classification"] == "new_pillar"]
    interlinks  = [r for r in results if r["classification"] == "interlink"]
    print(f"[rag]   new pillars: {len(new_pillars)} | interlink candidates: {len(interlinks)}")

    return results


if __name__ == "__main__":
    from scanner.firecrawl_scanner import scan_trends, dedupe_trends, group_by_keyword
    store = MemoryStore()
    print(f"Articles in store: {store.articles.count()}")
    trends = dedupe_trends(scan_trends())
    groups = group_by_keyword(trends)
    results = run_rag(groups, store)
    for r in results[:3]:
        print(f"\n[{r['classification']}] {r['group']['keyword']} ({len(r['group']['sources'])} sources)")
        print(f"  similarity: {r['top_similarity']}")
        for a in r["related_articles"][:2]:
            print(f"  → {a['title'][:60]} ({a['similarity']})")
