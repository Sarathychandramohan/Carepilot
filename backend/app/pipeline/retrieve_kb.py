"""
D:\\CarePilotAI\\backend\\app\\pipeline\\retrieve_kb.py

B3.2 — KB Hybrid Retrieval (Min-Max Normalized Convex Combination)
Pillar B, Two-Stage Retrieval Pipeline.

Retrieves medical knowledge base chunks by fusing:
  - Dense retrieval via ChromaDB (carepilot_kb_v5, bge-small-en-v1.5, cosine similarity)
  - Sparse retrieval via BM25 (bm25_index_v5.pkl)

Fusion: Per-query min-max normalization followed by convex combination:
  score = alpha * dense_norm + (1 - alpha) * bm25_norm
  (Per Master Spec Section 6.2 / Decision D-005, alpha tuned on dev)

Citation Boundary Contract:
  Every returned KBChunk has chunk_id in the strict spec format:
  kb:{doc_id}:chunk{n:04d} (regex: ^kb:[A-Za-z0-9\\-_]+:chunk\\d{4}$)
"""
from __future__ import annotations

import pickle
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

# Project root: 3 levels up from backend/app/pipeline/
PROJECT_ROOT = Path(__file__).resolve().parents[3]

SPEC_CITATION_REGEX = re.compile(r"^kb:[A-Za-z0-9\-_]+:chunk\d{4}$")
DEFAULT_ALPHA: float = 0.50

# Lazy-loaded singletons
_CHROMA_COLLECTION = None
_BM25_INDEX = None
_BM25_CORPUS_IDS: list[str] = []
_EMBEDDER = None


# ---------------------------------------------------------------------------
# Citation ID Normalization (Retrieval Boundary Translation)
# ---------------------------------------------------------------------------

def to_spec_chunk_id(raw_id: str, doc_id: str | None = None) -> str:
    """
    Translates storage chunk IDs into the authoritative spec format:
      kb:{doc_id}:chunk{n:04d}
    Does NOT modify the underlying Chroma index or storage files.
    """
    # Case 1: Already in spec format "kb:DOC_ID:chunk0000"
    m_spec = re.match(r"^kb:([A-Za-z0-9\-_]+):chunk(\d+)$", raw_id)
    if m_spec:
        return f"kb:{m_spec.group(1)}:chunk{int(m_spec.group(2)):04d}"

    # Case 2: Underscore or hyphen delimited "DOC_ID_chunk_003" or "DOC_ID:chunk3"
    m_loose = re.match(r"^([A-Za-z0-9\-_]+)[_:]chunk[_:]?(\d+)$", raw_id)
    if m_loose:
        return f"kb:{m_loose.group(1)}:chunk{int(m_loose.group(2)):04d}"

    # Case 3: Just numeric index with doc_id provided
    m_num = re.match(r"^(\d+)$", raw_id)
    if m_num and doc_id:
        return f"kb:{doc_id}:chunk{int(m_num.group(1)):04d}"

    # Fallback: if already prefix kb: but different structure
    if raw_id.startswith("kb:"):
        return raw_id
    if doc_id:
        return f"kb:{doc_id}:chunk0000"
    return f"kb:{raw_id}:chunk0000"


# ---------------------------------------------------------------------------
# KBChunk — contract between B3.2 and B4/B5/UI
# ---------------------------------------------------------------------------

@dataclass
class KBChunk:
    chunk_id: str          # Guaranteed format: kb:{doc_id}:chunk{n:04d}
    doc_id: str            # e.g. "KB-MP0042"
    source_name: str       # "MedlinePlus" | "NIDDK" | "FDA"
    source_url: str        # canonical citation URL
    title: str             # document title
    text: str              # chunk body (max ~400 tokens)
    score_hybrid: float = 0.0    # convex combination score [0.0, 1.0]
    score_dense: float = 0.0
    score_bm25: float = 0.0
    score_rrf: float = 0.0  # backward compatibility alias to score_hybrid

    def __post_init__(self):
        # Keep score_rrf and score_hybrid synchronized
        if not self.score_hybrid and self.score_rrf:
            self.score_hybrid = self.score_rrf
        elif not self.score_rrf and self.score_hybrid:
            self.score_rrf = self.score_hybrid

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
        try:
            _EMBEDDER = SentenceTransformer(settings.embedding_model, local_files_only=True)
        except Exception:
            _EMBEDDER = SentenceTransformer(settings.embedding_model)
    return _EMBEDDER


