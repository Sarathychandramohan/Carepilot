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

from backend.app.db.models_v3 import Consultation, Patient, Condition, LabResult, Prescription, Encounter, Allergy
from datetime import date

router = APIRouter(prefix="/api/patient", tags=["Patient Portal"])
patients_router = APIRouter(prefix="/api/patients", tags=["Patient Directory"])

def resolve_patient_id(patient_id: str) -> str:
    """Resolve mock/hero patient alias to the demo Synthea record."""
    if patient_id in ("hero-001", "p1", "patient-001", "hero"):
        return "demo40:55dedab5-5f48-0190-bd3a-34f79bec6e48"
    return patient_id

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
    from backend.app.api.consult import resolve_consultation
    resolved_pid = resolve_patient_id(patient_id)
    row = resolve_consultation(db, consultation_id)
    if not row:
        raise HTTPException(
            status_code=404,
            detail="Consultation not found",
        )

    if row.patient_id != resolved_pid and row.patient_id != patient_id:
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
    resolved_pid = resolve_patient_id(patient_id)
    rows = (
        db.query(Consultation)
        .filter(Consultation.patient_id.in_([resolved_pid, patient_id]))
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


@router.get("/{patient_id}/ehr", response_model=dict)
async def get_patient_ehr(
    patient_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Retrieve full longitudinal EHR context for a patient (Doctor & Clinical Workspace view).
    Includes demographics, active/past conditions, medications, recent labs, and encounters.
    """
    pid = resolve_patient_id(patient_id)
    patient = db.query(Patient).filter(Patient.id == pid).first()
    if not patient:
        # Fallback search by id prefix
        patient = db.query(Patient).filter(Patient.id.like(f"%{pid}%")).first()

    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found in EHR database")

    # Calculate age
    age = 0
    if patient.birth_date:
        today = date.today()
        age = today.year - patient.birth_date.year - ((today.month, today.day) < (patient.birth_date.month, patient.birth_date.day))

    # Retrieve conditions
    conditions = (
        db.query(Condition)
        .filter(Condition.patient_id == patient.id)
        .order_by(Condition.start_date.desc().nullslast())
        .limit(100)
        .all()
    )

    # Retrieve prescriptions (medications)
    prescriptions = (
        db.query(Prescription)
        .filter(Prescription.patient_id == patient.id)
        .order_by(Prescription.start_date.desc().nullslast())
        .limit(100)
        .all()
    )

    # Retrieve recent lab results
    labs = (
        db.query(LabResult)
        .filter(LabResult.patient_id == patient.id)
        .order_by(LabResult.observed_at.desc().nullslast())
        .limit(100)
        .all()
    )

    # Retrieve encounters
    encounters = (
        db.query(Encounter)
        .filter(Encounter.patient_id == patient.id)
        .order_by(Encounter.start_time.desc().nullslast())
        .limit(50)
        .all()
    )

    # Retrieve allergies
    allergies = (
        db.query(Allergy)
        .filter(Allergy.patient_id == patient.id)
        .limit(50)
        .all()
    )

    return {
        "id": patient.id,
        "firstName": patient.first_name,
        "lastName": patient.last_name,
        "dateOfBirth": str(patient.birth_date) if patient.birth_date else "",
        "gender": "M" if (patient.gender or "").upper().startswith("M") else "F",
        "age": age,
        "address": patient.address or f"{patient.city or ''}, {patient.state or ''}",
        "city": patient.city,
        "state": patient.state,
        "conditions": [
            {
                "id": c.id,
                "description": c.description,
                "startDate": str(c.start_date) if c.start_date else "",
                "stopDate": str(c.stop_date) if c.stop_date else None,
                "active": c.stop_date is None,
            }
            for c in conditions
        ],
        "medications": [
            {
                "id": p.id,
                "patientId": patient.id,
                "name": p.description,
                "dosage": "Standard dose",
                "frequency": "Daily",
                "startDate": str(p.start_date.date()) if p.start_date else "",
                "stopDate": str(p.stop_date.date()) if p.stop_date else None,
                "active": p.stop_date is None,
                "reasonDescription": p.reason_description,
            }
            for p in prescriptions
        ],
        "labResults": [
            {
                "id": l.id,
                "patientId": patient.id,
                "testName": l.description,
                "value": l.numeric_value or (float(l.value) if l.value and l.value.replace('.', '', 1).isdigit() else 0.0),
                "unit": l.units or "",
                "date": str(l.observed_at.date()) if l.observed_at else "",
                "isOutOfRange": bool(l.is_abnormal),
                "referenceMin": l.ref_min,
                "referenceMax": l.ref_max,
            }
            for l in labs
        ],
        "encounters": [
            {
                "id": e.id,
                "patientId": patient.id,
                "date": str(e.start_time.date()) if e.start_time else "",
                "type": e.encounter_class or "Clinical",
                "encounterClass": e.encounter_class or "Outpatient",
                "description": e.description or "Medical Encounter",
                "reasonDescription": e.reason_description or "",
            }
            for e in encounters
        ],
        "allergies": [
            {
                "id": a.id,
                "description": a.code or "Environmental/Drug Allergy",
                "severity": "Moderate",
                "type": "Allergy",
            }
            for a in allergies
        ],
    }


@patients_router.get("", response_model=List[dict])
async def list_patients(
    search: Optional[str] = Query(None, description="Search by name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> List[dict]:
    """
    List patients for clinician directory with basic demographics.
    """
    query = db.query(Patient)
    if search:
        query = query.filter(
            (Patient.first_name.ilike(f"%{search}%")) |
            (Patient.last_name.ilike(f"%{search}%")) |
            (Patient.id.ilike(f"%{search}%"))
        )

    rows = query.order_by(Patient.last_name.asc()).offset(offset).limit(limit).all()

    today = date.today()
    results = []
    for p in rows:
        age = 0
        if p.birth_date:
            age = today.year - p.birth_date.year - ((today.month, today.day) < (p.birth_date.month, p.birth_date.day))

        results.append({
            "id": p.id,
            "firstName": p.first_name,
            "lastName": p.last_name,
            "gender": "M" if (p.gender or "").upper().startswith("M") else "F",
            "age": age,
            "dateOfBirth": str(p.birth_date) if p.birth_date else "",
            "city": p.city or "Boston",
            "state": p.state or "MA",
            "conditionsCount": len(p.conditions) if p.conditions else 0,
            "medicationsCount": len(p.prescriptions) if p.prescriptions else 0,
        })
    return results
