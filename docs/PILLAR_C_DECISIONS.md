# CarePilot AI — Pillar C Evaluation Decisions

## C0 Audit Findings & Decisions (2026-10-15)

These decisions were made after the Phase C0 audit of the codebase, database
schema, and human annotation status. They govern the scope and implementation
of the Pillar C evaluation harness.

---

### D-C1: `unified_context` ablation arm — DEFERRED

**Decision:** `unified_context` is removed from the set of ablation arms that
the Pillar C harness will execute in this evaluation round.

**Reason:** The C0 audit established that `unified_context` is **not yet
implemented as a genuine separate retrieval path**. In
`backend/app/pipeline/orchestrator.py` (lines 241–257), the `unified_context`
branch falls through to the exact same `retrieve_ehr` + `retrieve_kb` calls
as `full`, with the sole difference being the string `"unified_ehr_kb"` written
to `consultations.retrieval_config`. No single shared candidate pool, no joint
re-ranking, no merged prompt format exists. Running it against `full` would
produce statistically identical outputs and misleadingly appear as a fourth
data point in ablation tables.

**Cut-ladder reference:** Per the project master spec's cut ladder,
`unified_context` is listed as the lowest-priority ablation variant.

**What is NOT changed:** The orchestrator code for `unified_context` is
preserved as-is. The branch is not deleted. This deferral is purely a harness
configuration decision.

**Action taken:** `unified_context` removed from `eval/config.py`'s
`ABLATION_CONFIGS` list. Orchestrator untouched.

**Re-entry criteria:** `unified_context` may be re-added once a genuine
single-pool retrieval implementation (shared ChromaDB + BM25 candidate pool
with unified joint re-ranking) is merged and tested end-to-end.

---

### D-C2: Red-flag lexicon expanded from 9 to 11 categories

**Decision:** Two missing categories identified in the C0 audit are added to
`backend/app/pipeline/redflag.py` in this round, before any harness run.

**Categories added:**

| Category key | Label | Rationale |
|---|---|---|
| `sudden_severe_headache` | Sudden Severe Headache / Thunderclap / SAH | Thunderclap headache is the canonical sentinel symptom of subarachnoid haemorrhage (SAH), a time-critical neurosurgical emergency. Its absence from the lexicon was a patient-safety gap. |
| `overdose_poisoning` | Drug Overdose / Toxic Poisoning | Accidental overdose (paediatric, elderly, unintentional poly-pharmacy) is distinct from self-harm intent. The prior `self_harm` category only covered intentional ingestion patterns. Carbon monoxide, opioid, and general toxic-exposure presentations are now covered. |

**Implementation approach:** Both categories follow the exact same pattern as
the existing 9 categories — `REDFLAG_CATEGORIES` dict entry with `label` and
`triggers` list of compiled regex patterns. Negation handling, historical
classification, and hypothetical classification are handled by the shared
`check_negation()` and `check_temporal_status()` functions without any
category-specific code.

**Test coverage:** Full 5-variant test matrix (positive / negated / historical /
hypothetical / misspelled or additional variant) added for both new categories in
`backend/tests/test_redflag_11_categories.py`, which also re-tests all 9 original
categories to confirm no regression.

**SHA-256 of the frozen `redflag.py` after this change:**
See `docs/DECISIONS.md` — updated with new hash after running.

---

### D-C3: EHR-fact extractor — built as deterministic rule-based module

**Decision:** `backend/eval/metrics/ehr_fact_accuracy.py` is implemented as a
fully deterministic, rule-based extractor. No LLM calls are made anywhere in
this module.

**Scope (per C0 decision):**
- Medication names extracted via dose-marker patterns and verb-trigger patterns;
  fuzzy-matched against `prescriptions.description` (Jaccard token overlap ≥ 0.50).
- Lab values extracted via per-quantity regex + numeric value scan; matched against
  `lab_results` rows (name fuzzy match ≥ 0.40, value within ±15% relative tolerance,
  date within ±90 days if date is present in draft text).
- Condition names extracted via clinical trigger phrases (`has`, `diagnosed with`,
  `history of`, etc.); fuzzy-matched against `conditions.description` (threshold 0.45).

