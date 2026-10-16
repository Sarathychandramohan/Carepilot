"""
backend/db_migrations/003_add_skip_reason_to_consultations.py

Migration: Add skip_reason column to consultations table.

What this migration does:
  Adds nullable column consultations.skip_reason VARCHAR(50).
  Stores the reason why LLM draft generation was bypassed:
    - 'emergency'               : Firm red-flag triage override
    - 'unsupported_intent'      : Unsupported intent safety gate (administrative / billing)
    - 'generation_parse_failed' : Generation JSON parse failed on retries
    - 'validation_failed'       : Faithfulness validation returned manual_required
    - 'patient_ehr_mismatch'    : D17 clinical conflict detection
    - 'missing_context'         : D17 missing context gate
    - NULL                      : Generation proceeded normally

Usage:
    python backend/db_migrations/003_add_skip_reason_to_consultations.py --apply
    python backend/db_migrations/003_add_skip_reason_to_consultations.py --rollback
    python backend/db_migrations/003_add_skip_reason_to_consultations.py --check
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

sys.path.insert(0, ".")
from backend.app.db.session import engine

MIGRATION_ID = "003_add_skip_reason_to_consultations"

FORWARD_SQL = [
    """
    ALTER TABLE consultations
        ADD COLUMN IF NOT EXISTS skip_reason VARCHAR(50)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_consultations_skip_reason
        ON consultations(skip_reason)
        WHERE skip_reason IS NOT NULL
    """,
]

ROLLBACK_SQL = [
    "DROP INDEX IF EXISTS idx_consultations_skip_reason",
    "ALTER TABLE consultations DROP COLUMN IF EXISTS skip_reason",
]

CHECK_SQL = """
SELECT COUNT(*) FROM information_schema.columns
WHERE table_name = 'consultations'
  AND column_name = 'skip_reason'
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
    exists = bool(row[0]) if row else False
    print(f"\n[{MIGRATION_ID}] Status check:")
    print(f"  consultations.skip_reason exists: {exists}")
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
            applied = check(conn)
            if applied:
                print("\n[INFO] Migration already applied. Nothing to do.")
                sys.exit(0)
            apply(conn)
            print("\nFinal state:")
            check(conn)
        elif args.rollback:
            rollback(conn)
            print("\nFinal state:")
            check(conn)
