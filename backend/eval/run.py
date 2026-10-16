"""
D:\\CarePilotAI\\backend\\eval\\run.py

Pillar C Evaluation Runner CLI.
Drives query execution through the live orchestrator pipeline, tracks runs in eval_runs table,
links generated consultation rows, and supports real execution and wiring dry-runs.

Usage:
    python -m backend.eval.run --config full --split gold-dev --seed 42
    python -m backend.eval.run --config no_ehr --split gold-dev --seed 42 --subset 5
    python -m backend.eval.run --config full --split gold-dev --seed 42 --subset 2 --dry-run
"""
from __future__ import annotations

import argparse
import datetime
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.app.core.settings import settings
from backend.app.db.session import engine, SessionLocal
from backend.app.db.models_v3 import EvalRun, Consultation
from backend.app.pipeline.orchestrator import run_pipeline
from backend.eval.config import (
    ACTIVE_ABLATION_ARMS,
    SUPPORTED_SPLITS,
    THRESHOLDS,
    KB_SNAPSHOT_ID,
    EHR_DATASET_ID,
    PROMPT_VERSION,
)
from backend.eval.query_sets import load_query_split, EvalQuery


def assert_preflight_invariants(db: Session) -> None:
    """Refuse to run if active database or KB configuration doesn't match frozen specs."""
    if settings.db_name != EHR_DATASET_ID:
        raise RuntimeError(
            f"Preflight check failed: Active DB is '{settings.db_name}', expected '{EHR_DATASET_ID}'."
        )

    if settings.kb_snapshot_id != KB_SNAPSHOT_ID:
        raise RuntimeError(
            f"Preflight check failed: Active KB snapshot is '{settings.kb_snapshot_id}', expected '{KB_SNAPSHOT_ID}'."
        )

    # Check that patients exist and are loaded
    alive_count = db.execute(text("SELECT COUNT(*) FROM patients WHERE is_alive = true")).scalar()
    if not alive_count or alive_count < 2000:
        raise RuntimeError(f"Preflight check failed: expected >= 2000 alive patients, found {alive_count}.")


