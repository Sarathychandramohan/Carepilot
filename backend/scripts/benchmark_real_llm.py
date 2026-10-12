"""
D:\\CarePilotAI\\backend\\scripts\\benchmark_real_llm.py

Gate 0: Real GGUF LLM Benchmark (Pillar B — Section 3.5)

Benchmarks Qwen3-8B Q4_K_M vs qwen2.5-7B Q4_K_M on the actual RTX 2050 (4 GB VRAM)
using real llama-cpp-python inference (NOT simulated timings).

Measures per model:
  - Tokens/sec (generation throughput)
  - VRAM peak (MB) via nvidia-smi
  - p50 / p95 latency per draft (seconds)
  - JSON-valid rate across 5 clinical prompt templates

Results are written to data/manifests/llm_benchmark_real.json and printed to stdout.
Model choice must be committed to docs/PILLAR_B_DECISIONS.md after reviewing results.

Requirements:
    pip install llama-cpp-python  (compiled with CUDA support for RTX 2050)
    Models must be downloaded to backend/models/ before running.

Usage:
    python -m backend.scripts.benchmark_real_llm
    python -m backend.scripts.benchmark_real_llm --models-dir /path/to/models
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_PATH = PROJECT_ROOT / "data" / "manifests" / "llm_benchmark_real.json"
MODELS_DIR = PROJECT_ROOT / "backend" / "models"

# ---------------------------------------------------------------------------
# 5 clinical prompt templates representative of RQ3 draft tasks
# Each targets ~200 prompt tokens + ~150 response tokens
# ---------------------------------------------------------------------------
CLINICAL_PROMPTS = [
    {
        "id": "T1_lab_creatinine",
        "prompt": (
            "You are a clinical assistant drafting a doctor's response.\n"
            "PATIENT: 62-year-old male, CKD Stage 3, Hypertension.\n"
            "EHR FACT: Serum Creatinine 1.8 mg/dL (↑ above normal 0.6–1.2) on 2023-08-10.\n"
            "KB: Creatinine is a waste product filtered by the kidneys. Rising values indicate reduced filtration.\n"
            "QUERY: 'Why is my creatinine getting higher each visit?'\n"
            "Respond in JSON: {\"sentences\":[{\"text\":\"...\",\"citations\":[\"ehr:lab:123\"]}],\"overall_tone\":\"informative\",\"urgency_assessment\":\"routine\"}"
        ),
    },
    {
        "id": "T2_medication_lisinopril",
        "prompt": (
            "You are a clinical assistant drafting a doctor's response.\n"
            "PATIENT: 55-year-old female, Hypertension, active medication: Lisinopril 10 mg.\n"
            "KB: Lisinopril is an ACE inhibitor. Common side effects include dry cough (~10–15% of patients).\n"
            "QUERY: 'I have a persistent dry cough since starting my blood pressure pill. Is this normal?'\n"
            "Respond in JSON: {\"sentences\":[{\"text\":\"...\",\"citations\":[\"KB-MP0042_chunk_003\"]}],\"overall_tone\":\"reassuring\",\"urgency_assessment\":\"routine\"}"
        ),
    },
    {
        "id": "T3_symptom_urgent",
        "prompt": (
            "You are a clinical assistant drafting a doctor's response.\n"
            "PATIENT: 70-year-old male, Type 2 Diabetes, Hypertension.\n"
            "QUERY: 'I am experiencing severe chest pressure and left arm pain right now.'\n"
            "[URGENT — red flag triggered. Do not downplay severity.]\n"
            "Respond in JSON: {\"sentences\":[{\"text\":\"...\",\"citations\":[]}],\"overall_tone\":\"urgent\",\"urgency_assessment\":\"urgent\"}"
        ),
    },
    {
        "id": "T4_lab_egfr_trend",
        "prompt": (
            "You are a clinical assistant drafting a doctor's response.\n"
            "PATIENT: 68-year-old female, CKD Stage 3b, Diabetes.\n"
            "EHR FACTS:\n"
            "  - eGFR 47 mL/min/1.73m² on 2023-06-01 (↓)\n"
            "  - eGFR 51 mL/min/1.73m² on 2023-02-15\n"
            "KB: An eGFR decline of >5 mL/min/year is considered rapid progression of CKD.\n"
            "QUERY: 'My kidney filtration number dropped again. What does this mean for my treatment?'\n"
            "Respond in JSON: {\"sentences\":[{\"text\":\"...\",\"citations\":[\"ehr:lab:201\",\"ehr:lab:198\"]}],\"overall_tone\":\"informative\",\"urgency_assessment\":\"soon\"}"
        ),
    },
    {
        "id": "T5_general_diet",
        "prompt": (
            "You are a clinical assistant drafting a doctor's response.\n"
            "PATIENT: 58-year-old male, CKD Stage 3, Type 2 Diabetes.\n"
            "KB: A low-sodium, low-potassium diet is recommended for CKD patients. Limiting protein to 0.6–0.8 g/kg/day can slow progression.\n"
            "QUERY: 'What foods should I avoid to protect my kidneys?'\n"
            "Respond in JSON: {\"sentences\":[{\"text\":\"...\",\"citations\":[\"KB-MP0101_chunk_002\"]}],\"overall_tone\":\"informative\",\"urgency_assessment\":\"routine\"}"
        ),
    },
]

# Models to benchmark: (display_name, gguf_filename, n_gpu_layers)
# Adjust n_gpu_layers based on VRAM available per model
MODELS_TO_BENCH = [
    {
        "name": "qwen3-8b-q4_k_m",
        "filename": "qwen3-8b-q4_k_m.gguf",
        "n_gpu_layers": 20,   # adjust after first run based on VRAM headroom
        "n_ctx": 2048,
    },
    {
        "name": "qwen2.5-7b-q4_k_m",
        "filename": "qwen2.5-7b-q4_k_m.gguf",
        "n_gpu_layers": 20,   # adjust after first run
        "n_ctx": 2048,
    },
]


def get_vram_mb() -> int:
    """Query NVIDIA GPU VRAM usage via nvidia-smi."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
        ).strip()
        return int(out.split("\n")[0].strip())
    except Exception:
        return -1  # nvidia-smi not available


