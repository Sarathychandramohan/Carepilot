# Pillar B Plan — RAG Generation, Triage, and Validation Pipeline

**Document Version:** 3.0 (Aligned with Master Plan v5 & Post-Phase-5 State)  
**Authoritative Reference:** `docs/MASTER_PROJECT_PLAN_v5.md` (Sections 1, 3, 5, 8, 10)  
**System Role:** Subsystem Specification and Implementation Plan for Pillar B (Consultation Lifecycle, Triage Classifiers, Dual Evidence Retrieval, Local LLM Inference, Readability Control, and Validation Guardrails)  
**Current Git State:** Implemented and verified on branches `main` and `friend` (commit `fee80e4` / `0f7f40a`)

---

## 1. Pillar Objectives and Scope

Pillar B implements the core clinical pipeline (`P1` through `P8`) that ingests patient consultation messages, performs safety triage, retrieves evidence from dual sources (EHR + Knowledge Base), drafts clinical responses via a local open-weight LLM, applies readability simplification, and enforces post-generation faithfulness validation prior to mandatory clinician review.

### Primary Research Objectives:
1. **RQ1 Dual-Context Evaluation**: Compare factual accuracy and hallucination rates between dual-context retrieval (`full`) and knowledge-only retrieval (`no_ehr`), establishing whether patient-scoped EHR grounding improves relevance without increasing unsupported claims.
2. **RQ2 Triage Safety Comparison**: Compare HIGH-urgency false negative rates between an independent calibrated classifier with negation-aware red-flag overrides vs. LLM self-reported urgency (`no_classifier` arm), specifically measuring keyword-free emergency scenarios.
3. **RQ4 Readability vs. Faithfulness Trade-Off**: Evaluate whether a post-generation readability controller reduces response complexity to grade $\le 8$ without sacrificing evidence faithfulness or clinical completeness (anchored to Small et al., 2024).
4. **Structured Provenance Logging**: Ensure every consultation generates an auditable, schema-compliant JSON trace logging all intermediate stages, latencies, citations, NLI scores, and validation decisions (`consultations` & `eval_runs` tables).

---

## 2. Applicable Requirements and Numerical Targets

| Stage / Component | Target / Constraint | Operational Implementation |
|---|---|---|
| **P1 Request Intake & Auth** | Server-side patient scoping | `patient_id` extracted exclusively from validated auth context, never client payload (**Invariant I2**). |
| **P2 Red-Flag Override** | 11 Emergency Categories | Frozen negation-aware rule engine; firm hits force HIGH urgency and emergency care diversion before drafting (**Invariant I3**). |
| **P4 Triage Classifiers** | 5 Intent / 3 Urgency classes | Calibrated Logistic Regression over `bge-small` embeddings. $\tau_{\text{intent}} = 0.45$, $\tau_{\text{high}} = 0.25$, $\tau_{\text{soon}} = 0.30$. |
| **P5.1 Structured EHR Retrieval** | Patient-scoped SQL + Rerank | Parameterized SQL restricted to `patient_id = :pid`; max 200 candidates; on-the-fly dense similarity + recency rerank; top-8 facts into prompt. |
| **P5.2 Knowledge Base Retrieval** | Dual Dense + BM25 Hybrid | Top-20 dense from `carepilot_kb_v5` + top-20 sparse from `bm25_index_v5.pkl`; convex combination fusion; top-3 passages into prompt. |
| **D17 Conflict & Missing Context** | Conflict & Gap detection | `ehr_mismatch` flags contradictions for doctor review; `missing_context` triggers **Clarify-Instead-of-Skip** question generation. |
| **P6 Local LLM Generation** | Ollama `qwen3:8b` | Local inference on `127.0.0.1:11434`, `"think": false`, `temperature: 0.0`, `seed: 42`, structured JSON output with inline citations. |
| **B5b Readability Controller** | Grade $\le 8$ + Length cap | Post-draft rewrite targeting reading grade $\le 8$; two-way NLI factual equivalence check; rejects rewrite if facts alter. |
| **P7 Validation Gate** | Multi-gate guardrails | Citation ID existence, citation coverage ($\ge 0.80$), NLI entailment ($\tau_{\text{faith}} = 0.15$, warning $0.001$), contradiction ceiling ($\le 0.05$). |
| **B6b Claim Verification** | Atomic evidence linking | Splits draft into atomic claims; links to EHR or KB evidence IDs; measures supported/unsupported/contradicted rates. |
| **P8 Clinician Enqueueing** | Mandatory Doctor Review | Draft placed in queue sorted by `urgency_final` descending. No patient delivery without explicit doctor approval (**Invariant I1**). |

