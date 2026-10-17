"""
backend/eval/tools/import_review.py

Imports clinician reviews for sealed gold synthetic pilot labels, validates
reviewer inputs against real pipeline enums, calculates inter-annotator agreement
(accuracy, unweighted Cohen's kappa, linear-weighted kappa for ordinal urgency),
prints confusion matrices, highlights directional urgency disagreements, and
exports disagreements to data/annotation/review_disagreements.csv.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Real pipeline enums from backend/app/pipeline/classify.py & models_v3.py
REAL_INTENTS: list[str] = [
    "followup_appointment",
    "general_health_info",
    "lab_result_query",
    "medication_query",
    "symptom_report",
]

REAL_URGENCIES: list[str] = [
    "routine",
    "soon",
    "urgent",
]

URGENCY_ORDER: dict[str, int] = {
    "routine": 0,
    "soon": 1,
    "urgent": 2,
}

DEFAULT_SEALED_PATH = PROJECT_ROOT / "data" / "queries" / "gold_synthetic_pilot_labels_sealed.csv"
DEFAULT_DISAGREEMENTS_PATH = PROJECT_ROOT / "data" / "annotation" / "review_disagreements.csv"


def parse_boolean(val: Any) -> bool:
    """Parses boolean value from string or bool representation."""
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("true", "t", "1", "yes", "y"):
        return True
    if s in ("false", "f", "0", "no", "n"):
        return False
    raise ValueError(f"Invalid boolean value: {val!r}")


def validate_reviewer_row(row: dict[str, Any], row_idx: int | None = None) -> dict[str, Any]:
    """
    Validates a single reviewer CSV record against pipeline enums and schema.
    Returns cleaned row with standardized types.
    """
    row_desc = f"Row {row_idx}" if row_idx is not None else "Reviewer row"

    required_fields = [
        "reviewer_id",
        "query_id",
        "intent",
        "urgency",
        "needs_ehr",
        "confidence",
        "rationale",
        "source_url",
    ]
    for field in required_fields:
        if field not in row:
            raise ValueError(f"{row_desc} missing required column: '{field}'")

    reviewer_id = str(row["reviewer_id"]).strip()
    if not reviewer_id:
        raise ValueError(f"{row_desc}: 'reviewer_id' cannot be empty")

    query_id = str(row["query_id"]).strip()
    if not query_id:
        raise ValueError(f"{row_desc}: 'query_id' cannot be empty")

    intent = str(row["intent"]).strip()
    if intent not in REAL_INTENTS:
        raise ValueError(
            f"{row_desc} (query_id={query_id}): Invalid intent '{intent}'. "
            f"Expected one of: {REAL_INTENTS}"
        )

    urgency = str(row["urgency"]).strip()
    if urgency not in REAL_URGENCIES:
        raise ValueError(
            f"{row_desc} (query_id={query_id}): Invalid urgency '{urgency}'. "
            f"Expected one of: {REAL_URGENCIES}"
        )

    try:
        needs_ehr = parse_boolean(row["needs_ehr"])
    except ValueError as e:
        raise ValueError(f"{row_desc} (query_id={query_id}): {e}") from e

    confidence = str(row.get("confidence", "")).strip()
    rationale = str(row.get("rationale", "")).strip()
    source_url = str(row.get("source_url", "")).strip()

    return {
        "reviewer_id": reviewer_id,
        "query_id": query_id,
        "intent": intent,
        "urgency": urgency,
        "needs_ehr": needs_ehr,
        "confidence": confidence,
        "rationale": rationale,
        "source_url": source_url,
    }


def compute_unweighted_cohen_kappa(y1: list[Any], y2: list[Any], categories: list[Any] | None = None) -> float:
    """
    Computes unweighted Cohen's Kappa for categorical agreement.
    """
    n = len(y1)
    if n == 0:
        return 1.0
    if len(y2) != n:
        raise ValueError("y1 and y2 must have identical lengths")

    if categories is None:
        categories = sorted(list(set(y1) | set(y2)))

    cat_to_idx = {c: i for i, c in enumerate(categories)}
    k = len(categories)
    cm = np.zeros((k, k), dtype=np.float64)

    for a, b in zip(y1, y2):
        if a in cat_to_idx and b in cat_to_idx:
            cm[cat_to_idx[a], cat_to_idx[b]] += 1.0

    po = float(np.trace(cm)) / float(n)
    row_sums = np.sum(cm, axis=1)
    col_sums = np.sum(cm, axis=0)
    pe = float(np.sum(row_sums * col_sums)) / float(n * n)

    if abs(1.0 - pe) < 1e-12:
        return 1.0 if abs(po - 1.0) < 1e-12 else 0.0

    return float((po - pe) / (1.0 - pe))


def compute_linear_weighted_kappa(
    y1: list[str],
    y2: list[str],
    ordered_categories: list[str],
) -> float:
    """
    Computes linear-weighted Cohen's Kappa for ordinal agreement (e.g. routine < soon < urgent).
    Weights w_ij = 1 - |i - j| / (K - 1).
    """
    n = len(y1)
    if n == 0:
        return 1.0
    if len(y2) != n:
        raise ValueError("y1 and y2 must have identical lengths")

    cat_to_idx = {c: i for i, c in enumerate(ordered_categories)}
    k = len(ordered_categories)
    cm = np.zeros((k, k), dtype=np.float64)

    for a, b in zip(y1, y2):
        if a in cat_to_idx and b in cat_to_idx:
            cm[cat_to_idx[a], cat_to_idx[b]] += 1.0

    w = np.zeros((k, k), dtype=np.float64)
    for i in range(k):
        for j in range(k):
            w[i, j] = 1.0 - (abs(i - j) / float(k - 1))

    po = float(np.sum(w * cm)) / float(n)
    row_sums = np.sum(cm, axis=1)
    col_sums = np.sum(cm, axis=0)
    pe = float(np.sum(w * np.outer(row_sums, col_sums))) / float(n * n)

    if abs(1.0 - pe) < 1e-12:
        return 1.0 if abs(po - 1.0) < 1e-12 else 0.0

    return float((po - pe) / (1.0 - pe))


def load_sealed_labels(sealed_path: Path | str) -> dict[str, dict[str, Any]]:
    """Loads and parses sealed author labels CSV."""
    sealed_map: dict[str, dict[str, Any]] = {}
    with open(sealed_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qid = row["query_id"].strip()
            sealed_map[qid] = {
                "query_id": qid,
                "intent": row["intent"].strip(),
                "urgency": row["urgency"].strip(),
                "needs_ehr": parse_boolean(row["needs_ehr"]),
            }
    return sealed_map


def load_and_join_reviews(
    review_path: Path | str,
    sealed_path: Path | str,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """
    Reads reviewer CSV, validates enums, and joins with sealed labels.
    Returns:
      matched_rows: list of joined dictionaries
      unmatched_in_review: reviewer query_ids not found in sealed labels
      unmatched_in_sealed: sealed query_ids not present in reviewer file
    """
    sealed_map = load_sealed_labels(sealed_path)

    matched_rows: list[dict[str, Any]] = []
    unmatched_in_review: list[str] = []
    seen_queries: set[str] = set()

    with open(review_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, raw_row in enumerate(reader, start=2):
            validated = validate_reviewer_row(raw_row, row_idx=idx)
            qid = validated["query_id"]
            seen_queries.add(qid)

            if qid in sealed_map:
                author_item = sealed_map[qid]
                matched_rows.append({
                    "reviewer_id": validated["reviewer_id"],
                    "query_id": qid,
                    "author_intent": author_item["intent"],
                    "reviewer_intent": validated["intent"],
                    "author_urgency": author_item["urgency"],
                    "reviewer_urgency": validated["urgency"],
                    "author_needs_ehr": author_item["needs_ehr"],
                    "reviewer_needs_ehr": validated["needs_ehr"],
                    "confidence": validated["confidence"],
                    "rationale": validated["rationale"],
                    "source_url": validated["source_url"],
                    "intent_disagree": author_item["intent"] != validated["intent"],
                    "urgency_disagree": author_item["urgency"] != validated["urgency"],
                    "needs_ehr_disagree": author_item["needs_ehr"] != validated["needs_ehr"],
                })
            else:
                unmatched_in_review.append(qid)

    unmatched_in_sealed = [qid for qid in sealed_map if qid not in seen_queries]

    return matched_rows, unmatched_in_review, unmatched_in_sealed


def compute_review_metrics(matched_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Computes summary agreement metrics, confusion matrices, and directional urgency shifts.
    """
    n = len(matched_rows)
    if n == 0:
        return {
            "n_matched": 0,
            "intent_accuracy": 0.0,
            "intent_cohen_kappa": 0.0,
            "needs_ehr_accuracy": 0.0,
            "needs_ehr_cohen_kappa": 0.0,
            "urgency_accuracy": 0.0,
            "urgency_linear_kappa": 0.0,
            "urgency_confusion_matrix": {},
            "urgency_higher_rows": [],
            "urgency_lower_rows": [],
        }

    author_intents = [r["author_intent"] for r in matched_rows]
    reviewer_intents = [r["reviewer_intent"] for r in matched_rows]

    author_urgencies = [r["author_urgency"] for r in matched_rows]
    reviewer_urgencies = [r["reviewer_urgency"] for r in matched_rows]

    author_ehrs = [r["author_needs_ehr"] for r in matched_rows]
    reviewer_ehrs = [r["reviewer_needs_ehr"] for r in matched_rows]

    # Accuracy calculations
    intent_acc = sum(1 for a, r in zip(author_intents, reviewer_intents) if a == r) / n
    urgency_acc = sum(1 for a, r in zip(author_urgencies, reviewer_urgencies) if a == r) / n
    ehr_acc = sum(1 for a, r in zip(author_ehrs, reviewer_ehrs) if a == r) / n

    # Kappa calculations
    intent_kappa = compute_unweighted_cohen_kappa(author_intents, reviewer_intents, categories=REAL_INTENTS)
    ehr_kappa = compute_unweighted_cohen_kappa(author_ehrs, reviewer_ehrs, categories=[True, False])
    urgency_kappa = compute_linear_weighted_kappa(author_urgencies, reviewer_urgencies, ordered_categories=REAL_URGENCIES)

    # Urgency Confusion Matrix (rows = author, cols = reviewer)
    cm: dict[str, dict[str, int]] = {
        auth_u: {rev_u: 0 for rev_u in REAL_URGENCIES}
        for auth_u in REAL_URGENCIES
    }
    urgency_higher_rows: list[dict[str, Any]] = []
    urgency_lower_rows: list[dict[str, Any]] = []

    for r in matched_rows:
        auth_u = r["author_urgency"]
        rev_u = r["reviewer_urgency"]
        cm[auth_u][rev_u] += 1

        auth_rank = URGENCY_ORDER[auth_u]
        rev_rank = URGENCY_ORDER[rev_u]

        if rev_rank > auth_rank:
            urgency_higher_rows.append(r)
        elif rev_rank < auth_rank:
            urgency_lower_rows.append(r)

    return {
        "n_matched": n,
        "intent_accuracy": intent_acc,
        "intent_cohen_kappa": intent_kappa,
        "needs_ehr_accuracy": ehr_acc,
        "needs_ehr_cohen_kappa": ehr_kappa,
        "urgency_accuracy": urgency_acc,
        "urgency_linear_kappa": urgency_kappa,
        "urgency_confusion_matrix": cm,
        "urgency_higher_rows": urgency_higher_rows,
        "urgency_lower_rows": urgency_lower_rows,
    }


