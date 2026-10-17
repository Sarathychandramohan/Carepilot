# Pillar A Plan — Synthetic EHR, Clinical Knowledge Base, and Normalization Engine

**Document Version:** 3.0 (Aligned with Master Plan v5 & Post-Phase-5 State)  
**Authoritative Reference:** `docs/MASTER_PROJECT_PLAN_v5.md` (Sections 1, 3, 5, 6)  
**System Role:** Subsystem Specification and Data Layer Plan for Pillar A (Synthea Longitudinal EHR, Curated Medical Knowledge Base, Terminology Normalization, and Offline Artifact Bundling)  
**Current Git State:** Implemented, scaled, and verified on branches `main` and `friend` (commit `fee80e4` / `0f7f40a`)

---

## 1. Pillar Objectives and Scope

Pillar A establishes the foundational clinical data engineering, external medical knowledge indexing, terminology normalization, and external data packaging required to support CarePilot AI's research pipeline (**Master Plan Section 3**).

### Primary Objectives:
1. **Longitudinal Synthetic EHR Generation & Scaling**: Generate and normalize realistic Electronic Health Records for a research cohort exceeding 2,000 patients using Synthea, enforcing zero real patient data (PHI) exposure.
2. **Dual-Index Medical Knowledge Base**: Curate, clean, chunk, and dual-index (dense vector + sparse BM25) authoritative public-domain medical reference material to support evidence-grounded drafting (**RQ1**).
3. **Clinical Terminology Normalization**: Map patient colloquial phrases to canonical SNOMED-CT, LOINC, and RxNorm concepts with negation and temporal tagging.
4. **Offline Transfer Packaging**: Package heavy database dumps, vector embeddings, and secrets into the verified **`CarePilotAI_Transfer`** bundle for seamless collaboration via Google Drive.

---

## 2. Applicable Requirements and Verified Assets

| Component / Subsystem | Spec Target | Actual Verified Repository Asset | Operational Notes |
|---|---|---|---|
| **EHR Database** | $\ge 2,000$ patients in PostgreSQL | **PostgreSQL 18 `carepilot_v3`** | **2,330 patients** (2,030 alive, 300 deceased), ~2.5M rows across 9 clinical tables. |
| **LOINC Lab Range Lookup** | Reference ranges & outlier tagging | `reference_ranges` table in `carepilot_v3` | Flags physiological artifacts (`is_outlier = true`) for prompt caveats. |
| **Knowledge Base Corpus** | Curated public medical sources | 1,045 documents from MedlinePlus, CDC, FDA, NIDDK | Frozen snapshot verified in `data/manifests/kb_snapshot_v5.json`. |
| **Dense Vector Index** | 384-d dense embeddings | ChromaDB collection **`carepilot_kb_v5`** | **10,074 chunks** embedded via `BAAI/bge-small-en-v1.5`. |
| **Sparse Lexical Index** | Token-aligned BM25 index | `rag_knowledge/bm25_index_v5.pkl` | BM25Okapi index with 100% ID synchronization with dense chunks. |
| **Duplicate Calibration** | Mean-centered cosine similarity | `backend/models/corpus_mean_bge_small.npy` | Calibrated over all distinct silver, gold, and new-query texts. |
| **External Data Bundle** | Out-of-Git handoff package | **`CarePilotAI_Transfer/`** | Google Drive handoff containing DB dump, vector zip, BM25 index, and `.env`. |

---

## 3. Subsystem Architecture and Implementation

### A1: Synthetic EHR Generation and Schema Architecture
- **Generator**: Synthea Java generator with fixed seed `42` for Massachusetts demographic baseline.
- **Relational Tables**: `patients`, `encounters`, `conditions`, `prescriptions`, `lab_results`, `allergies`, `procedures`, `care_plans`, `immunizations`.
- **Indexing**: High-performance B-tree indexes on `(patient_id, code, date)`, `(patient_id, status)`, and primary keys.
- **Patient Isolation Guardrail (Invariant I2)**: 100% of pipeline EHR queries are strictly filtered by parameterized `patient_id = :pid`.

### A2: Medical Knowledge Base Ingestion & Dual Indexing
- **Sources**: Public medical education materials stripped of boilerplate, navigation, and scripts.
- **Chunking Protocol**: Cleaned documents split into 400-token chunks with 60-token overlap; assigned stable deterministic IDs: `kb:{doc_id}:chunk{n:04d}`.
- **Dual Indexing**:
  1. *Dense Vector Store*: Upserted into ChromaDB persistent collection `carepilot_kb_v5`.
  2. *Sparse Inverted Index*: Indexed with `rank_bm25` (`BM25Okapi`) matching the exact corpus order.
- **Hybrid Retrieval Compatibility**: Allows convex-combination fusion scoring ($S_{\text{hybrid}} = \alpha \cdot S_{\text{dense}} + (1-\alpha) \cdot S_{\text{sparse}}$) during pipeline execution.

### A3: Terminology Normalization & Red-Flag Lexicon
- **Normalization**: Maps patient colloquial expressions to canonical clinical codes (SNOMED, LOINC, RxNorm) with a 30-character lookback negation engine.
- **Emergency Lexicon**: Frozen rule engine covering all 11 clinical emergency categories (chest pain, respiratory distress, stroke indicators, acute hemorrhage, etc.) triggering pre-generation overrides (**Invariant I3**).

### A4: External Artifact Packaging (`CarePilotAI_Transfer`)
To maintain repository hygiene and respect GitHub file limits:
- `01_DATABASE/carepilot_v3_backup.dump` (62.3 MB): Custom-format PostgreSQL 18 dump.
- `02_RAG_ARTIFACTS/chroma_db.zip` (227.4 MB): Compressed ChromaDB persistent directory.
- `02_RAG_ARTIFACTS/bm25_index_v5.pkl` (15.5 MB): Serialized BM25 index.
- `04_CONFIG_AND_ENV/.env` (81 B): Local database credentials template.
- Verified cryptographically via root **`CHECKSUMS_SHA256.txt`**.
