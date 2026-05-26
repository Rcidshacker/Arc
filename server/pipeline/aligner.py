"""
Arc pipeline — Step 3: Align Whisper segments with pyannote diarization.
For each Whisper segment, assigns the speaker label with maximum time overlap.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_UNKNOWN = "UNKNOWN"


def align_segments(
    whisper_segments: list[dict],
    diarization_segments: list[dict],
) -> list[dict]:
    """
    Merge Whisper transcription segments with pyannote diarization segments.

    For each Whisper segment the function finds the diarization window that
    overlaps it the most (by seconds) and assigns that speaker label.
    If no diarization window overlaps the segment at all, the label is
    ``"UNKNOWN"``.

    Parameters
    ----------
    whisper_segments:
        Output of :func:`transcriber.transcribe`.
        Each dict: ``{"start": float, "end": float, "text": str, "confidence": float}``
    diarization_segments:
        Output of :func:`diarizer.diarize`.
        Each dict: ``{"start": float, "end": float, "speaker": str}``

    Returns
    -------
    list[dict]
        Each element:
        ``{"start": float, "end": float, "speaker_label": str,
           "text": str, "confidence": float}``
        Preserves the original order of *whisper_segments*.
    """
    if not whisper_segments:
        logger.warning("align_segments called with empty whisper_segments.")
        return []

    if not diarization_segments:
        logger.warning(
            "align_segments called with empty diarization_segments; "
            "all segments will be labelled UNKNOWN."
        )

    aligned: list[dict] = []

    for wseg in whisper_segments:
        w_start: float = wseg["start"]
        w_end: float = wseg["end"]

        best_label: str = _UNKNOWN
        best_overlap: float = 0.0

        for dseg in diarization_segments:
            d_start: float = dseg["start"]
            d_end: float = dseg["end"]

            # Compute intersection length
            overlap_start = max(w_start, d_start)
            overlap_end = min(w_end, d_end)
            overlap = max(0.0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_label = dseg["speaker"]

        aligned.append(
            {
                "start": w_start,
                "end": w_end,
                "speaker_label": best_label,
                "text": wseg["text"],
                "confidence": wseg["confidence"],
            }
        )

    unknown_count = sum(1 for s in aligned if s["speaker_label"] == _UNKNOWN)
    logger.info(
        "Alignment complete: %d segments, %d labelled UNKNOWN.",
        len(aligned),
        unknown_count,
    )
    return aligned
