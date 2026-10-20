"""Optional speech endpoints for the patient application.

The heavy speech dependencies are loaded only when a voice endpoint is used, so
the core clinical API remains available on installations that do not enable
voice features.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from backend.app.pipeline.stt import transcribe_audio_file
from backend.app.pipeline.tts import get_tts_client

router = APIRouter(prefix="/api/voice", tags=["Voice"])


class SynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5_000)
    voice: str = "en-US-JennyNeural"


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    model_size: str = Form("base"),
) -> dict[str, str]:
    if not (audio.content_type or "").startswith("audio/"):
        raise HTTPException(status_code=415, detail="Upload an audio file.")
    return {"text": await transcribe_audio_file(audio, model_size=model_size)}


@router.post("/synthesize")
async def synthesize_audio(req: SynthesisRequest) -> FileResponse:
    fd, output_path = tempfile.mkstemp(prefix="carepilot_tts_", suffix=".mp3")
    os.close(fd)
    try:
        await get_tts_client(req.voice).synthesize(req.text, output_path)
    except Exception as exc:
        Path(output_path).unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail=f"TTS unavailable: {exc}") from exc
    return FileResponse(
        output_path,
        media_type="audio/mpeg",
        filename="carepilot-response.mp3",
        background=BackgroundTask(Path(output_path).unlink, missing_ok=True),
    )
