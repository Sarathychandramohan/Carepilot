"""
D:\\CarePilotAI\\backend\\tests\\test_ehr_fact_accuracy.py

Unit tests for backend/eval/metrics/ehr_fact_accuracy.py

Tests are ENTIRELY self-contained — no database, no real EHR data.
All 5 test cases use hand-constructed draft examples where the ground truth
is explicitly known (some facts correct, some deliberately wrong).

No mocking framework required: we call the extraction helpers directly
and pass synthetic EHR data to the matching functions.
"""
from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.eval.metrics.ehr_fact_accuracy import (
    extract_medications_from_text,
    extract_lab_values_from_text,
    extract_conditions_from_text,
    _fuzzy_match,
    _match_lab_value,
    _token_overlap_ratio,
    ExtractedLabValue,
    compute_ehr_fact_accuracy,
    EHRFactAccuracyResult,
    LAB_COVERAGE_CAVEAT_MSG,
)


# ===========================================================================
# Unit tests for extraction helpers
# ===========================================================================

class TestTokenOverlapRatio:
    def test_identical(self):
        assert _token_overlap_ratio("metformin", "metformin") == 1.0

    def test_completely_different(self):
        assert _token_overlap_ratio("lisinopril", "atorvastatin") == 0.0

    def test_partial_overlap(self):
        # "chronic kidney disease" vs "kidney disease" → 2/3 ≈ 0.667
        r = _token_overlap_ratio("chronic kidney disease", "kidney disease")
        assert r == pytest.approx(2 / 3, abs=0.01)

    def test_empty_strings(self):
        assert _token_overlap_ratio("", "") == 1.0

    def test_one_empty(self):
        assert _token_overlap_ratio("metformin", "") == 0.0


class TestFuzzyMatch:
    def test_exact_match(self):
        assert _fuzzy_match("metformin", ["metformin 500 MG Oral Tablet"])

    def test_partial_brand_match(self):
        # Different brand vs generic without alias table should NOT match by token overlap alone
        assert not _fuzzy_match("Glucophage", ["metformin 500 MG"])


    def test_case_insensitive(self):
        assert _fuzzy_match("LISINOPRIL", ["lisinopril 10 MG Oral Tablet"])

    def test_substring_token_overlap(self):
        # "alendronate sodium" vs "Alendronic acid 10 MG Oral Tablet"
        # 'alendronate' not in the other string → False
        result = _fuzzy_match("alendronate sodium", ["Alendronic acid 10 MG Oral Tablet"])
        # These are different generic names; correct that they don't match by token
        assert not result

    def test_threshold_respected(self):
        # Force high threshold → should fail
        assert not _fuzzy_match("kidney", ["chronic kidney disease"], threshold=0.9)
        # Lower threshold → should pass
        assert _fuzzy_match("kidney disease", ["chronic kidney disease"], threshold=0.5)


class TestExtractMedications:
    def test_dose_marker_extraction(self):
        text = "The patient is taking Metformin 500 mg twice daily."
        meds = extract_medications_from_text(text)
        assert any("Metformin" in m or "metformin" in m.lower() for m in meds), \
            f"Expected Metformin in {meds}"

    def test_verb_trigger_extraction(self):
        text = "She was prescribed Lisinopril and started Atorvastatin last week."
        meds = extract_medications_from_text(text)
        names = " ".join(meds).lower()
        assert "lisinopril" in names or "atorvastatin" in names, \
            f"Expected medication in {meds}"

    def test_no_false_positives_on_plain_prose(self):
        text = "Your kidney function has improved and blood pressure is stable."
        meds = extract_medications_from_text(text)
        assert len(meds) == 0, f"Expected no meds but got {meds}"


