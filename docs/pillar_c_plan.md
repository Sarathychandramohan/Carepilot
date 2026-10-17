# Pillar C Plan — Evaluation Harness, Benchmark, and Reproducibility Suite

**Document Version:** 3.0 (Aligned with Master Plan v5 & Post-Phase-5 State)  
**Authoritative Reference:** `docs/MASTER_PROJECT_PLAN_v5.md` (Sections 2, 4, 6, 7, 9, 10, 11)  
**System Role:** Subsystem Specification and Evaluation Protocol for Pillar C (Benchmark Construction, Evaluation Harness CLI, Statistical Metrics Engine, and Provenance Auditing)  
**Current Git State:** Pre-registered, implemented, and frozen under tag `freeze-eval` at commit `c9a1239` (branches `main` and `friend` at `fee80e4` / `0f7f40a`)

---

## 1. Pillar Objectives and Scope

Pillar C executes the pre-registered scientific evaluation of CarePilot AI, measuring system behavior across clinical safety, factual grounding, retrieval accuracy, linguistic readability, and runtime efficiency (**Master Plan Section 4**).

### Evaluated Research Questions:
1. **RQ1 (EHR Grounding)**: Does patient-scoped EHR retrieval improve coverage of patient-specific clinical facts without increasing unsupported or hallucinated claims? (`full` vs `no_ehr`).
2. **RQ2 (Urgency & Safety Triage)**: Does an independent calibrated classifier with red-flag overrides reduce dangerous under-triage compared with LLM self-reported urgency, specifically on keyword-free urgent inquiries? (`full` vs `no_classifier`).
3. **RQ3 (Doctor-Edit Instrumentation)**: Is the clinician review and edit stream reliably instrumented with structured diffs and timestamps without making unsubstantiated efficacy claims? (Instrumented, not evaluated).
4. **RQ4 (Readability vs. Faithfulness)**: Does a readability controller reduce response complexity to grade $\le 8$ without sacrificing evidence faithfulness or clinical completeness? (`full` vs `no_readability`).

---

## 2. Benchmark Dataset Architecture

Pillar C departs from unfeasible human-rater plans, adopting a transparent, reproducible benchmark protocol:

| Dataset Tier | Size | Composition & Construction | Intended Scientific Use |
|---|---|---|---|
| **`gold_synthetic`** | **150 queries** | 60 pilot (`S0001`–`S0060`) + 90 new queries authored from validated patient context packs. Stratified: ~60 urgent (20 explicit red-flag + 40 keyword-free), 40 soon, 50 routine. | **Primary benchmark** for headline reporting. Labelled blind by a 3-model LLM panel (ChatGPT, Gemini, Claude). |
| **Red-Flag Held-Out Set** | **$\ge 72$ queries** | Authored strictly blind to the lexicon; covers all 11 emergency categories with positive emergencies and negative hard non-emergencies. | **E3 Safety Evaluation**. Frozen; zero tuning permitted against this set. |
| **Silver Dataset** | **3,770 queries** | Templated synthetic queries across 29 clinical families (Train: 1,690, Dev: 1,040, Test: 1,040). | Classifier training, dev threshold tuning, and EHR-matching tests. **Never** used for headline generalization claims. |
| **Old Candidate Set** | 500 queries | `gold_scripted_candidate.jsonl` (contains only ~35–40 distinct base scenarios). | **Historical artifact only**. Immutable; excluded from headline benchmark reporting. |
| **RQ3 Stream** | 60 queries | `rq3_stream.jsonl` (12 queries $\times$ 5 intents across 34 patients). | Clinician review instrumentation and logging tests only. |

### Blind 3-Model LLM Panel Labelling Protocol
- **Panel**: Three independent model sessions (ChatGPT, Gemini, Claude) review each query with age and sex metadata, blind to each other's outputs and target pipeline drafts.
- **Rubric**: Standardized public emergency guidance defining 5 intent classes and 3 urgency levels.
- **Aggregation**: Majority vote determines primary label. Disagreements and unresolvable ties are logged and reported.
- **Safety Rule**: **Any-Vote-Urgent** (if any panel member votes urgent, the query is marked urgent) serves as the conservative primary safety set; unanimous-urgent serves as secondary.
- **Disclosure**: Authors disclose that Claude writes candidate queries and also participates on the labelling panel, noting potential shared-family bias.

---

## 3. Evaluation Suite: E1 through E10

All evaluations are executed via the unified CLI runner: `python -m backend.eval.run`.

### E1: Intent Classification
- **Dataset**: `gold_synthetic` (150 rows); silver-dev used for tuning.
- **Metrics**: Per-class Precision, Recall, F1-score, Macro-F1, Confusion Matrix, Majority-Class Baseline.
- **Expected Outcome**: Real gold generalization will be lower than templated silver (which previously scored 100% due to template similarity).

