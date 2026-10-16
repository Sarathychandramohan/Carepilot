# Pillar D Plan — Research Paper, Project Report, Artifacts, and Release
**Document Version:** 1.0  
**Authoritative Reference:** `CarePilot_AI_Master_Spec_v3.md` (Sections 1.1, 3.3, 11, 12, S14, Appendices E, G, I)  
**System Role:** Subsystem Plan for Pillar D (Academic Paper, Project Final Report, Dataset Cards, Reproducibility Package, and Public Release)

---

## 1. Pillar Objectives and Scope

Pillar D translates the experimental findings, architectural artifacts, and measured empirical telemetry from Pillars A, B, and C into a complete, reproducible academic and software deliverable package (**Spec Section 12, S14, Appendix G**).

### Primary Objectives:
1. **Academic Paper Preparation (Section 12)**: Author a rigorous, conservatively positioned 4-to-8-page research paper targeting a clinical NLP workshop, health informatics conference, or arXiv preprint.
2. **Project Final Report & Review Materials (S14)**: Deliver an exhaustive project technical report, data cards, and final presentation slide deck grounded in verified screenshots and real hardware numbers.
3. **Open-Science Reproducibility Suite (Appendix E, G)**: Package reproducible pipelines via Docker Compose, Makefile commands, dataset manifests with SHA-256 checksums, and architectural decision logs.
4. **Safety, Ethics, and Compliance Packaging (Section 11)**: Explicitly document the non-clinical, synthetic-data research prototype boundaries, ensuring zero PHI exposure and no unsubstantiated clinical device claims.

---

## 2. Research Paper Specifications (Spec Section 12)

### 2.1 Working Title and Authorship
- **Title**: *"CarePilot: An Evaluated Human-in-the-Loop Clinical RAG Workflow with Patient-Scoped EHR Retrieval, Independent Urgency Triage, and Doctor-Edit Feedback"*
- **Target Venues**: ACL Clinical NLP Workshop, AMIA Informatics Summit, SIGHIT/Health Informatics, or arXiv preprint.

### 2.2 Academic Positioning and Conservative Claims
- **Research Scope**: An open-weight, synthetic-EHR, human-in-the-loop clinical RAG research prototype.
- **Explicit Non-Clinical Framing**: Strictly a research prototype built on synthetic Synthea records and curated public-domain medical literature. **Not a medical device**; the system never provides autonomous diagnoses or prescribing advice (**Spec Section 11, lines 676–678**).
- **Core Gap Addressed**: Resolves the integration-and-evaluation gap in clinical informatics, where dual-context grounding, independent triage safety, and human feedback are typically studied in isolation (**Spec line 693**).
- **Prior-Art Boundaries (RQ3 Warning)**: Explicitly cite Seegmiller et al. (*How Much Would a Clinician Edit This Draft?*, arXiv:2601.11344, ACL 2026). Do not claim that clinician-edit adaptation is novel; claim the controlled ablation and weighted edit-burden evaluation under dual retrieval (**Spec lines 694–696**).

### 2.3 Six Definitive Paper Contributions (Spec lines 698–703)
1. **Reproducible Open-Weight Pipeline**: An end-to-end clinical RAG workflow utilizing synthetic EHR data and a license-audited, frozen public-domain medical knowledge base.
2. **Dual-Context Retrieval Ablation**: An empirical ablation isolating the factual impact of patient-scoped EHR retrieval vs knowledge-only retrieval, including a pilot unified-context baseline.
3. **Independent Safety Triage Comparison**: A rigorous safety comparison demonstrating that an independent calibrated classifier with red-flag overrides substantially reduces HIGH-acuity false negatives compared to LLM self-triage.
4. **Structured Clinician-Review Protocol**: A HITL review workflow logging granular approval, rejection, sentence-level citations, and a 12-category weighted edit-burden metric.
5. **Exploratory Clinician-Edit Memory Analysis**: An empirical analysis evaluating whether typed doctor-edit feedback reduces future clinician editing effort across sequential consultations.
6. **Reproducible Benchmark and Scale Study**: A complete evaluation harness evaluating retrieval accuracy, faithfulness, and latency across KB scale and patient record sizes.

### 2.4 Verified Prior-Art Leads to Cite (Spec Appendix I, lines 894–902)
- **Garcia et al. (Stanford Pilot)**: *AI-generated draft replies to patient inbox messages*, JAMA Netw Open 2024;7(3):e243201. Baseline human-review workflow.
- **UC San Diego Health Study**: *Randomized waiting-list study of AI-drafted replies*, JAMA Netw Open 2024;7(4):e246565. Clinician time and reply length effects.
- **NYU Langone Study**: *16 primary care physicians rated GPT-4 drafts with patient-specific data against clinician-written replies*, JAMA Netw Open 2024;7(7):e2422399. Patient-specific EHR drafting.
- **Seegmiller et al.**: *How Much Would a Clinician Edit This Draft?*, arXiv:2601.11344, ACL 2026. Edit-load evaluation and clinician preference adaptation.
- **Cao, Chen, Guo (EHR-RAG)**: *Long-horizon structured EHR retrieval*, arXiv:2601.21340. Scale grounding for structured EHR retrieval.

---

## 3. Academic Tables and Figures Suite (Spec Section 8, line 618)

All tables and figures must be generated deterministically via automated scripts from the `eval_runs` database table:

