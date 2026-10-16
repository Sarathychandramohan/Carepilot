"""
backend/tests/test_skip_reasons.py

Unit tests for consultation.skip_reason persistence in the orchestrator pipeline.
Covers all skip branches:
  1. 'emergency'               : Firm red flag emergency gate
  2. 'unsupported_intent'      : Administrative / billing unsupported intent gate
  3. 'generation_parse_failed' : LLM draft JSON parse failure
  4. 'validation_failed'       : Faithfulness validation manual_required
  5. None                      : Standard successful consultation generation
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.app.pipeline.orchestrator import run_pipeline
from backend.app.pipeline.generate import GeneratedDraft, DraftSentence
from backend.app.pipeline.validate import ValidationResult


class TestPipelineSkipReasons(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        # Mock patient context query
        self.mock_db.execute.return_value.fetchone.return_value = None

    @patch("backend.app.pipeline.orchestrator.evaluate_red_flags")
    def test_skip_reason_emergency(self, mock_rf):
        mock_rf.return_value = {
            "has_firm_hit": True,
            "hit_type": "firm",
            "primary_category": "chest_pain",
            "soft_hits": [],
        }
        consult = run_pipeline(
            patient_id="test-p1",
            query_text="I have severe crushing chest pain radiating to my arm",
            db=self.mock_db,
        )
        self.assertEqual(consult.skip_reason, "emergency")
        self.assertEqual(consult.validation_status, "manual_required")
        self.assertEqual(consult.thread_status, "awaiting_doctor")
        self.assertTrue(consult.is_high_priority)
        self.assertTrue(consult.is_red_flag_override)

    @patch("backend.app.pipeline.orchestrator.evaluate_red_flags")
    @patch("backend.app.pipeline.orchestrator.classify_intent")
    def test_skip_reason_unsupported_intent(self, mock_intent, mock_rf):
        mock_rf.return_value = {"has_firm_hit": False, "hit_type": "none", "primary_category": None, "soft_hits": []}
        mock_intent.return_value = {
            "intent": "admin_billing_insurance",
            "route": "unsupported",
            "intent_confidence": 0.95,
            "intent_probs": {"admin_billing_insurance": 0.95},
            "embedding": [0.0] * 384,
        }
        consult = run_pipeline(
            patient_id="test-p2",
            query_text="How much does my health insurance copay cost?",
            db=self.mock_db,
        )
        self.assertEqual(consult.skip_reason, "unsupported_intent")
        self.assertEqual(consult.validation_status, "manual_required")
        self.assertEqual(consult.thread_status, "awaiting_doctor")
        self.assertFalse(consult.is_high_priority)

    @patch("backend.app.pipeline.orchestrator.evaluate_red_flags")
    @patch("backend.app.pipeline.orchestrator.classify_intent")
    @patch("backend.app.pipeline.orchestrator.classify_urgency")
    @patch("backend.app.pipeline.orchestrator.retrieve_ehr")
    @patch("backend.app.pipeline.orchestrator.retrieve_kb")
    @patch("backend.app.pipeline.orchestrator.run_d17_checks")
    @patch("backend.app.pipeline.orchestrator.generate_draft")
    def test_skip_reason_generation_parse_failed(
        self, mock_gen, mock_d17, mock_kb, mock_ehr, mock_urg, mock_intent, mock_rf
    ):
        mock_rf.return_value = {"has_firm_hit": False, "hit_type": "none", "primary_category": None, "soft_hits": []}
        mock_intent.return_value = {
            "intent": "medication_query",
            "route": "draft",
            "intent_confidence": 0.90,
            "intent_probs": {"medication_query": 0.90},
            "embedding": [0.0] * 384,
        }
        mock_urg.return_value = {
            "urgency_classifier": "routine",
            "urgency_score": 0.1,
            "urgency_probs": {"routine": 0.9},
        }
        mock_ehr.return_value = []
        mock_kb.return_value = []
        mock_d17.return_value = {"manual_required": False, "patient_ehr_mismatch": False, "missing_context": False, "reason": None}
        mock_gen.return_value = None  # Simulates JSON parse failure on retries

        consult = run_pipeline(
            patient_id="test-p3",
            query_text="When should I take my lisinopril?",
            db=self.mock_db,
        )
        self.assertEqual(consult.skip_reason, "generation_parse_failed")
        self.assertEqual(consult.validation_status, "manual_required")

    @patch("backend.app.pipeline.orchestrator.evaluate_red_flags")
    @patch("backend.app.pipeline.orchestrator.classify_intent")
    @patch("backend.app.pipeline.orchestrator.classify_urgency")
    @patch("backend.app.pipeline.orchestrator.retrieve_ehr")
    @patch("backend.app.pipeline.orchestrator.retrieve_kb")
    @patch("backend.app.pipeline.orchestrator.run_d17_checks")
    @patch("backend.app.pipeline.orchestrator.generate_draft")
    @patch("backend.app.pipeline.orchestrator.validate_draft")
    def test_skip_reason_validation_failed(
        self, mock_val, mock_gen, mock_d17, mock_kb, mock_ehr, mock_urg, mock_intent, mock_rf
    ):
        mock_rf.return_value = {"has_firm_hit": False, "hit_type": "none", "primary_category": None, "soft_hits": []}
        mock_intent.return_value = {
            "intent": "medication_query",
            "route": "draft",
            "intent_confidence": 0.90,
            "intent_probs": {"medication_query": 0.90},
            "embedding": [0.0] * 384,
        }
        mock_urg.return_value = {
            "urgency_classifier": "routine",
            "urgency_score": 0.1,
            "urgency_probs": {"routine": 0.9},
        }
        mock_ehr.return_value = []
        mock_kb.return_value = []
        mock_d17.return_value = {"manual_required": False, "patient_ehr_mismatch": False, "missing_context": False, "reason": None}

        # Mock draft
        mock_draft = GeneratedDraft(
            sentences=[DraftSentence(text="Take lisinopril once daily.", citations=[])],
            overall_tone="informative",
            recommended_followup=None,
            urgency_assessment="routine",
            llm_model="qwen3:8b",
            prompt_version="v1",
            generation_latency_ms=850,
            raw_llm_output="{}",
        )
        mock_gen.return_value = mock_draft

        # Mock validation failure
        mock_val.return_value = ValidationResult(
            citation_coverage=0.20,
            citation_validity=0.50,
            avg_nli_entailment=0.10,
            validation_status="manual_required",
            has_outlier_only_sentence=False,
            per_sentence=[],
        )

        consult = run_pipeline(
            patient_id="test-p4",
            query_text="When should I take my lisinopril?",
            db=self.mock_db,
        )
        self.assertEqual(consult.skip_reason, "validation_failed")
        self.assertEqual(consult.validation_status, "manual_required")

    @patch("backend.app.pipeline.orchestrator.evaluate_red_flags")
    @patch("backend.app.pipeline.orchestrator.classify_intent")
    @patch("backend.app.pipeline.orchestrator.classify_urgency")
    @patch("backend.app.pipeline.orchestrator.retrieve_ehr")
    @patch("backend.app.pipeline.orchestrator.retrieve_kb")
    @patch("backend.app.pipeline.orchestrator.run_d17_checks")
    @patch("backend.app.pipeline.orchestrator.generate_draft")
    @patch("backend.app.pipeline.orchestrator.validate_draft")
    def test_normal_pipeline_skip_reason_is_none(
        self, mock_val, mock_gen, mock_d17, mock_kb, mock_ehr, mock_urg, mock_intent, mock_rf
    ):
        mock_rf.return_value = {"has_firm_hit": False, "hit_type": "none", "primary_category": None, "soft_hits": []}
        mock_intent.return_value = {
            "intent": "medication_query",
            "route": "draft",
            "intent_confidence": 0.90,
            "intent_probs": {"medication_query": 0.90},
            "embedding": [0.0] * 384,
        }
        mock_urg.return_value = {
            "urgency_classifier": "routine",
            "urgency_score": 0.1,
            "urgency_probs": {"routine": 0.9},
        }
        mock_ehr.return_value = []
        mock_kb.return_value = []
        mock_d17.return_value = {"manual_required": False, "patient_ehr_mismatch": False, "missing_context": False, "reason": None}

        mock_draft = GeneratedDraft(
            sentences=[DraftSentence(text="Take lisinopril once daily in the morning.", citations=["ehr:rx:1"])],
            overall_tone="informative",
            recommended_followup=None,
            urgency_assessment="routine",
            llm_model="qwen3:8b",
            prompt_version="v1",
            generation_latency_ms=920,
            raw_llm_output="{}",
        )
        mock_gen.return_value = mock_draft

        mock_val.return_value = ValidationResult(
            citation_coverage=1.0,
            citation_validity=1.0,
            avg_nli_entailment=0.92,
            validation_status="passed",
            has_outlier_only_sentence=False,
            per_sentence=[],
        )

        consult = run_pipeline(
            patient_id="test-p5",
            query_text="When should I take my lisinopril?",
            db=self.mock_db,
        )
        self.assertIsNone(consult.skip_reason)
        self.assertEqual(consult.validation_status, "passed")
        self.assertEqual(consult.thread_status, "awaiting_doctor")

    @patch("backend.app.pipeline.orchestrator.evaluate_red_flags")
    @patch("backend.app.pipeline.orchestrator.classify_intent")
    @patch("backend.app.pipeline.orchestrator.classify_urgency")
    @patch("backend.app.pipeline.orchestrator.retrieve_ehr")
    @patch("backend.app.pipeline.orchestrator.retrieve_kb")
    @patch("backend.app.pipeline.orchestrator.run_d17_checks")
    def test_skip_reason_ehr_mismatch(
        self, mock_d17, mock_kb, mock_ehr, mock_urg, mock_intent, mock_rf
    ):
        mock_rf.return_value = {"has_firm_hit": False, "hit_type": "none", "primary_category": None, "soft_hits": []}
        mock_intent.return_value = {
            "intent": "medication_query",
            "route": "draft",
            "intent_confidence": 0.90,
            "intent_probs": {"medication_query": 0.90},
            "embedding": [0.0] * 384,
        }
        mock_urg.return_value = {
            "urgency_classifier": "routine",
            "urgency_score": 0.1,
            "urgency_probs": {"routine": 0.9},
        }
        mock_ehr.return_value = []
        mock_kb.return_value = []
        mock_d17.return_value = {
            "manual_required": True,
            "patient_ehr_mismatch": True,
            "missing_context": False,
            "reason": "ehr_mismatch",
        }

        consult = run_pipeline(
            patient_id="test-p6",
            query_text="What is my dose of Lisinopril?",
            db=self.mock_db,
        )
        self.assertEqual(consult.skip_reason, "ehr_mismatch")
        self.assertEqual(consult.validation_status, "manual_required")
        self.assertTrue(consult.patient_ehr_mismatch_flag)

    @patch("backend.app.pipeline.orchestrator.evaluate_red_flags")
    @patch("backend.app.pipeline.orchestrator.classify_intent")
    @patch("backend.app.pipeline.orchestrator.classify_urgency")
    @patch("backend.app.pipeline.orchestrator.retrieve_ehr")
    @patch("backend.app.pipeline.orchestrator.retrieve_kb")
    @patch("backend.app.pipeline.orchestrator.run_d17_checks")
    def test_skip_reason_missing_context(
        self, mock_d17, mock_kb, mock_ehr, mock_urg, mock_intent, mock_rf
    ):
        mock_rf.return_value = {"has_firm_hit": False, "hit_type": "none", "primary_category": None, "soft_hits": []}
        mock_intent.return_value = {
            "intent": "general_health_info",
            "route": "draft",
            "intent_confidence": 0.90,
            "intent_probs": {"general_health_info": 0.90},
            "embedding": [0.0] * 384,
        }
        mock_urg.return_value = {
            "urgency_classifier": "routine",
            "urgency_score": 0.1,
            "urgency_probs": {"routine": 0.9},
        }
        mock_ehr.return_value = []
        mock_kb.return_value = []
        mock_d17.return_value = {
            "manual_required": True,
            "patient_ehr_mismatch": False,
            "missing_context": True,
            "reason": "missing_context",
        }

        consult = run_pipeline(
            patient_id="test-p7",
            query_text="Explain rare disease xyz.",
            db=self.mock_db,
        )
        self.assertEqual(consult.skip_reason, "missing_context")
        self.assertEqual(consult.validation_status, "manual_required")
        self.assertTrue(consult.missing_context_flag)


if __name__ == "__main__":
    unittest.main()