---

## 3. End-to-End Pipeline Architecture

```
[Patient Request]
       │
       ▼
[P1: Intake & Security Scoping] ──> Scoped by authenticated patient_id in SQL
       │
       ▼
[P2: Red-Flag Pre-Check] ─────────> 11 emergency categories
                                   (Firm Hit ──> static emergency override, no AI draft)
       │
       ▼
[P4: Triage Classification] ──────> BGE-small dense embedding (384-d)
                                   - Intent: 5 classes (symptom, med, lab, appt, info)
                                   - Urgency: routine, soon, urgent (tau_high = 0.25)
       │
       ▼
[P5: Evidence Retrieval] ─────────> B3.1 EHR: Parameterized SQL (top-200) ──> Rerank ──> Top-8 facts
                                   B3.2 KB:  ChromaDB (top-20) + BM25 (top-20) ──> Top-3 passages
                                   B3.3 D17: Conflict (mismatch) & Missing-Context checks
       │
       ▼
[P6: Local LLM Drafting] ─────────> Prompt skeleton + Qwen3-8B (Ollama, temp=0, seed=42)
                                   Structured JSON with sentence citations
                                   (If missing_context & clarify enabled: generate clarification)
       │
       ▼
[B5b: Readability Controller] ────> Target FK grade <= 8, length cap
                                   Two-way NLI fact check (rejects rewrite if facts change)
       │
       ▼
[P7: Multi-Gate Validation] ──────> 1. Citation validity & coverage (>= 0.80)
                                   2. NLI entailment scoring (nli-deberta-v3-small)
                                   3. Contradiction ceiling (<= 0.05)
                                   4. Claim-level support assessment (B6b)
       │
       ▼
[P8: Queue & Review Hook] ────────> urgency_final = max(classifier, redflag)
                                   Enqueued for Doctor Dashboard review
       │
       ▼
[Doctor Review & Delivery] ───────> Approve / Edit / Reject / Request Clarification
                                   Delivered to Patient App ONLY after approval (Invariant I1)
```

---

## 4. Pipeline Stages in Detail

### P1: Intake and Security Scoping
- **Implementation**: `backend/app/pipeline/orchestrator.py`
- Enforces server-side scoping: `patient_id` resolved from authenticated session, never trusted from client request parameters (**Invariant I2**).
- Persists consultation record to PostgreSQL with `thread_status = 'received'`, timestamps, and active ablation flags.

### P2 & P4: Safety Triage and Emergency Rules
- **Files**: `backend/app/pipeline/redflag.py`, `backend/app/pipeline/classify.py`
- **11 Red-Flag Emergency Categories**: Chest pain, acute respiratory distress, stroke indicators, acute severe hemorrhage, syncope/seizures, anaphylaxis, acute suicidal ideation/self-harm, meningitis/sepsis signs, acute surgical abdomen, sudden thunderclap headache, and acute poisoning/overdose.
- **Pre-Generation Override**: A firm red-flag match immediately sets `urgency_final = 'urgent'` and short-circuits drafting. The patient app receives an immediate emergency advisory (**Invariant I3**).
- **Classification**: Generates `bge-small` embedding. Classifies Intent across 5 classes (routes to unsupported if max confidence $< 0.45$). Urgency predicted across 3 ordered classes (`routine`, `soon`, `urgent`). Predicts `urgent` when $P(\text{urgent}) \ge 0.25$.

### P5: Dual Evidence Retrieval & D17 Safety Checks
- **Files**: `backend/app/pipeline/retrieve_ehr.py`, `backend/app/pipeline/retrieve_kb.py`, `backend/app/pipeline/detect_context_gaps.py`
- **EHR Retrieval**: Queries PostgreSQL `carepilot_v3` strictly scoped to `patient_id = :pid`. Caps candidate pool at 200 rows. Re-ranks dynamically using cosine similarity against query embedding + recency decay. Top 8 facts injected into prompt with LOINC reference ranges and outlier tags.
- **KB Hybrid Retrieval**: Augments query with canonical medical concept labels. Queries ChromaDB `carepilot_kb_v5` (top 20) and BM25 index `bm25_index_v5.pkl` (top 20). Fuses scores with configured $\alpha$; injects top 3 passages into prompt.
- **D17 Gaps & Clarification**:
  - `ehr_mismatch`: Detects contradiction between query claim and EHR (e.g., patient asking about a medication never prescribed). Routes to clinician review with explicit discrepancy warning.
  - `missing_context`: If key clinical context is absent, the pipeline triggers **Clarify-Instead-of-Skip**, generating a focused question asking the patient for the missing detail.

