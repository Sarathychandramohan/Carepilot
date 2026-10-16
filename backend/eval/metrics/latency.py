"""
D:\\CarePilotAI\\backend\\eval\\metrics\\latency.py

Latency and Throughput evaluation module.
Extracts per-stage and total latencies across evaluation runs:
  - Total pipeline latency percentiles (p50, p95, p99, mean)
  - LLM generation latency breakdown
  - Queries per second (throughput)
"""
from __future__ import annotations

from typing import Any, Sequence
import numpy as np


def compute_latency_metrics(
    generation_latencies_ms: Sequence[float | int],
    total_durations_s: Sequence[float] | None = None,
) -> dict[str, float]:
    """
    Computes latency distributions for pipeline stages.
    """
    if len(generation_latencies_ms) == 0:
        return {
            "generation_p50_ms": 0.0,
            "generation_p95_ms": 0.0,
            "generation_p99_ms": 0.0,
            "generation_mean_ms": 0.0,
            "total_queries": 0,
        }

    arr_gen = np.asarray(generation_latencies_ms, dtype=float)

    results: dict[str, float] = {
        "generation_p50_ms": float(np.percentile(arr_gen, 50)),
        "generation_p95_ms": float(np.percentile(arr_gen, 95)),
        "generation_p99_ms": float(np.percentile(arr_gen, 99)),
        "generation_mean_ms": float(np.mean(arr_gen)),
        "total_queries": len(arr_gen),
    }

    if total_durations_s and len(total_durations_s) > 0:
        arr_tot = np.asarray(total_durations_s, dtype=float)
        results["total_p50_s"] = float(np.percentile(arr_tot, 50))
        results["total_p95_s"] = float(np.percentile(arr_tot, 95))
        results["total_mean_s"] = float(np.mean(arr_tot))

    return results
