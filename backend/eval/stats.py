"""
D:\\CarePilotAI\\backend\\eval\\stats.py

Statistical computing layer for CarePilot AI Pillar C evaluation.
Implements shared statistical methods per Master Spec Section 8:
  - Wilson score interval for binomial proportions (e.g. HIGH FN rate, Red-Flag recall)
  - McNemar test for paired binary classification comparisons (e.g. Full vs No-Classifier)
  - Wilcoxon signed-rank test for paired continuous outcomes (e.g. Faithfulness, Latency)
  - Holm-Bonferroni step-down correction for multiple comparisons
  - Bootstrap confidence intervals for complex estimators (e.g. Weighted Edit Burden)
"""
from __future__ import annotations

import math
from typing import Sequence
import numpy as np
from scipy import stats


def wilson_score_interval(
    successes: int,
    total: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """
    Computes the Wilson score confidence interval for a binomial proportion.
    Handles edge cases (0% or 100%) gracefully without collapsing to zero width.

    Args:
        successes: Number of positive outcomes (e.g., false negatives or detected red flags).
        total: Sample size n.
        confidence: Desired confidence level (default 0.95).

    Returns:
        (lower_bound, upper_bound) tuple clamped to [0.0, 1.0].
    """
    if total <= 0:
        return (0.0, 0.0)

    p_hat = successes / total
    alpha = 1.0 - confidence
    z = stats.norm.ppf(1.0 - alpha / 2.0)
    z2 = z * z

    denominator = 1.0 + z2 / total
    center = (p_hat + z2 / (2.0 * total)) / denominator
    half_width = (
        z * math.sqrt((p_hat * (1.0 - p_hat) + z2 / (4.0 * total)) / total)
    ) / denominator

    lower = max(0.0, center - half_width)
    upper = min(1.0, center + half_width)
    return (float(lower), float(upper))


def mcnemar_test(
    table: tuple[tuple[int, int], tuple[int, int]] | Sequence[Sequence[int]],
    continuity_correction: bool = True,
) -> tuple[float, float]:
    """
    Computes McNemar's test for paired binary outcomes.
    Contingency table format:
                 Model B Correct    Model B Incorrect
      Model A Correct       b00                b01
      Model A Incorrect     b10                b11

    Discordant cells are b01 (A correct, B wrong) and b10 (A wrong, B correct).

    Returns:
        (statistic, p_value) tuple.
    """
    b01 = table[0][1]
    b10 = table[1][0]
    total_discordant = b01 + b10

    if total_discordant == 0:
        return (0.0, 1.0)

    # For small discordant counts (< 25), exact binomial test is preferred
    if total_discordant < 25:
        # Exact two-sided binomial test under H0: p = 0.5
        res = stats.binomtest(b01, n=total_discordant, p=0.5, alternative="two-sided")
        return (float(abs(b01 - b10)), float(res.pvalue))

    # Asymptotic chi-square test with optional Edwards continuity correction
    diff = abs(b01 - b10)
    if continuity_correction:
        diff = max(0.0, diff - 1.0)

    chi2_stat = (diff ** 2) / total_discordant
    p_val = stats.chi2.sf(chi2_stat, df=1)
    return (float(chi2_stat), float(p_val))


def wilcoxon_signed_rank(
    x: Sequence[float],
    y: Sequence[float],
    zero_method: str = "wilcox",
) -> tuple[float, float]:
    """
    Computes Wilcoxon signed-rank test for paired continuous samples.
    Used for comparing continuous metrics (faithfulness scores, latencies) across ablation pairs.

    Returns:
        (statistic, p_value) tuple. Returns (0.0, 1.0) if all paired differences are 0.
    """
    diffs = np.asarray(x, dtype=float) - np.asarray(y, dtype=float)
    non_zeros = diffs[diffs != 0]

    if len(non_zeros) == 0:
        return (0.0, 1.0)

    res = stats.wilcoxon(x, y, zero_method=zero_method, alternative="two-sided")
    return (float(res.statistic), float(res.pvalue))


def holm_bonferroni_correction(
    p_values: Sequence[float],
) -> list[float]:
    """
    Applies Holm-Bonferroni step-down procedure to adjust p-values for multiple hypothesis testing.
    Ensures Family-Wise Error Rate (FWER) control.

    Returns:
        List of adjusted p-values in the original input order, capped at 1.0.
    """
    m = len(p_values)
    if m == 0:
        return []

    # Sort indices by original p-value ascending
    indexed_p = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted = [0.0] * m

    cum_max = 0.0
    for rank, (orig_idx, p_val) in enumerate(indexed_p):
        multiplier = m - rank
        p_adj = min(1.0, p_val * multiplier)
        # Monotonicity enforcement
        p_adj = max(cum_max, p_adj)
        cum_max = p_adj
        adjusted[orig_idx] = float(min(1.0, p_adj))

    return adjusted


def bootstrap_ci(
    data: Sequence[float],
    statistic_fn=np.mean,
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """
    Calculates non-parametric bootstrap percentile confidence interval.
    Useful for non-normal metrics like weighted edit burden (W) and EDR.

    Returns:
        (ci_lower, ci_upper) tuple.
    """
    arr = np.asarray(data, dtype=float)
    if len(arr) == 0:
        return (0.0, 0.0)
    if len(arr) == 1:
        val = float(statistic_fn(arr))
        return (val, val)

    rng = np.random.default_rng(seed)
    boot_stats = np.empty(n_boot)

    for i in range(n_boot):
        sample = rng.choice(arr, size=len(arr), replace=True)
        boot_stats[i] = statistic_fn(sample)

    alpha = 1.0 - confidence
    lower = np.percentile(boot_stats, 100.0 * (alpha / 2.0))
    upper = np.percentile(boot_stats, 100.0 * (1.0 - alpha / 2.0))
    return (float(lower), float(upper))


def cluster_bootstrap_ci(
    data: Sequence[float],
    cluster_ids: Sequence[Any],
    statistic_fn=np.mean,
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """
    Calculates non-parametric cluster bootstrap percentile confidence interval.
    Resamples whole clusters (e.g. scenario_family) with replacement to account
    for intra-cluster correlation across queries within the same scenario.

    Args:
        data: Sequence of numeric observations.
        cluster_ids: Sequence of cluster identifiers corresponding to data.
        statistic_fn: Estimator function applied to concatenated cluster values.
        n_boot: Number of bootstrap resamples (default 2000).
        confidence: Confidence level (default 0.95).
        seed: Random seed for reproducibility (default 42).

    Returns:
        (ci_lower, ci_upper) tuple.
    """
    if len(data) != len(cluster_ids):
        raise ValueError("data and cluster_ids must have identical length")

    arr_data = np.asarray(data, dtype=float)
    if len(arr_data) == 0:
        return (0.0, 0.0)

    # Group data by cluster
    cluster_map: dict[Any, list[float]] = {}
    for val, cid in zip(arr_data, cluster_ids):
        cluster_map.setdefault(cid, []).append(val)

    unique_clusters = list(cluster_map.keys())
    k_clusters = len(unique_clusters)

    if k_clusters <= 1:
        val = float(statistic_fn(arr_data))
        return (val, val)

    rng = np.random.default_rng(seed)
    boot_stats = np.empty(n_boot)

    for i in range(n_boot):
        sampled_cids = rng.choice(unique_clusters, size=k_clusters, replace=True)
        sample_vals = []
        for cid in sampled_cids:
            sample_vals.extend(cluster_map[cid])
        boot_stats[i] = statistic_fn(sample_vals)

    alpha = 1.0 - confidence
    lower = np.percentile(boot_stats, 100.0 * (alpha / 2.0))
    upper = np.percentile(boot_stats, 100.0 * (1.0 - alpha / 2.0))
    return (float(lower), float(upper))
