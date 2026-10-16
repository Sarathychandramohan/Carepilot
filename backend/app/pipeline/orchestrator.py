"""
D:\\CarePilotAI\\backend\\app\\pipeline\\orchestrator.py

Full Pillar B Pipeline Orchestrator (P1 → P8).
Runs all stages in sequence: B1 receipt → B2 classify → B3 retrieve → B4 generate → B5 validate → B6 queue.

Ablation arms (threaded through every stage):
  full            — EHR + KB + classifier urgency
  no_ehr          — KB only (B3.1 skipped)
  no_classifier   — intent always runs; urgency from LLM self-report
  unified_context — EHR + KB with unified prompt format

Invariants enforced here:
  I1: No AI text reaches patient without doctor approval (Pillar C gate)
  I3: Firm red-flag hit always forces urgency=urgent in every arm
"""
from __future__ import annotations

import datetime
import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from backend.app.pipeline.redflag import evaluate_red_flags
from backend.app.pipeline.normalize import normalize_query_concepts
from backend.app.pipeline.classify import classify_intent, classify_urgency
from backend.app.pipeline.retrieve_ehr import retrieve_ehr, EHRChunk
from backend.app.pipeline.retrieve_kb import retrieve_kb, KBChunk
from backend.app.pipeline.detect_context_gaps import run_d17_checks
from backend.app.pipeline.generate import (
    generate_draft, load_edit_memory, compute_consultation_edit_weight,
    EDIT_CATEGORIES_TEMPLATE,
)
from backend.app.pipeline.validate import validate_draft
from backend.app.db.models_v3 import Consultation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_retrieval_trace(
    ehr_chunks: list[EHRChunk],
    kb_chunks: list[KBChunk],
    ehr_loinc_codes: list[str],
    is_dual_intent: bool = False,
    secondary_intent: str | None = None,
) -> dict:
    """Build retrieval_trace_json logged to the consultations table."""
    return {
        "ehr_query_loinc_codes": ehr_loinc_codes,
        "ehr_rows_returned": len(ehr_chunks),
        "ehr_outlier_count": sum(1 for c in ehr_chunks if c.is_outlier),
        "ehr_chunk_ids": [c.stable_eid for c in ehr_chunks],
        "is_dual_intent": is_dual_intent,
        "secondary_intent": secondary_intent,
        "kb_rrf_top_chunks": [
            {"chunk_id": c.chunk_id, "score_rrf": c.score_rrf} for c in kb_chunks
        ],
    }


def _get_patient_context(patient_id: str, db: Session) -> dict:
    """Fetch minimal patient context for prompt construction."""
    from sqlalchemy import text
    row = db.execute(
        text("""
            SELECT first_name, last_name, birth_date,
                   (SELECT STRING_AGG(description, ', ') FROM conditions
                    WHERE patient_id = p.id AND stop_date IS NULL LIMIT 5) AS conditions,
                   (SELECT STRING_AGG(description, ', ') FROM prescriptions
                    WHERE patient_id = p.id AND stop_date IS NULL LIMIT 5) AS medications
            FROM patients p WHERE p.id = :pid
        """),
        {"pid": patient_id},
    ).fetchone()

    if not row:
        return {"first_name": "Patient", "age": "unknown",
                "conditions": "unknown", "medications": "unknown"}

    age = "unknown"
    if row.birth_date:
        today = datetime.date.today()
        age = str(
            today.year - row.birth_date.year
            - ((today.month, today.day) < (row.birth_date.month, row.birth_date.day))
        )

    return {
        "first_name": row.first_name or "Patient",
        "age": age,
        "conditions": row.conditions or "None on record",
        "medications": row.medications or "None on record",
    }


def _finalize_manual_required(
    consultation: Consultation, reason: str, db: Session
) -> Consultation:
    consultation.skip_reason = reason
    consultation.thread_status = "awaiting_doctor"
    consultation.validation_status = "manual_required"
    consultation.is_high_priority = consultation.urgency_final == "urgent"
    consultation.updated_at = datetime.datetime.utcnow()
    db.add(consultation)
    db.commit()
    db.refresh(consultation)
    return consultation


