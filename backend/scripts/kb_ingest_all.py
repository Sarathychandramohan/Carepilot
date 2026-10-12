"""
D:\\CarePilotAI\\backend\\scripts\\kb_ingest_all.py

Full Knowledge Base Ingestion Pipeline:
1. Ingests existing core 18 documents from rag_knowledge/
2. Fetches DailyMed drug labels & MedlinePlus / CDC topics
3. Cleans and deduplicates all documents (kb_clean.py)
4. Chunks all documents into stable-ID segments (kb_chunk.py)
5. Builds ChromaDB collection `carepilot_kb_v2` (kb_build_index.py)
6. Builds BM25 sparse index `bm25_index_v2.pkl` (kb_build_bm25.py)
7. Generates `data/manifests/kb_snapshot_v2.json` and freezes snapshot
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from transformers import AutoTokenizer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.scripts.kb_clean import clean_markdown_document
from backend.scripts.kb_chunk import chunk_document, TOKENIZER_NAME
from backend.scripts.kb_build_index import build_chroma_index
from backend.scripts.kb_build_bm25 import build_bm25_index
from backend.scripts.kb_crawl_dailymed import crawl_dailymed

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAG_KNOWLEDGE_DIR = PROJECT_ROOT / "rag_knowledge"
RAW_KB_DIR = PROJECT_ROOT / "data" / "kb_raw"
CLEAN_KB_DIR = PROJECT_ROOT / "data" / "kb_clean"
CHUNKS_KB_DIR = PROJECT_ROOT / "data" / "kb_chunks"
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"


def ingest_existing_core_docs() -> list[dict[str, Any]]:
    """Ingests the 18 core documents from rag_knowledge/manifest/corpus_manifest.json."""
    manifest_path = RAG_KNOWLEDGE_DIR / "manifest" / "corpus_manifest.json"
    if not manifest_path.exists():
        print(f"[Ingest] Core manifest not found at {manifest_path}")
        return []

    with open(manifest_path, "r", encoding="utf-8-sig") as f:
        core_data = json.load(f)

    docs = []
    for d in core_data.get("documents", []):
        doc_id = d["document_id"]
        # Find cleaned or raw content (.txt or .md)
        content = None
        for ext in [".txt", ".md"]:
            clean_file = RAG_KNOWLEDGE_DIR / "cleaned" / f"{doc_id}{ext}"
            if clean_file.exists():
                content = clean_file.read_text(encoding="utf-8", errors="replace")
                break

        if not content:
            raw_folder = RAG_KNOWLEDGE_DIR / d.get("folder", "")
            for p in list(raw_folder.glob("*.txt")) + list(raw_folder.glob("*.md")):
                content = p.read_text(encoding="utf-8", errors="replace")
                break

        if not content:
            continue

        docs.append({
            "doc_id": doc_id,
            "title": d.get("title", doc_id),
            "source_name": d.get("source", "NIH / MedlinePlus"),
            "source_url": d.get("source_url", ""),
            "license": "Public Domain" if "WHO" not in d.get("source", "") else "CC BY-NC-SA 4.0",
            "commercial_use_restricted": "WHO" in d.get("source", ""),
            "topic": d.get("topic", "general"),
            "raw_text": content,
        })

    print(f"[Ingest] Loaded {len(docs)} existing core documents.")
    return docs


async def run_pipeline():
    CLEAN_KB_DIR.mkdir(parents=True, exist_ok=True)
    CHUNKS_KB_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 60)
    print("CarePilot AI — Knowledge Base Ingestion Pipeline (v2 Snapshot)")
    print("=" * 60)

    # 1. Gather all documents
    all_raw_docs = []

    # 1a. Core 18 docs
    core_docs = ingest_existing_core_docs()
    all_raw_docs.extend(core_docs)

    # 1b. DailyMed drug labels
    dailymed_entries = await crawl_dailymed(RAW_KB_DIR)
    for entry in dailymed_entries:
        path = Path(entry["file_path"])
        if path.exists():
            all_raw_docs.append({
                "doc_id": entry["doc_id"],
                "title": entry["title"],
                "source_name": entry["source_name"],
                "source_url": entry["source_url"],
                "license": entry["license"],
                "commercial_use_restricted": entry["commercial_use_restricted"],
                "topic": entry["topic"],
                "raw_text": path.read_text(encoding="utf-8"),
            })

    # 2. Clean & Deduplicate
    print(f"\n[Pipeline] Cleaning {len(all_raw_docs)} documents...")
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)
    cleaned_docs = []
    seen_hashes = set()

    for doc in all_raw_docs:
        res = clean_markdown_document(doc["raw_text"])
        if not res:
            continue
        if res["sha256"] in seen_hashes:
            print(f"  Duplicate skipped: {doc['doc_id']} ({doc['title']})")
            continue
        seen_hashes.add(res["sha256"])

        doc_clean_path = CLEAN_KB_DIR / f"{doc['doc_id']}.md"
        doc_clean_path.write_text(res["text"], encoding="utf-8")

        cleaned_docs.append({
            **doc,
            "cleaned_text": res["text"],
            "char_count": res["char_count"],
            "sha256": res["sha256"],
        })

    print(f"[Pipeline] {len(cleaned_docs)} clean, unique documents ready.")

    # 3. Chunk documents
    print(f"\n[Pipeline] Chunking documents (400 tokens / 60 overlap)...")
    all_chunks = []
    for doc in cleaned_docs:
        chunks = chunk_document(
            doc_id=doc["doc_id"],
            doc_title=doc["title"],
            source_name=doc["source_name"],
            license_type=doc["license"],
            commercial_restricted=doc["commercial_use_restricted"],
            text=doc["cleaned_text"],
            snapshot_id="v2",
            tokenizer=tokenizer,
        )
        all_chunks.extend(chunks)

        # Save per-doc chunk file
        chunk_file = CHUNKS_KB_DIR / f"{doc['doc_id']}.json"
        chunk_file.write_text(json.dumps(chunks, indent=2), encoding="utf-8")

    print(f"[Pipeline] Generated {len(all_chunks)} total chunks.")

    # 4. Build Dense Index (ChromaDB)
    build_chroma_index(all_chunks)

    # 5. Build Sparse Index (BM25)
    build_bm25_index(all_chunks)

    # 6. Write Snapshot Manifest
    snapshot_manifest = {
        "snapshot_id": "v2",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "chroma_collection": "carepilot_kb_v2",
        "bm25_index_path": "D:/CarePilotAI/rag_knowledge/bm25_index_v2.pkl",
        "doc_count": len(cleaned_docs),
        "chunk_count": len(all_chunks),
        "frozen": True,
        "documents": [
            {
                "doc_id": d["doc_id"],
                "title": d["title"],
                "source": d["source_name"],
                "license": d["license"],
                "sha256": d["sha256"],
            }
            for d in cleaned_docs
        ],
    }

    manifest_file = MANIFEST_DIR / "kb_snapshot_v2.json"
    manifest_file.write_text(json.dumps(snapshot_manifest, indent=2), encoding="utf-8")
    print(f"\n[OK] Snapshot manifest written & frozen -> {manifest_file}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_pipeline())
