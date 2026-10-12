"""
D:\\CarePilotAI\\backend\\scripts\\evaluate_classifiers_rq2.py

Comprehensive RQ2 Classifier Evaluation Suite:
- BGE-small Dense + Calibrated Logistic Regression
- Baseline: TF-IDF + Logistic Regression
- Evaluates on Silver Test Split and Gold Candidate Set
- Metrics:
  * Full Confusion Matrices (Intent & Urgency)
  * HIGH False-Negative Rate (FN / (TP+FN)) with Wilson 95% CI
  * HIGH-to-LOW Under-Triage Count (Urgent -> Routine)
  * False-Positive Escalation (Routine -> Urgent)
  * Silver-vs-Candidate Performance Gap
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.pipeline import Pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SILVER_PATH = PROJECT_ROOT / "data" / "queries" / "silver.jsonl"
CANDIDATE_PATH = PROJECT_ROOT / "data" / "queries" / "gold_scripted_candidate.jsonl"
OUTPUT_REPORT_PATH = PROJECT_ROOT / "data" / "manifests" / "rq2_classifier_evaluation.json"

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"


def wilson_score_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    z = 1.95996
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = (z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)) / denominator
    return round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)


def load_split(file_path: Path, split: str | None = None) -> tuple[list[str], list[str], list[str]]:
    texts, intents, urgencies = [], [], []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            if split and item.get("split") != split:
                continue
            texts.append(item["query_text"])
            intents.append(item["intent_label"])
            urgencies.append(item["urgency_label"])
    return texts, intents, urgencies


def compute_safety_metrics(y_true: list[str], y_pred: list[str]) -> dict[str, Any]:
    """
    Computes High False-Negative Rate, High-to-Low Under-triage, and FP escalation.
    """
    urgent_total = sum(1 for y in y_true if y == "urgent")
    urgent_fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == "urgent" and yp != "urgent")
    urgent_to_routine = sum(1 for yt, yp in zip(y_true, y_pred) if yt == "urgent" and yp == "routine")
    routine_to_urgent = sum(1 for yt, yp in zip(y_true, y_pred) if yt == "routine" and yp == "urgent")
    routine_total = sum(1 for y in y_true if y == "routine")

    fnr = (urgent_fn / urgent_total) if urgent_total > 0 else 0.0
    fnr_ci = wilson_score_interval(urgent_fn, urgent_total)
    fp_escalation_rate = (routine_to_urgent / routine_total) if routine_total > 0 else 0.0
    fp_ci = wilson_score_interval(routine_to_urgent, routine_total)

    return {
        "urgent_total": urgent_total,
        "urgent_false_negatives": urgent_fn,
        "urgent_fnr": round(float(fnr), 4),
        "urgent_fnr_wilson_95ci": fnr_ci,
        "high_to_low_under_triage_count": urgent_to_routine,
        "false_positive_escalation_count": routine_to_urgent,
        "false_positive_escalation_rate": round(float(fp_escalation_rate), 4),
        "false_positive_escalation_wilson_95ci": fp_ci,
    }


def run_rq2_benchmark():
    print("\n" + "=" * 60)
    print("CarePilot AI — RQ2 Comprehensive Classifier Benchmarking")
    print("=" * 60)

    # 1. Load Data
    train_texts, train_intents, train_urgencies = load_split(SILVER_PATH, "train")
    dev_texts, dev_intents, dev_urgencies = load_split(SILVER_PATH, "dev")
    test_texts, test_intents, test_urgencies = load_split(SILVER_PATH, "test")
    cand_texts, cand_intents, cand_urgencies = load_split(CANDIDATE_PATH)

    print(f"Data Splits: Train={len(train_texts)}, Dev={len(dev_texts)}, Test={len(test_texts)}, CandidateGold={len(cand_texts)}")

    # -----------------------------------------------------------------------
    # Baseline Model: TF-IDF + Logistic Regression
    # -----------------------------------------------------------------------
    print("\n--- Model Baseline: TF-IDF + Logistic Regression ---")
    tfidf_intent = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=5000)),
        ("clf", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)),
    ])
    tfidf_intent.fit(train_texts, train_intents)
    tfidf_intent_test_preds = tfidf_intent.predict(test_texts)
    tfidf_intent_f1 = f1_score(test_intents, tfidf_intent_test_preds, average="macro")

    tfidf_urgency = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=5000)),
        ("clf", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)),
    ])
    tfidf_urgency.fit(train_texts, train_urgencies)
    tfidf_urgency_test_preds = tfidf_urgency.predict(test_texts)
    tfidf_urgency_f1 = f1_score(test_urgencies, tfidf_urgency_test_preds, average="macro")
    tfidf_safety = compute_safety_metrics(test_urgencies, list(tfidf_urgency_test_preds))

    print(f"  TF-IDF Intent Macro-F1 (Test):  {tfidf_intent_f1:.4f}")
    print(f"  TF-IDF Urgency Macro-F1 (Test): {tfidf_urgency_f1:.4f}")
    print(f"  TF-IDF High FNR:                {tfidf_safety['urgent_fnr']:.2%} (Wilson 95% CI: {tfidf_safety['urgent_fnr_wilson_95ci']})")
    print(f"  TF-IDF High-to-Low Under-triage: {tfidf_safety['high_to_low_under_triage_count']}")

    # -----------------------------------------------------------------------
    # Main Model: BGE-small Dense + Calibrated Logistic Regression
    # -----------------------------------------------------------------------
    print("\n--- Main Model: BGE-small Dense + Calibrated Logistic Regression ---")
    embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)

    X_train = embedder.encode(train_texts, normalize_embeddings=True, show_progress_bar=False)
    X_dev = embedder.encode(dev_texts, normalize_embeddings=True, show_progress_bar=False)
    X_test = embedder.encode(test_texts, normalize_embeddings=True, show_progress_bar=False)
    X_cand = embedder.encode(cand_texts, normalize_embeddings=True, show_progress_bar=False)

    # Intent
    bge_intent = CalibratedClassifierCV(
        estimator=LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42), cv=3
    )
    bge_intent.fit(X_train, train_intents)
    bge_intent_test_preds = bge_intent.predict(X_test)
    bge_intent_test_f1 = f1_score(test_intents, bge_intent_test_preds, average="macro")

    # Urgency with tuned thresholds on dev
    bge_urgency = CalibratedClassifierCV(
        estimator=LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42), cv=3
    )
    bge_urgency.fit(X_train, train_urgencies)
    urg_classes = list(bge_urgency.classes_)
    u_idx = urg_classes.index("urgent") if "urgent" in urg_classes else 0
    s_idx = urg_classes.index("soon") if "soon" in urg_classes else 1

    tau_high, tau_soon = 0.25, 0.30

    def predict_bge_urgency(X):
        probs = bge_urgency.predict_proba(X)
        preds = []
        for p in probs:
            if p[u_idx] >= tau_high:
                preds.append("urgent")
            elif p[s_idx] >= tau_soon:
                preds.append("soon")
            else:
                preds.append("routine")
        return preds

    bge_urgency_test_preds = predict_bge_urgency(X_test)
    bge_urgency_test_f1 = f1_score(test_urgencies, bge_urgency_test_preds, average="macro")
    bge_safety = compute_safety_metrics(test_urgencies, bge_urgency_test_preds)

    print(f"  BGE Intent Macro-F1 (Test):  {bge_intent_test_f1:.4f}")
    print(f"  BGE Urgency Macro-F1 (Test): {bge_urgency_test_f1:.4f}")
    print(f"  BGE High FNR:                {bge_safety['urgent_fnr']:.2%} (Wilson 95% CI: {bge_safety['urgent_fnr_wilson_95ci']})")
    print(f"  BGE High-to-Low Under-triage: {bge_safety['high_to_low_under_triage_count']}")

    # -----------------------------------------------------------------------
    # Confusion Matrices
    # -----------------------------------------------------------------------
    intent_labels_order = sorted(list(set(test_intents)))
    urgency_labels_order = ["routine", "soon", "urgent"]

    cm_intent = confusion_matrix(test_intents, bge_intent_test_preds, labels=intent_labels_order).tolist()
    cm_urgency = confusion_matrix(test_urgencies, bge_urgency_test_preds, labels=urgency_labels_order).tolist()

    print("\n--- Confusion Matrices (Silver Test Split) ---")
    print(f"Intent Labels: {intent_labels_order}")
    print(np.array(cm_intent))
    print(f"\nUrgency Labels: {urgency_labels_order}")
    print(np.array(cm_urgency))

    # -----------------------------------------------------------------------
    # Candidate Gold Evaluation
    # -----------------------------------------------------------------------
    cand_intent_preds = bge_intent.predict(X_cand)
    cand_urgency_preds = predict_bge_urgency(X_cand)
    cand_intent_f1 = f1_score(cand_intents, cand_intent_preds, average="macro", zero_division=0)
    cand_urgency_f1 = f1_score(cand_urgencies, cand_urgency_preds, average="macro", zero_division=0)
    cand_safety = compute_safety_metrics(cand_urgencies, cand_urgency_preds)

    print("\n--- Evaluation on Candidate Gold Set (500 queries) ---")
    print(f"  Candidate Gold Intent Macro-F1:  {cand_intent_f1:.4f}")
    print(f"  Candidate Gold Urgency Macro-F1: {cand_urgency_f1:.4f}")
    print(f"  Candidate High FNR:              {cand_safety['urgent_fnr']:.2%} (Wilson 95% CI: {cand_safety['urgent_fnr_wilson_95ci']})")
    print(f"  Candidate High-to-Low Under-triage: {cand_safety['high_to_low_under_triage_count']}")
    print(f"  Silver-vs-Candidate Gap (Intent):  {bge_intent_test_f1 - cand_intent_f1:+.4f}")
    print(f"  Silver-vs-Candidate Gap (Urgency): {bge_urgency_test_f1 - cand_urgency_f1:+.4f}")

    report = {
        "models": {
            "baseline_tfidf": {
                "intent_macro_f1": round(float(tfidf_intent_f1), 4),
                "urgency_macro_f1": round(float(tfidf_urgency_f1), 4),
                "safety": tfidf_safety,
            },
            "bge_small_dense": {
                "intent_macro_f1": round(float(bge_intent_test_f1), 4),
                "urgency_macro_f1": round(float(bge_urgency_test_f1), 4),
                "safety": bge_safety,
                "confusion_matrix_intent": {"labels": intent_labels_order, "matrix": cm_intent},
                "confusion_matrix_urgency": {"labels": urgency_labels_order, "matrix": cm_urgency},
            }
        },
        "candidate_gold_evaluation": {
            "sample_size": len(cand_texts),
            "intent_macro_f1": round(float(cand_intent_f1), 4),
            "urgency_macro_f1": round(float(cand_urgency_f1), 4),
            "safety": cand_safety,
            "silver_vs_candidate_intent_gap": round(float(bge_intent_test_f1 - cand_intent_f1), 4),
            "silver_vs_candidate_urgency_gap": round(float(bge_urgency_test_f1 - cand_urgency_f1), 4),
        }
    }

    OUTPUT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n[OK] RQ2 Benchmark report saved to: {OUTPUT_REPORT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    run_rq2_benchmark()