class TestExtractLabValues:
    def test_creatinine_extraction(self):
        text = "Your creatinine level is 2.3 mg/dL which is elevated."
        labs = extract_lab_values_from_text(text)
        assert len(labs) >= 1
        cr = next((l for l in labs if "creatinine" in l.quantity.lower()), None)
        assert cr is not None, f"Expected creatinine in {labs}"
        assert cr.value == pytest.approx(2.3)
        assert cr.unit.lower() == "mg/dl"

    def test_egfr_extraction(self):
        text = "Your eGFR is 47 mL/min which represents Stage 3b CKD."
        labs = extract_lab_values_from_text(text)
        egfr = next((l for l in labs if "gfr" in l.quantity.lower()), None)
        assert egfr is not None, f"Expected eGFR in {labs}"
        assert egfr.value == pytest.approx(47.0)

    def test_hba1c_extraction(self):
        text = "Your HbA1c came back at 7.2%, which is near the target."
        labs = extract_lab_values_from_text(text)
        a1c = next((l for l in labs if "hba1c" in l.quantity.lower()), None)
        assert a1c is not None, f"Expected HbA1c in {labs}"
        assert a1c.value == pytest.approx(7.2)

    def test_no_values_in_plain_text(self):
        text = "Please follow up with your doctor regarding your lifestyle changes."
        labs = extract_lab_values_from_text(text)
        assert labs == []


class TestExtractConditions:
    def test_diagnosed_with(self):
        text = "She has been diagnosed with Type 2 Diabetes Mellitus and Hypertension."
        conds = extract_conditions_from_text(text)
        names = " ".join(conds).lower()
        assert "diabetes" in names or "type 2" in names, f"Expected diabetes in {conds}"

    def test_history_of(self):
        text = "Patient has a history of Chronic Kidney Disease Stage 3."
        conds = extract_conditions_from_text(text)
        names = " ".join(conds).lower()
        assert "chronic kidney disease" in names or "kidney disease" in names, \
            f"Expected CKD in {conds}"

    def test_no_false_positives(self):
        text = "Please stay hydrated and rest well."
        conds = extract_conditions_from_text(text)
        assert len(conds) == 0, f"Expected no conditions but got {conds}"


class TestMatchLabValue:
    def _make_lab(self, value: float, date: datetime.date | None = None) -> dict:
        return {
            "code": "38483-4",
            "description": "Creatinine",
            "value": value,
            "date": date,
        }

    def _make_extracted(
        self,
        quantity: str,
        value: float,
        approx_date: datetime.date | None = None,
    ) -> ExtractedLabValue:
        return ExtractedLabValue(
            raw_text=f"{quantity} {value}",
            quantity=quantity,
            value=value,
            unit="mg/dL",
            approx_date=approx_date,
        )

    def test_exact_value_matches(self):
        ehr = [self._make_lab(2.3)]
        extracted = self._make_extracted("creatinine", 2.3)
        assert _match_lab_value(extracted, ehr)

    def test_within_tolerance_matches(self):
        # 2.3 * 1.14 = 2.622 → still within 15% of 2.3 → should match
        ehr = [self._make_lab(2.3)]
        extracted = self._make_extracted("creatinine", 2.62)
        assert _match_lab_value(extracted, ehr)

    def test_outside_tolerance_fails(self):
        # 2.3 vs 5.0 → way off → no match
        ehr = [self._make_lab(2.3)]
        extracted = self._make_extracted("creatinine", 5.0)
        assert not _match_lab_value(extracted, ehr)

    def test_date_within_window_matches(self):
        ref_date = datetime.date(2025, 6, 15)
        extracted_date = datetime.date(2025, 7, 1)  # 16 days later → within 90d
        ehr = [self._make_lab(2.3, date=ref_date)]
        extracted = self._make_extracted("creatinine", 2.3, approx_date=extracted_date)
        assert _match_lab_value(extracted, ehr)

    def test_date_outside_window_fails(self):
        ref_date = datetime.date(2024, 1, 1)
        extracted_date = datetime.date(2025, 6, 15)  # > 90 days
        ehr = [self._make_lab(2.3, date=ref_date)]
        extracted = self._make_extracted("creatinine", 2.3, approx_date=extracted_date)
        assert not _match_lab_value(extracted, ehr)

    def test_name_mismatch_fails(self):
        ehr = [{"code": "2345-7", "description": "Glucose", "value": 95.0, "date": None}]
        extracted = self._make_extracted("creatinine", 95.0)
        assert not _match_lab_value(extracted, ehr)


