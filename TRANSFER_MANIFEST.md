# CarePilot AI — Repository Transfer Manifest & Artifact Inventory

This manifest records all components, database snapshots, vector stores, models, and scripts required to transfer CarePilot AI from the primary development laptop to a secondary development laptop without losing research state or experimental reproducibility.

---

## 1. Transfer Summary & Architecture Matrix

| Subsystem | Primary Artifact | Storage Location | Transfer Method | Size (Bytes) | SHA-256 Checksum | Integrity / Verification Check |
|---|---|---|---|---|---|---|
| **Source Code** | Full git repository (`feature/pillar-c-eval`) | GitHub (`Sarathychandramohan/Carepilot`) | `git clone` | ~50 MB | Commit Hash | `git rev-parse HEAD` |
| **Relational DB** | PostgreSQL database `carepilot_v3` | `01_DATABASE/carepilot_v3_backup.dump` | Custom format dump | 62,318,070 | `0afb298b53c90e70b26c05eff1e23758b6f41365d1940e2b91aef0e4baa0bb63` | 2,330 patients, ~2.5M rows across tables |
| **Vector Store** | ChromaDB collection `carepilot_kb_v5` | `02_RAG_ARTIFACTS/chroma_db.zip` | Zip archive | 227,351,321 | `65e6f1dd32c157e3e8cfc9a416a3835a942582127ae1a54974d9477e6bec6b05` | 10,074 chunks from 1,045 documents |
| **Sparse Index** | BM25 index `bm25_index_v5.pkl` | `02_RAG_ARTIFACTS/bm25_index_v5.pkl` | Serialized pickle | 15,548,899 | `1e6c4569754f565e6128a0969d0f19a2b87c5156fe28f457299d08c21053e333` | Matches `carepilot_kb_v5` corpus order |
| **Classifiers** | Intent & Urgency models | `backend/models/*.pkl` | Git + Backup | ~45 KB | Git Tracked | BGE-small calibrated Logistic Regression |
| **Local LLM** | Ollama Qwen3-8B | Local Ollama library | `ollama pull qwen3:8b` OR USB copy | ~4.87 GB | Registry / Blobs | Ollama tag `qwen3:8b` (Q4_K_M) |
| **Environment** | Configuration secrets | `04_CONFIG_AND_ENV/.env` | Secure manual copy | 81 | `8f3e61ed6e7e897d66d00a97634f0827932feb6ed2c8ab7a7046693fbe58bb22` | Based on safe `backend/.env.example` |
| **Working Patch**| Post-C-Audit Git Patch | `05_RESEARCH_DATA/working_changes_post_c_audit.patch` | Unified Git diff | 644,644 | `417726b54339a03290d97081e8b5a749bfd1b75934745111c45e5e36ad0cf0a7` | Applies cleanly with `git apply` |

---

## 2. Tracked Files (Stored in Git)

The following core modules and artifacts belong strictly inside Git:

### A. Application Source Code
- **FastAPI Backend**: `backend/app/`
  - `main.py`: Application entry point and router aggregation.
  - `api/`: API endpoints (`consult.py`, `queue.py`, `patient.py`).
  - `core/`: Settings (`settings.py`), local LLM loader (`llm.py`).
  - `db/`: ORM models (`models_v3.py`), database session (`session.py`).
  - `pipeline/`:
    - `orchestrator.py`: Full P1→P8 two-stage clinical pipeline.
    - `redflag.py`: Frozen 11-category clinical emergency rule engine.
    - `classify.py`: Runtime Intent and Urgency classifier module.
    - `retrieve_ehr.py`: Patient-scoped SQL retrieval with outlier tagging.
    - `retrieve_kb.py`: Convex combination hybrid retrieval (ChromaDB + BM25).
    - `generate.py`: Local LLM prompt assembly and JSON draft parsing.
    - `validate.py`: Citation coverage, validity, and sentence-level NLI entailment.
    - `detect_context_gaps.py`: D17 conflict (D17a) and missing-context (D17b) detectors.
- **Doctor Dashboard**: `doctor-dashboard/`
  - `src/`: React 18 + Vite clinical workspace, queue, and review components.
  - `package.json`, `package-lock.json`, `tailwind.config.ts`, `vite.config.ts`.
- **Patient Application**: `patient-app/`
  - `app/`: Expo SDK 57 / React Native pages, tabs, and consultation view.
  - `package.json`, `package-lock.json`, `tailwind.config.js`.

### B. Database Migrations & Schemas
- `backend/db_migrations/002_eval_runs_expand_and_eval_run_id.py`: Expands `eval_runs` provenance table.
- `backend/db_migrations/003_add_skip_reason_to_consultations.py`: Adds `skip_reason` column to `consultations`.
- `synthea/carepilot_data/DATABASE_SCHEMA.md` & `ETL_MAPPING.md`: Reference documentation for EHR schemas.
- `synthea/carepilot_data/etl.py`: Core ETL ingestion logic.

