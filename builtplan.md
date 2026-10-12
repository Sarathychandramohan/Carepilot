# CarePilot AI — Complete Frontend Architecture & Comprehensive Backend Integration Blueprint (`builtplan.md`)

This document serves as the authoritative, up-to-date **Frontend Architecture, Product Specification, and Backend Integration Blueprint** for CarePilot AI (`D:\CarePilotAI\`). It captures the latest codebase enhancements, Expo SDK 57 migration fixes, NativeWind v4 class-based dark mode configurations, bottom navigation bar optimizations, and provides an in-depth, page-by-page technical analysis explaining how backend integration transforms each page into an enterprise-grade clinical platform.

---

## 1. Executive Architecture Summary

CarePilot AI is an enterprise-grade prototype demonstrating a **Human-in-the-Loop Retrieval-Augmented Generation (RAG) Pipeline for Patient–Doctor Communication**. The frontend architecture consists of two specialized applications:

```
D:\CarePilotAI\
│
├── patient-app\          ← React Native + Expo SDK 57 Mobile & Web App (Calm, friendly, patient-centric)
├── doctor-dashboard\     ← React 18 + Vite Web Dashboard (Clinical, information-dense, 3-column desktop)
└── synthea\              ← Synthetic FHIR/EHR Data Layer (Synthea output & ETL scripts)
```

### Core Architectural Principles:
1. **Clinical Safety Guardrail**: The patient application **NEVER** displays raw AI drafts. Only doctor-approved responses (`status = 'approved'`) are presented to the patient.
2. **Class-Based Dark Mode System**: Configured with NativeWind v4 (`darkMode: "class"` in `tailwind.config.js`) for seamless, cross-platform theme switching on Web, iOS, and Android.
3. **Clean 5-Tab Navigation Bar**: Strict route scoping (`href: null` on all sub-routes in `app/(tabs)/_layout.tsx`) ensuring the mobile bottom bar renders exactly 5 core navigation tabs (`Home`, `Consult`, `Records`, `Visits`, `Profile`).
4. **Cross-Platform Realtime Synchronization**: Integrated `BroadcastChannel` + platform-safe `window.storage` event triggers so when a doctor approves a draft on `http://localhost:5173`, the patient app on `http://localhost:8081` updates in real time to **"Doctor Approved"** without manual page reloads.
5. **Academic Model Evaluation Engine**: Analytics page includes full evaluation metrics ($N=221$, 91.4% Accuracy, 0.89 Macro F1) and a 3x3 Urgency Confusion Matrix.

---

## 2. Technology Stack & Environment

| Layer | Patient App (`patient-app`) | Doctor Dashboard (`doctor-dashboard`) |
|---|---|---|
| **Framework** | Expo SDK 57.0.23 / React Native 0.86.3 | React 18.3.1 + Vite 6.0.0 |
| **Language** | TypeScript 6.0.3 | TypeScript 5.6.3 |
| **Routing** | Expo Router 57.0.21 (File-based) | React Router DOM 7.1.0 |
| **Styling** | NativeWind 4.2.7 + Tailwind CSS 3.4.0 | Tailwind CSS 3.4.17 + Lucide Icons |
| **State Management** | Zustand 5.0.0 (with AsyncStorage persist) | Zustand 5.0.0 |
| **Data Visualization** | Custom React Native SVGs | Recharts 2.15.0 |

---

## 3. Design System & Color Tokens

Both applications enforce strict healthcare-compliant color tokens across light and dark themes:

| Token Name | Hex Code | Role & Usage |
|---|---|---|
| **Primary** | `#1A56DB` | Deep Medical Blue — Primary actions, branding, active states |
| **Secondary** | `#0694A2` | Teal / Cyan — Secondary highlights, category badges |
| **Background** | `#F0F4F8` | Light Blue-Gray Canvas — Application background |
| **Card** | `#FFFFFF` | Pure White — Containers, panels, elevated cards |
| **Text Primary** | `#1A2B4A` | Dark Navy — Primary typography & headings |
| **Text Secondary** | `#6B7280` | Muted Gray — Subtitles, dates, secondary labels |
| **Border** | `#CBD5E1` | Soft Gray-Blue — Borders & dividers |

### Urgency Badge System (Color + Label + Icon)
To adhere to accessibility guidelines, urgency is never communicated by color alone:

| Level | Color Token | Hex | Visual Indicator | Label |
|---|---|---|---|---|
| **Routine** | `SUCCESS` | `#10B981` | Green Badge + Check Icon | `ROUTINE` |
| **Soon** | `WARNING` | `#F59E0B` | Amber Badge + Clock Icon | `SOON` |
| **Urgent** | `URGENT` | `#EF4444` | Red Badge + Alert Octagon Icon | `URGENT` |

---

## 4. Hero Patient Synthetic Data Profile

The application utilizes a rich synthetic patient profile derived from Synthea EHR data:

```
Name:        Christian Labadie
Age:         81 (Born 1945-05-12)
Gender:      Male
Patient ID:  hero-001

Conditions:
  - Chronic Kidney Disease (CKD) Stage 3
  - Hypertension
  - Type 2 Diabetes

Active Medications:
  - Lisinopril 10mg daily
  - Metformin 500mg twice daily
  - Furosemide 40mg daily

Longitudinal Lab Trend (Serum Creatinine):
  - 2022-03-15: 1.1 mg/dL
  - 2022-09-20: 1.2 mg/dL
  - 2023-02-14: 1.3 mg/dL
  - 2023-08-10: 1.4 mg/dL  (Rising trend)

Longitudinal Lab Trend (eGFR):
  - 2022-03-15: 58 mL/min
  - 2022-09-20: 55 mL/min
  - 2023-02-14: 51 mL/min
  - 2023-08-10: 47 mL/min  (Declining trend)

Hero Consultation Request (consult-001):
  Query:   "Why is my recent blood test different from before?"
  Status:  doctor_review
  Intent:  report_query
  Urgency: soon
```

---

## 5. Patient Mobile Application — Page Breakdown & Backend Value Add

### 1. Auth Login (`app/(auth)/login.tsx`)
- **Frontend Current State**: Form rendered with pre-filled demo credentials (`patient@carepilot.ai` / `demo1234`). Authenticates state into Zustand `useAuthStore` and persists to local storage.
- **Backend Integration Value Add**:
  - **HIPAA-Compliant Auth Service**: Integration with OAuth2 / OIDC providers (e.g. Auth0, Firebase Auth, or AWS Cognito) with Multi-Factor Authentication (MFA).
  - **Secure Key Storage**: Encrypts session tokens using `expo-secure-store` (Keychain on iOS, Keystore on Android).
  - **Biometric Authentication**: Enables TouchID / FaceID for rapid, secure patient re-authentication.

### 2. Home Dashboard (`app/(tabs)/index.tsx`)
- **Frontend Current State**: Personalized greeting ("Hello, Christian"), active consultation card showing status, quick action button ("New Consultation"), and unread notification counter badge.
- **Backend Integration Value Add**:
  - **Real-Time WebSockets / Server-Sent Events (SSE)**: Streams live consultation status transitions (e.g. `processing` $\rightarrow$ `doctor_review` $\rightarrow$ `approved`) instantly without polling.
  - **Proactive AI Nudges**: Connects to a backend Clinical Event Engine that scans incoming EHR updates (e.g., new lab result posted) and renders personalized health reminders.
  - **Dynamic Patient Summary**: Fetches live FHIR `Patient` and `Condition` resources via Google Cloud Healthcare API.

### 3. Chat Query Composer (`app/(tabs)/chat/index.tsx`)
- **Frontend Current State**: Multiline text input for symptom entry, submit button, and automatic navigation to consultation detail upon submission.
- **Backend Integration Value Add**:
  - **Asynchronous Ingestion Pipeline**: Posts queries to a message queue (Apache Kafka or GCP Pub/Sub).
  - **Multi-Modal Input Processing**: Accepts voice recordings (transcribed via Whisper AI) and medical photo attachments (uploaded to encrypted Cloud Storage buckets).
  - **Automated AI Triage Engine**: Invokes a Bio_ClinicalBERT classifier microservice that calculates intent, detects emergency keywords, and assigns an initial urgency score (`ROUTINE`, `SOON`, `URGENT`).

### 4. Consultation Detail & State Machine (`app/(tabs)/chat/[id].tsx`)
- **Frontend Current State**: Renders specific visual states for all 5 consultation lifecycle steps:
  - `sending`: Loading indicator.
  - `processing`: Blue status banner ("Analyzing Your Request... Retrieving lab history").
  - `doctor_review`: Amber card ("Waiting for Doctor Review · Dr. Amelia Smith").
  - `approved`: Green shield banner ("Doctor Approved Clinical Response") displaying Dr. Amelia Smith's verified response and timestamp.
  - `rejected`: Red banner ("Review Update Requested").
- **Backend Integration Value Add**:
  - **Workflow Orchestration (Temporal.io / AWS Step Functions)**: Guarantees state transitions and manages retry policies across microservices.
  - **Audit Logging & Compliance**: Logs every view and state change into an immutable, HIPAA-compliant audit ledger (e.g. AWS CloudTrail / GCP Audit Logs) for medical liability protection.
  - **Clinical Guardrail Enforcement**: Backend APIs enforce database-level access rules ensuring unapproved AI drafts are impossible to retrieve via patient endpoints.

### 5. Patient Notifications (`app/notifications.tsx`)
- **Frontend Current State**: List of consultation update alerts and appointment reminders with unread badges and click-to-navigate handlers.
- **Backend Integration Value Add**:
  - **Push Notification Service**: Integrates Expo Push Notification API with FCM (Firebase Cloud Messaging) and APNs (Apple Push Notification service) to deliver background push alerts to mobile devices when a doctor signs off on a response.
  - **Read State Sync**: Syncs read receipts across devices using a backend PostgreSQL / Redis store.

### 6. Medical Records Hub (`app/(tabs)/records/index.tsx`)
- **Frontend Current State**: Central hub displaying navigation cards for Lab Results, Active Medications, Clinical Notes, and Medical Documents.
- **Backend Integration Value Add**:
  - **FHIR R4 Gateway**: Connects to hospital EHR systems (Epic, Cerner, HAPI FHIR) via standard FHIR APIs to aggregate multi-site patient records into a single unified view.

### 7. Lab Results (`app/(tabs)/records/labs/index.tsx`)
- **Frontend Current State**: Visual trend cards showing historical lab test values (Serum Creatinine $1.1 \rightarrow 1.4\text{ mg/dL}$, eGFR $58 \rightarrow 47\text{ mL/min}$).
- **Backend Integration Value Add**:
  - **Automated Abnormality Detection**: Scans incoming FHIR `Observation` resources against age/gender-adjusted reference ranges and triggers automatic clinical alerts when values cross safety thresholds.
  - **Longitudinal Trend Analytics**: Queries a time-series database (e.g., InfluxDB or BigQuery) to compute velocity of lab degradation.

### 8. Active Medications (`app/(tabs)/records/medications.tsx`)
- **Frontend Current State**: List of active prescriptions (Lisinopril, Metformin, Furosemide) showing dosage and frequency.
- **Backend Integration Value Add**:
  - **Drug-Drug Interaction Engine**: Integrates with RxNorm and clinical APIs (e.g., First Databank) to check for drug interactions and contraindications.
  - **Refill Management**: Connects to pharmacy APIs (SureScripts) for automated prescription refill requests.

### 9. Clinical Notes & Encounters (`app/(tabs)/records/encounters.tsx`)
- **Frontend Current State**: List of historical clinical encounter notes and physician summaries.
- **Backend Integration Value Add**:
  - **NLP Note Summarization**: Uses generative AI to summarize complex physician progress notes into plain, patient-accessible language.

### 10. Medical Documents (`app/(tabs)/records/documents.tsx`)
- **Frontend Current State**: List of uploaded medical documents, lab PDFs, and discharge summaries.
- **Backend Integration Value Add**:
  - **Document OCR & Structuring**: Ingests uploaded PDF/image documents using Document AI / Tesseract OCR, extracts structured lab values, and populates the patient's FHIR record automatically.

### 11. Appointments (`app/(tabs)/appointments/index.tsx`)
- **Frontend Current State**: Display of upcoming scheduled visits and past appointment history.
- **Backend Integration Value Add**:
  - **EHR Scheduling Sync**: Syncs directly with provider calendars via FHIR `Appointment` resources.
  - **Telehealth Room Generation**: Automatically provisions encrypted WebRTC / Zoom Healthcare video consultation links upon appointment confirmation.

### 12. Profile & Settings (`app/(tabs)/profile/index.tsx`)
- **Frontend Current State**: Patient demographic summary (Age, DOB, Patient ID) and sign-out action.
- **Backend Integration Value Add**:
  - **Master Patient Index (MPI)**: Resolves patient identity across disparate healthcare systems using probabilistic matching.
  - **Consent Management Engine**: Allows patients to manage granular HIPAA data-sharing consents and emergency contact preferences.

---

## 6. Doctor Web Dashboard — Page Breakdown & Backend Value Add

### 1. Doctor Auth Login (`src/pages/LoginPage.tsx`)
- **Frontend Current State**: Doctor login form authenticating Dr. Amelia Smith (`doctor@carepilot.ai`).
- **Backend Integration Value Add**:
  - **Enterprise SSO / SAML 2.0**: Integrates with hospital Active Directory / Okta SSO for single sign-on.
  - **NPI & License Verification**: Validates provider National Provider Identifier (NPI) credentials against government registries.

### 2. Dashboard Home (`src/pages/DashboardPage.tsx`)
- **Frontend Current State**: 4 KPI summary cards (Pending Reviews: 12, Urgent Cases: 2, Today's Consultations: 8, Reviewed: 24) and a Priority Queue preview widget.
- **Backend Integration Value Add**:
  - **Real-Time Aggregation Engine**: Computes dashboard KPIs in real time using Redis cached counts over a PostgreSQL queue database.
  - **Smart Queue Dispatch**: Dynamically assigns incoming patient consultations to available specialists based on provider load and sub-specialty tags (e.g., Nephrology vs. Cardiology).

### 3. Review Queue (`src/pages/QueuePage.tsx`)
- **Frontend Current State**: Filterable table with search, urgency tags (`ROUTINE`, `SOON`, `URGENT`), status filters, and sorting options.
- **Backend Integration Value Add**:
  - **Server-Side Pagination & Filtering**: Queries BigQuery / PostgreSQL with full-text search indexes.
  - **Optimistic Locking Protocol**: Prevents concurrent review conflicts by placing a temporary 5-minute lock on a consultation record as soon as a physician opens it.

### 4. Consultation Review Workspace (`src/pages/ConsultationReviewPage.tsx`) — HERO WORKSPACE
- **Frontend Current State**: Information-dense 3-column clinical workspace:
  - **Column 1 (Left - Patient Context)**: Demographics, active conditions, current medications, and interactive lab trend cards.
  - **Column 2 (Center - Conversation)**: Complete patient query transcript and real-time status state indicator.
  - **Column 3 (Right - AI Analysis & RAG Draft Editor)**: AI triage classification, editable response draft with live **"Edited"** badge tracker, and clickable evidence citations (MedlinePlus, NIDDK).
  - **Action Bar**: Reject, Save Draft, Approve, and Approve & Next buttons.
- **Backend Integration Value Add**:
  - **RAG Pipeline (Retrieval-Augmented Generation)**:
    - *Embedding Vector DB (Vertex AI Search / pgvector / Qdrant)*: Performs semantic vector search over medical knowledge bases (MedlinePlus, PubMed, NIDDK guidelines) using patient query embeddings.
    - *LLM Generation (Gemini 1.5 Pro / Med-PaLM 2)*: Generates a tailored response draft conditioned on retrieved medical context and patient EHR data (Creatinine history, CKD Stage 3 diagnosis).
  - **Edit Distance & Alignment Analytics**: Tracks exact character and semantic edits made by the physician using Levenshtein distance calculations. Edit telemetry is stored to evaluate LLM accuracy and train future fine-tuned models.
  - **EHR Writeback & E-Signature**: On approval, cryptographically signs the final text using the doctor's digital certificate and writes it back to the hospital EHR as an official clinical note.

### 5. Patient Directory (`src/pages/PatientsPage.tsx`)
- **Frontend Current State**: Searchable patient table displaying MRN, demographics, primary condition, and last visit date.
- **Backend Integration Value Add**:
  - **ElasticSearch Cluster**: Provides sub-50ms search capabilities across millions of patient records by name, MRN, diagnosis code (ICD-10), or medication.

### 6. Patient EMR Workspace (`src/pages/PatientWorkspacePage.tsx`)
- **Frontend Current State**: 7-tab deep EHR viewer (`Overview`, `Timeline`, `Labs`, `Medications`, `Documents`, `Consultations`, `Appointments`) featuring interactive Recharts `LineChart` for lab trends.
- **Backend Integration Value Add**:
  - **FHIR Data Engine**: Assembles a unified longitudinal timeline from raw FHIR `Encounter`, `DiagnosticReport`, `Observation`, and `Procedure` resources.
  - **DICOM Viewer Integration**: Integrates web-based DICOM viewers (OHIF / Cornerstone.js) for viewing CT scans, X-rays, and ultrasounds directly within the workspace.

### 7. Appointments Management (`src/pages/AppointmentsPage.tsx`)
- **Frontend Current State**: Tabbed view (`Today`, `Upcoming`, `Past`) with Confirm, Reject, and Reschedule actions.
- **Backend Integration Value Add**:
  - **Bi-Directional Calendar Sync**: Syncs appointment status back to hospital scheduling software (Epic Cadence / Cerner Scheduling).

### 8. Analytics Dashboard & Academic Model Evaluation (`src/pages/AnalyticsPage.tsx`) — DEEP DIVE
- **Frontend Current State**: Operational performance charts (Volume LineChart, Edit Categories PieChart, Urgency Distribution BarChart, 80.9% Acceptance Rate Gauge) and an Academic Evaluation section ($N=221$ test suite, Accuracy 91.4%, Macro F1 0.89, 3x3 Confusion Matrix).
- **Backend Integration How-It-Works & Value Add**:
  - **Operational Analytics (BigQuery + Spark Pipeline)**:
    - *Data Collection*: Every consultation action (`submit`, `edit`, `approve`, `reject`) emits JSON event telemetry to Cloud Pub/Sub.
    - *Streaming Aggregation*: Apache Spark / BigQuery SQL queries aggregate metrics hourly:
      $$\text{Acceptance Rate} = \frac{N_{\text{approved\_unedited}} + N_{\text{approved\_minor\_edit}}}{N_{\text{total\_reviewed}}} \times 100\%$$
    - *Chart Feed*: The frontend fetches aggregated JSON endpoints to render Recharts line and pie charts.
  - **Academic AI Evaluation Engine (MLflow + Vertex AI Pipelines)**:
    - *Synthea Ground-Truth Mapping*: The backend maps Synthea synthetic EHR `EncounterClass` and clinical triage rules to ground-truth labels (`ROUTINE`, `SOON`, `URGENT`).
    - *Automated Model Testing*: Runs batch inferences of the Bio_ClinicalBERT urgency classifier against $N=221$ unseen test cases.
    - *Confusion Matrix Calculation*: Computes multi-class precision, recall, and F1-score matrices:
      $$\text{Precision}_c = \frac{TP_c}{TP_c + FP_c}, \quad \text{Recall}_c = \frac{TP_c}{TP_c + FN_c}, \quad F1_c = 2 \cdot \frac{\text{Precision}_c \cdot \text{Recall}_c}{\text{Precision}_c + \text{Recall}_c}$$
    - *Drift Monitoring*: If model accuracy drops below 90% or Urgent Recall drops below 95%, automated Webhooks trigger alerts for model retraining.

### 9. Clinical Notifications (`src/pages/NotificationsPage.tsx`)
- **Frontend Current State**: Feed of urgent clinical notifications and system alerts with "Mark all as read" controls.
- **Backend Integration Value Add**:
  - **Critical Alert Engine**: Monitors streaming EHR data for critical threshold breaches (e.g. Creatinine $> 2.5\text{ mg/dL}$ or Potassium $> 6.0\text{ mEq/L}$) and dispatches high-priority web and SMS alerts to the physician on call.

### 10. Settings & Preferences (`src/pages/SettingsPage.tsx`)
- **Frontend Current State**: Account settings, notification preference toggles, queue sorting rules, and password updates.
- **Backend Integration Value Add**:
  - **User Profile & Permission Service**: Manages provider preferences, notification rules, and role-based access control (RBAC) settings stored in a secure relational database.

---

## 7. End-to-End Realtime Workflow & Demo Protocol

To run the complete system and observe real-time cross-tab synchronization:

1. **Start Doctor Web Dashboard**:
   ```powershell
   cd D:\CarePilotAI\doctor-dashboard
   npm run dev
   ```
   Access `http://localhost:5173` (Login: `doctor@carepilot.ai` / `demo1234`).

2. **Start Patient Mobile / Web App**:
   ```powershell
   cd D:\CarePilotAI\patient-app
   npx.cmd expo start --web --clear
   ```
   Access `http://localhost:8081` (Login: `patient@carepilot.ai` / `demo1234`).

3. **Execute End-to-End Flow**:
   - On Patient App (`:8081`), click **New Consultation**, type: *"Why is my recent blood test different from before?"*, and click **Send**.
   - Status transitions to **"Waiting for Doctor Review"**.
   - On Doctor Dashboard (`:5173`), open the request in the Review Queue.
   - Inspect Column 1 (Creatinine trend $1.1 \rightarrow 1.4\text{ mg/dL}$), edit the response draft in Column 3, and click **Approve & Send**.
   - Switch back to Patient App (`:8081`) $\rightarrow$ **The status updates instantly via `BroadcastChannel` to "Doctor Approved Clinical Response" displaying Dr. Amelia Smith's verified clinical guidance!**
