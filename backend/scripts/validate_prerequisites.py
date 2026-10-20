#!/usr/bin/env python
"""
CarePilot AI — Prerequisite Validation Script

Checks all prerequisites that can be verified WITHOUT external artifacts:
- Python virtual environment
- Python dependencies
- .env configuration
- Code syntax
- Test suites (those runnable without DB/KB)

Missing artifacts are clearly reported with recovery instructions.
"""
import sys
import os
import importlib
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(r"D:\Final project\Carepilot")
BACKEND_ROOT = PROJECT_ROOT / "backend"
RAG_ROOT = PROJECT_ROOT / "rag_knowledge"

def print_header(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_check(name, status, detail=""):
    icon = "[OK]" if status else "[FAIL]"
    print(f"  {icon} {name}: {detail}")

def check_python_version():
    """Check Python version meets requirements."""
    version = sys.version_info
    if version.major == 3 and version.minor >= 11:
        print_check("Python version", True, f"{version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print_check("Python version", False, f"{version.major}.{version.minor}.{version.micro} (need 3.11+)")
        return False

def check_module(module_name, display_name=None):
    """Check if a Python module can be imported."""
    display = display_name or module_name
    try:
        importlib.import_module(module_name)
        print_check(display, True, "Installed")
        return True
    except ImportError:
        print_check(display, False, "Not installed")
        return False

def check_env_file():
    """Check .env file exists and has required fields."""
    env_file = BACKEND_ROOT / ".env"
    if not env_file.exists():
        print_check("backend/.env", False, "File not found")
        return False

    required_keys = [
        "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD",
        "KB_SNAPSHOT_ID", "CHROMA_COLLECTION", "BM25_INDEX_PATH",
        "EMBEDDING_MODEL", "LLM_LOCAL_MODEL_PATH", "GEMINI_API_KEY",
        "KB_DENSE_TOP_K", "KB_BM25_TOP_K", "KB_RRF_K", "KB_FINAL_TOP_N",
        "EHR_RETRIEVAL_K", "FAITHFULNESS_THRESHOLD", "NLI_ENTAILMENT_THRESHOLD",
        "BACKEND_HOST", "BACKEND_PORT", "CORS_ORIGINS",
    ]

    missing = []
    content = env_file.read_text(encoding="utf-8")
    for key in required_keys:
        if key not in content:
            missing.append(key)

    if missing:
        print_check("backend/.env", False, f"Missing keys: {', '.join(missing)}")
        return False
    else:
        print_check("backend/.env", True, "All required keys present")
        return True

def check_env_value(key, expected_value):
    """Check a specific .env value."""
    env_file = BACKEND_ROOT / ".env"
    content = env_file.read_text(encoding="utf-8")
    for line in content.splitlines():
        if line.strip().startswith(f"{key}="):
            actual = line.split("=", 1)[1].strip()
            if actual == expected_value:
                print_check(f".env {key}", True, f"={actual}")
                return True
            else:
                print_check(f".env {key}", False, f"={actual} (expected {expected_value})")
                return False
    print_check(f".env {key}", False, "Key not found")
    return False

def check_file(path, description):
    """Check if a file or directory exists."""
    if path.exists():
        print_check(description, True, str(path))
        return True
    else:
        print_check(description, False, f"Not found at {path}")
        return False

def check_syntax(filepath):
    """Check Python syntax of a file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            compile(f.read(), filepath, "exec")
        return True
    except SyntaxError as e:
        print(f"  ❌ SYNTAX ERROR in {filepath}: {e}")
        return False

def main():
    all_ok = True

    print_header("CAREPILOT AI - PREREQUISITE VALIDATION")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Python: {sys.executable}")

    # 1. Python version
    print_header("1. Python Environment")
    all_ok &= check_python_version()

    # 2. Python dependencies
    print_header("2. Python Dependencies")
    deps = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("pydantic", "Pydantic"),
        ("pydantic_settings", "Pydantic Settings"),
        ("sqlalchemy", "SQLAlchemy"),
        ("psycopg", "psycopg3"),
        ("alembic", "Alembic"),
        ("sentence_transformers", "Sentence Transformers"),
        ("transformers", "Transformers"),
        ("torch", "PyTorch"),
        ("chromadb", "ChromaDB"),
        ("rank_bm25", "rank-bm25"),
        ("sklearn", "scikit-learn"),
        ("scipy", "SciPy"),
        ("numpy", "NumPy"),
        ("requests", "Requests"),
        ("httpx", "HTTPX"),
        ("dotenv", "python-dotenv"),
        ("whisper", "OpenAI Whisper"),
        ("edge_tts", "edge-tts"),
        ("pytest", "Pytest"),
    ]
    for module, display in deps:
        all_ok &= check_module(module, display)
    print_header("3. Environment Configuration")
    all_ok &= check_env_file()
    all_ok &= check_env_value("DB_HOST", "db.avvajicpgohgiwxucstc.supabase.co")
    all_ok &= check_env_value("DB_PORT", "5432")
    all_ok &= check_env_value("DB_NAME", "carepilot_v3")
    all_ok &= check_env_value("DB_USER", "postgres")
    all_ok &= check_env_value("LANGUAGE_DEFAULT", "en")

    # 4. Code syntax
    print_header("4. Code Syntax Verification")
    syntax_files = [
        BACKEND_ROOT / "app" / "main.py",
        BACKEND_ROOT / "app" / "core" / "settings.py",
        BACKEND_ROOT / "app" / "core" / "llm.py",
        BACKEND_ROOT / "app" / "api" / "consult.py",
        BACKEND_ROOT / "app" / "api" / "patient.py",
        BACKEND_ROOT / "app" / "api" / "queue.py",
        BACKEND_ROOT / "app" / "api" / "voice.py",
        BACKEND_ROOT / "app" / "db" / "models_v3.py",
        BACKEND_ROOT / "app" / "db" / "session.py",
        BACKEND_ROOT / "app" / "pipeline" / "orchestrator.py",
        BACKEND_ROOT / "app" / "pipeline" / "classify.py",
        BACKEND_ROOT / "app" / "pipeline" / "redflag.py",
        BACKEND_ROOT / "app" / "pipeline" / "normalize.py",
        BACKEND_ROOT / "app" / "pipeline" / "retrieve_ehr.py",
        BACKEND_ROOT / "app" / "pipeline" / "retrieve_kb.py",
        BACKEND_ROOT / "app" / "pipeline" / "generate.py",
        BACKEND_ROOT / "app" / "pipeline" / "validate.py",
        BACKEND_ROOT / "app" / "pipeline" / "detect_context_gaps.py",
        BACKEND_ROOT / "app" / "pipeline" / "stt.py",
        BACKEND_ROOT / "app" / "pipeline" / "tts.py",
    ]
    for f in syntax_files:
        if not check_syntax(f):
            all_ok = False

    # 5. RAG artifacts
    print_header("5. RAG Knowledge Base Artifacts")
    all_ok &= check_file(RAG_ROOT / "chroma_db" / "chroma.sqlite3", "ChromaDB SQLite")
    # Check for actual vector store files (should have more than just sqlite3)
    chroma_files = list((RAG_ROOT / "chroma_db").glob("*")) if (RAG_ROOT / "chroma_db").exists() else []
    if len(chroma_files) <= 1:
        print_check("ChromaDB vector store", False, "Only chroma.sqlite3 present - full vector store missing")
        all_ok = False
    else:
        print_check("ChromaDB vector store", True, f"{len(chroma_files)} files present")

    all_ok &= check_file(RAG_ROOT / "bm25_index_v5.pkl", "BM25 index file")

    # 6. Model files
    print_header("6. Model Files")
    models_dir = BACKEND_ROOT / "models"
    all_ok &= check_file(models_dir / "intent_classifier.pkl", "Intent classifier")
    all_ok &= check_file(models_dir / "urgency_classifier.pkl", "Urgency classifier")

    # 7. Test suites
    print_header("7. Test Suites (Runnable Without External Artifacts)")
    tests_dir = BACKEND_ROOT / "tests"
    test_files = [
        ("test_redflag_11_categories.py", "Red-Flag Categories (88 tests)"),
        ("test_skip_reasons.py", "Skip Reasons (7 tests)"),
        ("test_ehr_fact_accuracy.py", "EHR Fact Accuracy (43 tests)"),
        ("test_eval_harness.py", "Evaluation Harness (16 tests)"),
        ("test_pillar_b_core.py", "Pillar B Core Integration"),
    ]
    for test_file, display in test_files:
        if (tests_dir / test_file).exists():
            print_check(test_file, True, "File present")
        else:
            print_check(test_file, False, "File not found")
            all_ok = False

    # 8. Frontend directories
    print_header("8. Frontend Applications")
    doctor_dash = PROJECT_ROOT / "doctor-dashboard"
    patient_app = PROJECT_ROOT / "patient-app"
    all_ok &= check_file(doctor_dash / "package.json", "Doctor Dashboard package.json")
    all_ok &= check_file(doctor_dash / "node_modules", "Doctor Dashboard node_modules")
    all_ok &= check_file(patient_app / "package.json", "Patient App package.json")
    all_ok &= check_file(patient_app / "node_modules", "Patient App node_modules")

    # Summary
    print_header("9. SUMMARY")
    if all_ok:
        print("  [OK] All checkable prerequisites satisfied.")
        print("  [WARN] External artifacts still required: PostgreSQL dump, ChromaDB zip,")
        print("         BM25 pickle, Ollama qwen3:8b model, FFmpeg.")
    else:
        print("  [FAIL] Some prerequisites missing - see failures above.")

    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())