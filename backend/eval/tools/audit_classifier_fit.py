"""
backend/eval/tools/audit_classifier_fit.py

Audits the classifier training code and evaluates the shipped classifiers
(backend/models/intent_classifier.pkl and urgency_classifier.pkl) on silver-dev and silver-test.
Prints confusion matrices and per-class precision/recall for intent and urgency.
"""
from __future__ import annotations

import json
from pathlib import Path
from sklearn.metrics import confusion_matrix, classification_report
from backend.app.pipeline.classify import classify_intent, classify_urgency

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SILVER_PATH = PROJECT_ROOT / "data" / "queries" / "silver.jsonl"


def evaluate_split(split_name: str, queries: list[dict]):
    print(f"\n{'=' * 80}")
    print(f"EVALUATING SHIPPED CLASSIFIERS ON SILVER-{split_name.upper()} (N={len(queries)})")
    print(f"{'=' * 80}")

    true_intents = []
    pred_intents = []
    true_urgencies = []
    pred_urgencies = []

    for q in queries:
        text = q["query_text"]
        true_intents.append(q["intent_label"])
        true_urgencies.append(q["urgency_label"])

        res_intent = classify_intent(text)
        pred_intents.append(str(res_intent["intent"]))

        # Use precomputed embedding from classify_intent to classify_urgency
        emb = res_intent.get("embedding")
        res_urgency = classify_urgency(text, embedding=emb)
        pred_urgencies.append(str(res_urgency["urgency_classifier"]))

    # 1. Intent Evaluation
    print(f"\n--- [1] INTENT CLASSIFICATION: SILVER-{split_name.upper()} ---")
    intent_classes = sorted(list(set(true_intents) | set(pred_intents)))
    cm_intent = confusion_matrix(true_intents, pred_intents, labels=intent_classes)
    
    print("\nConfusion Matrix (Rows=True, Cols=Predicted):")
    header = f"{'':<28} " + " ".join(f"{c[:10]:>10}" for c in intent_classes)
    print(header)
    for cls_name, row in zip(intent_classes, cm_intent):
        row_str = " ".join(f"{val:>10}" for val in row)
        print(f"{cls_name:<28} {row_str}")

    print("\nPer-Class Classification Report:")
    print(classification_report(true_intents, pred_intents, labels=intent_classes, digits=4, zero_division=0))

    # 2. Urgency Evaluation
    print(f"\n--- [2] URGENCY CLASSIFICATION: SILVER-{split_name.upper()} ---")
    urgency_classes = ["routine", "soon", "urgent"]
    cm_urgency = confusion_matrix(true_urgencies, pred_urgencies, labels=urgency_classes)

    print("\nConfusion Matrix (Rows=True, Cols=Predicted):")
    header = f"{'':<15} " + " ".join(f"{c:>10}" for c in urgency_classes)
    print(header)
    for cls_name, row in zip(urgency_classes, cm_urgency):
        row_str = " ".join(f"{val:>10}" for val in row)
        print(f"{cls_name:<15} {row_str}")

    print("\nPer-Class Classification Report:")
    print(classification_report(true_urgencies, pred_urgencies, labels=urgency_classes, digits=4, zero_division=0))


def main():
    with open(SILVER_PATH, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    dev_queries = [r for r in rows if r.get("split") == "dev"]
    test_queries = [r for r in rows if r.get("split") == "test"]

    evaluate_split("dev", dev_queries)
    evaluate_split("test", test_queries)


if __name__ == "__main__":
    main()
