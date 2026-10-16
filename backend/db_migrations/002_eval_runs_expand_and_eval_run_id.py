"""
D:\\CarePilotAI\\backend\\db_migrations\\002_eval_runs_expand_and_eval_run_id.py

Migration: Expand eval_runs table + add eval_run_id FK to consultations.

What this migration does:
  1. Expands eval_runs with columns:
       config          TEXT           — JSON-serialised eval harness config dict
       split           VARCHAR(20)    — 'dev' | 'test' | 'heldout'
       seed            INTEGER        — random seed used for this run
       kb_snapshot_id  VARCHAR(20)    — FK → kb_snapshots.snapshot_id (nullable)
       ehr_dataset_id  VARCHAR(50)    — identifier for the EHR patient cohort used
       prompt_version  VARCHAR(20)    — prompt template version (e.g. 'v1')
       thresholds      JSONB          — faithfulness_threshold, nli_*, etc.
       started_at      TIMESTAMP      — when harness began running
       finished_at     TIMESTAMP      — when harness completed (NULL if still running)

  2. Adds eval_run_id INTEGER → eval_runs.id (nullable FK) to consultations.
     Existing rows get eval_run_id = NULL (they predate run tracking).

Rollback: reverse_sql statements provided.

Usage:
    python backend/db_migrations/002_eval_runs_expand_and_eval_run_id.py --apply
    python backend/db_migrations/002_eval_runs_expand_and_eval_run_id.py --rollback
    python backend/db_migrations/002_eval_runs_expand_and_eval_run_id.py --check
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

# Use project session (reads backend/.env automatically)
sys.path.insert(0, ".")
from backend.app.db.session import engine


MIGRATION_ID = "002_eval_runs_expand_and_eval_run_id"

# ---------------------------------------------------------------------------
# Forward migration
# ---------------------------------------------------------------------------

FORWARD_SQL = [
    # ── eval_runs: new columns ──────────────────────────────────────────────
    """
    ALTER TABLE eval_runs
        ADD COLUMN IF NOT EXISTS config          TEXT,
        ADD COLUMN IF NOT EXISTS split           VARCHAR(20),
        ADD COLUMN IF NOT EXISTS seed            INTEGER,
        ADD COLUMN IF NOT EXISTS kb_snapshot_id  VARCHAR(20)
            REFERENCES kb_snapshots(snapshot_id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS ehr_dataset_id  VARCHAR(50),
        ADD COLUMN IF NOT EXISTS prompt_version  VARCHAR(20),
        ADD COLUMN IF NOT EXISTS thresholds      JSONB,
        ADD COLUMN IF NOT EXISTS started_at      TIMESTAMP,
        ADD COLUMN IF NOT EXISTS finished_at     TIMESTAMP
    """,

    # ── consultations: add eval_run_id FK ───────────────────────────────────
    """
    ALTER TABLE consultations
        ADD COLUMN IF NOT EXISTS eval_run_id INTEGER
            REFERENCES eval_runs(id) ON DELETE SET NULL
    """,

    # ── Index for quick lookup of all consultations belonging to one run ────
    """
    CREATE INDEX IF NOT EXISTS idx_consultations_eval_run_id
        ON consultations(eval_run_id)
        WHERE eval_run_id IS NOT NULL
    """,
]

# ---------------------------------------------------------------------------
# Rollback (reverse) migration
# ---------------------------------------------------------------------------

ROLLBACK_SQL = [
    "DROP INDEX IF EXISTS idx_consultations_eval_run_id",

    "ALTER TABLE consultations DROP COLUMN IF EXISTS eval_run_id",

    """
    ALTER TABLE eval_runs
        DROP COLUMN IF EXISTS config,
        DROP COLUMN IF EXISTS split,
        DROP COLUMN IF EXISTS seed,
        DROP COLUMN IF EXISTS kb_snapshot_id,
        DROP COLUMN IF EXISTS ehr_dataset_id,
        DROP COLUMN IF EXISTS prompt_version,
        DROP COLUMN IF EXISTS thresholds,
        DROP COLUMN IF EXISTS started_at,
        DROP COLUMN IF EXISTS finished_at
    """,
]

# ---------------------------------------------------------------------------
# Check: does the migration appear to be applied?
# ---------------------------------------------------------------------------

CHECK_SQL = """
SELECT
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_name = 'eval_runs'
       AND column_name = 'started_at') AS eval_runs_started_at_exists,
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_name = 'consultations'
       AND column_name = 'eval_run_id') AS consultations_eval_run_id_exists,
    (SELECT COUNT(*) FROM information_schema.table_constraints tc
     JOIN information_schema.constraint_column_usage ccu
       ON tc.constraint_name = ccu.constraint_name
     WHERE tc.constraint_type = 'FOREIGN KEY'
       AND tc.table_name = 'consultations'
       AND ccu.column_name = 'eval_run_id') AS fk_exists
