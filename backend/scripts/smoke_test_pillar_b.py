"""
backend/scripts/smoke_test_pillar_b.py

Live End-to-End Smoke Test for Pillar B:
1. P1->P8 full pipeline execution with local Ollama qwen3:8b
2. Post-generation faithfulness validation with cross-encoder NLI
3. Database persistence into PostgreSQL carepilot_v3
4. Doctor review submission with all 12 edit categories & Levenshtein metrics
5. D6 Doctor Edit Memory injection on follow-up consultation
"""
from __future__ import annotations

import datetime
import json
import time

from backend.app.db.session import SessionLocal
from backend.app.db.models_v3 import Consultation, Patient
from backend.app.pipeline.orchestrator import run_pipeline
from backend.app.api.consult import (
    DoctorReviewRequest,
    submit_doctor_review,
    deliver_consultation,
)
from backend.app.api.patient import get_patient_consultation
from backend.app.api.queue import get_queue
from fastapi import HTTPException
import asyncio


def run_smoke_test():
    print("=" * 70)
    print("CAREPILOT AI — PILLAR B LIVE END-TO-END SMOKE TEST")
    print("=" * 70)

    db = SessionLocal()
    try:
        # Step 0: Identify test patient
        patient = db.query(Patient).filter(Patient.id == "76b20010-c318-5754-8c85-983aa538522f").first()
        if not patient:
            patient = db.query(Patient).first()
        print(f"[TEST 0] Test Patient: {patient.first_name} {patient.last_name} (ID: {patient.id})")

        # Step 1: Execute P1->P8 Pipeline (Full Arm)
        query_text_1 = "Can I take Ibuprofen if I was also prescribed Amoxicillin for acute bronchitis?"
        print(f"\n[TEST 1] Submitting consultation query: '{query_text_1}'")
        t0 = time.perf_counter()
        consult_1 = run_pipeline(
            patient_id=patient.id,
            query_text=query_text_1,
            db=db,
            ablation_config="full",
            edit_memory=False,
            is_eval=False,
        )
        t_pipeline = time.perf_counter() - t0

        print(f" -> Consultation ID: {consult_1.id}")
        print(f" -> Elapsed Pipeline Time: {t_pipeline:.2f} s")
        print(f" -> Intent: {consult_1.intent} (Confidence: {consult_1.intent_prob:.4f})")
        print(f" -> Urgency: {consult_1.urgency_final} (Agreement: {consult_1.urgency_agreement})")
        print(f" -> EHR Chunks Retrieved: {len(consult_1.ehr_chunks_json or [])}")
        print(f" -> KB Chunks Retrieved: {len(consult_1.kb_chunks_json or [])}")
        print(f" -> AI Draft Generated: {consult_1.ai_draft_json is not None}")
        if consult_1.ai_draft_json:
            sentences = consult_1.ai_draft_json.get("sentences", [])
            print(f" -> Draft Sentence Count: {len(sentences)}")
            for idx, s in enumerate(sentences, 1):
                print(f"    [{idx}] {s.get('text')} | Cites: {s.get('citations')}")
            print(f" -> Generation Latency: {consult_1.generation_latency_ms} ms")
            print(f" -> Model: {consult_1.llm_model}")
        print(f" -> Validation Status: {consult_1.validation_status}")
        print(f" -> Citation Coverage: {consult_1.faithfulness_score}")
        print(f" -> NLI Entailment Score: {consult_1.citation_entailment_score}")
        print(f" -> Thread Status: {consult_1.thread_status}")

        assert consult_1.id is not None
        assert consult_1.intent == "medication_query"
        assert consult_1.validation_status in ("passed", "passed_with_warning", "passed_with_outlier_caveat", "manual_required")

        # Step 2: Doctor Review & Edit Tracking Submission (B5 / S9)
        print(f"\n[TEST 2] Submitting Clinician Review for Consultation {consult_1.id}...")
        # Doctor approves with minor clarification edit
        draft_sentences = (consult_1.ai_draft_json or {}).get("sentences", [])
        draft_text = " ".join(s.get("text", "") for s in draft_sentences)
        doctor_edited_text = draft_text + " Please drink plenty of fluids and rest."

        review_req = DoctorReviewRequest(
            doctor_action="approved",
            final_response=doctor_edited_text,
            edit_categories={"missing_caution": 1, "tone_change": 1},
            doctor_review_seconds=45,
            opened_sources=["ehr:medication:001"],
        )

        import asyncio
        review_resp = asyncio.run(submit_doctor_review(consult_1.id, review_req, db))

        print(f" -> Doctor Action: {review_resp.doctor_action}")
        print(f" -> Updated Thread Status: {review_resp.thread_status}")
        print(f" -> Final Response: '{review_resp.final_response[:80]}...'")
        print(f" -> Consultation Edit Weight: {review_resp.consultation_edit_weight}")
        print(f" -> Edit Distance (Chars): {review_resp.edit_distance_chars}")
        print(f" -> Edit Distance (Words): {review_resp.edit_distance_words}")
        print(f" -> EDR (Char): {review_resp.edr_char}")
        print(f" -> EDR (Word): {review_resp.edr_word}")
        print(f" -> Active Edit Categories: {[k for k, v in review_resp.edit_categories.items() if v]}")
        print(f" -> Review Timestamp: {review_resp.doctor_reviewed_at}")

        assert review_resp.thread_status == "approved"
        assert review_resp.consultation_edit_weight == 3.0  # missing_caution (2) + tone_change (1) = 3.0
        assert review_resp.edit_distance_chars > 0

        # Step 3: D6 Doctor Edit Memory on subsequent consultation
        query_text_2 = "What common side effects should I watch for with my Amoxicillin?"
        print(f"\n[TEST 3] Submitting follow-up consultation with edit_memory=True: '{query_text_2}'")
        t0 = time.perf_counter()
        consult_2 = run_pipeline(
            patient_id=patient.id,
            query_text=query_text_2,
            db=db,
            ablation_config="full",
            edit_memory=True,
            is_eval=False,
        )
        t_pipeline_2 = time.perf_counter() - t0

        print(f" -> Consultation ID: {consult_2.id}")
        print(f" -> Elapsed Pipeline Time: {t_pipeline_2:.2f} s")
        print(f" -> Edit Memory Used: {consult_2.edit_memory_used}")
        print(f" -> Edit Memory Records Found: {len(consult_2.edit_memory_json or [])}")
        if consult_2.edit_memory_json:
            for idx, rec in enumerate(consult_2.edit_memory_json, 1):
                print(f"    Memory [{idx}]: Query='{rec.get('query_text')[:40]}...' Cats={rec.get('edit_categories')}")
        print(f" -> AI Draft Generated: {consult_2.ai_draft_json is not None}")
        print(f" -> Validation Status: {consult_2.validation_status}")
        print(f" -> Final Urgency: {consult_2.urgency_final}")

        assert consult_2.edit_memory_used is True
        assert len(consult_2.edit_memory_json) >= 1
        assert consult_2.validation_status in ("passed", "passed_with_warning", "passed_with_outlier_caveat", "manual_required")

        # Step 4: Adversarial Faithfulness Validation Test
        print("\n" + "=" * 70)
        print("[TEST 4] ADVERSARIAL FAITHFULNESS VALIDATION TEST")
        print("=" * 70)
        print("Constructing adversarial draft with fabricated contradiction citing valid KB evidence:")
        print("  Sentence 1 (Grounded): 'Ibuprofen and Amoxicillin can generally be taken together.'")
        print("  Sentence 2 (Fabricated): 'Amoxicillin is an over-the-counter vitamin that cures all viral infections instantly at 5,000 mg hourly.'")

        from backend.app.pipeline.generate import GeneratedDraft, DraftSentence
        from backend.app.pipeline.validate import validate_draft
        from backend.app.pipeline.retrieve_kb import KBChunk
        from backend.app.pipeline.retrieve_ehr import EHRChunk

        # Reconstruct chunk objects from consult_1
        ehr_obj_list = [
            EHRChunk(
                stable_eid=c["stable_eid"],
                source_type=c["source_type"],
                label=c["label"],
                display_value=c["display_value"],
                date_str=c["date_str"],
                is_abnormal=c.get("is_abnormal", False),
                is_outlier=c.get("is_outlier", False),
                outlier_annotation=c.get("outlier_annotation"),
            )
            for c in (consult_1.ehr_chunks_json or [])
        ]
        kb_obj_list = [
            KBChunk(
                chunk_id=c["chunk_id"],
                doc_id=c["doc_id"],
                source_name=c["source_name"],
                source_url=c["source_url"],
                title=c["title"],
                text=c["text"],
                score_rrf=c.get("score_rrf", 0.0),
            )
            for c in (consult_1.kb_chunks_json or [])
        ]

        valid_chunk_id = kb_obj_list[0].chunk_id if kb_obj_list else "kb:KB-FDA0076:chunk0007"

        adversarial_draft = GeneratedDraft(
            sentences=[
                DraftSentence(
                    text="Ibuprofen and Amoxicillin can generally be taken together.",
                    citations=[valid_chunk_id],
                ),
                DraftSentence(
                    text="Amoxicillin is an over-the-counter vitamin that cures all viral infections instantly at 5,000 mg hourly.",
                    citations=[valid_chunk_id],  # Cites valid chunk, but statement is completely unsupported/contradictory
                ),
            ],
            overall_tone="informative",
            recommended_followup=None,
            urgency_assessment="routine",
            llm_model="adversarial_test",
            prompt_version="v1",
            generation_latency_ms=10,
            raw_llm_output="{}",
        )

        val_adversarial = validate_draft(adversarial_draft, ehr_obj_list, kb_obj_list)
        print(f" -> Citation Coverage: {val_adversarial.citation_coverage}")
        print(f" -> Citation Validity: {val_adversarial.citation_validity}")
        print(f" -> Average NLI Entailment: {val_adversarial.avg_nli_entailment:.4f}")
        print(f" -> Validation Status: {val_adversarial.validation_status}")
        for s_idx, sent_val in enumerate(val_adversarial.per_sentence, 1):
            print(f"    Sentence [{s_idx}] Entailment: {sent_val.get('entailment_score')} | Text: {sent_val.get('text')}")

        assert val_adversarial.validation_status == "manual_required", (
            f"Expected manual_required, got {val_adversarial.validation_status}"
        )
        assert val_adversarial.avg_nli_entailment < 0.30, (
            f"Expected avg NLI < 0.30, got {val_adversarial.avg_nli_entailment}"
        )
        print(" -> ADVERSARIAL VALIDATION TEST PASSED: correctly routed to manual_required!")

        # Step 5: P10 Delivery Sanitization & Delivery Endpoint
        print("\n" + "=" * 70)
        print("[TEST 5] P10 DELIVERY SANITIZATION & DELIVERY ENDPOINT")
        print("=" * 70)
        print(f"Delivering approved Consultation {consult_1.id}...")
        deliv_res = asyncio.run(deliver_consultation(consult_1.id, db))
        print(f" -> Delivered Thread Status: {deliv_res.thread_status}")
        print(f" -> Delivered Timestamp: {deliv_res.delivered_at}")
        print(f" -> Sanitized Final Response: '{deliv_res.final_response[:100]}...'")
        assert deliv_res.thread_status == "delivered"
        assert deliv_res.delivered_at is not None
        assert "[kb:" not in deliv_res.final_response
        assert "[ehr:" not in deliv_res.final_response
        assert "[EHR_CONTEXT]" not in deliv_res.final_response
        print(" -> P10 DELIVERY TEST PASSED!")

        # Step 6: Patient-Facing Read Endpoint & IDOR Protection
        print("\n" + "=" * 70)
        print("[TEST 6] PATIENT-FACING READ ENDPOINT & IDOR PROTECTION")
        print("=" * 70)
        # Legitimate access by patient
        pat_view = asyncio.run(get_patient_consultation(patient_id=patient.id, consultation_id=consult_1.id, db=db))
        print(f" -> Legitimate Patient Access Status: {pat_view.thread_status}")
        print(f" -> Final Response Received by Patient: '{pat_view.final_response[:80]}...'")
        assert pat_view.thread_status == "delivered"
        assert pat_view.final_response is not None

        # IDOR attack: wrong patient ID attempting to read consult_1
        attacker_id = "00000000-0000-0000-0000-000000000000"
        print(f" -> Simulating IDOR attempt by attacker patient '{attacker_id}'...")
        try:
            asyncio.run(get_patient_consultation(patient_id=attacker_id, consultation_id=consult_1.id, db=db))
            idor_blocked = False
        except HTTPException as he:
            idor_blocked = (he.status_code == 403)
        print(f" -> IDOR Attempt Blocked with 403: {idor_blocked}")
        assert idor_blocked, "IDOR vulnerability: consultation returned to mismatched patient ID (expected 403 Forbidden)!"

        # Draft masking check: unapproved consult_2 must mask draft from patient
        unapp_view = asyncio.run(get_patient_consultation(patient_id=patient.id, consultation_id=consult_2.id, db=db))
        print(f" -> Unapproved Consultation Patient View Status: {unapp_view.thread_status}")
        print(f" -> Draft Withheld / None: {unapp_view.final_response is None}")
        print(f" -> Patient Message: '{unapp_view.message}'")
        assert unapp_view.thread_status == "pending_review"
        assert unapp_view.final_response is None
        print(" -> PATIENT READ ENDPOINT & IDOR PROTECTION TESTS PASSED!")

        # Step 7: Doctor Queue Priority Ordering & is_eval Exclusion (P8)
        print("\n" + "=" * 70)
        print("[TEST 7] DOCTOR QUEUE PRIORITY ORDERING & IS_EVAL EXCLUSION")
        print("=" * 70)
        # Insert a temporary eval consultation
        import uuid
        eval_id = f"eval-{uuid.uuid4().hex[:8]}"
        eval_consult = Consultation(
            id=eval_id,
            patient_id=patient.id,
            query_text="Eval benchmark query",
            thread_status="awaiting_doctor",
            urgency_final="urgent",
            is_high_priority=True,
            is_eval=True,
            created_at=datetime.datetime.utcnow(),
        )
        db.add(eval_consult)
        db.commit()

        queue_items = asyncio.run(get_queue(ablation_arm=None, limit=50, offset=0, db=db))
        queue_ids = [item["id"] for item in queue_items]
        print(f" -> Total items returned in doctor queue: {len(queue_items)}")
        print(f" -> Eval consultation '{eval_id}' excluded from queue: {eval_id not in queue_ids}")
        assert eval_id not in queue_ids, "is_eval exclusion failed: eval query appeared in doctor queue!"

        # Check queue priority ordering: all 'urgent' items must appear before non-urgent items
        urgency_ranks = {"urgent": 1, "soon": 2, "routine": 3}
        queue_ranks = [urgency_ranks.get(item.get("urgency_final"), 3) for item in queue_items]
        is_sorted = all(queue_ranks[i] <= queue_ranks[i+1] for i in range(len(queue_ranks) - 1))
        print(f" -> Doctor queue urgency hierarchy strictly monotonically non-decreasing: {is_sorted}")
        assert is_sorted, f"Queue priority violated: {queue_ranks}"

        # Cleanup test eval consultation
        db.delete(eval_consult)
        db.commit()
        print(" -> DOCTOR QUEUE PRIORITY & IS_EVAL EXCLUSION TESTS PASSED!")

        print("\n" + "=" * 70)
        print("ALL PILLAR B SMOKE TESTS (P1 THROUGH P10 + SECURITY) PASSED!")
        print("=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    run_smoke_test()
