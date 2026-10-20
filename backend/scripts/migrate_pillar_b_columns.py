"""
D:\\CarePilotAI\\backend\\scripts\\migrate_pillar_b_columns.py

Alembic-free migration: adds all Pillar B columns to the consultations table
and renames edit_burden_weighted → consultation_edit_weight.

Safe to run multiple times — uses IF NOT EXISTS / DO NOTHING guards.

Usage:
    python -m backend.scripts.migrate_pillar_b_columns
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.settings import settings  # noqa: E402


# ---------------------------------------------------------------------------
# Column definitions: (name, pg_type, default_clause)
# ---------------------------------------------------------------------------
NEW_COLUMNS = [
    # B2 — urgency agreement
    ("urgency_agreement", "VARCHAR(20)", "DEFAULT NULL"),

    # B3 — retrieval provenance
    ("retrieval_trace_json", "JSONB", "DEFAULT NULL"),
    ("patient_ehr_mismatch_flag", "BOOLEAN", "DEFAULT FALSE"),
    ("missing_context_flag", "BOOLEAN", "DEFAULT FALSE"),
    ("outlier_chunk_count", "INTEGER", "DEFAULT 0"),

    # B4 — LLM self-report + edit memory (D6)
    ("llm_urgency_self_reported", "VARCHAR(10)", "DEFAULT NULL"),
    ("edit_memory_used", "BOOLEAN", "DEFAULT FALSE"),
    ("edit_memory_json", "JSONB", "DEFAULT NULL"),

    # B5 — outlier validation flags
    ("has_outlier_only_sentence", "BOOLEAN", "DEFAULT FALSE"),

    # Pillar C — supplementary edit distance ratios
    ("edr_char", "FLOAT", "DEFAULT NULL"),
    ("edr_word", "FLOAT", "DEFAULT NULL"),

    # Pillar C — per-consultation raw weighted edit sum (Section S9 naming)
    ("consultation_edit_weight", "FLOAT", "DEFAULT NULL"),
]

RENAME_COLUMNS = [
    # (old_name, new_name) — only if old exists and new does not
    ("edit_burden_weighted", "consultation_edit_weight"),
]


def run_migration() -> None:
    dsn = settings.db_url.replace("postgresql+psycopg://", "postgresql://")

    print("=" * 60)
    print("CarePilot AI — Pillar B DB Migration")
    print("=" * 60)

    conn = psycopg.connect(dsn)
    conn.autocommit = True
    with conn:
        with conn.cursor() as cur:


            # 1. Rename edit_burden_weighted → consultation_edit_weight if needed
            for old, new in RENAME_COLUMNS:
                cur.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'consultations' AND column_name = %s
                    """,
                    (old,),
                )
                old_exists = cur.fetchone() is not None

                cur.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'consultations' AND column_name = %s
                    """,
                    (new,),
                )
                new_exists = cur.fetchone() is not None

                if old_exists and not new_exists:
                    cur.execute(
                        f"ALTER TABLE consultations RENAME COLUMN {old} TO {new};"
                    )
                    print(f"  [RENAMED] {old} -> {new}")
                elif new_exists:
                    print(f"  [SKIP] {new} already exists")
                else:
                    print(f"  [SKIP] {old} not found (already migrated or never existed)")


            # 2. Add new columns (idempotent via information_schema check)
            for col_name, col_type, col_default in NEW_COLUMNS:
                cur.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'consultations' AND column_name = %s
                    """,
                    (col_name,),
                )
                if cur.fetchone() is not None:
                    print(f"  [SKIP] {col_name} already exists")
                    continue

                cur.execute(
                    f"ALTER TABLE consultations ADD COLUMN {col_name} {col_type} {col_default};"
                )
                print(f"  [ADDED] {col_name} {col_type}")

    print("\n[OK] Pillar B migration complete.")
    print("=" * 60)


if __name__ == "__main__":
    run_migration()