def execute_eval_run(
    config: str | None = None,
    split: str | None = None,
    seed: int = 42,
    subset_n: int | None = None,
    dry_run: bool = False,
    resume_id: int | None = None,
    subset_strategy: str = "head",
    per_family: int | None = None,
) -> int:
    """
    Executes an evaluation run and returns the eval_run_id.
    Supports resuming an interrupted run via resume_id.
    """
    random.seed(seed)
    started_at = datetime.datetime.utcnow()

    with SessionLocal() as db:
        assert_preflight_invariants(db)

        if resume_id:
            eval_run = db.query(EvalRun).filter(EvalRun.id == resume_id).first()
            if not eval_run:
                raise ValueError(f"Eval run with id={resume_id} not found.")

            cfg_dict = json.loads(eval_run.config) if eval_run.config else {}
            config = cfg_dict.get("ablation_arm", eval_run.run_name.split("_")[0])
            dry_run = cfg_dict.get("dry_run", dry_run)
            split = eval_run.split or split
            seed = eval_run.seed or seed
            eval_run_id = eval_run.id
            eval_run.status = "running"
            db.add(eval_run)
            db.commit()

            # Find already executed query texts for this run to avoid duplicate execution
            existing_query_texts = set(
                db.execute(
                    text("SELECT query_text FROM consultations WHERE eval_run_id = :rid"),
                    {"rid": eval_run_id},
                ).scalars().all()
            )
            print(f"[EVAL RUN RESUME] ID={eval_run_id} | Existing completed queries={len(existing_query_texts)}")
        else:
            if not config or config not in ACTIVE_ABLATION_ARMS:
                raise ValueError(
                    f"Invalid ablation config '{config}'. Active ablation arms allowed: {ACTIVE_ABLATION_ARMS}. "
                    f"(Note: unified_context is deferred per Decision D-C1)."
                )
            if not split or split not in SUPPORTED_SPLITS:
                raise ValueError(f"Invalid split '{split}'. Supported splits: {SUPPORTED_SPLITS}")

            # 1. Create eval_runs record
            eval_run = EvalRun(
                run_name=f"{config}_{split}_{seed}_{int(time.time())}",
                pipeline_version="pillar_c_v1",
                status="running",
                config=json.dumps({
                    "ablation_arm": config,
                    "dry_run": dry_run,
                    "subset_strategy": subset_strategy,
                    "per_family": per_family,
                }),
                split=split,
                seed=seed,
                kb_snapshot_id=KB_SNAPSHOT_ID,
                ehr_dataset_id=EHR_DATASET_ID,
                prompt_version=PROMPT_VERSION,
                thresholds=THRESHOLDS,
                started_at=started_at,
            )
            db.add(eval_run)
            db.commit()
            db.refresh(eval_run)
            eval_run_id = eval_run.id
            existing_query_texts = set()
            print(f"[EVAL RUN START] ID={eval_run_id} | Config={config} | Split={split} | DryRun={dry_run}")

        # 2. Load dataset split queries
        queries = load_query_split(
            split,
            db=db,
            subset_n=subset_n,
            subset_strategy=subset_strategy,
            per_family=per_family,
            seed=seed,
        )
        if subset_strategy == "family-stratified":
            from collections import Counter, defaultdict
            counts = Counter(q.raw_metadata.get("scenario_family", "unknown") for q in queries)
            distinct_counts = defaultdict(set)
            for q in queries:
                fam = q.raw_metadata.get("scenario_family", "unknown")
                distinct_counts[fam].add(q.query_text.strip())

            print(f"[STRATIFIED SAMPLING] Selected {len(queries)} queries across {len(counts)} families:")
            for fam, cnt in sorted(counts.items()):
                print(f"  {fam:<30}: {cnt} rows, {len(distinct_counts[fam])} distinct texts")

        queries_to_run = [q for q in queries if q.query_text not in existing_query_texts]
        print(f"[DATASET] Loaded {len(queries)} total queries for split '{split}' (Remaining to execute: {len(queries_to_run)})")

        completed_count = len(existing_query_texts)
        failed_count = 0

        # 3. Process remaining queries sequentially
        for idx, q in enumerate(queries_to_run, start=len(existing_query_texts) + 1):
            t0 = time.time()
            try:
                if dry_run:
                    # Validate wiring & pipeline logic without real LLM call:
                    from unittest.mock import patch
                    from backend.app.pipeline.generate import GeneratedDraft, DraftSentence

                    mock_draft = GeneratedDraft(
                        sentences=[DraftSentence(text="Patient is clinically stable based on review.", citations=[])],
                        overall_tone="informative",
                        recommended_followup=None,
                        urgency_assessment="routine",
                        llm_model="dry-run-mock",
                        prompt_version="v1",
                        generation_latency_ms=10,
                        raw_llm_output="{}",
                    )
                    with patch("backend.app.pipeline.orchestrator.generate_draft", return_value=mock_draft):
                        consultation = run_pipeline(
                            patient_id=q.patient_id,
                            query_text=q.query_text,
                            db=db,
                            ablation_config=config,
                            is_eval=True,
                            eval_run_id=eval_run_id,
                        )

                else:
                    # Full real pipeline execution with Ollama Qwen3:8B
                    consultation = run_pipeline(
                        patient_id=q.patient_id,
                        query_text=q.query_text,
                        db=db,
                        ablation_config=config,
                        is_eval=True,
                        eval_run_id=eval_run_id,
                    )

                latency_s = time.time() - t0
                completed_count += 1
                print(
                    f"  [{idx}/{len(queries)}] Query={q.query_id} -> ConsultID={consultation.id[:8]}.. "
                    f"| Latency={latency_s:.2f}s | Intent={consultation.intent} | Urgency={consultation.urgency_final}"
                )

            except Exception as e:
                failed_count += 1
                print(f"  [{idx}/{len(queries)}] Query={q.query_id} FAILED: {e}", file=sys.stderr)

        # 4. Finalize eval_run row
        eval_run.status = "completed" if failed_count == 0 else "completed_with_errors"
        eval_run.finished_at = datetime.datetime.utcnow()
        eval_run.metrics = {
            "total_queries": len(queries),
            "completed": completed_count,
            "failed": failed_count,
            "duration_seconds": (eval_run.finished_at - (eval_run.started_at or started_at)).total_seconds(),
        }
        db.add(eval_run)
        db.commit()
        print(
            f"[EVAL RUN FINISH] ID={eval_run_id} | Status={eval_run.status} | "
            f"Completed={completed_count}/{len(queries)} | Duration={eval_run.metrics['duration_seconds']:.1f}s"
        )

        return eval_run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="CarePilot AI Pillar C Evaluation Runner")
    parser.add_argument(
        "--config",
        choices=ACTIVE_ABLATION_ARMS,
        default=None,
        help="Ablation configuration arm to run",
    )
    parser.add_argument(
        "--split",
        choices=SUPPORTED_SPLITS,
        default=None,
        help="Query set split to evaluate",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for evaluation determinism",
    )
    parser.add_argument(
        "--subset",
        type=int,
        default=None,
        help="Optional query limit for dry-runs or subset evaluation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate wiring and database recording without real LLM generation calls",
    )
    parser.add_argument(
        "--resume",
        type=int,
        default=None,
        help="Resume an interrupted evaluation run by eval_run_id",
    )
    parser.add_argument(
        "--subset-strategy",
        choices=["head", "family-stratified"],
        default="head",
        help="Subset strategy: 'head' (sequential first N) or 'family-stratified' (sample N per scenario family)",
    )
    parser.add_argument(
        "--per-family",
        type=int,
        default=None,
        help="Number of queries to sample per scenario_family in family-stratified mode",
    )

    args = parser.parse_args()
    if not args.resume and (not args.config or not args.split):
        parser.error("--config and --split are required when not using --resume.")

    execute_eval_run(
        config=args.config,
        split=args.split,
        seed=args.seed,
        subset_n=args.subset,
        dry_run=args.dry_run,
        resume_id=args.resume,
        subset_strategy=args.subset_strategy,
        per_family=args.per_family,
    )


if __name__ == "__main__":
    main()
