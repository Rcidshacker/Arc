"""
Arc pipeline — Step 1: Transcription with provider selection.

  TRANSCRIPTION_PROVIDER=llamacpp  →  local llama-server (default, no cost)
  TRANSCRIPTION_PROVIDER=groq      →  Groq whisper-large-v3-turbo (<20 MB)
  TRANSCRIPTION_PROVIDER=gemini    →  Gemini 2.5 Flash Files API (>=20 MB)

All paths return identical segment format so aligner.py is unchanged.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_GROQ_SIZE_LIMIT_BYTES = 20 * 1024 * 1024  # 20 MB


def transcribe(audio_path: Path) -> list[dict]:
    """
    Transcribe *audio_path*, selecting provider via TRANSCRIPTION_PROVIDER env var.

    Parameters
    ----------
    audio_path:
        Path to a 16 kHz mono WAV file (output of normalizer.normalize_audio).

    Returns
    -------
    list[dict]
        Each element: ``{"start": float, "end": float, "text": str, "confidence": float}``

    Raises
    ------
    RuntimeError
        If the provider call fails or an unknown provider is specified.
    """
    provider = os.environ.get("TRANSCRIPTION_PROVIDER", "llamacpp").lower()

    if provider == "llamacpp":
        file_size = audio_path.stat().st_size
        print(f"[ARC] transcribe via llamacpp ({file_size / 1024 / 1024:.1f} MB)", flush=True)
        return _transcribe_llamacpp(audio_path)
    elif provider == "groq":
        file_size = audio_path.stat().st_size
        print(f"[ARC] transcribe via groq ({file_size / 1024 / 1024:.1f} MB)", flush=True)
        return _transcribe_groq(audio_path)
    elif provider == "gemini":
        file_size = audio_path.stat().st_size
        print(f"[ARC] transcribe via gemini ({file_size / 1024 / 1024:.1f} MB)", flush=True)
        return _transcribe_gemini(audio_path)
    else:
        raise RuntimeError(
            f"Unknown TRANSCRIPTION_PROVIDER={provider!r}. "
            "Valid values: llamacpp, groq, gemini"
        )


# ---------------------------------------------------------------------------
# whisper-cli.exe provider (local subprocess — the proven working pattern)
# ---------------------------------------------------------------------------

def _get_audio_duration(audio_path: Path) -> float:
    """Return audio duration in seconds via ffprobe. Returns 0.0 on failure."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except Exception as exc:
        logger.warning("ffprobe duration check failed: %s — defaulting to 0.0", exc)
        return 0.0


def _transcribe_llamacpp(audio_path: Path) -> list[dict]:
    whisper_cli = os.environ.get(
        "WHISPER_CLI_PATH", r"C:\llama\whisper\whisper-cli.exe"
    )
    model_path = os.environ.get(
        "WHISPER_MODEL_PATH", r"C:\llama\whisper\models\ggml-large-v3-turbo.bin"
    )
    language = os.environ.get("WHISPER_LANGUAGE", "hi")

    duration = _get_audio_duration(audio_path)

    # whisper-cli.exe writes <audio_path>.txt alongside the input file
    txt_path = Path(str(audio_path) + ".txt")
    if txt_path.exists():
        txt_path.unlink()

    cmd = [
        whisper_cli,
        "-m", model_path,
        "-f", str(audio_path),
        "-otxt",
        "-l", language,
    ]

    logger.info("whisper-cli: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, shell=False)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"whisper-cli.exe failed (exit {exc.returncode}):\n{exc.stderr}"
        ) from exc

    if not txt_path.exists():
        raise RuntimeError(
            f"whisper-cli.exe ran but did not produce output file: {txt_path}"
        )

    try:
        transcript = txt_path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception as exc:
        raise RuntimeError(f"Failed to read whisper output {txt_path}: {exc}") from exc

    logger.info("whisper-cli produced transcript (%d chars).", len(transcript))
    return [
        {
            "start": 0.0,
            "end": duration,
            "text": transcript,
            "confidence": 1.0,
        }
    ]


