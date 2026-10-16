"""
D:\\CarePilotAI\\backend\\eval\\query_sets.py

Dataset loaders for Pillar C evaluation harness.
Loads and validates queries across gold-dev, gold-test, silver-dev, silver-test, and rq3 splits.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.eval.config import DATASET_PATHS, SUPPORTED_SPLITS


@dataclass
class EvalQuery:
    query_id: str
    query_text: str
    patient_id: str
    tier: str
    split: str
    intent_ground_truth: str | None = None
    urgency_ground_truth: str | None = None
    requires_patient_context: bool = False
    expected_kb_doc_ids: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "query_text": self.query_text,
            "patient_id": self.patient_id,
            "tier": self.tier,
            "split": self.split,
            "intent_ground_truth": self.intent_ground_truth,
            "urgency_ground_truth": self.urgency_ground_truth,
            "requires_patient_context": self.requires_patient_context,
            "expected_kb_doc_ids": self.expected_kb_doc_ids,
        }


def _get_default_alive_patient_id(db: Session) -> str:
    """Fetch a default alive patient ID for general queries lacking patient context."""
    row = db.execute(text("SELECT id FROM patients WHERE is_alive = true LIMIT 1")).fetchone()
    if not row:
        raise RuntimeError("No alive patient found in database to ground general queries.")
    return str(row[0])


def load_query_split(
    split_name: str,
    db: Session,
    subset_n: int | None = None,
) -> list[EvalQuery]:
    """
    Load and validate queries for the requested split.

    Args:
        split_name: One of 'gold-dev', 'gold-test', 'silver-dev', 'silver-test', 'rq3'.
        db: SQLAlchemy DB session (for patient validation / grounding).
        subset_n: Optional integer limiting the number of queries loaded.

    Returns:
        List of validated EvalQuery objects.
    """
    if split_name not in SUPPORTED_SPLITS:
        raise ValueError(f"Unknown split '{split_name}'. Supported splits: {SUPPORTED_SPLITS}")

    default_patient_id = _get_default_alive_patient_id(db)
    queries: list[EvalQuery] = []

    if split_name in ("gold-dev", "gold-test"):
        path = DATASET_PATHS["gold_candidate"]
        target_subsplit = "dev" if split_name == "gold-dev" else "test"
        if not path.exists():
            raise FileNotFoundError(f"Gold candidate file not found at: {path}")

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("split") != target_subsplit:
                    continue

                pid = row.get("patient_id") or default_patient_id
                queries.append(
                    EvalQuery(
                        query_id=row["query_id"],
                        query_text=row["query_text"],
                        patient_id=pid,
                        tier="gold",
                        split=split_name,
                        intent_ground_truth=row.get("intent_label"),
                        urgency_ground_truth=row.get("urgency_label"),
                        requires_patient_context=bool(row.get("requires_patient_context", False)),
                        expected_kb_doc_ids=row.get("expected_kb_doc_ids") or [],
                        raw_metadata=row,
                    )
                )

    elif split_name in ("silver-dev", "silver-test"):
        path = DATASET_PATHS["silver"]
        target_subsplit = "dev" if split_name == "silver-dev" else "test"
        if not path.exists():
            raise FileNotFoundError(f"Silver dataset file not found at: {path}")

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("split") != target_subsplit:
                    continue

                pid = row.get("patient_id") or default_patient_id
                queries.append(
                    EvalQuery(
                        query_id=row["query_id"],
                        query_text=row["query_text"],
                        patient_id=pid,
                        tier="silver",
                        split=split_name,
                        intent_ground_truth=row.get("intent_label"),
                        urgency_ground_truth=row.get("urgency_label"),
                        requires_patient_context=bool(row.get("requires_patient_context", False)),
                        raw_metadata=row,
                    )
                )

    elif split_name == "rq3":
        path = DATASET_PATHS["rq3"]
        if not path.exists():
            raise FileNotFoundError(f"RQ3 dataset file not found at: {path}")

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                pid = row.get("patient_id") or default_patient_id
                queries.append(
                    EvalQuery(
                        query_id=row["query_id"],
                        query_text=row["query_text"],
                        patient_id=pid,
                        tier="rq3_stream",
                        split="rq3",
                        intent_ground_truth=row.get("intent_label"),
                        urgency_ground_truth=row.get("urgency_label"),
                        requires_patient_context=bool(row.get("requires_patient_context", False)),
                        raw_metadata=row,
                    )
                )

    if subset_n is not None and subset_n > 0:
        queries = queries[:subset_n]

    return queries
