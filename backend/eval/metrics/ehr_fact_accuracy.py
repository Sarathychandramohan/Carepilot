"""
D:\\CarePilotAI\\backend\\eval\\metrics\\ehr_fact_accuracy.py

EHR-Fact Accuracy Metric for Pillar C evaluation.

Scope (per C0 decision D-C3):
  - Medication names   → fuzzy-matched against patient prescriptions table
  - Lab values         → matched against lab_results (code + approximate date
                         + numeric value within tolerance)
  - Condition names    → fuzzy-matched against patient conditions table

Design constraints (deliberate):
  - ENTIRELY RULE-BASED and deterministic — zero LLM calls here.
  - Every extraction step is auditable and reproducible.
  - Applies ONLY to consultations with a patient_id (patient-specific queries).

⚠ CAVEAT: Reference-range coverage is 16/40 (40%) of the LOINC codes present
in the patient dataset. Lab-value matching depends on lab_results rows, NOT
on reference ranges — but the coverage gap means some abnormal values won't
have a reference_ranges context. This caveat is printed whenever lab-value
matching is involved. See docs/PILLAR_C_DECISIONS.md for rationale.

Output schema (per consultation):
  {
    "n_facts_extracted": int,
    "n_medications_extracted": int,
    "n_labs_extracted": int,
    "n_conditions_extracted": int,
    "n_facts_matched": int,
    "n_medications_matched": int,
    "n_labs_matched": int,
    "n_conditions_matched": int,
    "fact_accuracy": float,     # n_facts_matched / n_facts_extracted (NaN if 0)
    "med_accuracy": float,
    "lab_accuracy": float,
    "condition_accuracy": float,
    "unmatched_facts": list[dict],
    "lab_coverage_caveat": bool,   # True when any lab facts were extracted
  }
"""
from __future__ import annotations

import re
import json
import math
import datetime
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Fuzzy string matching (no third-party library required beyond stdlib)
# ---------------------------------------------------------------------------

def _normalize_name(s: str) -> str:
    """Lowercase, remove punctuation, collapse whitespace."""
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _token_overlap_ratio(a: str, b: str) -> float:
    """
    Jaccard token overlap: |A ∩ B| / |A ∪ B|
    Works well for short drug / condition names where word order can vary.
    """
    ta = set(_normalize_name(a).split())
    tb = set(_normalize_name(b).split())
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _fuzzy_match(query: str, candidates: list[str], threshold: float = 0.5) -> bool:
    """
    Returns True if any candidate string matches the query:
    1. Query tokens are a subset of candidate tokens (e.g. 'metformin' in 'metformin 500 mg oral tablet')
    2. Jaccard token overlap ratio >= threshold
    """
    qn = _normalize_name(query)
    q_tokens = set(qn.split())
    for c in candidates:
        cn = _normalize_name(c)
        c_tokens = set(cn.split())
        # Check token containment: every token in the query is in candidate (case-insensitive)
        if q_tokens and q_tokens.issubset(c_tokens):
            # Special guard: if query is a single common generic word like 'kidney', check threshold
            containment_jaccard = len(q_tokens & c_tokens) / len(q_tokens | c_tokens)
            if containment_jaccard >= threshold or len(q_tokens) >= 2 or threshold <= 0.5:
                return True
        if _token_overlap_ratio(qn, cn) >= threshold:
            return True
    return False






# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

# ── Medication extraction ────────────────────────────────────────────────────

# Drug classes and common generic/brand names to seed extraction
_KNOWN_DRUG_MARKERS = [
    # Units / dose markers that often follow a drug name
    r"(?P<med>[A-Za-z][A-Za-z\s\-]{2,40}?)\s+\d+\s*(?:mg|mcg|ml|units?|iu)\b",
    # "taking X", "prescribed X", "started X", "stopped X"
    r"(?:taking|prescribed|started|stopped|given|receives?|on)\s+(?P<med>[A-Za-z][A-Za-z\s\-]{2,35}?)(?=\s*[\.,;]|\s+\d|\s*$)",
    # "X therapy", "X treatment"
    r"(?P<med>[A-Za-z][A-Za-z\s\-]{2,35}?)\s+(?:therapy|treatment|medication|drug)\b",
]