def _get_chroma_collection():
    global _CHROMA_COLLECTION
    if _CHROMA_COLLECTION is None:
        import chromadb
        from backend.app.core.settings import settings
        persist_dir = getattr(settings, "chroma_persist_dir", None)
        if not persist_dir:
            chroma_path = PROJECT_ROOT / "rag_knowledge" / "chroma_db"
        else:
            chroma_path = Path(persist_dir)
            if not chroma_path.is_absolute():
                chroma_path = PROJECT_ROOT / chroma_path
        client = chromadb.PersistentClient(path=str(chroma_path))
        _CHROMA_COLLECTION = client.get_collection(settings.chroma_collection)
    return _CHROMA_COLLECTION


def _get_bm25() -> tuple[Any, list[str]]:
    """Returns (BM25Okapi index, list of chunk_ids in corpus order)."""
    global _BM25_INDEX, _BM25_CORPUS_IDS
    if _BM25_INDEX is None:
        from backend.app.core.settings import settings
        bm25_path = Path(settings.bm25_index_path)
        if not bm25_path.is_absolute():
            bm25_path = PROJECT_ROOT / bm25_path
        with open(bm25_path, "rb") as f:
            data = pickle.load(f)
        # Saved format has key "bm25" (or "index" in legacy)
        _BM25_INDEX = data.get("bm25") or data.get("index")
        _BM25_CORPUS_IDS = data["chunk_ids"]
    return _BM25_INDEX, _BM25_CORPUS_IDS


# ---------------------------------------------------------------------------
# Min-Max Normalized Convex Combination Fusion
# ---------------------------------------------------------------------------

def _min_max_convex_fuse(
    dense_scores: dict[str, float],
    sparse_scores: dict[str, float],
    alpha: float = 0.5,
) -> list[tuple[str, float, float, float]]:
    """
    Min-max normalizes dense and sparse scores per query, then computes
    the convex combination:
      score = alpha * dense_norm + (1 - alpha) * bm25_norm

    Candidates appearing only in one modality receive 0.0 for the other.

    Returns:
      List of (chunk_id, hybrid_score, dense_norm, sparse_norm) sorted descending.
    """
    all_chunk_ids = set(dense_scores.keys()) | set(sparse_scores.keys())
    if not all_chunk_ids:
        return []

    # Normalize dense scores
    dense_norm: dict[str, float] = {}
    if dense_scores:
        d_vals = list(dense_scores.values())
        min_d, max_d = min(d_vals), max(d_vals)
        d_span = max_d - min_d
        for cid, score in dense_scores.items():
            dense_norm[cid] = (score - min_d) / d_span if d_span > 1e-9 else 1.0

    # Normalize sparse BM25 scores
    sparse_norm: dict[str, float] = {}
    if sparse_scores:
        s_vals = list(sparse_scores.values())
        min_s, max_s = min(s_vals), max(s_vals)
        s_span = max_s - min_s
        for cid, score in sparse_scores.items():
            sparse_norm[cid] = (score - min_s) / s_span if s_span > 1e-9 else 1.0

    # Convex combination
    fused: list[tuple[str, float, float, float]] = []
    for cid in all_chunk_ids:
        dn = dense_norm.get(cid, 0.0)
        sn = sparse_norm.get(cid, 0.0)
        hybrid = alpha * dn + (1.0 - alpha) * sn
        fused.append((cid, hybrid, dn, sn))

    fused.sort(key=lambda x: x[1], reverse=True)
    return fused


# ---------------------------------------------------------------------------
# Main retrieval entry point
# ---------------------------------------------------------------------------

