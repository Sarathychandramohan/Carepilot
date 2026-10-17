# Pillar D Plan — UI/API Integration, Academic Paper, and Collaborator Handover

**Document Version:** 3.0 (Aligned with Master Plan v5 & Post-Phase-5 State)  
**Authoritative Reference:** `docs/MASTER_PROJECT_PLAN_v5.md` (Sections 1, 3, 8, 9, 10)  
**System Role:** Subsystem Specification and Handover Plan for Pillar D (Clinician Review Dashboard, Patient Mobile Portal, REST API Integration, Academic Paper Framing, and Collaborator Workflow)  
**Current Git State:** In progress on active branches `main` and `friend` (commit `fee80e4` / `0f7f40a`)

---

## 1. Pillar Objectives and Scope

Pillar D delivers the user-facing clinical workspace, the patient communication application, the REST API integration layer, and the academic reporting package, executing strictly **after** the frozen evaluation of Pillars A, B, and C (**Master Plan Section 8**).

### Primary Objectives:
1. **Clinician Review Workspace (`doctor-dashboard`)**: Provide a high-density, 3-column clinical desktop interface where doctors review AI drafts with inline citations, live EHR/KB evidence panels, and 12-category edit tracking.
2. **Patient Consultation Portal (`patient-app`)**: Deliver an accessible patient mobile/web interface that strictly enforces **Safety Invariant I1** (only approved responses reach the patient) and displays prominent emergency advisories.
3. **REST API Contracts & End-to-End Integration**: Connect FastAPI backend routes (`/api/consult`, `/api/queue`, `/api/patient`) with TypeScript API clients without altering the frozen research pipeline.
4. **Academic Research Reporting**: Author the final research paper anchored to Small et al. (2024), reporting quantitative findings, component ablations, and honest claim boundaries.
5. **Team Collaboration & Branch Workflow**: Enable seamless multi-developer workflow across dedicated branches (`main` and `friend`).

---

## 2. Phase D Gating and Non-Interference Rule

> [!IMPORTANT]
> **Non-Interference Gate**: Phase D interface and integration development occurs strictly on top of the frozen evaluation baseline (tag `freeze-eval` at commit `c9a1239`). Frontend features must consume existing API contracts and must **never** modify pipeline prompts, classification thresholds, or evaluation scripts.

---

## 3. User-Facing Systems & Work Packages

### 3.1 Doctor Review Dashboard (`doctor-dashboard` — React 18 + Vite)
- **Port**: `http://localhost:5173`
- **Features & Components**:
  - *Priority Queue (`QueuePage.tsx`)*: Consultations ordered by `urgency_final` descending (`urgent`, `soon`, `routine`), with live 5-second polling and prominent emergency red-flag badges.
  - *3-Column Review Workspace (`ConsultationReviewPage.tsx`)*:
    - Left Column: Longitudinal patient clinical history (conditions, medications, LOINC labs with reference ranges and abnormal flags).
    - Center Column: Patient–clinic consultation thread.
    - Right Column: AI draft rendered with interactive citation chips (`EHR`, `Knowledge`), NLI faithfulness badges, and readability grade.
  - *Clinician Action Console*:
    - Approve Unchanged: Delivers draft directly to patient.
    - Edit & Approve: Logs character/word Levenshtein distance and 12 structured edit categories (`factual_correction`, `missing_ehr_fact`, `tone_change`, etc.).
    - Reject: Requires structured rejection reason (`unsafe_response`, `factual_correction`, etc.).
    - Request Clarification: Sends focused follow-up inquiry to patient.

### 3.2 Patient Application (`patient-app` — React Native / Expo SDK 57)
- **Port**: `http://localhost:8081` (Web) / Expo Go (Mobile)
- **Features & Components**:
  - *Safety Invariant I1 Enforcement*: Consultations in `awaiting_doctor` state display a calm status indicator ("With your clinical care team"). The response text is rendered **only** after status transitions to `delivered`.
  - *Emergency Intercept*: In the event of an emergency red-flag match, an immediate static emergency instruction banner is rendered (directing patient to emergency services).
  - *Synthetic Data Disclaimer*: Every screen prominently displays the research prototype disclaimer: *"Demonstration using synthetic EHR records only. Not for real clinical emergencies or diagnosis."*

### 3.3 Backend API Integration & Services
- **FastAPI REST Endpoints**:
  - `POST /api/consult/submit`: Ingests patient inquiry, triggers asynchronous pipeline.
  - `GET /api/consult/{id}`: Polls consultation delivery status and approved response.
  - `GET /api/queue/pending`: Retrieves clinician review queue sorted by urgency.
  - `POST /api/queue/{id}/review`: Submits clinician approval, edit diff, and edit categories.
  - `GET /api/patient/{id}/summary`: Returns patient clinical profile and longitudinal labs.
- **Frontend API Clients**:
  - `doctor-dashboard/src/services/api/`: `apiClient.ts`, `consultationApi.ts`, `patientApi.ts`, `appointmentApi.ts`.
  - `patient-app/services/api/`: `apiClient.ts`, `consultationApi.ts`, `notificationApi.ts`, `trendApi.ts`.

---

## 4. Academic Paper Specifications

### 4.1 Working Title and Positioning
- **Title**: *"CarePilot: An Evaluated Human-in-the-Loop Clinical RAG Workflow with Patient-Scoped EHR Retrieval, Independent Urgency Triage, and Readability Control"*
- **Target Venues**: ACL Clinical NLP Workshop, AMIA Informatics Summit, SIGHIT Health Informatics, or arXiv preprint.
- **Primary Literature Anchor**: **Small et al. (2024)**, *JAMA Network Open*, 7(7):e2422399.
  - *The Gap Addressed*: Small et al. identified that generative AI patient draft replies are frequently too verbose, linguistically complex, and difficult for low-health-literacy patients. CarePilot AI demonstrates that combining an automated readability controller (grade $\le 8$) with patient-scoped EHR grounding and dual-index retrieval addresses this complexity gap while maintaining factual faithfulness.

### 4.2 Prohibited Claims (Scientific Integrity)
- Never claim real-world clinical safety or patient health benefits.
- Never claim reduced clinician burnout or physician time savings (as no real clinical trial was conducted).
- Never claim superiority over commercial EHR tools.
- Never claim doctor-edit adaptation or learning from edits (instrumented only).

---

## 5. Collaborator Onboarding & Git Workflow

Collaborators onboarding to CarePilot AI work directly in Pillar D:

1. **Quickstart Reference**: Follow **[`docs/FRIEND_SETUP_GUIDE.md`](file:///D:/CarePilotAI/docs/FRIEND_SETUP_GUIDE.md)** for cloning, database restoration, and service startup.
2. **Branch Rules**:
   - Sarathy develops on **`main`**.
   - Collaborator develops on **`friend`**.
   - Push to `origin/friend` and open Pull Requests into **`main`**.
3. **Smoke Verification Before Pushing**:
   ```powershell
   python -m pytest backend/tests/test_redflag_11_categories.py
   python -m pytest backend/tests/test_ehr_fact_accuracy.py
   python -m pytest backend/tests/test_skip_reasons.py
   python -m pytest backend/tests/test_eval_provenance.py
   ```