"""


def apply(conn) -> None:
    print(f"[{MIGRATION_ID}] Applying forward migration …")
    for i, sql in enumerate(FORWARD_SQL, 1):
        print(f"  Step {i}/{len(FORWARD_SQL)} …", end=" ", flush=True)
        conn.execute(text(sql))
        print("OK")
    conn.commit()
    print(f"[{MIGRATION_ID}] Forward migration complete.")


def rollback(conn) -> None:
    print(f"[{MIGRATION_ID}] Rolling back migration …")
    for i, sql in enumerate(ROLLBACK_SQL, 1):
        print(f"  Step {i}/{len(ROLLBACK_SQL)} …", end=" ", flush=True)
        conn.execute(text(sql))
        print("OK")
    conn.commit()
    print(f"[{MIGRATION_ID}] Rollback complete.")


def check(conn) -> bool:
    row = conn.execute(text(CHECK_SQL)).fetchone()
    print(f"\n[{MIGRATION_ID}] Status check:")
    print(f"  eval_runs.started_at exists          : {bool(row[0])}")
    print(f"  consultations.eval_run_id exists      : {bool(row[1])}")
    print(f"  FK consultations->eval_runs exists    : {bool(row[2])}")

    applied = bool(row[0]) and bool(row[1])
    print(f"\n  -> Migration status: {'APPLIED' if applied else 'NOT APPLIED'}")

    return applied


def _verify_existing_rows_null(conn) -> None:
    """Confirm all pre-migration consultation rows have eval_run_id = NULL."""
    n_non_null = conn.execute(
        text("SELECT COUNT(*) FROM consultations WHERE eval_run_id IS NOT NULL")
    ).scalar()
    n_total = conn.execute(text("SELECT COUNT(*) FROM consultations")).scalar()
    print(f"\n[{MIGRATION_ID}] Post-migration integrity check:")
    print(f"  Total consultation rows : {n_total}")
    print(f"  Rows with eval_run_id IS NOT NULL : {n_non_null}")
    if n_non_null == 0:
        print("  ✓ All pre-existing rows correctly have eval_run_id = NULL")
    else:
        print(f"  ⚠ WARNING: {n_non_null} rows have a non-NULL eval_run_id already.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"Migration {MIGRATION_ID}")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply",    action="store_true", help="Apply forward migration")
    group.add_argument("--rollback", action="store_true", help="Roll back migration")
    group.add_argument("--check",    action="store_true", help="Check migration status (read-only)")
    args = parser.parse_args()

    with engine.connect() as conn:
        if args.check:
            check(conn)
        elif args.apply:
            applied = check(conn)
            if applied:
                print("\n[INFO] Migration already applied. Nothing to do.")
                sys.exit(0)
            apply(conn)
            _verify_existing_rows_null(conn)
            print("\nFinal state:")
            check(conn)
        elif args.rollback:
            rollback(conn)
            print("\nFinal state:")
            check(conn)
