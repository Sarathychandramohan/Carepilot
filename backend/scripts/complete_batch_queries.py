"""
backend/scripts/complete_batch_queries.py

Executes the remaining 6 queries (10-15) from the 15-query batch with the
encounters start_time schema fix applied, then merges with queries 1-9 to produce
the final comprehensive 15-query batch report in data/manifests/pillar_b_batch_eval_15.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from collections import Counter

from backend.app.db.session import SessionLocal
from backend.app.pipeline.orchestrator import run_pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "pillar_b_batch_eval_15.json"


def run_remaining_queries():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    existing_results = data["results"]
    completed_results = [r for r in existing_results if r.get("validation_status") != "error"]
    failed_entries = [r for r in existing_results if r.get("validation_status") == "error"]

    print(f"Loaded {len(completed_results)} previously completed queries.")
    print(f"Running remaining {len(failed_entries)} queries (10-15)...")

    db = SessionLocal()
    try:
        newly_completed = []
        for idx, entry in enumerate(failed_entries, start=1):
            qid = entry["query_id"]
            pid = entry["patient_id"]
            qtext = entry["query_text"]
            true_intent = entry["true_intent"]

            print(f"\n--- [{idx}/{len(failed_entries)}] Query {qid} ({true_intent}) ---", flush=True)
            print(f"Query: \"{qtext}\"", flush=True)

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

                res = {
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
                newly_completed.append(res)
            except Exception as e:
                db.rollback()
                elapsed = time.perf_counter() - t0
                print(f" -> ERROR: {e}", flush=True)
                res = {
                    "query_id": qid,
                    "patient_id": pid,
                    "query_text": qtext,
                    "true_intent": true_intent,
                    "error": str(e),
                    "pipeline_elapsed_s": round(elapsed, 2),
                    "validation_status": "error",
                }
                newly_completed.append(res)

        all_results = completed_results + newly_completed
        status_counts = Counter(r.get("validation_status") for r in all_results)
        latencies = [r["generation_latency_ms"] for r in all_results if r.get("generation_latency_ms")]
        latencies.sort()

        p95_lat = latencies[int(0.95 * len(latencies))] if latencies else 0
        median_lat = latencies[len(latencies) // 2] if latencies else 0
        mean_lat = sum(latencies) / len(latencies) if latencies else 0

        total_time = sum(r.get("pipeline_elapsed_s", 0) for r in all_results)

        summary = {
            "total_queries": len(all_results),
            "total_duration_s": round(total_time, 2),
            "status_breakdown": dict(status_counts),
            "pass_rate": round(status_counts.get("passed", 0) / len(all_results), 4),
            "warning_rate": round(status_counts.get("passed_with_warning", 0) / len(all_results), 4),
            "outlier_caveat_rate": round(status_counts.get("passed_with_outlier_caveat", 0) / len(all_results), 4),
            "manual_required_rate": round(status_counts.get("manual_required", 0) / len(all_results), 4),
            "latency_ms": {
                "median": median_lat,
                "mean": round(mean_lat, 1),
                "p95": p95_lat,
            },
        }

        print("\n" + "=" * 75)
        print("FINAL MERGED 15-QUERY BATCH EVALUATION SUMMARY")
        print("=" * 75)
        print(f"Total Queries: {summary['total_queries']} in {summary['total_duration_s']} s")
        print(f"Status Breakdown: {summary['status_breakdown']}")
        print(f"  • passed:                   {status_counts.get('passed', 0)} ({summary['pass_rate']*100:.1f}%)")
        print(f"  • passed_with_warning:      {status_counts.get('passed_with_warning', 0)} ({summary['warning_rate']*100:.1f}%)")
        print(f"  • passed_with_outlier_caveat:{status_counts.get('passed_with_outlier_caveat', 0)} ({summary['outlier_caveat_rate']*100:.1f}%)")
        print(f"  • manual_required:          {status_counts.get('manual_required', 0)} ({summary['manual_required_rate']*100:.1f}%)")
        print(f"Generation Latency (ms): Median={median_lat} ms | Mean={mean_lat:.1f} ms | p95={p95_lat} ms")
        print("=" * 75)

        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "results": all_results}, f, indent=2)
        print(f"Final manifest saved to {MANIFEST_PATH}")

    finally:
        db.close()


if __name__ == "__main__":
    run_remaining_queries()
