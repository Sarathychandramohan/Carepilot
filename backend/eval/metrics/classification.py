"""
D:\\CarePilotAI\\backend\\eval\\metrics\\classification.py

Intent and Urgency classification evaluation module (Table T3, Figure F2).
Computes:
  - Per-class Precision, Recall, and F1-score
  - Macro-averaged and Weighted-averaged F1
  - Confusion matrix representation
  - Accuracy
"""
from __future__ import annotations

from typing import Sequence
import numpy as np


def compute_confusion_matrix(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    labels: Sequence[str] | None = None,
) -> tuple[list[str], list[list[int]]]:
    """Generates an integer confusion matrix matching labels ordering."""
    if labels is None:
        unique_labels = sorted(list(set(y_true) | set(y_pred)))
    else:
        unique_labels = list(labels)

    label_to_idx = {l: i for i, l in enumerate(unique_labels)}
    n = len(unique_labels)
    matrix = [[0] * n for _ in range(n)]

    for true_val, pred_val in zip(y_true, y_pred):
        if true_val in label_to_idx and pred_val in label_to_idx:
            matrix[label_to_idx[true_val]][label_to_idx[pred_val]] += 1

    return unique_labels, matrix


def compute_classification_metrics(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    labels: Sequence[str] | None = None,
) -> dict[str, Any]:
    """
    Computes per-class P/R/F1, macro-F1, accuracy, and confusion matrix.
    """
    if len(y_true) == 0 or len(y_pred) == 0:
        return {
            "accuracy": 0.0,
            "macro_f1": 0.0,
            "macro_precision": 0.0,
            "macro_recall": 0.0,
            "per_class": {},
            "confusion_matrix": {"labels": [], "matrix": []},
        }

    all_labels, matrix = compute_confusion_matrix(y_true, y_pred, labels=labels)
    mat_arr = np.array(matrix, dtype=int)
    total_samples = len(y_true)

    per_class = {}
    f1s = []
    precisions = []
    recalls = []

    for idx, label in enumerate(all_labels):
        tp = int(mat_arr[idx, idx])
        fp = int(np.sum(mat_arr[:, idx]) - tp)
        fn = int(np.sum(mat_arr[idx, :]) - tp)
        support = int(np.sum(mat_arr[idx, :]))

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2.0 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

        per_class[label] = {
            "precision": float(prec),
            "recall": float(rec),
            "f1": float(f1),
            "support": support,
        }
        precisions.append(prec)
        recalls.append(rec)
        f1s.append(f1)

    accuracy = int(np.trace(mat_arr)) / total_samples if total_samples > 0 else 0.0

    return {
        "accuracy": float(accuracy),
        "macro_precision": float(np.mean(precisions)) if precisions else 0.0,
        "macro_recall": float(np.mean(recalls)) if recalls else 0.0,
        "macro_f1": float(np.mean(f1s)) if f1s else 0.0,
        "per_class": per_class,
        "confusion_matrix": {
            "labels": all_labels,
            "matrix": matrix,
        },
    }
