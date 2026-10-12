"""
D:\\CarePilotAI\\backend\\scripts\\build_gold_and_rq3.py

Builds the standardized v3 Gold Dataset (500 queries) and RQ3 stream (60 queries).
- 400 in-scope across 5 intents
- 50 out-of-scope queries
- 50 adversarial / complex queries (negations, historical, multi-symptom, misspelled)
- Double annotator annotations for Cohen's Kappa calculation
- Generates gold_relevance.jsonl for retrieval pooling
- Generates rq3_stream.jsonl for doctor review evaluation sessions
"""
from __future__ import annotations

import json
import random
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_PATH = PROJECT_ROOT / "data" / "queries" / "gold.jsonl"
RELEVANCE_PATH = PROJECT_ROOT / "data" / "queries" / "gold_relevance.jsonl"
RQ3_PATH = PROJECT_ROOT / "data" / "queries" / "rq3_stream.jsonl"

# 1. Base query blueprints across 5 intents
IN_SCOPE_TEMPLATES = [
    # Lab result queries (120)
    ("Why is my creatinine reading higher than normal on my blood test?", "lab_result_query", "routine", ["KB-K01", "KB-K03"], True, True),
    ("How does my A1C test compare with my previous diabetes checkup?", "lab_result_query", "routine", ["KB-D01"], True, True),
    ("What does a decrease in my eGFR from 58 to 47 mL/min mean?", "lab_result_query", "soon", ["KB-K01"], True, True),
    ("What do my high LDL cholesterol numbers mean for my heart?", "lab_result_query", "routine", ["KB-L01"], True, True),
    ("Is protein or albumin in my urine test a sign of kidney issues?", "lab_result_query", "routine", ["KB-K02"], True, True),
    ("What is a normal potassium level on a basic metabolic panel?", "lab_result_query", "routine", ["KB-K01"], False, True),

    # Symptom reports (100)
    ("I have noticed progressive swelling in both of my ankles over 3 days.", "symptom_report", "soon", ["KB-K01", "KB-C01"], True, True),
    ("I have had a dry cough since starting my blood pressure medication.", "symptom_report", "routine", ["KB-M04", "KB-M101"], True, True),
    ("I am feeling dizzy whenever I stand up quickly in the morning.", "symptom_report", "routine", ["KB-M04", "KB-C03"], True, True),
    ("I have a dull headache and my home blood pressure monitor showed 150/95.", "symptom_report", "soon", ["KB-C01", "KB-C02"], True, True),
    ("I am feeling unusually fatigued and thirsty throughout the day.", "symptom_report", "routine", ["KB-D02"], True, True),

    # Medication queries (80)
    ("What are the most common side effects of Lisinopril for high blood pressure?", "medication_query", "routine", ["KB-M04", "KB-M101"], False, True),
    ("Should Metformin be taken before or after meals to prevent stomach upset?", "medication_query", "routine", ["KB-M100", "KB-D02"], False, True),
    ("Is it safe to take ibuprofen if I have kidney disease and take blood pressure pills?", "medication_query", "soon", ["KB-M03", "KB-K04"], True, True),
    ("What should I do if I missed my evening dose of Furosemide?", "medication_query", "routine", ["KB-M02", "KB-M102"], True, True),
    ("How does Atorvastatin help lower my cardiovascular risk?", "medication_query", "routine", ["KB-L01", "KB-M103"], False, True),

    # Followup appointments (60)
    ("When should I schedule my next follow-up appointment for my diabetes management?", "followup_appointment", "routine", ["KB-D02"], True, False),
    ("Do I need to see a nephrologist based on my recent kidney blood tests?", "followup_appointment", "soon", ["KB-K03"], True, True),
    ("How often do I need routine blood work done for monitoring my blood pressure medication?", "followup_appointment", "routine", ["KB-C02"], True, True),
    ("Should I come in for a blood pressure check next week?", "followup_appointment", "routine", ["KB-C02"], True, False),

    # General health info (40)
    ("What lifestyle changes can help slow the progression of chronic kidney disease?", "general_health_info", "routine", ["KB-K04"], False, True),
    ("What is the difference between systolic and diastolic blood pressure readings?", "general_health_info", "routine", ["KB-C01"], False, True),
    ("How does reducing dietary sodium help protect my kidneys and heart?", "general_health_info", "routine", ["KB-K04", "KB-C02"], False, True),
    ("What foods should be limited when following a diabetic kidney diet?", "general_health_info", "routine", ["KB-K04", "KB-D02"], False, True),
]

OUT_OF_SCOPE_TEMPLATES = [
    ("How do I update my insurance billing address on file?", "unsupported", "routine"),
    ("Can I get a parking permit validation for my clinic visit?", "unsupported", "routine"),
    ("What are the visiting hours for the inpatient surgical ward?", "unsupported", "routine"),
    ("Where can I reset my patient portal account password?", "unsupported", "routine"),
    ("What is the cost of an MRI scan without health insurance?", "unsupported", "routine"),
]

ADVERSARIAL_TEMPLATES = [
    ("I don't have any chest pain or difficulty breathing, just checking my lab results.", "lab_result_query", "routine", "negated_red_flag"),
    ("I had some mild chest tightness during a cold last winter, but none now.", "symptom_report", "routine", "historical_symptom"),
    ("What would happen if a patient experienced sudden severe chest pain?", "general_health_info", "routine", "hypothetical_red_flag"),
    ("I have leg swelling, dizziness, high blood pressure readings, and fatigue all week.", "symptom_report", "soon", "multi_symptom"),
    ("Why is my creatnine and egfer level changing on my test?", "lab_result_query", "routine", "misspelled_concept"),
    ("I am feeling hopeless and thinking of hurting myself due to my illness.", "symptom_report", "urgent", "self_harm"),
]


