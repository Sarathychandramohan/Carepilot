> [!CAUTION]
> ## ⛔ PARTIAL INVALIDATION NOTICE — 2026-10-16
>
> The following claims in this document are **INVALID** and must not be cited:
>
> | Line | Claim | Reason |
> |---|---|---|
> | Line 17 (C6 row) | `Spearman ρ = -0.2938, p = 0.0227, Figure F3 generated` | This value came from a **synthetic formula** (`base_weight = 2.5 if not is_mem_on else max(0.5, 2.5 - idx/40.0)`), not from real doctor reviews. 0 actual doctor reviews exist in the database for eval runs 3-7. Status `COMPLETED (STREAM ANALYZED)` is incorrect — should be `NOT COMPUTED`. |
> | Line 19 (Overall row) | `Tables T1–T8 & Figures F1–F4 generated in data/reports/` | Table T6 was hardcoded; Table T7 was synthetic; Table T8 was hardcoded from a single run. These tables have been moved to `data/reports/_invalid/`. |
>
> **Full incident record:** `docs/PILLAR_C_DECISIONS.md` — INCIDENT RECORD section.

# Pillar C Completion Status Report
**Document Version:** 1.0  
**Authoritative Reference:** `CarePilot_AI_Master_Spec_v3.md` (Sections 3.1–3.4, 4.1–4.2, 5.1, Section 8, S9, S10, S11, S12, S13, Appendices A, C, D)  
**System Role:** Independent Verification and Completion Status Report for Pillar C (Evaluation Harness, Doctor Review, and Interface Systems)

---

## 1. Executive Summary

| Sub-Pillar | Description | Verification Status | Completion Level |
| :--- | :--- | :--- | :--- |
| **C1: Clinical Frontend Interfaces** | Doctor Review Dashboard (React/Vite) and Patient Mobile App (Expo SDK 57). | `IN PROGRESS (SCAFFOLDED)` | Demo UI exists; Live API swap pending |
| **C2: Full System Integration** | Live API integration, role-based JWT auth, concurrency & IDOR security testing. | `IN PROGRESS` | API endpoints wired; security test suite exists |
| **C3: Automated Evaluation Harness** | `python -m eval.run`, `eval_runs` PostgreSQL logging, metrics engine. | `VERIFIED & OPERATIONAL` | Fully built, regression tests passing |
| **C4: Experimental Ablation Runs** | Primary ablations (`full`, `no_ehr`, `no_classifier`) on Gold & Silver. | `dry-run only` | Dry-runs verified (Runs 10, 11); non-dry-run evaluation not run |
| **C5: Human Clinician Evaluation** | Double-rater evaluation of 40 gold-test consultations across relevance, safety, and factuality. | `NOT STARTED` | Templates created; awaiting human double annotation |
| **C6: Live Doctor-Edit Study (RQ3)** | 60-query clinician review sessions with typed edit memory toggling (memory ON vs OFF). | `NOT STARTED` | Stream queries prepared; no doctor reviews conducted |
| **C7: Scale Sweeps (SA1 & SA2)** | KB distractor scale sweep (18 to 10k chunks) and patient record-length bucket analysis. | `NOT STARTED` | Sweep definitions drafted; execution not started |
| **Overall Pillar C Status** | Evaluation, Research Instrumentation, and Clinical HITL Review. | `IN PROGRESS (HARNESS & DRY-RUNS VERIFIED)` | Harness, metrics & skip guards built; real evaluation pending |

---

## 2. Component-by-Component Status & Dependency Audit

### 2.1 Clinical User Interfaces (Spec S10, S11)
- **Doctor Review Dashboard (`doctor-dashboard`)**:
  - *Expected*: React 18 + Vite 3-pane clinical workspace; paginated review queue ordered by `urgency_final`; interactive citation chips; source-type labels (`EHR`, `Knowledge`, `Mixed`, `Uncited`); sentence NLI badges; discrepancy banners; 12-category edit checkboxes; review effort logging (`review_seconds`, `sources_opened`).
  - *Actual Status*: Frontend code scaffolded at `doctor-dashboard/` from initial demo phase. Mock API exists; live backend review endpoint integration is not yet wired.
  - *Status*: `IN PROGRESS (SCAFFOLDED / LIVE SWAP PENDING)`.
- **Patient Mobile & Web Application (`patient-app`)**:
  - *Expected*: React Native / Expo SDK 57 app; strict adherence to Safety Invariant I1 (renders only approved final text); status polling; emergency intercept banner on firm red-flag hits.
  - *Actual Status*: Frontend code scaffolded at `patient-app/` from initial demo phase.
  - *Status*: `IN PROGRESS (SCAFFOLDED / LIVE SWAP PENDING)`.

---

