# Pillar A Plan — Data Collection, Scale-Up, and Indexing Engine
**Document Version:** 2.0 (Post-Execution Reconciliation)  
**Authoritative Reference:** `CarePilot_AI_Master_Spec_v3.md` (Sections 3.2, 3.4, 5.1–5.3, S1, S2, S4, S6, S15, Appendices C, D, E)  
**System Role:** Subsystem Plan for Pillar A (Data Layer, Medical Knowledge Base, Normalization, Triage Classifiers, and Benchmark Corpora)

---

## 1. Pillar Objectives and Scope

Pillar A establishes the foundational clinical data, external evidence knowledge base, terminology normalization, safety triage classifiers, and evaluation corpora required to support CarePilot AI's research design (**Spec Section 3.1–3.2**).

### Primary Objectives:
1. **Scale-Up Synthetic EHR Corpus (S1)**: Ingest realistic Electronic Health Records for at least 1,000 patients (target 2,000) using Synthea to support patient-scoped factual retrieval (**RQ1**).
2. **Curate and Dual-Index Medical Knowledge Base (S2)**: Collect, clean, deduplicate, and dual-index (dense vector + sparse BM25) public-domain clinical reference documents to support general medical evidence retrieval (**RQ1**).
3. **Clinical Terminology Normalization (S4)**: Provide a two-tier mapping system from patient colloquialisms to canonical SNOMED-CT, LOINC, and RxNorm codes with negation and temporal tagging.
4. **Safety Triage Classifiers and Red-Flag Pre-Check (S6)**: Train and calibrate intent and urgency classifiers, coupled with a frozen, negation-aware red-flag rule engine to establish independent clinical urgency triage (**RQ2**).
5. **Construct Stratified Query Corpora (S15)**: Author and generate Silver-synthetic training queries, candidate Gold human evaluation queries, and live RQ3 stream queries with strict scenario-family holdouts.

---

## 2. Applicable Spec Requirements and Numerical Targets

| Spec Section | Requirement / Asset | Minimum Floor | Target | Operational Constraint |
| :--- | :--- | :--- | :--- | :--- |
| **S1 (lines 408–420)** | Synthea Patient Records | 1,000 patients | 2,000 patients | Fixed seed `42`, preserve 40-patient CI fixture; stable ID format `ehr:{table}:{id}`; candidate query p95 $\le 200\text{ ms}$. |
| **S2 (lines 421–432)** | Curated KB Corpus | 500 documents | ~2,000 documents (20k–40k chunks) | Public-domain sources (MedlinePlus, openFDA/DailyMed, NIDDK, WHO); frozen snapshot manifest; dual-indexed (ChromaDB + BM25). |
| **S4 (lines 452–462)** | Terminology Normalization | Tier 1 Dictionary | Tier 1 + Tier 2 Embeddings | Concept resolution $\ge 90\%$; negation detection with 30-char window; regex temporal taggers. |
| **S6 (lines 471–480)** | Classifiers & Red-Flag | 3 Urgency / 5 Intent classes | Calibrated Logistic Regression on `bge-small` | Maximize HIGH recall subject to precision floor via tuned $\tau_{\text{high}}$; frozen negation-aware red-flag lexicon. |
| **S15 (lines 174–176, 204–206)** | Silver-Synthetic Queries | 3,000 queries | 6,000 queries | Split strictly by scenario family (train / dev / test); $\ge 30\%$ non-EHR queries (RQ1 fairness rule). |
| **S15 (lines 174, 204)** | Gold-Human Queries | 300 queries | 500 queries | Double-annotated, pooled relevance labels; dev (30%) / test (70%); frozen before eval. |
| **S15 (lines 176, 208)** | RQ3 Live Stream | 30 queries | 60 queries | 12 queries $\times$ 5 intents; zero overlap with Gold or Silver. |

---

## 3. Implementation Stages and Work Breakdown

### Stage A1: Synthetic EHR Scale-Up and Database Bulk Loading (S1)
- **S1-T1**: Schema definition for Synthea tables in PostgreSQL (`patients`, `encounters`, `conditions`, `medications`/`prescriptions`, `observations`/`lab_results`, `allergies`, `procedures`, `care_plans`, `immunizations`).
- **S1-T2**: Run Synthea generator with fixed seed `42` for Massachusetts demographic baseline.
- **S1-T3**: Ingest CSV outputs via PostgreSQL `COPY`, merging the 40-patient demo CI fixture without ID collision.
- **S1-T4**: Create B-tree indexes on `(patient_id, code, date)`, `(patient_id, status)`, and primary keys.
- **S1-T5**: Ingest LOINC lab reference ranges lookup table (`reference_ranges`) and add `is_outlier` flags for physiological artifacts.
- **S1-T6**: Generate Data Card and run query latency benchmark across 20 query samples per type.
- **S1-T7**: Build Patient Picker CLI tool to identify complex alive multi-morbidity patient records for query grounding.

