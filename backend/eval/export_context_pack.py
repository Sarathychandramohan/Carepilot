"""
backend/eval/export_context_pack.py

Exports clinical context packs for shortlisted patients to data/annotation/context_packs.jsonl
and trimmed batch files: data/annotation/packs_batch_1.jsonl, packs_batch_2.jsonl, packs_batch_3.jsonl.

Rules:
  - Parses medication name, strength and dose (preserving '70 UNT/ML / 30 UNT/ML' and '24 HR').
  - Applies clinical plausibility ranges per concept (e.g. Creatinine [0.2, 15.0] mg/dL),
    excluding out-of-range values.
  - Assigns clinical flag (high|low|normal) to every lab using lab_results.is_abnormal,
    ref_min/ref_max, and fallback to reference_ranges.
  - Quota assignment: guarantees no two patients with the same (intent, key_lab_concept)
    until all concepts are exhausted; marks followup_appointment:urgent and general_health_info:urgent
    as stress_test in quota_tag.
  - Guarantees each pack always includes its key_lab_concept lab, even if not among
    the 6 most recent.
  - Deterministic (seed 42).
"""
from __future__ import annotations

import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.db.session import SessionLocal

OUTPUT_DIR = PROJECT_ROOT / "data" / "annotation"
OUTPUT_FILE = OUTPUT_DIR / "context_packs.jsonl"
SHORTLIST_FILE = OUTPUT_DIR / "patient_picker_shortlist.csv"

REAL_INTENTS = [
    "followup_appointment",
    "general_health_info",
    "lab_result_query",
    "medication_query",
    "symptom_report",
]

URGENCY_LEVELS = [
    "routine",
    "soon",
    "urgent",
]

# Survey exclusions
SURVEY_KEYWORDS = [
    "phenx", "morse", "survey", "questionnaire", "score", "assessment",
    "scale", "reported", "audit", "dast", "hark", "mmse", "vr-12", "phq", "gad",
    "qols", "qaly", "daly", "nyha", "kccq", "intake", "frequency", "employment",
    "tobacco", "smoking", "alcohol", "housing", "transportation", "income",
]
SURVEY_REGEX = re.compile("|".join(SURVEY_KEYWORDS), re.IGNORECASE)
NON_CLINICAL_UNITS = {"{score}", "{t-score}", "{#}", "{nominal}", "/a", "{activity_score}"}

STRENGTH_REGEX = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:UNT/ML|MG/ML|MG|MCG|ML|UNT|MEQ|G)\b",
    re.IGNORECASE,
)

CORE_LAB_CONCEPTS = [
    "Creatinine",
    "Glucose",
    "Hemoglobin A1c",
    "Cholesterol",
    "Potassium",
    "Sodium",
    "Urea nitrogen (BUN)",
    "Calcium",
    "Chloride",
    "Triglycerides",
    "Blood Pressure",
    "Microalbumin",
]

# Plausibility bounds per concept to exclude unphysiological/outlier rows
PLAUSIBILITY_RANGES: dict[str, tuple[float, float]] = {
    "Creatinine": (0.2, 15.0),
    "Glucose": (20.0, 800.0),
    "Hemoglobin A1c": (3.5, 18.0),
    "Potassium": (1.5, 8.5),
    "Sodium": (100.0, 180.0),
    "Calcium": (4.0, 18.0),
    "Chloride": (60.0, 140.0),
    "Urea nitrogen (BUN)": (2.0, 150.0),
    "Cholesterol": (50.0, 600.0),
    "Triglycerides": (20.0, 1500.0),
    "Blood Pressure": (30.0, 260.0),
    "eGFR": (5.0, 200.0),
    "Microalbumin": (0.0, 5000.0),
}

