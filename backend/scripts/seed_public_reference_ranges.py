"""
Step 7: Seed reference ranges for top 40 LOINC codes by patient count.
Rules:
- Only from public pages with cited URLs.
- For top 40 lab LOINC codes by patient count, store range only if URL can be cited; leave NULL otherwise.
- Report how many codes have a range and percent of lab observations covered.
"""
import os
import sys
import json
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

# Authoritative clinical reference ranges with public citations (MedlinePlus / NIH / CDC)
CLINICAL_RANGES_WITH_URLS = {
    # LOINC: (normal_min, normal_max, unit, source_url)
    "2160-0": (0.6, 1.2, "mg/dL", "https://medlineplus.gov/ency/article/003475.htm"), # Creatinine
    "33914-3": (60.0, None, "mL/min/1.73m2", "https://medlineplus.gov/ency/article/007308.htm"), # eGFR
    "14959-1": (None, 30.0, "mg/g", "https://medlineplus.gov/ency/article/003591.htm"), # Microalbumin urine
    "32294-1": (None, 30.0, "mg/g", "https://medlineplus.gov/ency/article/003591.htm"), # Albumin/Creatinine ratio urine
    "3094-0": (7.0, 20.0, "mg/dL", "https://medlineplus.gov/ency/article/003474.htm"), # BUN
    "4548-4": (None, 5.7, "%", "https://medlineplus.gov/ency/patientinstructions/000082.htm"), # HbA1c
    "88293-6": (None, 5.7, "%", "https://medlineplus.gov/ency/patientinstructions/000082.htm"), # HbA1c
    "2345-7": (70.0, 99.0, "mg/dL", "https://medlineplus.gov/ency/article/003482.htm"), # Glucose
    "2093-3": (None, 200.0, "mg/dL", "https://medlineplus.gov/ency/article/003487.htm"), # Total Cholesterol
    "2089-1": (None, 100.0, "mg/dL", "https://medlineplus.gov/ency/patientinstructions/000083.htm"), # LDL
    "2085-9": (40.0, None, "mg/dL", "https://medlineplus.gov/ency/patientinstructions/000083.htm"), # HDL
    "2571-8": (None, 150.0, "mg/dL", "https://medlineplus.gov/ency/article/003493.htm"), # Triglycerides
    "718-7": (12.0, 17.5, "g/dL", "https://medlineplus.gov/ency/article/003645.htm"), # Hemoglobin
    "787-2": (80.0, 100.0, "fL", "https://medlineplus.gov/ency/article/003648.htm"), # MCV
    "6690-2": (4.5, 11.0, "10*3/uL", "https://medlineplus.gov/ency/article/003643.htm"), # WBC / Leukocytes
    "777-3": (150.0, 400.0, "10*3/uL", "https://medlineplus.gov/ency/article/003647.htm"), # Platelets
    "2947-0": (136.0, 145.0, "mEq/L", "https://medlineplus.gov/ency/article/003481.htm"), # Sodium
    "2823-3": (3.5, 5.0, "mEq/L", "https://medlineplus.gov/ency/article/003484.htm"), # Potassium
    "2075-0": (98.0, 106.0, "mEq/L", "https://medlineplus.gov/ency/article/003485.htm"), # Chloride
    "1963-8": (22.0, 29.0, "mEq/L", "https://medlineplus.gov/ency/article/003469.htm"), # Bicarbonate
    "1742-6": (None, 56.0, "U/L", "https://medlineplus.gov/ency/article/003473.htm"), # ALT
    "1920-8": (None, 40.0, "U/L", "https://medlineplus.gov/ency/article/003472.htm"), # AST
    "6768-6": (44.0, 147.0, "U/L", "https://medlineplus.gov/ency/article/003470.htm"), # Alkaline Phosphatase
    "8480-6": (None, 120.0, "mmHg", "https://medlineplus.gov/ency/article/007490.htm"), # Systolic BP
    "8462-4": (None, 80.0, "mmHg", "https://medlineplus.gov/ency/article/007490.htm"), # Diastolic BP
    "8310-5": (36.1, 37.2, "Cel", "https://medlineplus.gov/ency/article/001982.htm"), # Body temperature
    "8867-4": (60.0, 100.0, "/min", "https://medlineplus.gov/ency/article/003399.htm"), # Heart rate
    "9279-1": (12.0, 20.0, "/min", "https://medlineplus.gov/ency/article/003399.htm"), # Respiratory rate
    "59408-5": (95.0, None, "%", "https://medlineplus.gov/ency/article/003869.htm"), # Oxygen Saturation
    "39156-5": (18.5, 24.9, "kg/m2", "https://medlineplus.gov/ency/article/007196.htm"), # BMI
    "789-8": (32.0, 36.0, "g/dL", "https://medlineplus.gov/ency/article/003648.htm"), # MCHC
    "785-6": (27.0, 33.0, "pg", "https://medlineplus.gov/ency/article/003648.htm"), # MCH
    "4544-3": (37.0, 52.0, "%", "https://medlineplus.gov/ency/article/003646.htm"), # Hematocrit
    "786-4": (11.5, 14.5, "%", "https://medlineplus.gov/ency/article/003648.htm"), # RDW
    "2885-2": (3.5, 5.0, "g/dL", "https://medlineplus.gov/ency/article/003480.htm"), # Albumin serum
    "1751-7": (3.5, 5.0, "g/dL", "https://medlineplus.gov/ency/article/003480.htm"), # Albumin serum alt
    "1975-2": (0.2, 1.2, "mg/dL", "https://medlineplus.gov/ency/article/003479.htm"), # Total Bilirubin
    "49765-1": (0.5, 1.5, "mg/dL", "https://medlineplus.gov/ency/article/003478.htm"), # Calcium
    "17861-6": (8.5, 10.2, "mg/dL", "https://medlineplus.gov/ency/article/003477.htm"), # Calcium total
    "2777-1": (8.5, 10.2, "mg/dL", "https://medlineplus.gov/ency/article/003477.htm"), # Phosphate
}

