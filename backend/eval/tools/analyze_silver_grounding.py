"""
backend/eval/tools/analyze_silver_grounding.py

Analyzes clinical grounding across all silver dev+test queries with requires_patient_context=True (1,300 queries).
Counts rows whose grounded_ehr_concept has zero matching rows for the assigned patient:
1. Via the pipeline's concept resolver (normalize_query_concepts -> retrieve_ehr)
2. Prints counts per scenario_family
3. Prints 5 detailed examples from each of 3 families:
   - SF-DEV-LAB-ABNORMAL
   - SF-TEST-LAB-TREND
   - SF-TEST-SYMPTOM-DIZZINESS
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from backend.app.db.session import SessionLocal
from backend.app.pipeline.normalize import normalize_query_concepts
from backend.app.pipeline.retrieve_ehr import retrieve_ehr

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SILVER_PATH = PROJECT_ROOT / "data" / "queries" / "silver.jsonl"


def main():
    db = SessionLocal()
    with open(SILVER_PATH, "r", encoding="utf-8") as f:
        queries = [
            json.loads(line) for line in f
            if line.strip() and json.loads(line).get("split") in ("dev", "test")
            and json.loads(line).get("requires_patient_context")
        ]

    print(f"Total silver dev+test queries with requires_patient_context: {len(queries)}")

    # Track failures:
    # 1. Pipeline retrieve_ehr returns 0 chunks entirely
    # 2. Pipeline retrieve_ehr does not include the expected grounded concept code
    empty_retrieval_per_fam = defaultdict(int)
    missing_grounded_concept_per_fam = defaultdict(int)
    family_queries = defaultdict(list)

    for q in queries:
        fam = q["scenario_family"]
        pid = q["patient_id"]
        gec = q.get("grounded_ehr_concept", {})
        expected_code = str(gec.get("code") or "")
        family_queries[fam].append(q)

        norm = normalize_query_concepts(q["query_text"])
        resolved_concepts = norm.get("resolved_concepts", [])
        chunks = retrieve_ehr(
            patient_id=pid,
            db=db,
            normalized_concepts=resolved_concepts,
            intent=q.get("intent_label"),
        )

        if len(chunks) == 0:
            empty_retrieval_per_fam[fam] += 1

        matched = any(str(c.raw.get("code") or "") == expected_code for c in chunks)
        if not matched:
            missing_grounded_concept_per_fam[fam] += 1

    print("\n" + "=" * 80)
    print("SILVER GROUNDING AUDIT VIA PIPELINE CONCEPT RESOLVER (N=1300)")
    print("=" * 80)
    print(f"{'Scenario Family':<32} | {'Total':<5} | {'Empty EHR Chunks':<18} | {'Grounded Concept Missing':<24}")
    print("-" * 85)

    all_fams = sorted(list(family_queries.keys()))
    tot_empty = 0
    tot_missing = 0
    for fam in all_fams:
        n = len(family_queries[fam])
        n_empty = empty_retrieval_per_fam[fam]
        n_missing = missing_grounded_concept_per_fam[fam]
        tot_empty += n_empty
        tot_missing += n_missing
        print(f"{fam:<32} | {n:<5} | {n_empty:>5} ({n_empty/n*100:>5.1f}%)    | {n_missing:>5} ({n_missing/n*100:>5.1f}%)")

    print("-" * 85)
    print(f"{'OVERALL TOTAL':<32} | {len(queries):<5} | {tot_empty:>5} ({tot_empty/len(queries)*100:>5.1f}%)    | {tot_missing:>5} ({tot_missing/len(queries)*100:>5.1f}%)")

    # 3 Selected Families for Detailed Examples
    selected_fams = [
        "SF-DEV-LAB-ABNORMAL",
        "SF-TEST-LAB-TREND",
        "SF-TEST-SYMPTOM-DIZZINESS",
    ]

    for fam in selected_fams:
        print("\n" + "=" * 80)
        print(f"5 DETAILED EXAMPLES FROM: {fam}")
        print("=" * 80)
        f_queries = family_queries[fam]
        
        # Pick 5 examples where grounded concept is missing in retrieval
        failed_examples = []
        for q in f_queries:
            norm = normalize_query_concepts(q["query_text"])
            chunks = retrieve_ehr(
                patient_id=q["patient_id"],
                db=db,
                normalized_concepts=norm["resolved_concepts"],
                intent=q["intent_label"],
            )
            gec = q.get("grounded_ehr_concept", {})
            expected_code = str(gec.get("code") or "")
            if not any(str(c.raw.get("code") or "") == expected_code for c in chunks):
                failed_examples.append((q, norm, chunks))
            if len(failed_examples) == 5:
                break

        for idx, (q, norm, chunks) in enumerate(failed_examples, 1):
            gec = q.get("grounded_ehr_concept", {})
            print(f"\n[{idx}/5] Query ID: {q['query_id']} | Patient ID: {q['patient_id']}")
            print(f"  Query Text:       \"{q['query_text']}\"")
            print(f"  Intent Label:     {q['intent_label']}")
            print(f"  Grounded Concept: Type={gec.get('grounded_concept_type')} | Code={gec.get('code')} | Desc={gec.get('description')}")
            print(f"  Pipeline Norm:    {norm['resolved_concepts']}")
            chunk_summaries = [f"{c.source_type}:{c.raw.get('code')} ({c.label})" for c in chunks]
            print(f"  EHR Chunks ({len(chunks)}): {chunk_summaries}")

    db.close()


if __name__ == "__main__":
    main()
