"""
voice_pipeline.py — Local Voice I/O

STT: Whisper large-v3-turbo (via faster-whisper — 8× faster than openai-whisper)
TTS: Kokoro-82M (higher quality than Piper, still fully local)
Wake word: openWakeWord (sub-50ms, CPU-only)

All processing is local. No audio leaves the device.
"""

import asyncio
import io
import logging
from pathlib import Path

log = logging.getLogger("ai-os.voice")


async def transcribe(audio_bytes: bytes, cfg: dict) -> str:
    """
    Transcribe audio bytes to text using faster-whisper.
    Audio format: 16kHz mono PCM (WAV or raw).
    """
    model_size = cfg.get("voice", {}).get("stt_model", "large-v3-turbo")
    device     = cfg.get("voice", {}).get("stt_device", "cpu")
    compute    = cfg.get("voice", {}).get("stt_compute", "int8")

    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(model_size, device=device, compute_type=compute)

        # faster-whisper needs a file-like object
        audio_io = io.BytesIO(audio_bytes)
        segments, info = model.transcribe(
            audio_io,
            language=cfg.get("voice", {}).get("language", "en"),
            vad_filter=True,           # suppress silence
            beam_size=5,
        )
        text = " ".join(s.text.strip() for s in segments)
        log.debug(f"[stt] Transcribed: {text[:80]}")
        return text.strip()

    except ImportError:
        log.error("[stt] faster-whisper not installed. pip install faster-whisper")
        return ""
    except Exception as e:
        log.error(f"[stt] Transcription error: {e}")
        return ""


async def speak(text: str, cfg: dict):
    """
    Synthesize and play speech using Kokoro-82M.
    Falls back to Piper if Kokoro isn't available.
    """
    try:
        await _speak_kokoro(text, cfg)
    except Exception:
        await _speak_piper(text, cfg)


async def _speak_kokoro(text: str, cfg: dict):
    try:
        import kokoro
        import sounddevice as sd
        import numpy as np

        model_path = cfg.get("voice", {}).get("tts_model_path", "kokoro-v0_19.pth")
        voice      = cfg.get("voice", {}).get("tts_voice", "af")

        pipeline = kokoro.KPipeline(lang_code="a")
        audio_data = []
        for _, _, audio in pipeline(text, voice=voice, speed=1.0):
            audio_data.append(audio)

        if audio_data:
            import numpy as np
            combined = np.concatenate(audio_data)
            sd.play(combined, samplerate=24000, blocking=True)

    except ImportError:
        raise  # trigger fallback to Piper


async def _speak_piper(text: str, cfg: dict):
    try:
        import subprocess
        piper_model = cfg.get("voice", {}).get("piper_model", "en_US-amy-medium.onnx")
        proc = await asyncio.create_subprocess_exec(
            "piper",
            "--model", piper_model,
            "--output-raw",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate(input=text.encode())
        # Pipe raw PCM to aplay
        aplay = await asyncio.create_subprocess_exec(
            "aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-",
            stdin=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await aplay.communicate(input=stdout)
    except Exception as e:
        log.error(f"[tts] Piper fallback failed: {e}")
