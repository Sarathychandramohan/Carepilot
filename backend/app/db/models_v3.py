"""
D:\\CarePilotAI\\backend\\app\\db\\models_v3.py

Extended SQLAlchemy ORM models for CarePilot AI v3.
Adds:
  - stable_eid column on all patient-linked tables
  - ReferenceRange table for LOINC lab normal ranges
  - All indexes required by the two-stage EHR retrieval
  
These models target the carepilot_db PostgreSQL database.
The 40-patient fixture schema (synthea/carepilot_data/db/models.py)
is kept unchanged for CI tests.
"""
from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Core EHR Tables
# ---------------------------------------------------------------------------

class Patient(Base):
    """
    One row per Synthea patient.
    stable_eid format: ehr:patient:{uuid}
    """
    __tablename__ = "patients"

    id = Column(String(36), primary_key=True)
    stable_eid = Column(String(80), nullable=False, unique=True, index=True)

    birth_date = Column(Date)
    death_date = Column(Date)
    prefix = Column(String(20))
    first_name = Column(String(100), nullable=False)
    middle_name = Column(String(100))
    last_name = Column(String(100), nullable=False)
    suffix = Column(String(20))
    marital_status = Column(String(50))
    race = Column(String(100))
    ethnicity = Column(String(100))
    gender = Column(String(20))
    birthplace = Column(String(255))
    address = Column(Text)
    city = Column(String(100))
    state = Column(String(100))
    county = Column(String(100))
    zip_code = Column(String(20))
    latitude = Column(Float)
    longitude = Column(Float)
    income = Column(Integer)

    # EHR merge flags (v3 spec)
    is_demo_fixture = Column(Boolean, default=False, nullable=False)
    # TRUE when death_date IS NULL (computed at load time)
    is_alive = Column(Boolean, default=True, nullable=False)
    # 'scale2k' | 'demo40' — which Synthea run the row came from
    source_run = Column(String(20), nullable=True)

    # Relationships
    encounters = relationship("Encounter", back_populates="patient")
    lab_results = relationship("LabResult", back_populates="patient")
    conditions = relationship("Condition", back_populates="patient")
    prescriptions = relationship("Prescription", back_populates="patient")
    allergies = relationship("Allergy", back_populates="patient")
    procedures = relationship("Procedure", back_populates="patient")
    care_plans = relationship("CarePlan", back_populates="patient")
    immunizations = relationship("Immunization", back_populates="patient")


class Encounter(Base):
    """
    Clinical encounter record.
    stable_eid format: ehr:encounter:{uuid}
    """
    __tablename__ = "encounters"
    __table_args__ = (
        Index("idx_enc_patient_start", "patient_id", "start_time"),
    )

    id = Column(String(36), primary_key=True)
    stable_eid = Column(String(80), nullable=False, unique=True, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False, index=True)
    start_time = Column(DateTime)
    stop_time = Column(DateTime)
    organization_id = Column(String(36))
    provider_id = Column(String(36))
    payer_id = Column(String(36))
    encounter_class = Column(String(50))
    code = Column(String(100))
    description = Column(Text)
    reason_code = Column(String(100))
    reason_description = Column(Text)

    patient = relationship("Patient", back_populates="encounters")
    lab_results = relationship("LabResult", back_populates="encounter")
    conditions = relationship("Condition", back_populates="encounter")
    prescriptions = relationship("Prescription", back_populates="encounter")


class LabResult(Base):
    """
    Lab observations from Synthea observations.csv.
    stable_eid format: ehr:lab:{autoincrement_id}
    Used as citation key in pipeline: source_id = stable_eid
    """
    __tablename__ = "lab_results"
    __table_args__ = (
        # Two-stage EHR retrieval: SQL filter by patient+code, ordered by recency
        Index("idx_lab_patient_code_date", "patient_id", "code", "observed_at"),
        # Citation resolution lookup
        Index("idx_lab_stable_eid", "stable_eid"),
    )

    id = Column(String(255), primary_key=True)
    stable_eid = Column(String(80), nullable=True, unique=True)  # set after insert
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    encounter_id = Column(String(36), ForeignKey("encounters.id"), nullable=True)
    observed_at = Column(DateTime, index=True)
    code = Column(String(100))                 # LOINC code
    description = Column(Text)                # Human-readable test name
    value = Column(Text)                      # Raw value (string to handle ranges)
    numeric_value = Column(Float)             # Parsed float value when applicable
    units = Column(String(50))
    value_type = Column(String(50))           # numeric, text, boolean
    is_abnormal = Column(Boolean)             # Computed against reference_ranges
    ref_min = Column(Float)                   # Denormalised from reference_ranges at load
    ref_max = Column(Float)

    patient = relationship("Patient", back_populates="lab_results")
    encounter = relationship("Encounter", back_populates="lab_results")


