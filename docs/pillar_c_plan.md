# Pillar C Plan — Evaluation Harness, Doctor Review, and Interface Systems
**Document Version:** 1.0  
**Authoritative Reference:** `CarePilot_AI_Master_Spec_v3.md` (Sections 3.1–3.4, 4.1–4.2, 5.1, Section 8, S9, S10, S11, S12, S13, Appendices A, C, D)  
**System Role:** Subsystem Plan for Pillar C (Evaluation Instrumentation, Metrics Engine, Human-in-the-Loop Review, and User Interfaces)

---

## 1. Pillar Objectives and Scope

Pillar C executes the rigorous empirical research protocol defined in **Master Spec Section 3**, integrating the clinical review interfaces (**S10**), the automated evaluation harness (**S13**), the human evaluation studies (**S13**), and the clinician-edit feedback analysis (**RQ3 / S9**).

### Research Questions Evaluated:
1. **RQ1 (Dual-Context Grounding)**: Does patient-scoped EHR retrieval combined with curated medical knowledge improve patient-specific factual accuracy and evidence-groundedness over knowledge-only retrieval? (**Spec lines 160–161**).
   - *Comparisons*: Primary `full` vs `no_ehr`; pilot `full` vs `unified_context` on patient-specific gold queries.
2. **RQ2 (Independent Urgency Triage & Red-Flag Safety)**: Does an independent calibrated classifier with negation-aware red-flag override reduce HIGH-acuity false negatives compared to LLM self-reported urgency? (**Spec line 162**).
   - *Comparisons*: `full` (classifier + red-flag) vs `no_classifier` (LLM-only self-assessment) vs offline classifier-only.
3. **RQ3 (Doctor-Edit Feedback Loop)**: Do reviewed doctor edits provide useful feedback for reducing future editing effort for similar query types? (**Spec line 163**).
   - *Comparisons*: Typed edit memory `on` vs `off` across the 60-query RQ3 stream.

---

## 2. Applicable Spec Requirements and Experimental Configurations

### Experimental Configurations (Spec Section 3.2, lines 183–190)
| Configuration ID | EHR Retrieval Branch | Classifier + Red-Flag Triage | LLM Self-Reported Urgency Used As Final | Scope / Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **`full`** | Yes (two-stage) | Yes | No (logged only) | Primary experimental arm; standard system pipeline. |
| **`no_ehr`** | No (knowledge only) | Yes | No (logged only) | Primary ablation arm; isolates contribution of EHR retrieval. |
| **`no_classifier`** | Yes (two-stage) | No (skipped) | Yes (authoritative) | Primary safety ablation arm; isolates LLM self-triage behavior. |
| **`unified_context`**| Yes (shared candidate pool) | Yes | No (logged only) | Pilot baseline arm; evaluated on ~120 patient-specific gold test queries. |

*Note*: Typed edit memory is a separate boolean toggle, forced `off` for all benchmark evaluation runs, and toggled only during live RQ3 clinician sessions (**Spec line 190**).

---

## 3. Metrics Engine and Statistical Protocol (Spec Section 8, lines 601–615)

The metrics suite is strictly pre-registered and partitioned by stage:

### 3.1 Retrieval Metrics
- **EHR Candidate Recall & Precision**: Evaluated on gold patient-specific queries with required EHR concept annotations.
- **KB Retrieval Performance**: Hit@3, Hit@5, and Mean Reciprocal Rank (MRR) evaluated against pooled relevance labels on gold-dev and gold-test.
- **Fusion Latency Profile**: p50 and p95 retrieval latency across dense, BM25, and hybrid fusion.

### 3.2 Safety and Triage Metrics (RQ2)
- **HIGH-Acuity False Negative Rate (FNR)**: Fraction of true HIGH cases undertriaged to routine or soon. Reported with **Wilson 95% Confidence Intervals** (**Spec line 194, 614**).
- **High-to-Low Under-Triage**: Severe failures where a HIGH-acuity case is misclassified as LOW (`routine`). Target: 0 errors.
- **False-Positive Escalation Rate**: Non-urgent cases falsely escalated to HIGH by rule triggers. Reported with Wilson 95% CI.
- **Queue Ordering Metric**: Mean rank position of HIGH-acuity cases in the simulated clinician queue.

