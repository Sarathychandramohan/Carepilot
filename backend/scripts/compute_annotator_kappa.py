"""
D:\\CarePilotAI\\backend\\scripts\\compute_annotator_kappa.py

Computes Cohen's Kappa inter-annotator agreement between two independent
human annotator response files (CSV or JSONL).

Usage:
    python -m backend.scripts.compute_annotator_kappa --annotator1 annotator_A.csv --annotator2 annotator_B.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_annotations(file_path: Path) -> dict[str, dict[str, str]]:
    """Loads annotations keyed by query_id."""
    records = {}
    if file_path.suffix.lower() == ".csv":
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                qid = row["query_id"].strip()
                records[qid] = {
                    "intent": (row.get("intent_label") or "").strip().lower(),
                    "urgency": (row.get("urgency_label") or "").strip().lower(),
                    "needs_ehr": (row.get("needs_patient_ehr") or "").strip().lower(),
                }
    elif file_path.suffix.lower() == ".jsonl":
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    qid = item["query_id"].strip()
                    records[qid] = {
                        "intent": (item.get("intent_label") or "").strip().lower(),
                        "urgency": (item.get("urgency_label") or "").strip().lower(),
                        "needs_ehr": str(item.get("needs_patient_ehr", "")).strip().lower(),
                    }
    else:
        raise ValueError(f"Unsupported file extension: {file_path.suffix}")

    return records


def wilson_score_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    """Computes Wilson score interval for binomial proportion."""
    if total == 0:
        return 0.0, 0.0
    z = 1.95996  # 95% confidence
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = (z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)) / denominator
    return round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)


def main():
    parser = argparse.ArgumentParser(description="Compute Cohen's Kappa from 2 independent human annotators")
    parser.add_argument("--annotator1", type=Path, required=True, help="Path to Annotator 1 CSV or JSONL")
    parser.add_argument("--annotator2", type=Path, required=True, help="Path to Annotator 2 CSV or JSONL")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "manifests" / "human_annotation_kappa.json")
    args = parser.parse_args()

    if not args.annotator1.exists():
        print(f"ERROR: Annotator 1 file not found: {args.annotator1}", file=sys.stderr)
        sys.exit(1)
    if not args.annotator2.exists():
        print(f"ERROR: Annotator 2 file not found: {args.annotator2}", file=sys.stderr)
        sys.exit(1)

    ann1 = load_annotations(args.annotator1)
    ann2 = load_annotations(args.annotator2)

    common_ids = sorted(set(ann1.keys()) & set(ann2.keys()))
    if not common_ids:
        print("ERROR: Zero common query_ids found between the two files.", file=sys.stderr)
        sys.exit(1)

    intents1, intents2 = [], []
    urgencies1, urgencies2 = [], []
    ehr1, ehr2 = [], []

    for qid in common_ids:
        r1 = ann1[qid]
        r2 = ann2[qid]
        if r1["intent"] and r2["intent"]:
            intents1.append(r1["intent"])
            intents2.append(r2["intent"])
        if r1["urgency"] and r2["urgency"]:
            urgencies1.append(r1["urgency"])
            urgencies2.append(r2["urgency"])
        if r1["needs_ehr"] and r2["needs_ehr"]:
            ehr1.append(r1["needs_ehr"])
            ehr2.append(r2["needs_ehr"])

    kappa_intent = cohen_kappa_score(intents1, intents2)
    kappa_urgency = cohen_kappa_score(urgencies1, urgencies2, weights="linear")
    kappa_ehr = cohen_kappa_score(ehr1, ehr2) if ehr1 else 0.0

    # Agreement percentages
    intent_agree = sum(1 for a, b in zip(intents1, intents2) if a == b)
    urgency_agree = sum(1 for a, b in zip(urgencies1, urgencies2) if a == b)

    intent_ci = wilson_score_interval(intent_agree, len(intents1))
    urgency_ci = wilson_score_interval(urgency_agree, len(urgencies1))

    report = {
        "annotator_1_file": str(args.annotator1),
        "annotator_2_file": str(args.annotator2),
        "common_queries_judged": len(common_ids),
        "intent_cohen_kappa": round(float(kappa_intent), 4),
        "intent_raw_agreement": f"{intent_agree}/{len(intents1)} ({intent_agree/len(intents1):.2%})",
        "intent_agreement_wilson_95ci": intent_ci,
        "urgency_linear_weighted_kappa": round(float(kappa_urgency), 4),
        "urgency_raw_agreement": f"{urgency_agree}/{len(urgencies1)} ({urgency_agree/len(urgencies1):.2%})",
        "urgency_agreement_wilson_95ci": urgency_ci,
        "needs_ehr_kappa": round(float(kappa_ehr), 4),
        "gate_criterion": "Kappa >= 0.70 for intent and urgency",
        "gate_status": "PASS" if kappa_intent >= 0.70 and kappa_urgency >= 0.70 else "FAIL",
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 60)
    print("CarePilot AI — Human Inter-Annotator Agreement Report (S15)")
    print("=" * 60)
    print(f"Annotator 1: {args.annotator1.name}")
    print(f"Annotator 2: {args.annotator2.name}")
    print(f"Queries Evaluated: {len(common_ids)}")
    print(f"Intent Cohen's Kappa:      {kappa_intent:.4f}  (Agreement: {intent_agree/len(intents1):.1%}, 95% CI: {intent_ci})")
    print(f"Urgency Weighted Kappa:    {kappa_urgency:.4f}  (Agreement: {urgency_agree/len(urgencies1):.1%}, 95% CI: {urgency_ci})")
    print(f"Needs-EHR Kappa:           {kappa_ehr:.4f}")
    print(f"Gate Status:               {report['gate_status']}")
    print(f"Report saved to: {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