### C. Evaluation & Research Harness (Pillar C)
- `backend/eval/`:
  - `run.py`: Automated CLI runner with pre-flight invariant gates.
  - `config.py`: Frozen pre-registered ablation configs (`full`, `no_ehr`, `no_classifier`).
  - `query_sets.py`: Split loaders for Gold, Silver, and RQ3 stream queries.
  - `stats.py`: Wilson score confidence intervals, McNemar, Wilcoxon, and cluster bootstrap.
  - `export_patient_picker.py`: Generates patient clinical summaries for query authoring.
  - `diversity_report.py`: Dataset diversity and age/gender/condition coverage metrics.
  - `metrics/`: Individual statistical metric modules (faithfulness, retrieval, classification, safety, edit burden).
- `data/queries/`:
  - `gold_scripted_candidate.jsonl`: Pre-registered gold evaluation queries.
  - `silver.jsonl`: 3,770 synthetic evaluation queries across 29 clinical families.
  - `rq3_stream.jsonl`: 60 clinical queries for sequential doctor review study.
- `data/annotation/`:
  - `patient_picker_sheet.csv`: Patient clinical fact summaries across all alive patients.
  - `patient_picker_shortlist.csv`: 60 shortlisted representative patients for study queries.
  - `annotator_A.csv`, `annotator_B.csv`: Double-rater human evaluation templates.
- `data/manifests/`:
  - `kb_snapshot_v5.json`: Cryptographic manifest of all 1,045 documents in KB v5.
  - `ehr_source_manifest.json`: Provenance record of demo and scale_2k cohort merge.
  - `complex_patients.json`: Detailed clinical profiles for 60 shortlisted evaluation patients.
  - `classifier_metrics.json`: Pre-flight classification performance metrics.

### D. Verified Test Suites
- `backend/tests/`:
  - `test_redflag_11_categories.py`: 88-test matrix covering all 11 emergency categories.
  - `test_ehr_fact_accuracy.py`: 43-test suite verifying rule-based fact grounding.
  - `test_skip_reasons.py`: 7-test suite for skip_reason persistence and pipeline gates.
  - `test_eval_harness.py`: 16-test suite verifying statistical layer and metric calculators.
  - `test_pillar_b_core.py`: Integration test suite for classification, retrieval, review, and IDOR.
- `pytest.ini`: Project-level test discovery and recursion configuration.
- `backend/requirements.txt`: Pinned Python dependencies.

---

## 3. Excluded Artifacts & Transfer Instructions

The following artifacts are excluded from Git to prevent repository bloat, secret leakage, or corrupted Git object databases. They must be transferred using the **CarePilot Transfer Bundle**:

### A. PostgreSQL Database (`carepilot_v3`)
- **Reason for Exclusion**: Database contains ~2.5 million clinical rows (~500 MB raw uncompressed table storage).
- **Primary Source Machine Export**:
  ```powershell
  pg_dump -U postgres -h localhost -p 5432 -F c -b -v -f "D:\CarePilotAI_Backup\carepilot_v3_backup.dump" carepilot_v3
  ```
- **Secondary Machine Restore**:
  ```powershell
  createdb -U postgres -h localhost -p 5432 carepilot_v3
  pg_restore -U postgres -h localhost -p 5432 -d carepilot_v3 -v "carepilot_v3_backup.dump"
  ```
- **Integrity Check**:
  ```sql
  SELECT count(*) FROM patients;       -- Must equal 2330 (2030 alive, 300 deceased)
  SELECT count(*) FROM lab_results;    -- Must equal ~1731561
  SELECT count(*) FROM prescriptions;  -- Must equal ~115655
  ```