### Tables Suite:
| Table ID | Title / Content | Primary Source / Metrics |
| :--- | :--- | :--- |
| **Table 1 (T1)** | Dataset Statistics & Inter-Rater Reliability | Record counts, Silver splits, Gold stratification, Cohen's $\kappa$ and weighted $\kappa$. |
| **Table 2 (T2)** | Knowledge Retrieval Performance | Dense vs BM25 vs Hybrid fusion on dev and test (Hit@3, Hit@5, MRR, latency ms). |
| **Table 3 (T3)** | Intent & Urgency Classifier Performance | Test macro-F1, precision, recall, and support across all 5 intents and 3 urgency classes. |
| **Table 4 (T4)** | Safety Triage & Red-Flag False Negative Analysis | HIGH-acuity FNR with Wilson 95% CIs across LLM-only, classifier-only, and classifier + red-flag. |
| **Table 5 (T5)** | Master Ablation Matrix | Primary comparison (`full` vs `no_ehr` vs `no_classifier` vs `unified_context`) across EHR accuracy, NLI faithfulness, citation coverage, and latency. |
| **Table 6 (T6)** | Human Clinician Evaluation Results | Rater Likert scores (relevance, usefulness), safety approval rates, human citation accuracy, and preference. |
| **Table 7 (T7)** | Doctor-Edit Burden & Interaction Trend | Levenshtein distances and weighted edit burden across interaction ordinal $1 \dots N$ (memory ON vs OFF). |
| **Table 8 (T8)** | Empirical Scale Analysis | SA1 (KB size vs Hit@5/latency) and SA2 (patient record size vs EHR candidate recall). |

### Figures Suite:
- **Figure 1 (F1)**: Architectural Flowchart illustrating the 8-stage pipeline (P1–P8), dual-context retrieval branches, and 3-pane doctor workspace.
- **Figure 2 (F2)**: Confusion Matrices for Intent classification and Urgency classification under tuned $\tau_{\text{high}}$ thresholding.
- **Figure 3 (F3)**: Edit Distance and Weighted Edit Burden Trend across sequential interaction numbers with bootstrap confidence intervals.
- **Figure 4 (F4)**: Retrieval Latency and Hit@k vs Knowledge Base Chunk Scale (SA1 sweep).

---

## 4. Documentation and Project Deliverables (S14, Appendix G)

### 4.1 Technical Project Report & Slide Deck
- **Exhaustive Project Report (PDF/Markdown)**: Documenting motivation, architectural design, data collection pipelines, empirical benchmark results, and clinical human evaluation.
- **Final Presentation Slides**: High-density deck featuring system UI screenshots, live trace diagrams, confusion matrices, and ablation graphs.

### 4.2 Dataset Cards & Governance Declarations (S14-T7)
Four standardized Dataset Cards authored under clinical ML best practices:
1. **EHR Corpus Card**: Synthetic Synthea generation parameters (seed 42, Massachusetts baseline, 2,330 patients), demographic breakdown, record length percentiles, and 0-PHI declaration.
2. **Knowledge Base Snapshot Card (`v5.1`)**: Provenance manifest, URL catalog, public-domain licensing audit (openFDA, MedlinePlus, NIDDK, WHO), chunking parameters (400 tokens / 60 overlap), and SHA-256 checksums.
3. **Gold Evaluation Dataset Card**: Double-annotation protocol, annotator qualifications, Cohen's $\kappa$ agreement metrics, adversarial case taxonomy, and pooling provenance.
4. **Silver Training Dataset Card**: Scenario-family generation methodology, template taxonomy, family-level holdout guarantees, and audit results.

### 4.3 Reproducibility Suite and Software Artifacts
- **Docker Compose Stack (`docker-compose.yml`)**: Multi-container configuration orchestrating `api` (FastAPI), `postgres` (carepilot_v3), `chroma` (carepilot_kb_v5), and `ollama` (qwen3:8b).
- **Automated Workflow (`Makefile`)**:
  - `make data`: Loads Synthea data and builds indexes.
  - `make kb`: Fetches, cleans, chunks, and dual-indexes knowledge corpus.
  - `make train`: Trains and calibrates intent and urgency classifiers.
  - `make eval`: Executes evaluation harness across registered ablations.
  - `make report`: Compiles LaTeX tables, metrics JSON, and figures.
  - `make test`: Executes full pytest test suite (including 40-patient CI fixture).
- **Architectural Decision Logs**: Complete maintenance of `docs/DECISIONS.md` and `docs/PILLAR_B_DECISIONS.md`.
- **System Runbook (`docs/runbook.md`)**: Operational guide covering hardware prerequisites, Ollama model pulling, environment variables, database migrations, and health check endpoints.

---

## 5. Safety, Ethics, and Compliance Framework (Spec Section 11)

Every deliverable produced under Pillar D must strictly adhere to the following governance invariants:
1. **Synthetic Data Integrity**: Reiterate in all publications that all EHR data is 100% synthetic (Synthea). Real clinical data (such as MIMIC) is explicitly excluded due to data-use agreements and credentialing boundaries (**Spec line 682**).
2. **Medical Disclaimers**: UI and paper text must prominently state that CarePilot AI is a research prototype, not a certified clinical decision support system or medical device.
3. **Honest Negative Reporting**: Mandate transparent reporting of classifier false negatives, hallucinated citations, low inter-annotator agreement areas, and null results (**Spec line 685**).
4. **Licensing Transparency**: No redistribution of copyrighted medical textbooks or paywalled literature; only public-domain US government sources and licensed core documents are released (**Spec line 683**).
