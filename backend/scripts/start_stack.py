#!/usr/bin/env python
"""
CarePilot AI — Complete Stack Startup Script

Orchestrates the full 5-terminal service stack:
1. PostgreSQL (external service)
2. Ollama
3. FastAPI Backend (uvicorn)
4. Doctor Dashboard (npm dev)
5. Patient App (expo start --web)

Run this AFTER all runtime artifacts are restored:
- PostgreSQL database carepilot_v3 restored
- ChromaDB extracted to rag_knowledge/chroma_db/
- BM25 index copied to rag_knowledge/
- Ollama qwen3:8b model pulled
- FFmpeg installed in PATH
- All Python/Node dependencies installed
"""
import subprocess
import sys
import os
import time
import signal
from pathlib import Path

PROJECT_ROOT = Path(r"D:\Final project\Carepilot")
BACKEND_VENV_PY = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"

processes = []


def print_header(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def start_backend():
    """Start FastAPI backend with uvicorn."""
    print_header("STARTING BACKEND")
    cmd = [
        str(BACKEND_VENV_PY), "-m", "uvicorn",
        "backend.app.main:app",
        "--host", "127.0.0.1",
        "--port", "8000",
        "--reload",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "backend")
    proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), env=env)
    processes.append(("Backend (FastAPI)", proc))
    print(f"  PID: {proc.pid}")
    return proc


def check_ollama():
    """Check if Ollama server is reachable."""
    import urllib.request
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            import json
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            has_qwen = any("qwen3:8b" in m for m in models)
            print(f"  Ollama server: reachable")
            print(f"  Models: {models}")
            if not has_qwen:
                print("  ⚠️  WARNING: qwen3:8b not found — system will use NVIDIA API fallback")
            return True
    except Exception as e:
        print(f"  ❌ Ollama server NOT reachable: {e}")
        print("  ⚠️  System will use NVIDIA API fallback (requires internet)")
        return True  # Don't fail — NVIDIA fallback is available


def check_database():
    """Check if PostgreSQL database is reachable."""
    import urllib.request
    import json
    # We can't easily check PostgreSQL without psycopg, so just report
    print("  Database: will be checked on backend startup")
    print("  Configured: db.avvajicpgohgiwxucstc.supabase.co:5432/carepilot_v3")
    return True


def run_tests():
    """Run available test suites."""
    print_header("RUNNING TEST SUITES")
    tests = [
        ("test_redflag_11_categories.py", "Red-Flag Categories"),
        ("test_skip_reasons.py", "Skip Reasons"),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "backend")
    all_passed = True
    for test_file, display in tests:
        print(f"\n  Running: {display} ({test_file})")
        result = subprocess.run(
            [str(BACKEND_VENV_PY), "-m", "pytest", str(PROJECT_ROOT / "backend" / "tests" / test_file), "-q"],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"  ✅ {display}: PASSED")
        else:
            print(f"  ❌ {display}: FAILED")
            print(f"  STDERR: {result.stderr[-200:] if result.stderr else 'N/A'}")
            all_passed = False
    return all_passed


def start_frontend(name, cmd, cwd, port):
    """Start a frontend application."""
    print_header(f"STARTING {name.upper()}")
    print(f"  Command: {cmd}")
    print(f"  Working dir: {cwd}")
    print(f"  Expected URL: http://localhost:{port}")
    # We start but don't block — user should open browser manually
    proc = subprocess.Popen(cmd, cwd=str(cwd), shell=True)
    processes.append((name, proc))
    print(f"  PID: {proc.pid}")
    return proc


def main():
    print_header("CAREPILOT AI — COMPLETE STACK STARTUP")

    # Step 1: Run tests
    tests_passed = run_tests()

    # Step 2: Check external services
    print_header("CHECKING EXTERNAL SERVICES")
    check_ollama()
    check_database()

    # Step 3: Start backend
    backend_proc = start_backend()

    # Wait for backend to be ready
    print("  Waiting for backend to be ready...")
    import time
    for i in range(10):
        time.sleep(2)
        import urllib.request
        try:
            req = urllib.request.Request("http://127.0.0.1:8000/docs")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    print("  ✅ Backend is ready at http://127.0.0.1:8000/docs")
                    break
        except Exception:
            if i < 9:
                print(f"  Waiting... ({i+1}/10)")
            else:
                print("  ⚠️  Backend not ready yet — check logs")

    # Step 4: Start frontends
    print_header("STARTING FRONTENDS")
    doctor_proc = start_frontend(
        "Doctor Dashboard",
        "npm run dev",
        PROJECT_ROOT / "doctor-dashboard",
        5173,
    )
    time.sleep(3)

    patient_proc = start_frontend(
        "Patient App",
        "npx expo start --web",
        PROJECT_ROOT / "patient-app",
        8081,
    )

    # Summary
    print_header("STACK STARTUP COMPLETE")
    print("  Services started:")
    for name, proc in processes:
        print(f"    • {name} (PID: {proc.pid})")

    print("\n  Access URLs:")
    print("    • Backend API:    http://127.0.0.1:8000/docs")
    print("    • Doctor Dash:    http://localhost:5173")
    print("    • Patient App:    http://localhost:8081")

    print("\n  To stop all services, press Ctrl+C in each terminal or run:")
    print("    taskkill /F /IM uvicorn.exe")
    print("    taskkill /F /IM node.exe")

    print("\n  End-to-End Test Flow:")
    print("    1. Open Patient App: http://localhost:8081")
    print("    2. Login: patient@carepilot.ai / demo1234")
    print("    3. Submit consultation query")
    print("    4. Open Doctor Dashboard: http://localhost:5173")
    print("    5. Login: doctor@carepilot.ai / demo1234")
    print("    6. Review, edit, approve consultation")
    print("    7. Verify patient sees 'Doctor Approved' response")

    print(f"\n  Tests passed: {tests_passed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())