import json

silver = [json.loads(l) for l in open('data/queries/silver.jsonl', encoding='utf-8')]
families = [
    'SF-DEV-APPT-ROUTINE',
    'SF-DEV-APPT-SYMPTOM-REVIEW',
    'SF-TEST-APPT-CHRONIC-CHECK',
    'SF-TEST-APPT-CLINIC-VISIT',
    'SF-TEST-SYMPTOM-DIZZINESS',
    'SF-TEST-SYMPTOM-ANAPHYLAXIS'
]

for fam in families:
    matches = [s for s in silver if s.get('scenario_family') == fam]
    print(f"=== Family: {fam} (Total queries: {len(matches)}) ===")
    for m in matches[:5]:
        print(f"  - [{m['query_id']}] \"{m['query_text']}\"")
    print()
