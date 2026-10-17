"""
backend/eval/tools/make_manifest.py

Generates docs/eval_manifest.json with complete SHA-256 hashes, git HEAD commit,
imported thresholds, Python environment, and package versions for Pillar C freeze-eval.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOCS_DIR = PROJECT_ROOT / "docs"
MANIFEST_FILE = DOCS_DIR / "eval_manifest.json"


def sha256_file(p: Path) -> str:
    if not p.exists():
        return "MISSING_PENDING_INPUT"
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_git_head() -> str:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "unknown"


def get_installed_packages() -> dict[str, str]:
    pkgs = {}
    target_pkgs = [
        "torch",
        "transformers",
        "sentence-transformers",
        "scikit-learn",
        "numpy",
        "scipy",
        "sqlalchemy",
        "pydantic",
        "alembic",
        "fastapi",
        "rank-bm25",
        "chromadb",
        "psycopg2",
        "asyncpg",
    ]
    try:
        import importlib.metadata
        for pkg in target_pkgs:
            try:
                pkgs[pkg] = importlib.metadata.version(pkg)
            except Exception:
                pkgs[pkg] = "not_installed"
    except Exception as e:
        pkgs["error"] = str(e)
    return pkgs


def make_manifest() -> dict[str, Any]:
    from backend.eval.config import (
        THRESHOLDS,
        KB_SNAPSHOT_ID,
        EHR_DATASET_ID,
        PROMPT_VERSION,
        ACTIVE_ABLATION_ARMS,
        SUPPORTED_SPLITS,
    )

    manifest_data = {
        "manifest_version": "1.0.0",
        "evaluation_tag": "freeze-eval",
        "git_commit": get_git_head(),
        "python_version": sys.version,
        "package_versions": get_installed_packages(),
        "constants": {
            "kb_snapshot_id": KB_SNAPSHOT_ID,
            "ehr_dataset_id": EHR_DATASET_ID,
            "prompt_version": PROMPT_VERSION,
            "active_ablation_arms": ACTIVE_ABLATION_ARMS,
            "supported_splits": SUPPORTED_SPLITS,
        },
        "thresholds": THRESHOLDS,
        "files_sha256": {
            "data/queries/gold_synthetic_pilot_labels_sealed.csv": sha256_file(
                PROJECT_ROOT / "data" / "queries" / "gold_synthetic_pilot_labels_sealed.csv"
            ),
            "data/annotation/queries_noehr_45.jsonl": sha256_file(
                PROJECT_ROOT / "data" / "annotation" / "queries_noehr_45.jsonl"
            ),
            "data/queries/silver.jsonl": sha256_file(
                PROJECT_ROOT / "data" / "queries" / "silver.jsonl"
            ),
            "data/annotation/context_packs.jsonl": sha256_file(
                PROJECT_ROOT / "data" / "annotation" / "context_packs.jsonl"
            ),
            "data/annotation/context_packs_new_45_v2.jsonl": sha256_file(
                PROJECT_ROOT / "data" / "annotation" / "context_packs_new_45_v2.jsonl"
            ),
            "data/annotation/gold_synthetic_pilot.jsonl": sha256_file(
                PROJECT_ROOT / "data" / "annotation" / "gold_synthetic_pilot.jsonl"
            ),
            "backend/models/intent_classifier.pkl": sha256_file(
                PROJECT_ROOT / "backend" / "models" / "intent_classifier.pkl"
            ),
            "backend/models/urgency_classifier.pkl": sha256_file(
                PROJECT_ROOT / "backend" / "models" / "urgency_classifier.pkl"
            ),
            "backend/models/corpus_mean_bge_small.npy": sha256_file(
                PROJECT_ROOT / "backend" / "models" / "corpus_mean_bge_small.npy"
            ),
            "backend/app/pipeline/redflag.py": sha256_file(
                PROJECT_ROOT / "backend" / "app" / "pipeline" / "redflag.py"
            ),
            "backend/app/pipeline/orchestrator.py": sha256_file(
                PROJECT_ROOT / "backend" / "app" / "pipeline" / "orchestrator.py"
            ),
            "backend/app/pipeline/generate.py": sha256_file(
                PROJECT_ROOT / "backend" / "app" / "pipeline" / "generate.py"
            ),
            "backend/app/pipeline/classify.py": sha256_file(
                PROJECT_ROOT / "backend" / "app" / "pipeline" / "classify.py"
            ),
            "backend/app/pipeline/retrieve_kb.py": sha256_file(
                PROJECT_ROOT / "backend" / "app" / "pipeline" / "retrieve_kb.py"
            ),
            "backend/app/pipeline/retrieve_ehr.py": sha256_file(
                PROJECT_ROOT / "backend" / "app" / "pipeline" / "retrieve_ehr.py"
            ),
            "backend/app/pipeline/validate.py": sha256_file(
                PROJECT_ROOT / "backend" / "app" / "pipeline" / "validate.py"
            ),
            "backend/app/pipeline/detect_context_gaps.py": sha256_file(
                PROJECT_ROOT / "backend" / "app" / "pipeline" / "detect_context_gaps.py"
            ),
        },
    }

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    print(f"Successfully generated {MANIFEST_FILE}")
    return manifest_data


if __name__ == "__main__":
    data = make_manifest()
    print(json.dumps(data, indent=2))
