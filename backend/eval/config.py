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

from backend.app.pipeline.classify import load_urgency_model
from backend.app.pipeline.validate import (
    CONTRADICTION_CEILING,
    COVERAGE_THRESHOLD,
    NLI_PASS_THRESHOLD,
    NLI_WARN_THRESHOLD,
)

# ---------------------------------------------------------------------------
# Evaluation Thresholds & Hyperparameters
# Imported directly from pipeline modules to guarantee provenance consistency.
# ---------------------------------------------------------------------------
try:
    _urg_model = load_urgency_model()
    tau_high: float = float(_urg_model.get("tau_high", 0.25))
    tau_soon: float = float(_urg_model.get("tau_soon", 0.30))
    tau_intent: float = float(_urg_model.get("tau_intent", 0.45))
except Exception:
    tau_high = 0.25
    tau_soon = 0.30
    tau_intent = 0.45

THRESHOLDS: dict[str, Any] = {
    "coverage_threshold": COVERAGE_THRESHOLD,            # Citation coverage floor (0.80)
    "faithfulness_threshold": COVERAGE_THRESHOLD,        # Alias for backward compatibility
    "nli_pass_threshold": NLI_PASS_THRESHOLD,            # NLI sentence entailment floor (0.15)
    "nli_warn_threshold": NLI_WARN_THRESHOLD,            # NLI sentence entailment warning floor (0.001)
    "nli_entailment_threshold": NLI_PASS_THRESHOLD,      # Alias for backward compatibility
    "contradiction_ceiling": CONTRADICTION_CEILING,      # Hallucination/contradiction ceiling (0.05)
    "urgency_tau_high": tau_high,                        # High urgency classification cutoff (0.25)
    "tau_high": tau_high,                                # Direct pipeline constant name
    "tau_soon": tau_soon,                                # Routine vs soon threshold (0.30)
    "tau_intent": tau_intent,                            # Supported intent confidence floor (0.45)
    "retrieval_alpha": 0.50,                             # Dense / BM25 convex combination weight
    "lab_tolerance_relative": 0.15,                      # EHR-fact relative numeric tolerance
    "lab_date_window_days": 90,                          # EHR-fact approximate date window
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