class Condition(Base):
    """
    Patient conditions/diagnoses from Synthea conditions.csv.
    stable_eid format: ehr:condition:{autoincrement_id}
    """
    __tablename__ = "conditions"
    __table_args__ = (
        # Active condition filter (stop_date IS NULL = active)
        Index("idx_cond_patient_stopdate", "patient_id", "stop_date"),
        Index("idx_cond_stable_eid", "stable_eid"),
    )

    id = Column(String(255), primary_key=True)
    stable_eid = Column(String(80), nullable=True, unique=True)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    encounter_id = Column(String(36), ForeignKey("encounters.id"), nullable=True)
    start_date = Column(Date)
    stop_date = Column(Date)
    system = Column(String(255))
    code = Column(String(100))
    description = Column(Text)

    patient = relationship("Patient", back_populates="conditions")
    encounter = relationship("Encounter", back_populates="conditions")


class Prescription(Base):
    """
    Medications from Synthea medications.csv.
    stable_eid format: ehr:prescription:{autoincrement_id}
    """
    __tablename__ = "prescriptions"
    __table_args__ = (
        # Active medication filter
        Index("idx_rx_patient_stopdate", "patient_id", "stop_date"),
        Index("idx_rx_stable_eid", "stable_eid"),
    )

    id = Column(String(255), primary_key=True)
    stable_eid = Column(String(80), nullable=True, unique=True)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    encounter_id = Column(String(36), ForeignKey("encounters.id"), nullable=True)
    start_date = Column(DateTime)
    stop_date = Column(DateTime)
    code = Column(String(100))
    description = Column(Text)
    dispenses = Column(Integer)
    reason_code = Column(String(100))
    reason_description = Column(Text)

    patient = relationship("Patient", back_populates="prescriptions")
    encounter = relationship("Encounter", back_populates="prescriptions")


class Allergy(Base):
    """Allergies from Synthea allergies.csv."""
    __tablename__ = "allergies"

    id = Column(String(36), primary_key=True)
    stable_eid = Column(String(80), nullable=True, unique=True, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False, index=True)
    encounter_id = Column(String(36), ForeignKey("encounters.id"), nullable=True)
    start_date = Column(Date)
    stop_date = Column(Date)
    code = Column(String(100))
    system = Column(String(100))
    description = Column(Text)
    type = Column(String(50))
    category = Column(String(50))
    reaction1 = Column(String(255))
    reaction1_description = Column(Text)
    reaction1_severity = Column(String(50))
    reaction2 = Column(String(255))
    reaction2_description = Column(Text)
    reaction2_severity = Column(String(50))

    patient = relationship("Patient", back_populates="allergies")


class Procedure(Base):
    """Procedures from Synthea procedures.csv."""
    __tablename__ = "procedures"

    id = Column(String(36), primary_key=True)
    stable_eid = Column(String(80), nullable=True, unique=True, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False, index=True)
    encounter_id = Column(String(36), ForeignKey("encounters.id"), nullable=True, index=True)
    start_time = Column(DateTime)
    stop_time = Column(DateTime)
    system = Column(String(255))
    code = Column(String(100))
    description = Column(Text)
    reason_code = Column(String(100))
    reason_description = Column(Text)

    patient = relationship("Patient", back_populates="procedures")


class CarePlan(Base):
    """Care plans from Synthea careplans.csv."""
    __tablename__ = "care_plans"

    id = Column(String(36), primary_key=True)
    stable_eid = Column(String(80), nullable=True, unique=True, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False, index=True)
    encounter_id = Column(String(36), ForeignKey("encounters.id"), nullable=True, index=True)
    start_date = Column(Date)
    stop_date = Column(Date)
    code = Column(String(100))
    description = Column(Text)
    reason_code = Column(String(100))
    reason_description = Column(Text)

    patient = relationship("Patient", back_populates="care_plans")


class Immunization(Base):
    """Immunizations from Synthea immunizations.csv."""
    __tablename__ = "immunizations"

    id = Column(String(36), primary_key=True)    # md5 composite id
    stable_eid = Column(String(80), nullable=True, unique=True, index=True)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False, index=True)
    encounter_id = Column(String(36), ForeignKey("encounters.id"), nullable=True)
    administered_at = Column(DateTime)
    code = Column(String(100))
    description = Column(Text)
    base_cost = Column(Float)

    patient = relationship("Patient", back_populates="immunizations")


