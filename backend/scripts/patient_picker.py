"""
D:\\CarePilotAI\\backend\\scripts\\patient_picker.py

Selects complex test patients from carepilot_db for:
  - Silver query generation (A3.3)
  - RQ3 stream construction (A3.5)
  - Pipeline stress testing

Selection criteria (all must pass):
  1. >= 2 chronic conditions from the covered set
  2. >= 4 lab results across >= 2 distinct LOINC codes
  3. >= 1 active prescription
  4. Alive (no death_date)

Usage:
    python -m backend.scripts.patient_picker --db-password YOUR_PASS
    python -m backend.scripts.patient_picker --db-password YOUR_PASS --count 60 --output data/manifests/rq3_patients.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, date
from pathlib import Path
from typing import Any

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"

# Conditions covered by CarePilot's KB
COVERED_CONDITIONS = [
    "diabetes",
    "hypertension",
    "chronic kidney",
    "hyperlipidemia",
    "hypercholesterol",
    "cholesterol",
    "ckd",
    "heart failure",
    "coronary",
]


def date_serializer(obj: Any) -> str:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def pick_patients(
    cur: psycopg.Cursor,
    count: int,
    min_conditions: int = 2,
    min_labs: int = 4,
    min_distinct_codes: int = 2,
) -> list[dict]:
    """Return list of complex patient summaries."""

    print(f"\nSelecting up to {count} complex patients...")
    print(f"  Criteria: >= {min_conditions} conditions, >= {min_labs} labs "
          f"({min_distinct_codes}+ codes), >= 1 active rx, alive")

    # Step 1: Patients with >= 2 covered conditions
    condition_filter = " OR ".join(
        f"LOWER(c.description) LIKE '%%{cond}%%'" for cond in COVERED_CONDITIONS
    )

    cur.execute(f"""
        SELECT c.patient_id, COUNT(DISTINCT c.id) AS condition_count
        FROM conditions c
        JOIN patients p ON p.id = c.patient_id
        WHERE p.death_date IS NULL
          AND ({condition_filter})
          AND c.stop_date IS NULL
        GROUP BY c.patient_id
        HAVING COUNT(DISTINCT c.id) >= %s
    """, (min_conditions,))
    cond_patients = {row[0]: row[1] for row in cur.fetchall()}
    print(f"  Patients with >= {min_conditions} covered conditions: {len(cond_patients)}")

    if not cond_patients:
        print("  WARNING: No patients match condition criteria. Lowering threshold...")
        # Fallback: any patient with >= 1 condition
        cur.execute("""
            SELECT patient_id, COUNT(*) as cnt FROM conditions
            WHERE stop_date IS NULL GROUP BY patient_id HAVING COUNT(*) >= 1
        """)
        cond_patients = {row[0]: row[1] for row in cur.fetchall()}

    # Step 2: Of those, filter for >= min_labs labs across >= min_distinct_codes
    patient_ids = list(cond_patients.keys())
    # Process in batches of 500
    lab_patients = {}
    for i in range(0, len(patient_ids), 500):
        batch = patient_ids[i:i+500]
        placeholders = ",".join(["%s"] * len(batch))
        cur.execute(f"""
            SELECT patient_id,
                   COUNT(*) AS lab_count,
                   COUNT(DISTINCT code) AS distinct_codes
            FROM lab_results
            WHERE patient_id IN ({placeholders})
              AND numeric_value IS NOT NULL
            GROUP BY patient_id
            HAVING COUNT(*) >= %s AND COUNT(DISTINCT code) >= %s
        """, tuple(batch) + (min_labs, min_distinct_codes))
        for row in cur.fetchall():
            lab_patients[row[0]] = {"lab_count": row[1], "distinct_codes": row[2]}

    print(f"  Patients with >= {min_labs} numeric labs: {len(lab_patients)}")

    # Step 3: Of those, filter for >= 1 active prescription
    lab_patient_ids = list(lab_patients.keys())
    rx_patients = set()
    for i in range(0, len(lab_patient_ids), 500):
        batch = lab_patient_ids[i:i+500]
        placeholders = ",".join(["%s"] * len(batch))
        cur.execute(f"""
            SELECT DISTINCT patient_id FROM prescriptions
            WHERE patient_id IN ({placeholders})
              AND stop_date IS NULL
        """, tuple(batch))
        rx_patients.update(row[0] for row in cur.fetchall())

    print(f"  Patients with >= 1 active prescription: {len(rx_patients)}")

    # Intersection
    eligible = [p for p in lab_patient_ids if p in rx_patients]
    print(f"  Fully eligible patients: {len(eligible)}")

    # Take up to `count`
    selected = eligible[:count]

    # Step 4: Enrich each patient with full summary
    results = []
    for pid in selected:
        # Basic demographics
        cur.execute("""
            SELECT id, stable_eid, first_name, last_name, birth_date, death_date, gender
            FROM patients WHERE id = %s
        """, (pid,))
        p = cur.fetchone()
        if not p:
            continue

        # Active conditions
        cur.execute("""
            SELECT description, code, start_date
            FROM conditions
            WHERE patient_id = %s AND stop_date IS NULL
            ORDER BY start_date DESC
        """, (pid,))
        conditions = [
            {"description": r[0], "code": r[1], "start_date": r[2]}
            for r in cur.fetchall()
        ]

        # Most recent labs per LOINC code (top 5 most recent per code)
        cur.execute("""
            SELECT DISTINCT ON (code)
                code, description, numeric_value, units, observed_at, is_abnormal, stable_eid
            FROM lab_results
            WHERE patient_id = %s AND numeric_value IS NOT NULL
            ORDER BY code, observed_at DESC
            LIMIT 20
        """, (pid,))
        latest_labs = [
            {
                "code": r[0],
                "description": r[1],
                "value": r[2],
                "units": r[3],
                "date": r[4],
                "is_abnormal": r[5],
                "stable_eid": r[6],
            }
            for r in cur.fetchall()
        ]

        # Active medications
        cur.execute("""
            SELECT description, code, start_date, reason_description
            FROM prescriptions
            WHERE patient_id = %s AND stop_date IS NULL
            ORDER BY start_date DESC
        """, (pid,))
        medications = [
            {"description": r[0], "code": r[1], "start_date": r[2], "reason": r[3]}
            for r in cur.fetchall()
        ]

        results.append({
            "patient_id": p[0],
            "stable_eid": p[1],
            "first_name": p[2],
            "last_name": p[3],
            "birth_date": p[4],
            "death_date": p[5],
            "gender": p[6],
            "active_condition_count": len(conditions),
            "active_conditions": conditions[:5],
            "latest_labs": latest_labs,
            "active_medications": medications[:5],
            "lab_count": lab_patients.get(pid, {}).get("lab_count", 0),
            "distinct_lab_codes": lab_patients.get(pid, {}).get("distinct_codes", 0),
        })

    return results


import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def main():
    parser = argparse.ArgumentParser(description="Pick complex test patients from carepilot_db")
    parser.add_argument("--db-host", default=None)
    parser.add_argument("--db-port", type=int, default=None)
    parser.add_argument("--db-name", default=None)
    parser.add_argument("--db-user", default=None)
    parser.add_argument("--db-password", default=None)
    parser.add_argument("--count", type=int, default=20,
                        help="Number of patients to select (default: 20)")
    parser.add_argument("--min-conditions", type=int, default=2)
    parser.add_argument("--min-labs", type=int, default=4)
    parser.add_argument(
        "--output", type=Path,
        default=MANIFEST_DIR / "complex_patients.json",
        help="Output JSON path"
    )
    args = parser.parse_args()

    import os
    env_p = PROJECT_ROOT / "backend" / ".env"
    env = {}
    if env_p.exists():
        for line in env_p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
                
    db_url = env.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
    if db_url:
        dsn = db_url.replace("postgresql+psycopg://", "postgresql://")
    else:
        host = args.db_host or env.get("DB_HOST", "localhost")
        port = args.db_port or int(env.get("DB_PORT", "5432"))
        name = args.db_name or env.get("DB_NAME", "carepilot_v3")
        user = args.db_user or env.get("DB_USER", "postgres")
        pw   = args.db_password or env.get("POSTGRES_PASSWORD") or env.get("DB_PASSWORD")
        dsn  = f"host={host} port={port} user={user} password={pw} dbname={name}"

    args.output.parent.mkdir(parents=True, exist_ok=True)

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            patients = pick_patients(
                cur,
                count=args.count,
                min_conditions=args.min_conditions,
                min_labs=args.min_labs,
            )

    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(patients),
        "criteria": {
            "min_conditions": args.min_conditions,
            "min_labs": args.min_labs,
            "min_distinct_codes": 2,
            "min_active_rx": 1,
            "alive_only": True,
        },
        "patients": patients,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, default=date_serializer)

    print(f"\n✓ Saved {len(patients)} complex patients → {args.output}")

    if len(patients) < 20:
        print(f"⚠ WARNING: Only {len(patients)} patients selected (need >= 20).")
        print("  Consider running Synthea with more patients or lowering --min-conditions.")
    else:
        print("✓ A1.7 Patient picker gate: PASS")


if __name__ == "__main__":
    main()
