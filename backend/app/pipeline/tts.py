"""
D:\\CarePilotAI\\backend\\app\\pipeline\\tts.py

Text-to-Speech (TTS) Integration Module
Supports edge-tts (Microsoft Azure voices) and/or coqui TTS.

Public API:
  tts.synthesize(text, output_path) -> None  # generates MP3 file
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

class TTSClient:
    """Edge-TTS wrapper for clinical response synthesis."""

    # Supported voices for clinical English contexts
    SUPPORTED_VOICES = [
        "en-US-JennyNeural",  # Clear, natural, default
        "en-US-SaraNeural",   # Slightly different timbre
        "en-US-GuyNeural",    # Male voice option
    ]

    def __init__(self, voice: str = "en-US-JennyNeural"):
        """
        Initialize TTS client.

        Args:
            voice: Edge-TTS voice name. Must be one of SUPPORTED_VOICES
                   or a valid Edge-TTS voice identifier.
        """
        if voice not in self.SUPPORTED_VOICES:
            print(
                f"Warning: '{voice}' not in default supported voices. "
                f"Using as-is. Supported: {self.SUPPORTED_VOICES}"
            )
        self.voice = voice

    async def synthesize(self, text: str, output_path: str) -> None:
        """
        Synthesize text to speech and save as MP3.

        Args:
            text: The text to convert to speech.
            output_path: Path where the MP3 will be saved (e.g., "response.mp3").

        Raises:
            ValueError: If text is empty or None.
        """
        if not text:
            raise ValueError("Cannot synthesize empty or None text.")

        try:
            import edge_tts
        except ImportError as exc:
            raise RuntimeError("Text-to-speech requires the edge-tts package.") from exc
        communicate = edge_tts.Communicate(text, voice=self.voice)

        # Save to output path
        await communicate.save(output_path)

    @staticmethod
    def list_supported_voices() -> list[str]:
        """Return list of pre-validated supported voices."""
        return TTSClient.SUPPORTED_VOICES[:]


# Global cached instance
_tts_instance: TTSClient | None = None


def get_tts_client(voice: str = "en-US-JennyNeural") -> TTSClient:
    """Return cached TTS client instance."""
    global _tts_instance
    if _tts_instance is None or _tts_instance.voice != voice:
        _tts_instance = TTSClient(voice=voice)
    return _tts_instance


# ---------------------------------------------------------------------------
# Convenience function for sync usage (runs event loop internally)
# ---------------------------------------------------------------------------

def synthesize_text(text: str, output_path: str, voice: str = "en-US-JennyNeural") -> None:
    """
    Synchronous helper: synthesize text to speech.

    Args:
        text: The text to convert.
        output_path: Destination MP3 file path.
        voice: Edge-TTS voice identifier.
    """
    asyncio.run(_synthesize_async(text, output_path, voice))


async def _synthesize_async(text: str, output_path: str, voice: str) -> None:
    client = TTSClient(voice=voice)
    await client.synthesize(text, output_path)
