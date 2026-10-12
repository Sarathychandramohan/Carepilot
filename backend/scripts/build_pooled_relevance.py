"""
D:\\CarePilotAI\\backend\\scripts\\build_pooled_relevance.py

Builds Pooled Relevance candidate lists for human annotation (S15 / D15).
For each query:
  - Top 10 from Dense Retriever (ChromaDB carepilot_kb_v2)
  - Top 10 from BM25 Sparse Retriever (bm25_index_v2.pkl)
  - Top 10 from Hybrid Retriever (alpha * dense + (1-alpha) * bm25)
  - 5 Random Control Chunks (to detect annotator bias)
Pools the unique union and exports a clean template for human relevance judgments.
"""
from __future__ import annotations

import csv
import json
import pickle
import random
import sys
from pathlib import Path
from typing import Any

import chromadb
import numpy as np
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHROMA_DIR = PROJECT_ROOT / "rag_knowledge" / "chroma_db"
BM25_PATH = PROJECT_ROOT / "rag_knowledge" / "bm25_index_v5.pkl"
COLLECTION_NAME = "carepilot_kb_v5"
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

CANDIDATES_QUERY_PATH = PROJECT_ROOT / "data" / "queries" / "gold_scripted_candidate.jsonl"
OUTPUT_JSONL = PROJECT_ROOT / "data" / "queries" / "pooled_relevance_template.jsonl"
OUTPUT_CSV = PROJECT_ROOT / "data" / "queries" / "pooled_relevance_template.csv"


def min_max_normalize(scores: np.ndarray) -> np.ndarray:
    s_min = np.min(scores)
    s_max = np.max(scores)
    if s_max == s_min:
        return np.zeros_like(scores)
    return (scores - s_min) / (s_max - s_min)