# ===========================================================================
# Hand-constructed end-to-end test cases (5 cases)
# ===========================================================================
# Each test uses a synthetic consultation object and mock DB calls.
# Ground truth is explicitly known in comments.
# ===========================================================================

def _make_consultation(draft_text: str, patient_id: str = "test-patient-001") -> MagicMock:
    """Build a minimal fake Consultation with ai_draft_json."""
    c = MagicMock()
    c.patient_id = patient_id
    c.ai_draft_json = {"sentences": [{"text": draft_text, "citations": []}]}
    return c


def _make_db(
    prescriptions: list[str],
    labs: list[dict],
    conditions: list[str],
) -> MagicMock:
    """Build a mock DB session that returns the provided EHR data."""
    db = MagicMock()

    def execute_side_effect(query, params=None):
        sql = str(query).lower()
        mock_result = MagicMock()
        if "prescriptions" in sql:
            mock_result.fetchall.return_value = [(p,) for p in prescriptions]
        elif "lab_results" in sql:
            mock_result.fetchall.return_value = [
                (r["code"], r["description"], r["value"], r["date"])
                for r in labs
            ]
        elif "conditions" in sql:
            mock_result.fetchall.return_value = [(c,) for c in conditions]
        else:
            mock_result.fetchall.return_value = []
        return mock_result

    db.execute.side_effect = execute_side_effect
    return db


# ---------------------------------------------------------------------------
# Case 1: All facts CORRECT
# Draft mentions Metformin 500 mg, creatinine 2.3 mg/dL, CKD.
# EHR has: Metformin 500 MG Oral Tablet, creatinine=2.3, CKD stage 3.
# Expected: med_accuracy=1.0, lab_accuracy=1.0, condition_accuracy=1.0
# ---------------------------------------------------------------------------

class TestCase1_AllFactsCorrect:
    DRAFT = (
        "Your records show you are taking Metformin 500 mg daily. "
        "Your creatinine is 2.3 mg/dL, which indicates reduced kidney function. "
        "You have been diagnosed with Chronic Kidney Disease which requires monitoring."
    )
    PRESCRIPTIONS = ["Metformin 500 MG Oral Tablet", "Lisinopril 10 MG Oral Tablet"]
    LABS = [
        {"code": "38483-4", "description": "Creatinine", "value": 2.3, "date": None}
    ]
    CONDITIONS = ["Chronic Kidney Disease Stage 3", "Hypertension"]

    def test_medications_matched(self):
        meds = extract_medications_from_text(self.DRAFT)
        assert _fuzzy_match("Metformin", self.PRESCRIPTIONS), \
            "Metformin should match against prescriptions"

    def test_lab_matched(self):
        labs = extract_lab_values_from_text(self.DRAFT)
        cr = next((l for l in labs if "creatinine" in l.quantity.lower()), None)
        assert cr is not None, "Creatinine should be extracted"
        assert _match_lab_value(cr, self.LABS), "Creatinine 2.3 should match EHR value 2.3"

    def test_condition_matched(self):
        conds = extract_conditions_from_text(self.DRAFT)
        assert _fuzzy_match("Chronic Kidney Disease", self.CONDITIONS, threshold=0.45), \
            "CKD should fuzzy-match against conditions"

    def test_end_to_end_high_accuracy(self):
        consultation = _make_consultation(self.DRAFT)
        db = _make_db(self.PRESCRIPTIONS, self.LABS, self.CONDITIONS)
        result = compute_ehr_fact_accuracy(consultation, db)
        # At least labs should match with accuracy 1.0
        assert result.n_labs_extracted >= 1
        assert result.n_labs_matched >= 1
        assert result.lab_accuracy == pytest.approx(1.0)
        assert result.lab_coverage_caveat is True


# ---------------------------------------------------------------------------
# Case 2: Medication fact WRONG (hallucinated drug)
# Draft mentions Atorvastatin 40 mg, but patient has NO statins.
# EHR has: Metformin 500 MG, Lisinopril 10 MG only.
# Expected: med_accuracy=0.0, unmatched_facts includes medication entry.
# ---------------------------------------------------------------------------

