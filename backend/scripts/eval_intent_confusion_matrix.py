import json
import pickle
from pathlib import Path
from sklearn.metrics import confusion_matrix, classification_report
from sentence_transformers import SentenceTransformer

def main():
    root = Path(__file__).resolve().parents[2]
    model_path = root / "backend" / "models" / "intent_classifier.pkl"
    with open(model_path, "rb") as f:
        clf_data = pickle.load(f)
    clf = clf_data["model"]
    classes = list(clf.classes_)

    silver_path = root / "data" / "queries" / "silver.jsonl"
    with open(silver_path, "r", encoding="utf-8") as f:
        silver = [json.loads(line) for line in f]

    test_set = [s for s in silver if s.get("split") == "test"]
    print(f"Test set size: {len(test_set)}")

    embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")
    texts = [s["query_text"] for s in test_set]
    y_true = [s["intent_label"] for s in test_set]

    X = embedder.encode(texts, normalize_embeddings=True)
    y_pred = clf.predict(X)

    cm = confusion_matrix(y_true, y_pred, labels=classes)
    header = f"{'True Intent':<24}" + "".join([f"{c:<24}" for c in classes])
    sep = "-" * len(header)
    print("\n=== CONFUSION MATRIX (Test Split, N=1040) ===")
    print(header)
    print(sep)
    for i, label in enumerate(classes):
        row_str = f"{label:<24}" + "".join([f"{cm[i, j]:<24}" for j in range(len(classes))])
        print(row_str)
    print(sep)

    print("\n=== PER-CLASS CLASSIFICATION REPORT ===")
    print(classification_report(y_true, y_pred, target_names=classes, digits=4))

    # Also breakdown symptom_report predictions by scenario_family
    symptom_test = [s for s in test_set if s.get("intent_label") == "symptom_report"]
    print("\n=== BREAKDOWN OF SYMPTOM_REPORT TEST FAMILIES ===")
    for fam in set(s["scenario_family"] for s in symptom_test):
        fam_items = [s for s in symptom_test if s["scenario_family"] == fam]
        fam_texts = [s["query_text"] for s in fam_items]
        fam_X = embedder.encode(fam_texts, normalize_embeddings=True)
        fam_pred = clf.predict(fam_X)
        pred_dist = {}
        for p in fam_pred:
            pred_dist[p] = pred_dist.get(p, 0) + 1
        print(f"Family {fam} (n={len(fam_items)}): predictions = {pred_dist}")

if __name__ == "__main__":
    main()
