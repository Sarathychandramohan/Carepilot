"""
D:\\CarePilotAI\\backend\\scripts\\rebuild_bm25_from_chroma.py

Rebuilds bm25_index_v5.pkl directly from the exact chunks present in ChromaDB carepilot_kb_v5
so that both dense and sparse retrieval stores are guaranteed 100% synchronized (exactly 10,074 chunks).
"""
from __future__ import annotations

import pickle
from pathlib import Path
import chromadb
from rank_bm25 import BM25Okapi

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHROMA_DIR = PROJECT_ROOT / "rag_knowledge" / "chroma_db"
COLLECTION_NAME = "carepilot_kb_v5"
BM25_OUTPUT_PATH = PROJECT_ROOT / "rag_knowledge" / "bm25_index_v5.pkl"


def rebuild_bm25():
    print("=" * 70)
    print("CarePilot AI — Rebuilding BM25 Sparse Index from ChromaDB Chunks")
    print("=" * 70)

    # 1. Connect to ChromaDB
    print(f"Connecting to ChromaDB collection '{COLLECTION_NAME}' at {CHROMA_DIR}...")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection(COLLECTION_NAME)

    total_chunks = collection.count()
    print(f"Total chunks in Chroma collection '{COLLECTION_NAME}': {total_chunks}")

    # 2. Fetch all chunks and metadata from Chroma
    print("Fetching all chunk records from ChromaDB...")
    res = collection.get(include=["documents", "metadatas"])

    ids = res["ids"]
    documents = res["documents"]
    metadatas = res["metadatas"]

    print(f"Retrieved {len(ids)} chunks from ChromaDB.")

    # Sort chunks deterministically by chunk_id
    sorted_triplets = sorted(zip(ids, documents, metadatas), key=lambda x: x[0])

    tokenized_corpus = []
    chunk_ids = []
    chunk_metadata = []

    print("Tokenizing corpus for BM25Okapi...")
    for cid, doc_text, meta in sorted_triplets:
        tokens = [w.lower() for w in (doc_text or "").split() if w.strip()]
        tokenized_corpus.append(tokens)
        chunk_ids.append(cid)
        chunk_metadata.append({
            "chunk_id": cid,
            "doc_id": meta.get("doc_id", cid.split(":")[1] if ":" in cid else ""),
            "section_heading": meta.get("section_heading"),
            "source_name": meta.get("source_name"),
            "license": meta.get("license"),
        })

    # 3. Build BM25Okapi model
    print("Instantiating BM25Okapi...")
    bm25 = BM25Okapi(tokenized_corpus)

    payload = {
        "bm25": bm25,
        "chunk_ids": chunk_ids,
        "chunk_metadata": chunk_metadata,
        "total_chunks": len(chunk_ids),
    }

    # 4. Save to BM25_OUTPUT_PATH
    BM25_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BM25_OUTPUT_PATH, "wb") as f:
        pickle.dump(payload, f)

    print(f"[OK] Successfully built and saved BM25 index to: {BM25_OUTPUT_PATH}")
    print(f"  Total chunks indexed: {len(chunk_ids)}")
    print(f"  Exact match with ChromaDB: {len(chunk_ids) == total_chunks}")
    print("=" * 70)


if __name__ == "__main__":
    rebuild_bm25()
