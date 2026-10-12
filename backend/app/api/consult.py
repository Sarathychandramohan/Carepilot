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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.db.models_v3 import Consultation
from backend.app.pipeline.orchestrator import run_pipeline

router = APIRouter(prefix="/api/consult", tags=["Pillar B — Consultation"])


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
    generation_latency_ms: Optional[int]
    faithfulness_score: Optional[float]
    citation_entailment_score: Optional[float]

    class Config:
        from_attributes = True


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
        generation_latency_ms=consultation.generation_latency_ms,
        faithfulness_score=consultation.faithfulness_score,
        citation_entailment_score=consultation.citation_entailment_score,
    )


@router.get("/{consultation_id}", response_model=dict)
async def get_consultation(
    consultation_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Retrieve a single consultation record by ID."""
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
        "created_at": str(row.created_at),
    }
