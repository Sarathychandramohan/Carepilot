import json
packs = {}
for l in open('data/annotation/context_packs.jsonl', encoding='utf-8'):
    p = json.loads(l)
    packs[p['patient_id']] = json.dumps(p, ensure_ascii=False)
bad = 0
for i, l in enumerate(open('data/annotation/queries_all.jsonl', encoding='utf-8'), 1):
    q = json.loads(l)
    blob = packs.get(q['patient_id'])
    if blob is None:
        print(i, q['scenario_id'], 'UNKNOWN PATIENT'); bad += 1
    elif json.dumps(q['referenced_fact'], ensure_ascii=False)[1:-1] not in blob:
        print(i, q['scenario_id'], '| fact:', q['referenced_fact']); bad += 1
print('bad rows:', bad)