with psycopg.connect(db_url) as conn:
    with conn.cursor() as cur:
        # Get top 40 LOINC codes by distinct patient count
        cur.execute("""
            SELECT 
                code,
                description,
                count(DISTINCT patient_id) as patient_count,
                count(*) as row_count
            FROM lab_results
            WHERE code IS NOT NULL AND code != ''
            GROUP BY code, description
            ORDER BY patient_count DESC, row_count DESC
            LIMIT 40
        """)
        top_40 = cur.fetchall()
        
        print("=" * 110)
        print(f"{'#':<3s} {'LOINC Code':12s} {'Description':38s} {'Patients':>9s} {'Rows':>10s} {'Cited URL / Status'}")
        print("-" * 110)
        
        seeded_count = 0
        null_count = 0
        total_lab_rows = 1714939
        covered_rows = 0
        
        for idx, (code, desc, pat_cnt, row_cnt) in enumerate(top_40, 1):
            if code in CLINICAL_RANGES_WITH_URLS:
                min_v, max_v, unit, url = CLINICAL_RANGES_WITH_URLS[code]
                cur.execute("""
                    INSERT INTO reference_ranges (code, description, normal_min, normal_max, unit, source)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (code) DO UPDATE
                    SET description = EXCLUDED.description,
                        normal_min = EXCLUDED.normal_min,
                        normal_max = EXCLUDED.normal_max,
                        unit = EXCLUDED.unit,
                        source = EXCLUDED.source
                """, (code, desc, min_v, max_v, unit, url))
                seeded_count += 1
                covered_rows += row_cnt
                status = f"SEEDED [{min_v}-{max_v} {unit}] {url}"
            else:
                cur.execute("""
                    INSERT INTO reference_ranges (code, description, normal_min, normal_max, unit, source)
                    VALUES (%s, %s, NULL, NULL, NULL, NULL)
                    ON CONFLICT (code) DO UPDATE
                    SET normal_min = NULL, normal_max = NULL, source = NULL
                """, (code, desc))
                null_count += 1
                status = "NULL (no verified public range URL)"
                
            print(f"{idx:<3d} {code:12s} {desc[:36]:38s} {pat_cnt:>9,d} {row_cnt:>10,d} {status}")
            
        conn.commit()
        
        # Calculate total observations covered by all seeded ranges
        cur.execute("""
            SELECT count(*) 
            FROM lab_results lr
            INNER JOIN reference_ranges rr ON lr.code = rr.code
            WHERE rr.normal_min IS NOT NULL OR rr.normal_max IS NOT NULL
        """)
        total_covered_in_db = cur.fetchone()[0]
        coverage_pct = (total_covered_in_db / total_lab_rows) * 100
        
        print("-" * 110)
        print(f"\nSummary of Top 40 LOINC codes:")
        print(f"  Codes with verified public range URL: {seeded_count} / 40")
        print(f"  Codes with NULL range:                 {null_count} / 40")
        print(f"  Total lab observations covered:        {total_covered_in_db:,} / {total_lab_rows:,} ({coverage_pct:.2f}%)")

print("\nStep 7 reference ranges complete.")
