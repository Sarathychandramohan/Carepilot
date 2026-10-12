"""
D:\\CarePilotAI\\backend\\app\\pipeline\\validate.py

B5 — Faithfulness Validation
Pillar B, post-generation quality gate.

Two checks:
  B5a: Citation coverage  — fraction of sentences with valid, non-outlier-only citations
  B5b: NLI entailment     — cross-encoder/nli-deberta-v3-small per sentence
       (see docs/PILLAR_B_DECISIONS.md D-001 for model choice rationale)

Produces exactly 4 validation_status values:
  passed | passed_with_warning | passed_with_outlier_caveat | manual_required
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.app.pipeline.retrieve_ehr import EHRChunk
from backend.app.pipeline.retrieve_kb import KBChunk
from backend.app.pipeline.generate import GeneratedDraft

# Thresholds (overridden from settings in orchestrator)
COVERAGE_THRESHOLD = 0.80
NLI_PASS_THRESHOLD = 0.50
NLI_WARN_THRESHOLD = 0.30

# Lazy-loaded NLI model (cross-encoder/nli-deberta-v3-small)
# See docs/PILLAR_B_DECISIONS.md D-001
_NLI_MODEL = None


def _get_nli_model():
    global _NLI_MODEL
    if _NLI_MODEL is None:
        from sentence_transformers import CrossEncoder
        _NLI_MODEL = CrossEncoder("cross-encoder/nli-deberta-v3-small")
    return _NLI_MODEL


@dataclass
class ValidationResult:
    citation_coverage: float         # B5a: sentences with valid citations / total
    avg_nli_entailment: float        # B5b: average entailment score across sentences
    citation_validity: float         # fraction of cited IDs that actually exist
    has_outlier_only_sentence: bool  # True if any sentence cites only outlier chunks
    per_sentence: list[dict]         # per-sentence breakdown for faithfulness_details
    validation_status: str           # passed | passed_with_warning | passed_with_outlier_caveat | manual_required


def _build_citation_lookup(
    ehr_chunks: list[EHRChunk],
    kb_chunks: list[KBChunk],
) -> dict[str, dict]:
    """Build {citation_id → chunk_info} for fast lookup."""
    lookup: dict[str, dict] = {}
    for chunk in ehr_chunks:
        lookup[chunk.stable_eid] = {
            "text": chunk.display_value,
            "is_outlier": chunk.is_outlier,
            "source_type": chunk.source_type,
        }
    for chunk in kb_chunks:
        lookup[chunk.chunk_id] = {
            "text": chunk.text,
            "is_outlier": False,
            "source_type": "kb",
        }
    return lookup


def validate_draft(
    draft: GeneratedDraft,
    ehr_chunks: list[EHRChunk],
    kb_chunks: list[KBChunk],
    coverage_threshold: float = COVERAGE_THRESHOLD,
    nli_pass_threshold: float = NLI_PASS_THRESHOLD,
    nli_warn_threshold: float = NLI_WARN_THRESHOLD,
) -> ValidationResult:
    """
    Run B5a citation coverage + B5b NLI entailment checks on a GeneratedDraft.

    Returns ValidationResult with exactly one of 4 validation_status values.
    """
    citation_lookup = _build_citation_lookup(ehr_chunks, kb_chunks)
    nli_model = _get_nli_model()

    total_sentences = len(draft.sentences)
    if total_sentences == 0:
        return ValidationResult(
            citation_coverage=0.0,
            avg_nli_entailment=0.0,
            citation_validity=0.0,
            has_outlier_only_sentence=False,
            per_sentence=[],
            validation_status="manual_required",
        )

    per_sentence: list[dict] = []
    valid_citation_sentences = 0
    total_cited_ids = 0
    total_valid_ids = 0
    outlier_only_count = 0
    nli_scores: list[float] = []

    for sent in draft.sentences:
        cited_ids = sent.citations or []
        total_cited_ids += len(cited_ids)

        # ── B5a: Citation validity ─────────────────────────────────────────
        valid_ids = [cid for cid in cited_ids if cid in citation_lookup]
        total_valid_ids += len(valid_ids)

        # Outlier-only: ALL cited IDs resolve to outlier chunks
        all_outlier = bool(valid_ids) and all(
            citation_lookup[cid].get("is_outlier", False) for cid in valid_ids
        )
        if all_outlier:
            outlier_only_count += 1
            # Outlier-only citations count as ZERO valid citations for coverage
            has_valid_citation = False
        else:
            has_valid_citation = len(valid_ids) > 0

        if has_valid_citation:
            valid_citation_sentences += 1

        # ── B5b: NLI entailment ────────────────────────────────────────────
        # Only compute against non-outlier cited chunks
        non_outlier_ids = [
            cid for cid in valid_ids
            if not citation_lookup[cid].get("is_outlier", False)
        ]
        if non_outlier_ids:
            premise = " ".join(citation_lookup[cid]["text"] for cid in non_outlier_ids)
            # DeBERTa label order: [contradiction=0, entailment=1, neutral=2]
            scores = nli_model.predict(
                [(premise, sent.text)], apply_softmax=True
            )
            entailment_score = float(scores[0][1])
        else:
            # No non-outlier citations → treat entailment as 0
            entailment_score = 0.0

        nli_scores.append(entailment_score)

        per_sentence.append({
            "text": sent.text[:120],
            "cited_ids": cited_ids,
            "valid_citation": has_valid_citation,
            "all_outlier": all_outlier,
            "entailment_score": round(entailment_score, 4),
        })

    citation_coverage = valid_citation_sentences / total_sentences
    avg_nli = sum(nli_scores) / len(nli_scores) if nli_scores else 0.0
    citation_validity = total_valid_ids / total_cited_ids if total_cited_ids > 0 else 0.0
    has_outlier_only = outlier_only_count > 0

    # ── Decision matrix — 4 possible statuses ─────────────────────────────
    if citation_coverage < coverage_threshold or avg_nli < nli_warn_threshold:
        status = "manual_required"
    elif has_outlier_only:
        status = "passed_with_outlier_caveat"
    elif avg_nli < nli_pass_threshold:
        status = "passed_with_warning"
    else:
        status = "passed"

    return ValidationResult(
        citation_coverage=round(citation_coverage, 4),
        avg_nli_entailment=round(avg_nli, 4),
        citation_validity=round(citation_validity, 4),
        has_outlier_only_sentence=has_outlier_only,
        per_sentence=per_sentence,
        validation_status=status,
    )