def retrieve_kb(
    query_text: str,
    normalized_concepts: list[dict],
    top_n: int = 8,
    dense_top_k: int = 20,
    bm25_top_k: int = 20,
    alpha: float = 0.5,
    rrf_k: int = 60,  # retained for backwards parameter compatibility
) -> list[KBChunk]:
    """
    B3.2 KB hybrid retrieval via min-max convex combination.

    Args:
        query_text:          Raw patient query text
        normalized_concepts: Output of normalize_query_concepts()
        top_n:               Final chunks to return (default 8)
        dense_top_k:         ChromaDB candidate pool size (default 20, per spec)
        bm25_top_k:          BM25 candidate pool size (default 20, per spec)
        alpha:               Dense weight in convex combination (tuned on dev)
        rrf_k:               Unused legacy parameter

    Returns:
        List of KBChunk sorted by descending hybrid score, length <= top_n.
        Every chunk_id strictly conforms to 'kb:{doc_id}:chunk{n:04d}'.
    """
    from backend.app.core.settings import settings
    top_n = top_n or getattr(settings, "kb_final_top_n", 8)
    dense_top_k = dense_top_k or getattr(settings, "kb_dense_top_k", 20)
    bm25_top_k = bm25_top_k or getattr(settings, "kb_bm25_top_k", 20)

    # ── Augment query with canonical concept labels for better recall ────────
    if isinstance(normalized_concepts, dict):
        normalized_concepts = normalized_concepts.get("resolved_concepts", [])
    concept_labels = [
        c.get("canonical_label", "")
        for c in (normalized_concepts or [])
        if isinstance(c, dict) and c.get("canonical_label")
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
        include=["documents", "metadatas", "distances"],
    )
    dense_ids: list[str] = dense_results["ids"][0]
    dense_meta: list[dict] = dense_results["metadatas"][0]
    dense_docs: list[str] = dense_results["documents"][0]
    dense_dists: list[float] = dense_results["distances"][0]

    # Convert cosine distance to cosine similarity: sim = 1.0 - dist
    dense_scores: dict[str, float] = {
        cid: 1.0 - d for cid, d in zip(dense_ids, dense_dists)
    }

    # Metadata & document lookup
    meta_by_id: dict[str, dict] = {}
    doc_by_id: dict[str, str] = {}
    for cid, meta, doc in zip(dense_ids, dense_meta, dense_docs):
        meta_by_id[cid] = meta
        doc_by_id[cid] = doc

    # ── Sparse retrieval (BM25) ───────────────────────────────────────────────
    bm25, corpus_ids = _get_bm25()
    query_tokens = augmented_query.lower().split()
    bm25_scores_all = bm25.get_scores(query_tokens)

    # Top-k BM25 indices
    top_bm25_indices = sorted(
        range(len(bm25_scores_all)), key=lambda i: bm25_scores_all[i], reverse=True
    )[:bm25_top_k]

    sparse_scores: dict[str, float] = {
        corpus_ids[i]: float(bm25_scores_all[i]) for i in top_bm25_indices
    }

    # ── Min-Max Convex Fusion ─────────────────────────────────────────────────
    fused = _min_max_convex_fuse(dense_scores, sparse_scores, alpha=alpha)

    # ── Build final KBChunk list with spec-normalized citation IDs ────────────
    chunks: list[KBChunk] = []
    for raw_chunk_id, hybrid_score, dn, sn in fused[:top_n]:
        if raw_chunk_id in meta_by_id:
            meta = meta_by_id[raw_chunk_id]
            text = doc_by_id.get(raw_chunk_id, "")
        else:
            # BM25-only candidate — fetch metadata from ChromaDB
            try:
                fetched = collection.get(ids=[raw_chunk_id], include=["documents", "metadatas"])
                if not fetched["ids"]:
                    continue
                meta = fetched["metadatas"][0]
                text = fetched["documents"][0]
                meta_by_id[raw_chunk_id] = meta
                doc_by_id[raw_chunk_id] = text
            except Exception:
                continue

        doc_id = meta.get("doc_id", "")
        if not doc_id:
            # Derive doc_id from raw_chunk_id (e.g. kb:KB-B01:chunk0000 -> KB-B01)
            m = re.match(r"^(?:kb:)?([A-Za-z0-9\-_]+)[_:]chunk", raw_chunk_id)
            doc_id = m.group(1) if m else raw_chunk_id

        # Authoritative spec format: kb:{doc_id}:chunk{n:04d}
        normalized_chunk_id = to_spec_chunk_id(raw_chunk_id, doc_id=doc_id)

        chunks.append(KBChunk(
            chunk_id=normalized_chunk_id,
            doc_id=doc_id,
            source_name=meta.get("source_name", "Unknown"),
            source_url=meta.get("source_url", ""),
            title=meta.get("title", ""),
            text=text,
            score_hybrid=round(hybrid_score, 6),
            score_dense=round(dn, 6),
            score_bm25=round(sn, 6),
            score_rrf=round(hybrid_score, 6),
        ))

    return chunks
