"""
Step 6: Post-load checks for CarePilot v3 EHR.
Performs:
1. Row counts vs expected
2. Orphan FK check per table
3. NULL stable_eid count
4. Patients by source_run and alive/deceased
5. For each of the 40 demo patients: row counts per table in the database
"""
import os
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = PROJECT_ROOT / "data" / "manifests"
ENV_PATH = PROJECT_ROOT / "backend" / ".env"

if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import psycopg

db_url = os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
if not db_url:
    print("ERROR: DATABASE_URL not set.")
    sys.exit(1)

with psycopg.connect(db_url) as conn:
    with conn.cursor() as cur:
        print("=" * 80)
        print("STEP 6.1: ROW COUNTS VS EXPECTED (from ehr_source_manifest.json)")
        print("=" * 80)
        
        manifest_p = MANIFESTS / "ehr_source_manifest.json"
        manifest_data = {}
        if manifest_p.exists():
            manifest_data = json.loads(manifest_p.read_text(encoding="utf-8")).get("expected_rows_after_merge", {})
            
        tables_to_check = [
            ("patients",       "patients.csv"),
            ("encounters",     "encounters.csv"),
            ("lab_results",    "observations.csv"),
            ("conditions",     "conditions.csv"),
            ("prescriptions",  "medications.csv"),
            ("allergies",      "allergies.csv"),
            ("procedures",     "procedures.csv"),
            ("care_plans",     "careplans.csv"),
            ("immunizations",  "immunizations.csv"),
        ]
        
        print(f"{'DB Table':20s} {'Actual Rows':>14s} {'Expected Rows':>16s} {'Match':>8s}")
        print("-" * 62)
        all_match = True
        for tbl, csv_name in tables_to_check:
            cur.execute(f"SELECT count(*) FROM {tbl}")
            act = cur.fetchone()[0]
            exp = manifest_data.get(csv_name, {}).get("expected_rows_after_merge", -1)
            ok = (act == exp)
            if not ok:
                all_match = False
            print(f"{tbl:20s} {act:>14,d} {exp:>16,d} {'OK' if ok else 'FAIL':>8s}")
        print(f"All table row counts match expected: {all_match}\n")
        
        print("=" * 80)
        print("STEP 6.2: ORPHAN FOREIGN KEY CHECKS")
        print("=" * 80)
        fk_checks = [
            ("encounters",    "patient_id", "patients", "id"),
            ("lab_results",   "patient_id", "patients", "id"),
            ("conditions",    "patient_id", "patients", "id"),
            ("prescriptions", "patient_id", "patients", "id"),
            ("allergies",     "patient_id", "patients", "id"),
            ("procedures",    "patient_id", "patients", "id"),
            ("care_plans",    "patient_id", "patients", "id"),
            ("immunizations", "patient_id", "patients", "id"),
        ]
        
        for child_tbl, child_fk, parent_tbl, parent_pk in fk_checks:
            query = f"""
                SELECT count(*) 
                FROM {child_tbl} c 
                LEFT JOIN {parent_tbl} p ON c.{child_fk} = p.{parent_pk} 
                WHERE p.{parent_pk} IS NULL AND c.{child_fk} IS NOT NULL
            """
            cur.execute(query)
            orphans = cur.fetchone()[0]
            print(f"Orphan FKs in {child_tbl}.{child_fk} -> {parent_tbl}.{parent_pk}: {orphans} {'(OK)' if orphans == 0 else '(FAIL)'}")
            
        print("\n" + "=" * 80)
        print("STEP 6.3: NULL STABLE_EID CHECK")
        print("=" * 80)
        for tbl, _ in tables_to_check:
            cur.execute(f"SELECT count(*) FROM {tbl} WHERE stable_eid IS NULL")
            null_count = cur.fetchone()[0]
            print(f"NULL stable_eid in {tbl:20s}: {null_count:>6d} {'(OK)' if null_count == 0 else '(FAIL)'}")
            
        print("\n" + "=" * 80)
        print("STEP 6.4: PATIENTS BY SOURCE_RUN AND ALIVE/DECEASED")
        print("=" * 80)
        cur.execute("""
            SELECT 
                source_run,
                is_demo_fixture,
                is_alive,
                count(*)
            FROM patients
            GROUP BY source_run, is_demo_fixture, is_alive
            ORDER BY source_run, is_demo_fixture, is_alive
        """)
        print(f"{'Source Run':12s} {'is_demo_fixture':18s} {'is_alive':10s} {'Count':>8s}")
        print("-" * 52)
        for s_run, is_demo, is_alive, cnt in cur.fetchall():
            print(f"{str(s_run):12s} {str(is_demo):18s} {str(is_alive):10s} {cnt:>8,d}")
            
        cur.execute("SELECT count(*) FROM patients WHERE is_demo_fixture = TRUE")
        demo_fixtures_total = cur.fetchone()[0]
        print(f"\nTotal demo fixture patients (is_demo_fixture=TRUE): {demo_fixtures_total} (expected 40)")
        
        print("\n" + "=" * 80)
        print("STEP 6.5: ROW COUNTS PER TABLE FOR EACH OF THE 40 DEMO PATIENTS")
        print("=" * 80)
        cur.execute("""
            SELECT id, first_name, last_name, source_run, is_alive 
            FROM patients 
            WHERE is_demo_fixture = TRUE 
            ORDER BY last_name, first_name
        """)
        demo_patients = cur.fetchall()
        print(f"{'Patient ID':38s} {'Name':24s} {'Run':8s} {'Alive':6s} {'Enc':>5s} {'Lab':>6s} {'Cond':>5s} {'Rx':>5s} {'Allg':>5s} {'Proc':>5s} {'Care':>5s} {'Imm':>5s}")
        print("-" * 120)
        
        for pid, first, last, srun, alive in demo_patients:
            name = f"{first} {last}"[:23]
            counts = {}
            for tbl, col in [
                ("encounters", "patient_id"),
                ("lab_results", "patient_id"),
                ("conditions", "patient_id"),
                ("prescriptions", "patient_id"),
                ("allergies", "patient_id"),
                ("procedures", "patient_id"),
                ("care_plans", "patient_id"),
                ("immunizations", "patient_id"),
            ]:
                cur.execute(f"SELECT count(*) FROM {tbl} WHERE {col} = %s", (pid,))
                counts[tbl] = cur.fetchone()[0]
                
            print(f"{pid:38s} {name:24s} {str(srun):8s} {str(alive):6s} "
                  f"{counts['encounters']:>5d} {counts['lab_results']:>6d} {counts['conditions']:>5d} "
                  f"{counts['prescriptions']:>5d} {counts['allergies']:>5d} {counts['procedures']:>5d} "
                  f"{counts['care_plans']:>5d} {counts['immunizations']:>5d}")

print("\nPost-load checks complete.")
