"""
D:\\CarePilotAI\\backend\\app\\pipeline\\stt.py

Speech-to-Text (STT) Integration Module
Supports open-source whisper models and/or cloud STT APIs.

Public API:
  stt.transcribe(audio_path) -> str  # returns normalized text
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

class STTModel:
    """Wrapper for Whisper-based speech recognition."""

    def __init__(self, model_size: str = "base"):
        """
        Initialize Whisper model.

        Args:
            model_size: "tiny", "base", "small", "medium", "large"
                Larger = more accurate but slower/more memory.
                Recommended: "base" or "small" for production.
        """
        try:
            import whisper
        except ImportError as exc:
            raise RuntimeError(
                "Speech-to-text requires openai-whisper and FFmpeg. "
                "Install backend requirements and make FFmpeg available on PATH."
            ) from exc
        self.model_size = model_size
        self.model = whisper.load_model(model_size)

    def transcribe(self, audio_path: str) -> str:
        """
        Transcribe an audio file to text.

        Args:
            audio_path: Path to .wav, .mp3, .m4a, or other supported format.

        Returns:
            Normalized transcript text (stripped, lowercased).
        """
        result = self.model.transcribe(audio_path)
        text = result["text"].strip()
        return text

    def transcribe_with_timestamp(self, audio_path: str) -> dict:
        """
        Full transcription with word-level timestamps.

        Returns dict with 'text', 'segments' (each with 'start', 'end', 'text').
        """
        result = self.model.transcribe(audio_path, without_timestamps=False)
        return result


# Global instance for caching
_stt_instance: STTModel | None = None


def get_stt_model(model_size: str = "base") -> STTModel:
    """Return cached STT model instance."""
    global _stt_instance
    if _stt_instance is None or _stt_instance.model_size != model_size:
        _stt_instance = STTModel(model_size=model_size)
    return _stt_instance


# ---------------------------------------------------------------------------
# FastAPI integration helper
# ---------------------------------------------------------------------------

import asyncio
from fastapi import UploadFile, HTTPException


async def transcribe_audio_file(audio: UploadFile, model_size: str = "base") -> str:
    """
    Convenience endpoint helper: accepts an uploaded audio file,
    saves temp, transcribes, cleans up.

    Returns:
        Transcribed text string.

    Raises:
        HTTPException 400 if transcription fails.
    """
    # Save uploaded file to temp path
    suffix = os.path.splitext(audio.filename or "")[1] or ".wav"
    tmp_path = ""
    try:
        content = await audio.read()
        with tempfile.NamedTemporaryFile(prefix="carepilot_audio_", suffix=suffix, delete=False) as f:
            tmp_path = f.name
            f.write(content)

        # Transcribe
        model = get_stt_model(model_size)
        text = model.transcribe(tmp_path)
        return text
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"STT transcription failed: {e}",
        )
    finally:
        # Clean up temp file
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
