"""
D:\\CarePilotAI\\backend\\app\\pipeline\\retrieve_ehr.py

B3.1 — EHR Retrieval (Two-Stage Pipeline, Pillar B)

Fetches patient-specific clinical facts from PostgreSQL based on intent
and normalized concepts. Surfaces is_outlier on every returned chunk.

Skipped entirely when ablation_config == "no_ehr".
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field, asdict
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# EHRChunk — the contract between B3.1 and B4/B5
# ---------------------------------------------------------------------------

@dataclass
class EHRChunk:
    stable_eid: str          # citation key: "ehr:lab:456"
    source_type: str         # "lab_result" | "condition" | "prescription" | "encounter"
    label: str               # "Serum Creatinine"
    display_value: str       # "1.4 mg/dL (↑ above normal 0.6–1.2)"
    date_str: str            # "2023-08-10"
    is_abnormal: bool
    is_outlier: bool         # always present — drives B5 outlier caveat logic
    outlier_annotation: str | None  # set when is_outlier=True
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw", None)
        return d

    def prompt_text(self) -> str:
        """Formatted text for LLM prompt context block."""
        base = f"[{self.source_type.upper()}] {self.label}: {self.display_value} ({self.date_str})"
        if self.is_outlier:
            base += f"\n  {self.outlier_annotation}"
        return base


# ---------------------------------------------------------------------------
# Intent → query routing configuration
# ---------------------------------------------------------------------------

# LOINC code groups for intent-driven retrieval
LAB_INTENT_CODES: dict[str, list[str]] = {
    "lab_result_query":    [],   # codes come from normalized_concepts
    "medication_query":    [     # always add renal safety markers for meds
        "2160-0",   # Creatinine [Mass/volume] in Serum or Plasma
        "33914-3",  # eGFR
        "2823-3",   # Potassium
        "17861-6",  # Calcium
    ],
    "symptom_report":      [],   # all resolved concepts
    "general_health_info": [],   # conditions + prescriptions — no lab LOINC filter
    "followup_appointment": [],  # encounters only
}

EHR_RETRIEVAL_K = 5  # max rows per category; overridden by settings


def _format_display_value(
    value: float | None,
    numeric: float | None,
    units: str | None,
    ref_min: float | None,
    ref_max: float | None,
    is_abnormal: bool,
) -> str:
    """Human-readable lab result string with abnormal indicator."""
    val_str = str(value or numeric or "N/A")
    unit_str = f" {units}" if units else ""
    if ref_min is not None and ref_max is not None:
        ref_str = f" (normal {ref_min}–{ref_max})"
    else:
        ref_str = ""
    flag = " ↑" if is_abnormal and numeric and ref_max and numeric > ref_max else (
           " ↓" if is_abnormal and numeric and ref_min and numeric < ref_min else "")
    return f"{val_str}{unit_str}{flag}{ref_str}"


def retrieve_ehr(
    patient_id: str,
    normalized_concepts: list[dict],
    intent: str,
    db: Session,
    k: int = EHR_RETRIEVAL_K,
    secondary_intent: str | None = None,
    is_dual_intent: bool = False,
) -> list[EHRChunk]:
    """
    Main entry point for B3.1 EHR retrieval.

    Args:
        patient_id:          Stable patient UUID
        normalized_concepts: Output of normalize_query_concepts()
        intent:              Classified intent string
        db:                  SQLAlchemy session
        k:                   Max rows per category
        secondary_intent:    Optional secondary intent for dual-intent routing (D-007)
        is_dual_intent:      Flag indicating adverse reaction / multi-intent ambiguity

    Returns:
        List of EHRChunk objects sorted by date descending.
        Every chunk carries is_outlier and outlier_annotation.
    """
    chunks: list[EHRChunk] = []

    active_intents = {intent}
    if is_dual_intent and secondary_intent:
        active_intents.add(secondary_intent)

    # Extract LOINC codes from normalized concepts
    concept_loinc = []
    for c in normalized_concepts:
        if c.get("domain") in ("lab", "condition", "medication"):
            if c.get("loinc_code"):
                concept_loinc.append(c["loinc_code"])
            elif c.get("concept_id") and "LOINC:" in c["concept_id"]:
                concept_loinc.append(c["concept_id"].split("LOINC:")[1])
            elif c.get("code"):
                concept_loinc.append(c["code"])

    # Add intent-driven base codes
    extra_codes: list[str] = []
    for it in active_intents:
        extra_codes.extend(LAB_INTENT_CODES.get(it, []))
    all_loinc = list(dict.fromkeys(concept_loinc + extra_codes))  # dedupe, preserve order

    # ── Lab Results ─────────────────────────────────────────────────────────
    if any(it in ("lab_result_query", "medication_query", "symptom_report") for it in active_intents) and all_loinc:
        rows = db.execute(
            text("""
                SELECT
                    lr.id, lr.stable_eid, lr.code, lr.description,
                    lr.numeric_value, lr.value, lr.units,
                    lr.observed_at, lr.is_abnormal, lr.is_outlier,
                    COALESCE(lr.ref_min, rr.ref_min) AS ref_min,
                    COALESCE(lr.ref_max, rr.ref_max) AS ref_max
                FROM lab_results lr
                LEFT JOIN reference_ranges rr
                    ON rr.code = lr.code
                WHERE lr.patient_id = :pid
                  AND lr.code = ANY(:codes)
                ORDER BY lr.observed_at DESC
                LIMIT :k
            """),
            {"pid": patient_id, "codes": all_loinc, "k": k},
        ).fetchall()

        for row in rows:
            is_out = bool(row.is_outlier)
            display = _format_display_value(
                row.value, row.numeric_value, row.units,
                row.ref_min, row.ref_max, bool(row.is_abnormal)
            )
            chunks.append(EHRChunk(
                stable_eid=row.stable_eid or f"ehr:lab:{row.id}",
                source_type="lab_result",
                label=row.description or row.code,
                display_value=display,
                date_str=str(row.observed_at)[:10] if row.observed_at else "unknown",
                is_abnormal=bool(row.is_abnormal),
                is_outlier=is_out,
                outlier_annotation=(
                    "[OUTLIER: value may reflect simulation artifact — "
                    "do not state as plain clinical fact without caveat]"
                ) if is_out else None,
                raw=dict(row._mapping),
            ))

    # ── Active Conditions ────────────────────────────────────────────────────
    if any(it in ("symptom_report", "general_health_info", "followup_appointment") for it in active_intents):
        rows = db.execute(
            text("""
                SELECT id, stable_eid, code, description, start_date, stop_date
                FROM conditions
                WHERE patient_id = :pid
                  AND stop_date IS NULL
                ORDER BY start_date DESC
                LIMIT :k
            """),
            {"pid": patient_id, "k": k},
        ).fetchall()

        for row in rows:
            chunks.append(EHRChunk(
                stable_eid=row.stable_eid or f"ehr:condition:{row.id}",
                source_type="condition",
                label=row.description or row.code,
                display_value=f"Active since {str(row.start_date)[:10] if row.start_date else 'unknown'}",
                date_str=str(row.start_date)[:10] if row.start_date else "unknown",
                is_abnormal=False,
                is_outlier=False,
                outlier_annotation=None,
                raw=dict(row._mapping),
            ))

    # ── Active Prescriptions ─────────────────────────────────────────────────
    if any(it in ("medication_query", "general_health_info") for it in active_intents):
        rows = db.execute(
            text("""
                SELECT id, stable_eid, code, description, start_date, stop_date
                FROM prescriptions
                WHERE patient_id = :pid
                  AND stop_date IS NULL
                ORDER BY start_date DESC
                LIMIT :k
            """),
            {"pid": patient_id, "k": k},
        ).fetchall()

        for row in rows:
            chunks.append(EHRChunk(
                stable_eid=row.stable_eid or f"ehr:prescription:{row.id}",
                source_type="prescription",
                label=row.description or row.code,
                display_value=f"Active since {str(row.start_date)[:10] if row.start_date else 'unknown'}",
                date_str=str(row.start_date)[:10] if row.start_date else "unknown",
                is_abnormal=False,
                is_outlier=False,
                outlier_annotation=None,
                raw=dict(row._mapping),
            ))

    # ── Recent Encounters ────────────────────────────────────────────────────
    if any(it == "followup_appointment" for it in active_intents):
        rows = db.execute(
            text("""
                SELECT id, stable_eid, encounter_class, description, start_time, stop_time
                FROM encounters
                WHERE patient_id = :pid
                ORDER BY start_time DESC
                LIMIT 3
            """),
            {"pid": patient_id},
        ).fetchall()

        for row in rows:
            chunks.append(EHRChunk(
                stable_eid=row.stable_eid or f"ehr:encounter:{row.id}",
                source_type="encounter",
                label=row.description or row.encounter_class or "Encounter",
                display_value=f"Visit on {str(row.start_time)[:10] if row.start_time else 'unknown'}",
                date_str=str(row.start_time)[:10] if row.start_time else "unknown",
                is_abnormal=False,
                is_outlier=False,
                outlier_annotation=None,
                raw=dict(row._mapping),
            ))

    # Sort all chunks by date descending (mixed types)
    def _date_key(c: EHRChunk) -> str:
        return c.date_str if c.date_str != "unknown" else "1900-01-01"

    chunks.sort(key=_date_key, reverse=True)
    return chunks