def write_disagreements_csv(matched_rows: list[dict[str, Any]], output_path: Path | str) -> int:
    """
    Writes data/annotation/review_disagreements.csv for all rows where
    intent, urgency, or needs_ehr differs between author and reviewer.
    """
    disagreements = [
        r for r in matched_rows
        if r["intent_disagree"] or r["urgency_disagree"] or r["needs_ehr_disagree"]
    ]

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "reviewer_id",
        "query_id",
        "author_intent",
        "reviewer_intent",
        "author_urgency",
        "reviewer_urgency",
        "author_needs_ehr",
        "reviewer_needs_ehr",
        "confidence",
        "rationale",
        "source_url",
    ]

    with open(out_p, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for d in disagreements:
            writer.writerow({k: d[k] for k in fieldnames})

    return len(disagreements)


def print_review_report(
    metrics: dict[str, Any],
    unmatched_in_review: list[str],
    unmatched_in_sealed: list[str],
) -> None:
    """Prints a structured clinical review audit report to stdout."""
    n = metrics["n_matched"]
    print("\n" + "=" * 80)
    print("CLINICAL REVIEW IMPORT & INTER-RATER AUDIT REPORT")
    print("=" * 80)
    print(f"Matched Queries (n): {n}")
    if unmatched_in_review:
        print(f"Queries in reviewer CSV not found in sealed set ({len(unmatched_in_review)}): {unmatched_in_review}")
    if unmatched_in_sealed:
        print(f"Queries in sealed set missing from review ({len(unmatched_in_sealed)}): {unmatched_in_sealed}")

    print("\n" + "-" * 80)
    print("AGREEMENT METRICS SUMMARY")
    print("-" * 80)
    print(f"Intent Classification:")
    print(f"  - Accuracy:              {metrics['intent_accuracy'] * 100:.2f}%")
    print(f"  - Unweighted Cohen's kappa: {metrics['intent_cohen_kappa']:.4f}")

    print(f"Needs Patient EHR Flag:")
    print(f"  - Accuracy:              {metrics['needs_ehr_accuracy'] * 100:.2f}%")
    print(f"  - Unweighted Cohen's kappa: {metrics['needs_ehr_cohen_kappa']:.4f}")

    print(f"Urgency Classification (routine < soon < urgent):")
    print(f"  - Accuracy:              {metrics['urgency_accuracy'] * 100:.2f}%")
    print(f"  - Linear-Weighted kappa: {metrics['urgency_linear_kappa']:.4f}")


    print("\n" + "-" * 80)
    print("URGENCY CONFUSION MATRIX (Rows: Author/Sealed | Cols: Reviewer)")
    print("-" * 80)
    cm = metrics["urgency_confusion_matrix"]
    col_headers = [f"{u:>10}" for u in REAL_URGENCIES]
    print(f"{'Author \\ Reviewer':<20}" + "".join(col_headers) + f"{'Total':>10}")
    print("-" * 60)
    for auth_u in REAL_URGENCIES:
        counts = [cm[auth_u][rev_u] for rev_u in REAL_URGENCIES]
        row_tot = sum(counts)
        counts_str = "".join([f"{c:>10}" for c in counts])
        print(f"{auth_u:<20}{counts_str}{row_tot:>10}")
    print("-" * 60)
    col_totals = [sum(cm[auth_u][rev_u] for auth_u in REAL_URGENCIES) for rev_u in REAL_URGENCIES]
    col_tot_str = "".join([f"{c:>10}" for c in col_totals])
    print(f"{'Reviewer Total':<20}{col_tot_str}{sum(col_totals):>10}")

    print("\n" + "-" * 80)
    print(f"DIRECTIONAL SHIFTS: REVIEWER URGENCY HIGHER THAN AUTHOR ({len(metrics['urgency_higher_rows'])} rows)")
    print("-" * 80)
    if not metrics["urgency_higher_rows"]:
        print("None.")
    else:
        for r in metrics["urgency_higher_rows"]:
            print(
                f"[{r['query_id']}] Author: {r['author_urgency']} -> Reviewer: {r['reviewer_urgency']} | "
                f"Conf: {r['confidence']} | Rationale: {r['rationale']}"
            )

    print("\n" + "-" * 80)
    print(f"DIRECTIONAL SHIFTS: REVIEWER URGENCY LOWER THAN AUTHOR ({len(metrics['urgency_lower_rows'])} rows)")
    print("-" * 80)
    if not metrics["urgency_lower_rows"]:
        print("None.")
    else:
        for r in metrics["urgency_lower_rows"]:
            print(
                f"[{r['query_id']}] Author: {r['author_urgency']} -> Reviewer: {r['reviewer_urgency']} | "
                f"Conf: {r['confidence']} | Rationale: {r['rationale']}"
            )
    print("=" * 80 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import and audit clinician review CSV.")
    parser.add_argument(
        "--review-file",
        type=Path,
        required=True,
        help="Path to reviewer CSV file",
    )
    parser.add_argument(
        "--sealed-file",
        type=Path,
        default=DEFAULT_SEALED_PATH,
        help="Path to sealed author labels CSV",
    )
    parser.add_argument(
        "--output-disagreements",
        type=Path,
        default=DEFAULT_DISAGREEMENTS_PATH,
        help="Path to write disagreements CSV",
    )

    args = parser.parse_args()

    if not args.review_file.exists():
        print(f"Error: Review file not found: {args.review_file}", file=sys.stderr)
        return 1
    if not args.sealed_file.exists():
        print(f"Error: Sealed labels file not found: {args.sealed_file}", file=sys.stderr)
        return 1

    matched_rows, unmatched_rev, unmatched_seal = load_and_join_reviews(
        args.review_file,
        args.sealed_file,
    )
    metrics = compute_review_metrics(matched_rows)
    print_review_report(metrics, unmatched_rev, unmatched_seal)

    n_dis = write_disagreements_csv(matched_rows, args.output_disagreements)
    print(f"Wrote {n_dis} disagreement row(s) to {args.output_disagreements}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