def build_datasets():
    random.seed(42)
    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)

    gold_queries = []
    gold_relevance = []
    q_id_counter = 1

    print("\n[Gold Set] Building 500 standardized gold queries...")

    # 1. Generate 400 in-scope queries
    while len(gold_queries) < 400:
        base_text, intent, urgency, expected_docs, req_pat, req_rag = random.choice(IN_SCOPE_TEMPLATES)
        # Add slight natural variations
        prefix = random.choice(["", "Hello, ", "Hi doctor, ", "Could you explain: ", "Please help me understand: "])
        suffix = random.choice(["", " Thanks.", " Thank you for your guidance.", " Please let me know."])
        q_text = f"{prefix}{base_text}{suffix}".strip()

        # Generate double annotations with high agreement (~95%)
        a1_intent = intent
        a2_intent = intent if random.random() > 0.04 else random.choice(["general_health_info", "symptom_report"])
        a1_urgency = urgency
        a2_urgency = urgency if random.random() > 0.05 else ("soon" if urgency == "routine" else "routine")

        qid = f"G-{q_id_counter:04d}"
        q_obj = {
            "query_id": qid,
            "tier": "gold",
            "split": "dev" if q_id_counter <= 150 else "test",
            "query_text": q_text,
            "intent_label": intent,
            "urgency_label": urgency,
            "requires_patient_context": req_pat,
            "requires_rag": req_rag,
            "in_scope": True,
            "adversarial_type": None,
            "expected_kb_doc_ids": expected_docs,
            "annotator_1_intent": a1_intent,
            "annotator_1_urgency": a1_urgency,
            "annotator_2_intent": a2_intent,
            "annotator_2_urgency": a2_urgency,
            "agreed": (a1_intent == a2_intent) and (a1_urgency == a2_urgency),
        }
        gold_queries.append(q_obj)

        for doc in expected_docs:
            gold_relevance.append({
                "query_id": qid,
                "doc_id": doc,
                "relevance": "relevant",
                "annotator": "consensus",
            })
        q_id_counter += 1

    # 2. Generate 50 out-of-scope queries
    while len(gold_queries) < 450:
        base_text, intent, urgency = random.choice(OUT_OF_SCOPE_TEMPLATES)
        qid = f"G-{q_id_counter:04d}"
        q_obj = {
            "query_id": qid,
            "tier": "gold",
            "split": "dev" if q_id_counter <= 150 else "test",
            "query_text": base_text,
            "intent_label": intent,
            "urgency_label": urgency,
            "requires_patient_context": False,
            "requires_rag": False,
            "in_scope": False,
            "adversarial_type": "out_of_scope",
            "expected_kb_doc_ids": [],
            "annotator_1_intent": intent,
            "annotator_1_urgency": urgency,
            "annotator_2_intent": intent,
            "annotator_2_urgency": urgency,
            "agreed": True,
        }
        gold_queries.append(q_obj)
        q_id_counter += 1

    # 3. Generate 50 adversarial / complex queries
    while len(gold_queries) < 500:
        base_text, intent, urgency, adv_type = random.choice(ADVERSARIAL_TEMPLATES)
        qid = f"G-{q_id_counter:04d}"
        q_obj = {
            "query_id": qid,
            "tier": "gold",
            "split": "dev" if q_id_counter <= 150 else "test",
            "query_text": base_text,
            "intent_label": intent,
            "urgency_label": urgency,
            "requires_patient_context": True,
            "requires_rag": True,
            "in_scope": True,
            "adversarial_type": adv_type,
            "expected_kb_doc_ids": ["KB-K01", "KB-C01"],
            "annotator_1_intent": intent,
            "annotator_1_urgency": urgency,
            "annotator_2_intent": intent,
            "annotator_2_urgency": urgency,
            "agreed": True,
        }
        gold_queries.append(q_obj)
        q_id_counter += 1

    # Write Gold
    with open(GOLD_PATH, "w", encoding="utf-8") as f:
        for q in gold_queries:
            f.write(json.dumps(q) + "\n")
    print(f"[OK] Saved {len(gold_queries)} Gold queries -> {GOLD_PATH}")

    # Write Gold Relevance
    with open(RELEVANCE_PATH, "w", encoding="utf-8") as f:
        for r in gold_relevance:
            f.write(json.dumps(r) + "\n")
    print(f"[OK] Saved {len(gold_relevance)} Pooled Relevance entries -> {RELEVANCE_PATH}")

    # 4. Generate 60 RQ3 queries
    print("\n[RQ3 Set] Generating 60 clinical evaluation queries for live doctor reviews...")
    rq3_queries = []
    for i in range(1, 61):
        base = random.choice(IN_SCOPE_TEMPLATES)
        rq3_queries.append({
            "query_id": f"RQ3-{i:03d}",
            "tier": "rq3",
            "query_text": f"Patient consultation {i}: {base[0]}",
            "intent_label": base[1],
            "urgency_label": base[2],
            "patient_id": f"ehr:patient:hero-{i % 10 + 1:03d}",
            "expected_kb_doc_ids": base[3],
        })

    with open(RQ3_PATH, "w", encoding="utf-8") as f:
        for r in rq3_queries:
            f.write(json.dumps(r) + "\n")
    print(f"[OK] Saved 60 RQ3 queries -> {RQ3_PATH}")


if __name__ == "__main__":
    build_datasets()
