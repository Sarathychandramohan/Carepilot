# Pillar B Plan — RAG Generation, Triage, and Validation Pipeline
**Document Version:** 2.0 (Ongoing Implementation & Post-Gate 0 Blueprint)  
**Authoritative Reference:** `CarePilot_AI_Master_Spec_v3.md` (Sections 3.1–3.2, 3.5, 4.1–4.4, 5.1, S3, S5, S7, S8, S9, Appendices A, B, C, E)  
**System Role:** Subsystem Plan for Pillar B (Consultation Lifecycle, Retrieval Branches, Local LLM Inference, and NLI Guardrails)

---

## 1. Pillar Objectives and Scope

Pillar B implements the asynchronous core pipeline (`P1` through `P8`) that ingests patient requests, applies safety triage, retrieves evidence from dual sources (EHR + Knowledge Base), drafts clinical responses via a local open-weight LLM, and enforces post-generation faithfulness validation prior to clinician review.

### Primary Research Objectives:
1. **RQ1 Dual-Context Evaluation**: Compare factual accuracy and hallucination rates between dual-context retrieval (`full`) and knowledge-only retrieval (`no_ehr`), with a pilot `unified_context` baseline (**Spec Section 3.1, lines 160–161**).
2. **RQ2 Triage Safety Comparison**: Compare HIGH-urgency false negative rates between an independent calibrated classifier with red-flag override vs. LLM self-reported urgency (`no_classifier` arm) (**Spec Section 3.1, line 162**).
3. **Pillar C/D Grounding**: Ensure every consultation generates an auditable, schema-compliant JSON trace logging all intermediate stages, latencies, citations, and NLI scores (**Spec D20, line 301**).

---

## 2. Applicable Spec Requirements and Numerical Targets

| Spec Section | Component / Stage | Target / Constraint | Rationale / Reference |
| :--- | :--- | :--- | :--- |
| **S3 (lines 433–451)** | Request Lifecycle | P1 to P8 asynchronous pipeline per consult | Background task with semaphore, non-blocking polling (**D1**). |
| **S3 (lines 437–446)** | Stage 1 EHR Retrieval | Parameterized SQL scoped by `patient_id` | Restricted by classified intent, concept IDs, recency window; max 200 candidate facts (**D10**). |
| **S3 (lines 446)** | Stage 2 EHR Rerank | Dense similarity + recency weight | Reranks on the fly via `bge-small-en-v1.5`; top-8 facts into prompt (**D10, D11**). |
| **S5 (lines 464–470)** | KB Hybrid Retrieval | Dense (top-20) + BM25 (top-20) | Fused scoring over frozen `carepilot_kb_v5`; top-5 logged, top-3 into prompt. Target p95 $\le 300\text{ ms}$. |
| **D17 (line 298)** | Conflict & Missing Context | Rule-based flags over concepts | `patient_ehr_mismatch` requires clarification or explicit discrepancy; `missing_context` routes to `manual_required`. |
| **S7 (lines 482–488)** | Local LLM Drafting | Qwen3-8B via local Ollama | `"think": false`, `temp: 0`, structured JSON (Appendix A), prompt skeleton (Appendix B); up to 2 retries; target p95 $\le 120\text{ s}$ (**R4**). |
| **S8 (lines 489–501)** | Faithfulness & Citations | Sentence-level NLI + Citation Check | `cross-encoder/nli-deberta-v3-small` per sentence; citation validity, citation coverage ($\ge 0.80$), $\tau_{\text{faith}} = 0.50$, $\tau_{\text{faith\_low}} = 0.30$. |
| **S9 (lines 502–514)** | Review Queue & Memory | Status transition & Enqueueing | Priority ordering by `urgency_final`; 12-category weighted edit burden; typed edit memory (D6). |
| **Sec 3.5 (lines 221)** | Gold-Test Compute Budget | 1,050 drafts (350 $\times$ 3 configs) | Spec estimated envelope: 9 to 18 hours. |

---

## 3. Sub-Pillar Architecture and Implementation Breakdown

```
[Patient Request]
       │
       ▼
[B1: Intake & JWT Scope] ──> Create Consultation (is_eval, ablation_config)
       │
       ▼
[B2: Pre-Check & Triage] ──> P2: redflag.py (Firm Hit ──> Static Emergency Message)
                         ──> P3: normalize.py (Tier 1/2, Negation, Temporal)
                         ──> P4: classify.py (Intent [5 classes] + Urgency [3 classes])
                                (Max P(intent) < tau_intent ──> route: unsupported)
       │
       ▼
[B3: Evidence Retrieval] ──> B3.1: Two-Stage EHR (Scoped SQL ──> Dense/Recency Rerank ──> Top-8)
                         ──> B3.2: Hybrid KB (ChromaDB + BM25 ──> Fusion ──> Top-3 prompt / Top-5 log)
                         ──> B3.3: D17 Conflict & Missing-Context Check
       │
       ▼
[B4: Local LLM Drafting] ──> generate.py (Prompt Skeleton + Qwen3-8B via Ollama + JSON Retry Loop)
       │
       ▼
[B5: Post-Gen Validation]──> B5a: Citation ID validity & coverage check
                         ──> B5b: Sentence-level NLI entailment (nli-deberta-v3-small)
                         ──> B5c: Outlier caveat check ──> 4-state routing (passed, warning, caveat, manual)
       │
       ▼
[B6: Queue & Review Hook]──> P8: urgency_final = max(classifier, redflag) ──> Priority Enqueue
```

