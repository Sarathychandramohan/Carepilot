"""Check DB connection - prints host and database only, never password."""
import os
import sys
from pathlib import Path

env_p = Path(__file__).resolve().parents[2] / "backend" / ".env"
if not env_p.exists():
    env_p = Path("backend/.env")

if env_p.exists():
    for line in env_p.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from urllib.parse import urlparse

url = os.environ.get("DATABASE_URL", "")
if not url:
    print("ERROR: DATABASE_URL not set in backend/.env")
    sys.exit(1)

p = urlparse(url.replace("postgresql+psycopg://", "postgresql://"))
print(f"Host:     {p.hostname}")
print(f"Database: {p.path.lstrip('/')}")
print(f"Port:     {p.port}")

try:
    import psycopg
    conn_str = url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(conn_str) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), version()")
            row = cur.fetchone()
            print(f"Connected DB: {row[0]}")
            print(f"PG version:   {row[1].split('(')[0].strip()}")
except Exception as e:
    print(f"Connection failed: {e}")
    sys.exit(1)
