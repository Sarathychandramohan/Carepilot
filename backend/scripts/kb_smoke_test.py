"""
D:\\CarePilotAI\\backend\\scripts\\kb_smoke_test.py

Retrieval smoke test for the v2 KB snapshot.
Tests 5 clinical queries against both dense (ChromaDB) and sparse (BM25) indexes.
PASS criterion: 5/5 queries return at least 1 expected document in top-5 results.
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

import argparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHROMA_DIR = PROJECT_ROOT / "rag_knowledge" / "chroma_db"
DEFAULT_BM25_PATH = PROJECT_ROOT / "rag_knowledge" / "bm25_index_v5.pkl"
DEFAULT_COLLECTION_NAME = "carepilot_kb_v5"
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

TEST_QUERIES = [
    ("What is an A1C test and what does it measure?", ["KB-D01", "KB-MP0010", "KB-D03", "KB-MP0567"]),
    ("What does a serum creatinine test indicate?", ["KB-K01", "KB-MP0039", "KB-K02", "KB-MP0509"]),
    ("What are the side effects and uses of Lisinopril?", ["KB-FDA0001", "KB-M04", "KB-C01"]),
    ("What is eGFR and how is kidney function evaluated?", ["KB-K01", "KB-K03", "KB-MP0039", "KB-MP0535"]),
    ("What is Metformin used for and what are its warnings?", ["KB-FDA0026", "KB-D02", "KB-MP0076"]),
]


def run_smoke_test(
    collection_name: str = DEFAULT_COLLECTION_NAME,
    bm25_path: Path = DEFAULT_BM25_PATH,
) -> bool:
    print("\n" + "=" * 60)
    print(f"CarePilot AI — Knowledge Base Retrieval Smoke Test ({collection_name})")
    print("=" * 60)

    # 1. Load ChromaDB
    print(f"[Smoke Test] Loading ChromaDB collection '{collection_name}'...")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        collection = client.get_collection(collection_name)
    except Exception as e:
        print(f"FAILED to load ChromaDB collection: {e}")
        return False

    # 2. Load Embedding Model
    print(f"[Smoke Test] Loading embedding model '{EMBEDDING_MODEL_NAME}'...")
    embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)

    # 3. Load BM25 Index
    print(f"[Smoke Test] Loading BM25 index from {bm25_path}...")
    if not bm25_path.exists():
        print(f"FAILED: BM25 index file not found at {bm25_path}")
        return False

    with open(bm25_path, "rb") as f:
        bm25_data = pickle.load(f)

    bm25 = bm25_data["bm25"]
    chunk_ids = bm25_data["chunk_ids"]
    chunk_meta = {m["chunk_id"]: m for m in bm25_data["chunk_metadata"]}

    passed_count = 0
    total_queries = len(TEST_QUERIES)

    print("\n[Smoke Test] Evaluating test queries:")
    for query, expected_docs in TEST_QUERIES:
        print(f"\nQuery: '{query}'")
        print(f"Expected Doc IDs (any): {expected_docs}")

        # Dense retrieval
        q_embed = embedder.encode(query, normalize_embeddings=True).tolist()
        dense_res = collection.query(query_embeddings=[q_embed], n_results=5)
        dense_doc_ids = [m["doc_id"] for m in dense_res["metadatas"][0]]

        # Sparse retrieval (BM25)
        tokens = [w.lower() for w in query.split() if w.strip()]
        scores = bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:5]
        sparse_doc_ids = [chunk_meta[chunk_ids[i]]["doc_id"] for i in top_indices]

        # Union of top results
        combined_doc_ids = list(set(dense_doc_ids + sparse_doc_ids))
        match = any(exp in combined_doc_ids for exp in expected_docs)

        dense_match = any(exp in dense_doc_ids for exp in expected_docs)
        sparse_match = any(exp in sparse_doc_ids for exp in expected_docs)

        print(f"  Dense top-5 doc IDs:  {dense_doc_ids} {'[MATCH]' if dense_match else '[NO MATCH]'}")
        print(f"  Sparse top-5 doc IDs: {sparse_doc_ids} {'[MATCH]' if sparse_match else '[NO MATCH]'}")

        if match:
            print("  Result: [PASS] (Expected document found in top-5)")
            passed_count += 1
        else:
            print("  Result: [FAIL] (Expected document NOT found in top-5)")

    print("\n" + "-" * 60)
    print(f"Smoke Test Summary: {passed_count}/{total_queries} passed.")
    all_passed = passed_count == total_queries
    if all_passed:
        print("[OK] A2 KB Ingestion Gate: PASS")
    else:
        print("[FAIL] A2 KB Ingestion Gate: FAIL")
    print("=" * 60)
    return all_passed


if __name__ == "__main__":
    success = run_smoke_test()
    sys.exit(0 if success else 1)
