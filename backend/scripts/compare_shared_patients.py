"""
Step 2: Compare 31 shared patients by identity (BIRTHDATE, FIRST, LAST, GENDER).
Decision:
  - Same person (all 4 match): SAME_PERSON_SKIP_DEMO -> keep 2k version only
  - Different person (any differ): DIFFERENT_PERSON_KEEP_BOTH -> prefix IDs with 'demo40:'
"""
import csv
import json
from pathlib import Path

DEMO_CSV   = Path("synthea/carepilot_output/csv/patients.csv")
SCALE_CSV  = Path("synthea/carepilot_output_2k/csv/patients.csv")
OVERLAP_F  = Path("data/manifests/ehr_merge_overlap.json")
OUT_FILE   = Path("data/manifests/ehr_merge_decisions.json")
IDENTITY   = ["BIRTHDATE", "FIRST", "LAST", "GENDER"]

with open(OVERLAP_F) as f:
    overlap = json.load(f)

# The shared patient IDs are dict keys (UUID format, length ~36)
shared_ids = list(overlap.get("shared_patients", {}).keys())
print(f"Shared patient IDs from overlap: {len(shared_ids)}")

def read_patients(path):
    rows = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows[row["Id"]] = row
    return rows

demo  = read_patients(DEMO_CSV)
scale = read_patients(SCALE_CSV)
print(f"Demo CSV:  {len(demo)} patients")
print(f"Scale CSV: {len(scale)} patients")
print()
print(f"{'ID':40s}  {'Decision':26s}  Notes")
print("-" * 100)

decisions = []
same_count = 0
diff_count = 0

for pid in sorted(shared_ids):
    d = demo.get(pid)
    s = scale.get(pid)
    if d is None:
        print(f"{pid}  MISSING_IN_DEMO")
        continue
    if s is None:
        print(f"{pid}  MISSING_IN_SCALE")
        continue

    id_match = all(d.get(f, "") == s.get(f, "") for f in IDENTITY)
    diff_id = [f for f in IDENTITY if d.get(f, "") != s.get(f, "")]

    if id_match:
        dec  = "SAME_PERSON_SKIP_DEMO"
        note = "identity matches; keep 2k row"
        same_count += 1
    else:
        dec  = "DIFFERENT_PERSON_KEEP_BOTH"
        note = f"identity diffs: {diff_id}"
        diff_count += 1

    print(f"{pid}  {dec:26s}  {note}")
    decisions.append({
        "patient_id": pid,
        "decision": dec,
        "identity_match": id_match,
        "identity_diff_fields": diff_id,
        "demo":  {f: d.get(f, "") for f in IDENTITY},
        "scale": {f: s.get(f, "") for f in IDENTITY},
    })

print("-" * 100)
print(f"Same person (keep 2k only): {same_count}")
print(f"Different person (keep both): {diff_count}")
print(f"Total compared: {same_count + diff_count}")

OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_FILE, "w") as f:
    json.dump({
        "shared_count": len(shared_ids),
        "same_person_skip_demo": same_count,
        "different_person_keep_both": diff_count,
        "decisions": decisions,
    }, f, indent=2)
print(f"\nWritten: {OUT_FILE}")
