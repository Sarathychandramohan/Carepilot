"""
D:\\CarePilotAI\\backend\\scripts\\seed_reference_ranges.py

Seeds the reference_ranges table with standard clinical normal ranges
for all LOINC codes that appear in Synthea observations.

Also scans the observations CSV and warns on any unmapped codes.

Usage:
    python -m backend.scripts.seed_reference_ranges --db-password YOUR_PASS
    python -m backend.scripts.seed_reference_ranges --db-password YOUR_PASS --scan-csv synthea/carepilot_output_2k/csv/observations.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Reference range definitions
# Format: (loinc_code, description, normal_min, normal_max, unit, gender)
# None for normal_min or normal_max = no bound in that direction
# None for gender = applies to all genders
# ---------------------------------------------------------------------------

REFERENCE_RANGES: list[tuple] = [
    # Kidney function
    ("2160-0",  "Creatinine [Mass/volume] in Serum or Plasma", 0.6,  1.2,  "mg/dL",        None),
    ("33914-3", "Glomerular filtration rate (eGFR)",            60.0, None, "mL/min/1.73m2", None),
    ("14959-1", "Microalbumin [Mass/volume] in Urine",          None, 30.0, "mg/g",          None),
    ("32294-1", "Albumin/Creatinine ratio [Ratio] in Urine",    None, 30.0, "mg/g",          None),
    ("3094-0",  "Urea nitrogen (BUN) [Mass/volume] in Serum",   7.0,  20.0, "mg/dL",         None),

    # Diabetes / glucose
    ("4548-4",  "Hemoglobin A1c/Hemoglobin.total in Blood",     None, 5.7,  "%",             None),
    ("2345-7",  "Glucose [Mass/volume] in Serum or Plasma",     70.0, 99.0, "mg/dL",         None),
    ("88293-6", "Hemoglobin A1c/Hemoglobin.total in Blood",     None, 5.7,  "%",             None),  # alt code

    # Lipids / cholesterol
    ("2093-3",  "Cholesterol [Mass/volume] in Serum or Plasma", None, 200.0, "mg/dL",        None),
    ("2089-1",  "Cholesterol in LDL [Mass/volume] in Serum",    None, 100.0, "mg/dL",        None),
    ("2085-9",  "Cholesterol in HDL [Mass/volume] in Serum",    40.0, None,  "mg/dL",        None),
    ("2571-8",  "Triglycerides [Mass/volume] in Serum",         None, 150.0, "mg/dL",        None),

    # Blood count
    ("718-7",   "Hemoglobin [Mass/volume] in Blood",            12.0, 17.5, "g/dL",          None),
    ("787-2",   "MCV [Entitic volume] by Automated count",      80.0, 100.0, "fL",           None),
    ("6690-2",  "Leukocytes [#/volume] in Blood",               4.5,  11.0, "10*3/uL",       None),
    ("777-3",   "Platelets [#/volume] in Blood",                150.0, 400.0, "10*3/uL",     None),

    # Electrolytes
    ("2947-0",  "Sodium [Moles/volume] in Blood",               136.0, 145.0, "mEq/L",       None),
    ("2823-3",  "Potassium [Moles/volume] in Blood",            3.5,   5.0,   "mEq/L",       None),
    ("2075-0",  "Chloride [Moles/volume] in Blood",             98.0,  106.0, "mEq/L",       None),
    ("1963-8",  "Bicarbonate [Moles/volume] in Blood",          22.0,  29.0,  "mEq/L",       None),

    # Liver function
    ("1742-6",  "Alanine aminotransferase (ALT) [Enzymatic activity/volume]", None, 56.0, "U/L", None),
    ("1920-8",  "Aspartate aminotransferase (AST) [Enzymatic activity/volume]", None, 40.0, "U/L", None),
    ("6768-6",  "Alkaline phosphatase [Enzymatic activity/volume]",  44.0, 147.0, "U/L",     None),

    # Blood pressure (systolic / diastolic)
    ("55284-4", "Blood pressure systolic+diastolic",             None, None, "mmHg",         None),
    ("8480-6",  "Systolic blood pressure",                       None, 120.0, "mmHg",        None),
    ("8462-4",  "Diastolic blood pressure",                      None, 80.0,  "mmHg",        None),

    # Vital signs
    ("8310-5",  "Body temperature",                              36.1, 37.2, "Cel",           None),
    ("8867-4",  "Heart rate",                                    60.0, 100.0, "/min",         None),
    ("9279-1",  "Respiratory rate",                              12.0, 20.0,  "/min",         None),
    ("59408-5", "Oxygen saturation in Arterial blood",           95.0, None,  "%",            None),

    # Body measurements
    ("39156-5", "Body mass index (BMI) [Ratio]",                 None, 25.0, "kg/m2",         None),
]


def get_existing_codes(cur: psycopg.Cursor) -> set[str]:
    cur.execute("SELECT code FROM reference_ranges")
    return {row[0] for row in cur.fetchall()}


def seed_ranges(cur: psycopg.Cursor) -> int:
    existing = get_existing_codes(cur)
    inserted = 0

    for code, desc, lo, hi, unit, gender in REFERENCE_RANGES:
        if code in existing:
            continue
        cur.execute(
            """
            INSERT INTO reference_ranges 
                (code, description, normal_min, normal_max, unit, gender, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (code) DO NOTHING
            """,
            (code, desc, lo, hi, unit, gender, "clinical_standards_2026"),
        )
        inserted += 1

    return inserted


def scan_observations_csv(csv_path: Path) -> dict[str, int]:
    """Return {loinc_code: count} for all observation codes in CSV."""
    code_counts: dict[str, int] = {}
    with open(csv_path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = (row.get("CODE") or "").strip()
            if code:
                code_counts[code] = code_counts.get(code, 0) + 1
    return code_counts


def backfill_abnormal_flags(cur: psycopg.Cursor) -> None:
    """
    Compute is_abnormal and copy ref_min/ref_max into lab_results
    using the seeded reference_ranges table.
    """
    print("\n[backfill] Computing is_abnormal flags on lab_results...")
    cur.execute("""
        UPDATE lab_results lr
        SET
            ref_min = rr.normal_min,
            ref_max = rr.normal_max,
            is_abnormal = CASE
                WHEN lr.numeric_value IS NULL THEN NULL
                WHEN rr.normal_min IS NOT NULL AND lr.numeric_value < rr.normal_min THEN TRUE
                WHEN rr.normal_max IS NOT NULL AND lr.numeric_value > rr.normal_max THEN TRUE
                ELSE FALSE
            END
        FROM reference_ranges rr
        WHERE lr.code = rr.code
          AND lr.numeric_value IS NOT NULL
    """)
    print(f"[backfill] Updated {cur.rowcount} lab_results rows with is_abnormal flags")


def main():
    parser = argparse.ArgumentParser(description="Seed reference ranges into carepilot_db")
    parser.add_argument("--db-host", default="localhost")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-name", default="carepilot_db")
    parser.add_argument("--db-user", default="postgres")
    parser.add_argument("--db-password", required=True)
    parser.add_argument(
        "--scan-csv", type=Path, default=None,
        help="Path to observations.csv to check for unmapped LOINC codes"
    )
    parser.add_argument(
        "--backfill-flags", action="store_true",
        help="After seeding, backfill is_abnormal on lab_results"
    )
    args = parser.parse_args()

    dsn = (
        f"host={args.db_host} port={args.db_port} "
        f"user={args.db_user} password={args.db_password} "
        f"dbname={args.db_name}"
    )

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            print(f"Seeding {len(REFERENCE_RANGES)} reference ranges...")
            n = seed_ranges(cur)
            conn.commit()
            print(f"✓ Inserted {n} new reference ranges")

            # Verify total
            cur.execute("SELECT COUNT(*) FROM reference_ranges")
            total = cur.fetchone()[0]
            print(f"  Total reference_ranges rows: {total}")

            if args.scan_csv and args.scan_csv.exists():
                print(f"\nScanning observations CSV: {args.scan_csv}")
                code_counts = scan_observations_csv(args.scan_csv)
                seeded_codes = get_existing_codes(cur)
                unmapped = {c: n for c, n in code_counts.items() if c not in seeded_codes}
                if unmapped:
                    print(f"\n⚠ WARNING: {len(unmapped)} LOINC codes in observations have NO reference range:")
                    for code, count in sorted(unmapped.items(), key=lambda x: -x[1])[:20]:
                        print(f"  {code:15s} ({count:>6,} obs)")
                    if len(unmapped) > 20:
                        print(f"  ... and {len(unmapped) - 20} more")
                else:
                    print("✓ All LOINC codes in observations CSV are mapped to reference ranges")

            if args.backfill_flags:
                backfill_abnormal_flags(cur)
                conn.commit()
                print("✓ is_abnormal backfill complete")


if __name__ == "__main__":
    main()
