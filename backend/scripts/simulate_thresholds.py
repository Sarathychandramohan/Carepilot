"""
backend/scripts/simulate_thresholds.py

Simulates different threshold strategies on the 15-query batch.
Analyzes what flips from manual_required to passed / passed_with_warning,
and compares against the manual clinical audit.
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IN_PATH = PROJECT_ROOT / "data" / "manifests" / "batch_15_sentence_nli_analysis.json"

def main():
    with open(IN_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)

    print("Simulating threshold sweeps on N=15 batch:")
    print("--------------------------------------------------")

    thresholds_to_test = [0.30, 0.20, 0.15, 0.10, 0.05, 0.02, 0.01, 0.005]

    for thresh in thresholds_to_test:
        statuses = []
        for r in records:
            if not r.get("has_draft"):
                statuses.append("manual_required (safety guardrail)")
                continue

            # Compute avg NLI
            scores = [s["nli_score"] for s in r.get("sentences", []) if s.get("nli_score") is not None]
            avg_nli = sum(scores) / len(scores) if scores else 0.0

            # Coverage
            cov = r.get("citation_coverage", 1.0)
            if cov is None:
                cov = 0.0

            if cov < 0.80:
                statuses.append("manual_required (low coverage)")
            elif avg_nli < thresh:
                statuses.append("manual_required (low nli)")
            elif avg_nli < 0.50:
                statuses.append("passed_with_warning")
            else:
                statuses.append("passed")

        from collections import Counter
        counts = Counter(statuses)
        print(f"tau_warn = {thresh:.3f}:")
        for k, v in counts.items():
            print(f"   {k}: {v}")

if __name__ == "__main__":
    main()
