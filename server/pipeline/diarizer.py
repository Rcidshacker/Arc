"""
Arc pipeline — Step 2: Speaker diarization via pyannote.audio 3.x.
Runs AFTER transcription so Whisper has already released its VRAM.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_PIPELINE_ID = "pyannote/speaker-diarization-3.1"


def diarize(audio_path: Path) -> list[dict]:
    """
    Run speaker diarization on *audio_path*.

    Parameters
    ----------
    audio_path:
        Path to a 16 kHz mono WAV file.

    Returns
    -------
    list[dict]
        Each element: ``{"start": float, "end": float, "speaker": str}``
        Segments are sorted by start time.

    Raises
    ------
    KeyError
        If ``HF_TOKEN`` is not set in the environment.
    RuntimeError
        If the pyannote pipeline cannot be loaded or diarization fails.
    """
    try:
        from pyannote.audio import Pipeline  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "pyannote.audio is not installed. "
            "Run: pip install pyannote.audio"
        ) from exc

    hf_token = os.environ["HF_TOKEN"]  # intentional KeyError if absent

    logger.info("Loading pyannote pipeline '%s'", _PIPELINE_ID)
    try:
        pipeline = Pipeline.from_pretrained(
            _PIPELINE_ID,
            use_auth_token=hf_token,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load pyannote pipeline '{_PIPELINE_ID}': {exc}"
        ) from exc

    # Move to GPU if available
    try:
        import torch  # type: ignore[import]
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
            logger.info("Pyannote pipeline moved to CUDA.")
    except ImportError:
        logger.warning("torch not available; pyannote will run on CPU.")

    logger.info("Running diarization on: %s", audio_path)
    try:
        diarization = pipeline(
            str(audio_path),
            max_speakers=8,
        )
    except Exception as exc:
        raise RuntimeError(f"Diarization failed: {exc}") from exc

    segments: list[dict] = []
    for turn, _track, speaker in diarization.itertracks(yield_label=True):
        segments.append(
            {
                "start": float(turn.start),
                "end": float(turn.end),
                "speaker": str(speaker),
            }
        )

    # itertracks is already time-ordered, but sort defensively
    segments.sort(key=lambda s: s["start"])

    logger.info("Diarization produced %d speaker segments.", len(segments))
    return segments
