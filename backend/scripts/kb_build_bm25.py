"""
D:\\CarePilotAI\\backend\\scripts\\kb_build_bm25.py

Builds and freezes the BM25 sparse retrieval index over all chunks in data/kb_chunks/.
Saves pickled index to D:/CarePilotAI/rag_knowledge/bm25_index_v2.pkl
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHUNKS_DIR = PROJECT_ROOT / "data" / "kb_chunks"
DEFAULT_BM25_PATH = PROJECT_ROOT / "rag_knowledge" / "bm25_index_v2.pkl"


def build_bm25_index(
    chunks: list[dict[str, Any]],
    output_path: Path = DEFAULT_BM25_PATH,
) -> dict[str, Any]:
    """
    Builds BM25Okapi index from a list of chunk dicts.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n[BM25] Building sparse index for {len(chunks)} chunks...")

    tokenized_corpus = []
    chunk_ids = []
    chunk_metadata = []

    for c in chunks:
        # Simple word tokenization for BM25
        text = c.get("text", "")
        tokens = [w.lower() for w in text.split() if w.strip()]
        tokenized_corpus.append(tokens)
        chunk_ids.append(c["chunk_id"])
        chunk_metadata.append({
            "chunk_id": c["chunk_id"],
            "doc_id": c["doc_id"],
            "section_heading": c.get("section_heading"),
            "source_name": c.get("source_name"),
            "license": c.get("license"),
        })

    bm25 = BM25Okapi(tokenized_corpus)

    payload = {
        "bm25": bm25,
        "chunk_ids": chunk_ids,
        "chunk_metadata": chunk_metadata,
        "total_chunks": len(chunks),
    }

    with open(output_path, "wb") as f:
        pickle.dump(payload, f)

    print(f"[BM25] Index frozen and saved to: {output_path}")
    return payload


if __name__ == "__main__":
    # Scan all chunk JSON files
    all_chunks = []
    for p in CHUNKS_DIR.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    all_chunks.extend(data)
                elif isinstance(data, dict):
                    all_chunks.append(data)
        except Exception as e:
            print(f"Error reading {p}: {e}")

    if all_chunks:
        build_bm25_index(all_chunks)
    else:
        print("[BM25] No chunks found in data/kb_chunks/. Run kb_ingest_all.py first.")
