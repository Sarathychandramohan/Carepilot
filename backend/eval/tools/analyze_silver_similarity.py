"""
backend/eval/tools/analyze_silver_similarity.py

Computes cross-split semantic similarity for silver dataset:
- For each silver-TEST query: max cosine (mean-centered BGE) to silver-TRAIN and to silver-DEV.
  Prints fraction >= 0.60 and >= 0.80, overall and per scenario_family.
- For each silver-DEV query: max cosine to silver-TRAIN.
  Prints fraction >= 0.60 and >= 0.80, overall and per scenario_family.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer

from backend.eval.diversity_report import strip_greetings_and_signoffs, get_corpus_mean

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_PATH = PROJECT_ROOT / "data" / "queries" / "silver.jsonl"


def main():
    print("Loading silver queries...")
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    train_rows = [r for r in rows if r.get("split") == "train"]
    dev_rows = [r for r in rows if r.get("split") == "dev"]
    test_rows = [r for r in rows if r.get("split") == "test"]

    print(f"Loaded: train={len(train_rows)}, dev={len(dev_rows)}, test={len(test_rows)}")

    print("Loading BAAI/bge-small-en-v1.5 and mean vector...")
    model = SentenceTransformer("BAAI/bge-small-en-v1.5", local_files_only=True)
    mean_vec = get_corpus_mean()

    def encode_and_center(items: list[dict]) -> np.ndarray:
        texts = [strip_greetings_and_signoffs(r["query_text"]) for r in items]
        raw = model.encode(texts, batch_size=128, normalize_embeddings=True, show_progress_bar=False)
        c = raw - mean_vec
        norms = np.linalg.norm(c, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return c / norms

    print("Encoding splits...")
    train_embs = encode_and_center(train_rows)
    dev_embs = encode_and_center(dev_rows)
    test_embs = encode_and_center(test_rows)

    # ---------------------------------------------------------
    # 1. Silver-TEST vs Silver-TRAIN and Silver-DEV
    # ---------------------------------------------------------
    print("\n" + "=" * 80)
    print("SILVER-TEST -> SILVER-TRAIN & SILVER-DEV MAX COSINE SIMILARITY")
    print("=" * 80)

    # test vs train sim matrix: shape (len(test), len(train))
    sim_test_train = np.dot(test_embs, train_embs.T)
    max_sim_test_train = np.max(sim_test_train, axis=1)

    # test vs dev sim matrix: shape (len(test), len(dev))
    sim_test_dev = np.dot(test_embs, dev_embs.T)
    max_sim_test_dev = np.max(sim_test_dev, axis=1)

    # Overall test metrics
    n_test = len(test_rows)
    print(f"\n--- OVERALL SILVER-TEST (N={n_test}) ---")
    print("To Silver-TRAIN:")
    print(f"  Max sim range: min={max_sim_test_train.min():.4f}, mean={max_sim_test_train.mean():.4f}, max={max_sim_test_train.max():.4f}")
    print(f"  Fraction >= 0.60: {np.mean(max_sim_test_train >= 0.60):.4f} ({np.sum(max_sim_test_train >= 0.60)}/{n_test})")
    print(f"  Fraction >= 0.80: {np.mean(max_sim_test_train >= 0.80):.4f} ({np.sum(max_sim_test_train >= 0.80)}/{n_test})")

    print("\nTo Silver-DEV:")
    print(f"  Max sim range: min={max_sim_test_dev.min():.4f}, mean={max_sim_test_dev.mean():.4f}, max={max_sim_test_dev.max():.4f}")
    print(f"  Fraction >= 0.60: {np.mean(max_sim_test_dev >= 0.60):.4f} ({np.sum(max_sim_test_dev >= 0.60)}/{n_test})")
    print(f"  Fraction >= 0.80: {np.mean(max_sim_test_dev >= 0.80):.4f} ({np.sum(max_sim_test_dev >= 0.80)}/{n_test})")

    # Per scenario family for TEST
    test_families = defaultdict(list)
    for idx, r in enumerate(test_rows):
        test_families[r.get("scenario_family", "unknown")].append(idx)

    print("\n--- PER SCENARIO FAMILY: SILVER-TEST TO SILVER-TRAIN ---")
    print(f"{'Scenario Family':<32} | {'Count':<5} | {'Mean Max':<8} | {'Frac >= 0.60':<12} | {'Frac >= 0.80':<12}")
    print("-" * 80)
    for fam in sorted(test_families.keys()):
        idxs = test_families[fam]
        sims = max_sim_test_train[idxs]
        f60 = np.mean(sims >= 0.60)
        f80 = np.mean(sims >= 0.80)
        print(f"{fam:<32} | {len(idxs):<5} | {sims.mean():<8.4f} | {f60:<12.4f} | {f80:<12.4f}")

    print("\n--- PER SCENARIO FAMILY: SILVER-TEST TO SILVER-DEV ---")
    print(f"{'Scenario Family':<32} | {'Count':<5} | {'Mean Max':<8} | {'Frac >= 0.60':<12} | {'Frac >= 0.80':<12}")
    print("-" * 80)
    for fam in sorted(test_families.keys()):
        idxs = test_families[fam]
        sims = max_sim_test_dev[idxs]
        f60 = np.mean(sims >= 0.60)
        f80 = np.mean(sims >= 0.80)
        print(f"{fam:<32} | {len(idxs):<5} | {sims.mean():<8.4f} | {f60:<12.4f} | {f80:<12.4f}")

    # ---------------------------------------------------------
    # 2. Silver-DEV vs Silver-TRAIN
    # ---------------------------------------------------------
    print("\n" + "=" * 80)
    print("SILVER-DEV -> SILVER-TRAIN MAX COSINE SIMILARITY")
    print("=" * 80)

    sim_dev_train = np.dot(dev_embs, train_embs.T)
    max_sim_dev_train = np.max(sim_dev_train, axis=1)

    n_dev = len(dev_rows)
    print(f"\n--- OVERALL SILVER-DEV (N={n_dev}) TO SILVER-TRAIN ---")
    print(f"  Max sim range: min={max_sim_dev_train.min():.4f}, mean={max_sim_dev_train.mean():.4f}, max={max_sim_dev_train.max():.4f}")
    print(f"  Fraction >= 0.60: {np.mean(max_sim_dev_train >= 0.60):.4f} ({np.sum(max_sim_dev_train >= 0.60)}/{n_dev})")
    print(f"  Fraction >= 0.80: {np.mean(max_sim_dev_train >= 0.80):.4f} ({np.sum(max_sim_dev_train >= 0.80)}/{n_dev})")

    dev_families = defaultdict(list)
    for idx, r in enumerate(dev_rows):
        dev_families[r.get("scenario_family", "unknown")].append(idx)

    print("\n--- PER SCENARIO FAMILY: SILVER-DEV TO SILVER-TRAIN ---")
    print(f"{'Scenario Family':<32} | {'Count':<5} | {'Mean Max':<8} | {'Frac >= 0.60':<12} | {'Frac >= 0.80':<12}")
    print("-" * 80)
    for fam in sorted(dev_families.keys()):
        idxs = dev_families[fam]
        sims = max_sim_dev_train[idxs]
        f60 = np.mean(sims >= 0.60)
        f80 = np.mean(sims >= 0.80)
        print(f"{fam:<32} | {len(idxs):<5} | {sims.mean():<8.4f} | {f60:<12.4f} | {f80:<12.4f}")


if __name__ == "__main__":
    main()