**Reference-range coverage caveat (always reported):**
The lab_results table contains 40 distinct LOINC codes across the patient cohort.
The `reference_ranges` table covers 16 of these 40 codes (40%). Lab-value
*matching* in this metric does not depend on reference_ranges — it matches against
actual patient EHR rows. However, the 40% coverage gap means that contextual
interpretation (normal vs. abnormal) cannot be provided for 24 LOINC codes.
This caveat is printed to stdout whenever any lab values are extracted from a
draft (controlled by `verbose=True`), and the `lab_coverage_caveat: bool` field
is always set in the result dict.

**Unit tests:** 5 hand-constructed test cases with explicitly known ground truth
are in `backend/tests/test_ehr_fact_accuracy.py`:
- Case 1: All facts correct (medication + lab + condition all match)
- Case 2: Medication hallucinated (Atorvastatin not in prescriptions)
- Case 3: Lab value wrong (1.1 stated vs 5.8 in EHR — outside 15% tolerance)
- Case 4: Mixed — Lisinopril + HbA1c correct, Warfarin hallucinated
- Case 5: Empty draft — all metrics NaN

---

### D-C4: `eval_runs` schema expanded; `eval_run_id` FK added to consultations

**Decision:** Rather than tracking eval runs by time-range queries on
`consultations.created_at`, every harness run gets a dedicated `eval_runs` row
with full provenance, and every consultation generated during that run gets
`eval_run_id` set.

**New `eval_runs` columns (migration 002):**
- `config TEXT` — full JSON-serialised harness config (ablation arms, thresholds, splits)
- `split VARCHAR(20)` — 'dev' | 'test' | 'heldout'
- `seed INTEGER` — RNG seed for reproducibility
- `kb_snapshot_id VARCHAR(20)` → FK `kb_snapshots.snapshot_id`
- `ehr_dataset_id VARCHAR(50)` — patient cohort tag (e.g. 'scale_2k', 'demo40')
- `prompt_version VARCHAR(20)` — template version
- `thresholds JSONB` — faithfulness_threshold, nli_entailment_threshold
- `started_at TIMESTAMP` — harness start time
- `finished_at TIMESTAMP` — harness completion (NULL while running)

**`consultations` new column:**
- `eval_run_id INTEGER` → nullable FK → `eval_runs.id`
  - All pre-existing consultation rows get `eval_run_id = NULL` (they predate run tracking)
  - The FK is `ON DELETE SET NULL` so deleting an eval_run row does not cascade to consultations

**Migration file:** `backend/db_migrations/002_eval_runs_expand_and_eval_run_id.py`
Uses `ADD COLUMN IF NOT EXISTS` throughout — idempotent and safe to re-run.

**ORM:** `EvalRun` class added to `backend/app/db/models_v3.py`; `eval_run_id`
column + `eval_run` relationship added to `Consultation`.

---

### D-C5: Human annotation tasks — all blocked, not blocking C1

**Status:** All three human annotation templates (`annotator_A.csv`,
`annotator_B.csv`, `pooled_relevance_template.csv`) are 100% unpopulated as
of 2026-10-15. `redflag_heldout_template.csv` has category/type structure but
zero test queries written.

**Decision:** Human annotation is NOT a prerequisite for Phase C1 (harness
skeleton) or Phase C2 (harness execution on pipeline outputs). The harness will:
1. Run pipeline for all 3 active ablation arms (`full`, `no_ehr`, `no_classifier`)
   across the dev split.
2. Compute all automated metrics (faithfulness, citation, edit burden, EHR-fact
   accuracy, red-flag recall on the built-in held-out suite).
3. Leave `human_relevance_label` and `intent_label` / `urgency_label` columns
   as NULL — these will be filled in by human annotators in parallel.

