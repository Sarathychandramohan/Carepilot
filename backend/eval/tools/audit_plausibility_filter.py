"""
Audit Lab Plausibility Filter in export_context_pack.py
Measures:
1. Top 20 most frequent concepts dropped (survey and plausibility).
2. Top 20 most frequent concepts dropped strictly by plausibility.
3. 5 dropped values that fall inside [ref_min, ref_max] * 3 (or [ref_min/3, ref_max*3]).
"""
import csv
from collections import Counter
from pathlib import Path

from backend.app.db.session import SessionLocal
from backend.app.db.models_v3 import LabResult, Patient
from backend.eval.export_context_pack import (
    SHORTLIST_FILE,
    PLAUSIBILITY_RANGES,
    STATIC_REF_RANGES,
    is_survey_lab,
    extract_key_concept,
)

def main():
    # Load shortlisted patients (105 patients)
    patient_ids = []
    if SHORTLIST_FILE.exists():
        with open(SHORTLIST_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                patient_ids.append(r["patient_id"])
    else:
        print("Shortlist file not found.")
        return

    session = SessionLocal()
    try:
        lab_rows = (
            session.query(LabResult)
            .filter(LabResult.patient_id.in_(patient_ids))
            .filter(LabResult.numeric_value.isnot(None))
            .all()
        )
        print(f"Total numeric lab rows for {len(patient_ids)} shortlisted patients: {len(lab_rows)}")

        dropped_survey = Counter()
        dropped_plausibility = Counter()
        dropped_values_info = []

        for lr in lab_rows:
            desc = (lr.description or "").strip()
            units = (lr.units or "").strip()
            if not desc:
                continue

            if is_survey_lab(desc, units):
                dropped_survey[desc] += 1
                continue

            val = round(float(lr.numeric_value), 2)
            kc = extract_key_concept(desc)

            if kc and kc in PLAUSIBILITY_RANGES:
                if kc == "Glucose" and "urine" in desc.lower():
                    dropped_plausibility[desc + " (urine strip)"] += 1
                    continue
                p_min, p_max = PLAUSIBILITY_RANGES[kc]
                if val < p_min or val > p_max:
                    dropped_plausibility[desc] += 1
                    
                    # Check reference ranges
                    ref_min, ref_max = STATIC_REF_RANGES.get(lr.code, (lr.ref_min, lr.ref_max))
                    
                    # Check if val falls inside widened reference range [ref_min/3, ref_max*3]
                    is_within_ref_x3 = False
                    if ref_min is not None and ref_max is not None:
                        is_within_ref_x3 = (ref_min / 3.0) <= val <= (ref_max * 3.0)
                    elif ref_min is not None and ref_max is None:
                        is_within_ref_x3 = (ref_min / 3.0) <= val <= (ref_min * 3.0)
                    elif ref_max is not None and ref_min is None:
                        is_within_ref_x3 = 0 <= val <= (ref_max * 3.0)
                        
                    dropped_values_info.append({
                        "patient_id": str(lr.patient_id),
                        "code": lr.code,
                        "concept": desc,
                        "key_concept": kc,
                        "value": val,
                        "units": units,
                        "plausibility_bounds": (p_min, p_max),
                        "ref_bounds": (ref_min, ref_max),
                        "is_within_ref_x3": is_within_ref_x3,
                    })

        print("\n" + "=" * 80)
        print("TOP 20 MOST FREQUENT CONCEPTS DROPPED BY PLAUSIBILITY FILTER")
        print("=" * 80)
        for concept, count in dropped_plausibility.most_common(20):
            print(f"  {count:5d}  |  {concept}")

        print("\n" + "=" * 80)
        print("TOP 20 MOST FREQUENT CONCEPTS DROPPED AS SURVEY/ASSESSMENT LABS")
        print("=" * 80)
        for concept, count in dropped_survey.most_common(20):
            print(f"  {count:5d}  |  {concept}")

        inside_ref_x3 = [d for d in dropped_values_info if d["is_within_ref_x3"]]
        print("\n" + "=" * 80)
        print(f"DROPPED PLAUSIBILITY VALUES WITHIN [ref_min/3, ref_max*3]: {len(inside_ref_x3)} / {len(dropped_values_info)}")
        print("=" * 80)
        print("5 Representative Examples of Discarded Values with Clinical Context:")
        for idx, ex in enumerate(inside_ref_x3[:5], start=1):
            print(f"\n[{idx}/5] Concept: {ex['concept']} (Code {ex['code']})")
            print(f"     Dropped Value:       {ex['value']} {ex['units']}")
            print(f"     Plausibility Bounds: {ex['plausibility_bounds']}")
            print(f"     Static/Ref Bounds:   {ex['ref_bounds']}")
            print(f"     Widened [ref/3, ref*3]: {ex['is_within_ref_x3']}")

    finally:
        session.close()

if __name__ == "__main__":
    main()