### 3.3 Faithfulness, Citation, and Factual Accuracy Metrics (RQ1)
Per **Spec C29 (line 144) and Section 8 (lines 603–605)**, citation metrics are never collapsed into a single blended score:
1. **Citation Validity**: Fraction of cited chunk IDs that exist in the retrieved context set.
2. **Citation Coverage**: Fraction of draft sentences possessing at least one valid citation.
3. **Citation Entailment (NLI)**: Mean sentence entailment probability across cited sources via `cross-encoder/nli-deberta-v3-small`.
4. **Human Citation Accuracy**: Clinician binary judgment on whether each citation genuinely supports the claim.
5. **EHR-Fact Accuracy**: Fraction of patient-specific facts (medications, lab values, dates, conditions) matching authenticated EHR records; headline RQ1 metric.
6. **Conflict Resolution Rate**: Detection accuracy and unsafe silent-resolution rate on tagged patient-EHR discrepancies.

### 3.4 Clinician Edit and Burden Metrics (RQ3 / S9)
- **Edit Distances**: Normalized character-level Levenshtein distance:
  $$\text{Lev}_{\text{norm}} = \frac{\text{Lev}(\text{draft}, \text{final})}{\max(\text{len}(\text{draft}), \text{len}(\text{final}))}$$
  and word-level Levenshtein distance.
- **12-Category Weighted Edit Burden (Spec lines 506–507)**:
  $$\text{Edit Burden} = \frac{\sum_{i} \sum_{c \in \text{categories}_i} w(c)}{N_{\text{reviews}}}$$
  *Weights ($w$)*:
  - Weight 3: `urgency_correction`, `wrong_ehr_fact`, `unsupported_medical_claim`
  - Weight 2: `factual_correction`, `missing_ehr_fact`, `citation_error`, `retrieval_error`, `missing_caution`
  - Weight 1: `tone_change`, `unnecessary_content`, `other`
  - Weight 0: `no_change` (approved unchanged)
  *Sensitivity Analysis*: Evaluate under uniform weights ($w=1$) and safety-boosted weights ($w_{\text{safety}} \times 5$).
- **Review Effort Tracking**: `review_seconds`, `sources_opened`. Flag reviews under 10 seconds with 0 sources opened as `rubber_stamp_suspect`.

### 3.5 Statistical Significance Protocol
- **Paired Binary Outcomes**: McNemar's test.
- **Paired Continuous Outcomes**: Wilcoxon signed-rank test.
- **Multiple Comparisons Correction**: Holm-Bonferroni step-down correction.
- **Inter-Rater Reliability**: Cohen's $\kappa$ for binary ratings, linear-weighted $\kappa$ for ordinal urgency/scales.

---

## 4. Frontend Systems and Clinical Workspace (S10, S11)

### 4.1 Doctor Review Dashboard (`doctor-dashboard` — React 18 + Vite)
Clinical desktop workspace designed for high information density (**Spec lines 518–525**):
- **Paginated Queue**: Ordered by `urgency_final` descending, then `created_at` ascending. Eval consults strictly filtered out (`is_eval = false`).
- **3-Pane Clinical Review Workspace**:
  - *Left Pane (Patient Summary)*: Demographics, active conditions, active prescriptions, recent lab trends with reference ranges and abnormal flags.
  - *Center Pane (Thread)*: Chronological patient–clinic conversation thread.
  - *Right Pane (AI Draft & Review Console)*:
    - AI draft rendered sentence-by-sentence with interactive citation chips.
    - Source-type chips: `EHR`, `Knowledge`, `Mixed`, `Uncited`.
    - NLI faithfulness score badges per sentence.
    - Urgency breakdown banner displaying classifier score, LLM assessment, firm and soft red-flag matches.
    - Discrepancy banners for `patient_ehr_mismatch` or `missing_context`.
    - Interactive "Evidence is wrong" flag per citation.
    - Edit console with 12-category checkboxes, primary cause selector, structured reject reasons, and urgency override rationale.
    - One-click actions: Approve Unchanged, Edit & Approve, Reject & Write Manual.

