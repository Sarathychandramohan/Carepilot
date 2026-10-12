"""
D:\\CarePilotAI\\backend\\scripts\\create_db_schema.py

Creates all CarePilot v3 tables in carepilot_db.
Run this BEFORE merge_ehr.py (or synthea_bulk_load.py).

Credentials are read from backend/.env (DATABASE_URL or POSTGRES_PASSWORD).
Passwords are never printed or logged.

Usage:
    python -m backend.scripts.create_db_schema
    python -m backend.scripts.create_db_schema --drop-existing  # DESTRUCTIVE
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, text
from backend.app.db.models_v3 import Base


def read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def get_db_url(args) -> str:
    env = {**read_env(PROJECT_ROOT / "backend" / ".env"), **os.environ}
    if db_url := env.get("DATABASE_URL"):
        if "carepilot_db" in db_url:
            print("ERROR GUARD: DATABASE_URL points to 'carepilot_db'! Target MUST be 'carepilot_v3'. Stopping.")
            sys.exit(1)
        return db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    host     = args.db_host or env.get("DB_HOST", "localhost")
    port     = args.db_port or int(env.get("DB_PORT", "5432"))
    name     = args.db_name or env.get("DB_NAME", "carepilot_db")
    user     = args.db_user or env.get("DB_USER", "postgres")
    password = (
        env.get("POSTGRES_PASSWORD")
        or env.get("DB_PASSWORD")
        or env.get("PG_PASSWORD")
    )
    if not password:
        print("ERROR: No database password found in backend/.env.")
        print("       Add DATABASE_URL=postgresql://postgres:<pw>@localhost:5432/carepilot_db")
        print("       or POSTGRES_PASSWORD=<pw> to backend/.env and retry.")
        sys.exit(1)
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


def main():
    parser = argparse.ArgumentParser(description="Create CarePilot v3 schema")
    parser.add_argument("--db-host", default=None)
    parser.add_argument("--db-port", type=int, default=None)
    parser.add_argument("--db-name", default=None)
    parser.add_argument("--db-user", default=None)
    parser.add_argument(
        "--drop-existing", action="store_true",
        help="Drop all existing tables first (DESTRUCTIVE - use only in dev)"
    )
    args = parser.parse_args()

    db_url = get_db_url(args)
    engine = create_engine(db_url, echo=False)

    with engine.connect() as conn:
        result = conn.execute(text("SELECT current_database()"))
        print(f"Connected to: {result.scalar()}")

    if args.drop_existing:
        print("\n[WARNING] Dropping all existing tables (--drop-existing specified)...")
        Base.metadata.drop_all(engine)
        print("  All tables dropped.")

    print("\nCreating all CarePilot v3 tables...")
    Base.metadata.create_all(engine)

    # Verify
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        ))
        tables = [r[0] for r in result]

    print(f"\n[OK] Tables in DB ({len(tables)} total):")
    for t in tables:
        print(f"  - {t}")

    expected = {
        "patients", "encounters", "lab_results", "conditions",
        "prescriptions", "allergies", "procedures", "care_plans",
        "immunizations",
        "reference_ranges", "kb_documents", "kb_snapshots", "consultations",
    }
    missing = expected - set(tables)
    if missing:
        print(f"\n[WARN] Expected tables not found: {missing}", file=sys.stderr)
        sys.exit(1)
    else:
        print("\n[OK] All expected tables present.")


if __name__ == "__main__":
    main()
