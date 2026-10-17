"""
D:\\CarePilotAI\\backend\\app\\core\\llm.py

Local LLM loader for Pillar B — local models only.
Engine: Ollama (qwen3:8b, Q4_K_M) per Decision D-002 and Gate 0 benchmark.
Fallback: llama-cpp-python if Ollama is unreachable.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_OLLAMA_MODEL = "qwen3:8b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

_LLM_INSTANCE = None
_LLM_MODEL_NAME: str | None = None


class OllamaClient:
    """Ollama API client implementing the callable LLM interface."""
    def __init__(self, model: str = DEFAULT_OLLAMA_MODEL, base_url: str = DEFAULT_OLLAMA_URL):
        self.model = model
        self.base_url = base_url

    def __call__(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        stop: list[str] | None = None,
    ) -> dict[str, Any]:
        req_data = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "stop": stop or [],
                "seed": 42,
            },
            "think": False,  # disable thinking mode per spec
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(req_data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        return {
            "choices": [{"text": data.get("response", "")}],
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "eval_duration_ns": data.get("eval_duration", 0),
                "total_duration_ns": data.get("total_duration", 0),
            },
        }


def get_llm():
    """Returns the cached local LLM instance (Ollama qwen3:8b)."""
    global _LLM_INSTANCE, _LLM_MODEL_NAME
    if _LLM_INSTANCE is not None:
        return _LLM_INSTANCE

    # Verify Ollama server connectivity
    try:
        req = urllib.request.Request(f"{DEFAULT_OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
        model_names = [m.get("name", "") for m in tags.get("models", [])]
        chosen = DEFAULT_OLLAMA_MODEL if any(DEFAULT_OLLAMA_MODEL in m for m in model_names) else (model_names[0] if model_names else DEFAULT_OLLAMA_MODEL)
        _LLM_INSTANCE = OllamaClient(model=chosen)
        _LLM_MODEL_NAME = chosen
        return _LLM_INSTANCE
    except Exception as exc:
        # Fallback to llama-cpp if GGUF exists
        model_path = PROJECT_ROOT / "backend" / "models" / "qwen3-8b-q4_k_m.gguf"
        if model_path.exists():
            from llama_cpp import Llama  # type: ignore
            _LLM_INSTANCE = Llama(model_path=str(model_path), n_gpu_layers=20, n_ctx=2048, verbose=False)
            _LLM_MODEL_NAME = "qwen3-8b-q4_k_m"
            return _LLM_INSTANCE
        raise RuntimeError(
            f"Ollama server not reachable at {DEFAULT_OLLAMA_URL} and local GGUF not found. "
            f"Start Ollama service ('ollama serve') with '{DEFAULT_OLLAMA_MODEL}' loaded."
        ) from exc


def get_llm_model_name() -> str:
    """Returns the model identifier string for logging to consultations.llm_model."""
    global _LLM_MODEL_NAME
    if not _LLM_MODEL_NAME:
        _LLM_MODEL_NAME = DEFAULT_OLLAMA_MODEL
    return _LLM_MODEL_NAME
