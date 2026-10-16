"""
backend/eval/export_patient_picker.py

Exports patient clinical summaries for human annotators to construct
patient-grounded evaluation queries.
Targets all alive patients in carepilot_v3 database.
Output: data/annotation/patient_picker_sheet.csv
"""
from __future__ import annotations

import csv
import datetime
from collections import defaultdict
from pathlib import Path
import numpy as np
from sqlalchemy import text

from backend.app.db.session import SessionLocal

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "annotation"
OUTPUT_FILE = OUTPUT_DIR / "patient_picker_sheet.csv"
SHORTLIST_FILE = OUTPUT_DIR / "patient_picker_shortlist.csv"


def export_patient_picker_sheet() -> tuple[float, float, int, int]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today()

    db = SessionLocal()
    try:
        # 1. Query all alive patients with fact counts
        patient_sql = """
        SELECT 
            p.id AS patient_id,
            p.birth_date,
            p.gender,
            COALESCE(rx_act.cnt, 0) AS active_rx_count,
            COALESCE(rx_all.cnt, 0) AS rx_count,
            COALESCE(cd.cnt, 0) AS cd_count,
            COALESCE(lb.cnt, 0) AS lb_count,
            (COALESCE(rx_all.cnt, 0) + COALESCE(cd.cnt, 0) + COALESCE(lb.cnt, 0)) AS total_facts
        FROM patients p
        LEFT JOIN (
            SELECT patient_id, COUNT(*) AS cnt 
            FROM prescriptions 
            WHERE stop_date IS NULL
            GROUP BY patient_id
        ) rx_act ON p.id = rx_act.patient_id
        LEFT JOIN (
            SELECT patient_id, COUNT(*) AS cnt 
            FROM prescriptions 
            GROUP BY patient_id
        ) rx_all ON p.id = rx_all.patient_id
        LEFT JOIN (
            SELECT patient_id, COUNT(*) AS cnt 
            FROM conditions 
            GROUP BY patient_id
        ) cd ON p.id = cd.patient_id
        LEFT JOIN (
            SELECT patient_id, COUNT(*) AS cnt 
            FROM lab_results 
            GROUP BY patient_id
        ) lb ON p.id = lb.patient_id
        WHERE p.is_alive = TRUE
        ORDER BY p.id ASC;
        """
        patient_rows = db.execute(text(patient_sql)).fetchall()
        total_patients = len(patient_rows)

        if total_patients == 0:
            print("No alive patients found in database.")
            return 0.0, 0.0, 0, 0

        # Calculate median and p75 for total_facts
        facts_list = [r.total_facts for r in patient_rows]
        median_facts = float(np.median(facts_list))
        p75 = float(np.percentile(facts_list, 75))

        # 2. Query up to 5 active medications per patient (stop_date IS NULL)
        rx_sql = """
        SELECT patient_id, description
        FROM (
            SELECT patient_id, description,
                   ROW_NUMBER() OVER (
                       PARTITION BY patient_id 
                       ORDER BY start_date DESC NULLS LAST, id ASC
                   ) AS rn
            FROM prescriptions
            WHERE stop_date IS NULL
        ) sub
        WHERE rn <= 5;
        """
        rx_rows = db.execute(text(rx_sql)).fetchall()
        patient_meds = defaultdict(list)
        for r in rx_rows:
            if r.description:
                patient_meds[r.patient_id].append(r.description.strip())

        # 3. Query up to 5 conditions per patient
        cond_sql = """
        SELECT patient_id, description
        FROM (
            SELECT patient_id, description,
                   ROW_NUMBER() OVER (
                       PARTITION BY patient_id 
                       ORDER BY start_date DESC NULLS LAST, id ASC
                   ) AS rn
            FROM conditions
        ) sub
        WHERE rn <= 5;
        """
        cond_rows = db.execute(text(cond_sql)).fetchall()
        patient_conditions = defaultdict(list)
        for r in cond_rows:
            if r.description:
                patient_conditions[r.patient_id].append(r.description.strip())

        # 4. Query up to 5 most recent labs per patient with description and value
        lab_sql = """
        SELECT patient_id, description, value, units
        FROM (
            SELECT patient_id, description, value, units,
                   ROW_NUMBER() OVER (
                       PARTITION BY patient_id 
                       ORDER BY observed_at DESC NULLS LAST, id ASC
                   ) AS rn
            FROM lab_results
        ) sub
        WHERE rn <= 5;
        """
        lab_rows = db.execute(text(lab_sql)).fetchall()
        patient_labs = defaultdict(list)
        for r in lab_rows:
            desc = r.description.strip() if r.description else "Lab"
            val = str(r.value).strip() if r.value is not None else ""
            units = f" {r.units.strip()}" if r.units else ""
            lab_str = f"{desc}: {val}{units}" if val else desc
            patient_labs[r.patient_id].append(lab_str)

        # 5. Format CSV rows
        headers = [
            "patient_id",
            "age",
            "sex",
            "total_facts",
            "long_record",
            "active_medications",
            "conditions",
            "recent_labs",
        ]

        out_rows = []
        rows_by_id = {}
        for r in patient_rows:
            pid = str(r.patient_id)
            if r.birth_date:
                bdate = r.birth_date
                age = today.year - bdate.year - ((today.month, today.day) < (bdate.month, bdate.day))
            else:
                age = ""

            gender = str(r.gender) if r.gender else ""
            total_f = int(r.total_facts)
            is_long = bool(total_f > p75)

            meds_str = "; ".join(patient_meds.get(pid, []))
            cond_str = "; ".join(patient_conditions.get(pid, []))
            labs_str = "; ".join(patient_labs.get(pid, []))

            row_data = [
                pid,
                age,
                gender,
                total_f,
                is_long,
                meds_str,
                cond_str,
                labs_str,
            ]
            out_rows.append(row_data)
            rows_by_id[pid] = row_data

        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(out_rows)

        # 6. Build Shortlist of 60 patients
        # Eligibility: >=2 active medications, >=2 conditions, >=3 lab rows
        import hashlib

        eligible = [
            r for r in patient_rows
            if r.active_rx_count >= 2 and r.cd_count >= 2 and r.lb_count >= 3
        ]

        # Stratum 1: total_facts > p75 (30 patients)
        stratum_high = [r for r in eligible if r.total_facts > p75]
        stratum_high_sorted = sorted(
            stratum_high,
            key=lambda r: hashlib.sha256(f"42|{r.patient_id}".encode("utf-8")).hexdigest(),
        )
        picked_high = stratum_high_sorted[:30]

        # Stratum 2: median <= total_facts <= p75 (30 patients)
        stratum_mid = [r for r in eligible if median_facts <= r.total_facts <= p75]
        stratum_mid_sorted = sorted(
            stratum_mid,
            key=lambda r: hashlib.sha256(f"42|{r.patient_id}".encode("utf-8")).hexdigest(),
        )
        picked_mid = stratum_mid_sorted[:30]

        shortlist_records = picked_high + picked_mid
        # Deterministic order by patient_id
        shortlist_records_sorted = sorted(shortlist_records, key=lambda r: r.patient_id)
        shortlist_rows = [rows_by_id[str(r.patient_id)] for r in shortlist_records_sorted]

        with open(SHORTLIST_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(shortlist_rows)

        return median_facts, p75, total_patients, len(shortlist_rows)
    finally:
        db.close()


if __name__ == "__main__":
    median_facts, p75, count, sl_count = export_patient_picker_sheet()
    print(f"Exported {count} alive patients to {OUTPUT_FILE}")
    print(f"Exported {sl_count} shortlisted patients to {SHORTLIST_FILE}")
    print(f"Cohort median total facts: {median_facts:.2f}")
    print(f"Cohort p75 total facts threshold: {p75:.2f}")