# ---------------------------------------------------------------------------
# Reference Ranges (Static Seed Data)
# ---------------------------------------------------------------------------

class ReferenceRange(Base):
    """
    Normal reference ranges per LOINC code.
    Used to compute lab_results.is_abnormal at load time.
    Seeded by backend/scripts/seed_reference_ranges.py.
    """
    __tablename__ = "reference_ranges"

    code = Column(String(100), primary_key=True)   # LOINC code
    description = Column(Text)                     # Human-readable test name
    normal_min = Column(Float, nullable=True)      # None = no lower bound
    normal_max = Column(Float, nullable=True)      # None = no upper bound
    unit = Column(String(50))
    age_min = Column(Integer, nullable=True)       # None = all ages
    age_max = Column(Integer, nullable=True)
    gender = Column(String(1), nullable=True)      # 'M', 'F', None = both
    source = Column(String(100), default="synthea_defaults")


# ---------------------------------------------------------------------------
# Knowledge Base Provenance Tables
# ---------------------------------------------------------------------------

class KBDocument(Base):
    """
    One row per ingested KB document.
    Tracks provenance and license for every document in the corpus.
    """
    __tablename__ = "kb_documents"

    doc_id = Column(String(20), primary_key=True)           # KB-D01, KB-D02...
    title = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    source_name = Column(String(100), nullable=False)       # NIDDK, MedlinePlus, CDC...
    license = Column(String(100), nullable=False)           # "Public Domain", "CC BY-NC-SA 4.0"
    commercial_use_restricted = Column(Boolean, default=False)
    topic = Column(String(100))                             # diabetes, kidney, hypertension...
    retrieved_at = Column(DateTime, nullable=False)
    sha256 = Column(String(64), nullable=False, unique=True)
    snapshot_id = Column(String(20), ForeignKey("kb_snapshots.snapshot_id"), nullable=True)
    char_count = Column(Integer)
    chunk_count = Column(Integer)

    snapshot = relationship("KBSnapshot", back_populates="documents")


class KBSnapshot(Base):
    """
    Represents a frozen version of the KB corpus.
    v1 = original 18 documents (219 chunks)
    v2 = expanded corpus (500+ documents, 5000+ chunks)
    """
    __tablename__ = "kb_snapshots"

    snapshot_id = Column(String(20), primary_key=True)      # "v1", "v2"
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    chroma_collection = Column(String(100))
    bm25_index_path = Column(Text)
    doc_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    embedding_model = Column(String(100))
    frozen = Column(Boolean, default=False)                 # True = no more writes allowed

    documents = relationship("KBDocument", back_populates="snapshot")


# ---------------------------------------------------------------------------
# Conversation & Evaluation Tables (used by Pillar C)
# ---------------------------------------------------------------------------

class EvalRun(Base):
    """
    One row per harness invocation.  Created by the Pillar C harness before
    iterating over the query split, then updated (finished_at, metrics) after.

    Schema expanded in migration 002_eval_runs_expand_and_eval_run_id.
    """
    __tablename__ = "eval_runs"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    run_name         = Column(String(100), nullable=False)
    pipeline_version = Column(String(50))
    status           = Column(String(50), default="running")   # 'running' | 'completed' | 'failed'
    metrics          = Column(JSON)                             # aggregate metrics dict
    created_at       = Column(DateTime, default=datetime.datetime.utcnow)

    # ── Migration 002 additions ───────────────────────────────────────────────
    config           = Column(Text)          # JSON-serialised harness config dict
    split            = Column(String(20))    # 'dev' | 'test' | 'heldout'
    seed             = Column(Integer)       # RNG seed used
    kb_snapshot_id   = Column(String(20), ForeignKey("kb_snapshots.snapshot_id"), nullable=True)
    ehr_dataset_id   = Column(String(50))    # patient cohort identifier
    prompt_version   = Column(String(20))    # e.g. 'v1'
    thresholds       = Column(JSON)          # {faithfulness_threshold, nli_entailment_threshold, …}
    started_at       = Column(DateTime)      # when harness began
    finished_at      = Column(DateTime)      # when harness completed (NULL while still running)

    # Relationships
    consultations    = relationship("Consultation", back_populates="eval_run")
    kb_snapshot      = relationship("KBSnapshot")


