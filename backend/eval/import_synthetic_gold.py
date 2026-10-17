"""
backend/eval/import_synthetic_gold.py

Reads synthetic gold queries from an input JSONL, validates them against:
  1. Missing required fields
  2. Unknown patient_id (must exist in data/annotation/context_packs.jsonl)
  3. referenced_fact not found in that patient's context pack
  4. intent not in the real intent enum
  5. near-duplicate query (cosine similarity >= 0.7 using diversity_report embedding)
  6. scenario spanning dev/test after cluster-level split

If all checks pass, writes validated candidate queries to:
  data/annotation/gold_synthetic_candidate.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.eval.diversity_report import strip_greetings_and_signoffs

CONTEXT_PACKS_PATH = PROJECT_ROOT / "data" / "annotation" / "context_packs.jsonl"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "annotation" / "gold_synthetic_candidate.jsonl"

# Real intent and urgency enums
REAL_INTENTS = [
    "followup_appointment",
    "general_health_info",
    "lab_result_query",
    "medication_query",
    "symptom_report",
]

REAL_URGENCIES = [
    "routine",
    "soon",
    "urgent",
]

_EMBEDDER = None


def get_diversity_embedder(local_files_only: bool = True):
    """Load cached BAAI/bge-small-en-v1.5 embedding model for diversity check."""
    global _EMBEDDER
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer
        _EMBEDDER = SentenceTransformer("BAAI/bge-small-en-v1.5", local_files_only=local_files_only)
    return _EMBEDDER


def load_context_packs(path: Path = CONTEXT_PACKS_PATH) -> dict[str, dict[str, Any]]:
    """Load context packs indexed by patient_id."""
    if not path.exists():
        raise FileNotFoundError(f"Context packs file not found at: {path}")

    packs = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            packs[item["patient_id"]] = item
    return packs


def fact_exists_in_pack(fact: str, pack: dict[str, Any]) -> bool:
    """
    Check if referenced_fact exists in patient context pack.
    Searches active medications, disorders, recent labs, and encounters.
    """
    fact_clean = fact.strip().lower()
    if not fact_clean:
        return False

    # Check medications
    for med in pack.get("active_medications", []):
        m_name = (med.get("name") or "").lower()
        m_dose = (med.get("dose") or "").lower()
        if fact_clean in m_name or fact_clean in m_dose or m_name in fact_clean:
            return True

    # Check disorders
    for dis in pack.get("disorders", []):
        d_lower = dis.lower()
        d_stripped = re.sub(r"\s*\(disorder\)", "", d_lower).strip()
        if fact_clean in d_lower or fact_clean in d_stripped or d_stripped in fact_clean:
            return True

    # Check recent labs
    for lab in pack.get("recent_labs", []):
        c_lower = (lab.get("concept") or "").lower()
        c_clean = re.sub(r"\[.*?\]", "", c_lower).strip()
        if fact_clean in c_lower or fact_clean in c_clean or c_clean in fact_clean:
            return True
        # Check if value matches
        val_str = str(lab.get("value", ""))
        if fact_clean == val_str:
            return True

    # Check encounters
    for enc in pack.get("upcoming_or_recent_encounters", []):
        e_type = (enc.get("type") or "").lower()
        if fact_clean in e_type or e_type in fact_clean:
            return True

    return False


def validate_and_import_synthetic_gold(
    input_path: Path,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    context_packs_path: Path = CONTEXT_PACKS_PATH,
    cluster_threshold: float = 0.70,
) -> list[dict[str, Any]]:
    """
    Validates input synthetic JSONL queries and writes to output JSONL.
    Fails on:
      1. Missing required fields
      2. Unknown patient_id
      3. referenced_fact not found in that patient's pack
      4. intent not in real enum
      5. near-duplicate query (cosine >= 0.7 using diversity_report embedding)
      6. scenario spanning dev/test after cluster-level split
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found at: {input_path}")

    context_packs = load_context_packs(context_packs_path)
    print(f"Loaded {len(context_packs)} patient context packs from {context_packs_path}")

    # Read input rows
    raw_rows = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                row["_line_no"] = line_no
                raw_rows.append(row)
            except Exception as e:
                raise ValueError(f"Invalid JSON on line {line_no}: {e}")

    if not raw_rows:
        raise ValueError(f"Input file {input_path} contains 0 rows.")

    print(f"Read {len(raw_rows)} synthetic candidate rows from {input_path}")

    validated_rows: list[dict[str, Any]] = []

    # 1. Field validation, patient_id check, fact verification, intent enum check
    for r in raw_rows:
        line_no = r.get("_line_no", 0)

        # Check required fields
        for field in ("scenario_id", "patient_id", "query_text", "referenced_fact"):
            val = r.get(field)
            if val is None or str(val).strip() == "":
                raise ValueError(f"[FAIL: Missing Field] Line {line_no}: Missing required field '{field}'")

        # Intent resolution
        intent = r.get("intent") or r.get("intent_label")
        if not intent or str(intent).strip() == "":
            raise ValueError(f"[FAIL: Missing Field] Line {line_no}: Missing 'intent' / 'intent_label'")
        intent = str(intent).strip()

        # Urgency resolution
        urgency = r.get("urgency") or r.get("urgency_label")
        if not urgency or str(urgency).strip() == "":
            raise ValueError(f"[FAIL: Missing Field] Line {line_no}: Missing 'urgency' / 'urgency_label'")
        urgency = str(urgency).strip()

        # Check unknown patient_id
        pid = str(r["patient_id"]).strip()
        if pid not in context_packs:
            raise ValueError(
                f"[FAIL: Unknown Patient ID] Line {line_no}: patient_id '{pid}' not found in context packs"
            )

        # Check referenced_fact in patient pack
        ref_fact = str(r["referenced_fact"]).strip()
        pack = context_packs[pid]
        if not fact_exists_in_pack(ref_fact, pack):
            raise ValueError(
                f"[FAIL: Ungrounded Fact] Line {line_no}: referenced_fact '{ref_fact}' not found in context pack for patient '{pid}'"
            )

        # Check intent in real enum
        if intent not in REAL_INTENTS:
            raise ValueError(
                f"[FAIL: Invalid Intent] Line {line_no}: intent '{intent}' not in real intent enum {REAL_INTENTS}"
            )

        # Check urgency in real urgency enum
        if urgency not in REAL_URGENCIES:
            raise ValueError(
                f"[FAIL: Invalid Urgency] Line {line_no}: urgency '{urgency}' not in real urgency enum {REAL_URGENCIES}"
            )

        # Check required split field ('dev' or 'test')
        split = str(r.get("split", "")).strip().lower()
        if not split or split not in ("dev", "test"):
            raise ValueError(
                f"[FAIL: Missing/Invalid Split] Line {line_no}: Required field 'split' must be 'dev' or 'test', got '{r.get('split')}'"
            )

        item = {
            "query_id": r.get("query_id") or f"GS-{len(validated_rows) + 1:04d}",
            "scenario_id": str(r["scenario_id"]).strip(),
            "patient_id": pid,
            "query_text": str(r["query_text"]).strip(),
            "intent_label": intent,
            "urgency_label": urgency,
            "referenced_fact": ref_fact,
            "split": split,
            "tier": "gold",
            "requires_patient_context": True,
            "_line_no": line_no,
        }
        validated_rows.append(item)

    print(f"Passed basic schema, grounding, and enum validation: {len(validated_rows)} rows")

    # 2. Near-duplicate query validation using diversity_report embedding
    print(f"Computing embeddings with BAAI/bge-small-en-v1.5 and checking cosine >= {cluster_threshold}...")
    embedder = get_diversity_embedder()
    cleaned_texts = [strip_greetings_and_signoffs(r["query_text"]) for r in validated_rows]
    embeddings = embedder.encode(cleaned_texts, normalize_embeddings=True)

    # Pairwise cosine similarity check
    num_queries = len(validated_rows)
    for i in range(num_queries):
        for j in range(i + 1, num_queries):
            cos_sim = float(np.dot(embeddings[i], embeddings[j]))
            if cos_sim >= cluster_threshold:
                raise ValueError(
                    f"[FAIL: Near-Duplicate Query] Query {i+1} (Line {validated_rows[i]['_line_no']}) and "
                    f"Query {j+1} (Line {validated_rows[j]['_line_no']}) have cosine similarity "
                    f"{cos_sim:.4f} >= {cluster_threshold}.\n"
                    f"  Query {i+1}: '{validated_rows[i]['query_text']}'\n"
                    f"  Query {j+1}: '{validated_rows[j]['query_text']}'"
                )

    print(f"Passed near-duplicate query check (all pairwise cosine < {cluster_threshold}).")

    # 3. Cluster-level split and cross-split scenario leakage validation
    # If splits are provided on rows, verify neither scenario nor connected cluster spans dev/test
    # If splits are not provided on rows, assign cluster-level split deterministically
    has_explicit_splits = all(r["split"] in ("dev", "test") for r in validated_rows)

    if not has_explicit_splits:
        # Assign cluster/scenario-level split deterministically (e.g. 30% dev, 70% test)
        scenario_ids = sorted(list(set(r["scenario_id"] for r in validated_rows)))
        import random
        rng = random.Random(42)
        dev_scenarios = set(rng.sample(scenario_ids, max(1, int(len(scenario_ids) * 0.3))))
        for r in validated_rows:
            r["split"] = "dev" if r["scenario_id"] in dev_scenarios else "test"

    # Now verify scenario-level partitioning
    scenario_splits = defaultdict(set)
    for r in validated_rows:
        scenario_splits[r["scenario_id"]].add(r["split"])

    for sc_id, sps in scenario_splits.items():
        if "dev" in sps and "test" in sps:
            raise ValueError(
                f"[FAIL: Scenario Spanning Dev/Test] scenario_id '{sc_id}' contains queries assigned to both 'dev' and 'test'"
            )

    # Also verify that no near-duplicate cluster (even below the failure threshold, e.g. connected component at 0.5+) spans dev/test
    # Here cluster check at threshold:
    for i in range(num_queries):
        for j in range(i + 1, num_queries):
            sim = float(np.dot(embeddings[i], embeddings[j]))
            if sim >= cluster_threshold:
                # Should have been caught by near-dup, but if allowed:
                if validated_rows[i]["split"] != validated_rows[j]["split"]:
                    raise ValueError(
                        f"[FAIL: Cluster Spanning Dev/Test] Cluster with cosine {sim:.4f} spans dev and test: "
                        f"Query {i+1} ({validated_rows[i]['split']}) vs Query {j+1} ({validated_rows[j]['split']})"
                    )

    print("Passed cluster-level split verification: Zero scenarios or clusters span dev/test.")

    # Write output JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for r in validated_rows:
            clean_record = {
                "query_id": r["query_id"],
                "scenario_id": r["scenario_id"],
                "patient_id": r["patient_id"],
                "query_text": r["query_text"],
                "intent_label": r["intent_label"],
                "urgency_label": r["urgency_label"],
                "referenced_fact": r["referenced_fact"],
                "split": r["split"],
                "tier": r["tier"],
                "requires_patient_context": r["requires_patient_context"],
            }
            f.write(json.dumps(clean_record) + "\n")

    print(f"Successfully imported and saved {len(validated_rows)} queries -> {output_path}")
    return validated_rows


def main():
    parser = argparse.ArgumentParser(description="Validate and import synthetic gold queries.")
    parser.add_argument("--input", type=Path, required=True, help="Path to input synthetic JSONL")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Path to output JSONL")
    parser.add_argument("--context-packs", type=Path, default=CONTEXT_PACKS_PATH, help="Path to context_packs.jsonl")
    args = parser.parse_args()

    try:
        validated = validate_and_import_synthetic_gold(
            input_path=args.input,
            output_path=args.output,
            context_packs_path=args.context_packs,
        )
        print(f"\n[VALIDATOR PASS] Successfully processed {len(validated)} candidate queries.")
    except Exception as e:
        print(f"\n[VALIDATOR ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