def _finalize_emergency(
    consultation: Consultation, redflag: dict, db: Session
) -> Consultation:
    """Firm red-flag: route to priority queue without draft."""
    consultation.skip_reason = "emergency"
    consultation.thread_status = "awaiting_doctor"
    consultation.is_high_priority = True
    consultation.is_red_flag_override = True
    consultation.urgency_final = "urgent"
    consultation.validation_status = "manual_required"
    consultation.updated_at = datetime.datetime.utcnow()
    db.add(consultation)
    db.commit()
    db.refresh(consultation)
    return consultation


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_pipeline(
    patient_id: str,
    query_text: str,
    db: Session,
    ablation_config: str = "full",
    edit_memory: bool = False,
    is_eval: bool = False,
    eval_run_id: int | None = None,
) -> Consultation:
    """
    Full B1→B6 pipeline orchestrator.

    Args:
        patient_id:      Stable patient UUID
        query_text:      Raw patient query text
        db:              SQLAlchemy session
        ablation_config: One of: full | no_ehr | no_classifier | unified_context
        edit_memory:     If True, inject D6 prior approved responses into B4 prompt
        is_eval:         Authorization flag required for eval-only ablations like no_classifier
        eval_run_id:     Optional FK linking row to eval_runs table for Pillar C harness

    Returns:
        Consultation ORM object (committed to DB)
    """
    # Authorization Gate: no_classifier arm is strictly restricted to eval runs
    if ablation_config == "no_classifier" and not is_eval:
        raise PermissionError(
            "Ablation arm 'no_classifier' requires explicit evaluation authorization (is_eval=True)."
        )

    now = datetime.datetime.utcnow()

    # ── B1: Create consultation record ────────────────────────────────────────
    consultation = Consultation(
        id=str(uuid.uuid4()),
        patient_id=patient_id,
        query_text=query_text,
        query_received_at=now,
        ablation_arm=ablation_config,
        retrieval_config=ablation_config,
        prompt_version="v1",
        is_eval=is_eval,
        eval_run_id=eval_run_id,
        created_at=now,
        updated_at=now,
    )


    # ── B2: Red-flag check ────────────────────────────────────────────────────
    redflag = evaluate_red_flags(query_text)
    consultation.redflag_hit_type = redflag.get("hit_type", "none")
    consultation.redflag_category = redflag.get("primary_category")
    consultation.redflag_soft_hits = redflag.get("soft_hits", [])
    consultation.is_red_flag_override = redflag.get("has_firm_hit", False)

    # ── B2: Normalization ─────────────────────────────────────────────────────
    norm = normalize_query_concepts(query_text)
    consultation.normalized_query = query_text
    consultation.normalization_trace = norm.get("resolved_concepts", [])

    # ── B2: Intent classification — ALWAYS runs in every arm (C11) ───────────
    intent_result = classify_intent(query_text)
    consultation.intent = intent_result["intent"]
    consultation.intent_prob = intent_result["intent_confidence"]
    consultation.intent_probs_json = intent_result["intent_probs"]

    # Unsupported-route safety gate — runs in every arm
    if intent_result["route"] == "unsupported":
        consultation.urgency_final = "routine"
        consultation.urgency_agreement = "agree"
        db.add(consultation)
        db.flush()
        return _finalize_manual_required(consultation, "unsupported_intent", db)

    # ── B2: Urgency classification — SKIPPED in no_classifier arm (C11) ──────
    urgency_final: str | None = None

    if ablation_config != "no_classifier":
        urgency_result = classify_urgency(
            query_text, embedding=intent_result["embedding"]
        )
        consultation.urgency = urgency_result["urgency_classifier"]
        consultation.urgency_score = urgency_result["urgency_score"]
        consultation.urgency_probs_json = urgency_result["urgency_probs"]

        # I3: firm red-flag always overrides (applies in ALL arms)
        if redflag.get("has_firm_hit"):
            urgency_final = "urgent"
            consultation.urgency_agreement = "redflag_upgraded"
        else:
            urgency_final = urgency_result["urgency_classifier"]
            consultation.urgency_agreement = "agree"
    else:
        # no_classifier: urgency resolved after B4
        if redflag.get("has_firm_hit"):
            urgency_final = "urgent"   # I3 still enforced
            consultation.urgency_agreement = "redflag_upgraded"
        else:
            consultation.urgency_agreement = "self_reported"

    consultation.urgency_final = urgency_final or "routine"  # temp placeholder

    # ── Emergency gate (firm red-flag) ────────────────────────────────────────
    if redflag.get("has_firm_hit"):
        db.add(consultation)
        db.flush()
        return _finalize_emergency(consultation, redflag, db)

    # ── B3: Retrieval ─────────────────────────────────────────────────────────
    resolved_concepts = norm.get("resolved_concepts", [])
    ehr_loinc = [c["loinc_code"] for c in resolved_concepts if c.get("loinc_code")]

    if ablation_config == "no_ehr":
        ehr_chunks: list[EHRChunk] = []
        consultation.retrieval_config = "kb_only"
    else:
        ehr_chunks = retrieve_ehr(
            patient_id=patient_id,
            normalized_concepts=resolved_concepts,
            intent=consultation.intent,
            db=db,
            secondary_intent=intent_result.get("secondary_intent"),
            is_dual_intent=intent_result.get("is_dual_intent", False),
        )
        consultation.retrieval_config = (
            "unified_ehr_kb" if ablation_config == "unified_context" else "ehr_and_kb"
        )

    kb_chunks: list[KBChunk] = retrieve_kb(query_text, resolved_concepts)

    # Log retrieval trace
    consultation.ehr_chunks_json = [c.to_dict() for c in ehr_chunks]
    consultation.kb_chunks_json = [c.to_dict() for c in kb_chunks]
    consultation.retrieval_trace_json = _build_retrieval_trace(
        ehr_chunks,
        kb_chunks,
        ehr_loinc,
        is_dual_intent=intent_result.get("is_dual_intent", False),
        secondary_intent=intent_result.get("secondary_intent"),
    )
    consultation.outlier_chunk_count = sum(1 for c in ehr_chunks if c.is_outlier)

    # ── B3.3: D17 conflict / missing-context detection ────────────────────────
    d17 = run_d17_checks(resolved_concepts, ehr_chunks, kb_chunks, intent=consultation.intent)
    consultation.patient_ehr_mismatch_flag = d17["patient_ehr_mismatch"]
    consultation.missing_context_flag = d17["missing_context"]

    if d17["manual_required"]:
        db.add(consultation)
        db.flush()
        return _finalize_manual_required(consultation, d17["reason"], db)

    # ── B4: Edit memory (D6) ──────────────────────────────────────────────────
    edit_memory_records: list[dict] = []
    consultation.edit_memory_used = edit_memory
    if edit_memory:
        edit_memory_records = load_edit_memory(patient_id, db)
        consultation.edit_memory_json = edit_memory_records or None

    # ── B4: LLM draft generation ──────────────────────────────────────────────
    patient_ctx = _get_patient_context(patient_id, db)
    draft = generate_draft(
        patient=patient_ctx,
        ehr_chunks=ehr_chunks,
        kb_chunks=kb_chunks,
        query_text=query_text,
        intent=consultation.intent,
        urgency_final=urgency_final,
        ablation_config=ablation_config,
        edit_memory_records=edit_memory_records,
    )

    if draft is None:
        # JSON parse failed on both attempts
        db.add(consultation)
        db.flush()
        return _finalize_manual_required(consultation, "generation_parse_failed", db)

    consultation.ai_draft_json = draft.to_dict()
    consultation.llm_model = draft.llm_model
    consultation.generation_latency_ms = draft.generation_latency_ms
    consultation.llm_urgency_self_reported = draft.urgency_assessment

    # Resolve urgency_final for no_classifier arm
    if ablation_config == "no_classifier" and urgency_final is None:
        urgency_final = draft.urgency_assessment
    consultation.urgency_final = urgency_final or "routine"

    # ── B5: Faithfulness validation ───────────────────────────────────────────
    from backend.app.core.settings import settings
    validation = validate_draft(
        draft, ehr_chunks, kb_chunks,
        coverage_threshold=settings.faithfulness_threshold,
        nli_pass_threshold=settings.nli_entailment_threshold,
        nli_warn_threshold=settings.nli_entailment_threshold * 0.75,
    )

    consultation.faithfulness_score = validation.citation_coverage
    consultation.faithfulness_details = {"per_sentence": validation.per_sentence}
    consultation.citation_validity_score = validation.citation_validity
    consultation.citation_entailment_score = validation.avg_nli_entailment
    consultation.validation_status = validation.validation_status
    consultation.has_outlier_only_sentence = validation.has_outlier_only_sentence

    if validation.validation_status == "manual_required":
        db.add(consultation)
        db.flush()
        return _finalize_manual_required(consultation, "validation_failed", db)

    # ── B6: Doctor queue dispatch ─────────────────────────────────────────────
    consultation.thread_status = "awaiting_doctor"
    consultation.is_high_priority = (consultation.urgency_final == "urgent")
    consultation.updated_at = datetime.datetime.utcnow()

    db.add(consultation)
    db.commit()
    db.refresh(consultation)
    return consultation