### P6: Local LLM Drafting (Ollama Qwen3-8B)
- **File**: `backend/app/pipeline/generate.py`
- **Runtime**: Local Ollama instance (`http://127.0.0.1:11434/api/generate`) running `qwen3:8b` (Q4_K_M quantization).
- **Determinism**: Guarded with `temperature = 0.0`, `seed = 42`, `"think": false`.
- **Structured Schema**: Enforces JSON response containing individual sentence claims, citation tokens (`ehr:{table}:{id}` or `kb:{doc_id}:chunk{n}`), tone indicators, and clarification flags.

### B5b: Readability Controller (RQ4)
- **File**: `backend/app/pipeline/generate.py` / `backend/eval/metrics/readability.py`
- Post-generation simplification module targeting reading grade level $\le 8$ (Flesch–Kincaid) and a concise length cap.
- **Safety Invariant**: Rewritten text is verified against the original draft using two-way NLI (`cross-encoder/nli-deberta-v3-small`). If any clinical fact, medication dose, number, unit, or negation is altered, the rewrite is rejected and the original draft is retained.

### P7 & B6b: Multi-Gate Validation & Claim-Level Verification
- **File**: `backend/app/pipeline/validate.py`
- **Multi-Gate Checks**:
  1. *Citation Validity*: 100% of cited citation IDs must exist in the retrieved evidence set.
  2. *Citation Coverage*: At least 80% of factual sentences must carry valid citations.
  3. *NLI Faithfulness*: Evaluates entailment between each sentence and its cited source text.
  4. *Contradiction Ceiling*: Fails if contradiction probability exceeds 0.05.
- **Atomic Claim Verification (B6b)**: Decomposes draft into atomic propositions, checks direct entailment against EHR/KB evidence, and reports supported, unsupported, and contradicted claim rates.

### P8: Queue Management and Clinician Delivery Gate
- **File**: `backend/app/pipeline/orchestrator.py`
- Resolves `urgency_final = max(urgency_classifier, red_flag_level)`.
- Enqueues consultation in Doctor Review Queue (`doctor-dashboard`).
- **Safety Invariant I1**: Draft remains blocked until an authenticated clinician explicitly approves or edits it.

---

## 5. Feature Flags & Experimental Ablation Matrix

The pipeline architecture exposes explicit, logged configuration flags for reproducible ablation studies:

| Ablation Arm | EHR Context | KB Context | Urgency Triage | Readability Controller | Purpose / Evaluated Effect |
|---|---|---|---|---|---|
| **`full`** | Yes (Top 8) | Yes (Top 3) | Classifier + Red-Flag | Enabled (Grade $\le 8$) | Primary system pipeline with all safeguards active. |
| **`no_ehr`** | No | Yes (Top 3) | Classifier + Red-Flag | Enabled | Isolates clinical grounding contribution of patient EHR (**RQ1**). |
| **`no_classifier`** | Yes (Top 8) | Yes (Top 3) | LLM Self-Assessment | Enabled | Isolates safety impact of independent triage classifier (**RQ2**). |
| **`no_readability`** | Yes (Top 8) | Yes (Top 3) | Classifier + Red-Flag | Disabled (Raw LLM) | Measures readability vs faithfulness trade-off (**RQ4**). |
| **`clarify_enabled`** | Yes (Top 8) | Yes (Top 3) | Classifier + Red-Flag | Enabled | Emits clarifying question when clinical context is missing. |

---

## 6. Implementation Status & Verified Test Suites

Pillar B is fully implemented and passes all automated regression test suites:
- `backend/tests/test_redflag_11_categories.py`: **88/88 passed** (100% coverage of emergency categories & negation).
- `backend/tests/test_ehr_fact_accuracy.py`: **43/43 passed** (groundedness across meds, labs, and vitals).
- `backend/tests/test_skip_reasons.py`: **7/7 passed** (gate persistence and pipeline skip logic).
- `backend/tests/test_eval_provenance.py`: **2/2 passed** (threshold synchronization and run validation).
