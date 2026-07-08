"""ChromaDB vector store for article corpus and topic history."""

import os
import hashlib
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import yaml

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "chroma")


def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


class MemoryStore:
    def __init__(self):
        cfg = load_config()
        self.embedder = SentenceTransformer(cfg["embeddings"]["model"])
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)

        # Two collections: one for article chunks, one for scanned topics
        # explicit cosine space -- chroma defaults to l2, which makes "1 - distance" meaningless
        self.articles = self.client.get_or_create_collection(
            "articles_cosine", metadata={"hnsw:space": "cosine"}
        )
        self.topics = self.client.get_or_create_collection(
            "topics_cosine", metadata={"hnsw:space": "cosine"}
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return self.embedder.encode(texts, show_progress_bar=False).tolist()

    # ── Article corpus ────────────────────────────────────────────────────────

    def add_articles(self, chunks: list[dict]):
        """Embed and store article chunks. Skips duplicates."""
        if not chunks:
            return

        texts = [c["text"] for c in chunks]
        ids = [hashlib.md5(f"{c['url']}-{c['chunk_index']}".encode()).hexdigest() for c in chunks]
        metadatas = [{"url": c["url"], "title": c["title"], "chunk_index": c["chunk_index"]} for c in chunks]

        existing = set(self.articles.get(ids=ids)["ids"])
        new = [(i, t, m) for i, t, m in zip(ids, texts, metadatas) if i not in existing]
        if not new:
            print("[memory] All chunks already stored, skipping.")
            return

        new_ids, new_texts, new_metas = zip(*new)
        embeddings = self._embed(list(new_texts))
        self.articles.add(ids=list(new_ids), embeddings=embeddings,
                          documents=list(new_texts), metadatas=list(new_metas))
        print(f"[memory] Stored {len(new_ids)} new chunks ({self.articles.count()} total)")

    def search_articles(self, query: str, top_k: int = 3) -> list[dict]:
        """Return top-k article chunks most similar to query."""
        if self.articles.count() == 0:
            return []
        embedding = self._embed([query])[0]
        results = self.articles.query(query_embeddings=[embedding], n_results=min(top_k, self.articles.count()))
        hits = []
        for i, doc in enumerate(results["documents"][0]):
            hits.append({
                "text": doc,
                "url": results["metadatas"][0][i]["url"],
                "title": results["metadatas"][0][i]["title"],
                "score": 1 - results["distances"][0][i],  # cosine similarity
            })
        return hits

    # ── Topic history ─────────────────────────────────────────────────────────

    def topic_already_seen(self, topic: str, threshold: float = 0.92) -> bool:
        """True if a very similar topic was scanned before (dedup)."""
        if self.topics.count() == 0:
            return False
        embedding = self._embed([topic])[0]
        results = self.topics.query(query_embeddings=[embedding], n_results=1)
        similarity = 1 - results["distances"][0][0]
        return similarity >= threshold

    def add_topic(self, topic: str):
        tid = hashlib.md5(topic.encode()).hexdigest()
        embedding = self._embed([topic])[0]
        try:
            self.topics.add(ids=[tid], embeddings=[embedding], documents=[topic])
        except Exception:
            pass  # already exists


if __name__ == "__main__":
    store = MemoryStore()
    print(f"Articles in store: {store.articles.count()}")
    print(f"Topics in store:   {store.topics.count()}")