def build_pooled_relevance(query_limit: int = 150, alpha: float = 0.5):
    print("\n" + "=" * 60)
    print("CarePilot AI — Building Pooled Relevance Candidates for Annotation")
    print("=" * 60)

    # 1. Load ChromaDB
    print(f"Loading ChromaDB collection '{COLLECTION_NAME}'...")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection(COLLECTION_NAME)

    # 2. Load Embedding Model
    print(f"Loading embedding model '{EMBEDDING_MODEL_NAME}'...")
    embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)

    # 3. Load BM25
    print(f"Loading BM25 index from {BM25_PATH}...")
    with open(BM25_PATH, "rb") as f:
        bm25_data = pickle.load(f)

    bm25 = bm25_data["bm25"]
    chunk_ids = bm25_data["chunk_ids"]
    chunk_meta_map = {m["chunk_id"]: m for m in bm25_data["chunk_metadata"]}

    # All chunk IDs for random control sampling
    all_chunk_ids = list(chunk_ids)

    # 4. Load queries
    queries = []
    with open(CANDIDATES_QUERY_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                queries.append(json.loads(line))

    selected_queries = queries[:query_limit]
    print(f"Processing {len(selected_queries)} queries (Top-10 Dense, Top-10 BM25, Top-10 Hybrid, 5 Random controls)...")

    pooled_records = []
    csv_rows = []

    random.seed(42)

    for q in selected_queries:
        qid = q["query_id"]
        q_text = q["query_text"]

        # A. Dense Top-10
        q_emb = embedder.encode([q_text], normalize_embeddings=True).tolist()
        dense_res = collection.query(query_embeddings=q_emb, n_results=10)
        dense_top10 = dense_res["ids"][0]

        # B. BM25 Top-10
        tokens = [w.lower() for w in q_text.split() if w.strip()]
        bm25_raw_scores = np.array(bm25.get_scores(tokens))
        top_bm25_indices = np.argsort(bm25_raw_scores)[::-1][:10]
        bm25_top10 = [chunk_ids[i] for i in top_bm25_indices]

        # C. Hybrid Top-10 (over candidate union)
        cand_ids = list(set(dense_top10 + bm25_top10))
        chunk_id_to_idx = {cid: idx for idx, cid in enumerate(chunk_ids)}

        # Get dense cosine similarities for cand_ids
        dense_scores_map = {}
        for cid, dist in zip(dense_res["ids"][0], dense_res["distances"][0]):
            dense_scores_map[cid] = 1.0 - dist  # Cosine similarity

        cand_dense_scores = np.array([dense_scores_map.get(cid, 0.0) for cid in cand_ids])
        cand_bm25_scores = np.array([
            bm25_raw_scores[chunk_id_to_idx[cid]] if cid in chunk_id_to_idx else 0.0
            for cid in cand_ids
        ])

        norm_dense = min_max_normalize(cand_dense_scores)
        norm_bm25 = min_max_normalize(cand_bm25_scores)
        hybrid_scores = alpha * norm_dense + (1.0 - alpha) * norm_bm25

        top_hybrid_order = np.argsort(hybrid_scores)[::-1][:10]
        hybrid_top10 = [cand_ids[i] for i in top_hybrid_order]

        # D. 5 Random Control Chunks
        control_chunks = random.sample(all_chunk_ids, 5)

        # Union pool
        pooled_chunk_ids = list(dict.fromkeys(dense_top10 + bm25_top10 + hybrid_top10 + control_chunks))

        # Fetch chunk documents from Chroma
        chunk_docs_res = collection.get(ids=pooled_chunk_ids)
        doc_map = {cid: doc for cid, doc in zip(chunk_docs_res["ids"], chunk_docs_res["documents"])}
        meta_map = {cid: meta for cid, meta in zip(chunk_docs_res["ids"], chunk_docs_res["metadatas"])}

        for cid in pooled_chunk_ids:
            meta = meta_map.get(cid) or chunk_meta_map.get(cid, {})
            doc_id = meta.get("doc_id") or (cid.split(":")[1] if ":" in cid else "")
            sec_heading = meta.get("section_heading") or ""
            text_snippet = (doc_map.get(cid) or "")[:250] + "..."

            is_dense = cid in dense_top10
            is_bm25 = cid in bm25_top10
            is_hybrid = cid in hybrid_top10
            is_control = cid in control_chunks

            record = {
                "query_id": qid,
                "query_text": q_text,
                "chunk_id": cid,
                "doc_id": doc_id,
                "section_heading": sec_heading,
                "snippet": text_snippet,
                "retriever_flags": {
                    "dense_top10": is_dense,
                    "bm25_top10": is_bm25,
                    "hybrid_top10": is_hybrid,
                    "control": is_control,
                },
                "human_relevance_label": "",  # To be labeled: "relevant", "partially_relevant", "not_relevant"
            }
            pooled_records.append(record)

            csv_rows.append({
                "query_id": qid,
                "query_text": q_text,
                "chunk_id": cid,
                "doc_id": doc_id,
                "section_heading": sec_heading,
                "chunk_snippet": text_snippet,
                "human_relevance_label": "",  # Annotator fills: 2 (relevant), 1 (partially), 0 (not relevant)
            })

    # Save JSONL
    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSONL, "w", encoding="utf-8") as f:
        for r in pooled_records:
            f.write(json.dumps(r) + "\n")

    # Save CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "query_id", "query_text", "chunk_id", "doc_id", "section_heading", "chunk_snippet", "human_relevance_label"
        ])
        writer.writeheader()
        writer.writerows(csv_rows)

    # Source distribution
    source_counts = {"core": 0, "medlineplus": 0, "openfda": 0, "other": 0}
    unique_chunk_sources = {}
    for r in pooled_records:
        did = r["doc_id"].upper()
        if did.startswith("KB-FDA"):
            src = "openfda"
        elif did.startswith("KB-MP"):
            src = "medlineplus"
        elif any(did.startswith(f"KB-{prefix}") for prefix in ["B", "C", "D", "K", "L", "M"]):
            src = "core"
        else:
            src = "other"
        source_counts[src] += 1
        unique_chunk_sources[r["chunk_id"]] = src

    unique_src_counts = {"core": 0, "medlineplus": 0, "openfda": 0, "other": 0}
    for src in unique_chunk_sources.values():
        unique_src_counts[src] += 1

    print(f"[OK] Pooled {len(pooled_records)} query-chunk candidate pairs across {len(selected_queries)} queries.")
    print(f"  Average pooled chunks per query: {len(pooled_records)/len(selected_queries):.2f}")
    print(f"  Source distribution (pairs): core={source_counts['core']}, medlineplus={source_counts['medlineplus']}, openfda={source_counts['openfda']}, other={source_counts['other']}")
    print(f"  Source distribution (unique chunks): core={unique_src_counts['core']}, medlineplus={unique_src_counts['medlineplus']}, openfda={unique_src_counts['openfda']}, other={unique_src_counts['other']}")
    print(f"  Saved JSONL: {OUTPUT_JSONL}")
    print(f"  Saved CSV:   {OUTPUT_CSV}")
    print("=" * 60)


if __name__ == "__main__":
    build_pooled_relevance(150)