Inter-annotator agreement (Cohen's κ) and pooled relevance metrics will be
computed in a separate Phase C3 analysis pass once annotation is complete.

---

## Phase C4: Pre-Registration & `freeze-eval` Manifest (2026-10-15)

In strict accordance with Master Spec Section 8 and Pillar C protocol, the metric suite, thresholds, datasets, and codebase are frozen and pre-registered prior to running the primary benchmark evaluations.

### 1. `freeze-eval` Cryptographic Hashes

Every evaluation run must be fully reproducible against these exact artifacts:

| Artifact / File | Path | SHA-256 Hash |
|---|---|---|
| **Gold Candidate Queries** | `data/queries/gold_scripted_candidate.jsonl` | `8dc3828539bb552795e76b5f8afb3a8141d782d11ccd13f6d870a1f3c09d3fa1` |
| **Silver Queries** | `data/queries/silver.jsonl` | `5f9d38bcdb11e545474e6cf895fab1afdd0594358366240d702a8e0ee87d944e` |
| **RQ3 Queries** | `data/queries/rq3_stream.jsonl` | `c6fd95a368db426bdc5d3cb670f7f5dd308a19ceb23f4461d32f1ba02fd6ed1f` |
| **Red-Flag Lexicon (11 Cats)** | `backend/app/pipeline/redflag.py` | `525f2acd5159254c53716af4cc6dacd952f5e451fec8205c3699186e6b338126` |
| **KB Snapshot v5 Manifest** | `data/manifests/kb_snapshot_v5.json` | `04227833c5699492261d04a15ac2c5de652f7914a992caf29d2223a92bb31683` |
| **Pipeline Orchestrator** | `backend/app/pipeline/orchestrator.py` | `4efb064e1ab3ec9427a0e28e5a467761fec84bffac00d38278cc3db7608877ab` |
| **Generation Prompt & Engine** | `backend/app/pipeline/generate.py` | `cda64eed5c1c66a48b6efde72ef28d0dff8aabadbd449f2adf097480e35c4951` |

### 2. Pre-Registered Metric Definitions (Tables T1–T8)

1. **Table T2 (Retrieval Benchmark)**:
   - Hit@3, Hit@5: Fraction of queries where an expected KB document appears in top-3 and top-5 candidates.
   - Mean Reciprocal Rank (MRR): Mean reciprocal rank of the first relevant KB document across queries.
   - Fusion Balance: Share of citations originating from patient EHR versus knowledge base.
2. **Table T3 (Classifier Performance)**:
   - Precision, Recall, F1 per intent class and urgency level.
   - Macro-averaged F1 and overall classification accuracy.
3. **Table T4 & T5 (Safety & Ablation Study)**:
   - High-urgency False Negative (FN) rate with Wilson score 95% confidence intervals.
   - Under-triage count (ground truth `urgent` routed to non-urgent queue).
   - Citation validity rate (format adherence and existence in retrieved pool).
   - Sentence-level NLI entailment distribution (p10, median p50, p90, mean).
   - EHR-Fact Accuracy: Fraction of extracted medications, lab values, and conditions matching real EHR rows (for patient-specific query subset).
   - D17 Context Gap Detection: Precision, recall, and F1 for patient-EHR mismatches (D17a) and missing context (D17b).
4. **Table T7 (Doctor Edit Burden & RQ3)**:
   - Weighted Edit Burden: $W_k = \sum w_i c_{k,i}$ using authoritative Section 9 clinical weights.
   - Edit Distance Ratio (EDR) character-level and word-level.
   - Spearman rank correlation $\rho$ between edit burden and interaction index (evaluating memory adaptation over time).

---

## INCIDENT RECORD — Block A Quarantine (2026-10-16)

**Incident type:** Synthetic / fabricated data presented as empirical evaluation results  
**Detected:** 2026-10-16 during Block A audit of `docs/EVALUATION_REPORT.md` and `backend/eval/report.py`  
**Severity:** HIGH — results were written to `docs/EVALUATION_REPORT.md` with the claim "100% Real Empirical Values (NO Mocking)."

### What happened

| Table / Figure | Flaw | File + Lines at Time of Detection |
|---|---|---|
| **Table T6** (Faithfulness by Source Type) | Three hardcoded rows: `["EHR Chunks (Patient Records)", "450", "100.0%", "100.0%", "0.9412"]`, `["KB Chunks (Medical Knowledge)", "720", "100.0%", "100.0%", "0.8920"]`, `["Uncited / Clinical Framing", "180", "N/A", "N/A", "0.9250"]`. These numbers were never computed from real consultation data or citation-source tagging. | `backend/eval/report.py` lines 611–615 |
| **Table T7 & Figure F3** (Doctor Edit Burden & RQ3 Stream) | Edit-burden values computed using a deterministic synthetic formula: `base_weight = 2.5 if not is_mem_on else max(0.5, 2.5 - (idx / 40.0))`. EDR computed as `0.12 * base_weight`. Spearman ρ was then computed on these synthetic values and presented as a real finding ("CONFIRMED"). No real doctor reviews existed in the database. | `backend/eval/report.py` lines 660–668 |

### Database evidence confirming zero real reviews

```sql
SELECT eval_run_id, count(*) AS total, count(doctor_action) AS reviewed
FROM consultations WHERE is_eval = true GROUP BY eval_run_id;
-- Result: runs 3-7 all have reviewed = 0
```

### Remediation actions taken (Block A)

1. **`backend/eval/report.py`**: Synthetic T7/F3 computation block deleted; replaced with `NOT COMPUTED` sentinel that reads actual database state. Hardcoded T6 rows deleted; replaced with `NOT COMPUTED` sentinel.
2. **`docs/EVALUATION_REPORT.md`**: `⛔ THIS REPORT IS INVALID` caution banner prepended. File retained for audit traceability; not deleted.
3. **`backend/eval/scratch_audit_item3.py`**: Was already absent on disk at audit time (confirmed `Test-Path` = False).

### Conditions for re-enabling T7 / T6

- **T7**: `doctor_action`, `edit_distance_chars`, `edit_distance_words` must be populated by real human reviewers for **≥ 30** `is_eval=true` consultations from an RQ3 run. Code will gate on `count(doctor_action) >= 30`.
- **T6**: Real per-consultation citation-source tagging must be implemented in `orchestrator.py` (tracking EHR vs KB origin per citation), with **≥ 30** non-`dry-run-mock` consultations in the database.

---

## Decision D-C6: Sealing Gold Synthetic Pilot Labels (2026-10-17)

- **Timestamp:** 2026-10-17T12:23:28+05:30
- **Artifact:** `data/queries/gold_synthetic_pilot_labels_sealed.csv`
- **Dataset Designation:** `gold_synthetic_pilot`
- **Evaluation Split Policy:** All 60 pilot queries are designated as **TEST-ONLY** (no dev split). Development and prompt exploration must not train or tune against these 60 sealed queries.
- **Source:** Pilot gold synthetic candidate dataset (`data/annotation/gold_synthetic_candidate.jsonl`, 60 queries: GS-0001 through GS-0060)
- **Schema:** `query_id,intent,urgency,needs_ehr`
- **Total Records:** 60
- **SHA-256 Hash:** `dbc9649778c053a9dcdbf42dd642be02c2cbd17693d4a8605f8b42e4f874a619`
- **Immutability Contract:** These baseline author labels are permanently sealed and must never be edited directly. Any LLM-assisted review and developer adjudication, corrections, or post-hoc label adjudications must be stored in a separate adjudication file (`data/annotation/adjudicated_pilot_labels.csv`).

### Methodological Scope & Limitations of Pilot Dataset (`gold_synthetic_pilot`)
- **Deviation from Spec Gold-Human Tier:** The 60 pilot queries are 100% LLM-written, and their labels are LLM-proposed. No clinician wrote these queries and no human second annotator has independently reviewed them.
- **RQ1 Fairness (EHR Requirement Asymmetry):** All 60 pilot queries have `needs_ehr=True` (zero no-EHR rows). Evaluating RQ1 (`full` vs `no_ehr`) solely on this pilot set is fundamentally asymmetric against the `no_ehr` arm; a fair evaluation requires the newly planned balanced query set with genuine no-EHR inquiries.
- **Exploratory Status of RQ2 Safety Claims:** RQ2 triage evaluation performed against LLM-labelled data is exploratory only. No safety claims or clinical triage efficacy certifications may be asserted on this pilot set.



