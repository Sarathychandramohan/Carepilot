"""
backend/tests/test_failure_guards.py

Unit and regression tests verifying validation rules and failure guards
in backend/eval/import_synthetic_gold.py:
  1. Missing required fields (scenario_id, patient_id, query_text, referenced_fact)
  2. Missing or invalid split ('dev' or 'test')
  3. Unknown patient_id (not in context_packs.jsonl)
  4. Ungrounded referenced_fact (not found in patient's pack)
  5. Invalid intent enum (not in real intent enum)
  6. Invalid urgency enum (not in real urgency enum)
  7. Near-duplicate query (cosine >= 0.70 using BAAI/bge-small-en-v1.5)
  8. Scenario spanning dev/test splits
  9. Valid fixture import success
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.eval.import_synthetic_gold import validate_and_import_synthetic_gold

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTEXT_PACKS_PATH = PROJECT_ROOT / "data" / "annotation" / "context_packs.jsonl"


@pytest.fixture
def tmp_jsonl(tmp_path: Path):
    def _create(rows: list[dict]):
        p = tmp_path / "candidates.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return p

    return _create


def test_missing_required_field(tmp_jsonl, tmp_path):
    fpath = tmp_jsonl([
        {
            "scenario_id": "S0001",
            "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
            "intent": "medication_query",
            "urgency": "urgent",
            "referenced_fact": "Furosemide",
            "split": "dev",
        }
    ])
    out_p = tmp_path / "out.jsonl"
    with pytest.raises(ValueError, match=r"Missing required field 'query_text'"):
        validate_and_import_synthetic_gold(fpath, out_p, CONTEXT_PACKS_PATH)


def test_missing_or_invalid_split(tmp_jsonl, tmp_path):
    fpath = tmp_jsonl([
        {
            "scenario_id": "S0001",
            "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
            "query_text": "What about my medication?",
            "intent": "medication_query",
            "urgency": "urgent",
            "referenced_fact": "Furosemide",
            "split": "invalid_split",
        }
    ])
    out_p = tmp_path / "out.jsonl"
    with pytest.raises(ValueError, match=r"Required field 'split' must be 'dev' or 'test'"):
        validate_and_import_synthetic_gold(fpath, out_p, CONTEXT_PACKS_PATH)


def test_unknown_patient_id(tmp_jsonl, tmp_path):
    fpath = tmp_jsonl([
        {
            "scenario_id": "S0001",
            "patient_id": "unknown-patient-uuid-99999",
            "query_text": "What about my medication?",
            "intent": "medication_query",
            "urgency": "urgent",
            "referenced_fact": "Furosemide",
            "split": "dev",
        }
    ])
    out_p = tmp_path / "out.jsonl"
    with pytest.raises(ValueError, match=r"Unknown Patient ID"):
        validate_and_import_synthetic_gold(fpath, out_p, CONTEXT_PACKS_PATH)


def test_ungrounded_referenced_fact(tmp_jsonl, tmp_path):
    fpath = tmp_jsonl([
        {
            "scenario_id": "S0001",
            "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
            "query_text": "How should I take my Paclitaxel infusion?",
            "intent": "medication_query",
            "urgency": "urgent",
            "referenced_fact": "Chemotherapy Paclitaxel",
            "split": "dev",
        }
    ])
    out_p = tmp_path / "out.jsonl"
    with pytest.raises(ValueError, match=r"Ungrounded Fact"):
        validate_and_import_synthetic_gold(fpath, out_p, CONTEXT_PACKS_PATH)


def test_invalid_intent_enum(tmp_jsonl, tmp_path):
    fpath = tmp_jsonl([
        {
            "scenario_id": "S0001",
            "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
            "query_text": "What should I do if I missed my morning dose of Furosemide?",
            "intent": "billing_insurance_query",
            "urgency": "urgent",
            "referenced_fact": "Furosemide",
            "split": "dev",
        }
    ])
    out_p = tmp_path / "out.jsonl"
    with pytest.raises(ValueError, match=r"Invalid Intent"):
        validate_and_import_synthetic_gold(fpath, out_p, CONTEXT_PACKS_PATH)


def test_invalid_urgency_enum(tmp_jsonl, tmp_path):
    fpath = tmp_jsonl([
        {
            "scenario_id": "S0001",
            "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
            "query_text": "What should I do if I missed my morning dose of Furosemide?",
            "intent": "medication_query",
            "urgency": "immediate_emergency",
            "referenced_fact": "Furosemide",
            "split": "dev",
        }
    ])
    out_p = tmp_path / "out.jsonl"
    with pytest.raises(ValueError, match=r"Invalid Urgency"):
        validate_and_import_synthetic_gold(fpath, out_p, CONTEXT_PACKS_PATH)


def test_near_duplicate_query_cosine(tmp_jsonl, tmp_path):
    fpath = tmp_jsonl([
        {
            "scenario_id": "S0001",
            "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
            "query_text": "What should I do if I missed my morning dose of Furosemide?",
            "intent": "medication_query",
            "urgency": "urgent",
            "referenced_fact": "Furosemide",
            "split": "dev",
        },
        {
            "scenario_id": "S0002",
            "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
            "query_text": "Hello doctor, what should I do if I missed my morning dose of Furosemide? Thanks",
            "intent": "medication_query",
            "urgency": "urgent",
            "referenced_fact": "Furosemide",
            "split": "dev",
        },
    ])
    out_p = tmp_path / "out.jsonl"
    with pytest.raises(ValueError, match=r"Near-Duplicate Query"):
        validate_and_import_synthetic_gold(fpath, out_p, CONTEXT_PACKS_PATH)


def test_scenario_spanning_dev_test(tmp_jsonl, tmp_path):
    fpath = tmp_jsonl([
        {
            "scenario_id": "S0001",
            "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
            "query_text": "What should I do if I missed my morning dose of Furosemide?",
            "intent": "medication_query",
            "urgency": "urgent",
            "referenced_fact": "Furosemide",
            "split": "dev",
        },
        {
            "scenario_id": "S0001",
            "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
            "query_text": "Can you explain my recent glucose test result of 95.3 mg/dL?",
            "intent": "lab_result_query",
            "urgency": "routine",
            "referenced_fact": "Glucose",
            "split": "test",
        },
    ])
    out_p = tmp_path / "out.jsonl"
    with pytest.raises(ValueError, match=r"Scenario Spanning Dev/Test"):
        validate_and_import_synthetic_gold(fpath, out_p, CONTEXT_PACKS_PATH)


def test_valid_3row_fixture(tmp_jsonl, tmp_path):
    fpath = tmp_jsonl([
        {
            "scenario_id": "S0001",
            "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
            "query_text": "What should I do if I missed my morning dose of Furosemide?",
            "intent": "medication_query",
            "urgency": "urgent",
            "referenced_fact": "Furosemide",
            "split": "dev",
        },
        {
            "scenario_id": "S0002",
            "patient_id": "070cf91b-f623-772b-48f4-4088b69516f6",
            "query_text": "Can you explain my recent glucose test result of 98.2 mg/dL?",
            "intent": "lab_result_query",
            "urgency": "routine",
            "referenced_fact": "Glucose",
            "split": "test",
        },
        {
            "scenario_id": "S0003",
            "patient_id": "0b490094-beb0-b779-72b1-4cadb10c19ce",
            "query_text": "I have been experiencing a persistent productive cough since my acute bronchitis diagnosis.",
            "intent": "symptom_report",
            "urgency": "soon",
            "referenced_fact": "Acute bronchitis",
            "split": "test",
        },
    ])
    out_p = tmp_path / "out.jsonl"
    results = validate_and_import_synthetic_gold(fpath, out_p, CONTEXT_PACKS_PATH)
    assert len(results) == 3
    assert out_p.exists()