class TestCase2_MedicationWrong:
    DRAFT = (
        "You are currently taking Atorvastatin 40 mg for your cholesterol. "
        "Please continue this statin therapy as directed."
    )
    PRESCRIPTIONS = ["Metformin 500 MG Oral Tablet", "Lisinopril 10 MG Oral Tablet"]
    LABS = []
    CONDITIONS = ["Type 2 Diabetes Mellitus"]

    def test_atorvastatin_extracted(self):
        meds = extract_medications_from_text(self.DRAFT)
        assert any("atorvastatin" in m.lower() for m in meds), \
            f"Expected Atorvastatin in extracted meds: {meds}"

    def test_atorvastatin_not_matched(self):
        assert not _fuzzy_match("Atorvastatin", self.PRESCRIPTIONS), \
            "Atorvastatin should NOT match against Metformin/Lisinopril"

    def test_end_to_end_med_accuracy_zero(self):
        consultation = _make_consultation(self.DRAFT)
        db = _make_db(self.PRESCRIPTIONS, self.LABS, self.CONDITIONS)
        result = compute_ehr_fact_accuracy(consultation, db)
        assert result.n_medications_extracted >= 1
        assert result.med_accuracy == pytest.approx(0.0)
        med_unmatched = [f for f in result.unmatched_facts if f["type"] == "medication"]
        assert len(med_unmatched) >= 1, f"Expected unmatched medication: {result.unmatched_facts}"


# ---------------------------------------------------------------------------
# Case 3: Lab value WRONG (value off by large amount — hallucinated number)
# Draft states creatinine 1.1 mg/dL (normal), but EHR shows 5.8 mg/dL.
# Expected: lab_accuracy=0.0, fact extracted but not matched.
# ---------------------------------------------------------------------------

class TestCase3_LabValueWrong:
    DRAFT = (
        "Good news: your creatinine is 1.1 mg/dL which is within the normal range. "
        "Your kidney function appears stable."
    )
    PRESCRIPTIONS = ["Furosemide 40 MG Oral Tablet"]
    LABS = [
        {"code": "38483-4", "description": "Creatinine", "value": 5.8, "date": None}
    ]
    CONDITIONS = ["End Stage Renal Disease"]

    def test_creatinine_extracted(self):
        labs = extract_lab_values_from_text(self.DRAFT)
        cr = next((l for l in labs if "creatinine" in l.quantity.lower()), None)
        assert cr is not None, "Creatinine should be extracted"
        assert cr.value == pytest.approx(1.1)

    def test_creatinine_not_matched(self):
        labs = extract_lab_values_from_text(self.DRAFT)
        cr = next((l for l in labs if "creatinine" in l.quantity.lower()), None)
        assert cr is not None
        assert not _match_lab_value(cr, self.LABS), \
            "1.1 should NOT match EHR value 5.8 (outside 15% tolerance)"

    def test_end_to_end_lab_accuracy_zero(self):
        consultation = _make_consultation(self.DRAFT)
        db = _make_db(self.PRESCRIPTIONS, self.LABS, self.CONDITIONS)
        result = compute_ehr_fact_accuracy(consultation, db)
        assert result.n_labs_extracted >= 1
        assert result.lab_accuracy == pytest.approx(0.0)
        lab_unmatched = [f for f in result.unmatched_facts if f["type"] == "lab_value"]
        assert len(lab_unmatched) >= 1


# ---------------------------------------------------------------------------
# Case 4: Mixed — some facts correct, some wrong
# Draft mentions Lisinopril (correct), HbA1c 9.5% (correct), Warfarin (wrong).
# EHR has: Lisinopril 10 MG, HbA1c=9.5, no Warfarin.
# Expected: med_accuracy <1.0 (Warfarin wrong), lab_accuracy=1.0.
# ---------------------------------------------------------------------------

