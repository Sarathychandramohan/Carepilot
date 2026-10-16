"""
backend/scripts/tune_retrieval_alpha.py

Grid search over alpha in [0.0, 1.0] (step 0.1) on dev queries.
Computes Hit@3, Hit@5, and MRR for each alpha.
Reports dense-only (alpha=1.0), BM25-only (alpha=0.0), and hybrid (optimal alpha).
"""
import json
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[2]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from backend.app.pipeline.retrieve_kb import (
    _get_embedder,
    _get_chroma_collection,
    _get_bm25,
    _min_max_convex_fuse,
    to_spec_chunk_id,
)

def main():
    root = Path(__file__).resolve().parents[2]
    candidate_file = root / "data" / "queries" / "gold_scripted_candidate.jsonl"
    
    with open(candidate_file, "r", encoding="utf-8") as f:
        queries = [json.loads(line) for line in f]
    
    dev_queries = [
        q for q in queries 
        if q.get("split") == "dev" and q.get("expected_kb_doc_ids")
    ]
    print(f"Loaded {len(dev_queries)} dev queries with expected_kb_doc_ids.")
    
    embedder = _get_embedder()
    collection = _get_chroma_collection()
    bm25, corpus_ids = _get_bm25()
    
    dense_top_k = 20
    bm25_top_k = 20
    
    print("Pre-retrieving candidate pools for all dev queries...")
    t0 = time.time()
    
    query_pools = []
    for q in dev_queries:
        q_text = q["query_text"]
        expected_docs = set(q["expected_kb_doc_ids"])
        
        # Dense
        q_emb = embedder.encode([q_text], normalize_embeddings=True).tolist()[0]
        dense_res = collection.query(
            query_embeddings=[q_emb],
            n_results=dense_top_k,
            include=["metadatas", "distances"],
        )
        dense_ids = dense_res["ids"][0]
        dense_dists = dense_res["distances"][0]
        dense_scores = {cid: 1.0 - d for cid, d in zip(dense_ids, dense_dists)}
        
        # Document ID mapping
        chunk_to_doc = {}
        for cid, meta in zip(dense_ids, dense_res["metadatas"][0]):
            chunk_to_doc[cid] = meta.get("doc_id", "")
        
        # Sparse
        tokens = q_text.lower().split()
        bm25_all = bm25.get_scores(tokens)
        top_b_idx = sorted(range(len(bm25_all)), key=lambda i: bm25_all[i], reverse=True)[:bm25_top_k]
        sparse_scores = {corpus_ids[i]: float(bm25_all[i]) for i in top_b_idx}
        
        # BM25-only chunk doc_id lookup
        missing_cids = [cid for cid in sparse_scores if cid not in chunk_to_doc]
        if missing_cids:
            try:
                fetched = collection.get(ids=missing_cids, include=["metadatas"])
                for cid, meta in zip(fetched["ids"], fetched["metadatas"]):
                    chunk_to_doc[cid] = meta.get("doc_id", "")
            except Exception:
                pass
                
        # Fill any unresolved doc_ids by parsing ID string
        for cid in list(dense_scores.keys()) + list(sparse_scores.keys()):
            if cid not in chunk_to_doc or not chunk_to_doc[cid]:
                # e.g. "kb:KB-MP0042:chunk0000" -> "KB-MP0042"
                import re
                m = re.match(r"^(?:kb:)?([A-Za-z0-9\-_]+)[_:]chunk", cid)
                chunk_to_doc[cid] = m.group(1) if m else cid
        
        query_pools.append({
            "query_id": q["query_id"],
            "expected_docs": expected_docs,
            "dense_scores": dense_scores,
            "sparse_scores": sparse_scores,
            "chunk_to_doc": chunk_to_doc,
        })
        
    print(f"Pre-retrieval done in {time.time() - t0:.2f}s.")
    
    alphas = [round(x * 0.1, 1) for x in range(11)]
    results = []
    
    for alpha in alphas:
        hit3_count = 0
        hit5_count = 0
        rr_sum = 0.0
        
        for p in query_pools:
            expected = p["expected_docs"]
            fused = _min_max_convex_fuse(p["dense_scores"], p["sparse_scores"], alpha=alpha)
            ranked_doc_ids = [p["chunk_to_doc"].get(cid, "") for cid, _, _, _ in fused]
            
            # Hit@3
            if any(doc in expected for doc in ranked_doc_ids[:3]):
                hit3_count += 1
                
            # Hit@5
            if any(doc in expected for doc in ranked_doc_ids[:5]):
                hit5_count += 1
                
            # MRR
            first_rank = None
            for idx, doc in enumerate(ranked_doc_ids, start=1):
                if doc in expected:
                    first_rank = idx
                    break
            if first_rank is not None:
                rr_sum += 1.0 / first_rank
                
        n = len(query_pools)
        hit3 = hit3_count / n
        hit5 = hit5_count / n
        mrr = rr_sum / n
        results.append({
            "alpha": alpha,
            "hit@3": round(hit3, 4),
            "hit@5": round(hit5, 4),
            "mrr": round(mrr, 4),
        })
        
    print("\n=== ALPHA GRID SEARCH RESULTS (DEV SET, N=150) ===")
    print(f"{'Alpha':<8}{'Hit@3':<10}{'Hit@5':<10}{'MRR':<10}")
    print("-" * 38)
    for r in results:
        print(f"{r['alpha']:<8.1f}{r['hit@3']:<10.4f}{r['hit@5']:<10.4f}{r['mrr']:<10.4f}")
        
    # Save results to json
    out_path = root / "data" / "manifests" / "retrieval_alpha_grid_search.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved grid search results to {out_path}")

if __name__ == "__main__":
    main()