class Consultation(Base):
    """
    Full pipeline run record. Each patient query creates one consultation row.
    Tracks all pipeline stages from P1 through P10.
    """
    __tablename__ = "consultations"

    id = Column(String(36), primary_key=True)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False, index=True)


    # P1: Raw input
    query_text = Column(Text, nullable=False)
    query_received_at = Column(DateTime, default=datetime.datetime.utcnow)

    # P2: Red-flag
    redflag_hit_type = Column(String(20))          # "firm", "soft", "none"
    redflag_category = Column(String(100))
    redflag_soft_hits = Column(JSON)               # list of soft hit descriptions

    # P3: Normalization
    normalized_query = Column(Text)
    normalization_trace = Column(JSON)

    # P4: Classification
    intent = Column(String(50))
    intent_prob = Column(Float)
    intent_probs_json = Column(JSON)               # {"lab_result_query": 0.92, ...}
    urgency = Column(String(10))                   # "routine", "soon", "urgent"
    urgency_score = Column(Float)
    urgency_probs_json = Column(JSON)
    urgency_final = Column(String(10))             # after red-flag override

    # B2 addition: urgency agreement log
    urgency_agreement = Column(String(20))
    # "agree" | "redflag_upgraded" | "self_reported" (no_classifier arm)

    # P5: Retrieval
    ehr_chunks_json = Column(JSON)                 # list of retrieved EHR fact snippets
    kb_chunks_json = Column(JSON)                  # list of retrieved KB chunks
    retrieval_config = Column(String(30))          # "ehr_and_kb", "kb_only", "unified_ehr_kb"
    ablation_arm = Column(String(30))              # full | no_ehr | no_classifier | unified_context

    # B3 additions: retrieval provenance + D17 flags
    retrieval_trace_json = Column(JSON)
    # {ehr_query_loinc_codes, ehr_rows_returned, ehr_outlier_count,
    #  ehr_chunk_ids, kb_rrf_top_chunks}
    patient_ehr_mismatch_flag = Column(Boolean, default=False)   # D17a
    missing_context_flag = Column(Boolean, default=False)        # D17b
    outlier_chunk_count = Column(Integer, default=0)

    # P6: Generation
    ai_draft_json = Column(JSON)                   # {sentences: [{text, citations}]}
    llm_model = Column(String(100))
    prompt_version = Column(String(20))
    generation_latency_ms = Column(Integer)

    # B4 additions: LLM self-report + edit memory (D6)
    llm_urgency_self_reported = Column(String(10))
    # LLM's own urgency output — always logged; authoritative only in no_classifier arm
    edit_memory_used = Column(Boolean, default=False)
    edit_memory_json = Column(JSON)

    # P7: Validation
    faithfulness_score = Column(Float)
    faithfulness_details = Column(JSON)
    citation_validity_score = Column(Float)
    citation_entailment_score = Column(Float)
    validation_status = Column(String(40))
    # "passed" | "passed_with_warning" | "passed_with_outlier_caveat" | "manual_required"

    # B5 addition: outlier validation flag
    has_outlier_only_sentence = Column(Boolean, default=False)

    # P8: Doctor queue
    thread_status = Column(String(30), default="awaiting_doctor")
    is_high_priority = Column(Boolean, default=False)
    is_red_flag_override = Column(Boolean, default=False)
    is_eval = Column(Boolean, default=False, nullable=False)

    # P9: Doctor review
    doctor_action = Column(String(20))             # "approved", "edited", "rejected"
    reject_reason = Column(String(50))
    final_response = Column(Text)
    messages_json = Column(JSON)                   # multi-turn thread
    edit_distance_chars = Column(Integer)
    edit_distance_words = Column(Integer)
    # Per-consultation raw weighted sum W_k = Σ w_i * c_{k,i}
    # NOT the Section S9 aggregate (that is computed across reviews at analysis time)
    consultation_edit_weight = Column(Float)
    edit_categories_json = Column(JSON)
    # All 12 keys always present:
    # {factual_correction, missing_ehr_fact, wrong_ehr_fact, unsupported_medical_claim,
    #  citation_error, urgency_correction, missing_caution, tone_change,
    #  unnecessary_content, retrieval_error, no_change, other}
    doctor_review_seconds = Column(Integer)
    doctor_reviewed_at = Column(DateTime)

    # Pillar C: supplementary edit distance ratios
    edr_char = Column(Float)   # edit_distance_chars / max(|draft|, |final|)
    edr_word = Column(Float)   # word-level EDR

    # P10: Patient delivery
    patient_notified_at = Column(DateTime)
    delivered_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # ── Migration 002: Pillar C run tracking ─────────────────────────────────
    # NULL for all pre-harness consultations; set by the eval harness at row creation.
    eval_run_id = Column(Integer, ForeignKey("eval_runs.id"), nullable=True, index=True)

    patient  = relationship("Patient")
    eval_run = relationship("EvalRun", back_populates="consultations")


