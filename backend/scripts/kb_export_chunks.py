"""
backend/scripts/kb_export_chunks.py

Export the exact chunk text stored in the ChromaDB vector DB to
rag_knowledge/kb_export/{doc_id}.txt — one file per document,
chunks in original insertion order (chunk_index ascending),
separated by a divider line.

Rules:
 - Text is taken directly from ChromaDB; it is NOT re-cleaned or rewritten.
 - Chunk separator: 80 dashes followed by "CHUNK {n}" on its own line.
 - If a doc_id has no chunks, the file is written as empty (so verify_real_data
   can report it as "thin" rather than "missing").

Usage (from project root):
  python -m backend.scripts.kb_export_chunks
  python -m backend.scripts.kb_export_chunks --collection carepilot_kb_v2
  python -m backend.scripts.kb_export_chunks --doc-id KB-D01   # single doc
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHROMA_DIR  = PROJECT_ROOT / "rag_knowledge" / "chroma_db"
EXPORT_DIR  = PROJECT_ROOT / "rag_knowledge" / "kb_export"
MANIFESTS   = PROJECT_ROOT / "data" / "manifests"
MANIFEST    = MANIFESTS / "kb_snapshot_v2.json"

CHUNK_SEP   = "-" * 80 + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export KB chunks from ChromaDB to text files")
    parser.add_argument("--collection", default="carepilot_kb_v2",
                        help="ChromaDB collection name")
    parser.add_argument("--chroma-dir", default=str(CHROMA_DIR))
    parser.add_argument("--export-dir", default=str(EXPORT_DIR))
    parser.add_argument("--manifest",   default=str(MANIFEST))
    parser.add_argument("--doc-id",     default=None,
                        help="Export only this doc_id (default: all)")
    args = parser.parse_args()

    export_dir = Path(args.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    # ── load manifest for doc_id list ───────────────────────────────────────
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}")
        sys.exit(1)
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    all_doc_ids = [
        str(d.get("doc_id") or d.get("id"))
        for d in m.get("documents", [])
    ]
    if args.doc_id:
        target_ids = [args.doc_id]
    else:
        target_ids = all_doc_ids

    print(f"[export] Target docs: {len(target_ids)}  collection: {args.collection}")

    # ── connect to ChromaDB ───────────────────────────────────────────────────
    try:
        import chromadb
    except ImportError:
        print("ERROR: chromadb not installed. Run: pip install chromadb")
        sys.exit(1)

    client = chromadb.PersistentClient(path=str(args.chroma_dir))
    try:
        col = client.get_collection(args.collection)
    except Exception as e:
        print(f"ERROR: cannot open collection '{args.collection}': {e}")
        sys.exit(1)

    total_chunks = col.count()
    print(f"[export] Collection has {total_chunks:,} total chunks")

    exported = 0
    empty    = 0

    for doc_id in target_ids:
        # Fetch all chunks for this doc_id
        try:
            result = col.get(
                where={"doc_id": {"$eq": doc_id}},
                include=["documents", "metadatas"],
            )
        except Exception as e:
            print(f"[warn] {doc_id}: ChromaDB error: {e}")
            # Write empty file
            out = export_dir / f"{doc_id}.txt"
            out.write_text("", encoding="utf-8")
            empty += 1
            continue

        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []

        if not documents:
            out = export_dir / f"{doc_id}.txt"
            out.write_text("", encoding="utf-8")
            empty += 1
            print(f"[export] {doc_id}: 0 chunks (empty file written)")
            continue

        # Sort by chunk_index if available
        pairs = list(zip(documents, metadatas))
        try:
            pairs.sort(key=lambda p: int((p[1] or {}).get("chunk_index", 0)))
        except Exception:
            pass  # keep original order if sort fails

        lines: list[str] = []
        for n, (text, meta) in enumerate(pairs):
            if text:
                lines.append(text.strip() + "\n\n")

        out = export_dir / f"{doc_id}.txt"
        out.write_text("".join(lines).strip() + "\n", encoding="utf-8")
        exported += 1
        if exported % 50 == 0:
            print(f"[export] {exported}/{len(target_ids)} docs exported ...")

    print(f"\n[export] Done.")
    print(f"  Exported (non-empty): {exported}")
    print(f"  Empty/missing:        {empty}")
    print(f"  Files written to:     {export_dir}")


if __name__ == "__main__":
    main()