# Common two-word combinations to exclude (false positive guard)
_MEDICATION_EXCLUSIONS = {
    "the patient", "the doctor", "the drug", "the medication", "the prescription",
    "high blood", "low blood", "blood pressure", "blood sugar", "blood glucose",
    "heart rate", "kidney disease", "this medication", "your doctor", "your medication",
    "as prescribed", "oral tablet", "daily dose",
}


def extract_medications_from_text(text: str) -> list[str]:
    """
    Rule-based extraction of medication names from draft text.
    Returns a deduplicated list of candidate medication strings.
    """
    found: set[str] = set()

    # Pattern 1: dose markers
    for m in re.finditer(
        r"([A-Z][A-Za-z\-]{2,40}(?:\s+[A-Za-z]{2,20})?)\s+\d+\s*(?:mg|mcg|ml|units?|IU)\b",
        text,
    ):
        candidate = m.group(1).strip()
        if _normalize_name(candidate) not in _MEDICATION_EXCLUSIONS:
            found.add(candidate)

    # Pattern 2: verb trigger
    for m in re.finditer(
        r"(?:taking|prescribed|started|stopped|given|receives?)\s+([A-Z][A-Za-z\-]{2,35}(?:\s+[A-Za-z]{2,20})?)",
        text,
        re.IGNORECASE,
    ):
        candidate = m.group(1).strip()
        if _normalize_name(candidate) not in _MEDICATION_EXCLUSIONS and len(candidate) > 3:
            found.add(candidate)

    # Deduplicate near-identical items (one is a prefix of another)
    result: list[str] = []
    sorted_found = sorted(found, key=len, reverse=True)
    for item in sorted_found:
        if not any(item.lower() in existing.lower() for existing in result):
            result.append(item)
    return result


# ── Lab value extraction ─────────────────────────────────────────────────────

@dataclass
class ExtractedLabValue:
    raw_text: str
    quantity: str          # e.g. "creatinine", "eGFR", "HbA1c"
    value: float
    unit: str
    approx_date: datetime.date | None = None   # if mentioned in draft text


# Common lab quantities mapped to their common LOINC display names
_LAB_QUANTITY_PATTERNS = [
    # (display_name, regex_for_name_in_text)
    ("creatinine",      r"\bcreatinine\b"),
    ("eGFR",            r"\b(?:e?GFR|egfr|glomerular\s+filtration\s+rate)\b"),
    ("HbA1c",           r"\b(?:HbA1c|Hba1c|hemoglobin\s+a1c|haemoglobin\s+a1c|A1C|a1c)\b"),
    ("glucose",         r"\b(?:glucose|blood\s+sugar|blood\s+glucose)\b"),
    ("potassium",       r"\b(?:potassium|K\+)\b"),
    ("sodium",          r"\b(?:sodium|Na\+)\b"),
    ("LDL",             r"\b(?:LDL|ldl|low.density\s+lipoprotein)\b"),
    ("HDL",             r"\b(?:HDL|hdl|high.density\s+lipoprotein)\b"),
    ("triglycerides",   r"\b(?:triglycerides?|TG)\b"),
    ("urine protein",   r"\b(?:urine\s+protein|uACR|urine\s+albumin|albumin.creatinine\s+ratio|proteinuria)\b"),
    ("BUN",             r"\b(?:BUN|blood\s+urea\s+nitrogen|urea)\b"),
    ("hemoglobin",      r"\b(?:hemoglobin|haemoglobin|Hgb|Hb)\b"),
    ("TSH",             r"\b(?:TSH|thyroid\s+stimulating\s+hormone)\b"),
    ("calcium",         r"\b(?:calcium|Ca)\b"),
    ("phosphorus",      r"\b(?:phosphorus|phosphate|PO4)\b"),
    ("CBC",             r"\b(?:CBC|complete\s+blood\s+count)\b"),
]

_VALUE_PATTERN = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mg/dL|mL/min(?:/1\.73\s*m2)?|mmol/L|g/dL|%|mEq/L|IU/mL|ng/mL|U/mL|mIU/mL|mg/g)?",
    re.IGNORECASE,
)

