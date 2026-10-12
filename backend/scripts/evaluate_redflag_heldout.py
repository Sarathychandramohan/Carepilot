"""
D:\\CarePilotAI\\backend\\scripts\\evaluate_redflag_heldout.py

Freezes redflag.py by recording its SHA-256 checksum.
Evaluates the frozen red-flag engine against the held-out test suite.
Reports:
- True Positive Recall on Acute Emergencies
- False Positive Escalation Rate on Negated/Historical/Hypothetical Mentions
- Soft Hit Capture Rate on Non-Acute Mentions
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REDFLAG_FILE = PROJECT_ROOT / "backend" / "app" / "pipeline" / "redflag.py"
HELDOUT_TABLE_PATH = PROJECT_ROOT / "data" / "queries" / "redflag_held_out_table.json"
REPORT_OUTPUT_PATH = PROJECT_ROOT / "data" / "manifests" / "redflag_eval_report.json"

from backend.app.pipeline.redflag import evaluate_red_flags


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def wilson_score_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    z = 1.95996
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = (z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)) / denominator
    return round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)


def run_evaluation():
    if not REDFLAG_FILE.exists():
        print(f"ERROR: redflag.py not found at {REDFLAG_FILE}", file=sys.stderr)
        sys.exit(1)

    file_hash = compute_file_sha256(REDFLAG_FILE)
    print("\n" + "=" * 60)
    print("CarePilot AI — Frozen Red-Flag Rule Engine Evaluation (S6 / RQ2)")
    print("=" * 60)
    print(f"Frozen redflag.py SHA-256: {file_hash}")

    if not HELDOUT_TABLE_PATH.exists():
        print(f"ERROR: Held-out test table not found at {HELDOUT_TABLE_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(HELDOUT_TABLE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("cases", [])
    print(f"Loaded {len(cases)} held-out test cases across all categories and variant types.\n")

    positives = [c for c in cases if c["example_type"] in ("positive", "multi_symptom", "self_harm")]
    negatives = [c for c in cases if c["example_type"] in ("negated", "historical", "hypothetical", "ambiguous", "benign")]
    soft_targets = [c for c in cases if c["example_type"] in ("historical", "hypothetical")]

    # 1. Recall on Positives (Firm Hit required)
    pos_correct = 0
    pos_results = []
    for c in positives:
        res = evaluate_red_flags(c["query_text"])
        is_hit = (res["hit_type"] == "firm")
        if is_hit:
            pos_correct += 1
        pos_results.append({
            "case_id": c["case_id"],
            "category": c["category"],
            "type": c["example_type"],
            "query": c["query_text"],
            "passed": is_hit,
            "actual_hit_type": res["hit_type"],
        })

    pos_recall = (pos_correct / len(positives)) if positives else 1.0
    pos_recall_ci = wilson_score_interval(pos_correct, len(positives))

    # 2. False-Positive Escalation (Firm Hit on negative/negated/historical/hypothetical)
    fp_escalations = 0
    neg_results = []
    for c in negatives:
        res = evaluate_red_flags(c["query_text"])
        is_escalated = (res["hit_type"] == "firm")
        if is_escalated:
            fp_escalations += 1
        neg_results.append({
            "case_id": c["case_id"],
            "category": c["category"],
            "type": c["example_type"],
            "query": c["query_text"],
            "escalated_to_firm": is_escalated,
            "actual_hit_type": res["hit_type"],
        })

    fp_rate = (fp_escalations / len(negatives)) if negatives else 0.0
    fp_ci = wilson_score_interval(fp_escalations, len(negatives))

    # 3. Soft Hit Capture Rate on Historical & Hypothetical
    soft_captured = 0
    for c in soft_targets:
        res = evaluate_red_flags(c["query_text"])
        if res["hit_type"] == "soft":
            soft_captured += 1

    soft_rate = (soft_captured / len(soft_targets)) if soft_targets else 1.0

    print("--- Performance Metrics ---")
    print(f"Positive Emergency Recall (Firm):  {pos_correct}/{len(positives)} ({pos_recall:.2%})  [Wilson 95% CI: {pos_recall_ci}]")
    print(f"False-Positive Escalation Rate:     {fp_escalations}/{len(negatives)} ({fp_rate:.2%})  [Wilson 95% CI: {fp_ci}]")
    print(f"Soft Hit Routing (Advisory Doctor): {soft_captured}/{len(soft_targets)} ({soft_rate:.2%})")

    report = {
        "redflag_code_sha256": file_hash,
        "evaluation_dataset": str(HELDOUT_TABLE_PATH.name),
        "total_cases": len(cases),
        "positives_count": len(positives),
        "negatives_count": len(negatives),
        "positive_recall": round(float(pos_recall), 4),
        "positive_recall_wilson_95ci": pos_recall_ci,
        "false_positive_escalation_rate": round(float(fp_rate), 4),
        "false_positive_escalation_wilson_95ci": fp_ci,
        "soft_hit_capture_rate": round(float(soft_rate), 4),
        "gate_status": "PASS" if pos_recall >= 0.95 and fp_rate <= 0.05 else "FAIL",
    }

    REPORT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n[OK] Evaluation report saved to: {REPORT_OUTPUT_PATH}")
    print("=" * 60)
    return report


if __name__ == "__main__":
    run_evaluation()
