"""
backend/eval/import_synthetic_gold.py

Reads synthetic gold queries from an input JSONL, validates them, and merges
them into data/annotation/gold_synthetic_candidate.jsonl keyed by scenario_id.

Validation rules:
  1. Missing required fields (scenario_id, patient_id, query_text, referenced_fact)
  2. Unknown patient_id (must exist in data/annotation/context_packs.jsonl)
  3. referenced_fact not found in that patient's context pack
  4. intent not in real intent enum (followup_appointment, general_health_info,
     lab_result_query, medication_query, symptom_report)
  5. urgency not in real urgency enum (routine, soon, urgent)
  6. split is optional on input (if provided, must be 'dev' or 'test')
  7. Duplicate scenario_id rejection (both within input and against existing merged file)
  8. Near-duplicate query check (cosine >= 0.70 using BAAI/bge-small-en-v1.5)
     evaluated across the WHOLE merged file
  9. Scenario spanning dev/test after cluster-level split
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
    """Load cached BAAI/bge-small-en-v1.5 embedding model with local_files_only as default."""
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
    for med in pack.get("active_medications", []) or pack.get("meds", []):
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
    local_files_only: bool = True,
) -> list[dict[str, Any]]:
    """
    Validates input synthetic JSONL queries and merges them into output JSONL
    keyed by scenario_id.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found at: {input_path}")

    context_packs = load_context_packs(context_packs_path)
    print(f"Loaded {len(context_packs)} patient context packs from {context_packs_path}")

    # 1. Load existing records from output_path if it exists
    existing_rows: list[dict[str, Any]] = []
    existing_by_scenario: dict[str, dict[str, Any]] = {}
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            for l_idx, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    sc_id = item["scenario_id"]
                    existing_rows.append(item)
                    existing_by_scenario[sc_id] = item
                except Exception as e:
                    print(f"Warning: skipping malformed existing line {l_idx}: {e}")

    # 2. Read new input candidate rows
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

    new_validated_rows: list[dict[str, Any]] = []
    input_scenarios_seen: set[str] = set()

    for r in raw_rows:
        line_no = r.get("_line_no", 0)

        # Check required fields
        for field in ("scenario_id", "patient_id", "query_text", "referenced_fact"):
            val = r.get(field)
            if val is None or str(val).strip() == "":
                raise ValueError(f"[FAIL: Missing Field] Line {line_no}: Missing required field '{field}'")

        sc_id = str(r["scenario_id"]).strip()

        # Check duplicate scenario_id in input batch
        if sc_id in input_scenarios_seen:
            raise ValueError(
                f"[FAIL: Duplicate Scenario ID] Line {line_no}: scenario_id '{sc_id}' duplicated in input batch"
            )
        input_scenarios_seen.add(sc_id)

        # Check duplicate scenario_id against existing output file
        if sc_id in existing_by_scenario:
            raise ValueError(
                f"[FAIL: Duplicate Scenario ID] Line {line_no}: scenario_id '{sc_id}' already exists in {output_path}"
            )

        # Intent resolution
        intent = r.get("intent") or r.get("intent_label")
        if not intent or str(intent).strip() == "":
            raise ValueError(f"[FAIL: Missing Field] Line {line_no}: Missing 'intent' / 'intent_label'")
        intent = str(intent).strip()

        # Urgency resolution & validation
        urgency = r.get("urgency") or r.get("urgency_label")
        if not urgency or str(urgency).strip() == "":
            raise ValueError(f"[FAIL: Missing Field] Line {line_no}: Missing 'urgency' / 'urgency_label'")
        urgency = str(urgency).strip()
        if urgency not in REAL_URGENCIES:
            raise ValueError(
                f"[FAIL: Invalid Urgency] Line {line_no}: urgency '{urgency}' not in real urgency enum {REAL_URGENCIES}"
            )

        # Unknown patient_id check
        pid = str(r["patient_id"]).strip()
        if pid not in context_packs:
            raise ValueError(
                f"[FAIL: Unknown Patient ID] Line {line_no}: patient_id '{pid}' not found in context packs"
            )

        # Grounding check: referenced_fact in patient pack
        ref_fact = str(r["referenced_fact"]).strip()
        pack = context_packs[pid]
        if not fact_exists_in_pack(ref_fact, pack):
            raise ValueError(
                f"[FAIL: Ungrounded Fact] Line {line_no}: referenced_fact '{ref_fact}' not found in context pack for patient '{pid}'"
            )

        # Real intent enum check
        if intent not in REAL_INTENTS:
            raise ValueError(
                f"[FAIL: Invalid Intent] Line {line_no}: intent '{intent}' not in real intent enum {REAL_INTENTS}"
            )

        # Split check: optional on input (if provided, must be 'dev' or 'test')
        raw_split = r.get("split")
        split_val = None
        if raw_split is not None and str(raw_split).strip() != "":
            s_clean = str(raw_split).strip().lower()
            if s_clean not in ("dev", "test"):
                raise ValueError(
                    f"[FAIL: Invalid Split] Line {line_no}: Optional field 'split' must be 'dev' or 'test', got '{raw_split}'"
                )
            split_val = s_clean

        item = {
            "query_id": r.get("query_id") or f"GS-{len(existing_rows) + len(new_validated_rows) + 1:04d}",
            "scenario_id": sc_id,
            "patient_id": pid,
            "query_text": str(r["query_text"]).strip(),
            "intent_label": intent,
            "urgency_label": urgency,
            "referenced_fact": ref_fact,
            "split": split_val,
            "tier": "gold",
            "requires_patient_context": True,
            "_line_no": line_no,
        }
        new_validated_rows.append(item)

    print(f"Passed basic schema, grounding, and enum validation: {len(new_validated_rows)} new rows")

    # 3. MERGE with existing rows
    merged_rows = existing_rows + new_validated_rows
    print(f"Total merged candidate queries to validate: {len(merged_rows)} (Existing: {len(existing_rows)}, New: {len(new_validated_rows)})")

    # 4. Near-duplicate query validation across the WHOLE merged file
    print(f"Computing embeddings with BAAI/bge-small-en-v1.5 and checking cosine >= {cluster_threshold} across ALL {len(merged_rows)} merged queries...")
    embedder = get_diversity_embedder(local_files_only=local_files_only)
    cleaned_texts = [strip_greetings_and_signoffs(r["query_text"]) for r in merged_rows]
    embeddings = embedder.encode(cleaned_texts, normalize_embeddings=True)

    num_queries = len(merged_rows)
    for i in range(num_queries):
        for j in range(i + 1, num_queries):
            cos_sim = float(np.dot(embeddings[i], embeddings[j]))
            if cos_sim >= cluster_threshold:
                raise ValueError(
                    f"[FAIL: Near-Duplicate Query] Query {i+1} ('{merged_rows[i]['query_text']}') and "
                    f"Query {j+1} ('{merged_rows[j]['query_text']}') have cosine similarity "
                    f"{cos_sim:.4f} >= {cluster_threshold}."
                )

    print(f"Passed near-duplicate query check across whole merged file (all pairwise cosine < {cluster_threshold}).")

    # 5. Check scenario-level split consistency across merged file
    scenario_splits = defaultdict(set)
    for r in merged_rows:
        if r.get("split"):
            scenario_splits[r["scenario_id"]].add(r["split"])

    for sc_id, sps in scenario_splits.items():
        if "dev" in sps and "test" in sps:
            raise ValueError(
                f"[FAIL: Scenario Spanning Dev/Test] scenario_id '{sc_id}' contains queries assigned to both 'dev' and 'test'"
            )

    # 6. Write ALL merged rows to output JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for r in merged_rows:
            clean_record = {
                "query_id": r["query_id"],
                "scenario_id": r["scenario_id"],
                "patient_id": r["patient_id"],
                "query_text": r["query_text"],
                "intent_label": r["intent_label"],
                "urgency_label": r["urgency_label"],
                "referenced_fact": r["referenced_fact"],
                "split": r.get("split"),
                "tier": "gold",
                "requires_patient_context": r.get("requires_patient_context", True),
            }
            f.write(json.dumps(clean_record) + "\n")

    print(f"Successfully merged and saved {len(merged_rows)} candidate queries -> {output_path}")
    return merged_rows


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Validate and import synthetic gold queries.")
    parser.add_argument("--input", type=Path, required=True, help="Path to input synthetic JSONL")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Path to output JSONL")
    parser.add_argument("--context-packs", type=Path, default=CONTEXT_PACKS_PATH, help="Path to context_packs.jsonl")
    parser.add_argument("--no-local-files-only", action="store_true", help="Allow online download of embedder")
    args = parser.parse_args()

    try:
        validated = validate_and_import_synthetic_gold(
            input_path=args.input,
            output_path=args.output,
            context_packs_path=args.context_packs,
            local_files_only=not args.no_local_files_only,
        )
        print(f"\n[VALIDATOR PASS] Successfully processed and merged {len(validated)} candidate queries.")
    except Exception as e:
        print(f"\n[VALIDATOR ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