# ---------------------------------------------------------------------------
# Groq provider
# ---------------------------------------------------------------------------

def _transcribe_groq(audio_path: Path) -> list[dict]:
    try:
        from groq import Groq  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError("groq is not installed. Run: pip install groq") from exc

    api_key = os.environ["GROQ_API_KEY"]
    client = Groq(api_key=api_key)

    logger.info("Groq whisper-large-v3-turbo: %s", audio_path)
    try:
        with open(audio_path, "rb") as f:
            response = client.audio.transcriptions.create(
                file=(audio_path.name, f),
                model="whisper-large-v3-turbo",
                language="hi",
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
    except Exception as exc:
        raise RuntimeError(f"Groq transcription failed: {exc}") from exc

    results: list[dict] = []
    for seg in response.segments or []:
        if isinstance(seg, dict):
            results.append({
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "text": seg["text"].strip(),
                "confidence": float(seg.get("avg_logprob", 0.0)),
            })
        else:
            results.append({
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text.strip(),
                "confidence": float(getattr(seg, "avg_logprob", 0.0)),
            })

    logger.info("Groq produced %d segments.", len(results))
    return results


# ---------------------------------------------------------------------------
# Gemini provider
# ---------------------------------------------------------------------------

_GEMINI_MODEL = "gemini-2.5-flash"
_GEMINI_PROMPT = (
    "Transcribe this audio exactly as spoken, including both Hindi and English words. "
    "Return ONLY a JSON array. No other text, no markdown fences.\n"
    'Format: [{"start": 0.0, "end": 5.2, "text": "..."}, ...]'
)


def _transcribe_gemini(audio_path: Path) -> list[dict]:
    try:
        from google import genai  # type: ignore[import]
        from google.genai import types as genai_types  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "google-genai is not installed. Run: pip install google-genai"
        ) from exc

    api_key = os.environ["GOOGLE_API_KEY"]
    client = genai.Client(api_key=api_key)

    logger.info("Gemini %s Files API: %s", _GEMINI_MODEL, audio_path)

    # Upload via Files API
    uploaded_file = None
    try:
        uploaded_file = client.files.upload(
            file=str(audio_path),
            config=genai_types.UploadFileConfig(mime_type="audio/wav"),
        )
        logger.info("Uploaded file: %s", uploaded_file.name)

        # Wait for file to be ACTIVE (may take a few seconds)
        for _ in range(30):
            f = client.files.get(name=uploaded_file.name)
            if f.state and f.state.name == "ACTIVE":
                break
            time.sleep(2)
        else:
            raise RuntimeError("Gemini file upload never became ACTIVE.")

        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=[
                genai_types.Part.from_uri(
                    file_uri=uploaded_file.uri,
                    mime_type="audio/wav",
                ),
                _GEMINI_PROMPT,
            ],
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini transcription failed: {exc}") from exc
    finally:
        if uploaded_file is not None:
            try:
                client.files.delete(name=uploaded_file.name)
                logger.info("Deleted uploaded file: %s", uploaded_file.name)
            except Exception:
                pass  # non-fatal

    raw = response.text or ""
    segments = _parse_gemini_segments(raw)
    logger.info("Gemini produced %d segments.", len(segments))
    return segments


def _parse_gemini_segments(raw: str) -> list[dict]:
    # Strip markdown fences if Gemini disobeys the prompt
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        raise RuntimeError(f"Gemini returned no JSON array. Response: {cleaned[:300]!r}")

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini JSON parse error: {exc}. Raw: {cleaned[:300]!r}") from exc

    results: list[dict] = []
    for seg in parsed:
        results.append({
            "start": float(seg.get("start", 0.0)),
            "end": float(seg.get("end", 0.0)),
            "text": str(seg.get("text", "")).strip(),
            "confidence": 1.0,
        })
    return results