### E2: Urgency Triage & Safety Under-Triage
- **Dataset**: `gold_synthetic`, emphasizing the 40 keyword-free urgent queries.
- **Metrics**: Per-class Recall, Urgent Miss Rate (with **Wilson 95% Confidence Intervals**), Urgent-to-Routine Error Count, Soon-to-Routine Rate, False Escalation Rate.
- **Comparison**: `full` (Classifier + Red-Flag) vs `no_classifier` (LLM-only urgency self-assessment).
- **Statistical Test**: Exact paired McNemar's test with Holm-Bonferroni step-down correction.

### E3: Red-Flag Lexicon Evaluation
- **Dataset**: Separately held-out set ($\ge 72$ rows).
- **Metrics**: Positive Emergency Recall, False Escalation Rate on hard negatives, Wilson 95% CIs, Failure category list.
- **Rule**: Frozen; zero tuning on held-out errors.

### E4: Knowledge Base Retrieval Accuracy
- **Dataset**: Pooled top-$k$ candidates from dense-only, BM25-only, and hybrid fusion.
- **Metrics**: Hit@3, Hit@5, Mean Reciprocal Rank (MRR), query coverage.
- **Relevance**: Labelled via standardized LLM judge with a second-family cross-check on 25% of the pool.
- **Comparison**: Paired comparison of hybrid fusion vs the best single retriever.

### E5: EHR Grounding & Factual Accuracy (RQ1)
- **Dataset**: `gold_synthetic` + family-stratified silver-test subsample.
- **Metrics**: EHR-Fact Coverage, Hallucinated Patient Fact Rate, Unsupported Claim Rate, Contradiction Rate, Skip Rate.
- **Comparison**: `full` vs `no_ehr` evaluated on paired rows where drafts were produced.
- **Statistical Test**: Cluster bootstrap by distinct query scenario and patient (95% CI).

### E6: Multi-Gate Validation Analysis
- **Dataset**: Generated drafts with granular stage-level logs.
- **Metrics**: Pass/fail rate per gate (Citation validity, coverage, NLI entailment, contradiction ceiling).
- **Analysis**: Real row-level failure examples and offline gate-off counterfactual comparison.

### E7: Readability & Completeness Trade-Off (RQ4)
- **Arms**: Plain LLM vs CarePilot without controller vs CarePilot with controller.
- **Metrics**: Flesch–Kincaid Grade Level ($\le 8$), Word Count, Complexity, Subjectivity, Sentiment, Claim Support, Completeness, Empathy proxy.
- **Analysis**: Paired trade-off curve testing whether simplification lowers reading grade without sacrificing clinical accuracy or completeness.

### E8: Metamorphic Safety Tests
- **Methodology**: Deterministic invariance checks across 8 controlled input transformations:
  1. *Paraphrase Invariance*: Meaning-preserving rewrites preserve triage.
  2. *Red-Flag Monotonicity*: Adding a red-flag symptom never lowers urgency.
  3. *EHR Swap Sensitivity*: Changing patient EHR changes patient-specific claims but not unrelated symptom urgency.
  4. *Contradiction Handling*: Injected EHR contradictions are flagged or rejected.
  5. *Negation Invariance*: Red-flag negation ("no chest pain") does not escalate.
  6. *Readability Preservation*: Simplification preserves all numbers, units, meds, and negation.
  7. *Patient Isolation*: Zero cross-patient fact leakage (**Invariant I2**).
  8. *Missing-Context*: Absent context emits clarification, not fabrication.

### E9: Runtime Efficiency and Latency Profiling
- **Metrics**: End-to-end latency per draft, stage latencies (triage, retrieval, generation, validation), median and p90 times, JSON schema compliance.
- **Telemetry**: Host hardware telemetry (GeForce RTX 2050 / Ryzen 5 / 16GB RAM) logged with model tag `qwen3:8b`.

### E10: Doctor Edit Instrumentation (RQ3)
- **Implementation**: Structured review logging (`consultations` table) capturing review duration, sources opened, Levenshtein character/word distances, and 12-category weighted edit burden.
- **Claim Boundary**: Marked strictly as **instrumented, not evaluated**. No clinical efficacy or learning claims are made.

---

## 4. Pre-Registration & Reproducibility Protocol

1. **Centralized Configuration**: All thresholds (`tau_high = 0.25`, `tau_soon = 0.30`, `tau_intent = 0.45`, `retrieval_alpha`, NLI thresholds) are imported from `backend/eval/config.py` and synchronized with runtime code.
2. **Clean Working Tree Guard**: Non-dry-run evaluations automatically abort if `git status --short` detects uncommitted modifications.
3. **Run Provenance**: Every run persists in `eval_runs` with:
   `run_id, eval_query_id, git_commit, dataset_hash, kb_snapshot_hash, config_json, prompt_id, seed, dry_run, started_at, finished_at`.
4. **Invalid Run Filtering**: Older exploratory runs (runs 2–8) that used unverified thresholds are explicitly marked `invalid` in PostgreSQL and filtered out by `backend/eval/report.py`.
5. **Freeze Verification**: Pre-registration decisions locked in `docs/PILLAR_C_DECISIONS.md`; manifest fingerprints locked in `docs/eval_manifest.json` under Git tag `freeze-eval` (commit `c9a1239`).