# Clinical static reference range fallback from seed_reference_ranges.py
STATIC_REF_RANGES: dict[str, tuple[float | None, float | None]] = {
    "2160-0": (0.6, 1.2),     # Creatinine in Serum/Plasma
    "38483-4": (0.6, 1.3),    # Creatinine in Blood
    "33914-3": (60.0, None),  # eGFR
    "14959-1": (None, 30.0),  # Microalbumin in Urine
    "32294-1": (None, 30.0),  # Albumin/Creatinine ratio
    "3094-0": (7.0, 20.0),    # Urea nitrogen (BUN)
    "4548-4": (None, 5.7),    # Hemoglobin A1c
    "88293-6": (None, 5.7),   # Hemoglobin A1c
    "2345-7": (70.0, 99.0),   # Glucose in Serum/Plasma
    "2339-0": (70.0, 99.0),   # Glucose in Blood
    "2093-3": (None, 200.0),  # Total Cholesterol
    "2089-1": (None, 100.0),  # LDL Cholesterol
    "2085-9": (40.0, None),   # HDL Cholesterol
    "2571-8": (None, 150.0),  # Triglycerides
    "718-7": (12.0, 17.5),    # Hemoglobin
    "787-2": (80.0, 100.0),   # MCV
    "6690-2": (4.5, 11.0),    # Leukocytes
    "777-3": (150.0, 400.0),  # Platelets
    "2947-0": (136.0, 145.0), # Sodium
    "2823-3": (3.5, 5.0),     # Potassium
    "2075-0": (98.0, 106.0),  # Chloride
    "1963-8": (22.0, 29.0),   # Bicarbonate
    "49765-1": (8.5, 10.5),   # Calcium
}