### 2.2 System Integration and Security Verification (Spec S12, Section 4.5)
- **Target Requirements**:
  - End-to-end flow: Patient submission $\rightarrow$ async pipeline $\rightarrow$ AI draft $\rightarrow$ doctor review $\rightarrow$ patient delivery.
  - Role-based access control (patient, doctor, admin) enforced via JWT.
  - Mandatory tenant scoping (`patient_id` filter on 100% of queries).
  - Concurrency and IDOR penetration tests (verify Patient B can never retrieve Patient A's records).
- *Actual Status*: Stubs implemented in backend; comprehensive security integration tests not yet written.
- *Status*: `PENDING (Scheduled for Weeks 5–7)`.

---

### 2.3 Automated Research Instrumentation and Evaluation Harness (Spec S13)
- **Target Requirements**:
  - CLI runner `python -m eval.run --config ... --split ... --seed ...`
  - Automated logging of every consultation trace and summary metrics into `eval_runs` table in `carepilot_v3`.
  - Stage-wise automated metrics:
    - EHR candidate retrieval recall and precision.
    - KB retrieval Hit@3, Hit@5, and MRR against pooled relevance labels.
    - Citation validity, citation coverage, sentence NLI entailment scores.
    - Automated classification metrics (macro-F1, confusion matrices, HIGH-acuity FNR with Wilson 95% CIs).
- *Actual Status*: Not yet implemented. Evaluation runner scripts exist only as isolated training evaluators (`train_classifiers.py`, `evaluate_classifiers_rq2.py`).
- *Status*: `PENDING (Scheduled for Weeks 4–5)`.

---

### 2.4 Experimental Ablation Execution (Spec Section 3.2, lines 183–190)
- **Target Requirements**:
  - Primary headline evaluation: 350 gold-test queries evaluated across 3 primary configs (`full`, `no_ehr`, `no_classifier`) = **1,050 drafts**.
  - Scale evaluation: 1,000 silver-test queries evaluated across `full` and `no_ehr` = **2,000 drafts**.
  - Unified-context pilot: ~120 patient-specific gold-test queries evaluated on `unified_context` baseline.
- *Actual Status*: Awaiting Pillar B pipeline completion and formal eval freeze tag (`freeze-eval`).
- *Status*: `PENDING (Scheduled for Week 7 compute window)`.

---

### 2.5 Human Clinician Evaluation Protocol (Spec line 544)
- **Target Requirements**:
  - 40 gold-test queries (stratified: 20 patient-specific, 10 HIGH-urgency, 10 ambiguity/red-flag/conflict).
  - Blinded, randomized comparison between `full` and `no_ehr` drafts.
  - 2 independent raters judging relevance (1–5), medical usefulness (1–5), safety (binary), citation accuracy (binary), and would-approve-unchanged (binary).
  - Inter-rater agreement measured via Cohen's $\kappa$ and linear-weighted $\kappa$.
- *Actual Status*: Human rater outreach and annotation form setup pending.
- *Status*: `PENDING (Scheduled for Week 8)`.

---

### 2.6 Live Doctor-Edit Study (RQ3 / Spec lines 504–513, 545)
- **Target Requirements**:
  - 60 queries from `data/queries/rq3_stream.jsonl` reviewed across sequential sessions.
  - Typed edit memory (`edit_memory = true` vs `false`) alternated pseudo-randomly and blinded to reviewer.
  - Log review duration, sources opened, Levenshtein distance, and 12-category weighted edit burden.
  - Measure edit burden trajectory across interaction ordinal number ($1 \dots N$).
- *Actual Status*: Stream queries prepared (`rq3_stream.jsonl`); review session execution pending.
- *Status*: `PENDING (Scheduled for Week 8)`.

---

### 2.7 Scale Analyses (SA1 & SA2 / Spec lines 428, 546)
- **Target Requirements**:
  - **SA1 (KB Distractor Sweep)**: Evaluate Hit@5, MRR, and latency against KB subset sizes (18, 200, 500, 1,000, and full 10,074 chunks).
  - **SA2 (Patient Record Length Analysis)**: Evaluate candidate retrieval recall and EHR-fact accuracy across record size percentile buckets.
- *Actual Status*: Not yet executed.
- *Status*: `PENDING (Scheduled for Weeks 7–8)`.

---

## 3. Discrepancies and Outstanding Work Summary

1. **Prerequisite Dependency**: Pillar C execution cannot begin until Pillar B implementation is unfrozen, completed, and verified via end-to-end integration tests.
2. **Gold Human Annotation Prerequisite**: Human evaluation and headline gold ablations depend on independent human annotation of `data/queries/annotation_template_150.csv` and `data/queries/pooled_relevance_template.csv`.
3. **No Code Written for Harness**: Evaluation harness (`eval/run.py`) and metrics modules remain completely unwritten.
