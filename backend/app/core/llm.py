"""
D:\\CarePilotAI\\backend\\app\\core\\llm.py

LLM loader for Pillar B — local models only.

The model to load is determined by Gate 0 benchmark results recorded in
docs/PILLAR_B_DECISIONS.md. Update LLM_MODEL_PATH and N_GPU_LAYERS
after Gate 0 completes. Do NOT add cloud API fallbacks here without
explicit sign-off (see PILLAR_B_DECISIONS.md D-004).

Usage:
    from backend.app.core.llm import get_llm, get_llm_model_name
    llm = get_llm()
    output = llm(prompt, max_tokens=512, temperature=0.1)
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# *** UPDATE THESE AFTER GATE 0 BENCHMARK ***
# See data/manifests/llm_benchmark_real.json and docs/PILLAR_B_DECISIONS.md
# ---------------------------------------------------------------------------
LLM_MODEL_FILENAME = "qwen3-8b-q4_k_m.gguf"   # ← replace with Gate 0 winner
N_GPU_LAYERS = 20                               # ← tune after measuring VRAM peak
N_CTX = 2048
# ---------------------------------------------------------------------------

_LLM_INSTANCE = None
_LLM_MODEL_NAME: str | None = None


def get_llm():
    """
    Returns a cached llama-cpp-python Llama instance.
    Raises RuntimeError if the GGUF file is not present (run Gate 0 first).
    """
    global _LLM_INSTANCE, _LLM_MODEL_NAME

    if _LLM_INSTANCE is not None:
        return _LLM_INSTANCE

    try:
        from llama_cpp import Llama  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "llama-cpp-python is not installed. "
            "Install with CUDA support: pip install llama-cpp-python[cuda]"
        ) from exc

    model_path = PROJECT_ROOT / "backend" / "models" / LLM_MODEL_FILENAME
    if not model_path.exists():
        raise RuntimeError(
            f"LLM model file not found: {model_path}\n"
            "Run Gate 0 benchmark first:\n"
            "  python -m backend.scripts.benchmark_real_llm\n"
            "Then download the chosen model GGUF to backend/models/ and "
            "update LLM_MODEL_FILENAME in backend/app/core/llm.py"
        )

    _LLM_INSTANCE = Llama(
        model_path=str(model_path),
        n_gpu_layers=N_GPU_LAYERS,
        n_ctx=N_CTX,
        verbose=False,
    )
    _LLM_MODEL_NAME = LLM_MODEL_FILENAME.replace(".gguf", "")
    return _LLM_INSTANCE


def get_llm_model_name() -> str:
    """Returns the model identifier string for logging to consultations.llm_model."""
    if _LLM_MODEL_NAME:
        return _LLM_MODEL_NAME
    return LLM_MODEL_FILENAME.replace(".gguf", "")
