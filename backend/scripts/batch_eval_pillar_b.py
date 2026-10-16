"""
backend/scripts/batch_eval_pillar_b.py

Executes a stratified 15-query batch evaluation across all 5 clinical intents
using real silver test/dev queries and live patient records in PostgreSQL carepilot_v3.
Tests the full P1->P8 pipeline with local Ollama qwen3:8b, measuring:
- Intent / Urgency agreement
- Generation latency
- Citation coverage & validity
- NLI entailment scores
- 4-state validation distribution (passed, warning, caveat, manual_required)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from collections import Counter

from backend.app.db.session import SessionLocal
from backend.app.db.models_v3 import Patient, Consultation
from backend.app.pipeline.orchestrator import run_pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SILVER_PATH = PROJECT_ROOT / "data" / "queries" / "silver.jsonl"
OUT_MANIFEST = PROJECT_ROOT / "data" / "manifests" / "pillar_b_batch_eval_15.json"


def select_stratified_queries(db, target_per_intent: int = 3) -> list[dict]:
    """Select target_per_intent queries for each of the 5 intents where patient exists in DB."""
    db_pids = set(r[0] for r in db.query(Patient.id).all())
    
    with open(SILVER_PATH, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f]

    # Filter to matching patients, prioritize dev/test splits
    valid_records = [
        r for r in records
        if r.get("patient_id") in db_pids and r.get("intent_label")
    ]
    
    # Sort with dev and test first
    valid_records.sort(key=lambda x: 0 if x.get("split") in ("test", "dev") else 1)

    intents = [
        "symptom_report",
        "medication_query",
        "lab_result_query",
        "followup_appointment",
        "general_health_info",
    ]
    
    selected = []
    counts = {i: 0 for i in intents}
    
    for r in valid_records:
        intent = r.get("intent_label")
        if intent in counts and counts[intent] < target_per_intent:
            selected.append(r)
            counts[intent] += 1
            if all(c >= target_per_intent for c in counts.values()):
                break
                
    return selected


def run_batch_evaluation():
    print("=" * 75)
    print("CAREPILOT AI — PILLAR B 15-QUERY STRATIFIED BATCH EVALUATION")
    print("=" * 75)
    
    db = SessionLocal()
    try:
        queries = select_stratified_queries(db, target_per_intent=3)
        print(f"Selected {len(queries)} queries across 5 intents:")
        for q in queries:
            print(f"  • [{q.get('intent_label')}] ({q.get('split')}) {q.get('query_id')}: {q.get('query_text')[:60]}...")

        results = []
        t_batch_start = time.perf_counter()

        for idx, q in enumerate(queries, start=1):
            qid = q.get("query_id")
            pid = q.get("patient_id")
            qtext = q.get("query_text")
            true_intent = q.get("intent_label")

            print(f"\n--- [{idx}/{len(queries)}] Running Query {qid} ({true_intent}) ---")
            print(f"Query: \"{qtext}\"")

            t0 = time.perf_counter()
            try:
                consult = run_pipeline(
                    patient_id=pid,
                    query_text=qtext,
                    db=db,
                    ablation_config="full",
                    edit_memory=False,
                    is_eval=False,
                )
                elapsed = time.perf_counter() - t0

                res_entry = {
                    "query_id": qid,
                    "patient_id": pid,
                    "query_text": qtext,
                    "true_intent": true_intent,
                    "predicted_intent": consult.intent,
                    "intent_prob": consult.intent_prob,
                    "predicted_urgency": consult.urgency_final,
                    "has_draft": consult.ai_draft_json is not None,
                    "generation_latency_ms": consult.generation_latency_ms,
                    "pipeline_elapsed_s": round(elapsed, 2),
                    "citation_coverage": consult.faithfulness_score,
                    "citation_validity": consult.citation_validity_score,
                    "avg_nli_entailment": consult.citation_entailment_score,
                    "validation_status": consult.validation_status,
                    "thread_status": consult.thread_status,
                }
                print(f" -> Intent: {consult.intent} | Urgency: {consult.urgency_final}", flush=True)
                print(f" -> Draft: {consult.ai_draft_json is not None} (Latency: {consult.generation_latency_ms} ms)", flush=True)
                print(f" -> Status: {consult.validation_status} (Coverage: {consult.faithfulness_score}, NLI: {consult.citation_entailment_score})", flush=True)

            except Exception as e:
                elapsed = time.perf_counter() - t0
                db.rollback()
                print(f" -> ERROR: {e}", flush=True)
                res_entry = {
                    "query_id": qid,
                    "patient_id": pid,
                    "query_text": qtext,
                    "true_intent": true_intent,
                    "error": str(e),
                    "pipeline_elapsed_s": round(elapsed, 2),
                    "validation_status": "error",
                }

            results.append(res_entry)

        total_batch_time = time.perf_counter() - t_batch_start

        # Compute summary statistics
        status_counts = Counter(r.get("validation_status") for r in results)
        latencies = [r["generation_latency_ms"] for r in results if r.get("generation_latency_ms")]
        latencies.sort()

        p95_lat = latencies[int(0.95 * len(latencies))] if latencies else 0
        median_lat = latencies[len(latencies) // 2] if latencies else 0
        mean_lat = sum(latencies) / len(latencies) if latencies else 0

        summary = {
            "total_queries": len(results),
            "total_duration_s": round(total_batch_time, 2),
            "status_breakdown": dict(status_counts),
            "pass_rate": round(status_counts.get("passed", 0) / len(results), 4),
            "warning_rate": round(status_counts.get("passed_with_warning", 0) / len(results), 4),
            "outlier_caveat_rate": round(status_counts.get("passed_with_outlier_caveat", 0) / len(results), 4),
            "manual_required_rate": round(status_counts.get("manual_required", 0) / len(results), 4),
            "latency_ms": {
                "median": median_lat,
                "mean": round(mean_lat, 1),
                "p95": p95_lat,
            },
        }

        print("\n" + "=" * 75)
        print("PILLAR B BATCH EVALUATION SUMMARY (15 QUERIES)")
        print("=" * 75)
        print(f"Total Queries: {summary['total_queries']} in {summary['total_duration_s']} s")
        print(f"Status Breakdown: {summary['status_breakdown']}")
        print(f"  • passed:                   {status_counts.get('passed', 0)} ({summary['pass_rate']*100:.1f}%)")
        print(f"  • passed_with_warning:      {status_counts.get('passed_with_warning', 0)} ({summary['warning_rate']*100:.1f}%)")
        print(f"  • passed_with_outlier_caveat:{status_counts.get('passed_with_outlier_caveat', 0)} ({summary['outlier_caveat_rate']*100:.1f}%)")
        print(f"  • manual_required:          {status_counts.get('manual_required', 0)} ({summary['manual_required_rate']*100:.1f}%)")
        print(f"Generation Latency (ms): Median={median_lat} ms | Mean={mean_lat:.1f} ms | p95={p95_lat} ms")
        print("=" * 75)

        OUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_MANIFEST, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "results": results}, f, indent=2)
        print(f"Detailed manifest saved to {OUT_MANIFEST}")

    finally:
        db.close()


if __name__ == "__main__":
    run_batch_evaluation()
