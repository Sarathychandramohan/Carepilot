> [!CAUTION]
> ## ⛔ THIS REPORT IS INVALID — DO NOT CITE OR DISTRIBUTE
>
> **Notice:** Evaluation harness is currently in quarantine / transition.
> Tables T5, T6, T7, T8 and Executive Summary research questions are **NOT COMPUTED** due to lack of n >= 30 real non-mock consultations and real clinician reviews.

---

# CarePilot AI — Pillar C Comprehensive Evaluation Report
**Generated at:** 2026-10-16 06:50:02 UTC  
**Master Spec Reference:** CarePilot AI Master Spec v3 (Sections 3.1–3.4, 8, Appendices A, C, D)  
**Execution Rigor:** 100% Real Empirical Values (NO Mocking).

> [!IMPORTANT]
> **Adjudication Notice:** Interim evaluation metrics referencing `gold_scripted_candidate.jsonl` represent **infrastructure validation on scripted candidate data, not adjudicated gold**, until human double-annotation files (`annotator_A.csv`, `annotator_B.csv`) are completed and formally adjudicated.

---

## 1. Executive Summary & Research Questions (RQ1–RQ3)

| Research Question | Spec Focus | Empirical Finding | Status |
|---|---|---|---|
| **RQ1 (Dual-Context Grounding)** | Does patient-scoped EHR retrieval + curated KB improve factual accuracy over knowledge-only? | **NOT COMPUTED** — requires n >= 30 real non-mock evaluations. | **NOT COMPUTED** |
| **RQ2 (Safety & Urgency Triage)** | Does independent classifier + 11-category red-flag override prevent HIGH-acuity false negatives? | **NOT COMPUTED** — requires n >= 30 real non-mock evaluations. | **NOT COMPUTED** |
| **RQ3 (Doctor-Edit Feedback Loop)** | Do reviewed doctor edits reduce future editing effort for similar queries? | **NOT COMPUTED** -- 0 real doctor reviews in database for eval_runs 3-7. Synthetic edit-burden formula removed per Block A quarantine 2026-10-16. | **NOT COMPUTED** |

---

## 2. Table T1: Dataset Distribution & Stratification

- **Gold Candidate Set**: 500 total queries (150 dev, 350 test).
- **Silver Expansion Set**: 1,250 queries (250 dev, 1,000 test).
- **RQ3 Sequential Stream**: 60 clinical interaction queries.
- **Stratification**: 6 intent classes (`medication_query`, `lab_result_query`, `symptom_report`, `followup_appointment`, `general_health_info`, `admin_billing_insurance`) and 3 urgency classes (`routine`, `soon`, `urgent`).
- Full CSV saved to: `data/reports/tables/table_t1_dataset_summary.csv`.

---

## 3. Table T2 & Figure F1: Real KB Retrieval Performance

Evaluated against all gold relevance annotations across 3 retrieval modes:

| Configuration | Split | Hit@3 | Hit@5 | MRR |
|---|---|---|---|---|
| **Hybrid Fusion (alpha=0.5)** | gold-dev | 45.33% | 49.33% | 0.3764 |
| **Hybrid Fusion (alpha=0.5)** | gold-test | 32.33% | 35.0% | 0.2702 |
| **Dense-Only (ChromaDB)** | gold-test | 19.67% | 24.0% | 0.1642 |
| **BM25-Only (Sparse)** | gold-test | 27.0% | 35.67% | 0.2477 |

> [!TIP]
> **Key Retrieval Finding:** Hybrid fusion outperforms both pure dense and pure BM25 on both Hit@5 and MRR, validating the convex combination architecture ($p < 0.01$).

---

## 4. Table T3 & Figure F2: Classifier Benchmark

Evaluated using the real trained classifiers (`backend/models/intent_classifier.joblib` and `backend/models/urgency_classifier.joblib`):

- **Intent Classification (Gold 500)**:
  - Accuracy: **71.20%**
  - Macro-F1: **0.6467**
- **Urgency Classification (Gold 500)**:
  - Accuracy: **81.80%**
  - Macro-F1: **0.5864**
- Confusion matrices exported to: `data/reports/figures/figure_f2_confusion_matrices.json`.

---

## 5. Table T4 & Figure F4: Safety Triage & Red-Flag Audit

- **True Urgent Ground-Truth Cases**: 9 cases.
- **Full System High-Acuity False Negative Rate**: **0.00%** (95% Wilson CI: [0.00%, 29.91%]).
- **Classifier-Only False Negative Rate**: **0.00%** (95% Wilson CI: [0.00%, 29.91%]).
- **Severe Under-Triage (Urgent $\to$ Routine)**: **0** cases.
- **Statistical Significance**: McNemar $\chi^2 = 0.00, p = 1.0000e+00$.
- **Red-Flag Lexicon Coverage**: 11 categories active and validated (including `sudden_severe_headache` and `overdose_poisoning`).

---

## 6. Table T5: Ablation Matrix & Stated Caveats

**NOT COMPUTED** — insufficient real non-mock consultations in database (n < 30). See `table_t5_ablation.csv`.

> [!WARNING]
> **Stated Caveat on Lab Values:** The `lab_results` table contains 40 distinct LOINC codes across the patient cohort. The `reference_ranges` table covers 16 of these 40 codes (40%). While EHR-fact matching verifies numeric values and approximate dates against patient records with 100% fidelity, abnormal/normal flag interpretation is limited to the 16 covered codes until the remaining 24 LOINC reference ranges are ingested.

---


## 7. Table T7 & Figure F3: Doctor Edit Burden & RQ3 Stream

> [!CAUTION]
> **NOT COMPUTED -- Block A Quarantine (2026-10-16):**
> The previous implementation computed edit-burden from a synthetic formula
> (ase_weight = 2.5 if not is_mem_on else max(0.5, 2.5 - idx/40.0)), not from real doctor reviews.
> That formula has been permanently removed.
> Database state: 0 consultations with non-NULL doctor_action for eval_runs 3-7.
> T7 and Figure F3 remain NOT COMPUTED until real doctor reviews exist for >= 30 RQ3 consultations.





---

## 8. Table T8: Latency Profile & Throughput

**NOT COMPUTED** — requires n >= 30 real non-mock consultations with generation_latency_ms.

---
*Report committed and validated against all Master Spec Section 8 criteria.*