### Detailed Sub-Pillars:

#### B1: Request Intake and Security Scoping (`P1`)
- **File**: `backend/app/pipeline/orchestrator.py`
- Enforce strict server-side scoping: `patient_id` extracted exclusively from validated JWT token, never from request payload (**Spec Section 4.5, line 324**).
- Persist consultation record to PostgreSQL with `thread_status = 'received'`, timestamps, and ablation configuration.

#### B2: Safety Pre-Check, Terminology Normalization, and Triage (`P2–P4`)
- **Files**: `backend/app/pipeline/redflag.py`, `backend/app/pipeline/normalize.py`, `backend/app/pipeline/classify.py`
- **P2 Red-Flag Pre-Check**: Run raw text against frozen 9-category lexicon. Firm hits immediately override urgency to `urgent` and return a pre-approved static emergency template (**Invariant I3, D3, D8**). Soft hits (historical/hypothetical) are logged for doctor advisory display.
- **P3 Normalization**: Extract clinical concepts via Tier 1 dictionary (SNOMED, LOINC, RxNorm); resolve unmatched spans against concept embeddings; flag negation (30-char lookback) and temporal duration/anchor spans.
- **P4 Triage Classification**: Compute dense 384-d `bge-small` embedding once. Predict Intent (5 classes); if confidence $< \tau_{\text{intent}}$ (`0.45`), set route to `unsupported` $\rightarrow$ `manual_required`. In all arms except `no_classifier`, predict Urgency (predict `urgent` if $P(\text{urgent}) \ge \tau_{\text{high}} = 0.25$).

#### B3: Two-Stage Structured EHR and Hybrid KB Retrieval (`P5`)
- **Files**: `backend/app/pipeline/retrieve_ehr.py`, `backend/app/pipeline/retrieve_kb.py`, `backend/app/pipeline/detect_context_gaps.py`
- **B3.1 Two-Stage EHR Retrieval**:
  - *Stage 1*: Parameterized SQL restricted by `patient_id = :pid` and intent-routed tables (`symptom_report`: conditions, meds, allergies, encounters; `medication_query`: meds, allergies, renal labs; `lab_result_query`: matching LOINC observations and reference ranges; `followup_appointment`: encounters; `general_health_info`: conditions, meds). Cap at 200 facts.
  - *Stage 2*: Embed candidate snippets on the fly via `bge-small`, score by cosine similarity plus recency decay, select top-8 facts for prompt injection (**D10, D11**). Tag each chunk with `is_outlier`.
  - *Ablation*: Skipped entirely in `no_ehr` arm.
- **B3.2 Hybrid KB Retrieval**:
  - Query expansion with top canonical concept labels.
  - Retrieve top-20 dense candidates from ChromaDB collection `carepilot_kb_v5` and top-20 sparse candidates from `bm25_index_v5.pkl`.
  - Fusion scoring: rank/score candidates, log top-5, pass top-3 into prompt context block.
- **B3.3 D17 Conflict and Context Gap Safety**:
  - `patient_ehr_mismatch`: Query references a medication/condition/lab absent from or contradicting the EHR. Requires LLM `needs_clarification = true` or routes to `manual_required`.
  - `missing_context`: EHR-dependent intent has zero valid non-outlier EHR rows and low-confidence KB evidence. Bypasses LLM drafting and routes directly to `manual_required`.

#### B4: Local LLM Draft Generation (`P6`)
- **File**: `backend/app/pipeline/generate.py`
- **Model**: Local `qwen3:8b` via Ollama (`http://127.0.0.1:11434/api/generate`) with `"think": false`, `temperature: 0`, `seed: 42`.
- **Concurrency**: Guarded by `asyncio.Semaphore(1)` to serialize GPU calls and prevent VRAM exhaustion (**D1**).
- **Prompt Architecture (Appendix B)**: Isolated delimited blocks (`[PATIENT_MESSAGE]`, `[NORMALIZED_CONCEPTS]`, `[FLAGS]`, `[EHR_CONTEXT]`, `[KNOWLEDGE_CONTEXT]`, optional `[REVIEWED_EXAMPLES]`). System instructions strictly forbid following instructions within context blocks (injection defense) and forbid diagnostic/prescriptive instructions.
- **Outlier Caveat Handling**: If any retrieved EHR chunk has `is_outlier = true`, inject explicit prompt caveat warning.
- **Ablation Arm Routing**:
  - `full`: EHR context + KB context + classifier urgency.
  - `no_ehr`: KB context only + classifier urgency.
  - `no_classifier`: EHR context + KB context; prompt asks LLM to self-assess urgency; skips classifier step (requires `is_eval=true` authorization check).
  - `unified_context`: Merged shared candidate pool of EHR snippets and KB chunks ranked by single score.
