"""
D:\\CarePilotAI\\backend\\app\\pipeline\\normalize.py

Terminology Normalization Engine (S4 / P3)
Normalizes patient colloquial expressions into canonical clinical concepts.

Architecture:
- Tier 1: Exact / Regex clinical dictionary (SNOMED-CT, LOINC, RxNorm)
- Tier 2: Dense embedding similarity against concept anchors (bge-small)
- Negation Detector: Flags negated concepts
- Temporal Tagger: Extracts symptom onset and duration spans
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Tier 1 Dictionary: Layperson / Clinical Phrase -> Canonical Concept
# ---------------------------------------------------------------------------

CONCEPT_DICTIONARY: list[dict[str, Any]] = [
    # Labs (LOINC)
    {"pattern": r"\b(creatinine|serum\s+creatinine|creatnine|cr)\b", "concept_id": "LOINC:2160-0", "label": "Creatinine", "domain": "lab"},
    {"pattern": r"\b(a1c|hba1c|hemoglobin\s+a1c|glycated\s+hemoglobin)\b", "concept_id": "LOINC:4548-4", "label": "HbA1c", "domain": "lab"},
    {"pattern": r"\b(egfr|gfr|filtration\s+rate|kidney\s+function\s+rate)\b", "concept_id": "LOINC:33914-3", "label": "eGFR", "domain": "lab"},
    {"pattern": r"\b(cholesterol|total\s+cholesterol|lipid\s+panel)\b", "concept_id": "LOINC:2093-3", "label": "Total Cholesterol", "domain": "lab"},
    {"pattern": r"\b(ldl|bad\s+cholesterol|low\s+density\s+lipoprotein)\b", "concept_id": "LOINC:2089-1", "label": "LDL Cholesterol", "domain": "lab"},
    {"pattern": r"\b(hdl|good\s+cholesterol)\b", "concept_id": "LOINC:2085-9", "label": "HDL Cholesterol", "domain": "lab"},
    {"pattern": r"\b(microalbumin|albumin\s+in\s+urine|urine\s+protein)\b", "concept_id": "LOINC:14959-1", "label": "Urine Albumin", "domain": "lab"},
    {"pattern": r"\b(potassium|serum\s+potassium|k\+?)\b", "concept_id": "LOINC:2823-3", "label": "Potassium", "domain": "lab"},
    {"pattern": r"\b(sodium|na\+?)\b", "concept_id": "LOINC:2947-0", "label": "Sodium", "domain": "lab"},
    {"pattern": r"\b(glucose|blood\s+sugar|fasting\s+sugar)\b", "concept_id": "LOINC:2345-7", "label": "Glucose", "domain": "lab"},

    # Conditions (SNOMED)
    {"pattern": r"\b(chronic\s+kidney\s+disease|ckd|kidney\s+disease|renal\s+disease)\b", "concept_id": "SNOMED:709044004", "label": "Chronic Kidney Disease", "domain": "condition"},
    {"pattern": r"\b(hypertension|high\s+blood\s+pressure|htn|elevated\s+bp)\b", "concept_id": "SNOMED:38341003", "label": "Hypertension", "domain": "condition"},
    {"pattern": r"\b(diabetes|type\s+2\s+diabetes|diabetic|t2d|dm2)\b", "concept_id": "SNOMED:44054006", "label": "Type 2 Diabetes Mellitus", "domain": "condition"},
    {"pattern": r"\b(hyperlipidemia|high\s+cholesterol|hypercholesterolemia)\b", "concept_id": "SNOMED:55822004", "label": "Hyperlipidemia", "domain": "condition"},

    # Medications (RxNorm)
    {"pattern": r"\b(lisinopril|prinivil|zestril)\b", "concept_id": "RxNorm:29046", "label": "Lisinopril", "domain": "medication"},
    {"pattern": r"\b(metformin|glucophage)\b", "concept_id": "RxNorm:6809", "label": "Metformin", "domain": "medication"},
    {"pattern": r"\b(furosemide|lasix)\b", "concept_id": "RxNorm:4603", "label": "Furosemide", "domain": "medication"},
    {"pattern": r"\b(atorvastatin|lipitor)\b", "concept_id": "RxNorm:83367", "label": "Atorvastatin", "domain": "medication"},
    {"pattern": r"\b(amlodipine|norvasc)\b", "concept_id": "RxNorm:17767", "label": "Amlodipine", "domain": "medication"},
    {"pattern": r"\b(losartan|cozaar)\b", "concept_id": "RxNorm:5224", "label": "Losartan", "domain": "medication"},
    {"pattern": r"\b(empagliflozin|jardiance)\b", "concept_id": "RxNorm:1545653", "label": "Empagliflozin", "domain": "medication"},
    {"pattern": r"\b(insulin|lantus|glargine)\b", "concept_id": "RxNorm:274783", "label": "Insulin Glargine", "domain": "medication"},
    {"pattern": r"\b(albuterol|ventolin|proair)\b", "concept_id": "RxNorm:435", "label": "Albuterol", "domain": "medication"},
    {"pattern": r"\b(omeprazole|prilosec)\b", "concept_id": "RxNorm:7646", "label": "Omeprazole", "domain": "medication"},
]

# Negation Patterns
NEGATION_REGEX = re.compile(
    r"\b(no|not|never|denies|denied|without|negative\s+for|none)\b",
    re.IGNORECASE
)

# Temporal Patterns
TEMPORAL_REGEXES = [
    (r"\b(for\s+\d+\s+(days?|weeks?|months?|years?))\b", "duration"),
    (r"\b(since\s+(yesterday|last\s+week|last\s+month|monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b", "anchor"),
    (r"\b(\d+\s+(days?|weeks?|months?|years?)\s+ago)\b", "relative_past"),
    (r"\b(in\s+the\s+morning|at\s+night|in\s+the\s+evening|after\s+meals)\b", "diurnal"),
]


def extract_temporal_tags(text: str) -> list[dict[str, str]]:
    """Extracts duration and temporal anchor tags from text."""
    tags = []
    for pattern, tag_type in TEMPORAL_REGEXES:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            tags.append({
                "span": match.group(0),
                "type": tag_type,
                "start": match.start(),
                "end": match.end(),
            })
    return tags


def normalize_query_concepts(query_text: str) -> dict[str, Any]:
    """
    Normalizes a patient message:
    1. Identifies canonical concepts via Tier 1 clinical dictionary.
    2. Identifies negation status for each concept.
    3. Extracts temporal expressions.
    Returns:
    {
        "normalized_text": str,
        "resolved_concepts": list[dict],
        "temporal_tags": list[dict],
        "has_negated_concepts": bool
    }
    """
    text = query_text.strip()
    resolved_concepts = []

    for item in CONCEPT_DICTIONARY:
        for match in re.finditer(item["pattern"], text, re.IGNORECASE):
            start = match.start()
            end = match.end()

            # Check if this concept span is negated
            lookback = text[max(0, start - 30):start]
            is_negated = bool(NEGATION_REGEX.search(lookback))

            resolved_concepts.append({
                "matched_text": match.group(0),
                "concept_id": item["concept_id"],
                "canonical_label": item["label"],
                "domain": item["domain"],
                "is_negated": is_negated,
                "tier": "Tier1_Dictionary",
                "start": start,
                "end": end,
            })

    temporal_tags = extract_temporal_tags(text)

    return {
        "raw_query": text,
        "resolved_concepts": resolved_concepts,
        "temporal_tags": temporal_tags,
        "has_negated_concepts": any(c["is_negated"] for c in resolved_concepts),
    }
