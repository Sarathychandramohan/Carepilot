"""
D:\\CarePilotAI\\backend\\app\\pipeline\\retrieve_kb.py

B3.2 — KB Hybrid Retrieval (Reciprocal Rank Fusion)
Pillar B, Two-Stage Retrieval Pipeline.

Retrieves medical knowledge base chunks by fusing:
  - Dense retrieval via ChromaDB (carepilot_kb_v5, bge-small-en-v1.5)
  - Sparse retrieval via BM25 (bm25_index_v5.pkl)

Fusion: Reciprocal Rank Fusion (RRF, k=60)
Final output: top N=8 chunks sorted by descending RRF score.
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Lazy-loaded singletons
_CHROMA_COLLECTION = None
_BM25_INDEX = None
_BM25_CORPUS_IDS: list[str] = []
_EMBEDDER = None


# ---------------------------------------------------------------------------
# KBChunk — the contract between B3.2 and B4/B5
# ---------------------------------------------------------------------------

@dataclass
class KBChunk:
    chunk_id: str       # e.g. "KB-MP0042_chunk_003"
    doc_id: str         # e.g. "KB-MP0042"
    source_name: str    # "MedlinePlus" | "NIDDK" | "FDA"
    source_url: str     # canonical citation URL
    title: str          # document title
    text: str           # chunk body (max ~400 tokens)
    score_rrf: float    # final RRF score (higher = more relevant)

    def to_dict(self) -> dict:
        return asdict(self)

    def prompt_text(self) -> str:
        return f"[KB: {self.source_name} — {self.title}]\n{self.text}"


# ---------------------------------------------------------------------------
# Loader helpers (lazy, cached)
# ---------------------------------------------------------------------------

def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer
        from backend.app.core.settings import settings
        _EMBEDDER = SentenceTransformer(settings.embedding_model)
    return _EMBEDDER


def _get_chroma_collection():
    global _CHROMA_COLLECTION
    if _CHROMA_COLLECTION is None:
        import chromadb
        from backend.app.core.settings import settings
        client = chromadb.PersistentClient(
            path=str(PROJECT_ROOT / "rag_knowledge" / "chroma_db")
        )
        _CHROMA_COLLECTION = client.get_collection(settings.chroma_collection)
    return _CHROMA_COLLECTION


def _get_bm25() -> tuple[Any, list[str]]:
    """Returns (BM25Okapi index, list of chunk_ids in corpus order)."""
    global _BM25_INDEX, _BM25_CORPUS_IDS
    if _BM25_INDEX is None:
        from backend.app.core.settings import settings
        bm25_path = Path(settings.bm25_index_path)
        with open(bm25_path, "rb") as f:
            data = pickle.load(f)
        # Saved format: {"index": BM25Okapi, "chunk_ids": [...], "corpus": [...]}
        _BM25_INDEX = data["index"]
        _BM25_CORPUS_IDS = data["chunk_ids"]
    return _BM25_INDEX, _BM25_CORPUS_IDS


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------

def _rrf_fuse(
    dense_ids: list[str],
    sparse_ids: list[str],
    k: int = 60,
) -> list[tuple[str, float]]:
    """
    Reciprocal Rank Fusion over two ranked lists.
    score(d) = Σ 1 / (k + rank_i(d))

    Returns list of (chunk_id, rrf_score) sorted descending.
    """
    scores: dict[str, float] = {}
    for rank, cid in enumerate(dense_ids, start=1):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    for rank, cid in enumerate(sparse_ids, start=1):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ---------------------------------------------------------------------------
# Main retrieval entry point
# ---------------------------------------------------------------------------

def retrieve_kb(
    query_text: str,
    normalized_concepts: list[dict],
    top_n: int = 8,
    dense_top_k: int = 15,
    bm25_top_k: int = 15,
    rrf_k: int = 60,
) -> list[KBChunk]:
    """
    B3.2 KB hybrid retrieval.

    Args:
        query_text:          Raw patient query text
        normalized_concepts: Output of normalize_query_concepts()
        top_n:               Final chunks to return after RRF (default 8)
        dense_top_k:         ChromaDB candidate pool size (default 15)
        bm25_top_k:          BM25 candidate pool size (default 15)
        rrf_k:               RRF constant (default 60)

    Returns:
        List of KBChunk sorted by descending RRF score, length <= top_n.
    """
    from backend.app.core.settings import settings
    top_n = top_n or settings.kb_final_top_n
    dense_top_k = dense_top_k or settings.kb_dense_top_k
    bm25_top_k = bm25_top_k or settings.kb_bm25_top_k
    rrf_k = rrf_k or settings.kb_rrf_k

    # ── Augment query with canonical concept labels for better recall ────────
    concept_labels = [
        c.get("canonical_label", "")
        for c in normalized_concepts
        if c.get("canonical_label")
    ]
    augmented_query = query_text
    if concept_labels:
        augmented_query = query_text + " " + " ".join(concept_labels[:5])

    # ── Dense retrieval (ChromaDB) ────────────────────────────────────────────
    embedder = _get_embedder()
    query_emb = embedder.encode([augmented_query], normalize_embeddings=True).tolist()[0]

    collection = _get_chroma_collection()
    dense_results = collection.query(
        query_embeddings=[query_emb],
        n_results=dense_top_k,
        include=["documents", "metadatas"],
    )
    dense_ids: list[str] = dense_results["ids"][0]
    dense_meta: list[dict] = dense_results["metadatas"][0]
    dense_docs: list[str] = dense_results["documents"][0]

    # Build metadata lookup from dense results
    meta_by_id: dict[str, dict] = {}
    doc_by_id: dict[str, str] = {}
    for cid, meta, doc in zip(dense_ids, dense_meta, dense_docs):
        meta_by_id[cid] = meta
        doc_by_id[cid] = doc

    # ── Sparse retrieval (BM25) ───────────────────────────────────────────────
    bm25, corpus_ids = _get_bm25()
    query_tokens = augmented_query.lower().split()
    bm25_scores = bm25.get_scores(query_tokens)

    # Take top-k by score
    top_bm25_indices = sorted(
        range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True
    )[:bm25_top_k]
    sparse_ids: list[str] = [corpus_ids[i] for i in top_bm25_indices]

    # ── RRF fusion ────────────────────────────────────────────────────────────
    fused = _rrf_fuse(dense_ids, sparse_ids, k=rrf_k)

    # ── Build final KBChunk list from top_n fused results ─────────────────────
    chunks: list[KBChunk] = []
    for chunk_id, rrf_score in fused[:top_n]:
        if chunk_id in meta_by_id:
            meta = meta_by_id[chunk_id]
            text = doc_by_id.get(chunk_id, "")
        else:
            # BM25-only hit — fetch document from ChromaDB by ID
            try:
                fetched = collection.get(ids=[chunk_id], include=["documents", "metadatas"])
                if not fetched["ids"]:
                    continue
                meta = fetched["metadatas"][0]
                text = fetched["documents"][0]
                meta_by_id[chunk_id] = meta
                doc_by_id[chunk_id] = text
            except Exception:
                continue

        chunks.append(KBChunk(
            chunk_id=chunk_id,
            doc_id=meta.get("doc_id", chunk_id.rsplit("_chunk_", 1)[0]),
            source_name=meta.get("source_name", "Unknown"),
            source_url=meta.get("source_url", ""),
            title=meta.get("title", ""),
            text=text,
            score_rrf=round(rrf_score, 6),
        ))

    return chunks
