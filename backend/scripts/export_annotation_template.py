"""
D:\\CarePilotAI\\backend\\scripts\\export_annotation_template.py

Exports 150 candidate queries to a clean CSV template for human annotation.
Two independent human annotators will each fill out a separate copy of this template.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_PATH = PROJECT_ROOT / "data" / "queries" / "gold_scripted_candidate.jsonl"
OUTPUT_CSV_PATH = PROJECT_ROOT / "data" / "queries" / "annotation_template_150.csv"


def export_template(count: int = 150):
    OUTPUT_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)

    queries = []
    if CANDIDATE_PATH.exists():
        with open(CANDIDATE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    queries.append(json.loads(line))

    # Take first `count` queries
    selected = queries[:count] if len(queries) >= count else queries

    fieldnames = [
        "query_id",
        "query_text",
        "annotator_id",
        "intent_label",
        "urgency_label",
        "needs_patient_ehr",
        "is_in_scope",
        "comments",
    ]

    with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for q in selected:
            writer.writerow({
                "query_id": q["query_id"],
                "query_text": q["query_text"],
                "annotator_id": "",
                "intent_label": "",          # Choices: symptom_report, medication_query, lab_result_query, followup_appointment, general_health_info, unsupported
                "urgency_label": "",         # Choices: routine, soon, urgent
                "needs_patient_ehr": "",     # Choices: true, false
                "is_in_scope": "",           # Choices: true, false
                "comments": "",
            })

    print(f"[OK] Exported {len(selected)} query annotation templates to: {OUTPUT_CSV_PATH}")
    print("  Instructions: Copy this file for Annotator A and Annotator B to independently fill.")


if __name__ == "__main__":
    export_template(150)
