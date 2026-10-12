"""
backend/scripts/merge_ehr.py

CarePilot v3 Phase 1B – Smart EHR merge with full demo-fixture integration.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEMO_DIR  = PROJECT_ROOT / "synthea" / "carepilot_output"    / "csv"
SCALE_DIR = PROJECT_ROOT / "synthea" / "carepilot_output_2k" / "csv"
MANIFESTS = PROJECT_ROOT / "data" / "manifests"

LOAD_TABLES = [
    ("patients.csv",       "patients"),
    ("encounters.csv",     "encounters"),
    ("observations.csv",   "lab_results"),
    ("conditions.csv",     "conditions"),
    ("medications.csv",    "prescriptions"),
    ("allergies.csv",      "allergies"),
    ("procedures.csv",     "procedures"),
    ("careplans.csv",      "care_plans"),
    ("immunizations.csv",  "immunizations"),
]


def clean(val: str | None) -> str | None:
    v = (val or "").strip()
    return v if v else None


def stable_eid(table: str, raw_id: str) -> str:
    return f"ehr:{table}:{raw_id}"


def _csv_line(*fields) -> str:
    parts = []
    for f in fields:
        if f is None or f == "":
            parts.append("\\N")
        else:
            parts.append(str(f).replace(",", " "))
    return ",".join(parts) + "\n"


# ─── Buffer Builders ─────────────────────────────────────────────────────────

def build_patients_buffer(
    csv_dir: Path,
    id_prefix: str = "",
    is_demo: bool = False,
    source_run: str = "scale2k",
) -> tuple[io.StringIO, int]:
    buf = io.StringIO()
    count = 0
    with open(csv_dir / "patients.csv", encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            raw_id = clean(row.get("Id"))
            if not raw_id:
                continue
            pid = f"{id_prefix}{raw_id}" if id_prefix else raw_id
            deathdate = clean(row.get("DEATHDATE"))
            is_alive = "f" if deathdate else "t"
            buf.write(_csv_line(
                pid,
                stable_eid("patient", pid),
                clean(row.get("BIRTHDATE")),
                deathdate,
                clean(row.get("PREFIX")),
                clean(row.get("FIRST")) or "Unknown",
                clean(row.get("MIDDLE")),
                clean(row.get("LAST")) or "Unknown",
                clean(row.get("SUFFIX")),
                clean(row.get("MARITAL")),
                clean(row.get("RACE")),
                clean(row.get("ETHNICITY")),
                clean(row.get("GENDER")),
                clean(row.get("BIRTHPLACE")),
                clean(row.get("ADDRESS")),
                clean(row.get("CITY")),
                clean(row.get("STATE")),
                clean(row.get("COUNTY")),
                clean(row.get("ZIP")),
                clean(row.get("LAT")),
                clean(row.get("LON")),
                clean(row.get("INCOME")),
                "t" if is_demo else "f",
                is_alive,
                source_run,
            ))
            count += 1
    return buf, count


def build_encounters_buffer(
    csv_dir: Path,
    id_prefix: str = "",
) -> tuple[io.StringIO, int]:
    p = csv_dir / "encounters.csv"
    if not p.exists():
        return io.StringIO(), 0
    buf = io.StringIO()
    count = 0
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            raw_id = clean(row.get("Id"))
            pat_id = clean(row.get("PATIENT"))
            if not raw_id or not pat_id:
                continue
            enc_id = f"{id_prefix}{raw_id}" if id_prefix else raw_id
            p_id = f"{id_prefix}{pat_id}" if id_prefix else pat_id
            buf.write(_csv_line(
                enc_id,
                stable_eid("encounter", enc_id),
                p_id,
                clean(row.get("START")),
                clean(row.get("STOP")),
                clean(row.get("ORGANIZATION")),
                clean(row.get("PROVIDER")),
                clean(row.get("PAYER")),
                clean(row.get("ENCOUNTERCLASS")),
                clean(row.get("CODE")),
                clean(row.get("DESCRIPTION")),
                clean(row.get("REASONCODE")),
                clean(row.get("REASONDESCRIPTION")),
            ))
            count += 1
    return buf, count


def build_observations_buffer(
    csv_dir: Path,
    id_prefix: str = "",
) -> tuple[io.StringIO, int]:
    p = csv_dir / "observations.csv"
    if not p.exists():
        return io.StringIO(), 0
    buf = io.StringIO()
    count = 0
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            pat_id = clean(row.get("PATIENT"))
            if not pat_id:
                continue
            p_id = f"{id_prefix}{pat_id}" if id_prefix else pat_id
            enc_id = clean(row.get("ENCOUNTER"))
            if enc_id and id_prefix:
                enc_id = f"{id_prefix}{enc_id}"
            
            val_str = clean(row.get("VALUE"))
            num_val = None
            if val_str:
                try:
                    num_val = float(val_str)
                except ValueError:
                    num_val = None

            buf.write(_csv_line(
                p_id,
                enc_id,
                clean(row.get("DATE")),
                clean(row.get("CODE")),
                clean(row.get("DESCRIPTION")),
                val_str,
                num_val,
                clean(row.get("UNITS")),
                clean(row.get("TYPE")),
            ))
            count += 1
    return buf, count


def build_conditions_buffer(
    csv_dir: Path,
    id_prefix: str = "",
) -> tuple[io.StringIO, int]:
    p = csv_dir / "conditions.csv"
    if not p.exists():
        return io.StringIO(), 0
    buf = io.StringIO()
    count = 0
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            pat_id = clean(row.get("PATIENT"))
            if not pat_id:
                continue
            p_id = f"{id_prefix}{pat_id}" if id_prefix else pat_id
            enc_id = clean(row.get("ENCOUNTER"))
            if enc_id and id_prefix:
                enc_id = f"{id_prefix}{enc_id}"
            buf.write(_csv_line(
                p_id,
                enc_id,
                clean(row.get("START")),
                clean(row.get("STOP")),
                clean(row.get("CODE")),
                clean(row.get("DESCRIPTION")),
            ))
            count += 1
    return buf, count


def build_medications_buffer(
    csv_dir: Path,
    id_prefix: str = "",
) -> tuple[io.StringIO, int]:
    p = csv_dir / "medications.csv"
    if not p.exists():
        return io.StringIO(), 0
    buf = io.StringIO()
    count = 0
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            pat_id = clean(row.get("PATIENT"))
            if not pat_id:
                continue
            p_id = f"{id_prefix}{pat_id}" if id_prefix else pat_id
            enc_id = clean(row.get("ENCOUNTER"))
            if enc_id and id_prefix:
                enc_id = f"{id_prefix}{enc_id}"
            buf.write(_csv_line(
                p_id,
                enc_id,
                clean(row.get("START")),
                clean(row.get("STOP")),
                clean(row.get("CODE")),
                clean(row.get("DESCRIPTION")),
                clean(row.get("DISPENSES")),
                clean(row.get("REASONCODE")),
                clean(row.get("REASONDESCRIPTION")),
            ))
            count += 1
    return buf, count


def build_allergies_buffer(
    csv_dir: Path,
    id_prefix: str = "",
) -> tuple[io.StringIO, int]:
    p = csv_dir / "allergies.csv"
    if not p.exists():
        return io.StringIO(), 0
    buf = io.StringIO()
    count = 0
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            pat_id = clean(row.get("PATIENT"))
            if not pat_id:
                continue
            p_id = f"{id_prefix}{pat_id}" if id_prefix else pat_id
            enc_id = clean(row.get("ENCOUNTER"))
            if enc_id and id_prefix:
                enc_id = f"{id_prefix}{enc_id}"
            raw_id = f"{p_id}_{clean(row.get('CODE'))}_{clean(row.get('START'))}"
            buf.write(_csv_line(
                raw_id,
                stable_eid("allergy", raw_id),
                p_id,
                enc_id,
                clean(row.get("START")),
                clean(row.get("STOP")),
                clean(row.get("CODE")),
                clean(row.get("SYSTEM")),
                clean(row.get("DESCRIPTION")),
                clean(row.get("TYPE")),
                clean(row.get("CATEGORY")),
                clean(row.get("REACTION1")),
                clean(row.get("DESCRIPTION1")),
                clean(row.get("SEVERITY1")),
                clean(row.get("REACTION2")),
                clean(row.get("DESCRIPTION2")),
                clean(row.get("SEVERITY2")),
            ))
            count += 1
    return buf, count


def build_procedures_buffer(
    csv_dir: Path,
    id_prefix: str = "",
) -> tuple[io.StringIO, int]:
    p = csv_dir / "procedures.csv"
    if not p.exists():
        return io.StringIO(), 0
    buf = io.StringIO()
    count = 0
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            pat_id = clean(row.get("PATIENT"))
            if not pat_id:
                continue
            p_id = f"{id_prefix}{pat_id}" if id_prefix else pat_id
            enc_id = clean(row.get("ENCOUNTER"))
            if enc_id and id_prefix:
                enc_id = f"{id_prefix}{enc_id}"
            raw_id = f"{p_id}_{clean(row.get('CODE'))}_{clean(row.get('START'))}"
            buf.write(_csv_line(
                raw_id,
                stable_eid("procedure", raw_id),
                p_id,
                enc_id,
                clean(row.get("START")),
                clean(row.get("STOP")),
                clean(row.get("SYSTEM")),
                clean(row.get("CODE")),
                clean(row.get("DESCRIPTION")),
                clean(row.get("REASONCODE")),
                clean(row.get("REASONDESCRIPTION")),
            ))
            count += 1
    return buf, count


def build_careplans_buffer(
    csv_dir: Path,
    id_prefix: str = "",
) -> tuple[io.StringIO, int]:
    p = csv_dir / "careplans.csv"
    if not p.exists():
        return io.StringIO(), 0
    buf = io.StringIO()
    count = 0
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            raw_id = clean(row.get("Id"))
            pat_id = clean(row.get("PATIENT"))
            if not raw_id or not pat_id:
                continue
            cp_id = f"{id_prefix}{raw_id}" if id_prefix else raw_id
            p_id = f"{id_prefix}{pat_id}" if id_prefix else pat_id
            enc_id = clean(row.get("ENCOUNTER"))
            if enc_id and id_prefix:
                enc_id = f"{id_prefix}{enc_id}"
            buf.write(_csv_line(
                cp_id,
                stable_eid("care_plan", cp_id),
                p_id,
                enc_id,
                clean(row.get("START")),
                clean(row.get("STOP")),
                clean(row.get("CODE")),
                clean(row.get("DESCRIPTION")),
                clean(row.get("REASONCODE")),
                clean(row.get("REASONDESCRIPTION")),
            ))
            count += 1
    return buf, count


def build_immunizations_buffer(
    csv_dir: Path,
    id_prefix: str = "",
) -> tuple[io.StringIO, int]:
    p = csv_dir / "immunizations.csv"
    if not p.exists():
        return io.StringIO(), 0
    buf = io.StringIO()
    count = 0
    with open(p, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            pat_id = clean(row.get("PATIENT"))
            if not pat_id:
                continue
            p_id = f"{id_prefix}{pat_id}" if id_prefix else pat_id
            enc_id = clean(row.get("ENCOUNTER"))
            if enc_id and id_prefix:
                enc_id = f"{id_prefix}{enc_id}"
            raw_id = f"{p_id}_{clean(row.get('CODE'))}_{clean(row.get('DATE'))}"
            buf.write(_csv_line(
                raw_id,
                stable_eid("immunization", raw_id),
                p_id,
                enc_id,
                clean(row.get("DATE")),
                clean(row.get("CODE")),
                clean(row.get("DESCRIPTION")),
                clean(row.get("BASE_COST")),
            ))
            count += 1
    return buf, count


def backfill_stable_eids(cur) -> None:
    tables = [
        ("lab_results",   "lab"),
        ("conditions",    "condition"),
        ("prescriptions", "prescription"),
    ]
    for table, prefix in tables:
        cur.execute(
            f"UPDATE {table} SET stable_eid = 'ehr:' || '{prefix}:' || id::text WHERE stable_eid IS NULL"
        )


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


def get_dsn(args) -> str:
    env = {**read_env(PROJECT_ROOT / "backend" / ".env"), **os.environ}
    db_url = env.get("DATABASE_URL")
    if not db_url:
        print("ERROR: No DATABASE_URL found in backend/.env.")
        sys.exit(1)
    
    if "carepilot_db" in db_url:
        print("ERROR GUARD: DATABASE_URL points to 'carepilot_db'! Target MUST be 'carepilot_v3'. Stopping.")
        sys.exit(1)
        
    return db_url.replace("postgresql+psycopg://", "postgresql://")


def do_copy(cur, sql: str, buf: io.StringIO) -> None:
    buf.seek(0)
    with cur.copy(sql) as copy:
        while chunk := buf.read(65536):
            copy.write(chunk)


def main() -> None:
    parser = argparse.ArgumentParser(description="CarePilot v3 Phase 1B Smart EHR Merger")
    parser.add_argument("--dry-run", action="store_true", help="Parse and verify totals without DB writes")
    args = parser.parse_args()

    print("=" * 70)
    print("CarePilot v3 Phase 1B – Smart EHR Merge")
    print("=" * 70)

    p_scale_buf, p_scale_n = build_patients_buffer(SCALE_DIR, id_prefix="", is_demo=False, source_run="scale2k")
    p_demo_buf,  p_demo_n  = build_patients_buffer(DEMO_DIR,  id_prefix="demo40:", is_demo=True,  source_run="demo40")

    e_scale_buf, e_scale_n = build_encounters_buffer(SCALE_DIR, id_prefix="")
    e_demo_buf,  e_demo_n  = build_encounters_buffer(DEMO_DIR,  id_prefix="demo40:")

    obs_scale_buf, obs_scale_n = build_observations_buffer(SCALE_DIR, id_prefix="")
    obs_demo_buf,  obs_demo_n  = build_observations_buffer(DEMO_DIR,  id_prefix="demo40:")

    c_scale_buf, c_scale_n = build_conditions_buffer(SCALE_DIR, id_prefix="")
    c_demo_buf,  c_demo_n  = build_conditions_buffer(DEMO_DIR,  id_prefix="demo40:")

    rx_scale_buf, rx_scale_n = build_medications_buffer(SCALE_DIR, id_prefix="")
    rx_demo_buf,  rx_demo_n  = build_medications_buffer(DEMO_DIR,  id_prefix="demo40:")

    al_scale_buf, al_scale_n = build_allergies_buffer(SCALE_DIR, id_prefix="")
    al_demo_buf,  al_demo_n  = build_allergies_buffer(DEMO_DIR,  id_prefix="demo40:")

    pr_scale_buf, pr_scale_n = build_procedures_buffer(SCALE_DIR, id_prefix="")
    pr_demo_buf,  pr_demo_n  = build_procedures_buffer(DEMO_DIR,  id_prefix="demo40:")

    cp_scale_buf, cp_scale_n = build_careplans_buffer(SCALE_DIR, id_prefix="")
    cp_demo_buf,  cp_demo_n  = build_careplans_buffer(DEMO_DIR,  id_prefix="demo40:")

    im_scale_buf, im_scale_n = build_immunizations_buffer(SCALE_DIR, id_prefix="")
    im_demo_buf,  im_demo_n  = build_immunizations_buffer(DEMO_DIR,  id_prefix="demo40:")

    manifest_p = MANIFESTS / "ehr_source_manifest.json"
    manifest_data = {}
    if manifest_p.exists():
        manifest_data = json.loads(manifest_p.read_text(encoding="utf-8")).get("expected_rows_after_merge", {})

    summary = [
        ("patients.csv",      "patients",       p_scale_n,   p_demo_n),
        ("encounters.csv",    "encounters",     e_scale_n,   e_demo_n),
        ("observations.csv",  "lab_results",    obs_scale_n, obs_demo_n),
        ("conditions.csv",    "conditions",     c_scale_n,   c_demo_n),
        ("medications.csv",   "prescriptions",  rx_scale_n,  rx_demo_n),
        ("allergies.csv",     "allergies",      al_scale_n,  al_demo_n),
        ("procedures.csv",    "procedures",     pr_scale_n,  pr_demo_n),
        ("careplans.csv",     "care_plans",     cp_scale_n,  cp_demo_n),
        ("immunizations.csv", "immunizations",  im_scale_n,  im_demo_n),
    ]

    print("\n" + "=" * 100)
    print(f"{'Source CSV':18s} {'DB Table':15s} {'Scale 2k':>12s} {'Demo 40':>12s} {'Total Planned':>14s} {'Expected':>14s} {'Match':>8s}")
    print("-" * 100)

    all_match = True
    for src_csv, db_tbl, s_cnt, d_cnt in summary:
        tot = s_cnt + d_cnt
        exp = manifest_data.get(src_csv, {}).get("expected_rows_after_merge", -1)
        matches = (tot == exp)
        if not matches:
            all_match = False
        print(f"{src_csv:18s} {db_tbl:15s} {s_cnt:>12,d} {d_cnt:>12,d} {tot:>14,d} {exp:>14,d} {'OK' if matches else 'DIFF':>8s}")
    print("-" * 100)

    if not all_match:
        print("\nERROR: Table total calculations do not match expected manifest counts! Stopping.")
        sys.exit(1)

    print(f"\nAll table calculations match manifest: {all_match}")

    if args.dry_run:
        print("\n*** DRY RUN COMPLETE — 0 rows written to database ***")
        return

    import psycopg
    dsn = get_dsn(args)
    print("\nConnecting to database carepilot_v3 ...")

    with psycopg.connect(dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE patients, encounters, lab_results, conditions, prescriptions, allergies, procedures, care_plans, immunizations RESTART IDENTITY CASCADE;")
            
            print("Loading patients ...")
            pat_sql = "COPY patients (id, stable_eid, birth_date, death_date, prefix, first_name, middle_name, last_name, suffix, marital_status, race, ethnicity, gender, birthplace, address, city, state, county, zip_code, latitude, longitude, income, is_demo_fixture, is_alive, source_run) FROM STDIN (FORMAT CSV, NULL '\\N')"
            do_copy(cur, pat_sql, p_scale_buf)
            do_copy(cur, pat_sql, p_demo_buf)

            print("Loading encounters ...")
            enc_sql = "COPY encounters (id, stable_eid, patient_id, start_time, stop_time, organization_id, provider_id, payer_id, encounter_class, code, description, reason_code, reason_description) FROM STDIN (FORMAT CSV, NULL '\\N')"
            do_copy(cur, enc_sql, e_scale_buf)
            do_copy(cur, enc_sql, e_demo_buf)

            print("Loading lab_results ...")
            obs_sql = "COPY lab_results (patient_id, encounter_id, observed_at, code, description, value, numeric_value, units, value_type) FROM STDIN (FORMAT CSV, NULL '\\N')"
            do_copy(cur, obs_sql, obs_scale_buf)
            do_copy(cur, obs_sql, obs_demo_buf)

            print("Loading conditions ...")
            cond_sql = "COPY conditions (patient_id, encounter_id, start_date, stop_date, code, description) FROM STDIN (FORMAT CSV, NULL '\\N')"
            do_copy(cur, cond_sql, c_scale_buf)
            do_copy(cur, cond_sql, c_demo_buf)

            print("Loading prescriptions ...")
            rx_sql = "COPY prescriptions (patient_id, encounter_id, start_date, stop_date, code, description, dispenses, reason_code, reason_description) FROM STDIN (FORMAT CSV, NULL '\\N')"
            do_copy(cur, rx_sql, rx_scale_buf)
            do_copy(cur, rx_sql, rx_demo_buf)

            print("Loading allergies ...")
            alg_sql = "COPY allergies (id, stable_eid, patient_id, encounter_id, start_date, stop_date, code, system, description, type, category, reaction1, reaction1_description, reaction1_severity, reaction2, reaction2_description, reaction2_severity) FROM STDIN (FORMAT CSV, NULL '\\N')"
            do_copy(cur, alg_sql, al_scale_buf)
            do_copy(cur, alg_sql, al_demo_buf)

            print("Loading procedures ...")
            proc_sql = "COPY procedures (id, stable_eid, patient_id, encounter_id, start_time, stop_time, system, code, description, reason_code, reason_description) FROM STDIN (FORMAT CSV, NULL '\\N')"
            do_copy(cur, proc_sql, pr_scale_buf)
            do_copy(cur, proc_sql, pr_demo_buf)

            print("Loading care_plans ...")
            cp_sql = "COPY care_plans (id, stable_eid, patient_id, encounter_id, start_date, stop_date, code, description, reason_code, reason_description) FROM STDIN (FORMAT CSV, NULL '\\N')"
            do_copy(cur, cp_sql, cp_scale_buf)
            do_copy(cur, cp_sql, cp_demo_buf)

            print("Loading immunizations ...")
            imm_sql = "COPY immunizations (id, stable_eid, patient_id, encounter_id, administered_at, code, description, base_cost) FROM STDIN (FORMAT CSV, NULL '\\N')"
            do_copy(cur, imm_sql, im_scale_buf)
            do_copy(cur, imm_sql, im_demo_buf)

            print("Backfilling stable_eids ...")
            backfill_stable_eids(cur)

            conn.commit()
            print("\n[OK] Transaction committed successfully!")

    print("\nMerge Phase 1B Complete!")


if __name__ == "__main__":
    main()
