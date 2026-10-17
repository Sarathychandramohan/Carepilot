import json, numpy as np
from sentence_transformers import SentenceTransformer

rows = [json.loads(l) for l in open('data/annotation/queries_all.jsonl', encoding='utf-8')]
m = SentenceTransformer('BAAI/bge-small-en-v1.5', local_files_only=True)
E = m.encode([r['query_text'] for r in rows], normalize_embeddings=True)

def report(E, label):
    S = E @ E.T
    iu = np.triu_indices(len(rows), 1)
    v = S[iu]
    print(f"\n== {label} ==")
    print("percentiles 50/90/99/max:", [round(float(np.percentile(v, p)), 3) for p in (50, 90, 99, 100)])
    for t in (0.5, 0.6, 0.7, 0.8, 0.85, 0.9):
        print(f"pairs >= {t}: {int((v >= t).sum())}")
    order = np.argsort(-v)[:8]
    for k in order:
        i, j = iu[0][k], iu[1][k]
        print(f"  {rows[i]['scenario_id']} vs {rows[j]['scenario_id']}: {v[k]:.3f}")

report(E, "raw")
Ec = E - E.mean(axis=0)
Ec /= np.linalg.norm(Ec, axis=1, keepdims=True)
report(Ec, "mean-centered")