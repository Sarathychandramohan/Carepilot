"""
D:\\CarePilotAI\\backend\\eval\\config.py

Pillar C Evaluation Configuration.
Defines active ablation arms, benchmark thresholds, dataset filepaths, and dataset IDs.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Active Ablation Arms
# ---------------------------------------------------------------------------
# Note: unified_context is explicitly deferred per C0 audit Decision D-C1
# (not yet implemented as a genuine separate single-pool retrieval path).
ACTIVE_ABLATION_ARMS: list[str] = [
    "full",
    "no_ehr",
    "no_classifier",
]

# ---------------------------------------------------------------------------
# Evaluation Thresholds & Hyperparameters
# ---------------------------------------------------------------------------
THRESHOLDS: dict[str, Any] = {
    "faithfulness_threshold": 0.80,      # Citation coverage floor
    "nli_entailment_threshold": 0.40,    # NLI sentence entailment floor
    "retrieval_alpha": 0.50,             # Dense / BM25 convex combination weight
    "urgency_tau_high": 0.65,            # High urgency classification cutoff
    "lab_tolerance_relative": 0.15,      # EHR-fact relative numeric tolerance
    "lab_date_window_days": 90,          # EHR-fact approximate date window
}

# ---------------------------------------------------------------------------
# Artifact & Model Provenance Identifiers
# ---------------------------------------------------------------------------
KB_SNAPSHOT_ID = "v5"
EHR_DATASET_ID = "carepilot_v3"
PROMPT_VERSION = "v1"
LLM_MODEL = "qwen3:8b"

# ---------------------------------------------------------------------------
# Dataset File Paths
# ---------------------------------------------------------------------------
DATA_DIR = PROJECT_ROOT / "data" / "queries"

DATASET_PATHS: dict[str, Path] = {
    "gold_candidate": DATA_DIR / "gold_scripted_candidate.jsonl",
    "silver": DATA_DIR / "silver.jsonl",
    "rq3": DATA_DIR / "rq3_stream.jsonl",
}

# Allowed split names
SUPPORTED_SPLITS = [
    "gold-dev",
    "gold-test",
    "silver-dev",
    "silver-test",
    "rq3",
]
