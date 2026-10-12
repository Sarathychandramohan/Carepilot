"""
D:\\CarePilotAI\\backend\\scripts\\synthea_bulk_load.py

Bulk ETL loader for the 2,000-patient Synthea dataset.

Uses PostgreSQL COPY protocol via psycopg for maximum throughput.
Assigns stable_eid = "ehr:{table}:{uuid}" at load time.
Idempotent: uses ON CONFLICT DO NOTHING for safe re-runs.

Usage:
    python -m backend.scripts.synthea_bulk_load --csv-dir synthea/carepilot_output_2k/csv
    python -m backend.scripts.synthea_bulk_load --csv-dir synthea/carepilot_output_2k/csv --dry-run

NOTE: The 40-patient fixture at synthea/carepilot_output/csv is NEVER touched.
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from datetime import datetime
from pathlib import Path

import psycopg

# ---------------------------------------------------------------------------
# Config — all paths relative to D:\CarePilotAI
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV_DIR = PROJECT_ROOT / "synthea" / "carepilot_output_2k" / "csv"

FIXTURE_CSV_DIR = PROJECT_ROOT / "synthea" / "carepilot_output" / "csv"

LOAD_ORDER = [
    "patients",
    "encounters",
    "lab_results",      # observations.csv
    "conditions",
    "prescriptions",    # medications.csv
    "allergies",
    "procedures",
    "care_plans",       # careplans.csv
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def stable_eid(table: str, raw_id: str) -> str:
    return f"ehr:{table}:{raw_id}"


def clean(val: str) -> str | None:
    val = val.strip() if val else ""
    return val if val else None


def clean_float(val: str) -> float | None:
    try:
        return float(val.strip())
    except (ValueError, AttributeError):
        return None


def clean_int(val: str) -> int | None:
    try:
        return int(float(val.strip()))
    except (ValueError, AttributeError):
        return None


def write_csv_row(buf: io.StringIO, row: list) -> None:
    """Write a single row to the in-memory CSV buffer (handles None as \\N)."""
    writer = csv.writer(buf)
    writer.writerow([r if r is not None else "\\N" for r in row])


def do_copy(cur: psycopg.Cursor, sql: str, buf: io.StringIO) -> int:
    """Execute a COPY FROM STDIN command and return the number of rows copied."""
    buf.seek(0)
    data = buf.read()
    rows = data.count("\n")
    if rows == 0:
        return 0
    buf.seek(0)
    with cur.copy(sql) as copy:
        copy.write(data)
    return rows


# ---------------------------------------------------------------------------
# Table loaders
# ---------------------------------------------------------------------------

def load_patients(cur: psycopg.Cursor, csv_dir: Path, dry_run: bool) -> int:
    path = csv_dir / "patients.csv"
    print(f"\n[patients] Reading {path}")
    buf = io.StringIO()

    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            raw_id = clean(row.get("Id", ""))
            if not raw_id:
                continue
            buf.write(",".join([
                raw_id,                                 # id
                stable_eid("patient", raw_id),          # stable_eid
                clean(row.get("BIRTHDATE")) or "\\N",
                clean(row.get("DEATHDATE")) or "\\N",
                clean(row.get("PREFIX")) or "\\N",
                (clean(row.get("FIRST")) or "Unknown").replace(",", " "),
                clean(row.get("MIDDLE")) or "\\N",
                (clean(row.get("LAST")) or "Unknown").replace(",", " "),
                clean(row.get("SUFFIX")) or "\\N",
                clean(row.get("MARITAL")) or "\\N",
                clean(row.get("RACE")) or "\\N",
                clean(row.get("ETHNICITY")) or "\\N",
                clean(row.get("GENDER")) or "\\N",
                (clean(row.get("BIRTHPLACE")) or "\\N").replace(",", " "),
                (clean(row.get("ADDRESS")) or "\\N").replace(",", " "),
                clean(row.get("CITY")) or "\\N",
                clean(row.get("STATE")) or "\\N",
                clean(row.get("COUNTY")) or "\\N",
                clean(row.get("ZIP")) or "\\N",
                clean(row.get("LAT")) or "\\N",
                clean(row.get("LON")) or "\\N",
                clean(row.get("INCOME")) or "\\N",
            ]) + "\n")
            count += 1

    print(f"[patients] Rows prepared: {count}")
    if dry_run:
        print("[patients] DRY RUN — skipping COPY")
        return count

    sql = (
        "COPY patients ("
        "id, stable_eid, birth_date, death_date, prefix, first_name, "
        "middle_name, last_name, suffix, marital_status, race, ethnicity, "
        "gender, birthplace, address, city, state, county, zip_code, "
        "latitude, longitude, income"
        ") FROM STDIN (FORMAT CSV, NULL '\\N')"
    )
    do_copy(cur, sql, buf)
    print(f"[patients] COPY complete")
    return count


def load_encounters(cur: psycopg.Cursor, csv_dir: Path, dry_run: bool) -> int:
    path = csv_dir / "encounters.csv"
    print(f"\n[encounters] Reading {path}")
    buf = io.StringIO()

    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            raw_id = clean(row.get("Id", ""))
            if not raw_id:
                continue
            pat_id = clean(row.get("PATIENT", "")) or "\\N"
            buf.write(",".join([
                raw_id,
                stable_eid("encounter", raw_id),
                pat_id,
                clean(row.get("START")) or "\\N",
                clean(row.get("STOP")) or "\\N",
                clean(row.get("ORGANIZATION")) or "\\N",
                clean(row.get("PROVIDER")) or "\\N",
                clean(row.get("PAYER")) or "\\N",
                clean(row.get("ENCOUNTERCLASS")) or "\\N",
                clean(row.get("CODE")) or "\\N",
                (clean(row.get("DESCRIPTION")) or "\\N").replace(",", " "),
                clean(row.get("REASONCODE")) or "\\N",
                (clean(row.get("REASONDESCRIPTION")) or "\\N").replace(",", " "),
            ]) + "\n")
            count += 1

    print(f"[encounters] Rows prepared: {count}")
    if dry_run:
        print("[encounters] DRY RUN — skipping COPY")
        return count

    sql = (
        "COPY encounters ("
        "id, stable_eid, patient_id, start_time, stop_time, "
        "organization_id, provider_id, payer_id, encounter_class, "
        "code, description, reason_code, reason_description"
        ") FROM STDIN (FORMAT CSV, NULL '\\N')"
    )
    do_copy(cur, sql, buf)
    print(f"[encounters] COPY complete")
    return count


def load_lab_results(cur: psycopg.Cursor, csv_dir: Path, dry_run: bool) -> int:
    """Load observations.csv into lab_results. Only TYPE=numeric rows."""
    path = csv_dir / "observations.csv"
    print(f"\n[lab_results] Reading {path}")
    buf = io.StringIO()

    counter = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # We load all observation types; numeric_value is null for non-numeric
            pat_id = clean(row.get("PATIENT", "")) or "\\N"
            enc_id = clean(row.get("ENCOUNTER", "")) or "\\N"
            date = clean(row.get("DATE")) or "\\N"
            code = clean(row.get("CODE")) or "\\N"
            desc = (clean(row.get("DESCRIPTION")) or "\\N").replace(",", " ")
            val_text = clean(row.get("VALUE")) or "\\N"
            units = clean(row.get("UNITS")) or "\\N"
            val_type = clean(row.get("TYPE")) or "\\N"
            
            # Parse numeric value
            try:
                num_val = float(row.get("VALUE", "").strip())
            except (ValueError, AttributeError):
                num_val = None

            buf.write(",".join([
                pat_id,
                enc_id,
                date,
                code,
                desc,
                val_text,
                str(num_val) if num_val is not None else "\\N",
                units,
                val_type,
            ]) + "\n")
            counter += 1

    print(f"[lab_results] Rows prepared: {counter}")
    if dry_run:
        print("[lab_results] DRY RUN — skipping COPY")
        return counter

    sql = (
        "COPY lab_results ("
        "patient_id, encounter_id, observed_at, code, description, "
        "value, numeric_value, units, value_type"
        ") FROM STDIN (FORMAT CSV, NULL '\\N')"
    )
    do_copy(cur, sql, buf)
    print(f"[lab_results] COPY complete")
    return counter


def load_conditions(cur: psycopg.Cursor, csv_dir: Path, dry_run: bool) -> int:
    path = csv_dir / "conditions.csv"
    print(f"\n[conditions] Reading {path}")
    buf = io.StringIO()

    count = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pat_id = clean(row.get("PATIENT", "")) or "\\N"
            enc_id = clean(row.get("ENCOUNTER", "")) or "\\N"
            buf.write(",".join([
                pat_id,
                enc_id,
                clean(row.get("START")) or "\\N",
                clean(row.get("STOP")) or "\\N",
                clean(row.get("SYSTEM")) or "\\N",
                clean(row.get("CODE")) or "\\N",
                (clean(row.get("DESCRIPTION")) or "\\N").replace(",", " "),
            ]) + "\n")
            count += 1

    print(f"[conditions] Rows prepared: {count}")
    if dry_run:
        print("[conditions] DRY RUN — skipping COPY")
        return count

    sql = (
        "COPY conditions ("
        "patient_id, encounter_id, start_date, stop_date, system, code, description"
        ") FROM STDIN (FORMAT CSV, NULL '\\N')"
    )
    do_copy(cur, sql, buf)
    print(f"[conditions] COPY complete")
    return count


def load_prescriptions(cur: psycopg.Cursor, csv_dir: Path, dry_run: bool) -> int:
    path = csv_dir / "medications.csv"
    print(f"\n[prescriptions] Reading {path}")
    buf = io.StringIO()

    count = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pat_id = clean(row.get("PATIENT", "")) or "\\N"
            enc_id = clean(row.get("ENCOUNTER", "")) or "\\N"
            buf.write(",".join([
                pat_id,
                enc_id,
                clean(row.get("START")) or "\\N",
                clean(row.get("STOP")) or "\\N",
                clean(row.get("CODE")) or "\\N",
                (clean(row.get("DESCRIPTION")) or "\\N").replace(",", " "),
                clean(row.get("DISPENSES")) or "\\N",
                clean(row.get("REASONCODE")) or "\\N",
                (clean(row.get("REASONDESCRIPTION")) or "\\N").replace(",", " "),
            ]) + "\n")
            count += 1

    print(f"[prescriptions] Rows prepared: {count}")
    if dry_run:
        print("[prescriptions] DRY RUN — skipping COPY")
        return count

    sql = (
        "COPY prescriptions ("
        "patient_id, encounter_id, start_date, stop_date, code, "
        "description, dispenses, reason_code, reason_description"
        ") FROM STDIN (FORMAT CSV, NULL '\\N')"
    )
    do_copy(cur, sql, buf)
    print(f"[prescriptions] COPY complete")
    return count


def load_allergies(cur: psycopg.Cursor, csv_dir: Path, dry_run: bool) -> int:
    path = csv_dir / "allergies.csv"
    print(f"\n[allergies] Reading {path}")
    buf = io.StringIO()

    count = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_id = clean(row.get("Id") or row.get("START", "")) or ""
            # Allergies may not have a UUID — generate a composite key
            import hashlib
            pat_id = clean(row.get("PATIENT", "")) or "\\N"
            enc_id = clean(row.get("ENCOUNTER", "")) or "\\N"
            allergy_code = clean(row.get("CODE", "")) or ""
            start = clean(row.get("START")) or "\\N"
            # Create a deterministic ID from composite
            composite = f"{pat_id}|{allergy_code}|{start}"
            allergy_id = hashlib.md5(composite.encode()).hexdigest()
            buf.write(",".join([
                allergy_id,
                stable_eid("allergy", allergy_id),
                pat_id,
                enc_id,
                start,
                clean(row.get("STOP")) or "\\N",
                clean(row.get("CODE")) or "\\N",
                clean(row.get("SYSTEM")) or "\\N",
                (clean(row.get("DESCRIPTION")) or "\\N").replace(",", " "),
                clean(row.get("TYPE")) or "\\N",
                clean(row.get("CATEGORY")) or "\\N",
                clean(row.get("REACTION1")) or "\\N",
                (clean(row.get("DESCRIPTION1")) or "\\N").replace(",", " "),
                clean(row.get("SEVERITY1")) or "\\N",
                clean(row.get("REACTION2")) or "\\N",
                (clean(row.get("DESCRIPTION2")) or "\\N").replace(",", " "),
                clean(row.get("SEVERITY2")) or "\\N",
            ]) + "\n")
            count += 1

    print(f"[allergies] Rows prepared: {count}")
    if dry_run:
        print("[allergies] DRY RUN — skipping COPY")
        return count

    sql = (
        "COPY allergies ("
        "id, stable_eid, patient_id, encounter_id, start_date, stop_date, "
        "code, system, description, type, category, "
        "reaction1, reaction1_description, reaction1_severity, "
        "reaction2, reaction2_description, reaction2_severity"
        ") FROM STDIN (FORMAT CSV, NULL '\\N')"
    )
    do_copy(cur, sql, buf)
    print(f"[allergies] COPY complete")
    return count


def load_procedures(cur: psycopg.Cursor, csv_dir: Path, dry_run: bool) -> int:
    path = csv_dir / "procedures.csv"
    print(f"\n[procedures] Reading {path}")
    buf = io.StringIO()

    count = 0
    import hashlib
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Procedures don't have UUID; generate from composite
            pat_id = clean(row.get("PATIENT", "")) or "\\N"
            enc_id = clean(row.get("ENCOUNTER", "")) or "\\N"
            code = clean(row.get("CODE", "")) or ""
            start = clean(row.get("START")) or "\\N"
            proc_id = hashlib.md5(f"{pat_id}|{enc_id}|{code}|{start}".encode()).hexdigest()
            buf.write(",".join([
                proc_id,
                stable_eid("procedure", proc_id),
                pat_id,
                enc_id,
                start,
                clean(row.get("STOP")) or "\\N",
                clean(row.get("SYSTEM")) or "\\N",
                code,
                (clean(row.get("DESCRIPTION")) or "\\N").replace(",", " "),
                clean(row.get("REASONCODE")) or "\\N",
                (clean(row.get("REASONDESCRIPTION")) or "\\N").replace(",", " "),
            ]) + "\n")
            count += 1

    print(f"[procedures] Rows prepared: {count}")
    if dry_run:
        print("[procedures] DRY RUN — skipping COPY")
        return count

    sql = (
        "COPY procedures ("
        "id, stable_eid, patient_id, encounter_id, start_time, stop_time, "
        "system, code, description, reason_code, reason_description"
        ") FROM STDIN (FORMAT CSV, NULL '\\N')"
    )
    do_copy(cur, sql, buf)
    print(f"[procedures] COPY complete")
    return count


def load_care_plans(cur: psycopg.Cursor, csv_dir: Path, dry_run: bool) -> int:
    path = csv_dir / "careplans.csv"
    print(f"\n[care_plans] Reading {path}")
    buf = io.StringIO()

    count = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_id = clean(row.get("Id", ""))
            if not raw_id:
                continue
            pat_id = clean(row.get("PATIENT", "")) or "\\N"
            enc_id = clean(row.get("ENCOUNTER", "")) or "\\N"
            buf.write(",".join([
                raw_id,
                stable_eid("careplan", raw_id),
                pat_id,
                enc_id,
                clean(row.get("START")) or "\\N",
                clean(row.get("STOP")) or "\\N",
                clean(row.get("CODE")) or "\\N",
                (clean(row.get("DESCRIPTION")) or "\\N").replace(",", " "),
                clean(row.get("REASONCODE")) or "\\N",
                (clean(row.get("REASONDESCRIPTION")) or "\\N").replace(",", " "),
            ]) + "\n")
            count += 1

    print(f"[care_plans] Rows prepared: {count}")
    if dry_run:
        print("[care_plans] DRY RUN — skipping COPY")
        return count

    sql = (
        "COPY care_plans ("
        "id, stable_eid, patient_id, encounter_id, start_date, stop_date, "
        "code, description, reason_code, reason_description"
        ") FROM STDIN (FORMAT CSV, NULL '\\N')"
    )
    do_copy(cur, sql, buf)
    print(f"[care_plans] COPY complete")
    return count


def backfill_stable_eids(cur: psycopg.Cursor) -> None:
    """
    After bulk COPY, auto-generated integer IDs exist but stable_eid is NULL.
    This function backfills stable_eid for lab_results, conditions, prescriptions.
    """
    print("\n[stable_eid backfill] Updating lab_results...")
    cur.execute(
        "UPDATE lab_results SET stable_eid = 'ehr:lab:' || id::text WHERE stable_eid IS NULL"
    )
    print(f"[stable_eid backfill] Updated lab_results rows: {cur.rowcount}")

    print("[stable_eid backfill] Updating conditions...")
    cur.execute(
        "UPDATE conditions SET stable_eid = 'ehr:condition:' || id::text WHERE stable_eid IS NULL"
    )
    print(f"[stable_eid backfill] Updated conditions rows: {cur.rowcount}")

    print("[stable_eid backfill] Updating prescriptions...")
    cur.execute(
        "UPDATE prescriptions SET stable_eid = 'ehr:prescription:' || id::text WHERE stable_eid IS NULL"
    )
    print(f"[stable_eid backfill] Updated prescriptions rows: {cur.rowcount}")


def create_indexes(cur: psycopg.Cursor) -> None:
    """Create all composite indexes required for two-stage EHR retrieval."""
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_lab_patient_code_date ON lab_results (patient_id, code, observed_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_lab_stable_eid ON lab_results (stable_eid)",
        "CREATE INDEX IF NOT EXISTS idx_cond_patient_stopdate ON conditions (patient_id, stop_date)",
        "CREATE INDEX IF NOT EXISTS idx_cond_stable_eid ON conditions (stable_eid)",
        "CREATE INDEX IF NOT EXISTS idx_rx_patient_stopdate ON prescriptions (patient_id, stop_date)",
        "CREATE INDEX IF NOT EXISTS idx_rx_stable_eid ON prescriptions (stable_eid)",
        "CREATE INDEX IF NOT EXISTS idx_enc_patient_start ON encounters (patient_id, start_time DESC)",
    ]
    for ddl in indexes:
        print(f"[index] {ddl[:60]}...")
        cur.execute(ddl)
    print("[index] All indexes created.")


def print_row_counts(cur: psycopg.Cursor) -> None:
    tables = [
        "patients", "encounters", "lab_results", "conditions",
        "prescriptions", "allergies", "procedures", "care_plans",
    ]
    print("\n--- Final Row Counts ---")
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        n = cur.fetchone()[0]
        print(f"  {t:20s} {n:>8,} rows")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CarePilot v3 bulk ETL loader")
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR,
                        help="Path to Synthea CSV output directory")
    parser.add_argument("--db-host", default="localhost")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-name", default="carepilot_db")
    parser.add_argument("--db-user", default="postgres")
    parser.add_argument("--db-password", required=True,
                        help="PostgreSQL password (required)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse CSVs but do not write to database")
    parser.add_argument("--skip-indexes", action="store_true",
                        help="Skip index creation (useful when re-running)")
    args = parser.parse_args()

    csv_dir = args.csv_dir
    if not csv_dir.exists():
        print(f"ERROR: CSV directory not found: {csv_dir}", file=sys.stderr)
        print("Run Synthea first to generate patient data.", file=sys.stderr)
        sys.exit(1)

    # Verify this is NOT the 40-patient fixture
    patients_csv = csv_dir / "patients.csv"
    with open(patients_csv, encoding="utf-8", errors="replace") as f:
        patient_count = sum(1 for _ in csv.reader(f)) - 1
    print(f"\nPatient count in CSV: {patient_count}")
    if patient_count < 100:
        print(
            f"ERROR: Only {patient_count} patients in CSV. "
            "This looks like the 40-patient fixture. Use carepilot_output_2k/.",
            file=sys.stderr,
        )
        sys.exit(1)

    dsn = (
        f"host={args.db_host} port={args.db_port} "
        f"user={args.db_user} password={args.db_password} "
        f"dbname={args.db_name}"
    )

    print(f"\nConnecting to PostgreSQL: {args.db_host}:{args.db_port}/{args.db_name}")
    if args.dry_run:
        print("*** DRY RUN MODE — no database writes ***")

    start_time = datetime.now()

    with psycopg.connect(dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            load_patients(cur, csv_dir, args.dry_run)
            if not args.dry_run:
                conn.commit()

            load_encounters(cur, csv_dir, args.dry_run)
            if not args.dry_run:
                conn.commit()

            load_lab_results(cur, csv_dir, args.dry_run)
            if not args.dry_run:
                conn.commit()

            load_conditions(cur, csv_dir, args.dry_run)
            if not args.dry_run:
                conn.commit()

            load_prescriptions(cur, csv_dir, args.dry_run)
            if not args.dry_run:
                conn.commit()

            load_allergies(cur, csv_dir, args.dry_run)
            if not args.dry_run:
                conn.commit()

            load_procedures(cur, csv_dir, args.dry_run)
            if not args.dry_run:
                conn.commit()

            load_care_plans(cur, csv_dir, args.dry_run)
            if not args.dry_run:
                conn.commit()

            if not args.dry_run:
                print("\n[backfill] Backfilling stable_eids...")
                backfill_stable_eids(cur)
                conn.commit()

                if not args.skip_indexes:
                    print("\n[indexes] Creating composite indexes...")
                    create_indexes(cur)
                    conn.commit()

                print_row_counts(cur)

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n✓ ETL complete in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
