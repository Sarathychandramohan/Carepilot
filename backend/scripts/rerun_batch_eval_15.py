"""
backend/scripts/rerun_batch_eval_15.py

Re-evaluates the 15-query batch using the updated validation pipeline in validate.py
(tuned thresholds: NLI_PASS_THRESHOLD=0.15, NLI_WARN_THRESHOLD=0.001, CONTRADICTION_CEILING=0.05).
Updates the consultations table in PostgreSQL and data/manifests/pillar_b_batch_eval_15.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from collections import Counter

from backend.app.db.session import SessionLocal
from backend.app.db.models_v3 import Consultation
from backend.app.pipeline.retrieve_ehr import EHRChunk
from backend.app.pipeline.retrieve_kb import KBChunk
from backend.app.pipeline.generate import GeneratedDraft, DraftSentence
from backend.app.pipeline.validate import validate_draft

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "pillar_b_batch_eval_15.json"

def main():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    db = SessionLocal()
    updated_results = []

    print("================================================================================")
    print("RE-RUNNING BATCH EVALUATION ON N=15 QUERIES WITH REVISED THRESHOLDS")
    print("================================================================================")

    for item in manifest["results"]:
        qid = item["query_id"]
        qtext = item["query_text"]

        c = (
            db.query(Consultation)
            .filter(Consultation.query_text == qtext)
            .order_by(Consultation.query_received_at.desc())
            .first()
        )
        if not c:
            print(f"[{qid}] Consultation not found in DB")
            updated_results.append(item)
            continue

        if not c.ai_draft_json:
            # Query halted by safety guardrail (e.g. D17a patient-EHR mismatch)
            print(f"[{qid}] {item['true_intent']:20s} -> manual_required (D17a Patient-EHR Mismatch)")
            updated_results.append(item)
            continue

        draft_dict = c.ai_draft_json
        sentences = [DraftSentence(text=s["text"], citations=s["citations"]) for s in draft_dict.get("sentences", [])]
        draft = GeneratedDraft(
            sentences=sentences,
            overall_tone=draft_dict.get("overall_tone", "reassuring"),
            recommended_followup=draft_dict.get("recommended_followup"),
            urgency_assessment=draft_dict.get("urgency_assessment", "routine"),
            llm_model=draft_dict.get("llm_model", "qwen3:8b"),
            prompt_version=draft_dict.get("prompt_version", "v1"),
            generation_latency_ms=draft_dict.get("generation_latency_ms", 0),
            raw_llm_output="",
        )

        ehr_chunks = [
            EHRChunk(
                stable_eid=ec.get("stable_eid", ec.get("chunk_id", "")),
                source_type=ec.get("source_type", "condition"),
                label=ec.get("label", ""),
                display_value=ec.get("display_value", ec.get("text", "")),
                date_str=ec.get("date_str", ""),
                is_abnormal=ec.get("is_abnormal", False),
                is_outlier=ec.get("is_outlier", False),
                outlier_annotation=ec.get("outlier_annotation", None),
            )
            for ec in (c.ehr_chunks_json or [])
        ]

        kb_chunks = [
            KBChunk(
                chunk_id=kc["chunk_id"],
                doc_id=kc.get("doc_id", ""),
                source_name=kc.get("source_name", "KB"),
                source_url=kc.get("source_url", ""),
                title=kc.get("title", ""),
                text=kc["text"],
                score_hybrid=kc.get("score", 0.0),
            )
            for kc in (c.kb_chunks_json or [])
        ]

        # Execute revised validate_draft
        val_res = validate_draft(draft, ehr_chunks, kb_chunks)

        # Update DB row
        c.faithfulness_score = val_res.citation_coverage
        c.faithfulness_details = {
            "per_sentence": val_res.per_sentence,
            "max_contradiction": val_res.max_contradiction,
        }
        c.citation_validity_score = val_res.citation_validity
        c.citation_entailment_score = val_res.avg_nli_entailment
        c.has_outlier_only_sentence = val_res.has_outlier_only_sentence
        c.validation_status = val_res.validation_status
        db.commit()

        # Update manifest entry
        res_entry = dict(item)
        res_entry["citation_coverage"] = val_res.citation_coverage
        res_entry["citation_validity"] = val_res.citation_validity
        res_entry["avg_nli_entailment"] = val_res.avg_nli_entailment
        res_entry["max_contradiction"] = val_res.max_contradiction
        res_entry["validation_status"] = val_res.validation_status
        updated_results.append(res_entry)

        old_status = item.get("validation_status")
        print(f"[{qid}] {item['true_intent']:20s} -> {val_res.validation_status:20s} (was: {old_status:15s}) | Avg NLI: {val_res.avg_nli_entailment:.4f} | Max Contra: {val_res.max_contradiction:.4f}")

    db.close()

    # Recompute summary statistics
    status_counts = Counter(r.get("validation_status") for r in updated_results)
    total_q = len(updated_results)

    manifest["summary"]["status_breakdown"] = dict(status_counts)
    manifest["summary"]["pass_rate"] = round(status_counts.get("passed", 0) / total_q, 4)
    manifest["summary"]["warning_rate"] = round(status_counts.get("passed_with_warning", 0) / total_q, 4)
    manifest["summary"]["outlier_caveat_rate"] = round(status_counts.get("passed_with_outlier_caveat", 0) / total_q, 4)
    manifest["summary"]["manual_required_rate"] = round(status_counts.get("manual_required", 0) / total_q, 4)
    manifest["results"] = updated_results

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("\n================== REVISED BATCH EVALUATION SUMMARY ==================")
    print(f"Total Queries: {total_q}")
    print(f"Status Breakdown: {dict(status_counts)}")
    print(f"Pass Rate:             {manifest['summary']['pass_rate']*100:.1f}% ({status_counts.get('passed', 0)}/{total_q})")
    print(f"Warning Rate:          {manifest['summary']['warning_rate']*100:.1f}% ({status_counts.get('passed_with_warning', 0)}/{total_q})")
    print(f"Outlier Caveat Rate:   {manifest['summary']['outlier_caveat_rate']*100:.1f}% ({status_counts.get('passed_with_outlier_caveat', 0)}/{total_q})")
    print(f"Manual Required Rate:  {manifest['summary']['manual_required_rate']*100:.1f}% ({status_counts.get('manual_required', 0)}/{total_q})")
    print(f"Updated manifest saved to {MANIFEST_PATH}")

if __name__ == "__main__":
    main()
