import os
from pathlib import Path

env_p = Path("backend/.env")
if env_p.exists():
    for line in env_p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import psycopg

url = os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(url) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name, column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND data_type = 'json'
        """)
        json_cols = cur.fetchall()
        print(f"Columns with type 'json': {len(json_cols)}")
        for tbl, col in json_cols:
            print(f"Altering {tbl}.{col} to jsonb...")
            cur.execute(f"ALTER TABLE {tbl} ALTER COLUMN {col} TYPE jsonb USING {col}::jsonb")
        conn.commit()
        print("Done altering json -> jsonb.")
