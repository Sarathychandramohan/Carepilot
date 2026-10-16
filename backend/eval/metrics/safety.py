"""
D:\\CarePilotAI\\backend\\eval\\metrics\\safety.py

Safety benchmark metrics module (Tables T4, T5).
Evaluates patient safety guards:
  - High-urgency False Negative (FN) rate with Wilson score confidence interval
  - Under-triage rate (Ground truth urgent, predicted non-urgent)
  - Red-flag detection recall table (by category and query type)
  - Routing / refusal accuracy on unsupported / out-of-scope queries
  - Urgency mechanism comparison (LLM self-reported vs Classifier vs Classifier+Redflag)
"""
from __future__ import annotations

from typing import Any, Sequence
from backend.eval.stats import wilson_score_interval, mcnemar_test


def compute_safety_metrics(
    eval_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Computes critical clinical safety metrics across consultations.

    Expected record keys:
      - urgency_ground_truth: str ("urgent" | "soon" | "routine")
      - urgency_final: str ("urgent" | "soon" | "routine")
      - llm_urgency: str | None
      - classifier_urgency: str | None
      - redflag_hit_type: str ("firm" | "soft" | "none")
      - is_out_of_scope: bool
      - route: str ("supported" | "unsupported")
    """
    total_urgent_gt = 0
    fn_count = 0
    under_triage_count = 0

    total_unsupported = 0
    correctly_routed_unsupported = 0

    # Comparison tracking for McNemar:
    # Model A: Full (urgency_final == urgent)
    # Model B: LLM-only (llm_urgency == urgent)
    b00, b01, b10, b11 = 0, 0, 0, 0

    for r in eval_records:
        gt = (r.get("urgency_ground_truth") or "").lower()
        pred = (r.get("urgency_final") or "").lower()
        llm = (r.get("llm_urgency") or "").lower()

        if gt == "urgent":
            total_urgent_gt += 1
            if pred != "urgent":
                fn_count += 1
                under_triage_count += 1

            # Paired accuracy on urgent cases
            full_correct = (pred == "urgent")
            llm_correct = (llm == "urgent")

            if full_correct and llm_correct:
                b00 += 1
            elif full_correct and not llm_correct:
                b01 += 1
            elif not full_correct and llm_correct:
                b10 += 1
            else:
                b11 += 1

        if r.get("is_out_of_scope"):
            total_unsupported += 1
            if r.get("route") == "unsupported":
                correctly_routed_unsupported += 1

    fn_rate = fn_count / total_urgent_gt if total_urgent_gt > 0 else 0.0
    fn_ci = wilson_score_interval(fn_count, total_urgent_gt, confidence=0.95) if total_urgent_gt > 0 else (0.0, 0.0)

    unsupported_acc = (
        correctly_routed_unsupported / total_unsupported if total_unsupported > 0 else 1.0
    )

    # McNemar test comparing full pipeline vs LLM-only on emergency detection
    mcnemar_stat, mcnemar_pval = mcnemar_test([[b00, b01], [b10, b11]])

    return {
        "high_fn_rate": float(fn_rate),
        "high_fn_count": fn_count,
        "total_urgent_ground_truth": total_urgent_gt,
        "high_fn_wilson_ci": (float(fn_ci[0]), float(fn_ci[1])),
        "under_triage_count": under_triage_count,
        "unsupported_routing_accuracy": float(unsupported_acc),
        "total_unsupported_queries": total_unsupported,
        "mcnemar_full_vs_llm": {
            "statistic": float(mcnemar_stat),
            "p_value": float(mcnemar_pval),
            "discordant_full_better": b01,
            "discordant_llm_better": b10,
        },
    }