def parse_medication(raw_desc: str) -> dict[str, str]:
    """
    Parse medication name, strength and dose from raw prescriptions.description.
    Keeps composite strengths like '70 UNT/ML / 30 UNT/ML' and prefix '24 HR'.
    """
    raw = (raw_desc or "").strip()
    is_24hr = bool(re.match(r"^24\s*HR\b", raw, re.IGNORECASE))

    # Extract brand name if present [Humulin], [Tylenol]
    brand_match = re.search(r"(\[.*?\])", raw)
    brand = f" {brand_match.group(1)}" if brand_match else ""

    # Extract strengths
    strengths = STRENGTH_REGEX.findall(raw)
    strength_str = " / ".join(s.strip() for s in strengths) if strengths else ""

    # Clean name
    clean = STRENGTH_REGEX.sub("", raw)
    clean = re.sub(r"\[.*?\]", "", clean)
    clean = re.sub(
        r"\b(?:Extended Release|Oral Tablet|Injectable Suspension|Injectable Solution|Oral Solution|Topical Gel|Chewable Tablet|Oral Capsule|Capsule|Tablet)\b",
        "",
        clean,
        flags=re.IGNORECASE,
    )
    clean = re.sub(r"\s*/\s*", " / ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    if is_24hr and not clean.lower().startswith("24 hr"):
        clean = f"24 HR {clean}"

    name = f"{clean}{brand}".strip()
    return {
        "raw": raw,
        "name": name,
        "strength": strength_str,
        "dose": strength_str,
    }


def is_survey_lab(desc: str, units: str | None) -> bool:
    """Filter out surveys, scores, and questionnaires."""
    if not units or units.strip().lower() in NON_CLINICAL_UNITS:
        return True
    if SURVEY_REGEX.search(desc):
        return True
    if "?" in desc or desc.startswith(("What ", "How ", "Do ", "Have ", "Are ", "Total ", "Overall ")):
        return True
    return False


def determine_lab_flag(
    val: float,
    is_abnormal: bool | None,
    min_v: float | None,
    max_v: float | None,
    desc: str,
) -> str:
    """Determine flag (high|low|normal) using ranges and is_abnormal fallback."""
    if max_v is not None and val > max_v:
        return "high"
    if min_v is not None and val < min_v:
        return "low"
    if min_v is not None and max_v is not None and min_v <= val <= max_v:
        return "normal"
    if min_v is not None and max_v is None:
        return "normal" if val >= min_v else "low"
    if max_v is not None and min_v is None:
        return "normal" if val <= max_v else "high"

    # Fallback to is_abnormal
    if is_abnormal is True:
        return "high"
    return "normal"


def extract_key_concept(desc: str) -> str | None:
    """Map raw lab test description to one of the canonical core concepts."""
    d_lower = desc.lower()
    if "creatinine" in d_lower and "egfr" not in d_lower and "ratio" not in d_lower:
        return "Creatinine"
    if "glucose" in d_lower:
        return "Glucose"
    if "hemoglobin a1c" in d_lower or "hba1c" in d_lower:
        return "Hemoglobin A1c"
    if "cholesterol" in d_lower:
        return "Cholesterol"
    if "potassium" in d_lower:
        return "Potassium"
    if "sodium" in d_lower:
        return "Sodium"
    if "urea nitrogen" in d_lower:
        return "Urea nitrogen (BUN)"
    if "calcium" in d_lower:
        return "Calcium"
    if "chloride" in d_lower:
        return "Chloride"
    if "triglyceride" in d_lower:
        return "Triglycerides"
    if "blood pressure" in d_lower or "systolic" in d_lower or "diastolic" in d_lower:
        return "Blood Pressure"
    if "microalbumin" in d_lower:
        return "Microalbumin"
    return None


def select_recent_labs_with_key_concept(
    candidate_labs: list[dict[str, Any]],
    key_concept: str,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """
    Ensure the pack's key_lab_concept lab is always included, even if it is not
    among the limit most recent.
    """
    if not candidate_labs:
        return []

    # Check if key_concept is already within top limit
    has_kc = any(extract_key_concept(l["concept"]) == key_concept for l in candidate_labs[:limit])
    if has_kc:
        return candidate_labs[:limit]

    # Find the most recent lab matching key_concept
    kc_lab = None
    for l in candidate_labs:
        if extract_key_concept(l["concept"]) == key_concept:
            kc_lab = l
            break

    if kc_lab is not None:
        # Include it: take top limit - 1 and append kc_lab
        selected = candidate_labs[: max(1, limit - 1)] + [kc_lab]
        # Sort by date DESC
        return sorted(selected, key=lambda x: str(x.get("date", "")), reverse=True)

    return candidate_labs[:limit]


def export_context_packs(
    shortlist_path: Path = SHORTLIST_FILE,
    output_path: Path = OUTPUT_FILE,
    seed: int = 42,
    rename_bp_to_vital: bool = False,
    start_scenario_idx: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """
    Export clinical context packs with enhanced quota assignment, lab flags,
    plausibility filtering, and guaranteed key lab concept inclusion.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(shortlist_path, "r", encoding="utf-8") as f:
        shortlist = list(csv.DictReader(f))

    shortlist = sorted(shortlist, key=lambda x: x["patient_id"])
    total_patients = len(shortlist)

    db = SessionLocal()
    today = date.today()
    packs = []
    total_excluded_plausibility = 0

    try:
        # Load reference ranges from DB
        rr_map = dict(STATIC_REF_RANGES)
        rr_rows = db.execute(
            text("SELECT code, normal_min, normal_max, ref_min, ref_max FROM reference_ranges")
        ).fetchall()
        for r in rr_rows:
            min_v = r.ref_min if r.ref_min is not None else r.normal_min
            max_v = r.ref_max if r.ref_max is not None else r.normal_max
            if min_v is not None or max_v is not None:
                rr_map[r.code] = (min_v, max_v)

        # Pre-query clinical labs with plausibility filtering
        patient_labs_raw: dict[str, list[dict[str, Any]]] = {}
        patient_concepts: dict[str, list[str]] = {}

        for row in shortlist:
            pid = row["patient_id"]
            lab_rows = db.execute(
                text("""
                    SELECT code, description, numeric_value, units, observed_at, is_abnormal, ref_min, ref_max
                    FROM lab_results 
                    WHERE patient_id = :pid 
                      AND numeric_value IS NOT NULL
                    ORDER BY observed_at DESC NULLS LAST, id ASC
                """),
                {"pid": pid},
            ).fetchall()

            valid_labs = []
            seen_concepts = set()
            avail_concepts = []

            for lr in lab_rows:
                desc = (lr.description or "").strip()
                units = (lr.units or "").strip()
                if not desc or is_survey_lab(desc, units):
                    continue

                val = round(float(lr.numeric_value), 2)

                # Plausibility bounds check
                kc = extract_key_concept(desc)
                if kc and kc in PLAUSIBILITY_RANGES:
                    # Filter out urine test strip glucose from serum plausibility
                    if kc == "Glucose" and "urine" in desc.lower():
                        total_excluded_plausibility += 1
                        continue
                    p_min, p_max = PLAUSIBILITY_RANGES[kc]
                    if val < p_min or val > p_max:
                        total_excluded_plausibility += 1
                        continue

                if desc.lower() in seen_concepts:
                    continue
                seen_concepts.add(desc.lower())

                d_str = lr.observed_at.strftime("%Y-%m-%d") if lr.observed_at else ""

                min_v, max_v = rr_map.get(lr.code, (lr.ref_min, lr.ref_max))
                if min_v is None:
                    min_v = lr.ref_min
                if max_v is None:
                    max_v = lr.ref_max

                flag = determine_lab_flag(val, lr.is_abnormal, min_v, max_v, desc)

                valid_labs.append({
                    "concept": desc,
                    "value": val,
                    "unit": units,
                    "date": d_str,
                    "flag": flag,
                    "code": lr.code,
                })

                if kc and kc not in avail_concepts:
                    avail_concepts.append(kc)

            patient_labs_raw[pid] = valid_labs
            patient_concepts[pid] = avail_concepts

        # Quota Assignment (seed 42)
        rng = random.Random(seed)
        combos = [(intent, urg) for intent in REAL_INTENTS for urg in URGENCY_LEVELS]
        slots = (combos * ((total_patients // len(combos)) + 1))[:total_patients]
        rng.shuffle(slots)

        intent_used_concepts: dict[str, set[str]] = defaultdict(set)
        patient_assigned_key_concept: dict[str, str] = {}

        for idx, row in enumerate(shortlist):
            pid = row["patient_id"]
            intent, urg = slots[idx]
            avail = patient_concepts.get(pid, [])

            chosen_concept = None
            for c in avail:
                if c not in intent_used_concepts[intent]:
                    chosen_concept = c
                    break

            if chosen_concept is None:
                if avail:
                    chosen_concept = avail[0]
                else:
                    chosen_concept = CORE_LAB_CONCEPTS[idx % len(CORE_LAB_CONCEPTS)]

            intent_used_concepts[intent].add(chosen_concept)
            patient_assigned_key_concept[pid] = chosen_concept

        # Build packs
        for idx, row in enumerate(shortlist):
            pid = row["patient_id"]
            intent, urg = slots[idx]

            # Mark stress_test for followup_appointment:urgent and general_health_info:urgent
            if (intent == "followup_appointment" and urg == "urgent") or (
                intent == "general_health_info" and urg == "urgent"
            ):
                quota_tag = f"{intent}:{urg}:stress_test"
            else:
                quota_tag = f"{intent}:{urg}"

            scenario_id = f"S{start_scenario_idx + idx + 1:04d}"
            key_concept = patient_assigned_key_concept[pid]
            if rename_bp_to_vital and key_concept == "Blood Pressure":
                key_concept = "vital"

            # Demographics
            p_row = db.execute(
                text("SELECT birth_date, gender FROM patients WHERE id = :pid"),
                {"pid": pid},
            ).fetchone()
            bdate = p_row.birth_date if p_row else None
            gender = p_row.gender if p_row else row.get("sex", "")

            if bdate:
                age = today.year - bdate.year - ((today.month, today.day) < (bdate.month, bdate.day))
            else:
                age = int(row.get("age", 0)) if row.get("age") else 0

            sex = "M" if str(gender).upper().startswith("M") else "F" if str(gender).upper().startswith("F") else str(gender)

            # Active medications
            rx_rows = db.execute(
                text("""
                    SELECT description, start_date 
                    FROM prescriptions 
                    WHERE patient_id = :pid AND stop_date IS NULL
                    ORDER BY start_date DESC NULLS LAST, id ASC
                """),
                {"pid": pid},
            ).fetchall()

            active_meds = []
            seen_meds = set()
            for r in rx_rows:
                raw_desc = (r.description or "").strip()
                if not raw_desc:
                    continue
                parsed = parse_medication(raw_desc)
                if parsed["name"].lower() in seen_meds:
                    continue
                seen_meds.add(parsed["name"].lower())
                start_str = r.start_date.strftime("%Y-%m-%d") if r.start_date else ""
                active_meds.append({
                    "name": parsed["name"],
                    "dose": parsed["dose"],
                    "strength": parsed["strength"],
                    "start": start_str,
                })
                if len(active_meds) >= 6:
                    break

            # Disorders
            cond_rows = db.execute(
                text("""
                    SELECT description, start_date 
                    FROM conditions 
                    WHERE patient_id = :pid 
                      AND LOWER(description) LIKE '%(disorder)%'
                    ORDER BY start_date DESC NULLS LAST, id ASC
                """),
                {"pid": pid},
            ).fetchall()

            disorders = []
            seen_dis = set()
            for r in cond_rows:
                d_desc = (r.description or "").strip()
                if not d_desc or d_desc.lower() in seen_dis:
                    continue
                seen_dis.add(d_desc.lower())
                disorders.append(d_desc)
                if len(disorders) >= 6:
                    break

            # Ensure recent_labs always includes the key_lab_concept lab
            raw_patient_labs = patient_labs_raw[pid]
            raw_key_concept = patient_assigned_key_concept[pid]
            selected_labs = select_recent_labs_with_key_concept(raw_patient_labs, raw_key_concept, limit=6)

            recent_labs = [
                {
                    "concept": l["concept"],
                    "value": l["value"],
                    "unit": l["unit"],
                    "date": l["date"],
                    "flag": l["flag"],
                }
                for l in selected_labs
            ]

            # Encounters (up to 3)
            enc_rows = db.execute(
                text("""
                    SELECT description, encounter_class, start_time 
                    FROM encounters 
                    WHERE patient_id = :pid 
                    ORDER BY start_time DESC NULLS LAST, id ASC
                    LIMIT 3
                """),
                {"pid": pid},
            ).fetchall()

            encounters = []
            for er in enc_rows:
                enc_type = (er.description or er.encounter_class or "Consultation").strip()
                date_str = er.start_time.strftime("%Y-%m-%d") if er.start_time else ""
                encounters.append({
                    "type": enc_type,
                    "date": date_str,
                })

            allowed = []
            if len(active_meds) > 0:
                allowed.append("medication_query")
            if len(disorders) > 0:
                allowed.append("symptom_report")
            if len(recent_labs) > 0:
                allowed.append("lab_result_query")
            if len(encounters) > 0:
                allowed.append("followup_appointment")
            allowed.append("general_health_info")
            allowed_sorted = [i for i in REAL_INTENTS if i in allowed]

            pack = {
                "patient_id": pid,
                "age": age,
                "sex": sex,
                "active_medications": active_meds,
                "disorders": disorders,
                "recent_labs": recent_labs,
                "upcoming_or_recent_encounters": encounters,
                "allowed_intents": allowed_sorted,
                "assigned_quota_tag": quota_tag,
                "scenario_id": scenario_id,
                "key_lab_concept": key_concept,
            }
            packs.append(pack)

    finally:
        db.close()

    # Write master context_packs.jsonl
    with open(output_path, "w", encoding="utf-8") as f:
        for p in packs:
            f.write(json.dumps(p) + "\n")

    # Write batches of 20 trimmed as data/annotation/packs_batch_N.jsonl
    batch_size = 20
    for b_idx in range(0, total_patients, batch_size):
        b_num = (b_idx // batch_size) + 1
        b_file = OUTPUT_DIR / f"packs_batch_{b_num}.jsonl"
        b_slice = packs[b_idx : b_idx + batch_size]
        with open(b_file, "w", encoding="utf-8") as bf:
            for p in b_slice:
                trimmed = {
                    "patient_id": p["patient_id"],
                    "age": p["age"],
                    "sex": p["sex"],
                    "meds": p["active_medications"],
                    "disorders": p["disorders"],
                    "recent_labs": p["recent_labs"],
                    "upcoming_or_recent_encounters": p["upcoming_or_recent_encounters"],
                    "assigned_quota_tag": p["assigned_quota_tag"],
                    "scenario_id": p["scenario_id"],
                    "key_lab_concept": p["key_lab_concept"],
                }
                bf.write(json.dumps(trimmed) + "\n")

    return packs, total_excluded_plausibility


def main():
    import argparse
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Export clinical context packs")
    parser.add_argument("--new-45", action="store_true", help="Export 45 new context packs from patient_picker_shortlist_new_45.csv")
    args = parser.parse_args()

    if args.new_45:
        shortlist_target = OUTPUT_DIR / "patient_picker_shortlist_new_45.csv"
        output_target = OUTPUT_DIR / "context_packs_new_45.jsonl"
        print(f"Exporting 45 new context packs from {shortlist_target}...")
        packs, excluded = export_context_packs(
            shortlist_path=shortlist_target,
            output_path=output_target,
            start_scenario_idx=60,
        )
    else:
        print(f"Exporting context packs from {SHORTLIST_FILE}...")
        packs, excluded = export_context_packs()

    print(f"Row count: {len(packs)}")
    print(f"Count of excluded out-of-range lab rows: {excluded}")

    # Check key_lab_concept inclusion across all packs
    all_included = True
    missing_count = 0
    for p in packs:
        kc = p["key_lab_concept"]
        has_it = any(extract_key_concept(l["concept"]) == kc for l in p["recent_labs"])
        if not has_it:
            all_included = False
            missing_count += 1

    print(f"Check: Key lab concept included in all {len(packs)} packs: {all_included} (missing={missing_count})")


if __name__ == "__main__":
    main()