def is_valid_json_draft(text: str) -> bool:
    """Check if the LLM output is valid JSON with the expected keys."""
    try:
        obj = json.loads(text.strip())
        return (
            isinstance(obj, dict)
            and "sentences" in obj
            and isinstance(obj["sentences"], list)
            and "urgency_assessment" in obj
        )
    except (json.JSONDecodeError, ValueError):
        return False


def benchmark_model(model_cfg: dict[str, Any], models_dir: Path) -> dict[str, Any]:
    """Run all 5 clinical prompts through a single model and return metrics."""
    try:
        from llama_cpp import Llama  # type: ignore
    except ImportError:
        print("[ERROR] llama-cpp-python is not installed.")
        print("  Install with CUDA support: pip install llama-cpp-python[cuda]")
        sys.exit(1)

    model_path = models_dir / model_cfg["filename"]
    if not model_path.exists():
        return {
            "error": f"Model file not found: {model_path}",
            "status": "SKIP",
        }

    print(f"\n  Loading {model_cfg['name']} from {model_path.name} ...")
    vram_before = get_vram_mb()

    llm = Llama(
        model_path=str(model_path),
        n_gpu_layers=model_cfg["n_gpu_layers"],
        n_ctx=model_cfg["n_ctx"],
        verbose=False,
    )

    vram_after_load = get_vram_mb()
    vram_model_mb = max(0, vram_after_load - vram_before) if vram_before >= 0 else -1

    latencies: list[float] = []
    tokens_per_sec_list: list[float] = []
    json_valid_count = 0

    for prompt_cfg in CLINICAL_PROMPTS:
        print(f"    Prompt {prompt_cfg['id']} ...", end=" ", flush=True)
        t0 = time.perf_counter()

        output = llm(
            prompt_cfg["prompt"],
            max_tokens=256,
            temperature=0.0,
            stop=["}\n\n", "\n\n\n"],
        )

        elapsed = time.perf_counter() - t0
        latencies.append(elapsed)

        completion = output["choices"][0]["text"]
        tok_count = output["usage"]["completion_tokens"]
        tps = tok_count / elapsed if elapsed > 0 else 0
        tokens_per_sec_list.append(tps)

        valid = is_valid_json_draft(completion)
        if valid:
            json_valid_count += 1

        print(f"{elapsed:.1f}s | {tps:.1f} tok/s | JSON={'OK' if valid else 'FAIL'}")

    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2]
    p95_idx = int(len(latencies_sorted) * 0.95)
    p95 = latencies_sorted[min(p95_idx, len(latencies_sorted) - 1)]
    avg_tps = sum(tokens_per_sec_list) / len(tokens_per_sec_list)

    vram_peak = get_vram_mb()

    return {
        "status": "OK",
        "model_file": model_cfg["filename"],
        "n_gpu_layers": model_cfg["n_gpu_layers"],
        "n_ctx": model_cfg["n_ctx"],
        "vram_model_load_mb": vram_model_mb,
        "vram_peak_inference_mb": max(0, vram_peak - vram_before) if vram_before >= 0 else -1,
        "avg_tokens_per_sec": round(avg_tps, 1),
        "latency_p50_sec": round(p50, 2),
        "latency_p95_sec": round(p95, 2),
        "json_valid_rate": round(json_valid_count / len(CLINICAL_PROMPTS), 2),
        "prompts_run": len(CLINICAL_PROMPTS),
        "note": (
            "Real measured values. Set n_gpu_layers to maximise GPU offload "
            "without exceeding 3800 MB VRAM (4 GB card — leave ~200 MB headroom)."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Gate 0: Real LLM Benchmark")
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=MODELS_DIR,
        help=f"Directory containing GGUF files (default: {MODELS_DIR})",
    )
    args = parser.parse_args()

    models_dir: Path = args.models_dir
    models_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("CarePilot AI — Gate 0: Real LLM Benchmark")
    print(f"Models dir: {models_dir}")
    print("=" * 60)

    results: dict[str, Any] = {
        "gate": "Gate 0",
        "hardware_note": "RTX 2050 4 GB VRAM — benchmark with real GGUF files",
        "models": {},
    }

    for model_cfg in MODELS_TO_BENCH:
        print(f"\nBenchmarking: {model_cfg['name']}")
        result = benchmark_model(model_cfg, models_dir)
        results["models"][model_cfg["name"]] = result

        if result.get("status") == "SKIP":
            print(f"  [SKIP] {result['error']}")
            print(f"  → Download {model_cfg['filename']} to {models_dir} and re-run.")

    # Decision guidance
    print("\n" + "=" * 60)
    print("BENCHMARK COMPLETE — DECISION REQUIRED")
    print("=" * 60)
    print("Compare results above, then update docs/PILLAR_B_DECISIONS.md with:")
    print("  1. Chosen model (name, quantization)")
    print("  2. Confirmed n_gpu_layers setting")
    print("  3. Measured p50 latency (this replaces the old simulated 6.3s figure)")
    print("  4. Rationale for the choice")
    print()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"[OK] Results saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
