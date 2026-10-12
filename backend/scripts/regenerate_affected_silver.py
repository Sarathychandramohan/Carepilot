"""
D:\\CarePilotAI\\backend\\scripts\\regenerate_affected_silver.py

Identifies and regenerates ONLY the affected queries in silver.jsonl
that were grounded in administrative or non-clinical situation/finding conditions.
Leaves all other queries in silver.jsonl completely untouched, preserving their IDs and content.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from rapidfuzz import fuzz

from backend.scripts.silver_generator import (
    clean_condition,
    is_clinical_condition,
    load_patients,
    SCENARIO_FAMILIES,
    SILVER_OUTPUT_PATH,
    GOLD_PATH,
)


def main():
    if not SILVER_OUTPUT_PATH.exists():
        raise FileNotFoundError(f"Missing {SILVER_OUTPUT_PATH}")

    existing_lines = SILVER_OUTPUT_PATH.read_text(encoding="utf-8").splitlines()
    queries = [json.loads(line) for line in existing_lines if line.strip()]

    print(f"Total existing queries in silver.jsonl: {len(queries)}")

    # Load gold queries for anti-leakage checking
    gold_queries = []
    if GOLD_PATH.exists():
        with open(GOLD_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    gold_queries.append(json.loads(line).get("query_text", ""))

    patients = load_patients()
    random.seed(4242)

    affected_indices = []
    for idx, q in enumerate(queries):
        concept = q.get("grounded_ehr_concept", {})
        if concept.get("grounded_concept_type") == "condition":
            desc = concept.get("description", "")
            if not is_clinical_condition(desc):
                affected_indices.append(idx)

    print(f"Found {len(affected_indices)} affected queries across silver.jsonl to regenerate.")

    for idx in affected_indices:
        q = queries[idx]
        sf_id = q["scenario_family"]
        sf_info = SCENARIO_FAMILIES[sf_id]
        templates = sf_info["templates"]

        # Find a valid patient with at least one clinical condition
        success = False
        attempts = 0
        while not success and attempts < 1000:
            attempts += 1
            p = random.choice(patients)
            raw_conds = p.get("active_conditions", [])
            clinical_conds = [c for c in raw_conds if is_clinical_condition(c["description"])]
            if not clinical_conds:
                continue

            cond_obj = random.choice(clinical_conds)
            cond_name = clean_condition(cond_obj["description"])
            tmpl = random.choice(templates)
            filled_text = tmpl.format(condition=cond_name)

            # Check similarity with Gold scripted candidate set
            is_dup = False
            for gq in gold_queries:
                if fuzz.ratio(filled_text.lower(), gq.lower()) > 88:
                    is_dup = True
                    break
            if is_dup:
                continue

            # Update the existing query in place, keeping query_id, tier, split, etc.
            q["query_text"] = filled_text
            q["patient_id"] = p["patient_id"]
            q["grounded_ehr_concept"] = {
                "grounded_concept_type": "condition",
                "code": cond_obj["code"],
                "description": cond_obj["description"],
            }
            success = True

        if not success:
            raise RuntimeError(f"Could not regenerate query {q['query_id']}")

    # Write updated silver.jsonl
    with open(SILVER_OUTPUT_PATH, "w", encoding="utf-8") as f:
        for q in queries:
            f.write(json.dumps(q) + "\n")

    print(f"[OK] Successfully replaced {len(affected_indices)} affected queries in {SILVER_OUTPUT_PATH}.")
    print("All other queries remain completely untouched.")


if __name__ == "__main__":
    main()
