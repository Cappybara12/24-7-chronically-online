#!/usr/bin/env python3
"""Local dashboard for the content engine — corpus, trends, RAG scores, review queue."""

import os
import sys
import json
import markdown as md_lib
from flask import Flask, render_template, redirect, url_for, request, flash

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from review.parser import list_all_outlines, parse_outline, update_status
from memory.store import MemoryStore

app = Flask(__name__)
app.secret_key = "dev-only-not-secret"

_store = None


def get_store():
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store


def load_config():
    import yaml
    with open("config.yaml") as f:
        return yaml.safe_load(f)


@app.route("/")
def dashboard():
    store = get_store()
    outlines = list_all_outlines()

    pending = [o for o in outlines if o["frontmatter"].get("status") == "pending_review"]
    approved = [o for o in outlines if o["frontmatter"].get("status") == "approved"]
    rejected = [o for o in outlines if o["frontmatter"].get("status") == "rejected"]
    interlinks = [o for o in outlines if o["frontmatter"].get("classification") == "interlink"]
    new_pillars = [o for o in outlines if o["frontmatter"].get("classification") == "new_pillar"]

    cfg = load_config()
    scan_cache = os.path.join("scanner", "cache", "last_scan.json")
    last_scan_count = 0
    if os.path.exists(scan_cache):
        with open(scan_cache) as f:
            last_scan_count = len(json.load(f))

    return render_template(
        "dashboard.html",
        niche=cfg.get("niche", "unknown"),
        blog_url=cfg["blog"]["url"],
        article_chunks=store.articles.count(),
        topics_scanned=store.topics.count(),
        last_scan_count=last_scan_count,
        total_outlines=len(outlines),
        pending_count=len(pending),
        approved_count=len(approved),
        rejected_count=len(rejected),
        interlink_count=len(interlinks),
        new_pillar_count=len(new_pillars),
    )


@app.route("/corpus")
def corpus():
    store = get_store()
    raw = store.articles.get(include=["metadatas"])
    seen = {}
    for meta in raw["metadatas"]:
        url = meta["url"]
        if url not in seen:
            seen[url] = {"title": meta["title"], "url": url, "chunks": 0}
        seen[url]["chunks"] += 1

    articles = sorted(seen.values(), key=lambda a: -a["chunks"])
    return render_template("corpus.html", articles=articles, total=len(articles))


@app.route("/trends")
def trends():
    outlines = list_all_outlines()
    rows = []
    for o in outlines:
        fm = o["frontmatter"]
        rows.append({
            "filename": o["filename"],
            "keyword": fm.get("keyword", ""),
            "platforms": fm.get("platforms", ""),
            "source_count": fm.get("source_count", 1),
            "classification": fm.get("classification", ""),
            "status": fm.get("status", ""),
        })

    filter_class = request.args.get("classification", "all")
    if filter_class != "all":
        rows = [r for r in rows if r["classification"] == filter_class]

    return render_template("trends.html", rows=rows, filter_class=filter_class)


@app.route("/outlines")
def outlines_list():
    outlines = list_all_outlines()
    status_filter = request.args.get("status", "all")
    if status_filter != "all":
        outlines = [o for o in outlines if o["frontmatter"].get("status") == status_filter]
    return render_template("outlines.html", outlines=outlines, status_filter=status_filter)


@app.route("/outlines/<filename>")
def outline_detail(filename):
    outline = parse_outline(filename)
    body_html = md_lib.markdown(outline["body"])
    return render_template("outline_detail.html", outline=outline, body_html=body_html)


@app.route("/outlines/<filename>/status", methods=["POST"])
def set_status(filename):
    new_status = request.form.get("status")
    update_status(filename, new_status)
    flash(f"Marked as {new_status}")
    return redirect(url_for("outline_detail", filename=filename))


@app.route("/run/build-corpus", methods=["POST"])
def run_build_corpus():
    from corpus.scraper import scrape_blog, build_chunks
    cfg = load_config()
    force = request.form.get("force") == "true"
    articles = scrape_blog(cfg["blog"]["url"], cfg["blog"]["max_articles"], use_cache=not force)
    chunks = build_chunks(articles)
    get_store().add_articles(chunks)
    flash(f"Corpus updated: {len(articles)} articles, {get_store().articles.count()} chunks total")
    return redirect(url_for("dashboard"))


@app.route("/run/scan", methods=["POST"])
def run_scan():
    from scanner.firecrawl_scanner import scan_trends, dedupe_trends, group_by_keyword
    from rag.retriever import run_rag
    from outline.generator import generate_all_outlines
    from review.queue import save_all_outlines

    force = request.form.get("force") == "true"
    store = get_store()
    raw_trends = scan_trends(use_cache=not force)
    trend_list = dedupe_trends(raw_trends)
    groups = group_by_keyword(trend_list)
    rag_results = run_rag(groups, store)

    if not rag_results:
        flash("No new topics to generate (all seen before, or no trends found)")
        return redirect(url_for("dashboard"))

    cfg = load_config()
    cap = cfg["scanner"].get("max_outlines_per_run", len(rag_results))
    if len(rag_results) > cap:
        rag_results = rag_results[:cap]

    outlines = generate_all_outlines(rag_results, store=store)
    paths = save_all_outlines(outlines)
    flash(f"Generated {len(paths)} new outlines")
    return redirect(url_for("outlines_list"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, port=port)