### Stage A2: Medical Knowledge Base Ingestion and Dual Indexing (S2)
- **S2-T1**: Curate public-domain sources (openFDA drug labels, MedlinePlus health topics and lab tests, NIDDK, WHO).
- **S2-T2**: Crawl and extract text, stripping HTML navigation, boilerplate, and scripts.
- **S2-T3**: Deduplicate documents via SHA-256 and exact URL matching.
- **S2-T4**: Chunk documents into 400-token chunks with 60-token overlap; assign stable IDs `kb:{doc_id}:chunk{n}` or `KB-{doc_id}_chunk_{n}`.
- **S2-T5**: Embed chunks using `BAAI/bge-small-en-v1.5` and upsert into ChromaDB collection.
- **S2-T6**: Build sparse inverted index using `rank_bm25` (`BM25Okapi`) over the exact same chunk corpus.
- **S2-T7**: Verify 100% synchronization between dense and sparse chunk IDs; freeze snapshot manifest with SHA-256 hash.

### Stage A3: Terminology Normalization and Clinical Anchors (S4)
- **S4-T1**: Build Tier 1 regex dictionary from loaded Synthea code tables (SNOMED, LOINC, RxNorm) and colloquial phrases.
- **S4-T2**: Establish Tier 2 embedding fallback against canonical concept vectors.
- **S4-T3**: Implement rule-based negation detection (lookback window of 30 characters) and temporal duration/anchor taggers.

### Stage A4: Triage Classifiers and Red-Flag Rule Engine (S6)
- **S6-T1**: Formulate intent classes (`symptom_report`, `medication_query`, `lab_result_query`, `followup_appointment`, `general_health_info`) and urgency classes (`routine`, `soon`, `urgent`).
- **S6-T2**: Train calibrated Logistic Regression models on dense `bge-small` embeddings of training queries.
- **S6-T3**: Tune decision thresholds on dev split: $\tau_{\text{high}}$ for safety-prioritized urgent classification, $\tau_{\text{intent}}$ for routing low-confidence queries to `unsupported`.
- **S6-T4**: Implement negation-aware red-flag rule engine across emergency categories with firm-hit override and soft-hit advisory logging. Freeze code with SHA-256 checksum.

### Stage A5: Benchmark Datasets and Annotation Infrastructure (S15)
- **S15-T1**: Generate Silver-synthetic queries instantiated against complex patient records, partitioned strictly by scenario family across train, dev, and test.
- **S15-T2**: Construct candidate Gold evaluation pool (500 queries) with adversarial and unsupported cases.
- **S15-T3**: Generate pooled relevance labeling templates (`pooled_relevance_template.csv`) combining top-10 dense, top-10 BM25, top-10 hybrid, and 5 random controls.
- **S15-T4**: Prepare independent human annotation templates for intent/urgency (`annotation_template_150.csv`) and red-flag validation (`redflag_heldout_template.csv`).
- **S15-T5**: Construct 60-query RQ3 stream balanced across 5 intents for clinician edit evaluation.

---

## 4. Dependencies and Inter-Pillar Handoffs

```
[Synthea 2k Engine] ──> [PostgreSQL: carepilot_v3] ──> (Pillar B: Two-Stage EHR Retrieval P5)
[Public Medical Docs] ──> [ChromaDB + BM25 v5.1]   ──> (Pillar B: Hybrid KB Retrieval P5)
[Concept Dictionaries] ──> [normalize.py]           ──> (Pillar B: Pre-Retrieval P3)
[Trained Calibrated Models] ──> [classify.py]      ──> (Pillar B: Triage P4)
[Frozen redflag.py]    ──> [Emergency Gate]         ──> (Pillar B: Pre-Check P2)
[Silver/Gold/RQ3 Sets] ──> [data/queries/]          ──> (Pillar C: Evaluation Harness S13)
```

---

## 5. Acceptance Criteria and Verification Gates

1. **Gate G1 (Infrastructure & Data Pipelines)**:
   - At least 1,000 patients loaded in PostgreSQL (target 2,000); patient query p95 latency $\le 200\text{ ms}$.
   - At least 500 KB documents indexed (target ~2,000); ChromaDB and BM25 indexes completely synchronized.
   - All EHR rows and KB chunks carry stable, persistent identifiers.
2. **Gate G2 (Classifier & Freeze Gate)**:
   - Intent and urgency classifiers trained on silver train split; $\tau_{\text{high}}$ and $\tau_{\text{intent}}$ calibrated on dev.
   - Red-flag rule engine frozen with SHA-256 hash committed.
   - Scenario-family holdout strictly enforced with zero cross-split template leakage.
   - Gold candidate and pooled relevance templates exported and frozen.

---

## 6. Architectural and Implementation Decisions

- **D-01 (Database Schema)**: PostgreSQL database named `carepilot_v3` (superseding pre-execution placeholder `carepilot_db`). Preserved the 40-patient CI fixture alongside the 2,290 scaled patients for a total of 2,330 patients.
- **D-02 (KB Versioning)**: Knowledge base frozen at snapshot `v5.1` with 10,074 chunks across 1,045 documents, synchronizing ChromaDB collection `carepilot_kb_v5` and sparse index `bm25_index_v5.pkl`.
- **D-03 (Split Leakage Rule)**: Partitioning must hold out whole scenario families, not individual queries (**Spec line 143, 175**).
- **D-04 (Red-Flag Independence Rule)**: Agent-authored test tables (`redflag_test_table.json`, `redflag_held_out_table.json`) are labeled `"agent-authored, NOT a validation set"`. Only independent human clinician completions of `redflag_heldout_template.csv` count as real validation.