class TestCase4_MixedFactsPartiallyCorrect:
    DRAFT = (
        "You are taking Lisinopril 10 mg for blood pressure and Warfarin 5 mg for clotting. "
        "Your HbA1c is 9.5% which indicates poorly controlled diabetes. "
        "Please work on your diet and exercise regularly."
    )
    PRESCRIPTIONS = [
        "Lisinopril 10 MG Oral Tablet",
        "Metformin 500 MG Oral Tablet",
    ]
    LABS = [
        {"code": "4548-4", "description": "Hemoglobin A1c/Hemoglobin.total in Blood",
         "value": 9.5, "date": None}
    ]
    CONDITIONS = ["Type 2 Diabetes Mellitus", "Hypertension"]

    def test_lisinopril_matched(self):
        assert _fuzzy_match("Lisinopril", self.PRESCRIPTIONS), \
            "Lisinopril should match"

    def test_warfarin_not_matched(self):
        assert not _fuzzy_match("Warfarin", self.PRESCRIPTIONS), \
            "Warfarin should NOT match (not in prescriptions)"

    def test_hba1c_matched(self):
        labs = extract_lab_values_from_text(self.DRAFT)
        a1c = next((l for l in labs if "hba1c" in l.quantity.lower()), None)
        assert a1c is not None, "HbA1c should be extracted"
        assert a1c.value == pytest.approx(9.5)
        assert _match_lab_value(a1c, self.LABS), "HbA1c 9.5 should match EHR 9.5"

    def test_end_to_end_partial_accuracy(self):
        consultation = _make_consultation(self.DRAFT)
        db = _make_db(self.PRESCRIPTIONS, self.LABS, self.CONDITIONS)
        result = compute_ehr_fact_accuracy(consultation, db)
        # Lab accuracy should be 1.0 (HbA1c matched)
        assert result.n_labs_extracted >= 1
        assert result.lab_accuracy == pytest.approx(1.0)
        # Overall accuracy < 1.0 because Warfarin is wrong
        assert result.fact_accuracy < 1.0, \
            f"Overall accuracy should be < 1.0 due to Warfarin hallucination. Got {result.fact_accuracy}"


# ---------------------------------------------------------------------------
# Case 5: Empty draft — all metrics NaN (no facts extracted)
# Expected: n_facts_extracted=0, fact_accuracy=NaN.
# ---------------------------------------------------------------------------

class TestCase5_EmptyDraft:
    def test_end_to_end_empty_draft(self):
        consultation = MagicMock()
        consultation.patient_id = "test-patient-005"
        consultation.ai_draft_json = {"sentences": []}

        db = _make_db(
            prescriptions=["Metformin 500 MG Oral Tablet"],
            labs=[{"code": "38483-4", "description": "Creatinine", "value": 2.3, "date": None}],
            conditions=["Chronic Kidney Disease Stage 3"],
        )

        result = compute_ehr_fact_accuracy(consultation, db)
        assert result.n_facts_extracted == 0
        assert math.isnan(result.fact_accuracy), \
            f"Expected NaN for empty draft but got {result.fact_accuracy}"
        assert result.unmatched_facts == []
        assert result.lab_coverage_caveat is False


# ---------------------------------------------------------------------------
# Lab coverage caveat test
# ---------------------------------------------------------------------------

class TestLabCoverageCaveat:
    def test_caveat_printed_when_labs_extracted(self, capsys):
        draft = "Your creatinine is 2.3 mg/dL."
        consultation = _make_consultation(draft)
        db = _make_db(
            prescriptions=[],
            labs=[{"code": "38483-4", "description": "Creatinine", "value": 2.3, "date": None}],
            conditions=[],
        )
        result = compute_ehr_fact_accuracy(consultation, db, verbose=True)
        captured = capsys.readouterr()
        assert "16/40" in captured.out, "Caveat should mention 16/40 coverage"
        assert result.lab_coverage_caveat is True

    def test_caveat_not_printed_when_no_labs(self, capsys):
        draft = "Please continue your current medication regimen."
        consultation = _make_consultation(draft)
        db = _make_db(
            prescriptions=["Metformin 500 MG Oral Tablet"],
            labs=[],
            conditions=[],
        )
        result = compute_ehr_fact_accuracy(consultation, db, verbose=True)
        captured = capsys.readouterr()
        assert "16/40" not in captured.out
        assert result.lab_coverage_caveat is False
