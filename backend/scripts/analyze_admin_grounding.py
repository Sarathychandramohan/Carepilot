import json
from pathlib import Path

silver_path = Path("data/queries/silver.jsonl")
queries = [json.loads(line) for line in silver_path.read_text(encoding="utf-8").splitlines() if line.strip()]

symptom_queries = [q for q in queries if q.get("intent_label") == "symptom_report"]

all_admin_queries = []
admin_symptom_queries = []

for q in queries:
    concept = q.get("grounded_ehr_concept", {})
    if concept.get("grounded_concept_type") == "condition":
        desc = concept.get("description", "")
        desc_l = desc.lower()
        if "(situation)" in desc_l or "review due" in desc_l:
            all_admin_queries.append(q)
            if q.get("intent_label") == "symptom_report":
                admin_symptom_queries.append(q)
        elif "(finding)" in desc_l:
            non_clinical = [
                "employment", "educated", "education", "social", "housing",
                "refugee", "stress", "partner abuse", "abuse", "criminal",
                "transportation", "food insecurity", "marital", "drinking behavior",
                "misuses drugs", "violence", "labor force"
            ]
            if any(k in desc_l for k in non_clinical):
                all_admin_queries.append(q)
                if q.get("intent_label") == "symptom_report":
                    admin_symptom_queries.append(q)

print(f"Total silver queries: {len(queries)}")
print(f"Total queries grounded in situation/admin finding: {len(all_admin_queries)}")
print(f"Total symptom_report queries: {len(symptom_queries)}")
print(f"symptom_report queries grounded in situation/admin finding: {len(admin_symptom_queries)} ({len(admin_symptom_queries)/len(symptom_queries)*100:.2f}%)")

print("\n--- 5 Examples of symptom_report queries grounded in administrative/situation conditions ---")
for i, ex in enumerate(admin_symptom_queries[:5], 1):
    c = ex["grounded_ehr_concept"]
    print(f"Example {i}:")
    print(f"  Query ID: {ex['query_id']}")
    print(f"  Scenario Family: {ex['scenario_family']}")
    print(f"  Query Text: \"{ex['query_text']}\"")
    print(f"  Patient ID: {ex['patient_id']}")
    print(f"  Condition Code: {c['code']}")
    print(f"  Condition Description: \"{c['description']}\"")
    print()
