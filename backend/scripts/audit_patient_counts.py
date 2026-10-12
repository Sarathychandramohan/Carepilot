import json
from pathlib import Path

# Check complex_patients.json
complex_p = json.load(open("data/manifests/complex_patients.json"))
print(f"Total patients in complex_patients.json: {len(complex_p.get('patients', []))}")
complex_ids = set(p["patient_id"] for p in complex_p.get("patients", []))

# Check silver.jsonl
silver_lines = [json.loads(line) for line in open("data/queries/silver.jsonl", encoding="utf-8") if line.strip()]
silver_patient_ids = set(q["patient_id"] for q in silver_lines if q.get("patient_id"))
print(f"Distinct patient IDs sampled in silver.jsonl: {len(silver_patient_ids)}")
print(f"Are all silver patient IDs within the complex patients pool? {silver_patient_ids.issubset(complex_ids)}")

# Check rq3_stream.jsonl
rq3_lines = [json.loads(line) for line in open("data/queries/rq3_stream.jsonl", encoding="utf-8") if line.strip()]
rq3_patient_ids = set(q["patient_id"] for q in rq3_lines if q.get("patient_id"))
print(f"Distinct patient IDs sampled in rq3_stream.jsonl: {len(rq3_patient_ids)}")
print(f"Are all rq3 patient IDs within the complex patients pool? {rq3_patient_ids.issubset(complex_ids)}")
