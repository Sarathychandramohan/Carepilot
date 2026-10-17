import json
from sentence_transformers import SentenceTransformer

rows = [json.loads(l) for l in open('data/annotation/queries_all.jsonl', encoding='utf-8')]
m = SentenceTransformer('BAAI/bge-small-en-v1.5', local_files_only=True)
E = m.encode([r['query_text'] for r in rows], normalize_embeddings=True)
S = E @ E.T
n = 0
for i in range(len(rows)):
    for j in range(i + 1, len(rows)):
        if S[i, j] >= 0.7:
            n += 1
            print(f"{rows[i]['scenario_id']} vs {rows[j]['scenario_id']}: {S[i, j]:.3f}")
print('pairs >= 0.7:', n)