"""
backend/tests/test_import_review.py

Unit tests for backend/eval/tools/import_review.py, including a hand-computed
10-row toy test with exact analytical verification for accuracy, Cohen's kappa,
linear-weighted kappa, confusion matrix, directional urgency shifts, and enum validations.
"""
from __future__ import annotations

import csv
import pytest
from pathlib import Path

from backend.eval.tools.import_review import (
    REAL_INTENTS,
    REAL_URGENCIES,
    compute_linear_weighted_kappa,
    compute_review_metrics,
    compute_unweighted_cohen_kappa,
    load_and_join_reviews,
    validate_reviewer_row,
    write_disagreements_csv,
)


class TestImportReviewMetrics:
    """Hand-computed 10-row toy test and validation test suite."""

    @pytest.fixture
    def hand_computed_toy_dataset(self) -> tuple[list[dict], list[dict]]:
        """
        Analytical 10-row dataset hand-calculated as follows:

        N = 10 queries: T-01 through T-10

        Intent (5 classes, balanced author distribution: 2 of each):
          - Author:
            T-01..T-02: medication_query (2)
            T-03..T-04: lab_result_query (2)
            T-05..T-06: symptom_report (2)
            T-07..T-08: general_health_info (2)
            T-09..T-10: followup_appointment (2)
          - Reviewer:
            T-01..T-03: agree
            T-04: medication_query (disagree, author=lab_result_query)
            T-05..T-07: agree
            T-08: symptom_report (disagree, author=general_health_info)
            T-09..T-10: agree
          - Observed agreement: 8/10 = 0.80
          - Chance agreement pe:
            Author marginals: [2, 2, 2, 2, 2]
            Reviewer marginals: med=3, lab=1, sym=3, gen=1, fol=2
            pe = (2*3 + 2*1 + 2*3 + 2*1 + 2*2) / 100 = 20 / 100 = 0.20
          - Cohen's kappa: (0.80 - 0.20) / (1 - 0.20) = 0.60 / 0.80 = 0.7500

        Urgency (3 ordinal classes: routine=0, soon=1, urgent=2):
          - Author:
            T-01..T-03: routine (3)
            T-04..T-07: soon (4)
            T-08..T-10: urgent (3)
          - Reviewer:
            T-01, T-02: routine (agree)
            T-03: soon (higher: 0 -> 1)
            T-04: routine (lower: 1 -> 0)
            T-05, T-06: soon (agree)
            T-07: urgent (higher: 1 -> 2)
            T-08: soon (lower: 2 -> 1)
            T-09, T-10: urgent (agree)
          - Urgency CM:
            routine row: [2, 1, 0] (sum 3)
            soon row:    [1, 2, 1] (sum 4)
            urgent row:  [0, 1, 2] (sum 3)
            col sums:    [3, 4, 3]
          - Linear weights:
            diagonal (diff 0): w = 1.0
            diff 1:            w = 0.5
            diff 2:            w = 0.0
          - Weighted po: (2+2+2)*1.0 + (1+1+1+1)*0.5 = 6.0 + 2.0 = 8.0 / 10 = 0.80
          - Outer products row_sum * col_sum:
            diag: 3*3 + 4*4 + 3*3 = 9 + 16 + 9 = 34
            diff 1: 3*4 + 4*3 + 4*3 + 3*4 = 48
            Weighted pe: (34*1.0 + 48*0.5) / 100 = (34 + 24) / 100 = 58 / 100 = 0.58
          - Linear-weighted kappa: (0.80 - 0.58) / (1 - 0.58) = 0.22 / 0.42 = 11 / 21 ≈ 0.5238095

        Needs EHR (binary True/False):
          - Author:
            T-01..T-06: True (6)
            T-07..T-08: False (2)
            T-09: True (1)
            T-10: False (1)
            Total author: 7 True, 3 False
          - Reviewer:
            T-01..T-05: True (agree)
            T-06: False (disagree: author True, rev False)
            T-07..T-08: False (agree)
            T-09: True (agree)
            T-10: True (disagree: author False, rev True)
            Total reviewer: 7 True, 3 False
          - Observed agreement: 8/10 = 0.80
          - Chance agreement pe: (7*7 + 3*3) / 100 = (49 + 9) / 100 = 58 / 100 = 0.58
          - Cohen's kappa: (0.80 - 0.58) / (1 - 0.58) = 0.22 / 0.42 = 11 / 21 ≈ 0.5238095
        """
        author_data = [
            {"query_id": "T-01", "intent": "medication_query", "urgency": "routine", "needs_ehr": True},
            {"query_id": "T-02", "intent": "medication_query", "urgency": "routine", "needs_ehr": True},
            {"query_id": "T-03", "intent": "lab_result_query", "urgency": "routine", "needs_ehr": True},
            {"query_id": "T-04", "intent": "lab_result_query", "urgency": "soon", "needs_ehr": True},
            {"query_id": "T-05", "intent": "symptom_report", "urgency": "soon", "needs_ehr": True},
            {"query_id": "T-06", "intent": "symptom_report", "urgency": "soon", "needs_ehr": True},
            {"query_id": "T-07", "intent": "general_health_info", "urgency": "soon", "needs_ehr": False},
            {"query_id": "T-08", "intent": "general_health_info", "urgency": "urgent", "needs_ehr": False},
            {"query_id": "T-09", "intent": "followup_appointment", "urgency": "urgent", "needs_ehr": True},
            {"query_id": "T-10", "intent": "followup_appointment", "urgency": "urgent", "needs_ehr": False},
        ]

        reviewer_data = [
            {"reviewer_id": "DR-1", "query_id": "T-01", "intent": "medication_query", "urgency": "routine", "needs_ehr": True, "confidence": "5", "rationale": "Clear med question", "source_url": ""},
            {"reviewer_id": "DR-1", "query_id": "T-02", "intent": "medication_query", "urgency": "routine", "needs_ehr": True, "confidence": "5", "rationale": "Refill check", "source_url": ""},
            {"reviewer_id": "DR-1", "query_id": "T-03", "intent": "lab_result_query", "urgency": "soon", "needs_ehr": True, "confidence": "4", "rationale": "Elevated lab", "source_url": ""},
            {"reviewer_id": "DR-1", "query_id": "T-04", "intent": "medication_query", "urgency": "routine", "needs_ehr": True, "confidence": "4", "rationale": "Medication concern", "source_url": ""},
            {"reviewer_id": "DR-1", "query_id": "T-05", "intent": "symptom_report", "urgency": "soon", "needs_ehr": True, "confidence": "5", "rationale": "Mild symptoms", "source_url": ""},
            {"reviewer_id": "DR-1", "query_id": "T-06", "intent": "symptom_report", "urgency": "soon", "needs_ehr": False, "confidence": "3", "rationale": "General inquiry", "source_url": ""},
            {"reviewer_id": "DR-1", "query_id": "T-07", "intent": "general_health_info", "urgency": "urgent", "needs_ehr": False, "confidence": "5", "rationale": "Concerning symptoms", "source_url": ""},
            {"reviewer_id": "DR-1", "query_id": "T-08", "intent": "symptom_report", "urgency": "soon", "needs_ehr": False, "confidence": "4", "rationale": "Moderate symptom", "source_url": ""},
            {"reviewer_id": "DR-1", "query_id": "T-09", "intent": "followup_appointment", "urgency": "urgent", "needs_ehr": True, "confidence": "5", "rationale": "Overdue urgent review", "source_url": ""},
            {"reviewer_id": "DR-1", "query_id": "T-10", "intent": "followup_appointment", "urgency": "urgent", "needs_ehr": True, "confidence": "4", "rationale": "Needs record", "source_url": ""},
        ]
        return author_data, reviewer_data

    def test_hand_computed_10_row_toy_metrics(self, tmp_path: Path, hand_computed_toy_dataset):
        author_data, reviewer_data = hand_computed_toy_dataset

        sealed_file = tmp_path / "sealed_test.csv"
        with open(sealed_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["query_id", "intent", "urgency", "needs_ehr"])
            writer.writeheader()
            writer.writerows(author_data)

        review_file = tmp_path / "reviewer_test.csv"
        with open(review_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "reviewer_id", "query_id", "intent", "urgency", "needs_ehr",
                    "confidence", "rationale", "source_url"
                ],
            )
            writer.writeheader()
            writer.writerows(reviewer_data)

        matched, unmatched_rev, unmatched_seal = load_and_join_reviews(review_file, sealed_file)
        assert len(matched) == 10
        assert len(unmatched_rev) == 0
        assert len(unmatched_seal) == 0

        metrics = compute_review_metrics(matched)

        # 1. Intent Verification (Exact Hand Calculated: acc=0.80, kappa=0.75)
        assert metrics["intent_accuracy"] == pytest.approx(0.80, abs=1e-6)
        assert metrics["intent_cohen_kappa"] == pytest.approx(0.75, abs=1e-6)

        # 2. Needs EHR Verification (Exact Hand Calculated: acc=0.80, kappa=11/21)
        assert metrics["needs_ehr_accuracy"] == pytest.approx(0.80, abs=1e-6)
        assert metrics["needs_ehr_cohen_kappa"] == pytest.approx(11.0 / 21.0, abs=1e-6)

        # 3. Urgency Verification (Exact Hand Calculated: acc=0.60, linear kappa=11/21)
        assert metrics["urgency_accuracy"] == pytest.approx(0.60, abs=1e-6)
        assert metrics["urgency_linear_kappa"] == pytest.approx(11.0 / 21.0, abs=1e-6)

        # 4. Urgency Confusion Matrix Verification
        cm = metrics["urgency_confusion_matrix"]
        assert cm["routine"] == {"routine": 2, "soon": 1, "urgent": 0}
        assert cm["soon"] == {"routine": 1, "soon": 2, "urgent": 1}
        assert cm["urgent"] == {"routine": 0, "soon": 1, "urgent": 2}

        # 5. Directional Urgency Shift Verification
        higher_qids = [r["query_id"] for r in metrics["urgency_higher_rows"]]
        lower_qids = [r["query_id"] for r in metrics["urgency_lower_rows"]]
        assert higher_qids == ["T-03", "T-07"]
        assert lower_qids == ["T-04", "T-08"]

        # 6. Disagreements CSV export
        dis_file = tmp_path / "disagreements.csv"
        n_dis = write_disagreements_csv(matched, dis_file)
        assert n_dis == 6
        with open(dis_file, encoding="utf-8") as f:
            dis_reader = list(csv.DictReader(f))
        assert len(dis_reader) == 6
        assert [r["query_id"] for r in dis_reader] == ["T-03", "T-04", "T-06", "T-07", "T-08", "T-10"]

    def test_enum_validations(self):
        # Valid row
        valid_row = {
            "reviewer_id": "DR-1",
            "query_id": "GS-0001",
            "intent": "lab_result_query",
            "urgency": "urgent",
            "needs_ehr": "True",
            "confidence": "5",
            "rationale": "High glucose",
            "source_url": "",
        }
        res = validate_reviewer_row(valid_row)
        assert res["intent"] == "lab_result_query"
        assert res["urgency"] == "urgent"
        assert res["needs_ehr"] is True

        # Invalid intent
        invalid_intent = dict(valid_row, intent="unknown_intent")
        with pytest.raises(ValueError, match="Invalid intent 'unknown_intent'"):
            validate_reviewer_row(invalid_intent)

        # Invalid urgency
        invalid_urgency = dict(valid_row, urgency="critical")
        with pytest.raises(ValueError, match="Invalid urgency 'critical'"):
            validate_reviewer_row(invalid_urgency)

        # Invalid boolean
        invalid_bool = dict(valid_row, needs_ehr="maybe")
        with pytest.raises(ValueError, match="Invalid boolean value"):
            validate_reviewer_row(invalid_bool)

        # Missing required field
        missing_field = dict(valid_row)
        del missing_field["confidence"]
        with pytest.raises(ValueError, match="missing required column: 'confidence'"):
            validate_reviewer_row(missing_field)

    def test_reviewer_keyed_by_blind_id(self, tmp_path: Path):
        sealed_file = tmp_path / "sealed_test.csv"
        with open(sealed_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["query_id", "intent", "urgency", "needs_ehr"])
            writer.writeheader()
            writer.writerow({"query_id": "GS-0001", "intent": "lab_result_query", "urgency": "urgent", "needs_ehr": True})
            writer.writerow({"query_id": "GS-0002", "intent": "medication_query", "urgency": "routine", "needs_ehr": True})

        map_file = tmp_path / "blind_map.csv"
        with open(map_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["blind_id", "query_id"])
            writer.writeheader()
            writer.writerow({"blind_id": "R1001", "query_id": "GS-0001"})
            writer.writerow({"blind_id": "R1002", "query_id": "GS-0002"})

        # Reviewer file has blind_id instead of query_id
        rev_file = tmp_path / "rev_blind.csv"
        with open(rev_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["reviewer_id", "blind_id", "intent", "urgency", "needs_ehr", "confidence", "rationale", "source_url"],
            )
            writer.writeheader()
            writer.writerow({
                "reviewer_id": "DR-1", "blind_id": "R1001", "intent": "lab_result_query",
                "urgency": "urgent", "needs_ehr": "True", "confidence": "5", "rationale": "High lab", "source_url": ""
            })
            writer.writerow({
                "reviewer_id": "DR-1", "blind_id": "R1002", "intent": "medication_query",
                "urgency": "soon", "needs_ehr": "True", "confidence": "4", "rationale": "Moderate med", "source_url": ""
            })

        matched, un_rev, un_seal = load_and_join_reviews(rev_file, sealed_file, blind_map_path=map_file)
        assert len(matched) == 2
        assert matched[0]["query_id"] == "GS-0001"
        assert matched[0]["blind_id"] == "R1001"
        assert matched[1]["query_id"] == "GS-0002"
        assert matched[1]["blind_id"] == "R1002"

        # Check unknown blind_id rejection
        bad_rev_file = tmp_path / "rev_bad_blind.csv"
        with open(bad_rev_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["reviewer_id", "blind_id", "intent", "urgency", "needs_ehr", "confidence", "rationale", "source_url"],
            )
            writer.writeheader()
            writer.writerow({
                "reviewer_id": "DR-1", "blind_id": "R9999", "intent": "lab_result_query",
                "urgency": "urgent", "needs_ehr": "True", "confidence": "5", "rationale": "", "source_url": ""
            })

        with pytest.raises(ValueError, match="unmapped blind_id 'R9999'"):
            load_and_join_reviews(bad_rev_file, sealed_file, blind_map_path=map_file)