### B. ChromaDB Collection (`carepilot_kb_v5`)
- **Reason for Exclusion**: Binary SQLite and HNSW vector index files (376 MB).
- **Source Path**: `D:\CarePilotAI\rag_knowledge\chroma_db\`
- **Transfer Procedure**:
  - Compress on primary machine: `Compress-Archive -Path "rag_knowledge\chroma_db" -DestinationPath "D:\CarePilotAI_Backup\chroma_db.zip"`
  - Unpack on secondary machine into: `D:\CarePilotAI\rag_knowledge\chroma_db\`
- **Integrity Check**:
  - Run `python -m backend.scripts.inspect_pillar_a kb`.
  - Must report: 1,045 documents, 10,074 chunks in collection `carepilot_kb_v5`.

### C. BM25 Index (`bm25_index_v5.pkl`)
- **Reason for Exclusion**: Serialized Python pickle index (14.8 MB).
- **Source Path**: `D:\CarePilotAI\rag_knowledge\bm25_index_v5.pkl`
- **Transfer Procedure**: Copy directly to `rag_knowledge\bm25_index_v5.pkl` on the secondary machine.
- **Alternative (Regeneration)**:
  If file is unavailable, regenerate from ChromaDB chunks:
  ```powershell
  python -m backend.scripts.rebuild_bm25_from_chroma
  ```

### D. Local Configuration Secrets (`backend/.env`)
- **Reason for Exclusion**: Security-first. Real database passwords and configuration paths must never be pushed to GitHub.
- **Transfer Procedure**: Securely copy via USB drive or create from `backend/.env.example` on the second laptop.

### E. External Synthea Source Checkout (`synthea/.git`)
- **Reason for Exclusion**: Synthea is an external Git repository from MITRE. Tracking it directly inside CarePilot AI would create an accidental submodule or commit the 100MB+ external Git database.
- **Reconstruction Provenance**:
  - Repository: `https://github.com/synthetichealth/synthea.git`
  - Cloned Commit: `d9d07a6ee`
  - Generation Command:
    ```bash
    ./gradlew run --args="-p 2000 -s 42 Massachusetts"
    ```
- **Note**: Synthea regeneration is **NOT required** if the PostgreSQL database dump is restored.

---

## 4. Item-by-Item File Classification & Disposition

| Item / Directory | Classification | Action | Rationale |
|---|---|---|---|
| `backend/app/` | 1. Required Source | Tracked in Git | Core application pipeline and API |
| `backend/eval/` | 1. Required Source | Tracked in Git | Pillar C evaluation harness |
| `backend/tests/` | 1. Required Source | Tracked in Git | Regression test suites |
| `doctor-dashboard/` | 1. Required Source | Tracked in Git | React clinician review dashboard |
| `patient-app/` | 1. Required Source | Tracked in Git | Expo React Native patient portal |
| `data/queries/` | 1. Required Research Data | Tracked in Git | Pre-registered Gold, Silver, RQ3 query sets |
| `data/manifests/` | 1. Required Research Data | Tracked in Git | Research provenance manifests and configs |
| `data/annotation/patient_picker_*.csv` | 1. Required Research Data | Tracked in Git | Patient fact summaries and shortlist |
| `rag_knowledge/*.py` | 1. Required Source | Tracked in Git | RAG chunking, crawling, and ingestion scripts |
| `synthea/carepilot_data/` | 1. Required Source | Tracked in Git / Backed up | CarePilot custom ETL scripts and schema docs |
| `backend/models/*.pkl` | 2. Runtime Artifact | Tracked in Git / Backed up | Small calibrated classifier models (44 KB total) |
| `carepilot_v3` (DB) | 2. Runtime Artifact | Transfer via `carepilot_v3_backup.dump` | 2.5M rows; cannot fit in Git |
| `rag_knowledge/chroma_db/` | 2. Runtime Artifact | Transfer via `chroma_db.zip` | 376 MB binary vector store |
| `rag_knowledge/bm25_index_v5.pkl` | 2. Runtime Artifact | Transfer via file copy or rebuild | 14.8 MB sparse retrieval index |
| `synthea/carepilot_output_2k/` | 3. Safely Regenerable | Excluded from Git; kept in backup | 1.8 GB raw Synthea CSV/FHIR outputs |
| `rag_knowledge/raw/` | 3. Safely Regenerable | Excluded from Git; kept in backup | 84.5 MB raw scraped HTML files |
| `synthea/.git/` | 4. External Metadata | Excluded from Git | External MITRE Synthea Git repository |
| `*.sdk57-backup` | 4. Local Backup | Excluded from Git (local only) | Historical Expo SDK migration backup |
| `backend/.env` | 5. Confidential Secret | Excluded from Git (copy securely) | Contains real database password |

---

## 5. Pre-Flight Verification Gate

Before running any primary benchmark on the secondary laptop, execute this pre-flight verification:

1. **Database Gate**:
   `SELECT count(*) FROM patients WHERE is_alive = true;` $\ge 2000$.
2. **KB Gate**:
   ChromaDB collection `carepilot_kb_v5` has exactly 10,074 chunks.
3. **Classifiers Gate**:
   `backend/models/intent_classifier.pkl` and `urgency_classifier.pkl` load without error.
4. **Safety Gate**:
   88/88 tests pass in `backend/tests/test_redflag_11_categories.py`.
5. **Harness Gate**:
   `python -m backend.eval.run --config full --split gold-dev --seed 42 --subset 2 --dry-run` completes with `Wiring dry-run completed successfully.`
