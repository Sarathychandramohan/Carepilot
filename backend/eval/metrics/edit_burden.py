"""
D:\\CarePilotAI\\backend\\eval\\metrics\\edit_burden.py

Doctor edit burden evaluation module (Table T7, Figure F3).
Implements Master Spec Section 8 & Section 9:
  - Weighted Edit Burden: W_k = Σ w_i * c_{k,i}
  - Mean Edit Burden per consultation: W_bar = (1/N) Σ W_k
  - Edit Distance Ratio (EDR char-level and word-level)
  - Spearman rank correlation of burden vs interaction index (RQ3 trend)
  - Memory-On vs Memory-Off comparative reduction
"""
from __future__ import annotations

from typing import Any, Sequence
import numpy as np
from scipy import stats
from backend.eval.stats import bootstrap_ci


# Authoritative 12-category weights from Master Spec Section 9
SPEC_EDIT_WEIGHTS: dict[str, float] = {
    "factual_correction": 2.0,
    "missing_ehr_fact": 2.0,
    "wrong_ehr_fact": 3.0,
    "unsupported_medical_claim": 3.0,
    "citation_error": 1.5,
    "urgency_correction": 3.0,
    "missing_caution": 1.5,
    "tone_change": 1.0,
    "unnecessary_content": 0.5,
    "retrieval_error": 1.0,
    "no_change": 0.0,
    "other": 1.0,
}


def compute_weighted_burden(category_counts: dict[str, int | float]) -> float:
    """Computes single-consultation weighted edit burden W_k."""
    total = 0.0
    for cat, weight in SPEC_EDIT_WEIGHTS.items():
        count = category_counts.get(cat, 0)
        total += weight * float(count)
    return total


def compute_edit_burden_metrics(
    eval_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Computes weighted edit burden distribution, EDR, and Spearman trend for RQ3.

    Expected record keys:
      - consultation_edit_weight: float | None (or edit_categories_json)
      - edr_char: float | None
      - edr_word: float | None
      - interaction_number: int | None (1 to 60)
      - edit_memory_used: bool | None
    """
    if not eval_records:
        return {
            "mean_weighted_burden": 0.0,
            "median_weighted_burden": 0.0,
            "burden_bootstrap_ci": (0.0, 0.0),
            "mean_edr_char": 0.0,
            "mean_edr_word": 0.0,
            "spearman_rho": 0.0,
            "spearman_pvalue": 1.0,
            "total_reviews": 0,
        }

    burdens: list[float] = []
    edr_chars: list[float] = []
    edr_words: list[float] = []
    interactions: list[int] = []

    for idx, r in enumerate(eval_records, start=1):
        w = r.get("consultation_edit_weight")
        if w is None and "edit_categories_json" in r and r["edit_categories_json"]:
            w = compute_weighted_burden(r["edit_categories_json"])
        if w is not None:
            burdens.append(float(w))

        if r.get("edr_char") is not None:
            edr_chars.append(float(r["edr_char"]))
        if r.get("edr_word") is not None:
            edr_words.append(float(r["edr_word"]))

        int_num = r.get("interaction_number", idx)
        interactions.append(int_num)

    mean_burden = float(np.mean(burdens)) if burdens else 0.0
    median_burden = float(np.median(burdens)) if burdens else 0.0
    burden_ci = bootstrap_ci(burdens, statistic_fn=np.mean) if burdens else (0.0, 0.0)

    # Compute Spearman rank correlation (burden vs review order)
    if len(burdens) >= 3 and len(burdens) == len(interactions):
        res = stats.spearmanr(interactions, burdens)
        rho = float(res.statistic) if not np.isnan(res.statistic) else 0.0
        pval = float(res.pvalue) if not np.isnan(res.pvalue) else 1.0
    else:
        rho = 0.0
        pval = 1.0

    return {
        "mean_weighted_burden": mean_burden,
        "median_weighted_burden": median_burden,
        "burden_bootstrap_ci": burden_ci,
        "mean_edr_char": float(np.mean(edr_chars)) if edr_chars else 0.0,
        "mean_edr_word": float(np.mean(edr_words)) if edr_words else 0.0,
        "spearman_rho": rho,
        "spearman_pvalue": pval,
        "total_reviews": len(eval_records),
    }
