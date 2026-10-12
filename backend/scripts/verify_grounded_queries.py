"""
D:\\CarePilotAI\\backend\\scripts\\verify_grounded_queries.py

Picks 10 random patient-specific queries from silver.jsonl and rq3_stream.jsonl,
queries carepilot_v3 directly, and prints the queries alongside the exact matching EHR rows.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SILVER_PATH = PROJECT_ROOT / "data" / "queries" / "silver.jsonl"
RQ3_PATH = PROJECT_ROOT / "data" / "queries" / "rq3_stream.jsonl"

def main():
    env_p = PROJECT_ROOT / "backend" / ".env"
    env = {}
    for line in env_p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    dsn = env["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")

    # Combine grounded EHR queries from both silver and rq3
    silver_ehr = [
        json.loads(line) for line in open(SILVER_PATH, encoding="utf-8")
        if json.loads(line).get("requires_patient_context") and json.loads(line).get("patient_id")
    ]
    rq3_ehr = [
        json.loads(line) for line in open(RQ3_PATH, encoding="utf-8")
        if json.loads(line).get("requires_patient_context") and json.loads(line).get("patient_id")
    ]

    all_ehr_queries = silver_ehr + rq3_ehr
    random.seed(999)
    sample = random.sample(all_ehr_queries, 10)

    print("=" * 80)
    print("CarePilot AI — Verifying 10 Random Patient-Grounded Queries against carepilot_v3")
    print("=" * 80)

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for idx, q in enumerate(sample, 1):
                pid = q["patient_id"]
                qtext = q["query_text"]
                concept = q["grounded_ehr_concept"]
                ctype = concept.get("grounded_concept_type") or concept.get("concept_type")
                code = concept.get("code")

                print(f"[{idx}/10] Query ID: {q['query_id']} | Tier: {q.get('tier', 'silver')}")
                print(f"  Text: \"{qtext}\"")
                print(f"  Patient ID: {pid}")
                print(f"  Expected Concept: {ctype} (code: {code})")

                # Fetch patient alive status
                cur.execute("SELECT first_name, last_name, death_date FROM patients WHERE id = %s", (pid,))
                pat_row = cur.fetchone()
                p_status = "ALIVE" if pat_row and pat_row[2] is None else "DECEASED"
                print(f"  Patient Name: {pat_row[0]} {pat_row[1]} | Status: {p_status}")

                if ctype in ("lab_result", "lab"):
                    cur.execute("""
                        SELECT code, description, numeric_value, units, observed_at
                        FROM lab_results
                        WHERE patient_id = %s AND code = %s
                        ORDER BY observed_at DESC LIMIT 1
                    """, (pid, str(code)))
                    row = cur.fetchone()
                    print(f"  Matched EHR Row (lab_results):")
                    print(f"    Code: {row[0]}")
                    print(f"    Description: {row[1]}")
                    print(f"    Value: {row[2]} {row[3]}")
                    print(f"    Observed At: {row[4]}")

                elif ctype in ("prescription", "med"):
                    cur.execute("""
                        SELECT code, description, start_date, stop_date
                        FROM prescriptions
                        WHERE patient_id = %s AND code = %s
                        ORDER BY start_date DESC LIMIT 1
                    """, (pid, str(code)))
                    row = cur.fetchone()
                    print(f"  Matched EHR Row (prescriptions):")
                    print(f"    Code: {row[0]}")
                    print(f"    Description: {row[1]}")
                    print(f"    Start Date: {row[2]} | Stop Date: {row[3]}")

                elif ctype in ("condition",):
                    cur.execute("""
                        SELECT code, description, start_date, stop_date
                        FROM conditions
                        WHERE patient_id = %s AND code = %s
                        ORDER BY start_date DESC LIMIT 1
                    """, (pid, str(code)))
                    row = cur.fetchone()
                    print(f"  Matched EHR Row (conditions):")
                    print(f"    Code: {row[0]}")
                    print(f"    Description: {row[1]}")
                    print(f"    Start Date: {row[2]} | Stop Date: {row[3]}")

                print("-" * 80)

if __name__ == "__main__":
    main()
