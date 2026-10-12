from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
import datetime

class MessageSchema(BaseModel):
    id: str
    consultationId: str
    role: str  # patient, system, doctor
    content: str
    timestamp: str
    status: Optional[str] = None

class ConversationCreateSchema(BaseModel):
    patientId: str
    patientName: str
    queryText: str
    threadId: Optional[str] = None  # If provided, appends to existing thread for multi-turn threading

class ConversationResponseSchema(BaseModel):
    id: str
    patientId: str
    patientName: str
    queryText: str
    status: str
    threadStatus: str  # awaiting_doctor, approved, patient_replied
    intent: Optional[str] = None
    urgency: Optional[str] = None
    aiAnalysis: Optional[Dict[str, Any]] = None
    aiDraft: Optional[Dict[str, Any]] = None
    doctorReview: Optional[Dict[str, Any]] = None
    finalResponse: Optional[str] = None
    messages: List[MessageSchema] = []
    isHighPriorityAlert: bool = False
    isRedFlagOverride: bool = False
    alertReason: Optional[str] = None
    createdAt: str
    updatedAt: str

class DoctorReviewSchema(BaseModel):
    action: str  # approved, rejected
    finalResponse: Optional[str] = None
    editCategory: Optional[str] = None
    reason: Optional[str] = None
    reasonNote: Optional[str] = None

# MODULE 2 SCHEMAS — APPOINTMENTS
class AppointmentRequestCreateSchema(BaseModel):
    patientId: str
    patientName: str
    requestType: str = "new"  # new, reschedule
    originalAppointmentId: Optional[str] = None
    requestedDate: str
    requestedTime: str
    reason: str

class AppointmentRequestRespondSchema(BaseModel):
    action: str  # approve, deny, propose_alternative
    doctorResponse: Optional[str] = None
    proposedAlternativeDate: Optional[str] = None
    proposedAlternativeTime: Optional[str] = None

class AppointmentRequestResponseSchema(BaseModel):
    id: str
    patientId: str
    patientName: str
    requestType: str
    originalAppointmentId: Optional[str] = None
    requestedDate: str
    requestedTime: str
    reason: str
    status: str
    doctorResponse: Optional[str] = None
    proposedAlternativeDate: Optional[str] = None
    proposedAlternativeTime: Optional[str] = None
    createdAt: str

# MODULE 3 SCHEMAS — REPORT TRENDS
class LabReadingSchema(BaseModel):
    id: str
    date: str
    value: float
    unit: str
    isOutOfRange: bool = False

class ReportTrendSchema(BaseModel):
    patientId: str
    testName: str
    unit: string = "mg/dL"
    referenceMin: Optional[float] = None
    referenceMax: Optional[float] = None
    latestValue: float
    latestDate: str
    previousValue: Optional[float] = None
    trendDirection: str  # rising, falling, stable
    readingsCount: int
    isOutOfRange: bool
    readings: List[LabReadingSchema]
