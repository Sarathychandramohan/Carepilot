import json
from pathlib import Path

BASE_DIR = Path(r".\rag_knowledge")
OUTPUT_PATH = BASE_DIR / "manifest" / "gold_questions.json"

questions = [
    # ------------------------------------------------------------
    # REPORT QUERY — 8
    # ------------------------------------------------------------
    {
        "question_id": "R01",
        "question": "Has my A1C increased compared with my previous result?",
        "intent": "report_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-D01"]
    },
    {
        "question_id": "R02",
        "question": "How has my creatinine changed between my recent tests?",
        "intent": "report_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-K01"]
    },
    {
        "question_id": "R03",
        "question": "Can you compare my recent kidney test results?",
        "intent": "report_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-K01", "KB-K02"]
    },
    {
        "question_id": "R04",
        "question": "What does my recent eGFR result tell me?",
        "intent": "report_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-K01"]
    },
    {
        "question_id": "R05",
        "question": "What does my urine protein result mean?",
        "intent": "report_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-K02"]
    },
    {
        "question_id": "R06",
        "question": "Has my cholesterol changed compared with my earlier result?",
        "intent": "report_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-L01"]
    },
    {
        "question_id": "R07",
        "question": "What do my LDL and HDL results mean?",
        "intent": "report_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-L01"]
    },
    {
        "question_id": "R08",
        "question": "What does my hemoglobin result mean?",
        "intent": "report_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-B01", "KB-B02"]
    },

    # ------------------------------------------------------------
    # MEDICATION QUERY — 6
    # ------------------------------------------------------------
    {
        "question_id": "M01",
        "question": "Why am I taking this medication?",
        "intent": "medication_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-M01", "KB-M02", "KB-M04"]
    },
    {
        "question_id": "M02",
        "question": "Why was my medication changed?",
        "intent": "medication_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-M01", "KB-M02", "KB-M04"]
    },
    {
        "question_id": "M03",
        "question": "I feel dizzy after starting my new medication. What should I know?",
        "intent": "medication_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-M03", "KB-M01"]
    },
    {
        "question_id": "M04",
        "question": "What is this medication generally used for?",
        "intent": "medication_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-M04"]
    },
    {
        "question_id": "M05",
        "question": "Can you check which medications I am currently taking?",
        "intent": "medication_query",
        "requires_patient_context": True,
        "requires_rag": False,
        "expected_document_ids": []
    },
    {
        "question_id": "M06",
        "question": "What common safety information should I know about taking my medicines?",
        "intent": "medication_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-M01", "KB-M02", "KB-M03"]
    },

    # ------------------------------------------------------------
    # SYMPTOM QUERY — 6
    # ------------------------------------------------------------
    {
        "question_id": "S01",
        "question": "I have chest tightness. What should I know?",
        "intent": "symptom_query",
        "requires_patient_context": False,
        "requires_rag": True,
        "expected_document_ids": ["KB-C01"]
    },
    {
        "question_id": "S02",
        "question": "My ankles are swelling. What could this be related to?",
        "intent": "symptom_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-C01", "KB-K04"]
    },
    {
        "question_id": "S03",
        "question": "I have been feeling more tired recently. What should I know?",
        "intent": "symptom_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-B01", "KB-B02"]
    },
    {
        "question_id": "S04",
        "question": "My rash seems to be getting worse. What should I know?",
        "intent": "symptom_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-M03"]
    },
    {
        "question_id": "S05",
        "question": "I have been dizzy since starting my new prescription. What should I know?",
        "intent": "symptom_query",
        "requires_patient_context": True,
        "requires_rag": True,
        "expected_document_ids": ["KB-M03", "KB-M01"]
    },
    {
        "question_id": "S06",
        "question": "I have a sore throat and cough. What should I know?",
        "intent": "symptom_query",
        "requires_patient_context": False,
        "requires_rag": False,
        "expected_document_ids": []
    },

    # ------------------------------------------------------------
    # APPOINTMENT REQUEST — 2
    # ------------------------------------------------------------
    {
        "question_id": "A01",
        "question": "I would like a follow-up appointment to discuss my recent blood work.",
        "intent": "appointment_request",
        "requires_patient_context": True,
        "requires_rag": False,
        "expected_document_ids": []
    },
    {
        "question_id": "A02",
        "question": "Can I get an earlier appointment because of my recent results?",
        "intent": "appointment_request",
        "requires_patient_context": True,
        "requires_rag": False,
        "expected_document_ids": []
    },

    # ------------------------------------------------------------
    # FOLLOW-UP — 2
    # ------------------------------------------------------------
    {
        "question_id": "F01",
        "question": "Can we continue our previous conversation about my medication?",
        "intent": "follow_up",
        "requires_patient_context": True,
        "requires_rag": False,
        "expected_document_ids": []
    },
    {
        "question_id": "F02",
        "question": "Can you update me on the issue we discussed previously?",
        "intent": "follow_up",
        "requires_patient_context": True,
        "requires_rag": False,
        "expected_document_ids": []
    },

    # ------------------------------------------------------------
    # GENERAL RAG SANITY — 6
    # ------------------------------------------------------------
    {
        "question_id": "G01",
        "question": "What is an A1C test?",
        "intent": "report_query",
        "requires_patient_context": False,
        "requires_rag": True,
        "expected_document_ids": ["KB-D01"]
    },
    {
        "question_id": "G02",
        "question": "What is eGFR and how is it used?",
        "intent": "report_query",
        "requires_patient_context": False,
        "requires_rag": True,
        "expected_document_ids": ["KB-K01"]
    },
    {
        "question_id": "G03",
        "question": "What is albuminuria?",
        "intent": "report_query",
        "requires_patient_context": False,
        "requires_rag": True,
        "expected_document_ids": ["KB-K02"]
    },
    {
        "question_id": "G04",
        "question": "What do LDL and HDL cholesterol mean?",
        "intent": "report_query",
        "requires_patient_context": False,
        "requires_rag": True,
        "expected_document_ids": ["KB-L01"]
    },
    {
        "question_id": "G05",
        "question": "What is chronic kidney disease?",
        "intent": "symptom_query",
        "requires_patient_context": False,
        "requires_rag": True,
        "expected_document_ids": ["KB-K01", "KB-K03", "KB-K04"]
    },
    {
        "question_id": "G06",
        "question": "What is hypertension?",
        "intent": "symptom_query",
        "requires_patient_context": False,
        "requires_rag": True,
        "expected_document_ids": ["KB-C01", "KB-C02"]
    }
]

