"""
D:\\CarePilotAI\\backend\\scripts\\generate_rq3_stream.py

Generates 60 clinical evaluation queries (12 per intent across 5 intents)
for the RQ3 evaluation stream.
Every patient-specific query is grounded in real EHR data from carepilot_v3 alive patients.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPLEX_PATIENTS_PATH = PROJECT_ROOT / "data" / "manifests" / "complex_patients.json"
RQ3_OUTPUT_PATH = PROJECT_ROOT / "data" / "queries" / "rq3_stream.jsonl"


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


def clean_lab(desc: str) -> str:
    d = re.sub(r"\s*\[.*?\]", "", desc)
    d = re.sub(r"\s+in\s+.*", "", d, flags=re.IGNORECASE)
    d = d.strip()
    return d if d else desc


TEMPLATES_BY_INTENT = {
    "symptom_report": [
        ("I have noticed persistent swelling in my legs and ankles since my diagnosis of {condition}.", "soon", "condition"),
        ("I have had occasional mild dizziness after taking my {med}.", "routine", "med"),
        ("I am experiencing severe pressure in my chest and trouble breathing.", "urgent", "none"),
        ("I have developed a dry persistent cough after starting {med}.", "routine", "med"),
    ],
    "medication_query": [
        ("Can you tell me if {med} commonly causes morning nausea or fatigue?", "routine", "med"),
        ("Is it safe to take an over-the-counter pain reliever while on {med}?", "soon", "med"),
        ("What is the best time of day to take my {med} prescription?", "routine", "med"),
        ("If I accidentally missed my scheduled dose of {med}, what should I do?", "routine", "med"),
    ],
    "lab_result_query": [
        ("My recent {lab_name} result came back at {val} {unit}. Is that within expected limits?", "routine", "lab"),
        ("Why is my {lab_name} level marked abnormal at {val} {unit}?", "soon", "lab"),
        ("What should my target range be for {lab_name} given my overall health history?", "routine", "lab"),
        ("Should I have my {lab_name} re-tested after my recent reading of {val} {unit}?", "routine", "lab"),
    ],
    "followup_appointment": [
        ("When should I schedule my next follow-up appointment to monitor my {condition}?", "routine", "condition"),
        ("Do I need to come in for an in-person doctor visit to check on my {med}?", "routine", "med"),
        ("Should I schedule an appointment with a specialist for my {condition}?", "soon", "condition"),
        ("How often do I need follow-up lab work done for my {condition}?", "routine", "condition"),
    ],
    "general_health_info": [
        ("What dietary recommendations are most beneficial for managing {condition}?", "routine", "condition"),
        ("What are the key lifestyle habits that help slow the progression of {condition}?", "routine", "condition"),
        ("How does regular hydration and physical activity help someone with {condition}?", "routine", "condition"),
        ("Are there specific exercises recommended for patients diagnosed with {condition}?", "routine", "condition"),
    ]
}


def generate_rq3():
    with open(COMPLEX_PATIENTS_PATH, "r", encoding="utf-8") as f:
        patients = json.load(f)["patients"]

    random.seed(123)
    intents = ["symptom_report", "medication_query", "lab_result_query", "followup_appointment", "general_health_info"]
    rq3_queries = []
    q_counter = 1

    for intent in intents:
        tmpl_list = TEMPLATES_BY_INTENT[intent]
        for j in range(12):
            tmpl, urgency, ctype = tmpl_list[j % len(tmpl_list)]
            p = random.choice(patients)
            pid = p["patient_id"]
            grounding = {"concept_type": ctype}

            if ctype == "lab":
                lab = random.choice(p["latest_labs"])
                lname = clean_lab(lab["description"])
                val = lab["value"]
                unit = lab.get("units") or "mg/dL"
                qtext = tmpl.format(lab_name=lname, val=val, unit=unit)
                grounding["code"] = lab["code"]
                grounding["description"] = lab["description"]
                grounding["value"] = val
                grounding["units"] = unit
                req_ehr = True
            elif ctype == "med":
                med = random.choice(p["active_medications"])
                mname = clean_medication(med["description"])
                qtext = tmpl.format(med=mname)
                grounding["code"] = med["code"]
                grounding["description"] = med["description"]
                req_ehr = True
            elif ctype == "condition":
                cond = random.choice(p["active_conditions"])
                cname = clean_condition(cond["description"])
                qtext = tmpl.format(condition=cname)
                grounding["code"] = cond["code"]
                grounding["description"] = cond["description"]
                req_ehr = True
            else:
                qtext = tmpl
                pid = None
                req_ehr = False

            rq3_queries.append({
                "query_id": f"RQ3-{q_counter:03d}",
                "tier": "rq3_stream",
                "intent_label": intent,
                "urgency_label": urgency,
                "requires_patient_context": req_ehr,
                "patient_id": pid,
                "query_text": qtext,
                "grounded_ehr_concept": grounding,
            })
            q_counter += 1

    RQ3_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RQ3_OUTPUT_PATH, "w", encoding="utf-8") as f:
        for q in rq3_queries:
            f.write(json.dumps(q) + "\n")

    print(f"[OK] Generated {len(rq3_queries)} RQ3 stream queries across 5 intents (12 per intent).")
    print(f"Saved to: {RQ3_OUTPUT_PATH}")


if __name__ == "__main__":
    generate_rq3()
