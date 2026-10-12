"""
Backfill stable_eids for integer-PK tables and create all spec indexes.
"""
import os
import sys
from pathlib import Path

ENV_PATH = Path("backend/.env")
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import psycopg

db_url = os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
print(f"Connecting to database...")

with psycopg.connect(db_url) as conn:
    with conn.cursor() as cur:
        for tbl, prefix in [
            ("lab_results", "lab"),
            ("conditions", "condition"),
            ("prescriptions", "prescription"),
            ("immunizations", "immunization"),
        ]:
            print(f"Backfilling stable_eid for {tbl}...")
            cur.execute(f"UPDATE {tbl} SET stable_eid = 'ehr:{prefix}:' || id::text WHERE stable_eid IS NULL")
            print(f"  {tbl}: {cur.rowcount} rows updated")
        conn.commit()
        
        print("\nCreating indexes...")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_pat_alive ON patients (is_alive, is_demo_fixture)",
            "CREATE INDEX IF NOT EXISTS idx_lab_patient_code_date ON lab_results (patient_id, code, observed_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_lab_stable_eid ON lab_results (stable_eid)",
            "CREATE INDEX IF NOT EXISTS idx_cond_patient_stopdate ON conditions (patient_id, stop_date)",
            "CREATE INDEX IF NOT EXISTS idx_cond_stable_eid ON conditions (stable_eid)",
            "CREATE INDEX IF NOT EXISTS idx_rx_patient_stopdate ON prescriptions (patient_id, stop_date)",
            "CREATE INDEX IF NOT EXISTS idx_rx_stable_eid ON prescriptions (stable_eid)",
            "CREATE INDEX IF NOT EXISTS idx_enc_patient_start ON encounters (patient_id, start_time DESC)",
            "CREATE INDEX IF NOT EXISTS idx_imm_patient ON immunizations (patient_id)",
        ]
        for ddl in indexes:
            print(f"Executing: {ddl}")
            cur.execute(ddl)
        conn.commit()
        print("All indexes created successfully.")
