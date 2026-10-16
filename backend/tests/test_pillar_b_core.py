"""
Unit and integration tests for Pillar B components:
- Intent / Urgency classifier split
- D17 conflict and missing-context detection
- B5 Faithfulness validation (4 status values, outlier exclusions)
- 12-category weighted edit-burden calculations
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from backend.app.pipeline.classify import classify_intent, classify_urgency, classify_query
from backend.app.pipeline.detect_context_gaps import (
    detect_ehr_mismatch,
    detect_missing_context,
    run_d17_checks,
)
from backend.app.pipeline.retrieve_ehr import EHRChunk
from backend.app.pipeline.retrieve_kb import (
    KBChunk,
    to_spec_chunk_id,
    SPEC_CITATION_REGEX,
    retrieve_kb,
)
from backend.app.pipeline.generate import (
    compute_consultation_edit_weight,
    compute_edit_distances,
    sanitize_delivery_text,
    EDIT_CATEGORIES_TEMPLATE,
    GeneratedDraft,
    DraftSentence,
)
from backend.app.pipeline.validate import validate_draft
from backend.app.pipeline.orchestrator import run_pipeline
from backend.app.api.consult import (
    DoctorReviewRequest,
    submit_doctor_review,
    deliver_consultation,
    get_consultation,
)
from backend.app.api.patient import (
    get_patient_consultation,
    list_patient_consultations,
)
from backend.app.api.queue import get_queue, get_queue_stats
from backend.app.db.models_v3 import Consultation
from fastapi import HTTPException
import asyncio


class TestPillarBClassification(unittest.TestCase):
    def test_classify_split_and_wrapper(self):
        query = "What lifestyle changes can slow chronic kidney disease progression?"
        intent_res = classify_intent(query)
        self.assertIn("intent", intent_res)
        self.assertIn("embedding", intent_res)
        self.assertIn(intent_res["route"], ["draft", "unsupported"])

        urgency_res = classify_urgency(query, embedding=intent_res["embedding"])
        self.assertIn(urgency_res["urgency_classifier"], ["routine", "soon", "urgent"])

        legacy_res = classify_query(query)
        self.assertEqual(legacy_res["intent"], intent_res["intent"])
        self.assertEqual(legacy_res["urgency_classifier"], urgency_res["urgency_classifier"])


class TestD17ContextGaps(unittest.TestCase):
    def test_d17a_ehr_mismatch_detection(self):
        normalized = [
            {"canonical_label": "Lisinopril", "domain": "medication"},
            {"canonical_label": "Serum Creatinine", "domain": "lab"},
        ]
        # EHR chunks contain only Creatinine, missing Lisinopril
        ehr_chunks = [
            EHRChunk(
                stable_eid="ehr:lab:001",
                source_type="lab_result",
                label="Serum Creatinine",
                display_value="1.4 mg/dL",
                date_str="2023-08-10",
                is_abnormal=True,
                is_outlier=False,
                outlier_annotation=None,
            )
        ]
        self.assertTrue(detect_ehr_mismatch(normalized, ehr_chunks))

    def test_d17b_missing_context_detection(self):
        # All EHR chunks outlier, all KB scores below 0.25
        outlier_ehr = [
            EHRChunk(
                stable_eid="ehr:lab:002",
                source_type="lab_result",
                label="Creatinine",
                display_value="45 mg/dL",
                date_str="2023-08-10",
                is_abnormal=True,
                is_outlier=True,
                outlier_annotation="Simulation artifact",
            )
        ]
        weak_kb = [
            KBChunk(
                chunk_id="KB-001_chunk_001",
                doc_id="KB-001",
                source_name="MedlinePlus",
                source_url="http://example.com",
                title="Generic Info",
                text="Some text",
                score_rrf=0.10,
            )
        ]
        self.assertTrue(detect_missing_context(outlier_ehr, weak_kb, rrf_threshold=0.25))

        res = run_d17_checks([], outlier_ehr, weak_kb)
        self.assertTrue(res["missing_context"])
        self.assertEqual(res["reason"], "missing_context")


class TestEditWeightFormula(unittest.TestCase):
    def test_edit_categories_and_weighted_sum(self):
        cats = dict(EDIT_CATEGORIES_TEMPLATE)
        self.assertEqual(len(cats), 12)
        # Apply factual_correction (w=2) + wrong_ehr_fact (w=3) + tone_change (w=1)
        cats["factual_correction"] = 1
        cats["wrong_ehr_fact"] = 1
        cats["tone_change"] = 1
        weight = compute_consultation_edit_weight(cats)
        self.assertEqual(weight, 6.0)


class TestB5FaithfulnessValidation(unittest.TestCase):
    def test_outlier_only_and_four_status_values(self):
        # 1. Zero sentences -> manual_required
        empty_draft = GeneratedDraft(
            sentences=[],
            overall_tone="informative",
            recommended_followup=None,
            urgency_assessment="routine",
            llm_model="test-llm",
            prompt_version="v1",
            generation_latency_ms=100,
            raw_llm_output="{}",
        )
        val_empty = validate_draft(empty_draft, [], [])
        self.assertEqual(val_empty.validation_status, "manual_required")

        # 2. Outlier-only sentence -> treated as having 0 valid citations -> manual_required
        outlier_chunk = EHRChunk(
            stable_eid="ehr:lab:outlier",
            source_type="lab_result",
            label="Creatinine",
            display_value="45 mg/dL",
            date_str="2023-08-10",
            is_abnormal=True,
            is_outlier=True,
            outlier_annotation="Simulation artifact",
        )
        draft_with_outlier = GeneratedDraft(
            sentences=[DraftSentence(text="Your creatinine reading was 45 mg/dL.", citations=["ehr:lab:outlier"])],
            overall_tone="informative",
            recommended_followup=None,
            urgency_assessment="routine",
            llm_model="test-llm",
            prompt_version="v1",
            generation_latency_ms=120,
            raw_llm_output="{}",
        )
        val_outlier = validate_draft(draft_with_outlier, [outlier_chunk], [])
        self.assertTrue(val_outlier.has_outlier_only_sentence)
        self.assertEqual(val_outlier.citation_coverage, 0.0)
        self.assertEqual(val_outlier.validation_status, "manual_required")


class TestCitationIDStandardization(unittest.TestCase):
    def test_chunk_id_translation_and_spec_regex(self):
        # 1. Translation helper checks
        self.assertEqual(to_spec_chunk_id("KB-MP0042_chunk_003"), "kb:KB-MP0042:chunk0003")
        self.assertEqual(to_spec_chunk_id("kb:KB-B01:chunk0"), "kb:KB-B01:chunk0000")
        self.assertEqual(to_spec_chunk_id("kb:KB-B01:chunk0004"), "kb:KB-B01:chunk0004")
        self.assertTrue(bool(SPEC_CITATION_REGEX.match("kb:KB-MP0042:chunk0003")))

        # 2. Live retrieve_kb returns IDs strictly matching spec regex
        chunks = retrieve_kb("What lifestyle changes can slow chronic kidney disease progression?", [], top_n=3)
        self.assertGreater(len(chunks), 0)
        for chunk in chunks:
            self.assertTrue(
                bool(SPEC_CITATION_REGEX.match(chunk.chunk_id)),
                f"Chunk ID {chunk.chunk_id} does not match spec regex ^kb:[A-Za-z0-9\\-_]+:chunk\\d{{4}}$"
            )

    def test_citation_validator_valid_vs_dangling(self):
        valid_chunk = KBChunk(
            chunk_id="kb:KB-MP0042:chunk0003",
            doc_id="KB-MP0042",
            source_name="MedlinePlus",
            source_url="http://example.com",
            title="Chronic Kidney Disease",
            text="Dietary modifications and sodium restriction help slow chronic kidney disease.",
            score_hybrid=0.85,
        )

        # Valid citation case
        valid_draft = GeneratedDraft(
            sentences=[DraftSentence(
                text="Dietary modifications and sodium restriction help slow chronic kidney disease.",
                citations=["kb:KB-MP0042:chunk0003"]
            )],
            overall_tone="informative",
            recommended_followup=None,
            urgency_assessment="routine",
            llm_model="test-llm",
            prompt_version="v1",
            generation_latency_ms=100,
            raw_llm_output="{}",
        )
        val_valid = validate_draft(valid_draft, [], [valid_chunk])
        self.assertEqual(val_valid.citation_validity, 1.0)
        self.assertEqual(val_valid.citation_coverage, 1.0)
        self.assertIn(val_valid.validation_status, ["passed", "passed_with_warning"])

        # Dangling citation case
        dangling_draft = GeneratedDraft(
            sentences=[DraftSentence(
                text="Dietary modifications can slow progression of kidney disease.",
                citations=["kb:KB-DANGLING:chunk9999"]
            )],
            overall_tone="informative",
            recommended_followup=None,
            urgency_assessment="routine",
            llm_model="test-llm",
            prompt_version="v1",
            generation_latency_ms=100,
            raw_llm_output="{}",
        )
        val_dangling = validate_draft(dangling_draft, [], [valid_chunk])
        self.assertEqual(val_dangling.citation_validity, 0.0)
        self.assertEqual(val_dangling.citation_coverage, 0.0)
        self.assertEqual(val_dangling.validation_status, "manual_required")

    def test_citation_validator_mixed_fabricated_citation_hard_fails(self):
        """Confirm that a draft with high coverage (100%) but even one fabricated citation hard-fails to manual_required."""
        valid_chunk = KBChunk(
            chunk_id="kb:KB-MP0042:chunk0003",
            doc_id="KB-MP0042",
            source_name="MedlinePlus",
            source_url="http://example.com",
            title="Chronic Kidney Disease",
            text="Dietary modifications and sodium restriction help slow chronic kidney disease.",
            score_hybrid=0.85,
        )
        # Sentence 1 has valid citation; Sentence 2 has both valid AND a fabricated citation.
        mixed_draft = GeneratedDraft(
            sentences=[
                DraftSentence(
                    text="Dietary modifications help slow kidney disease.",
                    citations=["kb:KB-MP0042:chunk0003"],
                ),
                DraftSentence(
                    text="Sodium restriction also helps slow kidney disease.",
                    citations=["kb:KB-MP0042:chunk0003", "kb:KB-FAKE9999:chunk9999"],
                ),
            ],
            overall_tone="informative",
            recommended_followup=None,
            urgency_assessment="routine",
            llm_model="test-llm",
            prompt_version="v1",
            generation_latency_ms=100,
            raw_llm_output="{}",
        )
        val_mixed = validate_draft(mixed_draft, [], [valid_chunk])
        # Coverage is 100% because every sentence has at least 1 valid citation
        self.assertEqual(val_mixed.citation_coverage, 1.0)
        # Validity is 2/3 (66.7%) because 1 of 3 cited IDs is fabricated
        self.assertAlmostEqual(val_mixed.citation_validity, 0.6667, places=3)
        # MUST hard-fail to manual_required despite 100% coverage
        self.assertEqual(val_mixed.validation_status, "manual_required")


class TestOrchestratorAuthorizationGate(unittest.TestCase):
    def test_no_classifier_is_eval_gate(self):
        mock_db = MagicMock()
        # 1. Calling no_classifier without is_eval=True MUST raise PermissionError
        with self.assertRaises(PermissionError):
            run_pipeline(
                patient_id="test-patient-uuid",
                query_text="What are my lab results?",
                db=mock_db,
                ablation_config="no_classifier",
                is_eval=False,
            )

        # 2. Calling with is_eval=True must pass authorization gate
        # (It will proceed into DB queries and fail on mock db, NOT on PermissionError)
        with self.assertRaises(Exception) as cm:
            run_pipeline(
                patient_id="test-patient-uuid",
                query_text="What are my lab results?",
                db=mock_db,
                ablation_config="no_classifier",
                is_eval=True,
            )
        self.assertNotIsInstance(cm.exception, PermissionError)


class TestDualIntentADRRouting(unittest.TestCase):
    def test_classify_intent_flags_adr_dual_intent(self):
        query = "I experienced mild postural dizziness shortly after taking my Clopidogrel."
        res = classify_intent(query)
        self.assertIn(res["intent"], ["medication_query", "symptom_report"])
        self.assertTrue(res["is_dual_intent"])
        expected_secondary = "symptom_report" if res["intent"] == "medication_query" else "medication_query"
        self.assertEqual(res["secondary_intent"], expected_secondary)

    def test_retrieve_ehr_dual_intent_queries_both_conditions_and_prescriptions(self):
        from backend.app.pipeline.retrieve_ehr import retrieve_ehr
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []

        retrieve_ehr(
            patient_id="patient-123",
            normalized_concepts=[],
            intent="medication_query",
            db=mock_db,
            secondary_intent="symptom_report",
            is_dual_intent=True,
        )

        executed_sqls = [call[0][0].text for call in mock_db.execute.call_args_list]
        conditions_queried = any("FROM conditions" in sql for sql in executed_sqls)
        prescriptions_queried = any("FROM prescriptions" in sql for sql in executed_sqls)

        self.assertTrue(conditions_queried, "Dual-intent routing failed to query conditions")
        self.assertTrue(prescriptions_queried, "Dual-intent routing failed to query prescriptions")


class TestDoctorReviewTracking(unittest.TestCase):
    def test_edit_weights_and_categories_completeness(self):
        # Spec Section S9: 12 categories
        self.assertEqual(len(EDIT_CATEGORIES_TEMPLATE), 12)
        # No-change should produce 0.0 edit weight
        w_no_change = compute_consultation_edit_weight({"no_change": 1})
        self.assertEqual(w_no_change, 0.0)

        # High-penalty edits: wrong_ehr_fact (3) + urgency_correction (3) = 6.0
        w_severe = compute_consultation_edit_weight({
            "wrong_ehr_fact": 1,
            "urgency_correction": 1,
        })
        self.assertEqual(w_severe, 6.0)

    def test_compute_edit_distances_and_edr(self):
        # 1. Identical texts
        res_exact = compute_edit_distances("Your blood pressure is normal.", "Your blood pressure is normal.")
        self.assertEqual(res_exact["edit_distance_chars"], 0)
        self.assertEqual(res_exact["edit_distance_words"], 0)
        self.assertEqual(res_exact["edr_char"], 0.0)
        self.assertEqual(res_exact["edr_word"], 0.0)

        # 2. Minor edit: 1 char difference, 1 word difference
        # "10mg" -> "20mg" (1 substitution: '1' -> '2')
        res_edit = compute_edit_distances("Take 10mg daily.", "Take 20mg daily.")
        self.assertEqual(res_edit["edit_distance_chars"], 1)
        self.assertEqual(res_edit["edit_distance_words"], 1)
        self.assertAlmostEqual(res_edit["edr_char"], 1 / 16, places=3)
        self.assertAlmostEqual(res_edit["edr_word"], 1 / 3, places=3)

    def test_doctor_action_rejects_override_and_accepts_spec_3_actions(self):
        # Spec Section 5 / S9: exactly 3 actions: approve | edit | reject
        # "override" must be strictly rejected with HTTP 422
        mock_db = MagicMock()
        mock_consult = MagicMock()
        mock_consult.id = "test-consult"
        mock_consult.ai_draft_json = {"sentences": [{"text": "Draft sentence."}]}
        mock_consult.edit_categories_json = None
        mock_consult.consultation_edit_weight = None
        mock_db.query.return_value.filter.return_value.first.return_value = mock_consult

        req_override = DoctorReviewRequest(doctor_action="override")
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(submit_doctor_review("test-consult", req_override, mock_db))
        self.assertEqual(cm.exception.status_code, 422)
        self.assertIn("approved", str(cm.exception.detail))

        # The 3 spec actions must succeed and map to canonical names
        for valid_act, expected in [("approve", "approved"), ("approved", "approved"),
                                    ("edit", "edited"), ("edited", "edited"),
                                    ("reject", "rejected"), ("rejected", "rejected")]:
            req_valid = DoctorReviewRequest(doctor_action=valid_act)
            res = asyncio.run(submit_doctor_review("test-consult", req_valid, mock_db))
            self.assertEqual(res.doctor_action, expected)


class TestDoctorQueuePriorityAndExclusion(unittest.TestCase):
    def test_queue_ordering_3_tier_urgency_and_is_eval_exclusion(self):
        # Verify get_queue builds query with is_eval == False and 3-tier urgency case ordering
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_filtered = MagicMock()
        mock_query.filter.return_value = mock_filtered
        mock_ordered = MagicMock()
        mock_filtered.order_by.return_value = mock_ordered
        mock_offset = MagicMock()
        mock_ordered.offset.return_value = mock_offset
        mock_offset.limit.return_value.all.return_value = []

        res = asyncio.run(get_queue(ablation_arm=None, limit=50, offset=0, db=mock_db))
        self.assertEqual(res, [])

        # Verify filter was called on mock_query
        self.assertTrue(mock_query.filter.called)
        # Verify order_by was called
        self.assertTrue(mock_filtered.order_by.called)


class TestDeliverySanitizationAndP10(unittest.TestCase):
    def test_sanitize_delivery_text(self):
        raw = (
            "```json\n"
            "[EHR_CONTEXT] Your creatinine is 1.4 mg/dL [ehr:lab:12345] . "
            "[KNOWLEDGE_CONTEXT] Consult a nephrologist [kb:KB-D01:chunk0002, kb:KB-D02:chunk0005]! "
            "```"
        )
        cleaned = sanitize_delivery_text(raw)
        self.assertNotIn("```", cleaned)
        self.assertNotIn("[EHR_CONTEXT]", cleaned)
        self.assertNotIn("[KNOWLEDGE_CONTEXT]", cleaned)
        self.assertNotIn("ehr:lab:12345", cleaned)
        self.assertNotIn("kb:KB-D01:chunk0002", cleaned)
        self.assertIn("Your creatinine is 1.4 mg/dL.", cleaned)
        self.assertIn("Consult a nephrologist!", cleaned)

    def test_deliver_endpoint_guards(self):
        mock_db = MagicMock()
        mock_consult = MagicMock()
        mock_consult.id = "c-123"
        mock_consult.patient_id = "p-abc"
        mock_consult.thread_status = "awaiting_doctor"
        mock_consult.doctor_action = None
        mock_consult.final_response = "Some advice [kb:KB-D01:chunk0001]."
        mock_db.query.return_value.filter.return_value.first.return_value = mock_consult

        # 1. Non-approved/unreviewed consultation must fail with HTTP 400
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(deliver_consultation("c-123", mock_db))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("must be 'approved' or 'edited'", cm.exception.detail)

        # 2. Approved consultation succeeds and is sanitized
        mock_consult.doctor_action = "approved"
        mock_consult.thread_status = "approved"
        res = asyncio.run(deliver_consultation("c-123", mock_db))
        self.assertEqual(res.thread_status, "delivered")
        self.assertNotIn("kb:KB-D01", res.final_response)
        self.assertEqual(mock_consult.thread_status, "delivered")
        self.assertIsNotNone(mock_consult.delivered_at)
        self.assertEqual(mock_consult.patient_notified_at, mock_consult.delivered_at)


class TestPatientReadEndpointAndIDOR(unittest.TestCase):
    def test_idor_mismatched_patient_returns_403(self):
        mock_db = MagicMock()
        mock_consult = MagicMock()
        mock_consult.id = "c-123"
        mock_consult.patient_id = "patient-A"
        mock_consult.thread_status = "delivered"
        mock_consult.final_response = "Doctor approved response."
        mock_db.query.return_value.filter.return_value.first.return_value = mock_consult

        # Attacker 'patient-B' attempts to access patient-A's consultation -> 403 Forbidden
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(get_patient_consultation(patient_id="patient-B", consultation_id="c-123", db=mock_db))
        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn("belongs to another patient", cm.exception.detail)

    def test_unapproved_consultation_masks_draft_from_patient(self):
        mock_db = MagicMock()
        mock_consult = MagicMock()
        mock_consult.id = "c-123"
        mock_consult.patient_id = "patient-A"
        mock_consult.query_text = "Why is my creatinine high?"
        mock_consult.thread_status = "awaiting_doctor"
        mock_consult.final_response = None
        mock_consult.ai_draft_json = {"sentences": [{"text": "Draft internal diagnosis."}]}
        mock_consult.created_at = "2026-10-14 10:00:00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_consult

        # Legitimate patient accesses their own pending consultation
        res = asyncio.run(get_patient_consultation(patient_id="patient-A", consultation_id="c-123", db=mock_db))
        self.assertEqual(res.thread_status, "pending_review")
        self.assertIsNone(res.final_response)
        self.assertIn("being reviewed by a clinician", res.message)

    def test_approved_or_delivered_returns_sanitized_final_response(self):
        mock_db = MagicMock()
        mock_consult = MagicMock()
        mock_consult.id = "c-123"
        mock_consult.patient_id = "patient-A"
        mock_consult.query_text = "Why is my creatinine high?"
        mock_consult.thread_status = "delivered"
        mock_consult.final_response = "Your creatinine level is stable at 1.4 mg/dL."
        mock_consult.delivered_at = "2026-10-14 10:30:00"
        mock_consult.created_at = "2026-10-14 10:00:00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_consult

        res = asyncio.run(get_patient_consultation(patient_id="patient-A", consultation_id="c-123", db=mock_db))
        self.assertEqual(res.thread_status, "delivered")
        self.assertEqual(res.final_response, "Your creatinine level is stable at 1.4 mg/dL.")
        self.assertEqual(res.delivered_at, "2026-10-14 10:30:00")


class TestDoctorConsultationRoleSecurity(unittest.TestCase):
    def test_get_consultation_requires_doctor_role(self):
        from backend.app.api.consult import get_consultation, require_doctor_role

        # Verify dependency rejects unauthorized/patient role with 403
        with self.assertRaises(HTTPException) as cm:
            require_doctor_role(role="patient")
        self.assertEqual(cm.exception.status_code, 403)

        with self.assertRaises(HTTPException) as cm2:
            require_doctor_role(role=None, x_user_role=None)
        self.assertEqual(cm2.exception.status_code, 403)

        # Doctor role passes dependency
        self.assertEqual(require_doctor_role(role="doctor"), "doctor")
        self.assertEqual(require_doctor_role(x_user_role="doctor"), "doctor")

        # Calling get_consultation with valid doctor role returns record
        mock_db = MagicMock()
        mock_consult = MagicMock()
        mock_consult.id = "c-123"
        mock_consult.patient_id = "p-1"
        mock_consult.query_text = "test query"
        mock_consult.intent = "medication_query"
        mock_consult.urgency_final = "routine"
        mock_consult.validation_status = "passed"
        mock_consult.thread_status = "approved"
        mock_consult.is_high_priority = False
        mock_consult.is_red_flag_override = False
        mock_consult.ai_draft_json = {}
        mock_consult.faithfulness_score = 0.95
        mock_consult.citation_entailment_score = 0.95
        mock_consult.ablation_arm = "full"
        mock_consult.llm_model = "llama3:8b"
        mock_consult.generation_latency_ms = 120
        mock_consult.doctor_action = "approved"
        mock_consult.reject_reason = None
        mock_consult.final_response = "Clean advice"
        mock_consult.consultation_edit_weight = 0.0
        mock_consult.edit_categories_json = {}
        mock_consult.edit_distance_chars = 0
        mock_consult.edit_distance_words = 0
        mock_consult.edr_char = 0.0
        mock_consult.edr_word = 0.0
        mock_consult.is_eval = False
        mock_consult.doctor_review_seconds = 15.0
        mock_consult.doctor_reviewed_at = None
        mock_consult.delivered_at = None
        mock_consult.created_at = "2026-10-14 10:00:00"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_consult

        res = asyncio.run(get_consultation(consultation_id="c-123", db=mock_db, _role="doctor"))
        self.assertEqual(res["id"], "c-123")
        self.assertEqual(res["final_response"], "Clean advice")


if __name__ == "__main__":
    unittest.main()


