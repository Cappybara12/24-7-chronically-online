"""Generate article outlines using Groq LLM with RAG context."""

import os
from groq import Groq
from dotenv import load_dotenv
import yaml

load_dotenv()


def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def build_prompt(rag_result: dict) -> str:
    group = rag_result["group"]
    related = rag_result["related_articles"]
    classification = rag_result["classification"]
    sources = group["sources"]

    sources_block = "\n".join(
        f"  - [{s['platform']}] \"{s['title']}\" ({s['url']}) — {s['description'][:120]}"
        for s in sources[:8]  # cap prompt size
    )

    related_block = ""
    if related:
        lines = "\n".join(
            f"  - \"{a['title']}\" ({a['url']}) — similarity {a['similarity']}"
            for a in related
        )
        related_block = f"\nExisting related articles in our corpus:\n{lines}\n"

    interlink_instruction = ""
    if classification == "interlink":
        interlink_instruction = (
            "\nSince related articles exist, include a section in the outline called "
            "\"Internal Links\" that lists which existing articles to link to and at which H2 section."
        )
    else:
        interlink_instruction = (
            "\nNo closely related articles exist yet. This is a new pillar topic — "
            "note this at the top of the outline."
        )

    return f"""You are an SEO content strategist. Generate ONE structured article outline for the trending keyword below, informed by ALL the real posts/pages found for it (not just one).

Trending topic keyword: {group['keyword']}

Real signals found for this keyword ({len(sources)} sources across platforms):
{sources_block}
{related_block}{interlink_instruction}

Output a structured outline with:
1. Recommended article title (SEO-optimised, under 60 chars)
2. Meta description (under 155 chars)
3. Primary keyword + 4-5 secondary/LSI keywords
4. H2 sections (5-7 sections with one-line description each)
5. FAQ section (3 questions people are actually searching)
6. Internal links (if applicable — which existing article, which section to link from)
7. Content type recommendation (how-to / comparison / listicle / thought leadership)
8. Estimated search intent (informational / navigational / transactional)
9. Distribution suggestions — from the real sources listed above, pick which specific ones (by platform + title) would be worth replying to or sharing this article in once it's published, and briefly say why. Only suggest ones where a genuine, non-spammy reply/share would fit naturally.

Synthesize across all the sources above into one coherent outline — don't just summarize the first source. Be concise. This is a planning outline, not a full draft."""


def generate_outline(rag_result: dict) -> str:
    cfg = load_config()
    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    prompt = build_prompt(rag_result)
    response = client.chat.completions.create(
        model=cfg["llm"]["model"],
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=1200,
    )
    return response.choices[0].message.content


def generate_all_outlines(rag_results: list[dict], store=None) -> list[dict]:
    """Generate an outline for each RAG result. If `store` is given, marks the
    keyword as seen ONLY after a successful generation -- so failures (e.g. rate
    limits) get retried on the next run instead of being silently skipped forever."""
    outlines = []
    for i, result in enumerate(rag_results):
        keyword = result["group"]["keyword"]
        n_sources = len(result["group"]["sources"])
        print(f"[outline] Generating {i+1}/{len(rag_results)}: {keyword[:50]} ({n_sources} sources)")
        try:
            outline_text = generate_outline(result)
            outlines.append({
                "rag_result": result,
                "outline": outline_text,
            })
            if store is not None:
                store.add_topic(keyword)
        except Exception as e:
            print(f"  [outline] Error: {e} -- will retry next run")
    print(f"[outline] {len(outlines)} outlines generated")
    return outlines
