"""
D:\\CarePilotAI\\backend\\app\\pipeline\\generate.py

B4 — LLM Draft Generation
Pillar B, RAG Generation Pipeline.

Generates a citation-backed clinical response draft using the local LLM
(model determined by Gate 0 benchmark — see docs/PILLAR_B_DECISIONS.md).

Key behaviours:
  - Outlier-flagged EHR chunks carry a caveat annotation in the prompt
  - no_classifier arm: prompt asks LLM to self-assess urgency
  - edit_memory (D6): injects prior approved responses into the prompt
  - On JSON parse failure: one retry at temperature=0, then manual_required
  - No cloud API calls — local models only
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any

from backend.app.pipeline.retrieve_ehr import EHRChunk
from backend.app.pipeline.retrieve_kb import KBChunk

PROMPT_VERSION = "v1"

# Edit categories — all 12 must be present in every reviewed consultation
EDIT_CATEGORIES_TEMPLATE: dict[str, int] = {
    "factual_correction": 0,
    "missing_ehr_fact": 0,
    "wrong_ehr_fact": 0,
    "unsupported_medical_claim": 0,
    "citation_error": 0,
    "urgency_correction": 0,
    "missing_caution": 0,
    "tone_change": 0,
    "unnecessary_content": 0,
    "retrieval_error": 0,
    "no_change": 0,
    "other": 0,
}

# Weights for per-consultation raw weighted sum (Section S9 — D-002 in decisions log)
EDIT_WEIGHTS: dict[str, int] = {
    "factual_correction": 2,
    "missing_ehr_fact": 2,
    "wrong_ehr_fact": 3,
    "unsupported_medical_claim": 3,
    "citation_error": 2,
    "urgency_correction": 3,
    "missing_caution": 2,
    "tone_change": 1,
    "unnecessary_content": 1,
    "retrieval_error": 2,
    "no_change": 0,
    "other": 1,
}


@dataclass
class DraftSentence:
    text: str
    citations: list[str] = field(default_factory=list)


@dataclass
class GeneratedDraft:
    sentences: list[DraftSentence]
    overall_tone: str                    # "reassuring" | "informative" | "urgent"
    recommended_followup: str | None
    urgency_assessment: str              # always present; authoritative only in no_classifier
    llm_model: str
    prompt_version: str
    generation_latency_ms: int
    raw_llm_output: str                  # stored for debugging / audit

    def to_dict(self) -> dict:
        return {
            "sentences": [asdict(s) for s in self.sentences],
            "overall_tone": self.overall_tone,
            "recommended_followup": self.recommended_followup,
            "urgency_assessment": self.urgency_assessment,
            "llm_model": self.llm_model,
            "prompt_version": self.prompt_version,
            "generation_latency_ms": self.generation_latency_ms,
        }


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def _format_ehr_context(ehr_chunks: list[EHRChunk]) -> str:
    if not ehr_chunks:
        return "No patient EHR data retrieved for this query."
    lines = []
    for chunk in ehr_chunks:
        lines.append(f"  • [{chunk.source_type.upper()}] {chunk.label}: {chunk.display_value} ({chunk.date_str})")
        if chunk.is_outlier and chunk.outlier_annotation:
            lines.append(f"    ⚠ {chunk.outlier_annotation}")
    return "\n".join(lines)


def _format_kb_context(kb_chunks: list[KBChunk]) -> str:
    if not kb_chunks:
        return "No knowledge base articles retrieved."
    lines = []
    for i, chunk in enumerate(kb_chunks, start=1):
        lines.append(f"  [{i}] {chunk.source_name} — {chunk.title}")
        lines.append(f"      {chunk.text[:600].strip()}")  # truncate very long chunks
    return "\n".join(lines)


def _format_edit_memory(memory_records: list[dict]) -> str:
    if not memory_records:
        return ""
    lines = ["DOCTOR EDIT HISTORY (last approved responses for this patient):"]
    for i, rec in enumerate(memory_records[:3], start=1):
        cats = [k for k, v in rec.get("edit_categories", {}).items() if v]
        cat_str = ", ".join(cats) if cats else "no_change"
        lines.append(f"  [{i}] Query: \"{rec.get('query_text', '')[:80]}\"")
        lines.append(f"       Edit categories applied: {cat_str}")
        lines.append(f"       Final response: \"{rec.get('final_response', '')[:120]}\"")
    return "\n".join(lines)


def _build_prompt(
    patient: dict,
    ehr_chunks: list[EHRChunk],
    kb_chunks: list[KBChunk],
    query_text: str,
    intent: str,
    urgency_final: str | None,
    ablation_config: str,
    edit_memory_records: list[dict],
) -> str:
    has_outliers = any(c.is_outlier for c in ehr_chunks)
    outlier_warning = (
        "\n⚠ WARNING: One or more EHR values below are flagged as possible simulation "
        "artifacts. Do NOT state outlier-flagged values as plain clinical facts. "
        "Always include a caveat when referencing them.\n"
        if has_outliers else ""
    )

    urgency_line = (
        f"Urgency assessed by classifier: {urgency_final}"
        if ablation_config != "no_classifier"
        else (
            "Urgency: Please assess the clinical urgency yourself. "
            "Include 'urgency_assessment' in your JSON output with value "
            "'routine', 'soon', or 'urgent'."
        )
    )

    memory_block = _format_edit_memory(edit_memory_records)
    memory_section = f"\n{memory_block}\n" if memory_block else ""

    age = patient.get("age", "unknown")
    name = patient.get("first_name", "Patient")

    return f"""You are a clinical assistant drafting a doctor's response to a patient message.
