from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import datetime
import uuid

from backend.app.api.consult import router as consult_router
from backend.app.api.queue import router as queue_router
from backend.app.api.patient import router as patient_router, patients_router

# Stand-in FastAPI router implementation for CarePilot AI Modules 1-4
app = FastAPI(
    title="CarePilot AI Backend Pipeline",
    description="REST API for Human-in-the-loop clinical RAG pipeline, multi-turn threading, report trends & appointment scheduling",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pillar B Routers
app.include_router(consult_router)
app.include_router(queue_router)
app.include_router(patient_router)
app.include_router(patients_router)

# -----------------------------------------------------------------------------

# MODULE 1 — CONVERSATION & MULTI-TURN THREADING ENDPOINTS
# -----------------------------------------------------------------------------

@app.get("/api/conversations/{conversation_id}")
def get_conversation_thread(conversation_id: str):
    """
    Module 1: Retrieve full multi-turn conversation thread by ID.
    Persists full thread context (all prior patient/doctor turns) to pass to patient-retrieval.
    """
    # Prototype stand-in implementation
    return {
        "id": conversation_id,
        "patientId": "hero-001",
        "threadStatus": "awaiting_doctor", # awaiting_doctor | approved | patient_replied
        "messages": [
            {"id": "m1", "role": "patient", "content": "Why is my creatinine rising?", "timestamp": "2026-09-18T10:00:00Z"},
            {"id": "m2", "role": "doctor", "content": "Your creatinine has risen from 1.2 to 1.4 mg/dL...", "timestamp": "2026-09-18T10:30:00Z"},
            {"id": "m3", "role": "patient", "content": "Should I adjust my Metformin dose because of this?", "timestamp": "2026-09-18T11:00:00Z"}
        ]
    }

@app.post("/api/conversations/reply")
def post_thread_reply(conversation_id: str = Query(...), query_text: str = Query(...)):
    """
    Module 1: Append patient follow-up reply to an existing conversation thread.
    Updates thread_status = 'patient_replied' / 'awaiting_doctor' and re-routes to doctor queue.
    """
    return {
        "id": conversation_id,
        "threadStatus": "awaiting_doctor",
        "turnCount": 3,
        "status": "doctor_review",
        "message": "Follow-up added to existing thread. Awaiting doctor approval."
    }


# -----------------------------------------------------------------------------
# MODULE 2 — APPOINTMENT REQUEST & RESCHEDULE ENDPOINTS
# -----------------------------------------------------------------------------

@app.get("/api/appointments/requests")
def list_appointment_requests(status: Optional[str] = None):
    """
    Module 2: Doctor Queue for pending appointment requests and reschedule requests.
    """
    return [
        {
            "id": "app-req-001",
            "patientId": "hero-001",
            "patientName": "Christian Labadie",
            "requestType": "reschedule",  # new | reschedule
            "originalAppointmentId": "a1",
            "requestedDate": "2026-09-25",
            "requestedTime": "10:30 AM",
            "reason": "Need to reschedule nephrology checkup due to conflict",
            "status": "pending_doctor_approval",
            "createdAt": "2026-09-18T09:00:00Z"
        }
    ]

@app.post("/api/appointments/requests")
def create_appointment_request(patient_id: str, request_type: str, requested_date: str, requested_time: str, reason: str, original_appointment_id: Optional[str] = None):
    """
    Module 2: Patient submits new appointment or reschedule request (routes to doctor for approval — HITL).
    """
    return {
        "id": f"app-req-{uuid.uuid4().hex[:6]}",
        "patientId": patient_id,
        "requestType": request_type,
        "status": "pending_doctor_approval",
        "message": "Appointment request submitted. Awaiting doctor review."
    }

@app.put("/api/appointments/requests/{request_id}/respond")
def respond_appointment_request(request_id: str, action: str, doctor_response: Optional[str] = None, proposed_date: Optional[str] = None, proposed_time: Optional[str] = None):
    """
    Module 2: Doctor approves, denies, or proposes an alternative time for an appointment request.
    Actions: 'approve' | 'deny' | 'propose_alternative'
    """
    status_map = {
        "approve": "approved",
        "deny": "denied",
        "propose_alternative": "alternative_proposed"
    }
    return {
        "id": request_id,
        "status": status_map.get(action, "approved"),
        "doctorResponse": doctor_response,
        "proposedAlternativeDate": proposed_date,
        "proposedAlternativeTime": proposed_time,
        "updatedAt": datetime.datetime.utcnow().isoformat()
    }


# -----------------------------------------------------------------------------
# MODULE 3 — REPORT ANALYSIS & TREND ENDPOINTS
# -----------------------------------------------------------------------------

@app.get("/api/reports/trends/{patient_id}")
def get_lab_report_trends(patient_id: str, test_name: str = Query("Creatinine")):
    """
    Module 3: Read-only endpoint that groups lab_results by test_name and date.
    Calculates trend direction (rising, falling, stable) over 3+ readings.
    Display aid only — does NOT generate AI commentary without HITL doctor approval.
    """
    # Sample trend data for Hero Patient (Christian Labadie)
    readings = [
        {"id": "r1", "date": "2022-03-15", "value": 1.1, "unit": "mg/dL", "isOutOfRange": False},
        {"id": "r2", "date": "2022-09-20", "value": 1.2, "unit": "mg/dL", "isOutOfRange": False},
        {"id": "r3", "date": "2023-02-14", "value": 1.3, "unit": "mg/dL", "isOutOfRange": True},
        {"id": "r4", "date": "2023-08-10", "value": 1.4, "unit": "mg/dL", "isOutOfRange": True}
    ]
    
    return {
        "patientId": patient_id,
        "testName": test_name,
        "unit": "mg/dL",
        "referenceMin": 0.6,
        "referenceMax": 1.2,
        "latestValue": 1.4,
        "latestDate": "2023-08-10",
        "previousValue": 1.3,
        "trendDirection": "rising",  # rising | falling | stable
        "readingsCount": 4,
        "isOutOfRange": True,
        "readings": readings
    }


# -----------------------------------------------------------------------------
# MODULE 4 — PRIORITY ALERT & NOTIFICATION ENDPOINTS
# -----------------------------------------------------------------------------

@app.get("/api/notifications/doctor/alerts")
def get_doctor_priority_alerts():
    """
    Module 4: Priority alert banner/badge data for high urgency / red-flag queries on doctor queue.
    """
    return [
        {
            "id": "alert-001",
            "consultationId": "consult-002",
            "patientId": "p2",
            "patientName": "James Okonkwo",
            "urgency": "urgent",
            "isHighPriorityAlert": True,
            "isRedFlagOverride": True,
            "alertReason": "Urgency Classifier High-Risk Priority & Red-Flag Symptom Keyword (Chest Tightness)",
            "createdAt": datetime.datetime.utcnow().isoformat()
        }
    ]

@app.get("/api/notifications/patient/{patient_id}")
def get_patient_notifications(patient_id: str):
    """
    Module 4: In-app notification list for approved consultation responses and appointment reminders.
    (In-app only for prototype; push notification marked as future work candidate).
    """
    return [
        {
            "id": "notif-001",
            "userId": patient_id,
            "category": "consultation",
            "title": "Doctor Approved Response Available",
            "body": "Dr. Amelia Smith has reviewed your question regarding recent blood test results.",
            "read": False,
            "relatedId": "consult-001",
            "createdAt": datetime.datetime.utcnow().isoformat()
        },
        {
            "id": "notif-002",
            "userId": patient_id,
            "category": "appointment",
            "title": "Follow-up Reminder",
            "body": "Your follow-up checkup is scheduled in 3 days (Sep 25 at 10:00 AM).",
            "read": False,
            "relatedId": "a1",
            "createdAt": datetime.datetime.utcnow().isoformat()
        }
    ]
