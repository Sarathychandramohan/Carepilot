"""
D:\\CarePilotAI\\backend\\app\\api\\consult.py

POST /api/consult — Full Pillar B pipeline entry point.
GET  /api/consult/{consultation_id} — Retrieve a single consultation.

The endpoint accepts a patient query and runs the full P1→P8 orchestrator,
returning the resulting consultation record (with AI draft if pipeline passed,
or manual_required status if any gate failed).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import datetime

from backend.app.db.models_v3 import Consultation
from backend.app.pipeline.orchestrator import run_pipeline
from backend.app.pipeline.generate import (
    EDIT_CATEGORIES_TEMPLATE,
    compute_consultation_edit_weight,
    compute_edit_distances,
    sanitize_delivery_text,
)

router = APIRouter(prefix="/api/consult", tags=["Pillar B — Consultation"])


# ---------------------------------------------------------------------------
# Authorization Dependencies
# ---------------------------------------------------------------------------

def require_doctor_role(
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    role: Optional[str] = Query(None, description="Clinician role query parameter"),
) -> str:
    """
    Enforces that caller has doctor/clinician authorization to view or review
    unredacted clinical consultation records (drafts, NLI metrics, audit notes).
    Patients must use the patient-scoped endpoint /api/patient/{patient_id}/consultations/{id}.
    """
    header_val = x_user_role if isinstance(x_user_role, str) else None
    query_val = role if isinstance(role, str) else None
    authorized_role = (header_val or query_val or "").lower().strip()
    if authorized_role not in ("doctor", "clinician", "physician", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Clinician review access requires doctor role ('X-User-Role: doctor' header or role='doctor'). "
                   "Patients must access consultations via /api/patient/{patient_id}/consultations/{id}.",
        )
    return authorized_role


# ---------------------------------------------------------------------------
# Dependency: DB session
# ---------------------------------------------------------------------------

def get_db():
    """Dependency that yields a SQLAlchemy session."""
    from backend.app.db.session import SessionLocal  # type: ignore
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ConsultRequest(BaseModel):
    patient_id: str = Field(..., description="Stable patient UUID")
    query_text: str = Field(..., min_length=3, max_length=2000)
    ablation_config: str = Field(
        default="full",
        description="Ablation arm: full | no_ehr | no_classifier | unified_context",
    )
    edit_memory: bool = Field(
        default=False,
        description="If True, inject D6 prior approved responses into draft prompt",
    )
    is_eval: bool = Field(
        default=False,
        description="If True, marks query as evaluation/benchmark run and excludes from clinical doctor queue",
    )


class ConsultResponse(BaseModel):
    consultation_id: str
    patient_id: str
    intent: Optional[str]
    urgency_final: Optional[str]
    urgency_agreement: Optional[str]
    validation_status: Optional[str]
    thread_status: str
    is_high_priority: bool
    is_red_flag_override: bool
    patient_ehr_mismatch_flag: Optional[bool]
    missing_context_flag: Optional[bool]
    has_draft: bool
    ablation_config: str
    is_eval: bool = False
    generation_latency_ms: Optional[int]
    faithfulness_score: Optional[float]
    citation_entailment_score: Optional[float]

    class Config:
        from_attributes = True


class DoctorReviewRequest(BaseModel):
    doctor_action: str = Field(..., description="Action: 'approved' | 'edited' | 'rejected'")
    final_response: Optional[str] = Field(None, description="Doctor-approved final text sent to patient")
    reject_reason: Optional[str] = Field(None, description="Reason code if rejected")
    edit_categories: Optional[dict[str, int]] = Field(
        default=None,
        description="All 12 edit categories {cat: 0|1}. Defaults to no_change=1 if approved without edit.",
    )
    doctor_review_seconds: Optional[int] = Field(None, description="Duration of review in seconds")
    opened_sources: Optional[list[str]] = Field(default_factory=list, description="List of source IDs opened")


class DoctorReviewResponse(BaseModel):
    consultation_id: str
    doctor_action: str
    thread_status: str
    final_response: Optional[str]
    edit_categories: dict[str, int]
    consultation_edit_weight: float
    edit_distance_chars: Optional[int]
    edit_distance_words: Optional[int]
    edr_char: Optional[float]
    edr_word: Optional[float]
    doctor_reviewed_at: str


class DeliveryResponse(BaseModel):
    consultation_id: str
    patient_id: str
    thread_status: str
    final_response: str
    delivered_at: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", response_model=ConsultResponse, status_code=201)
async def submit_consultation(
    req: ConsultRequest,
    db: Session = Depends(get_db),
) -> ConsultResponse:
    """
    Submit a patient query through the full Pillar B pipeline (P1→P8).

    - B2: red-flag check + intent classification (always) + urgency (arm-dependent)
    - B3: EHR retrieval + KB retrieval + D17 conflict detection
    - B4: LLM draft generation (local model only)
    - B5: Faithfulness validation
    - B6: Doctor queue dispatch

    Returns the consultation record with pipeline outcomes.
    """
    if req.ablation_config not in ("full", "no_ehr", "no_classifier", "unified_context"):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid ablation_config '{req.ablation_config}'. "
                   "Must be one of: full, no_ehr, no_classifier, unified_context",
        )

    consultation = run_pipeline(
        patient_id=req.patient_id,
        query_text=req.query_text,
        db=db,
        ablation_config=req.ablation_config,
        edit_memory=req.edit_memory,
        is_eval=req.is_eval,
    )

    return ConsultResponse(
        consultation_id=consultation.id,
        patient_id=consultation.patient_id,
        intent=consultation.intent,
        urgency_final=consultation.urgency_final,
        urgency_agreement=getattr(consultation, "urgency_agreement", None),
        validation_status=consultation.validation_status,
        thread_status=consultation.thread_status,
        is_high_priority=bool(consultation.is_high_priority),
        is_red_flag_override=bool(consultation.is_red_flag_override),
        patient_ehr_mismatch_flag=getattr(consultation, "patient_ehr_mismatch_flag", None),
        missing_context_flag=getattr(consultation, "missing_context_flag", None),
        has_draft=consultation.ai_draft_json is not None,
        ablation_config=consultation.ablation_arm or req.ablation_config,
        is_eval=bool(getattr(consultation, "is_eval", False)),
        generation_latency_ms=consultation.generation_latency_ms,
        faithfulness_score=consultation.faithfulness_score,
        citation_entailment_score=consultation.citation_entailment_score,
    )


@router.get("/{consultation_id}", response_model=dict)
async def get_consultation(
    consultation_id: str,
    db: Session = Depends(get_db),
    _role: str = Depends(require_doctor_role),
) -> dict:
    """
    Retrieve a single clinical consultation record by ID (clinician view).
    Requires doctor authorization ('X-User-Role: doctor' or role='doctor').
    Patients must access their responses via /api/patient/{patient_id}/consultations/{id}.
    """
    row = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Consultation not found")

    return {
        "id": row.id,
        "patient_id": row.patient_id,
        "query_text": row.query_text,
        "intent": row.intent,
        "urgency_final": row.urgency_final,
        "validation_status": row.validation_status,
        "thread_status": row.thread_status,
        "is_high_priority": row.is_high_priority,
        "is_red_flag_override": row.is_red_flag_override,
        "ai_draft": row.ai_draft_json,
        "faithfulness_score": row.faithfulness_score,
        "citation_entailment_score": row.citation_entailment_score,
        "ablation_arm": row.ablation_arm,
        "llm_model": row.llm_model,
        "generation_latency_ms": row.generation_latency_ms,
        "doctor_action": row.doctor_action,
        "reject_reason": row.reject_reason,
        "final_response": row.final_response,
        "consultation_edit_weight": row.consultation_edit_weight,
        "edit_categories": row.edit_categories_json,
        "edit_distance_chars": row.edit_distance_chars,
        "edit_distance_words": row.edit_distance_words,
        "edr_char": row.edr_char,
        "edr_word": row.edr_word,
        "is_eval": row.is_eval,
        "doctor_review_seconds": row.doctor_review_seconds,
        "doctor_reviewed_at": str(row.doctor_reviewed_at) if row.doctor_reviewed_at else None,
        "delivered_at": str(row.delivered_at) if row.delivered_at else None,
        "created_at": str(row.created_at),
    }


@router.post("/{consultation_id}/review", response_model=DoctorReviewResponse)
async def submit_doctor_review(
    consultation_id: str,
    req: DoctorReviewRequest,
    db: Session = Depends(get_db),
) -> DoctorReviewResponse:
    """
    Submit clinician review for a consultation (B5 / S9 review tracking).

    - Validates doctor action (approved, edited, rejected).
    - Enforces all 12 edit categories.
    - Computes Levenshtein char/word distances and EDR ratios.
    - Computes weighted edit burden score W_k = Σ w_i * c_{k,i}.
    - Transitions thread_status to 'approved' or 'rejected'.
    - Updates consultation record in PostgreSQL for audit and D6 edit memory.
    """
    action_raw = req.doctor_action.lower().strip()
    action_map = {
        "approve": "approved",
        "approved": "approved",
        "edit": "edited",
        "edited": "edited",
        "reject": "rejected",
        "rejected": "rejected",
    }
    if action_raw not in action_map:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid doctor_action '{req.doctor_action}'. Must be one of ('approved', 'edited', 'rejected')",
        )
    canonical_action = action_map[action_raw]

    row = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Consultation not found")

    # Extract draft text
    draft_text = ""
    if row.ai_draft_json and isinstance(row.ai_draft_json, dict):
        sentences = row.ai_draft_json.get("sentences", [])
        draft_text = " ".join(s.get("text", "") for s in sentences if isinstance(s, dict))

    final_response = req.final_response
    if final_response is None:
        if canonical_action in ("approved", "edited"):
            final_response = draft_text

    # Populate all 12 edit categories
    cats = {k: int(bool((req.edit_categories or {}).get(k, 0))) for k in EDIT_CATEGORIES_TEMPLATE}
    if not any(cats.values()):
        if canonical_action == "approved" or (draft_text and final_response == draft_text):
            cats["no_change"] = 1

    weight = compute_consultation_edit_weight(cats)
    distances = compute_edit_distances(draft_text, final_response or "")

    now = datetime.datetime.utcnow()
    row.doctor_action = canonical_action
    row.reject_reason = req.reject_reason
    row.final_response = final_response
    row.edit_categories_json = cats
    row.consultation_edit_weight = weight
    row.doctor_review_seconds = req.doctor_review_seconds
    row.doctor_reviewed_at = now
    row.thread_status = "rejected" if canonical_action == "rejected" else "approved"
    row.edit_distance_chars = distances["edit_distance_chars"]
    row.edit_distance_words = distances["edit_distance_words"]
    row.edr_char = distances["edr_char"]
    row.edr_word = distances["edr_word"]

    db.commit()
    db.refresh(row)

    return DoctorReviewResponse(
        consultation_id=row.id,
        doctor_action=row.doctor_action,
        thread_status=row.thread_status,
        final_response=row.final_response,
        edit_categories=row.edit_categories_json or cats,
        consultation_edit_weight=row.consultation_edit_weight or 0.0,
        edit_distance_chars=row.edit_distance_chars,
        edit_distance_words=row.edit_distance_words,
        edr_char=row.edr_char,
        edr_word=row.edr_word,
        doctor_reviewed_at=str(row.doctor_reviewed_at),
    )


@router.post("/{consultation_id}/deliver", response_model=DeliveryResponse)
async def deliver_consultation(
    consultation_id: str,
    db: Session = Depends(get_db),
) -> DeliveryResponse:
    """
    Deliver doctor-approved consultation response to the patient (P10).

    - Verifies that thread_status is 'approved'.
    - Sanitizes final_response by stripping internal tokens, citations, context markers, and code blocks.
    - Records delivered_at and patient_notified_at timestamps.
    - Transitions thread_status to 'delivered'.
    """
    row = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Consultation not found")

    if row.doctor_action not in ("approved", "edited"):
        raise HTTPException(
            status_code=400,
            detail=f"Consultation cannot be delivered. Doctor review action must be 'approved' or 'edited' (currently '{row.doctor_action}').",
        )

    clean_text = sanitize_delivery_text(row.final_response or "")
    if not clean_text:
        raise HTTPException(status_code=400, detail="Cannot deliver empty consultation response")

    now = datetime.datetime.utcnow()
    row.final_response = clean_text
    row.delivered_at = now
    row.patient_notified_at = now
    row.thread_status = "delivered"

    db.commit()
    db.refresh(row)

    return DeliveryResponse(
        consultation_id=row.id,
        patient_id=row.patient_id,
        thread_status=row.thread_status,
        final_response=row.final_response,
        delivered_at=str(row.delivered_at),
    )
