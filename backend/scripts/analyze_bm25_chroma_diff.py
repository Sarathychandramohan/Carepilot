import pickle
import chromadb
import json
from pathlib import Path

# Check ChromaDB
client = chromadb.PersistentClient("rag_knowledge/chroma_db")
coll = client.get_collection("carepilot_kb_v5")
chroma_count = coll.count()
chroma_res = coll.get()
chroma_ids = set(chroma_res["ids"])
print(f"Chroma collection carepilot_kb_v5 count: {chroma_count}")

# Check BM25
with open("rag_knowledge/bm25_index_v5.pkl", "rb") as f:
    bm25_data = pickle.load(f)
bm25_count = len(bm25_data["chunk_ids"])
bm25_ids = set(bm25_data["chunk_ids"])
print(f"BM25 index v5 count: {bm25_count}")

diff_chroma_only = chroma_ids - bm25_ids
diff_bm25_only = bm25_ids - chroma_ids
print(f"Chunks in Chroma but NOT in BM25: {len(diff_chroma_only)}")
print(f"Chunks in BM25 but NOT in Chroma: {len(diff_bm25_only)}")

docs_chroma_only = {cid.split(":")[1] if ":" in cid else cid for cid in diff_chroma_only}
print(f"Doc IDs with chunks in Chroma but NOT in BM25 ({len(docs_chroma_only)} docs):")
print(sorted(list(docs_chroma_only))[:30])

docs_bm25_only = {cid.split(":")[1] if ":" in cid else cid for cid in diff_bm25_only}
print(f"Doc IDs with chunks in BM25 but NOT in Chroma ({len(docs_bm25_only)} docs):")
print(sorted(list(docs_bm25_only))[:30])

manifest = json.load(open("data/manifests/kb_snapshot_v5.json"))
manifest_doc_count = len(manifest["documents"])
manifest_chunks = sum(d.get("chunk_count", 0) for d in manifest["documents"])
print(f"Manifest documents: {manifest_doc_count}")
print(f"Manifest total chunk_count sum: {manifest_chunks}")
