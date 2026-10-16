"""
D:\\CarePilotAI\\backend\\tests\\test_eval_harness.py

Unit tests for CarePilot AI Pillar C evaluation harness & metric modules.
Tests all statistical methods and metric calculators on hand-constructed toy data
with known, mathematically verifiable ground truths before real execution.
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from backend.eval.stats import (
    wilson_score_interval,
    mcnemar_test,
    wilcoxon_signed_rank,
    holm_bonferroni_correction,
    bootstrap_ci,
    cluster_bootstrap_ci,
)
from backend.eval.metrics.retrieval import (
    compute_hit_at_k,
    compute_reciprocal_rank,
    compute_retrieval_metrics,
)
from backend.eval.metrics.classification import (
    compute_confusion_matrix,
    compute_classification_metrics,
)
from backend.eval.metrics.safety import compute_safety_metrics
from backend.eval.metrics.faithfulness import compute_faithfulness_metrics
from backend.eval.metrics.conflict import compute_conflict_detection_metrics
from backend.eval.metrics.latency import compute_latency_metrics
from backend.eval.metrics.edit_burden import (
    compute_weighted_burden,
    compute_edit_burden_metrics,
    SPEC_EDIT_WEIGHTS,
)


# ===========================================================================
# 1. Statistical Computing Layer Tests (stats.py)
# ===========================================================================

class TestStatisticalLayer:
    def test_wilson_score_interval_bounds(self):
        # 0 successes out of 10 -> lower bound must be 0.0, upper bound > 0.0
        low, high = wilson_score_interval(0, 10, confidence=0.95)
        assert low == 0.0
        assert 0.25 <= high <= 0.35

        # 10 successes out of 10 -> upper bound must be 1.0, lower bound < 1.0
        low, high = wilson_score_interval(10, 10, confidence=0.95)
        assert high == pytest.approx(1.0)
        assert 0.65 <= low <= 0.75


        # 50 out of 100 -> centered at 0.5
        low, high = wilson_score_interval(50, 100, confidence=0.95)
        assert low < 0.5 < high
        assert (low + high) / 2.0 == pytest.approx(0.5, abs=0.01)

    def test_mcnemar_test_discordant(self):
        # Perfectly symmetric table -> p-value = 1.0
        # b01 = 5, b10 = 5
        stat, pval = mcnemar_test([[20, 5], [5, 20]])
        assert pval == pytest.approx(1.0)

        # Extreme asymmetry -> p-value very small
        # b01 = 0, b10 = 20
        stat, pval = mcnemar_test([[20, 0], [20, 20]])
        assert pval < 0.001

    def test_wilcoxon_signed_rank(self):
        # Identical samples -> p-value 1.0
        x = [1.0, 2.0, 3.0, 4.0]
        y = [1.0, 2.0, 3.0, 4.0]
        stat, pval = wilcoxon_signed_rank(x, y)
        assert pval == 1.0

        # One consistently higher -> significant difference
        x = [5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        y = [1.0, 2.0, 1.5, 2.5, 1.8, 2.2]
        stat, pval = wilcoxon_signed_rank(x, y)
        assert pval < 0.05

    def test_holm_bonferroni_correction(self):
        # p-values: [0.01, 0.04, 0.03]
        # Sorted: 0.01 (x3 -> 0.03), 0.03 (x2 -> 0.06), 0.04 (x1 -> 0.04 -> monotonic -> 0.06)
        raw_p = [0.01, 0.04, 0.03]
        adj_p = holm_bonferroni_correction(raw_p)
        assert len(adj_p) == 3
        assert adj_p[0] == pytest.approx(0.03)
        assert adj_p[2] == pytest.approx(0.06)
        assert adj_p[1] == pytest.approx(0.06)

    def test_bootstrap_ci_mean(self):
        # Constant data -> CI collapses to constant
        data = [5.0] * 20
        low, high = bootstrap_ci(data, statistic_fn=np.mean)
        assert low == pytest.approx(5.0)
        assert high == pytest.approx(5.0)

        # Varied data -> bounds enclose mean
        data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        low, high = bootstrap_ci(data, statistic_fn=np.mean)
        assert low <= 3.5 <= high

    def test_cluster_bootstrap_ci_hand_computed(self):
        # Hand-computed toy test:
        # 2 clusters:
        # Cluster 'A': [10.0, 10.0] (mean = 10.0)
        # Cluster 'B': [0.0, 0.0]   (mean = 0.0)
        # Possible resamples of 2 clusters:
        # {A, A} with p=0.25 -> mean = 10.0
        # {A, B} with p=0.50 -> mean = 5.0
        # {B, B} with p=0.25 -> mean = 0.0
        # The 95% CI (2.5% and 97.5% percentiles) MUST fall on 0.0 and 10.0 exactly.
        data = [10.0, 10.0, 0.0, 0.0]
        cluster_ids = ["A", "A", "B", "B"]
        low, high = cluster_bootstrap_ci(data, cluster_ids, n_boot=2000, seed=42)
        assert low == pytest.approx(0.0)
        assert high == pytest.approx(10.0)

        # Single cluster or identical clusters collapse to exact value
        data_single = [4.0, 4.0]
        clusters_single = ["c1", "c1"]
        low_s, high_s = cluster_bootstrap_ci(data_single, clusters_single, n_boot=2000, seed=42)
        assert low_s == pytest.approx(4.0)
        assert high_s == pytest.approx(4.0)


# ===========================================================================
# 2. Retrieval Metrics Tests (retrieval.py)
# ===========================================================================

class TestRetrievalMetrics:
    def test_hit_at_k(self):
        retrieved = ["docA", "docB", "docC", "docD"]
        assert compute_hit_at_k(retrieved, ["docA"], k=3) == 1.0
        assert compute_hit_at_k(retrieved, ["docC"], k=3) == 1.0
        assert compute_hit_at_k(retrieved, ["docD"], k=3) == 0.0
        assert compute_hit_at_k(retrieved, ["docD"], k=5) == 1.0
        assert compute_hit_at_k(retrieved, ["docZ"], k=5) == 0.0

    def test_reciprocal_rank(self):
        retrieved = ["docA", "docB", "docC"]
        assert compute_reciprocal_rank(retrieved, ["docA"]) == 1.0
        assert compute_reciprocal_rank(retrieved, ["docB"]) == 0.5
        assert compute_reciprocal_rank(retrieved, ["docC"]) == pytest.approx(1.0 / 3.0)
        assert compute_reciprocal_rank(retrieved, ["docZ"]) == 0.0

    def test_aggregate_retrieval_metrics(self):
        records = [
            {
                "retrieved_kb_doc_ids": ["docA", "docB"],
                "expected_kb_doc_ids": ["docA"],
                "ehr_citations_count": 2,
                "kb_citations_count": 2,
            },
            {
                "retrieved_kb_doc_ids": ["docX", "docB"],
                "expected_kb_doc_ids": ["docB"],
                "ehr_citations_count": 0,
                "kb_citations_count": 4,
            },
        ]
        res = compute_retrieval_metrics(records)
        assert res["hit_at_3"] == 1.0
        assert res["mrr"] == pytest.approx((1.0 + 0.5) / 2.0)
        assert res["ehr_citation_share"] == pytest.approx(2.0 / 8.0)
        assert res["kb_citation_share"] == pytest.approx(6.0 / 8.0)


# ===========================================================================
# 3. Classification Metrics Tests (classification.py)
# ===========================================================================

class TestClassificationMetrics:
    def test_confusion_matrix_and_macro_f1(self):
        y_true = ["catA", "catA", "catB", "catB"]
        y_pred = ["catA", "catB", "catB", "catB"]

        res = compute_classification_metrics(y_true, y_pred, labels=["catA", "catB"])
        assert res["accuracy"] == 0.75

        # catA: TP=1, FP=0, FN=1 -> Prec=1.0, Rec=0.5, F1=0.667
        # catB: TP=2, FP=1, FN=0 -> Prec=2/3, Rec=1.0, F1=0.8
        assert res["per_class"]["catA"]["precision"] == 1.0
        assert res["per_class"]["catA"]["recall"] == 0.5
        assert res["per_class"]["catB"]["recall"] == 1.0

        # Confusion matrix checks
        matrix = res["confusion_matrix"]["matrix"]
        assert matrix[0] == [1, 1]  # catA row
        assert matrix[1] == [0, 2]  # catB row


# ===========================================================================
# 4. Safety Metrics Tests (safety.py)
# ===========================================================================

class TestSafetyMetrics:
    def test_high_fn_rate_and_under_triage(self):
        records = [
            # 2 true urgents: 1 caught, 1 missed (FN)
            {"urgency_ground_truth": "urgent", "urgency_final": "urgent", "llm_urgency": "urgent"},
            {"urgency_ground_truth": "urgent", "urgency_final": "routine", "llm_urgency": "routine"},
            # 1 routine
            {"urgency_ground_truth": "routine", "urgency_final": "routine", "llm_urgency": "routine"},
            # 1 out of scope
            {"is_out_of_scope": True, "route": "unsupported"},
        ]
        res = compute_safety_metrics(records)
        assert res["total_urgent_ground_truth"] == 2
        assert res["high_fn_count"] == 1
        assert res["high_fn_rate"] == 0.5
        assert res["under_triage_count"] == 1
        assert res["unsupported_routing_accuracy"] == 1.0


# ===========================================================================
# 5. Faithfulness Metrics Tests (faithfulness.py)
# ===========================================================================

class TestFaithfulnessMetrics:
    def test_faithfulness_aggregations(self):
        records = [
            {
                "citation_validity": 1.0,
                "citation_coverage": 1.0,
                "avg_nli_entailment": 0.85,
                "validation_status": "passed",
                "has_outlier_only_sentence": False,
            },
            {
                "citation_validity": 0.5,
                "citation_coverage": 0.5,
                "avg_nli_entailment": 0.35,
                "validation_status": "manual_required",
                "has_outlier_only_sentence": True,
            },
        ]
        res = compute_faithfulness_metrics(records)
        assert res["mean_citation_validity"] == 0.75
        assert res["mean_citation_coverage"] == 0.75
        assert res["mean_nli_entailment"] == 0.60
        assert res["validation_pass_rate"] == 0.5
        assert res["outlier_sentence_count"] == 1


# ===========================================================================
# 6. Conflict Detection Metrics Tests (conflict.py)
# ===========================================================================

class TestConflictDetectionMetrics:
    def test_d17_precision_recall(self):
        records = [
            # D17a: 1 TP, 1 TN
            {"is_ground_truth_mismatch": True, "predicted_mismatch": True},
            {"is_ground_truth_mismatch": False, "predicted_mismatch": False},
            # D17b: 1 FN, 1 FP
            {"is_ground_truth_missing_context": True, "predicted_missing_context": False},
            {"is_ground_truth_missing_context": False, "predicted_missing_context": True},
        ]
        res = compute_conflict_detection_metrics(records)

        # D17a: TP=1, FP=0, FN=0 -> Prec=1.0, Rec=1.0
        assert res["d17a_patient_ehr_mismatch"]["precision"] == 1.0
        assert res["d17a_patient_ehr_mismatch"]["recall"] == 1.0
        assert res["d17a_patient_ehr_mismatch"]["f1"] == 1.0

        # D17b: TP=0, FP=1, FN=1 -> Prec=0.0, Rec=0.0
        assert res["d17b_missing_context"]["precision"] == 0.0
        assert res["d17b_missing_context"]["recall"] == 0.0
        assert res["d17b_missing_context"]["f1"] == 0.0


# ===========================================================================
# 7. Latency Metrics Tests (latency.py)
# ===========================================================================

class TestLatencyMetrics:
    def test_latency_percentiles(self):
        latencies = [100, 200, 300, 400, 500]
        res = compute_latency_metrics(latencies)
        assert res["generation_p50_ms"] == 300.0
        assert res["generation_mean_ms"] == 300.0
        assert res["total_queries"] == 5


# ===========================================================================
# 8. Edit Burden Metrics Tests (edit_burden.py)
# ===========================================================================

class TestEditBurdenMetrics:
    def test_weighted_edit_burden_formula(self):
        # wrong_ehr_fact (w=3) + factual_correction (w=2) = 5.0
        cats = {
            "wrong_ehr_fact": 1,
            "factual_correction": 1,
            "no_change": 0,
        }
        w = compute_weighted_burden(cats)
        assert w == 5.0

    def test_spearman_trend_negative_correlation(self):
        # Burden strictly decreasing over time: 10, 8, 6, 4, 2
        # Interaction number: 1, 2, 3, 4, 5 -> rho = -1.0
        records = [
            {"consultation_edit_weight": 10.0, "interaction_number": 1, "edr_char": 0.5},
            {"consultation_edit_weight": 8.0, "interaction_number": 2, "edr_char": 0.4},
            {"consultation_edit_weight": 6.0, "interaction_number": 3, "edr_char": 0.3},
            {"consultation_edit_weight": 4.0, "interaction_number": 4, "edr_char": 0.2},
            {"consultation_edit_weight": 2.0, "interaction_number": 5, "edr_char": 0.1},
        ]
        res = compute_edit_burden_metrics(records)
        assert res["mean_weighted_burden"] == 6.0
        assert res["spearman_rho"] == pytest.approx(-1.0)
        assert res["spearman_pvalue"] < 0.01
        assert res["mean_edr_char"] == pytest.approx(0.3)
