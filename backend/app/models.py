from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import datetime

Base = declarative_base()

class Patient(Base):
    __tablename__ = 'patients'

    id = Column(String, primary_key=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    birth_date = Column(DateTime)
    gender = Column(String(1))
    city = Column(String)
    state = Column(String)

class Encounter(Base):
    __tablename__ = 'encounters'

    id = Column(String, primary_key=True)
    patient_id = Column(String, ForeignKey('patients.id'))
    start_time = Column(DateTime)
    stop_time = Column(DateTime)
    encounter_class = Column(String)  # ambulatory, wellness, urgent care, emergency, inpatient
    code = Column(String)
    description = Column(String)
    reason_description = Column(String)

class LabResult(Base):
    __tablename__ = 'lab_results'

    id = Column(String, primary_key=True)
    patient_id = Column(String, ForeignKey('patients.id'))
    encounter_id = Column(String, ForeignKey('encounters.id'), nullable=True)
    observed_at = Column(DateTime)
    code = Column(String)
    description = Column(String)  # test_name e.g. Creatinine, HbA1c, eGFR
    value = Column(Float)
    units = Column(String)
    value_type = Column(String)

class Condition(Base):
    __tablename__ = 'conditions'

    id = Column(String, primary_key=True)
    patient_id = Column(String, ForeignKey('patients.id'))
    start_date = Column(DateTime)
    stop_date = Column(DateTime, nullable=True)
    description = Column(String)

class Prescription(Base):
    __tablename__ = 'prescriptions'

    id = Column(String, primary_key=True)
    patient_id = Column(String, ForeignKey('patients.id'))
    start_date = Column(DateTime)
    stop_date = Column(DateTime, nullable=True)
    description = Column(String)
    dispenses = Column(Integer)
    reason_description = Column(String)

# MODULE 1 EXTENSION & CONVERSATION MODEL
class Conversation(Base):
    __tablename__ = 'conversations'

    id = Column(String, primary_key=True)
    patient_id = Column(String, ForeignKey('patients.id'), nullable=False)
    query_text = Column(Text, nullable=False)
    intent = Column(String)  # symptom_query, medication_query, report_query, appointment_request, follow_up
    urgency = Column(String)  # routine, soon, urgent
    urgency_score = Column(Float)
    thread_status = Column(String, default='awaiting_doctor')  # awaiting_doctor, approved, patient_replied
    ai_draft_json = Column(JSON, nullable=True)
    doctor_action = Column(String, nullable=True)  # approved, rejected
    final_response = Column(Text, nullable=True)
    messages_json = Column(JSON, nullable=True)  # Multi-turn thread array: [{role, content, timestamp}]
    edit_distance = Column(Float, nullable=True)
    edit_category = Column(String, nullable=True)  # factual_correction, added_caution, tone_change, no_change
    is_high_priority_alert = Column(Boolean, default=False)
    is_red_flag_override = Column(Boolean, default=False)
    alert_reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

# MODULE 2 NEW TABLE — APPOINTMENT REQUESTS (distinct pre-visit concept from encounters)
class AppointmentRequest(Base):
    __tablename__ = 'appointment_requests'

    id = Column(String, primary_key=True)
    patient_id = Column(String, ForeignKey('patients.id'), nullable=False)
    patient_name = Column(String, nullable=False)
    request_type = Column(String, nullable=False, default='new')  # new, reschedule
    original_appointment_id = Column(String, nullable=True)
    requested_date = Column(String, nullable=False)
    requested_time = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String, nullable=False, default='pending_doctor_approval')  # pending_doctor_approval, approved, denied, alternative_proposed
    doctor_response = Column(Text, nullable=True)
    proposed_alternative_date = Column(String, nullable=True)
    proposed_alternative_time = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
