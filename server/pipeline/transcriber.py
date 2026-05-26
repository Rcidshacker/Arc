"""
Arc pipeline — Step 1: Transcription via faster-whisper.
Returns word-level-confidence segment dicts; word timestamps are NOT requested
(segment level only) to stay within VRAM budget on the RTX 4050.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def transcribe(audio_path: Path) -> list[dict]:
    """
    Transcribe *audio_path* with faster-whisper.

    Parameters
    ----------
    audio_path:
        Path to a 16 kHz mono WAV file (output of normalizer.normalize_audio).

    Returns
    -------
    list[dict]
        Each element has keys:
        ``{"start": float, "end": float, "text": str, "confidence": float}``
        where *confidence* is the mean word probability for the segment,
        or 0.9 when word probabilities are unavailable.

    Raises
    ------
    RuntimeError
        If faster-whisper cannot load the model or transcription fails.
    """
    # Import here so the module is importable even if faster_whisper is absent
    # (unit-test mocking convenience).
    try:
        from faster_whisper import WhisperModel  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. "
            "Run: pip install faster-whisper"
        ) from exc

    model_name: str = os.environ.get("WHISPER_MODEL", "large-v3")
    device: str = os.environ.get("WHISPER_DEVICE", "cuda")

    logger.info(
        "Loading faster-whisper model '%s' on device '%s'", model_name, device
    )

    try:
        model = WhisperModel(
            model_name,
            device=device,
            compute_type="float16" if device == "cuda" else "int8",
        )
    except Exception as exc:
        if device == "cuda":
            logger.warning(
                "CUDA model load failed (%s); retrying on CPU.", exc
            )
            try:
                model = WhisperModel(model_name, device="cpu", compute_type="int8")
            except Exception as cpu_exc:
                raise RuntimeError(
                    f"faster-whisper model load failed on both CUDA and CPU: {cpu_exc}"
                ) from cpu_exc
        else:
            raise RuntimeError(
                f"faster-whisper model load failed: {exc}"
            ) from exc

    logger.info("Transcribing: %s", audio_path)

    try:
        segments_iter, info = model.transcribe(
            str(audio_path),
            language=None,                       # auto-detect
            language_detection_threshold=0.5,
            vad_filter=True,                     # filter silence
            word_timestamps=False,               # segment level only
        )
    except Exception as exc:
        raise RuntimeError(f"Transcription failed: {exc}") from exc

    logger.info(
        "Detected language '%s' (probability %.2f)",
        info.language,
        info.language_probability,
    )

    results: list[dict] = []
    for seg in segments_iter:
        # Compute average word probability when available
        if seg.words:
            confidence = float(
                sum(w.probability for w in seg.words) / len(seg.words)
            )
        else:
            confidence = 0.9

        results.append(
            {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text.strip(),
                "confidence": confidence,
            }
        )

    logger.info("Transcription produced %d segments.", len(results))
    return results
