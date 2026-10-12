"""
D:\\CarePilotAI\\backend\\scripts\\kb_build_index.py

Embeds chunks using BAAI/bge-small-en-v1.5 and upserts them into ChromaDB
collection `carepilot_kb_v2`.
Batch processing ensures low VRAM footprint on 4GB GPUs (RTX 2050).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHROMA_DIR = PROJECT_ROOT / "rag_knowledge" / "chroma_db"
COLLECTION_NAME = "carepilot_kb_v2"
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
BATCH_SIZE = 64


def build_chroma_index(
    chunks: list[dict[str, Any]],
    chroma_dir: Path = CHROMA_DIR,
    collection_name: str = COLLECTION_NAME,
) -> int:
    print(f"\n[ChromaDB] Initializing client at {chroma_dir}...")
    client = chromadb.PersistentClient(path=str(chroma_dir))

    # Reset or get collection
    try:
        client.delete_collection(collection_name)
        print(f"[ChromaDB] Deleted existing collection: {collection_name}")
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    print(f"[ChromaDB] Loading embedding model: {EMBEDDING_MODEL_NAME}...")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    total = len(chunks)
    print(f"[ChromaDB] Embedding and indexing {total} chunks in batches of {BATCH_SIZE}...")

    for i in range(0, total, BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        texts = [c["text"] for c in batch]
        ids = [c["chunk_id"] for c in batch]
        metadatas = [
            {
                "doc_id": c["doc_id"],
                "snapshot_id": c.get("snapshot_id", "v2"),
                "section_heading": c.get("section_heading") or "",
                "source_name": c.get("source_name") or "",
                "license": c.get("license") or "",
                "token_count": c.get("token_count", 0),
            }
            for c in batch
        ]

        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).tolist()

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        print(f"  Indexed {min(i + BATCH_SIZE, total)} / {total} chunks")

    print(f"[ChromaDB] Successfully indexed {collection.count()} chunks in '{collection_name}'.")
    return collection.count()
