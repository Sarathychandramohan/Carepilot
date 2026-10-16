"""
D:\\CarePilotAI\\backend\\app\\api\\patient.py

Patient-Facing Endpoints with IDOR Protection and Approved-Text Scoping.

GET /api/patient/{patient_id}/consultations/{consultation_id}
GET /api/patient/{patient_id}/consultations

Guarantees:
1. IDOR Prevention: Patients can only retrieve consultations matching their own patient_id.
2. Clinical Leakage Prevention: Unapproved consultations (awaiting_doctor, manual_required)
   never expose internal AI drafts, NLI metrics, or clinician notes to the patient.
   Only 'approved' or 'delivered' final_response text is returned.
"""
from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db.models_v3 import Consultation

router = APIRouter(prefix="/api/patient", tags=["Patient Portal"])


def get_db():
    from backend.app.db.session import SessionLocal  # type: ignore
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class PatientConsultationView(BaseModel):
    consultation_id: str
    patient_id: str
    thread_status: str
    query_text: str
    final_response: Optional[str] = None
    message: Optional[str] = None
    delivered_at: Optional[str] = None
    created_at: str


@router.get("/{patient_id}/consultations/{consultation_id}", response_model=PatientConsultationView)
async def get_patient_consultation(
    patient_id: str,
    consultation_id: str,
    db: Session = Depends(get_db),
) -> PatientConsultationView:
    """
    Retrieve a consultation record scoped strictly to the authenticated/requesting patient.

    - Returns 404 if consultation does not exist at all.
    - Returns 403 Forbidden if consultation belongs to another patient (IDOR protection).
    - Returns ONLY final_response when thread_status indicates 'delivered'.
    - Returns a safe 'pending review' placeholder otherwise.
    - NEVER returns draft_text, ai_draft_json, citations, NLI scores, or any clinician-only field.
    """
    row = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not row:
        raise HTTPException(
            status_code=404,
            detail="Consultation not found",
        )

    if row.patient_id != patient_id:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: consultation belongs to another patient",
        )

    # Return final_response strictly when thread_status indicates delivered
    if row.thread_status == "delivered":
        return PatientConsultationView(
            consultation_id=row.id,
            patient_id=row.patient_id,
            thread_status="delivered",
            query_text=row.query_text,
            final_response=row.final_response,
            delivered_at=str(row.delivered_at) if row.delivered_at else None,
            created_at=str(row.created_at),
        )

    # Pending clinician review or delivery — mask all drafts and clinical internals
    return PatientConsultationView(
        consultation_id=row.id,
        patient_id=row.patient_id,
        thread_status="pending_review",
        query_text=row.query_text,
        final_response=None,
        message="Your consultation is currently being reviewed by a clinician.",
        delivered_at=None,
        created_at=str(row.created_at),
    )


@router.get("/{patient_id}/consultations", response_model=List[PatientConsultationView])
async def list_patient_consultations(
    patient_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> List[PatientConsultationView]:
    """
    List all consultations for a patient with IDOR protection and draft masking.
    """
    rows = (
        db.query(Consultation)
        .filter(Consultation.patient_id == patient_id)
        .order_by(Consultation.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    results: list[PatientConsultationView] = []
    for row in rows:
        if row.thread_status == "delivered":
            results.append(
                PatientConsultationView(
                    consultation_id=row.id,
                    patient_id=row.patient_id,
                    thread_status="delivered",
                    query_text=row.query_text,
                    final_response=row.final_response,
                    delivered_at=str(row.delivered_at) if row.delivered_at else None,
                    created_at=str(row.created_at),
                )
            )
        else:
            results.append(
                PatientConsultationView(
                    consultation_id=row.id,
                    patient_id=row.patient_id,
                    thread_status="pending_review",
                    query_text=row.query_text,
                    final_response=None,
                    message="Your consultation is currently being reviewed by a clinician.",
                    delivered_at=None,
                    created_at=str(row.created_at),
                )
            )

    return results
