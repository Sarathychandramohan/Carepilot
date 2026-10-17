"""
backend/eval/tools/print_spanning_clusters.py
Analyzes silver dev+test splits and prints dev/test spanning clusters.
"""
import json
from pathlib import Path
from collections import defaultdict
import numpy as np
from sentence_transformers import SentenceTransformer
from backend.eval.diversity_report import strip_greetings_and_signoffs

def main():
    silver_path = Path("data/queries/silver.jsonl")
    silver_eval = [
        json.loads(line) for line in open(silver_path, encoding="utf-8")
        if line.strip() and json.loads(line).get("split") in ("dev", "test")
    ]
    print(f"Total silver dev+test queries: {len(silver_eval)}")

    model = SentenceTransformer("BAAI/bge-small-en-v1.5", local_files_only=True)
    mean_path = Path("backend/models/corpus_mean_bge_small.npy")
    mean = np.load(mean_path)

    cleaned = [strip_greetings_and_signoffs(q["query_text"]) for q in silver_eval]
    embs = model.encode(cleaned, normalize_embeddings=True)
    embs = embs - mean
    embs = embs / np.linalg.norm(embs, axis=1, keepdims=True)

    threshold = 0.60
    sim_mat = np.dot(embs, embs.T)
    n = len(silver_eval)

    adj = defaultdict(set)
    for i in range(n):
        for j in range(i + 1, n):
            if sim_mat[i, j] >= threshold:
                adj[i].add(j)
                adj[j].add(i)

    visited = set()
    components = []
    for i in range(n):
        if i not in visited:
            comp = []
            q = [i]
            visited.add(i)
            while q:
                curr = q.pop(0)
                comp.append(curr)
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        q.append(neighbor)
            components.append(comp)

    spanning = []
    for comp in components:
        splits = {silver_eval[idx]["split"] for idx in comp}
        if "dev" in splits and "test" in splits:
            spanning.append(comp)

    print(f"\nFound {len(spanning)} dev/test spanning clusters at threshold {threshold}:")
    for idx, comp in enumerate(spanning, start=1):
        fams = sorted(list({silver_eval[i].get("scenario_family") for i in comp}))
        dev_texts = [silver_eval[i]["query_text"] for i in comp if silver_eval[i]["split"] == "dev"]
        test_texts = [silver_eval[i]["query_text"] for i in comp if silver_eval[i]["split"] == "test"]
        print(f"\n=== Spanning Cluster {idx} (size: {len(comp)} queries) ===")
        print(f"  Scenario families ({len(fams)}): {fams}")
        print(f"  Dev count: {len(dev_texts)}, Test count: {len(test_texts)}")
        print(f"  Sample Dev text:  \"{dev_texts[0]}\"")
        print(f"  Sample Test text: \"{test_texts[0]}\"")

if __name__ == "__main__":
    main()
