# CarePilot AI — Collaborator & Friend Setup Guide

Welcome to the CarePilot AI development team! This guide walks you through setting up CarePilot AI on your Windows laptop so you can collaborate seamlessly on the project using your dedicated branch: **`friend`**.

---

## 1. Purpose and Architecture

CarePilot AI is an academic clinical AI system providing a **Human-in-the-Loop (HITL) Retrieval-Augmented Generation (RAG) Pipeline for Patient–Doctor Communication**.

### Core Architecture Principles
1. **Safety Invariant I1 (Clinical Guardrail)**: The patient mobile app never displays raw AI drafts. Responses are only delivered to the patient after a licensed clinician approves or edits them in the Doctor Dashboard.
2. **Safety Invariant I2 (Patient Data Isolation)**: 100% of patient Electronic Health Record (EHR) queries are strictly scoped by `patient_id`. Zero cross-tenant data leakage is permitted.
3. **Safety Invariant I3 (Firm Emergency Override)**: Patient queries matching any of the 11 clinical emergency red-flag categories (e.g., chest pain, acute hemorrhage, stroke signs, anaphylaxis) trigger immediate emergency diversion without AI draft generation.
4. **Citation Boundary Contract**: Every claim in an AI response is grounded with explicit citation tokens (`kb:{doc_id}:chunk{n}` or `ehr:{table}:{stable_id}`) verified by cross-encoder Natural Language Inference (NLI).

### Why Certain Artifacts Are Shared via Google Drive
The repository code, test suites, evaluation scripts, and UI applications live on GitHub. However, runtime data artifacts—such as the PostgreSQL longitudinal database (~62 MB compressed / ~500 MB raw), the ChromaDB vector embeddings (~227 MB compressed / ~376 MB raw), and local environment credentials—are excluded from Git to prevent repository bloat, preserve Git performance, and protect secrets. These are packaged into an external bundle named **`CarePilotAI_Transfer`** shared via Google Drive.

---

## 2. Prerequisites

Install the following dependencies on your Windows laptop:

