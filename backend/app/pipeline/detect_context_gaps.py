"""
D:\\CarePilotAI\\backend\\app\\pipeline\\detect_context_gaps.py

B3.3 — D17: Conflict and Missing-Context Detection
Pillar B, pre-generation safety checks.

Two failure modes:
  D17a: patient_ehr_mismatch — query references a concept not in retrieved EHR
  D17b: missing_context     — both EHR and KB are empty / too weak to ground a draft

Both trigger manual_required routing before the LLM is called.
"""
from __future__ import annotations

from backend.app.pipeline.retrieve_ehr import EHRChunk
from backend.app.pipeline.retrieve_kb import KBChunk

# Minimum RRF score for a KB chunk to be considered "substantive"
KB_RRF_THRESHOLD = 0.25


def detect_ehr_mismatch(
    normalized_concepts: list[dict],
    ehr_chunks: list[EHRChunk],
    intent: str | None = None,
) -> bool:
    """
    D17a: Returns True when the patient's query references a clinical concept
    (lab, medication, or condition) that is NOT present in their retrieved EHR data.

    Example: Patient asks about their Lisinopril dosage, but no Lisinopril
    prescription appears in ehr_chunks → mismatch → manual_required.

    Only triggers for concepts with domain in {lab, medication, condition}.
    Concepts from general_health_info queries (intent=general_health_info) are excluded
    because those are knowledge questions, not EHR-grounded.
    """
    if intent == "general_health_info":
        return False

    clinical_concepts = [
        c for c in normalized_concepts
        if c.get("domain") in ("lab", "medication", "condition")
        and (c.get("canonical_label") or "").strip()
    ]
    if not clinical_concepts:
        return False

    if not ehr_chunks:
        # Patient asked an EHR-oriented question with a specific clinical concept,
        # but has zero matching EHR records for it → mismatch
        return True

    # Build a set of labels from retrieved chunks (case-insensitive)
    retrieved_labels = {c.label.lower().strip() for c in ehr_chunks}

    for concept in clinical_concepts:
        canonical = (concept.get("canonical_label") or "").lower().strip()
        matched = any(canonical in label or label in canonical for label in retrieved_labels)
        if not matched:
            return True

    return False


def detect_missing_context(
    ehr_chunks: list[EHRChunk],
    kb_chunks: list[KBChunk],
    rrf_threshold: float = KB_RRF_THRESHOLD,
) -> bool:
    """
    D17b: Returns True when BOTH conditions hold:
      1. EHR chunks are absent OR all chunks are outlier-flagged
      2. All KB chunks have RRF scores below rrf_threshold

    When both are true, there is no reliable grounding for any LLM draft.
    Routing to manual_required is the only safe option.
    """
    # Condition 1: EHR is effectively empty (absent or all outlier)
    ehr_empty = (
        len(ehr_chunks) == 0
        or all(c.is_outlier for c in ehr_chunks)
    )

    # Condition 2: KB chunks are all low-confidence
    kb_weak = (
        len(kb_chunks) == 0
        or all(c.score_rrf < rrf_threshold for c in kb_chunks)
    )

    return ehr_empty and kb_weak


def run_d17_checks(
    normalized_concepts: list[dict],
    ehr_chunks: list[EHRChunk],
    kb_chunks: list[KBChunk],
    intent: str | None = None,
) -> dict:
    """
    Runs both D17 checks and returns a summary dict for logging.

    Returns:
        {
            "patient_ehr_mismatch": bool,
            "missing_context": bool,
            "manual_required": bool,   # True if either flag is True
            "reason": str | None,      # "ehr_mismatch" | "missing_context" | None
        }
    """
    mismatch = detect_ehr_mismatch(normalized_concepts, ehr_chunks, intent=intent)
    missing = detect_missing_context(ehr_chunks, kb_chunks)

    if mismatch:
        reason = "ehr_mismatch"
    elif missing:
        reason = "missing_context"
    else:
        reason = None

    return {
        "patient_ehr_mismatch": mismatch,
        "missing_context": missing,
        "manual_required": mismatch or missing,
        "reason": reason,
    }
