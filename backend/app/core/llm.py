"""
D:\\CarePilotAI\\backend\\app\\core\\llm.py

Local LLM loader for Pillar B — hybrid: Ollama primary, optional NVIDIA API fallback.
Engine: Ollama (qwen3:8b, Q4_K_M) per Decision D-002 and Gate 0 benchmark.
Fallback: NVIDIA integrate/api/completions if Ollama model unavailable or unreachable.
"""
from __future__ import annotations
import json
import urllib.request
from typing import Any

from backend.app.core.settings import settings

DEFAULT_OLLAMA_MODEL = settings.ollama_model
DEFAULT_OLLAMA_URL = settings.ollama_url
NVIDIA_MODEL = settings.nvidia_model
NVIDIA_URL = settings.nvidia_url

_LLM_INSTANCE = None
_LLM_MODEL_NAME: str | None = None
_using_nvidia = False


class OllamaClient:
    """Ollama API client implementing the callable LLM interface."""
    def __init__(self, model: str = DEFAULT_OLLAMA_MODEL, base_url: str = DEFAULT_OLLAMA_URL):
        self.model = model
        self.base_url = base_url

    def __call__(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.1,
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


class NVIDIAClient:
    """NVIDIA API client for cloud LLM fallback.
    Normalizes output to Ollama-format: {"choices": [{"text": "..."}], ...}
    This ensures compatibility with the existing pipeline (generate.py, validate.py)."""
    def __init__(self, api_key: str, model: str = NVIDIA_MODEL):
        if not api_key:
            raise ValueError("NVIDIA_API_KEY is not configured")
        self.api_key = api_key
        self.model = model

    def __call__(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.1,
        stop: list[str] | None = None,
    ) -> dict[str, Any]:
        # The NVIDIA API expects a messages array.
        messages = [
            {"role": "user", "content": prompt}
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if stop:
            payload["stop"] = stop

        req = urllib.request.Request(
            NVIDIA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # NVIDIA format: choices[0].message.content
        # Normalize to Ollama format: choices[0].text
        choices = data.get("choices", [])
        text = ""
        if choices:
            msg = choices[0].get("message", {})
            text = msg.get("content", "")

        return {
            "choices": [{"text": text}],
            "usage": {
                "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("completion_tokens", 0),
                "eval_duration_ns": 0,
                "total_duration_ns": 0,
            },
        }


def get_llm():
    """Returns the LLM instance using the hybrid strategy:
    1. Try Ollama first (primary, local, free, private)
    2. If Ollama model qwen3:8b is unavailable, fall back to NVIDIA API

    Returns:
        LLM client instance (Ollama or NVIDIA)
    """
    global _LLM_INSTANCE, _LLM_MODEL_NAME, _using_nvidia

    if _LLM_INSTANCE is not None:
        return _LLM_INSTANCE

    # Step 1: Try Ollama
    try:
        # Check if Ollama server is reachable
        req = urllib.request.Request(f"{DEFAULT_OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            tags_data = json.loads(resp.read().decode("utf-8"))
        model_names = [m.get("name", "") for m in tags_data.get("models", [])]

        # Check if qwen3:8b is available in Ollama
        has_qwen3 = any(DEFAULT_OLLAMA_MODEL in m for m in model_names)

        if has_qwen3:
            # Ollama server is reachable AND qwen3:8b model is available
            chosen_model = DEFAULT_OLLAMA_MODEL
            _LLM_INSTANCE = OllamaClient(chosen_model)
            _LLM_MODEL_NAME = chosen_model
            _using_nvidia = False
            return _LLM_INSTANCE
        else:
            # Ollama server reachable but qwen3:8b not pulled — fall through to NVIDIA
            raise Exception("Ollama model qwen3:8b not available")

    except Exception as ollama_exc:
        if not settings.nvidia_fallback_enabled or not settings.nvidia_api_key:
            raise RuntimeError(
                f"Ollama is unavailable ({ollama_exc}). NVIDIA fallback is disabled "
                "or NVIDIA_API_KEY is not configured."
            ) from ollama_exc

        # Cloud inference requires an explicit opt-in and a locally configured key.
        try:
            _LLM_INSTANCE = NVIDIAClient(api_key=settings.nvidia_api_key, model=NVIDIA_MODEL)
            _LLM_MODEL_NAME = NVIDIA_MODEL
            _using_nvidia = True
            return _LLM_INSTANCE
        except Exception as nvidia_exc:
            raise RuntimeError(
                f"Ollama is unavailable ({ollama_exc}); NVIDIA fallback could not "
                f"be configured ({nvidia_exc})."
            ) from nvidia_exc


def get_llm_model_name() -> str:
    """Returns the model identifier string for logging to consultations.llm_model."""
    global _LLM_MODEL_NAME
    if not _LLM_MODEL_NAME:
        _LLM_MODEL_NAME = DEFAULT_OLLAMA_MODEL
    return _LLM_MODEL_NAME


def is_using_nvidia() -> bool:
    """Returns True if currently using NVIDIA API fallback (vs local Ollama)."""
    return _using_nvidia
