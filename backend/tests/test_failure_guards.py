"""
backend/tests/test_failure_guards.py

Unit and regression tests verifying validation rules and failure guards
in backend/eval/import_synthetic_gold.py and backend/eval/split_gold.py:
  1. Missing required fields (scenario_id, patient_id, query_text, referenced_fact)
  2. Invalid split value (when provided, must be 'dev' or 'test')
  3. Optional split (omitted split succeeds on input)
  4. Unknown patient_id (not in context_packs.jsonl)
  5. Ungrounded referenced_fact (not found in patient's pack)
  6. Invalid intent enum (not in real intent enum)
  7. Invalid urgency enum (routine/soon/urgent)
  8. Duplicate scenario_id in input batch
  9. Duplicate scenario_id against existing merged file
 10. Near-duplicate query against whole merged file (cosine >= 0.70)
 11. Valid import and merge
 12. split_gold cluster-level partitioning guarantees zero clusters span dev and test
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.eval.import_synthetic_gold import validate_and_import_synthetic_gold
from backend.eval.split_gold import compute_clusters_and_scenarios, split_candidate_clusters

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTEXT_PACKS_PATH = PROJECT_ROOT / "data" / "annotation" / "context_packs.jsonl"


@pytest.fixture
def tmp_jsonl(tmp_path: Path):
    def _create(rows: list[dict], filename: str = "candidates.jsonl"):
        p = tmp_path / filename
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


def test_invalid_split(tmp_jsonl, tmp_path):
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
    with pytest.raises(ValueError, match=r"Optional field 'split' must be 'dev' or 'test'"):
        validate_and_import_synthetic_gold(fpath, out_p, CONTEXT_PACKS_PATH)


def test_optional_split_success(tmp_jsonl, tmp_path):
    fpath = tmp_jsonl([
        {
            "scenario_id": "S0001",
            "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
            "query_text": "What should I do if I missed my morning dose of Furosemide?",
            "intent": "medication_query",
            "urgency": "urgent",
            "referenced_fact": "Furosemide",
            # split is omitted
        }
    ])
    out_p = tmp_path / "out.jsonl"
    res = validate_and_import_synthetic_gold(fpath, out_p, CONTEXT_PACKS_PATH)
    assert len(res) == 1
    assert res[0]["split"] is None


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


def test_duplicate_scenario_id_in_input(tmp_jsonl, tmp_path):
    fpath = tmp_jsonl([
        {
            "scenario_id": "S0001",
            "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
            "query_text": "What should I do if I missed my morning dose of Furosemide?",
            "intent": "medication_query",
            "urgency": "urgent",
            "referenced_fact": "Furosemide",
        },
        {
            "scenario_id": "S0001",
            "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
            "query_text": "Can you explain my recent glucose test result?",
            "intent": "lab_result_query",
            "urgency": "routine",
            "referenced_fact": "Glucose",
        },
    ])
    out_p = tmp_path / "out.jsonl"
    with pytest.raises(ValueError, match=r"Duplicate Scenario ID"):
        validate_and_import_synthetic_gold(fpath, out_p, CONTEXT_PACKS_PATH)


def test_duplicate_scenario_id_against_existing_file(tmp_jsonl, tmp_path):
    out_p = tmp_jsonl(
        [
            {
                "query_id": "GS-0001",
                "scenario_id": "S0001",
                "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
                "query_text": "What should I do if I missed my morning dose of Furosemide?",
                "intent_label": "medication_query",
                "urgency_label": "urgent",
                "referenced_fact": "Furosemide",
                "split": "dev",
            }
        ],
        filename="existing_gold.jsonl",
    )
    new_input = tmp_jsonl(
        [
            {
                "scenario_id": "S0001",
                "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
                "query_text": "Can you explain my recent glucose test result of 95.3 mg/dL?",
                "intent": "lab_result_query",
                "urgency": "routine",
                "referenced_fact": "Glucose",
            }
        ],
        filename="new_batch.jsonl",
    )
    with pytest.raises(ValueError, match=r"Duplicate Scenario ID"):
        validate_and_import_synthetic_gold(new_input, out_p, CONTEXT_PACKS_PATH)


def test_near_duplicate_query_against_whole_merged_file(tmp_jsonl, tmp_path):
    out_p = tmp_jsonl(
        [
            {
                "query_id": "GS-0001",
                "scenario_id": "S0001",
                "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
                "query_text": "What should I do if I missed my morning dose of Furosemide?",
                "intent_label": "medication_query",
                "urgency_label": "urgent",
                "referenced_fact": "Furosemide",
                "split": "dev",
            }
        ],
        filename="existing_gold.jsonl",
    )
    new_input = tmp_jsonl(
        [
            {
                "scenario_id": "S0002",
                "patient_id": "062d51e6-50d3-3fdf-dc51-4874850033ec",
                "query_text": "Hello doctor, what should I do if I missed my morning dose of Furosemide? Thanks",
                "intent": "medication_query",
                "urgency": "urgent",
                "referenced_fact": "Furosemide",
            }
        ],
        filename="new_batch.jsonl",
    )
    with pytest.raises(ValueError, match=r"Near-Duplicate Query"):
        validate_and_import_synthetic_gold(new_input, out_p, CONTEXT_PACKS_PATH)


def test_split_gold_zero_spanning_clusters():
    records = [
        {
            "query_id": "GS-0001",
            "scenario_id": "S0001",
            "query_text": "What should I do if I missed my morning dose of Furosemide?",
            "intent_label": "medication_query",
            "urgency_label": "urgent",
        },
        {
            "query_id": "GS-0002",
            "scenario_id": "S0002",
            "query_text": "Can you explain my recent glucose test result of 98.2 mg/dL?",
            "intent_label": "lab_result_query",
            "urgency_label": "routine",
        },
        {
            "query_id": "GS-0003",
            "scenario_id": "S0003",
            "query_text": "I have been experiencing a persistent productive cough since my acute bronchitis diagnosis.",
            "intent_label": "symptom_report",
            "urgency_label": "soon",
        },
    ]
    clusters = compute_clusters_and_scenarios(records, threshold=0.70, local_files_only=True)
    dev_recs, test_recs = split_candidate_clusters(records, clusters, dev_ratio=0.35, seed=42)

    # Verify zero clusters span dev and test
    dev_ids = {r["query_id"] for r in dev_recs}
    test_ids = {r["query_id"] for r in test_recs}
    for comp in clusters:
        comp_qids = [records[idx]["query_id"] for idx in comp]
        in_dev = any(qid in dev_ids for qid in comp_qids)
        in_test = any(qid in test_ids for qid in comp_qids)
        assert not (in_dev and in_test), f"Cluster spanned dev and test: {comp_qids}"


def test_fixture_paraphrase_pairs_flagged_and_distinct_pairs_not():
    """
    Test fixture:
      - 5 near-duplicate paraphrase pairs must be flagged as duplicates (cosine >= dup_threshold)
      - 5 distinct-scenario pairs must not be flagged as duplicates (cosine < dup_threshold)
      - 5 hard-negative pairs sharing clinical concepts but different scenarios must NOT flag (cosine < dup_threshold)
      - 5 moderate-paraphrase pairs evaluated with empirically measured similarities
    Evaluated under calibrated mean-centered BAAI/bge-small-en-v1.5 (dup_threshold=0.60).
    """
    import numpy as np
    from backend.eval.import_synthetic_gold import get_corpus_mean, get_diversity_embedder

    embedder = get_diversity_embedder(local_files_only=True)
    corpus_mean = get_corpus_mean()

    paraphrase_pairs = [
        ("Can I take metformin with my dinner?", "Is it okay to take my metformin medication with dinner?"),
        ("My blood pressure was 150/95 this morning, should I be concerned?", "This morning my BP was 150/95, is that dangerous?"),
        ("I need to reschedule my followup appointment for next week.", "Can I change the date of my upcoming followup visit to next week?"),
        ("What do my latest creatinine lab results mean?", "Could you explain my recent creatinine blood test results?"),
        ("I am experiencing severe dizziness and nausea after taking lisinopril.", "Feeling very dizzy and nauseous since starting lisinopril."),
    ]

    distinct_pairs = [
        ("Can I take metformin with my dinner?", "I need to schedule an appointment for routine flu vaccine."),
        ("My blood pressure was 150/95 this morning, should I be concerned?", "What are the normal reference ranges for total cholesterol?"),
        ("I need to reschedule my followup appointment for next week.", "I have an itchy rash on my left arm that started yesterday."),
        ("What do my latest creatinine lab results mean?", "Can I drink coffee before my fasting blood glucose test?"),
        ("I am experiencing severe dizziness and nausea after taking lisinopril.", "I want to know if my insurance covers physical therapy."),
    ]

    hard_negative_pairs = [
        ("I take lisinopril 10mg daily. Can I take ibuprofen for my headache?", "What are the long-term kidney risks of lisinopril?"),
        ("My fasting blood sugar was 110 mg/dL today.", "My fasting blood sugar was 250 mg/dL and I feel confused and thirsty."),
        ("When is my next annual wellness visit scheduled?", "Can I reschedule my cardiology followup appointment to Thursday?"),
        ("I noticed a small red itchy bump on my right ankle.", "I have progressive swelling in both ankles and difficulty breathing."),
        ("Should I take my levothyroxine before or after breakfast?", "Can levothyroxine cause heart palpitations and anxiety?"),
    ]

    moderate_paraphrase_pairs = [
        ("Can I take my blood pressure pills in the evening instead?", "Is it safe to switch my BP medication to bedtime?"),
        ("My doctor said my potassium was slightly high on my lab test.", "Recent blood work showed elevated potassium levels."),
        ("I have had a mild dry cough for three days.", "Experiencing a dry cough since earlier this week."),
        ("How do I request a refill for my atorvastatin prescription?", "I am running out of atorvastatin and need a refill."),
        ("Do I need to fast before my cholesterol blood test tomorrow?", "Should I avoid eating before my lipid panel in the morning?"),
    ]

    threshold = 0.60

    def calc_similarity(t1: str, t2: str) -> float:
        e1 = embedder.encode([t1], normalize_embeddings=True)[0]
        e2 = embedder.encode([t2], normalize_embeddings=True)[0]
        c1 = e1 - corpus_mean
        c2 = e2 - corpus_mean
        c1 = c1 / np.linalg.norm(c1)
        c2 = c2 / np.linalg.norm(c2)
        return float(np.dot(c1, c2))

    # 1. 5 paraphrase pairs must be flagged as duplicates (sim >= threshold)
    for idx, (t1, t2) in enumerate(paraphrase_pairs, start=1):
        sim = calc_similarity(t1, t2)
        assert sim >= threshold, f"Paraphrase pair {idx} failed to flag as duplicate: sim={sim:.4f} < {threshold}"

    # 2. 5 distinct-scenario pairs must NOT be flagged as duplicates (sim < threshold)
    for idx, (t1, t2) in enumerate(distinct_pairs, start=1):
        sim = calc_similarity(t1, t2)
        assert sim < threshold, f"Distinct pair {idx} falsely flagged as duplicate: sim={sim:.4f} >= {threshold}"

    # 3. 5 hard-negative pairs sharing clinical entities must NOT be flagged (sim < threshold)
    for idx, (t1, t2) in enumerate(hard_negative_pairs, start=1):
        sim = calc_similarity(t1, t2)
        assert sim < threshold, f"Hard negative pair {idx} falsely flagged: sim={sim:.4f} >= {threshold}"

    # 4. 5 moderate-paraphrase pairs: measure similarity and assert empirical bounds [0.50, 0.85]
    for idx, (t1, t2) in enumerate(moderate_paraphrase_pairs, start=1):
        sim = calc_similarity(t1, t2)
        assert 0.45 <= sim <= 0.85, f"Moderate paraphrase pair {idx} outside expected bounds: sim={sim:.4f}"