Use ONLY the patient data and medical knowledge provided below.
Do NOT invent facts, lab values, or diagnoses not present in the context.
Write in plain, patient-friendly English. Maximum 3 sentences per point.
{outlier_warning}
PATIENT CONTEXT:
  Name: {name}, Age: {age}
  Active Conditions: {patient.get('conditions', 'See EHR below')}
  Active Medications: {patient.get('medications', 'See EHR below')}

PATIENT EHR FACTS:
{_format_ehr_context(ehr_chunks)}

MEDICAL KNOWLEDGE BASE:
{_format_kb_context(kb_chunks)}
{memory_section}
PATIENT QUERY (Intent: {intent}, {urgency_line}):
"{query_text}"

Respond with ONLY a valid JSON object matching this exact schema:
{{
  "sentences": [
    {{"text": "<sentence text>", "citations": ["<stable_eid or chunk_id>"]}}
  ],
  "overall_tone": "reassuring|informative|urgent",
  "recommended_followup": "<optional recommendation or null>",
  "urgency_assessment": "<routine|soon|urgent>"
}}

Rules:
- Every sentence MUST cite at least one source ID from the context above.
- Do not include any text outside the JSON object.
- urgency_assessment is always required in the output."""


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def _parse_draft(
    raw: str,
    llm_model: str,
    latency_ms: int,
) -> GeneratedDraft | None:
    """Attempt to parse LLM output into GeneratedDraft. Returns None on failure."""
    # Strip markdown code fences if model wraps output
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()

    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    if not isinstance(obj.get("sentences"), list):
        return None

    sentences = [
        DraftSentence(
            text=s.get("text", ""),
            citations=s.get("citations", []),
        )
        for s in obj["sentences"]
        if isinstance(s, dict) and s.get("text")
    ]

    return GeneratedDraft(
        sentences=sentences,
        overall_tone=obj.get("overall_tone", "informative"),
        recommended_followup=obj.get("recommended_followup") or None,
        urgency_assessment=obj.get("urgency_assessment", "routine"),
        llm_model=llm_model,
        prompt_version=PROMPT_VERSION,
        generation_latency_ms=latency_ms,
        raw_llm_output=raw,
    )


# ---------------------------------------------------------------------------
# Main generation entry point
# ---------------------------------------------------------------------------

def generate_draft(
    patient: dict,
    ehr_chunks: list[EHRChunk],
    kb_chunks: list[KBChunk],
    query_text: str,
    intent: str,
    urgency_final: str | None,
    ablation_config: str,
    edit_memory_records: list[dict],
) -> GeneratedDraft | None:
    """
    B4: Generate a citation-backed clinical draft using the local LLM.

    Returns GeneratedDraft on success, None if JSON parsing fails after retry
    (caller must route to manual_required).

    Args:
        patient:              Dict with age, first_name, conditions, medications
        ehr_chunks:           B3.1 output (may be empty in no_ehr arm)
        kb_chunks:            B3.2 output
        query_text:           Raw patient query
        intent:               Classified intent label
        urgency_final:        Urgency string (None in no_classifier before generation)
        ablation_config:      Ablation arm string
        edit_memory_records:  D6 prior approved responses (empty list if not used)
    """
    from backend.app.core.llm import get_llm, get_llm_model_name

    llm = get_llm()
    model_name = get_llm_model_name()

    prompt = _build_prompt(
        patient, ehr_chunks, kb_chunks, query_text,
        intent, urgency_final, ablation_config, edit_memory_records,
    )

    # First attempt
    t0 = time.perf_counter()
    output = llm(prompt, max_tokens=512, temperature=0.1, stop=["\n\n\n"])
    latency_ms = int((time.perf_counter() - t0) * 1000)
    raw = output["choices"][0]["text"]

    draft = _parse_draft(raw, model_name, latency_ms)
    if draft is not None:
        return draft

    # Retry at temperature=0 on parse failure
    t0 = time.perf_counter()
    output = llm(prompt, max_tokens=512, temperature=0.0, stop=["\n\n\n"])
    latency_ms = int((time.perf_counter() - t0) * 1000)
    raw = output["choices"][0]["text"]

    return _parse_draft(raw, model_name, latency_ms)  # None on second failure → manual_required


def load_edit_memory(patient_id: str, db, limit: int = 3) -> list[dict]:
    """
    D6: Fetch the last `limit` doctor-approved responses for this patient.
    Used to condition the LLM on the doctor's editing preferences.
    """
    from sqlalchemy import text as sql_text
    rows = db.execute(
        sql_text("""
            SELECT query_text, final_response, edit_categories_json, urgency_final
            FROM consultations
            WHERE patient_id = :pid
              AND doctor_action = 'approved'
              AND final_response IS NOT NULL
            ORDER BY doctor_reviewed_at DESC
            LIMIT :lim
        """),
        {"pid": patient_id, "lim": limit},
    ).fetchall()

    return [
        {
            "query_text": r.query_text,
            "final_response": r.final_response,
            "edit_categories": r.edit_categories_json or {},
            "urgency": r.urgency_final,
        }
        for r in rows
    ]


def compute_consultation_edit_weight(edit_categories: dict[str, int]) -> float:
    """
    Per-consultation raw weighted sum W_k = Σ w_i * c_{k,i}.
    Stored as consultation_edit_weight in the DB.
    NOT the Section S9 aggregate — that is computed across multiple reviews.
    """
    return float(sum(
        EDIT_WEIGHTS.get(cat, 0) * int(bool(ticked))
        for cat, ticked in edit_categories.items()
    ))
