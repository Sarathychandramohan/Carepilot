"""
D:\\CarePilotAI\\backend\\eval\\metrics\\conflict.py

D17 Context Gap and Conflict Detection Metrics (Table T5).
Measures system ability to detect:
  - D17a: Patient-EHR Mismatch (e.g. Query refers to a medication/condition absent from patient's EHR)
  - D17b: Missing Context (e.g. Query requires recent lab panel, but none exists on record)
"""
from __future__ import annotations

from typing import Any, Sequence
import numpy as np


def compute_conflict_detection_metrics(
    eval_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Computes Precision, Recall, and F1 for D17a and D17b conflict detection against tagged ground truths.

    Expected record keys:
      - is_ground_truth_mismatch: bool (D17a ground truth)
      - predicted_mismatch: bool        (consultations.patient_ehr_mismatch_flag)
      - is_ground_truth_missing_context: bool (D17b ground truth)
      - predicted_missing_context: bool       (consultations.missing_context_flag)
    """
    def calc_prf(tp: int, fp: int, fn: int) -> dict[str, float]:
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2.0 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        return {"precision": float(prec), "recall": float(rec), "f1": float(f1)}

    # D17a tracking
    tp_a, fp_a, fn_a, tn_a = 0, 0, 0, 0
    # D17b tracking
    tp_b, fp_b, fn_b, tn_b = 0, 0, 0, 0

    for r in eval_records:
        gt_a = bool(r.get("is_ground_truth_mismatch", False))
        pred_a = bool(r.get("predicted_mismatch", False))

        if gt_a and pred_a:
            tp_a += 1
        elif not gt_a and pred_a:
            fp_a += 1
        elif gt_a and not pred_a:
            fn_a += 1
        else:
            tn_a += 1

        gt_b = bool(r.get("is_ground_truth_missing_context", False))
        pred_b = bool(r.get("predicted_missing_context", False))

        if gt_b and pred_b:
            tp_b += 1
        elif not gt_b and pred_b:
            fp_b += 1
        elif gt_b and not pred_b:
            fn_b += 1
        else:
            tn_b += 1

    return {
        "d17a_patient_ehr_mismatch": {
            **calc_prf(tp_a, fp_a, fn_a),
            "true_positives": tp_a,
            "false_positives": fp_a,
            "false_negatives": fn_a,
            "total_ground_truth": tp_a + fn_a,
        },
        "d17b_missing_context": {
            **calc_prf(tp_b, fp_b, fn_b),
            "true_positives": tp_b,
            "false_positives": fp_b,
            "false_negatives": fn_b,
            "total_ground_truth": tp_b + fn_b,
        },
    }
