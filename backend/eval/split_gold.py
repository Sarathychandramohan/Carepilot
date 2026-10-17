"""
backend/eval/split_gold.py

Splits synthetic gold candidates into dev and test splits at the whole cluster level:
  - Clusters connected components with cosine >= 0.70 (using BAAI/bge-small-en-v1.5)
    and enforces that queries sharing the same scenario_id belong to the same cluster.
  - Assigns whole clusters to 'dev' or 'test' deterministically (seed 42).
  - Stratified across (intent_label, urgency_label).
  - Guarantees zero cluster and zero scenario leakage between dev and test.
  - Outputs: data/annotation/gold_dev.jsonl and data/annotation/gold_test.jsonl.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.eval.diversity_report import strip_greetings_and_signoffs
from backend.eval.import_synthetic_gold import get_diversity_embedder

DEFAULT_CANDIDATES_PATH = PROJECT_ROOT / "data" / "annotation" / "gold_synthetic_candidate.jsonl"
DEFAULT_DEV_PATH = PROJECT_ROOT / "data" / "annotation" / "gold_dev.jsonl"
DEFAULT_TEST_PATH = PROJECT_ROOT / "data" / "annotation" / "gold_test.jsonl"


def compute_clusters_and_scenarios(
    records: list[dict[str, Any]],
    threshold: float = 0.70,
    local_files_only: bool = True,
) -> list[list[int]]:
    """
    Compute cluster components at cosine >= threshold.
    Enforces that queries sharing the same scenario_id are united into the same component.
    """
    n = len(records)
    if n == 0:
        return []

    embedder = get_diversity_embedder(local_files_only=local_files_only)
    cleaned = [strip_greetings_and_signoffs(r["query_text"]) for r in records]
    embs = embedder.encode(cleaned, normalize_embeddings=True)

    adj = defaultdict(set)

    # 1. Edges based on cosine similarity
    for i in range(n):
        for j in range(i + 1, n):
            sim = float(np.dot(embs[i], embs[j]))
            if sim >= threshold:
                adj[i].add(j)
                adj[j].add(i)

    # 2. Edges based on identical scenario_id
    sc_map = defaultdict(list)
    for idx, r in enumerate(records):
        sc_map[r["scenario_id"]].append(idx)

    for idxs in sc_map.values():
        if len(idxs) > 1:
            for a in range(len(idxs)):
                for b in range(a + 1, len(idxs)):
                    adj[idxs[a]].add(idxs[b])
                    adj[idxs[b]].add(idxs[a])

    # Connected components
    visited = set()
    clusters = []
    for i in range(n):
        if i not in visited:
            comp = []
            queue = deque([i])
            visited.add(i)
            while queue:
                curr = queue.popleft()
                comp.append(curr)
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            clusters.append(sorted(comp))
    return clusters


def split_candidate_clusters(
    records: list[dict[str, Any]],
    clusters: list[list[int]],
    dev_ratio: float = 0.35,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Stratify and partition whole clusters into dev and test.
    Guarantees zero clusters span dev and test.
    """
    # Group clusters by primary stratum: (intent_label, urgency_label)
    strata: dict[tuple[str, str], list[list[int]]] = defaultdict(list)
    for comp in clusters:
        intents = [records[idx]["intent_label"] for idx in comp]
        urgencies = [records[idx]["urgency_label"] for idx in comp]
        primary_intent = max(set(intents), key=intents.count)
        primary_urgency = max(set(urgencies), key=urgencies.count)
        strata[(primary_intent, primary_urgency)].append(comp)

    rng = random.Random(seed)
    cluster_split: dict[int, str] = {}

    for (intent, urg), comp_list in sorted(strata.items()):
        # Deterministic ordering by first record scenario_id
        sorted_comps = sorted(
            comp_list,
            key=lambda c: (records[c[0]]["scenario_id"], records[c[0]]["query_id"]),
        )
        rng.shuffle(sorted_comps)

        n_comps = len(sorted_comps)
        n_dev = max(1, int(round(n_comps * dev_ratio))) if n_comps > 1 else (1 if rng.random() < dev_ratio else 0)

        for c_idx, comp in enumerate(sorted_comps):
            assigned_split = "dev" if c_idx < n_dev else "test"
            for row_idx in comp:
                cluster_split[row_idx] = assigned_split

    dev_records = []
    test_records = []

    for idx, r in enumerate(records):
        sp = cluster_split[idx]
        r_copy = dict(r)
        r_copy["split"] = sp
        if sp == "dev":
            dev_records.append(r_copy)
        else:
            test_records.append(r_copy)

    # Verification: zero clusters span dev and test
    for c_i, comp in enumerate(clusters):
        assigned_splits = {cluster_split[idx] for idx in comp}
        if len(assigned_splits) > 1:
            raise ValueError(f"Cluster {c_i} spans multiple splits: {assigned_splits}")

    # Verification: zero scenarios span dev and test
    sc_splits = defaultdict(set)
    for idx, r in enumerate(records):
        sc_splits[r["scenario_id"]].add(cluster_split[idx])
    for sc, sps in sc_splits.items():
        if len(sps) > 1:
            raise ValueError(f"Scenario '{sc}' spans multiple splits: {sps}")

    return dev_records, test_records


def split_gold_dataset(
    input_path: Path = DEFAULT_CANDIDATES_PATH,
    dev_path: Path = DEFAULT_DEV_PATH,
    test_path: Path = DEFAULT_TEST_PATH,
    dev_ratio: float = 0.35,
    seed: int = 42,
    local_files_only: bool = True,
) -> tuple[int, int]:
    """Execute cluster-level stratified split and write dev & test JSONL files."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input candidate file not found: {input_path}")

    records = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        raise ValueError(f"No records found in {input_path}")

    print(f"Loaded {len(records)} records from {input_path}")
    clusters = compute_clusters_and_scenarios(records, threshold=0.70, local_files_only=local_files_only)
    print(f"Computed {len(clusters)} near-duplicate & scenario clusters.")

    dev_records, test_records = split_candidate_clusters(
        records, clusters, dev_ratio=dev_ratio, seed=seed
    )

    dev_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dev_path, "w", encoding="utf-8") as df:
        for r in dev_records:
            df.write(json.dumps(r) + "\n")

    test_path.parent.mkdir(parents=True, exist_ok=True)
    with open(test_path, "w", encoding="utf-8") as tf:
        for r in test_records:
            tf.write(json.dumps(r) + "\n")

    # Update input file so its records reflect the assigned split
    with open(input_path, "w", encoding="utf-8") as f:
        for r in dev_records + test_records:
            f.write(json.dumps(r) + "\n")

    print(f"[OK] Wrote {len(dev_records)} queries -> {dev_path}")
    print(f"[OK] Wrote {len(test_records)} queries -> {test_path}")
    return len(dev_records), len(test_records)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Split gold candidates by cluster into dev and test.")
    parser.add_argument("--input", type=Path, default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--dev-out", type=Path, default=DEFAULT_DEV_PATH)
    parser.add_argument("--test-out", type=Path, default=DEFAULT_TEST_PATH)
    parser.add_argument("--dev-ratio", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    n_dev, n_test = split_gold_dataset(
        input_path=args.input,
        dev_path=args.dev_out,
        test_path=args.test_out,
        dev_ratio=args.dev_ratio,
        seed=args.seed,
    )
    print(f"\nFinal Split Counts: DEV = {n_dev}, TEST = {n_test}, TOTAL = {n_dev + n_test}")


if __name__ == "__main__":
    main()
