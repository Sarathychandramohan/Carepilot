"""
backend/db_migrations/004_add_git_commit_and_eval_query_id.py

Migration: Add git_commit to eval_runs, add eval_query_id (indexed) to consultations,
and mark historical eval_runs 2-8 as invalid_wrong_thresholds.

Usage:
    python backend/db_migrations/004_add_git_commit_and_eval_query_id.py --apply
    python backend/db_migrations/004_add_git_commit_and_eval_query_id.py --rollback
    python backend/db_migrations/004_add_git_commit_and_eval_query_id.py --check
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

sys.path.insert(0, ".")
from backend.app.db.session import engine

MIGRATION_ID = "004_add_git_commit_and_eval_query_id"

FORWARD_SQL = [
    """
    ALTER TABLE eval_runs
        ADD COLUMN IF NOT EXISTS git_commit VARCHAR(40)
    """,
    """
    ALTER TABLE consultations
        ADD COLUMN IF NOT EXISTS eval_query_id VARCHAR(64)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_consultations_eval_query_id
        ON consultations(eval_query_id)
        WHERE eval_query_id IS NOT NULL
    """,
    """
    UPDATE eval_runs
    SET status = 'invalid_wrong_thresholds'
    WHERE id IN (2, 3, 4, 5, 6, 7, 8)
    """,
]

ROLLBACK_SQL = [
    "DROP INDEX IF EXISTS idx_consultations_eval_query_id",
    "ALTER TABLE consultations DROP COLUMN IF EXISTS eval_query_id",
    "ALTER TABLE eval_runs DROP COLUMN IF EXISTS git_commit",
]

CHECK_SQL_EVAL = """
SELECT COUNT(*) FROM information_schema.columns
WHERE table_name = 'eval_runs'
  AND column_name = 'git_commit'
"""

CHECK_SQL_CONSULT = """
SELECT COUNT(*) FROM information_schema.columns
WHERE table_name = 'consultations'
  AND column_name = 'eval_query_id'
"""


def apply(conn) -> None:
    print(f"[{MIGRATION_ID}] Applying forward migration …")
    for i, sql in enumerate(FORWARD_SQL, 1):
        print(f"  Step {i}/{len(FORWARD_SQL)} …", end=" ", flush=True)
        res = conn.execute(text(sql))
        if "UPDATE eval_runs" in sql:
            print(f"OK ({res.rowcount} rows updated to 'invalid_wrong_thresholds')")
        else:
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
    row_eval = conn.execute(text(CHECK_SQL_EVAL)).fetchone()
    row_consult = conn.execute(text(CHECK_SQL_CONSULT)).fetchone()
    eval_ok = bool(row_eval[0]) if row_eval else False
    consult_ok = bool(row_consult[0]) if row_consult else False
    exists = eval_ok and consult_ok

    print(f"\n[{MIGRATION_ID}] Status check:")
    print(f"  eval_runs.git_commit exists: {eval_ok}")
    print(f"  consultations.eval_query_id exists: {consult_ok}")
    print(f"  -> Migration status: {'APPLIED' if exists else 'NOT APPLIED'}")
    return exists


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"Migration {MIGRATION_ID}")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="Apply forward migration")
    group.add_argument("--rollback", action="store_true", help="Roll back migration")
    group.add_argument("--check", action="store_true", help="Check migration status (read-only)")
    args = parser.parse_args()

    with engine.connect() as conn:
        if args.check:
            check(conn)
        elif args.apply:
            apply(conn)
        elif args.rollback:
            rollback(conn)
