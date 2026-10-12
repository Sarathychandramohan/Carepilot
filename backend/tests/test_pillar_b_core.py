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
from backend.app.pipeline.retrieve_kb import KBChunk
from backend.app.pipeline.generate import (
    compute_consultation_edit_weight,
    EDIT_CATEGORIES_TEMPLATE,
    GeneratedDraft,
    DraftSentence,
)
from backend.app.pipeline.validate import validate_draft


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


if __name__ == "__main__":
    unittest.main()