### 4.2 Patient Mobile & Web Application (`patient-app` — Expo SDK 57)
Calm, accessible patient portal interface (**Spec lines 516–517**):
- **Safety Invariant I1**: Patients see **ONLY** doctor-approved final responses (`thread_status = 'approved' | 'edited_approved'`). Raw AI drafts are never exposed.
- **Emergency Intercept**: In the event of a firm red-flag hit, immediately renders a static emergency care instruction banner (e.g., directing patient to emergency services) without waiting for drafting or review (**D8**).
- **Status Machine Polling**: Displays real-time message state ("With your care team") via pull-to-refresh and polling.

---

## 5. Evaluation Harness and Study Protocols (S13)

### 5.1 Automated Evaluation Harness (`python -m eval.run`)
- Invoked via CLI:
  ```powershell
  python -m eval.run --config {full|no_ehr|no_classifier|unified_context} --split {gold-dev|gold-test|silver-dev|silver-test} --seed 42
  ```
- Reads queries from `data/queries/`, executes through the full pipeline, and writes complete trace JSONL files and summary metrics.
- Commits evaluation metadata into the `eval_runs` PostgreSQL table:
  `id, config, split, seed, git_commit, prompt_version, thresholds, kb_snapshot_id, ehr_dataset_id, data_manifest_sha256, started_at, finished_at`.

### 5.2 Human Evaluation Protocol (Spec line 544)
- **Sample Size**: 40 gold-test queries (minimum 20 for pilot designation).
- **Stratification**: At least 20 patient-specific, 10 HIGH-urgency, and 10 ambiguity/red-flag/conflict edge cases.
- **Arm Exposure**: Blinded and randomized drafts from `full` and `no_ehr`.
- **Raters**: 2 independent raters (clinically qualified where possible).
- **Dimensions Evaluated**:
  - Relevance (Likert 1–5)
  - Medical Usefulness (Likert 1–5)
  - Safety (Binary: safe / unsafe)
  - Citation Accuracy (Binary per citation)
  - EHR-Fact Accuracy (Binary per patient fact)
  - Would Approve Unchanged (Binary)
  - Pairwise Preference (full vs no_ehr)

### 5.3 Live Doctor Session Protocol (RQ3 / Spec line 545)
- **Sample Size**: 60 queries from [rq3_stream.jsonl](file:///d:/CarePilotAI/data/queries/rq3_stream.jsonl) (12 queries $\times$ 5 intents across 34 patients).
- **Design**: Reviewers evaluate cases in sequence; edit memory toggles (`on` vs `off`) pseudo-randomly based on hash of `consultation_id`, blinded to the reviewer.
- **Analysis**: Measure change in weighted edit burden across interaction ordinal number ($1 \dots N$).

### 5.4 Scale Sweeps (Spec S2, S13, lines 428, 546)
- **SA1 (KB Distractor Sweep)**: Evaluate Hit@5, MRR, and latency against KB subset sizes: 18 (core), 200, 500, 1,000, and full 10,074 chunks.
- **SA2 (Patient Record Size Sweep)**: Evaluate candidate retrieval recall and EHR-fact accuracy across patient record size percentiles (small, medium, long records).

---

## 6. Implementation Deliverables and Tracking

1. **Harness Skeleton (`eval/run.py`)**: Script wiring pipeline runs against test splits and logging to `eval_runs`.
2. **Metrics Computation Engine (`eval/metrics/`)**: Pure functions computing stage-wise retrieval, classification, faithfulness, edit burden, and Wilcoxon/McNemar statistics.
3. **Doctor Review Workspace (`doctor-dashboard`)**: Full 3-pane UI integrated with live backend review API.
4. **Patient App Review Flow (`patient-app`)**: Invariant I1 gate and emergency template renderers.
5. **Human Annotation App / Forms**: Spreadsheets or web forms capturing blinded rater evaluations for Cohen's $\kappa$ calculation.
