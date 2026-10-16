"""
D:\\CarePilotAI\\backend\\scripts\\silver_generator.py

Generates at least 3,000 synthetic patient queries (Silver Dataset)
from 25 Scenario Families (SF) instantiated with complex alive patient EHR records from carepilot_v3.

Requirements:
- 25 scenario families, split assigned strictly by whole scenario family (Train / Dev / Test).
- At least 3,000 total queries.
- At least 30% not needing the EHR (requires_patient_context = False).
- Every patient-specific query MUST reference a real concept present in that patient's EHR
  (active condition, latest lab result, or active medication from carepilot_v3).
- Outputs to data/queries/silver.jsonl.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPLEX_PATIENTS_PATH = PROJECT_ROOT / "data" / "manifests" / "complex_patients.json"
SILVER_OUTPUT_PATH = PROJECT_ROOT / "data" / "queries" / "silver.jsonl"
GOLD_PATH = PROJECT_ROOT / "data" / "queries" / "gold_scripted_candidate.jsonl"


def clean_medication(desc: str) -> str:
    d = re.sub(r"^\d+\s*HR\s*", "", desc, flags=re.IGNORECASE)
    d = re.sub(r"\s*\d+(\.\d+)?\s*(MG|MCG|ML|UNT|MEQ).*", "", d, flags=re.IGNORECASE)
    d = re.sub(r"\[.*?\]", "", d)
    d = d.strip()
    return d if d else desc


def clean_condition(desc: str) -> str:
    d = re.sub(r"\s*\((disorder|finding|situation)\)", "", desc, flags=re.IGNORECASE)
    d = re.sub(r"\[.*?\]", "", d)
    d = d.strip()
    return d if d else desc


def is_clinical_condition(desc: str) -> bool:
    """Filter out situations and administrative findings that lack clinical symptom/disease content."""
    dl = desc.lower()
    if "(situation)" in dl or "review due" in dl:
        return False
    if "(finding)" in dl:
        # Exclude administrative/social/lifestyle findings
        non_clinical = [
            "employment", "educated", "education", "social", "housing",
            "refugee", "stress", "partner abuse", "abuse", "criminal",
            "transportation", "food insecurity", "marital", "drinking behavior",
            "misuses drugs", "violence", "labor force", "unemployed"
        ]
        if any(k in dl for k in non_clinical):
            return False
    return True


def clean_lab(desc: str) -> str:
    d = re.sub(r"\s*\[.*?\]", "", desc)
    d = re.sub(r"\s+in\s+.*", "", d, flags=re.IGNORECASE)
    d = d.strip()
    return d if d else desc


SCENARIO_FAMILIES = {
    # -----------------------------------------------------------------------
    # TRAIN FAMILIES (13 families)
    # -----------------------------------------------------------------------
    "SF-TRAIN-LAB-PATIENT": {
        "intent": "lab_result_query",
        "urgency": "routine",
        "split": "train",
        "requires_ehr": True,
        "concept_type": "lab",
        "templates": [
            "My recent {lab_name} test came back at {val} {unit}. What does this mean?",
            "Is a {lab_name} level of {val} {unit} considered normal or concerning?",
            "Can you explain why my {lab_name} is showing {val} {unit}?",
            "Should I be worried about my latest {lab_name} reading of {val} {unit}?",
        ],
    },
    "SF-TRAIN-MED-SIDE-EFFECT": {
        "intent": "medication_query",
        "urgency": "routine",
        "split": "train",
        "requires_ehr": True,
        "concept_type": "med",
        "templates": [
            "I've been taking {med} and feel slightly dizzy in the morning. Is this a side effect?",
            "Can taking {med} cause mild stomach upset or fatigue?",
            "I started {med} recently and noticed mild nausea. Is that expected?",
            "Are there any common side effects I should watch out for while taking {med}?",
        ],
    },
    "SF-TRAIN-COND-MANAGEMENT": {
        "intent": "general_health_info",
        "urgency": "routine",
        "split": "train",
        "requires_ehr": True,
        "concept_type": "condition",
        "templates": [
            "What daily habits help manage my diagnosis of {condition}?",
            "How can I best monitor symptoms related to my {condition}?",
            "What lifestyle adjustments should I make for my {condition}?",
        ],
    },
    "SF-TRAIN-MED-INTERACTION": {
        "intent": "medication_query",
        "urgency": "soon",
        "split": "train",
        "requires_ehr": True,
        "concept_type": "med",
        "templates": [
            "Is it safe to take over-the-counter ibuprofen while I am prescribed {med}?",
            "Can I take seasonal allergy pills while on {med}?",
            "Do any cold medications interact dangerously with my {med}?",
        ],
    },
    "SF-TRAIN-APPT-ROUTINE": {
        "intent": "followup_appointment",
        "urgency": "routine",
        "split": "train",
        "requires_ehr": True,
        "concept_type": "condition",
        "templates": [
            "When should I schedule my next routine checkup for my {condition}?",
            "Do I need a follow-up appointment next month to check on my {condition}?",
            "How often should I see my physician to review my {condition}?",
        ],
    },
    "SF-TRAIN-SYMPTOM-FATIGUE": {
        "intent": "symptom_report",
        "urgency": "routine",
        "split": "train",
        "requires_ehr": True,
        "concept_type": "condition",
        "templates": [
            "I've been feeling unusually tired lately. Could it be linked to my {condition}?",
            "Is chronic daytime fatigue common for someone with {condition}?",
        ],
    },
    "SF-TRAIN-MED-TIMING": {
        "intent": "medication_query",
        "urgency": "routine",
        "split": "train",
        "requires_ehr": True,
        "concept_type": "med",
        "templates": [
            "Should I take my {med} with breakfast or right before going to bed?",
            "Does {med} need to be taken with meals to prevent stomach irritation?",
        ],
    },
    "SF-TRAIN-SYMPTOM-URGENT": {
        "intent": "symptom_report",
        "urgency": "urgent",
        "split": "train",
        "requires_ehr": False,
        "concept_type": "none",
        "templates": [
            "I am having severe crushing chest pain radiating to my jaw and arm.",
            "I suddenly cannot move my left arm and my face is drooping.",
            "I am coughing up bright red blood and cannot catch my breath.",
            "I have intense sudden difficulty speaking and numbness on one side of my body.",
        ],
    },
    "SF-TRAIN-GENERAL-DIET": {
        "intent": "general_health_info",
        "urgency": "routine",
        "split": "train",
        "requires_ehr": False,
        "concept_type": "none",
        "templates": [
            "What dietary changes are recommended to support healthy kidney filtration?",
            "How does reducing dietary sodium help protect cardiovascular health?",
            "What are the benefits of a Mediterranean-style diet for heart health?",
            "How much water should an adult drink daily for optimal hydration?",
        ],
    },
    "SF-TRAIN-GENERAL-BP": {
        "intent": "general_health_info",
        "urgency": "routine",
        "split": "train",
        "requires_ehr": False,
        "concept_type": "none",
        "templates": [
            "What is considered an ideal blood pressure reading for adults?",
            "How does aerobic exercise help lower resting blood pressure?",
            "What is the difference between systolic and diastolic blood pressure numbers?",
        ],
    },
    "SF-TRAIN-GENERAL-VACCINE": {
        "intent": "general_health_info",
        "urgency": "routine",
        "split": "train",
        "requires_ehr": False,
        "concept_type": "none",
        "templates": [
            "Who should receive the annual influenza immunization?",
            "Are adult booster shots for tetanus recommended every ten years?",
            "What are the CDC guidelines for pneumococcal pneumonia vaccination?",
        ],
    },
    "SF-TRAIN-GENERAL-SLEEP": {
        "intent": "general_health_info",
        "urgency": "routine",
        "split": "train",
        "requires_ehr": False,
        "concept_type": "none",
        "templates": [
            "How many hours of sleep each night are optimal for metabolic health?",
            "What lifestyle strategies improve sleep hygiene and reduce insomnia?",
        ],
    },
    "SF-TRAIN-GENERAL-EXERCISE": {
        "intent": "general_health_info",
        "urgency": "routine",
        "split": "train",
        "requires_ehr": False,
        "concept_type": "none",
        "templates": [
            "What are the physical activity guidelines for moderate weekly exercise?",
            "How does resistance training improve insulin sensitivity and bone density?",
        ],
    },

    # -----------------------------------------------------------------------
    # DEV FAMILIES (6 families)
    # -----------------------------------------------------------------------
    "SF-DEV-LAB-ABNORMAL": {
        "intent": "lab_result_query",
        "urgency": "soon",
        "split": "dev",
        "requires_ehr": True,
        "concept_type": "lab",
        "templates": [
            "My {lab_name} showed an elevated level of {val} {unit}. Should I retest soon?",
            "The lab marked my {lab_name} at {val} {unit} as out of range. How urgent is this?",
            "Why is my {lab_name} at {val} {unit} on my recent test panel?",
        ],
    },
    "SF-DEV-MED-MISSED-DOSE": {
        "intent": "medication_query",
        "urgency": "routine",
        "split": "dev",
        "requires_ehr": True,
        "concept_type": "med",
        "templates": [
            "I missed my morning dose of {med}. Should I take it now or wait until tomorrow?",
            "If I forgot my afternoon pill of {med}, should I double the dose at bedtime?",
        ],
    },
    "SF-DEV-SYMPTOM-HEADACHE": {
        "intent": "symptom_report",
        "urgency": "soon",
        "split": "dev",
        "requires_ehr": True,
        "concept_type": "condition",
        "templates": [
            "I've had a persistent throbbing headache since yesterday morning alongside my {condition}.",
            "My head has been aching constantly for two days. Could this be related to my {condition}?",
        ],
    },
    "SF-DEV-SYMPTOM-CHESTPAIN": {
        "intent": "symptom_report",
        "urgency": "urgent",
        "split": "dev",
        "requires_ehr": False,
        "concept_type": "none",
        "templates": [
            "I have intense tight squeezing in the middle of my chest and breaking out in cold sweat.",
            "I am gasping for air with heavy substernal chest heaviness.",
        ],
    },
    "SF-DEV-GENERAL-CHOLESTEROL": {
        "intent": "general_health_info",
        "urgency": "routine",
        "split": "dev",
        "requires_ehr": False,
        "concept_type": "none",
        "templates": [
            "What is the difference between LDL and HDL cholesterol in cardiovascular risk?",
            "What dietary fats help improve the overall cholesterol lipid profile?",
            "How often should a healthy adult have their lipid profile checked?",
        ],
    },
    "SF-DEV-GENERAL-STRESS": {
        "intent": "general_health_info",
        "urgency": "routine",
        "split": "dev",
        "requires_ehr": False,
        "concept_type": "none",
        "templates": [
            "How does chronic stress elevate cortisol and affect blood sugar control?",
            "What mindfulness techniques can help reduce physical stress responses?",
        ],
    },
    "SF-DEV-APPT-ROUTINE": {
        "intent": "followup_appointment",
        "urgency": "routine",
        "split": "dev",
        "requires_ehr": True,
        "concept_type": "condition",
        "templates": [
            "When should I schedule my next follow-up appointment for my {condition}?",
            "Do I need to come in for a routine follow-up visit to monitor my {condition}?",
            "My doctor asked me to follow up about my {condition}. How do I schedule that visit?",
        ],
    },
    "SF-DEV-APPT-SYMPTOM-REVIEW": {
        "intent": "followup_appointment",
        "urgency": "soon",
        "split": "dev",
        "requires_ehr": True,
        "concept_type": "condition",
        "templates": [
            "I need to schedule a follow-up consultation soon to review my ongoing symptoms from {condition}.",
            "Can I book a follow-up appointment next week to discuss my treatment plan for {condition}?",
        ],
    },

    # -----------------------------------------------------------------------
    # TEST FAMILIES (8 families)
    # -----------------------------------------------------------------------
    "SF-TEST-LAB-TREND": {
        "intent": "lab_result_query",
        "urgency": "routine",
        "split": "test",
        "requires_ehr": True,
        "concept_type": "lab",
        "templates": [
            "Looking at my latest {lab_name} result of {val} {unit}, how does it compare to standard targets?",
            "What steps can I take to improve my {lab_name} level from {val} {unit}?",
        ],
    },
    "SF-TEST-MED-CONTRAINDICATION": {
        "intent": "medication_query",
        "urgency": "soon",
        "split": "test",
        "requires_ehr": True,
        "concept_type": "med",
        "templates": [
            "Can I safely take decongestants or cold syrup while on {med}?",
            "Are there any prescription or OTC pain relievers contraindicated with {med}?",
        ],
    },
    "SF-TEST-SYMPTOM-DIZZINESS": {
        "intent": "symptom_report",
        "urgency": "routine",
        "split": "test",
        "requires_ehr": True,
        "concept_type": "med",
        "templates": [
            "I feel slightly lightheaded for a few moments after taking my morning {med}.",
            "I experienced mild postural dizziness shortly after taking my {med}.",
        ],
    },
    "SF-TEST-SYMPTOM-ANAPHYLAXIS": {
        "intent": "symptom_report",
        "urgency": "urgent",
        "split": "test",
        "requires_ehr": False,
        "concept_type": "none",
        "templates": [
            "My throat is closing up rapidly, lips are swelling, and I have hives everywhere.",
            "I am wheezing severely with swollen tongue and feeling like I might pass out.",
        ],
    },
    "SF-TEST-GENERAL-DIABETES": {
        "intent": "general_health_info",
        "urgency": "routine",
        "split": "test",
        "requires_ehr": False,
        "concept_type": "none",
        "templates": [
            "What is hemoglobin A1c and what level indicates prediabetes?",
            "How does physical activity immediately influence blood glucose levels?",
            "What are the typical signs and symptoms of low blood sugar hypoglycemia?",
        ],
    },
    "SF-TEST-GENERAL-HYDRATION": {
        "intent": "general_health_info",
        "urgency": "routine",
        "split": "test",
        "requires_ehr": False,
        "concept_type": "none",
        "templates": [
            "What are the early clinical signs of mild dehydration?",
            "How does adequate daily hydration protect renal function and prevent kidney stones?",
        ],
    },
    "SF-TEST-APPT-CHRONIC-CHECK": {
        "intent": "followup_appointment",
        "urgency": "routine",
        "split": "test",
        "requires_ehr": True,
        "concept_type": "condition",
        "templates": [
            "How far in advance should I book my follow-up checkup for my {condition}?",
            "Is it time for me to schedule my routine follow-up consultation for my {condition}?",
            "When is my next recommended follow-up visit regarding my {condition}?",
        ],
    },
    "SF-TEST-APPT-CLINIC-VISIT": {
        "intent": "followup_appointment",
        "urgency": "soon",
        "split": "test",
        "requires_ehr": True,
        "concept_type": "condition",
        "templates": [
            "I was advised to make a follow-up appointment within two weeks for my {condition}.",
            "Could I schedule a follow-up appointment soon to check in on my {condition}?",
        ],
    },
}


def load_patients() -> list[dict[str, Any]]:
    if not COMPLEX_PATIENTS_PATH.exists():
        raise FileNotFoundError(f"Missing {COMPLEX_PATIENTS_PATH}. Run patient_picker first.")
    with open(COMPLEX_PATIENTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        patients = data.get("patients", [])
    if not patients:
        raise ValueError(f"No patients found in {COMPLEX_PATIENTS_PATH}")
    return patients


def generate_silver_dataset(target_count: int = 3250) -> list[dict[str, Any]]:
    patients = load_patients()
    random.seed(42)

    queries = []
    gold_queries = []
    if GOLD_PATH.exists():
        with open(GOLD_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    gold_queries.append(json.loads(line).get("query_text", ""))

    print("\n" + "=" * 60)
    print(f"CarePilot AI — Generating Silver Dataset (Target: {target_count})")
    print(f"Scenario Families: {len(SCENARIO_FAMILIES)} across Train, Dev, Test")
    print(f"Alive Complex Patients Pool: {len(patients)}")
    print("=" * 60)

    per_family_target = (target_count + len(SCENARIO_FAMILIES) - 1) // len(SCENARIO_FAMILIES)
    query_counter = 1

    for sf_id, sf_info in SCENARIO_FAMILIES.items():
        family_generated = 0
        templates = sf_info["templates"]
        requires_ehr = sf_info["requires_ehr"]
        concept_type = sf_info["concept_type"]

        # To ensure grounded EHR reference, prepare patient candidates for EHR families
        attempts = 0
        while family_generated < per_family_target and attempts < 10000:
            attempts += 1
            p = random.choice(patients)
            tmpl = random.choice(templates)

            grounding_meta = {}

            if requires_ehr:
                if concept_type == "lab":
                    labs = p.get("latest_labs", [])
                    if not labs:
                        continue
                    lab_obj = random.choice(labs)
                    lab_name = clean_lab(lab_obj["description"])
                    val = lab_obj["value"]
                    unit = lab_obj.get("units") or "mg/dL"
                    filled_text = tmpl.format(lab_name=lab_name, val=val, unit=unit)
                    grounding_meta = {
                        "grounded_concept_type": "lab_result",
                        "code": lab_obj["code"],
                        "description": lab_obj["description"],
                        "value": val,
                        "units": unit,
                    }

                elif concept_type == "med":
                    meds = p.get("active_medications", [])
                    if not meds:
                        continue
                    med_obj = random.choice(meds)
                    med_name = clean_medication(med_obj["description"])
                    filled_text = tmpl.format(med=med_name)
                    grounding_meta = {
                        "grounded_concept_type": "prescription",
                        "code": med_obj["code"],
                        "description": med_obj["description"],
                    }

                elif concept_type == "condition":
                    raw_conds = p.get("active_conditions", [])
                    clinical_conds = [c for c in raw_conds if is_clinical_condition(c["description"])]
                    if not clinical_conds:
                        continue
                    cond_obj = random.choice(clinical_conds)
                    cond_name = clean_condition(cond_obj["description"])
                    filled_text = tmpl.format(condition=cond_name)
                    grounding_meta = {
                        "grounded_concept_type": "condition",
                        "code": cond_obj["code"],
                        "description": cond_obj["description"],
                    }
                else:
                    continue
                patient_id = p["patient_id"]
            else:
                filled_text = tmpl
                patient_id = None
                grounding_meta = {
                    "grounded_concept_type": "none",
                }

            # Check similarity with Gold scripted candidate set to avoid cross-tier leakage
            is_dup = False
            for gq in gold_queries:
                if fuzz.ratio(filled_text.lower(), gq.lower()) > 88:
                    is_dup = True
                    break

            if is_dup:
                continue

            query_item = {
                "query_id": f"S-{query_counter:05d}",
                "tier": "silver",
                "split": sf_info["split"],
                "scenario_family": sf_id,
                "query_text": filled_text,
                "intent_label": sf_info["intent"],
                "urgency_label": sf_info["urgency"],
                "requires_patient_context": requires_ehr,
                "patient_id": patient_id,
                "grounded_ehr_concept": grounding_meta,
                "generation_model": "synthetic_rule_instantiator_v2",
            }

            queries.append(query_item)
            query_counter += 1
            family_generated += 1

    SILVER_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SILVER_OUTPUT_PATH, "w", encoding="utf-8") as f:
        for q in queries:
            f.write(json.dumps(q) + "\n")

    total = len(queries)
    train_count = sum(1 for q in queries if q["split"] == "train")
    dev_count = sum(1 for q in queries if q["split"] == "dev")
    test_count = sum(1 for q in queries if q["split"] == "test")
    no_ehr_count = sum(1 for q in queries if not q["requires_patient_context"])
    ehr_count = sum(1 for q in queries if q["requires_patient_context"])

    print(f"\n[OK] Generated {total} silver queries across {len(SCENARIO_FAMILIES)} families:")
    print(f"  Train: {train_count} ({train_count/total*100:.1f}%)")
    print(f"  Dev:   {dev_count} ({dev_count/total*100:.1f}%)")
    print(f"  Test:  {test_count} ({test_count/total*100:.1f}%)")
    print(f"  Requires EHR: {ehr_count} ({ehr_count/total*100:.1f}%)")
    print(f"  No EHR needed: {no_ehr_count} ({no_ehr_count/total*100:.1f}%) [Requirement >= 30%]")
    print(f"Saved to: {SILVER_OUTPUT_PATH}")
    print("=" * 60)

    return queries


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Silver dataset")
    parser.add_argument("--count", type=int, default=3770, help="Target total query count")
    args = parser.parse_args()
    generate_silver_dataset(target_count=args.count)
