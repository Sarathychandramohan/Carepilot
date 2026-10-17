"""
backend/eval/tools/audit_classifier_fit.py

Audits the classifier training code and evaluates the shipped classifiers
(backend/models/intent_classifier.pkl and urgency_classifier.pkl).
Evaluates on silver-dev, silver-test overall, and silver-test leakage-free families.
Includes n distinct texts in every summary.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from sklearn.metrics import confusion_matrix, classification_report, accuracy_score, f1_score
from backend.app.pipeline.classify import classify_intent, classify_urgency

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SILVER_PATH = PROJECT_ROOT / "data" / "queries" / "silver.jsonl"

LEAKAGE_FREE_FAMILIES = {
    "SF-TEST-GENERAL-DIABETES",
    "SF-TEST-GENERAL-HYDRATION",
    "SF-TEST-SYMPTOM-ANAPHYLAXIS",
}


def evaluate_split(title: str, queries: list[dict]):
    distinct_texts = len(set(q["query_text"] for q in queries))
    print(f"\n{'=' * 80}")
    print(f"{title.upper()} (N={len(queries)}, n distinct texts={distinct_texts})")
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

        emb = res_intent.get("embedding")
        res_urgency = classify_urgency(text, embedding=emb)
        pred_urgencies.append(str(res_urgency["urgency_classifier"]))

    # 1. Intent Evaluation
    print(f"\n--- [1] INTENT CLASSIFICATION ---")
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
    print(f"\n--- [2] URGENCY CLASSIFICATION ---")
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

    return {
        "count": len(queries),
        "distinct": distinct_texts,
        "intent_acc": accuracy_score(true_intents, pred_intents),
        "intent_macro_f1": f1_score(true_intents, pred_intents, average="macro", zero_division=0),
        "urgency_acc": accuracy_score(true_urgencies, pred_urgencies),
        "urgency_macro_f1": f1_score(true_urgencies, pred_urgencies, average="macro", zero_division=0),
    }


def main():
    with open(SILVER_PATH, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    test_queries = [r for r in rows if r.get("split") == "test"]
    leakage_free_test = [r for r in test_queries if r.get("scenario_family") in LEAKAGE_FREE_FAMILIES]

    # Evaluate Silver-Test Overall
    res_all = evaluate_split("SILVER-TEST (ALL 8 FAMILIES)", test_queries)

    # Evaluate Silver-Test Leakage-Free Families
    res_clean = evaluate_split("SILVER-TEST (3 LEAKAGE-FREE FAMILIES)", leakage_free_test)

    # Per-Family Table for Silver-Test
    print(f"\n{'=' * 95}")
    print("SILVER-TEST PER-SCENARIO FAMILY SUMMARY TABLE")
    print(f"{'=' * 95}")
    print(f"{'Scenario Family':<32} | {'Total':>5} | {'Distinct':>8} | {'Intent Acc':>10} | {'Intent F1':>9} | {'Urg Acc':>8} | {'Urg F1':>8}")
    print("-" * 95)

    families = sorted(list(set(q["scenario_family"] for q in test_queries)))
    for fam in families:
        fam_qs = [q for q in test_queries if q["scenario_family"] == fam]
        d_count = len(set(q["query_text"] for q in fam_qs))
        t_int = [q["intent_label"] for q in fam_qs]
        p_int = [classify_intent(q["query_text"])["intent"] for q in fam_qs]
        t_urg = [q["urgency_label"] for q in fam_qs]
        p_urg = [classify_urgency(q["query_text"])["urgency_classifier"] for q in fam_qs]

        acc_i = accuracy_score(t_int, p_int)
        f1_i = f1_score(t_int, p_int, average="macro", zero_division=0)
        acc_u = accuracy_score(t_urg, p_urg)
        f1_u = f1_score(t_urg, p_urg, average="macro", zero_division=0)

        mark = " *" if fam in LEAKAGE_FREE_FAMILIES else "  "
        print(f"{fam:<30}{mark} | {len(fam_qs):5d} | {d_count:8d} | {acc_i:10.4f} | {f1_i:9.4f} | {acc_u:8.4f} | {f1_u:8.4f}")

    print("-" * 95)
    print("* = Leakage-Free Scenario Family (0% similarity >= 0.60 to silver-dev or silver-train)")


if __name__ == "__main__":
    main()