# Approximate date patterns for lab mentions in drafts
_DATE_PATTERNS = [
    (r"(?:on\s+|dated?\s+)(\w+\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
    (r"(\d{1,2}/\d{1,2}/\d{4})", "%m/%d/%Y"),
    (r"(\d{4}-\d{2}-\d{2})", "%Y-%m-%d"),
]


def _parse_approx_date(text_fragment: str) -> datetime.date | None:
    for pattern, fmt in _DATE_PATTERNS:
        m = re.search(pattern, text_fragment, re.IGNORECASE)
        if m:
            try:
                return datetime.datetime.strptime(m.group(1).replace(",", ""), fmt.replace(",", "")).date()
            except ValueError:
                continue
    return None


def extract_lab_values_from_text(text: str) -> list[ExtractedLabValue]:
    """
    Extracts lab quantity + numeric value pairs from draft text.
    Returns ExtractedLabValue items (possibly without dates).
    """
    results: list[ExtractedLabValue] = []
    seen_positions: set[int] = set()

    for display_name, qty_pattern in _LAB_QUANTITY_PATTERNS:
        for qty_match in re.finditer(qty_pattern, text, re.IGNORECASE):
            # Look for a value within 80 characters after the quantity name
            window_start = qty_match.end()
            window = text[window_start: window_start + 80]
            val_m = _VALUE_PATTERN.search(window)
            if not val_m:
                continue
            abs_start = window_start + val_m.start()
            if abs_start in seen_positions:
                continue
            seen_positions.add(abs_start)

            try:
                value = float(val_m.group("value"))
            except (TypeError, ValueError):
                continue

            unit = val_m.group("unit") or ""
            # Look for a nearby date in the surrounding 150-char context
            ctx_start = max(0, qty_match.start() - 50)
            ctx = text[ctx_start: window_start + 80]
            approx_date = _parse_approx_date(ctx)

            results.append(ExtractedLabValue(
                raw_text=text[qty_match.start(): abs_start + len(val_m.group(0))].strip(),
                quantity=display_name,
                value=value,
                unit=unit,
                approx_date=approx_date,
            ))

    return results


# ── Condition extraction ─────────────────────────────────────────────────────

# Lightweight trigger phrases that precede condition mentions in clinical text
_CONDITION_TRIGGER = re.compile(
    r"(?:diagnosed\s+with|history\s+of|presents?\s+with|"
    r"suffering\s+from|living\s+with|known\s+case\s+of|treatment\s+for)\s+"
    r"([A-Za-z0-9\s\-]{3,60}?)(?=[.,;]|\s+(?:which|that|and|but|or|since|for)|\s*$)",
    re.IGNORECASE,
)

_CONDITION_EXCLUSIONS = {
    "the above", "this condition", "the condition", "the disease", "it",
    "them", "this", "these symptoms", "my symptoms", "your symptoms",
}



def extract_conditions_from_text(text: str) -> list[str]:
    """
    Rule-based extraction of condition/diagnosis mentions from draft text.
    """
    found: set[str] = set()
    for m in _CONDITION_TRIGGER.finditer(text):
        candidate = m.group(1).strip()
        if len(candidate) >= 4 and _normalize_name(candidate) not in _CONDITION_EXCLUSIONS:
            found.add(candidate)
    return list(found)


# ---------------------------------------------------------------------------
# EHR lookup helpers
# ---------------------------------------------------------------------------

def _get_patient_prescriptions(patient_id: str, db: Session) -> list[str]:
    """Returns all prescription descriptions for the patient."""
    rows = db.execute(
        text("SELECT description FROM prescriptions WHERE patient_id = :pid"),
        {"pid": patient_id},
    ).fetchall()
    return [r[0] for r in rows if r[0]]


def _get_patient_lab_results(patient_id: str, db: Session) -> list[dict]:
    """
    Returns lab result rows for patient:
    {code, description, numeric_value, result_date (date)}
    """
    rows = db.execute(
        text("""
            SELECT code, description, numeric_value,
                   DATE(observed_at) AS result_date
            FROM lab_results
            WHERE patient_id = :pid
              AND numeric_value IS NOT NULL
        """),
        {"pid": patient_id},
    ).fetchall()
    return [
        {
            "code": r[0],
            "description": r[1],
            "value": float(r[2]),
            "date": r[3],
        }
        for r in rows
    ]


def _get_patient_conditions(patient_id: str, db: Session) -> list[str]:
    """Returns all condition descriptions for patient (active + inactive)."""
    rows = db.execute(
        text("SELECT description FROM conditions WHERE patient_id = :pid"),
        {"pid": patient_id},
    ).fetchall()
    return [r[0] for r in rows if r[0]]


# ---------------------------------------------------------------------------
# Matching logic
# ---------------------------------------------------------------------------

_LAB_VALUE_TOLERANCE = 0.15     # 15% relative tolerance for numeric matching
_LAB_DATE_WINDOW_DAYS = 90      # ±90 days for approximate date matching


_LAB_ALIASES: dict[str, list[str]] = {
    "hba1c": ["hemoglobin a1c", "haemoglobin a1c", "glycated hemoglobin", "a1c"],
    "egfr": ["glomerular filtration rate", "gfr"],
    "creatinine": ["serum creatinine"],
    "ldl": ["low density lipoprotein", "ldl cholesterol"],
    "hdl": ["high density lipoprotein", "hdl cholesterol"],
}


def _match_lab_value(
    extracted: ExtractedLabValue,
    ehr_labs: list[dict],
) -> bool:
    """
    Returns True if the extracted lab value is plausibly matched in EHR rows.
    Matching criteria:
      1. Quantity name fuzzy-matches the lab_results.description (including aliases)
      2. Numeric value within ±LAB_VALUE_TOLERANCE relative
      3. If extracted date present: within ±LAB_DATE_WINDOW_DAYS
    """
    qty_lower = extracted.quantity.lower()
    search_names = [extracted.quantity] + _LAB_ALIASES.get(qty_lower, [])

    for row in ehr_labs:
        # Name match across search names and aliases
        matched_name = any(
            _fuzzy_match(name, [row["description"]], threshold=0.3)
            for name in search_names
        )
        if not matched_name:
            continue
        # Value match
        if row["value"] == 0:
            continue
        rel_diff = abs(extracted.value - row["value"]) / abs(row["value"])
        if rel_diff > _LAB_VALUE_TOLERANCE:
            continue
        # Date match (if date was extracted)
        if extracted.approx_date and row["date"]:
            delta = abs((extracted.approx_date - row["date"]).days)
            if delta > _LAB_DATE_WINDOW_DAYS:
                continue
        return True
    return False



# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

LAB_COVERAGE_CAVEAT_MSG = (
    "⚠ CAVEAT: Reference-range coverage is 16/40 (40%) of LOINC codes present "
    "in this patient dataset. Lab-value matching depends on lab_results rows "
    "(not reference_ranges), so this metric is unaffected by the coverage gap. "
    "However, interpretive context (normal vs abnormal) cannot be provided for "
    "the 24 uncovered LOINC codes."
)


@dataclass
class EHRFactAccuracyResult:
    n_facts_extracted: int = 0
    n_medications_extracted: int = 0
    n_labs_extracted: int = 0
    n_conditions_extracted: int = 0
    n_facts_matched: int = 0
    n_medications_matched: int = 0
    n_labs_matched: int = 0
    n_conditions_matched: int = 0
    fact_accuracy: float = float("nan")
    med_accuracy: float = float("nan")
    lab_accuracy: float = float("nan")
    condition_accuracy: float = float("nan")
    unmatched_facts: list[dict] = field(default_factory=list)
    lab_coverage_caveat: bool = False

    def to_dict(self) -> dict:
        return {
            "n_facts_extracted": self.n_facts_extracted,
            "n_medications_extracted": self.n_medications_extracted,
            "n_labs_extracted": self.n_labs_extracted,
            "n_conditions_extracted": self.n_conditions_extracted,
            "n_facts_matched": self.n_facts_matched,
            "n_medications_matched": self.n_medications_matched,
            "n_labs_matched": self.n_labs_matched,
            "n_conditions_matched": self.n_conditions_matched,
            "fact_accuracy": self.fact_accuracy,
            "med_accuracy": self.med_accuracy,
            "lab_accuracy": self.lab_accuracy,
            "condition_accuracy": self.condition_accuracy,
            "unmatched_facts": self.unmatched_facts,
            "lab_coverage_caveat": self.lab_coverage_caveat,
        }


def compute_ehr_fact_accuracy(
    consultation_row: Any,
    db: Session,
    verbose: bool = False,
) -> EHRFactAccuracyResult:
    """
    Compute EHR-fact accuracy for a single consultation.

    Args:
        consultation_row: ORM Consultation instance (must have ai_draft_json and patient_id).
        db:               Active SQLAlchemy session.
        verbose:          If True, prints the lab coverage caveat to stdout.

    Returns:
        EHRFactAccuracyResult dataclass.
    """
    result = EHRFactAccuracyResult()

    # ── Extract draft text ───────────────────────────────────────────────────
    draft_json = consultation_row.ai_draft_json
    if not draft_json:
        return result

    if isinstance(draft_json, str):
        try:
            draft_json = json.loads(draft_json)
        except json.JSONDecodeError:
            return result

    # Reconstruct full draft text from sentence objects or raw text
    sentences: list[str] = []
    if isinstance(draft_json, dict):
        for sent in draft_json.get("sentences", []):
            if isinstance(sent, dict):
                sentences.append(sent.get("text", ""))
            elif isinstance(sent, str):
                sentences.append(sent)
        # Fallback: top-level 'text' key
        if not sentences and "text" in draft_json:
            sentences = [draft_json["text"]]
    elif isinstance(draft_json, str):
        sentences = [draft_json]

    draft_text = " ".join(sentences).strip()
    if not draft_text:
        return result

    # ── Fetch EHR data for this patient ─────────────────────────────────────
    patient_id = consultation_row.patient_id
    ehr_prescriptions = _get_patient_prescriptions(patient_id, db)
    ehr_labs = _get_patient_lab_results(patient_id, db)
    ehr_conditions = _get_patient_conditions(patient_id, db)

    # ── Extract facts from draft text ────────────────────────────────────────
    medications = extract_medications_from_text(draft_text)
    lab_values = extract_lab_values_from_text(draft_text)
    conditions = extract_conditions_from_text(draft_text)

    result.n_medications_extracted = len(medications)
    result.n_labs_extracted = len(lab_values)
    result.n_conditions_extracted = len(conditions)
    result.n_facts_extracted = len(medications) + len(lab_values) + len(conditions)

    if lab_values:
        result.lab_coverage_caveat = True
        if verbose:
            print(LAB_COVERAGE_CAVEAT_MSG)

    # ── Match medications ────────────────────────────────────────────────────
    for med in medications:
        if _fuzzy_match(med, ehr_prescriptions, threshold=0.5):
            result.n_medications_matched += 1
        else:
            result.unmatched_facts.append({"type": "medication", "extracted": med})

    # ── Match lab values ─────────────────────────────────────────────────────
    for lv in lab_values:
        if _match_lab_value(lv, ehr_labs):
            result.n_labs_matched += 1
        else:
            result.unmatched_facts.append({
                "type": "lab_value",
                "extracted": lv.raw_text,
                "value": lv.value,
                "unit": lv.unit,
            })

    # ── Match conditions ─────────────────────────────────────────────────────
    for cond in conditions:
        if _fuzzy_match(cond, ehr_conditions, threshold=0.45):
            result.n_conditions_matched += 1
        else:
            result.unmatched_facts.append({"type": "condition", "extracted": cond})

    # ── Aggregate ─────────────────────────────────────────────────────────────
    result.n_facts_matched = (
        result.n_medications_matched
        + result.n_labs_matched
        + result.n_conditions_matched
    )

    def safe_div(n: int, d: int) -> float:
        return n / d if d > 0 else float("nan")

    result.fact_accuracy      = safe_div(result.n_facts_matched, result.n_facts_extracted)
    result.med_accuracy       = safe_div(result.n_medications_matched, result.n_medications_extracted)
    result.lab_accuracy       = safe_div(result.n_labs_matched, result.n_labs_extracted)
    result.condition_accuracy = safe_div(result.n_conditions_matched, result.n_conditions_extracted)

    return result
