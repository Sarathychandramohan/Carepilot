"""
D:\\CarePilotAI\\backend\\scripts\\verify_ehr_latency.py

Benchmarks EHR retrieval query latency against carepilot_db.
Tests 3 query patterns across 20 random patients.
PASS criterion: p95 <= 200ms for all 3 query types.

Saves results to data/manifests/ehr_latency_report.json.

Usage:
    python -m backend.scripts.verify_ehr_latency --db-password YOUR_PASS
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import psycopg

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"


def percentile(values: list[float], p: int) -> float:
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * p / 100
    f = int(k)
    c = f + 1
    if c >= len(sorted_v):
        return sorted_v[-1]
    return sorted_v[f] + (k - f) * (sorted_v[c] - sorted_v[f])


def get_random_patient_ids(cur: psycopg.Cursor, n: int = 20) -> list[str]:
    cur.execute(
        "SELECT id FROM patients WHERE death_date IS NULL ORDER BY RANDOM() LIMIT %s",
        (n,)
    )
    rows = cur.fetchall()
    if not rows:
        raise RuntimeError("No alive patients found in database. Run ETL first.")
    return [r[0] for r in rows]


def benchmark_query(
    cur: psycopg.Cursor,
    sql: str,
    params: tuple,
    label: str,
    patient_ids: list[str],
    n_samples: int = 20,
) -> dict:
    latencies = []
    for pid in patient_ids[:n_samples]:
        t0 = time.perf_counter()
        cur.execute(sql, (pid,) + params)
        cur.fetchall()
        latencies.append((time.perf_counter() - t0) * 1000)  # ms

    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    passed = p95 <= 200.0

    result = {
        "query_type": label,
        "samples": n_samples,
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "max_ms": round(max(latencies), 2),
        "passed": passed,
    }
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {status} {label}: p50={p50:.1f}ms  p95={p95:.1f}ms  max={max(latencies):.1f}ms")
    return result


def get_dsn_and_largest_patient(cur) -> str:
    pass

def main():
    parser = argparse.ArgumentParser(description="Verify EHR query latency")
    parser.add_argument("--db-host", default=None)
    parser.add_argument("--db-port", type=int, default=None)
    parser.add_argument("--db-name", default=None)
    parser.add_argument("--db-user", default=None)
    parser.add_argument("--db-password", default=None)
    parser.add_argument("--samples", type=int, default=20,
                        help="Number of random patients to benchmark per query type")
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

    print(f"\nConnecting to database...")

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            # Find patient with largest record
            cur.execute("""
                SELECT patient_id, count(*) as total_records
                FROM (
                    SELECT patient_id FROM encounters
                    UNION ALL SELECT patient_id FROM lab_results
                    UNION ALL SELECT patient_id FROM conditions
                    UNION ALL SELECT patient_id FROM prescriptions
                    UNION ALL SELECT patient_id FROM procedures
                ) all_rec
                GROUP BY patient_id
                ORDER BY total_records DESC
                LIMIT 1
            """)
            largest_row = cur.fetchone()
            largest_pid, largest_cnt = largest_row[0], largest_row[1]
            print(f"Patient with largest clinical record: {largest_pid} ({largest_cnt:,} total rows)")
            
            # Benchmark largest patient
            print("\n--- Latency on Patient with Largest Record ---")
            queries = [
                ("SELECT id, description, code FROM conditions WHERE patient_id = %s AND stop_date IS NULL ORDER BY start_date DESC",
                 (), "active_conditions (largest patient)"),
                ("SELECT id, stable_eid, observed_at, numeric_value, units, is_abnormal FROM lab_results WHERE patient_id = %s AND code = '2160-0' ORDER BY observed_at DESC LIMIT 5",
                 (), "creatinine_labs_recent5 (largest patient)"),
                ("SELECT id, description, start_date FROM prescriptions WHERE patient_id = %s AND stop_date IS NULL ORDER BY start_date DESC",
                 (), "active_medications (largest patient)"),
            ]
            for sql, params, label in queries:
                latencies = []
                for _ in range(10):
                    t0 = time.perf_counter()
                    cur.execute(sql, (largest_pid,) + params)
                    cur.fetchall()
                    latencies.append((time.perf_counter() - t0) * 1000)
                p50 = percentile(latencies, 50)
                p95 = percentile(latencies, 95)
                status = "PASS" if p95 <= 200.0 else "FAIL"
                print(f"  [{status}] {label}: p50={p50:.2f}ms, p95={p95:.2f}ms, max={max(latencies):.2f}ms")

            print("\n--- Latency on Random Sample of Alive Patients ---")
            patient_ids = get_random_patient_ids(cur, args.samples)
            print(f"Benchmarking with {len(patient_ids)} random patients...\n")

            results = []

            # Q1: Active conditions for a patient
            results.append(benchmark_query(
                cur=cur,
                sql="SELECT id, description, code FROM conditions WHERE patient_id = %s AND stop_date IS NULL ORDER BY start_date DESC",
                params=(),
                label="active_conditions",
                patient_ids=patient_ids,
                n_samples=args.samples,
            ))

            # Q2: Most recent 5 lab results for a specific LOINC code (Creatinine)
            results.append(benchmark_query(
                cur=cur,
                sql="SELECT id, stable_eid, observed_at, numeric_value, units, is_abnormal FROM lab_results WHERE patient_id = %s AND code = '2160-0' ORDER BY observed_at DESC LIMIT 5",
                params=(),
                label="creatinine_labs_recent5",
                patient_ids=patient_ids,
                n_samples=args.samples,
            ))

            # Q3: Active medications
            results.append(benchmark_query(
                cur=cur,
                sql="SELECT id, description, start_date FROM prescriptions WHERE patient_id = %s AND stop_date IS NULL ORDER BY start_date DESC",
                params=(),
                label="active_medications",
                patient_ids=patient_ids,
                n_samples=args.samples,
            ))

    # Evaluate overall gate
    all_passed = all(r["passed"] for r in results)
    gate_status = "PASS" if all_passed else "FAIL"

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "gate_status": gate_status,
        "gate_criterion": "p95 <= 200ms for all query types",
        "sample_count": args.samples,
        "results": results,
    }

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    report_path = MANIFEST_DIR / "ehr_latency_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n{'='*50}")
    print(f"Overall gate: {gate_status}")
    print(f"Report saved: {report_path}")

    if not all_passed:
        print("\nACTION REQUIRED: Some queries exceed p95 = 200ms threshold.")
        print("Check that all composite indexes were created (run create_db_schema.py or synthea_bulk_load.py).")
        sys.exit(1)
    else:
        print("✓ A1 EHR latency gate PASSED. Proceed to A2.")


if __name__ == "__main__":
    main()
