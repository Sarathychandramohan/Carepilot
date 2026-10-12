"""
D:\\CarePilotAI\\backend\\scripts\\compute_cohen_kappa.py

Calculates inter-annotator agreement (Cohen's Kappa) for:
1. Intent Classification (multi-class)
2. Urgency Triage (ordinal: routine, soon, urgent)

Input: data/queries/gold.jsonl
Output: data/manifests/annotation_kappa.json
Gate: Kappa >= 0.70 for both intent and urgency before gold freeze.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_PATH = PROJECT_ROOT / "data" / "queries" / "gold.jsonl"
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "annotation_kappa.json"


def evaluate_kappa(gold_file: Path = GOLD_PATH) -> dict:
    if not gold_file.exists():
        print(f"ERROR: Gold query file not found at {gold_file}")
        return {}

    annotator1_intents = []
    annotator2_intents = []
    annotator1_urgencies = []
    annotator2_urgencies = []

    total_records = 0
    with open(gold_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            a1_intent = item.get("annotator_1_intent")
            a2_intent = item.get("annotator_2_intent")
            a1_urgency = item.get("annotator_1_urgency")
            a2_urgency = item.get("annotator_2_urgency")

            if a1_intent and a2_intent:
                annotator1_intents.append(a1_intent)
                annotator2_intents.append(a2_intent)

            if a1_urgency and a2_urgency:
                annotator1_urgencies.append(a1_urgency)
                annotator2_urgencies.append(a2_urgency)

            total_records += 1

    if not annotator1_intents or not annotator1_urgencies:
        print("ERROR: Incomplete annotator fields in dataset.")
        return {}

    kappa_intent = cohen_kappa_score(annotator1_intents, annotator2_intents)
    kappa_urgency = cohen_kappa_score(annotator1_urgencies, annotator2_urgencies, weights="linear")

    intent_pass = kappa_intent >= 0.70
    urgency_pass = kappa_urgency >= 0.70
    overall_pass = intent_pass and urgency_pass

    results = {
        "dataset": "gold.jsonl",
        "sample_size": total_records,
        "intent_cohen_kappa": round(kappa_intent, 4),
        "intent_gate_pass": intent_pass,
        "urgency_linear_weighted_kappa": round(kappa_urgency, 4),
        "urgency_gate_pass": urgency_pass,
        "gate_criterion": "Kappa >= 0.70",
        "overall_gate_status": "PASS" if overall_pass else "FAIL",
    }

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 50)
    print("CarePilot AI - Inter-Annotator Agreement Report")
    print("=" * 50)
    print(f"Total Annotations Judged: {total_records}")
    print(f"Intent Cohen's Kappa:      {kappa_intent:.4f}  [{'[OK] PASS' if intent_pass else '[FAIL]'}]")
    print(f"Urgency Weighted Kappa:    {kappa_urgency:.4f}  [{'[OK] PASS' if urgency_pass else '[FAIL]'}]")
    print(f"Overall Gate Status:       {results['overall_gate_status']}")
    print(f"Report saved to: {MANIFEST_PATH}")
    print("=" * 50)

    return results


if __name__ == "__main__":
    evaluate_kappa()