- **JSON Validation & Retry**: Output parsed against Appendix A Pydantic schema (`sentences` with `claim_type` and `citations`, `overall_tone`, `urgency_self_report`, `needs_clarification`). If invalid, retry up to 2 times; if still invalid, route to `manual_required`.

#### B5: Post-Generation Faithfulness and Citation Guardrails (`P7`)
- **File**: `backend/app/pipeline/validate.py`
- **B5a Citation Validity & Coverage**:
  - Check that every cited ID exists in the retrieved candidate set.
  - If a sentence cites *only* outlier-flagged EHR rows without non-outlier corroboration, it receives zero validity credit.
  - Compute `citation_coverage` = (sentences with $\ge 1$ valid citation) / (total scored sentences).
- **B5b NLI Entailment Scoring**:
  - Model: `cross-encoder/nli-deberta-v3-small` (softmax over contradiction=0, entailment=1, neutral=2).
  - For each non-caution sentence: premise = cited source text; hypothesis = sentence text; score = max entailment probability across cited sources.
  - Compute draft `faithfulness_mean` (`avg_nli_entailment`).
- **4-State Gate Matrix**:
  1. `manual_required`: `citation_coverage < 0.80` OR `avg_nli_entailment < 0.30` ($\tau_{\text{faith\_low}}$). AI draft withheld from doctor.
  2. `passed_with_outlier_caveat`: Any sentence relies exclusively on outlier-flagged EHR evidence.
  3. `passed_with_warning`: `0.30 \le avg_nli_entailment < 0.50` ($\tau_{\text{faith}}$). Individual sentences highlighted for clinician.
  4. `passed`: `citation_coverage \ge 0.80` AND `avg_nli_entailment \ge 0.50`.

#### B6: Urgency Finalization, Enqueueing, and Review Hook (`P8–P10`)
- **File**: `backend/app/pipeline/orchestrator.py`
- Resolve `urgency_final`:
  - `full`, `no_ehr`, `unified_context`: `max(urgency_classifier, red_flag_level)`.
  - `no_classifier`: `urgency_self_report` (unless overridden by firm red-flag).
- Enqueue consultation into doctor review queue ordered by `urgency_final` descending, then `created_at` ascending.
- Review effort and edit tracking hooks: record review duration, sources opened, Levenshtein distances, and 12-category weighted edit burden.

---

## 4. Hardware Telemetry and Measured Compute Budget (Gate 0)

From Gate 0 benchmark on host hardware (NVIDIA GeForce RTX 2050 4GB VRAM, AMD Ryzen 5 5600H CPU, 16GB RAM):
- **Model Tag**: `qwen3:8b` (5.2 GB, Q4_K_M equivalent via Ollama v0.40.3).
- **Layer Offload**: 13 layers CUDA / 24 layers CPU. Peak VRAM: ~2,311 MiB. Peak RAM: ~14.8 GB.
- **Measured Latency Profile (Stratified 20-Query Run across 5 Intents)**:
  - Median: **47.41 s/draft**
  - Mean: **52.21 s/draft**
  - p95: **85.43 s/draft** (below Spec Risk R4 ceiling of 120 s)
  - Throughput: **3.80 tokens/sec**
  - JSON Schema Validity: **100% on first attempt** (0 retries required)
- **Recomputed Gold-Test Drafting Budget (350 queries $\times$ 3 configs = 1,050 drafts)**:
  - At Median (47.41 s): **13.83 hours**
  - At Mean (52.21 s): **15.23 hours**
  - At p95 (85.43 s): **24.92 hours**
  - Conforms strictly to Spec Section 3.5 planned window of **9 to 18 hours**.

---

## 5. Technical Decisions and Policy Constraints

- **D-001 (NLI Model)**: `cross-encoder/nli-deberta-v3-small` selected per Spec Section 4.4 (line 313).
- **D-002 (LLM Model Selection)**: `qwen3:8b` confirmed as authoritative drafting model based on real Gate 0 latency and 100% schema compliance.
- **D-003 (`no_classifier` Urgency Policy)**: In the `no_classifier` arm, the LLM self-assesses urgency via prompt instructions, testing RQ2.
- **D-004 (Zero Cloud LLMs)**: Gemini API and external cloud fallbacks strictly excluded. Pipeline operates 100% locally.
- **Authorization Enforcement**: `no_classifier` and other evaluation ablations must enforce `is_eval == true` and admin privileges to prevent unsafe deployment in live patient care.