primary_questions = [
    q for q in questions
    if q["question_id"].startswith(("R", "M", "S", "A", "F"))
]

rag_workflow_questions = [
    q for q in primary_questions
    if q["requires_rag"]
]

general_questions = [
    q for q in questions
    if q["question_id"].startswith("G")
]

data = {
    "gold_set_version": "1.0",
    "created_date": "2026-09-18",
    "total_questions": len(questions),
    "workflow_question_count": len(primary_questions),
    "general_rag_sanity_count": len(general_questions),

    "evaluation_rules": {
        "primary_metric": "Hit@5",
        "primary_denominator": (
            "workflow questions where requires_rag=true"
        ),
        "primary_denominator_count": len(rag_workflow_questions),
        "excluded_from_primary_metric": (
            "workflow questions where requires_rag=false"
        ),
        "general_rag_metric": (
            "Report Hit@5 separately for the 6 general RAG "
            "sanity questions; do not include them in the "
            "primary denominator."
        ),
        "expected_document_rule": (
            "A retrieval result counts as a hit when at least "
            "one expected_document_id appears within the top-5 "
            "retrieved chunks."
        )
    },

    "questions": questions
}

OUTPUT_PATH.write_text(
    json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

print("=" * 70)
print("CAREPILOT AI — GOLD QUESTION SET")
print("=" * 70)
print(f"Total questions              : {len(questions)}")
print(f"Workflow questions           : {len(primary_questions)}")
print(f"Workflow requires RAG        : {len(rag_workflow_questions)}")
print(f"Workflow excludes from Hit@5: {len(primary_questions) - len(rag_workflow_questions)}")
print(f"General RAG sanity questions : {len(general_questions)}")
print()
print(f"Saved: {OUTPUT_PATH}")
print()
print("PRIMARY Hit@5 denominator:")
print(
    f"  {len(rag_workflow_questions)} workflow questions "
    f"with requires_rag=true"
)
print()
print("Gold set finalized BEFORE retrieval tuning.")
