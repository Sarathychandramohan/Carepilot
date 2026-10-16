"""
D:\\CarePilotAI\\backend\\eval\\metrics\\faithfulness.py

Faithfulness and Citation metrics module (Tables T5, T6).
Measures hallucination prevention and attribution grounding:
  - Citation Validity score (valid regex format + real retrieved chunk IDs)
  - Citation Entailment score (per-sentence NLI entailment distribution)
  - Citation Coverage (fraction of draft sentences carrying valid citations)
  - Source-type specific accuracy (EHR vs KB vs mixed sentences)
  - Outlier-only sentence presence
"""
from __future__ import annotations

from typing import Any, Sequence
import numpy as np


def compute_faithfulness_metrics(
    eval_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Computes citation and faithfulness distributions across evaluated consultations.

    Expected record keys:
      - citation_validity: float (0.0 to 1.0)
      - citation_coverage: float (0.0 to 1.0)
      - avg_nli_entailment: float (0.0 to 1.0)
      - validation_status: str ("passed" | "passed_with_warning" | "manual_required" | etc.)
      - has_outlier_only_sentence: bool
    """
    if not eval_records:
        return {
            "mean_citation_validity": 0.0,
            "mean_citation_coverage": 0.0,
            "mean_nli_entailment": 0.0,
            "validation_pass_rate": 0.0,
            "outlier_sentence_count": 0,
            "total_evaluated": 0,
        }

    validities = [r.get("citation_validity", 0.0) for r in eval_records]
    coverages = [r.get("citation_coverage", 0.0) for r in eval_records]
    entailments = [r.get("avg_nli_entailment", 0.0) for r in eval_records if r.get("avg_nli_entailment") is not None]

    passed_count = sum(
        1 for r in eval_records
        if r.get("validation_status") in ("passed", "passed_with_warning", "passed_with_outlier_caveat")
    )
    outlier_count = sum(1 for r in eval_records if r.get("has_outlier_only_sentence"))

    return {
        "mean_citation_validity": float(np.mean(validities)),
        "mean_citation_coverage": float(np.mean(coverages)),
        "mean_nli_entailment": float(np.mean(entailments)) if entailments else 0.0,
        "nli_p10": float(np.percentile(entailments, 10)) if entailments else 0.0,
        "nli_p50": float(np.percentile(entailments, 50)) if entailments else 0.0,
        "nli_p90": float(np.percentile(entailments, 90)) if entailments else 0.0,
        "validation_pass_rate": float(passed_count / len(eval_records)),
        "outlier_sentence_count": outlier_count,
        "total_evaluated": len(eval_records),
    }