| Software | Required Version | Verified Version | Installation Command / Link |
|---|---|---|---|
| **Operating System** | Windows 10/11 64-bit | Windows 11 Pro 64-bit | Standard Windows OS |
| **PowerShell** | PowerShell 5.1+ | PowerShell 7.4+ | Built-in or `winget install Microsoft.PowerShell` |
| **Git** | 2.40+ | 2.47+ | `winget install Git.Git` |
| **Python** | 3.11 – 3.13 (64-bit) | Python 3.13.1 | `winget install Python.Python.3.13` *(Check "Add to PATH")* |
| **PostgreSQL** | 16.0+ | PostgreSQL 18.0 | `winget install PostgreSQL.PostgreSQL` |
| **Node.js & npm** | Node 20 LTS | Node 20.18.0 / npm 10.8+ | `winget install OpenJS.NodeJS.LTS` |
| **Ollama** | 0.3.0+ | 0.4.0+ | Download installer from [https://ollama.com/download](https://ollama.com/download) |

---

## 3. Clone the Repository

Open Windows PowerShell, navigate to your desired development directory (e.g., `D:\` or `C:\Projects`), and clone your branch:

```powershell
# 1. Clone repository
git clone https://github.com/Sarathychandramohan/Carepilot.git CarePilotAI

# 2. Enter project folder
Set-Location -Path "CarePilotAI"

# 3. Check out your dedicated collaboration branch
git checkout friend

# 4. Confirm branch and clean status
git status
```

---

## 4. Download the External Data Folder

1. Open your browser and navigate to the shared Google Drive folder:
   👉 **Google Drive Link**: `[INSERT_GOOGLE_DRIVE_FOLDER_LINK_HERE]`
2. Download the entire **`CarePilotAI_Transfer`** folder as a ZIP file (or sync it to your laptop).
3. Extract the folder to a convenient local location (e.g., `D:\CarePilotAI_Transfer` or your `Downloads` directory).

---

## 5. Folder Structure and File Mapping

The `CarePilotAI_Transfer` folder contains pre-configured runtime artifacts. Map each item to its exact destination inside your local repository:

```
CarePilotAI_Transfer/
├── 01_DATABASE/
│   └── carepilot_v3_backup.dump       ──> Restore into PostgreSQL database 'carepilot_v3'
├── 02_RAG_ARTIFACTS/
│   ├── chroma_db.zip                 ──> Extract into D:\CarePilotAI\rag_knowledge\
│   └── bm25_index_v5.pkl             ──> Copy into D:\CarePilotAI\rag_knowledge\
├── 03_SYNTHEA_ETL/
│   └── carepilot_data/               ──> Reference ETL scripts (already inside git/transfer)
├── 04_CONFIG_AND_ENV/
│   └── .env                          ──> Copy into D:\CarePilotAI\backend\.env
├── 05_RESEARCH_DATA/
│   ├── patient_picker_sheet.csv      ──> Reference clinical summaries
│   └── patient_picker_shortlist.csv  ──> Reference study cohort
├── 06_LLM_CONFIG/
│   └── README_OLLAMA.md              ──> Ollama setup instructions
├── CHECKSUMS_SHA256.txt              ──> SHA-256 verification hashes
├── SETUP_ON_ANOTHER_LAPTOP.md        ──> General transfer reference
└── TRANSFER_MANIFEST.md              ──> Architectural artifact manifest
```

### Destination Mapping Commands (Run from `D:\CarePilotAI`)
Assuming your downloaded transfer folder is at `D:\CarePilotAI_Transfer`:

```powershell
# 1. Unpack ChromaDB vector store
Expand-Archive -Path "D:\CarePilotAI_Transfer\02_RAG_ARTIFACTS\chroma_db.zip" -DestinationPath "rag_knowledge\" -Force

# 2. Copy BM25 Index
Copy-Item "D:\CarePilotAI_Transfer\02_RAG_ARTIFACTS\bm25_index_v5.pkl" -Destination "rag_knowledge\" -Force

# 3. Copy Local Environment Configuration
Copy-Item "D:\CarePilotAI_Transfer\04_CONFIG_AND_ENV\.env" -Destination "backend\.env" -Force
```

---

## 6. Database Setup

CarePilot AI uses a **PostgreSQL 18** database named **`carepilot_v3`** containing 2,330 patient longitudinal records (~2.5 million rows across 9 clinical tables).

### Step 1: Create Database
Open PowerShell (ensure PostgreSQL bin is in your PATH or add `C:\Program Files\PostgreSQL\18\bin`):
```powershell
# Add PostgreSQL CLI tools to session PATH if needed
$env:PATH += ";C:\Program Files\PostgreSQL\18\bin"

# Create the target database
createdb -U postgres -h localhost -p 5432 carepilot_v3
```
*(Enter your local postgres superuser password when prompted).*

### Step 2: Restore Database Dump
Restore the custom-format snapshot from the transfer folder:
```powershell
pg_restore -U postgres -h localhost -p 5432 -d carepilot_v3 -v "D:\CarePilotAI_Transfer\01_DATABASE\carepilot_v3_backup.dump"
```
*Note: A few warning lines about roles or tablespaces during pg_restore are normal and safe to ignore.*

### Step 3: Configure `backend/.env`
Open `backend/.env` in your text editor and ensure the password matches your local PostgreSQL setup:
```ini
DB_HOST=localhost
DB_PORT=5432
DB_NAME=carepilot_v3
DB_USER=postgres
DB_PASSWORD=YOUR_LOCAL_POSTGRES_PASSWORD

KB_SNAPSHOT_ID=v5
CHROMA_COLLECTION=carepilot_kb_v5
BM25_INDEX_PATH=rag_knowledge/bm25_index_v5.pkl
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5

BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://localhost:8081

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
```

---

## 7. Knowledge Base and Retrieval Setup

CarePilot AI uses a convex-combination hybrid retrieval engine combining dense vector search and sparse lexical search:
- **Dense Store**: ChromaDB collection `carepilot_kb_v5` with 10,074 chunks from 1,045 documents located at `rag_knowledge/chroma_db`.
- **Sparse Index**: BM25Okapi index located at `rag_knowledge/bm25_index_v5.pkl`.
- **Embedding Model**: `BAAI/bge-small-en-v1.5` (automatically downloaded from Hugging Face cache on first run; no manual file copy required).

### Verification
Run the built-in inspection utility from the repository root:
```powershell
.\.venv\Scripts\python -m backend.scripts.inspect_pillar_a kb
```
It should report: `1,045 documents, 10,074 chunks in collection carepilot_kb_v5`.

---

## 8. Model Setup (Local LLM via Ollama)

CarePilot AI generates clinician draft suggestions strictly locally using **Ollama** running **`qwen3:8b`** (Q4_K_M 4-bit quantization, 8 Billion parameters).

1. Install and start the Ollama application from [https://ollama.com/download](https://ollama.com/download). It will run in your Windows system tray.
2. In PowerShell, pull the verified model:
   ```powershell
   ollama pull qwen3:8b
   ```
3. Test that the model is responsive:
   ```powershell
   ollama list
   ollama run qwen3:8b "CarePilot pre-flight check"
   ```

---

## 9. Run the Project

### A. Python Backend Setup
From `D:\CarePilotAI`:
```powershell
# 1. Create virtual environment
python -m venv .venv

# 2. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 3. Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### B. Frontend Dashboards Setup
```powershell
# 1. Doctor Dashboard (React 18 + Vite)
Set-Location -Path "doctor-dashboard"
npm install
Set-Location -Path ".."

# 2. Patient App (React Native / Expo SDK 57)
Set-Location -Path "patient-app"
npm install
Set-Location -Path ".."
```

### C. Launching All Services
Start services in separate PowerShell terminal windows:

| Terminal | Service | Command | Working Directory | Default URL |
|---|---|---|---|---|
| **Terminal 1** | **PostgreSQL** | Windows Background Service | — | `localhost:5432` |
| **Terminal 2** | **Ollama** | `ollama serve` | — | `http://localhost:11434` |
| **Terminal 3** | **FastAPI Backend** | `.\.venv\Scripts\Activate.ps1`<br>`uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload` | `D:\CarePilotAI` | `http://localhost:8000/docs` |
| **Terminal 4** | **Doctor Dashboard** | `npm run dev` | `D:\CarePilotAI\doctor-dashboard` | `http://localhost:5173` |
| **Terminal 5** | **Patient App** | `npx expo start --web` | `D:\CarePilotAI\patient-app` | `http://localhost:8081` |

---

## 10. Verify the Setup

Run the regression test suites to confirm full end-to-end functionality:

```powershell
Set-Location -Path "D:\CarePilotAI"
.\.venv\Scripts\Activate.ps1

# 1. Test 11 Red-Flag Clinical Categories (88 tests)
python -m pytest backend/tests/test_redflag_11_categories.py

# 2. Test EHR Fact Extraction Accuracy (43 tests)
python -m pytest backend/tests/test_ehr_fact_accuracy.py

# 3. Test Skip Reasons and Pipeline Safety Gates (7 tests)
python -m pytest backend/tests/test_skip_reasons.py

# 4. Test Evaluation Provenance Logic (2 tests)
python -m pytest backend/tests/test_eval_provenance.py

# 5. Run Fast Evaluation Harness Wiring Test (Dry Run Only)
python -m backend.eval.run --config full --split gold-dev --seed 42 --subset 2 --dry-run
```

> [!IMPORTANT]
> **Safety Rule**: Never run full benchmark evaluation (`--dry-run` omitted) without coordination, as full evaluation executes model runs that generate benchmark logs locked under research pre-registration.

---

## 11. Troubleshooting

| Symptom | Root Cause | Fix |
|---|---|---|
| `psycopg.OperationalError: connection to 127.0.0.1:5432 failed` | PostgreSQL service not running or port blocked | Start the PostgreSQL service via Windows `services.msc` or run `net start postgresql-x64-18`. |
| `ERROR GUARD: DATABASE_URL points to 'carepilot_db'! Target MUST be 'carepilot_v3'` | Incorrect database name in `backend/.env` | Update `backend/.env` to `DB_NAME=carepilot_v3`. |
| `Ollama server not reachable at http://127.0.0.1:11434` | Ollama service not started | Launch Ollama from Windows Start menu or run `ollama serve`. |
| `FileNotFoundError: bm25_index_v5.pkl` | BM25 index not copied to repo | Copy `02_RAG_ARTIFACTS\bm25_index_v5.pkl` to `D:\CarePilotAI\rag_knowledge\`. |
| `Chroma collection 'carepilot_kb_v5' does not exist` | ChromaDB ZIP not unpacked correctly | Unpack `chroma_db.zip` directly into `rag_knowledge\chroma_db`. |
| `Script execution is disabled on this system` | PowerShell ExecutionPolicy | Run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`. |

---

## 12. Git Collaboration Rules

To keep our development organized and conflict-free:

1. **Dedicated Branches**:
   - Sarathy develops on **`main`**.
   - You develop on **`friend`**.
2. **Commit and Push to Your Own Branch**:
   ```powershell
   git add <modified-source-files>
   git commit -m "feat(ui): your descriptive feature message"
   git push origin friend
   ```
3. **Pull Requests for Integration**:
   - When your feature is ready, open a **Pull Request (PR)** on GitHub from `friend` into `main`.
   - Never commit directly to or force-push onto `main`.
   - Sarathy will review and merge changes into `main`.
4. **Staying Up-to-Date**:
   - To incorporate updates from `main` into your `friend` branch:
     ```powershell
     git fetch origin
     git merge origin/main
     git push origin friend
     ```

---

## 13. Keeping Local Artifacts Out of Git

Never commit database dumps, vector indices, node modules, virtual environments, or `.env` files to Git.

Before every commit, always check:
```powershell
git status --short
```

Verify that none of the following appear in your staged changes:
- `backend/.env`
- `*.dump`, `*.sql`
- `rag_knowledge/chroma_db/`
- `rag_knowledge/*.pkl`
- `node_modules/`, `.venv/`

If you have questions, reach out to Sarathy directly!
