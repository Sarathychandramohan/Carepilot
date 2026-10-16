"""
D:\\CarePilotAI\\backend\\eval\\metrics\\retrieval.py

Retrieval benchmark metrics module (Table T2).
Computes:
  - Hit@k (Hit@3, Hit@5)
  - Mean Reciprocal Rank (MRR)
  - Dense vs BM25 vs Hybrid fusion metrics
  - EHR candidate recall and precision
  - Fusion balance (share of citations originating from EHR vs KB)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence
import numpy as np


def compute_hit_at_k(
    retrieved_doc_ids: Sequence[str],
    expected_doc_ids: Sequence[str],
    k: int = 3,
) -> float:
    """Returns 1.0 if any expected doc ID appears in top-k retrieved, else 0.0."""
    if not expected_doc_ids:
        return 0.0
    top_k = retrieved_doc_ids[:k]
    expected_set = set(expected_doc_ids)
    return 1.0 if any(doc in expected_set for doc in top_k) else 0.0


def compute_reciprocal_rank(
    retrieved_doc_ids: Sequence[str],
    expected_doc_ids: Sequence[str],
) -> float:
    """Returns 1 / rank of the first relevant document found (1-indexed), or 0.0."""
    if not expected_doc_ids:
        return 0.0
    expected_set = set(expected_doc_ids)
    for rank, doc_id in enumerate(retrieved_doc_ids, start=1):
        if doc_id in expected_set:
            return 1.0 / rank
    return 0.0


def compute_retrieval_metrics(
    eval_records: list[dict[str, Any]],
) -> dict[str, float]:
    """
    Computes aggregate Hit@3, Hit@5, MRR, and citation fusion balance across queries.

    Expected record format:
      {
        "retrieved_kb_doc_ids": list[str],
        "expected_kb_doc_ids": list[str],
        "ehr_citations_count": int,
        "kb_citations_count": int,
      }
    """
    if not eval_records:
        return {
            "hit_at_3": 0.0,
            "hit_at_5": 0.0,
            "mrr": 0.0,
            "ehr_citation_share": 0.0,
            "kb_citation_share": 0.0,
            "total_queries_evaluated": 0,
        }

    hits_3 = []
    hits_5 = []
    rrs = []
    total_ehr_cites = 0
    total_kb_cites = 0

    for rec in eval_records:
        retrieved = rec.get("retrieved_kb_doc_ids", [])
        expected = rec.get("expected_kb_doc_ids", [])
        if expected:
            hits_3.append(compute_hit_at_k(retrieved, expected, k=3))
            hits_5.append(compute_hit_at_k(retrieved, expected, k=5))
            rrs.append(compute_reciprocal_rank(retrieved, expected))

        total_ehr_cites += rec.get("ehr_citations_count", 0)
        total_kb_cites += rec.get("kb_citations_count", 0)

    total_citations = total_ehr_cites + total_kb_cites
    ehr_share = total_ehr_cites / total_citations if total_citations > 0 else 0.0
    kb_share = total_kb_cites / total_citations if total_citations > 0 else 0.0

    return {
        "hit_at_3": float(np.mean(hits_3)) if hits_3 else 0.0,
        "hit_at_5": float(np.mean(hits_5)) if hits_5 else 0.0,
        "mrr": float(np.mean(rrs)) if rrs else 0.0,
        "ehr_citation_share": float(ehr_share),
        "kb_citation_share": float(kb_share),
        "total_queries_evaluated": len(eval_records),
    }
