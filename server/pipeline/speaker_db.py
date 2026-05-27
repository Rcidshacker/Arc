"""
Arc pipeline — Step 4: Speaker identification.

MVP: skip embedding/matching entirely. Every diarized speaker label is treated
as unknown and sent to the naming UI. Cross-session speaker matching is v2.
"""

from __future__ import annotations

import logging
import sqlite3
import subprocess
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_CLIP_DURATION = 10.0  # seconds


def match_and_embed_speakers(
    conn: sqlite3.Connection,
    meeting_id: str,
    wav_path: Path,
    aligned_segments: list[dict],
) -> list[str]:
    """
    MVP: return all unique speaker labels as unknown (no embedding/matching).
    Extracts a 10s clip per label so the naming UI can play audio.
    """
    label_to_first_seg: dict[str, dict] = {}
    for seg in aligned_segments:
        label = seg.get("speaker_label", "UNKNOWN")
        if label == "UNKNOWN":
            continue
        if label not in label_to_first_seg:
            label_to_first_seg[label] = seg

    clips_dir = wav_path.parent.parent / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    for label, first_seg in label_to_first_seg.items():
        clip_path = clips_dir / f"{meeting_id}_{label}.wav"
        extract_clip(wav_path, first_seg["start"], clip_path, duration=_CLIP_DURATION)
        logger.info("Clip extracted for label '%s': %s", label, clip_path)

    unknown_labels = list(label_to_first_seg.keys())
    logger.info("Returning %d speaker labels as unknown (MVP).", len(unknown_labels))
    return unknown_labels


def extract_clip(
    wav_path: Path,
    start: float,
    clip_path: Path,
    duration: float = _CLIP_DURATION,
) -> None:
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-t", str(duration),
        "-i", str(wav_path),
        "-ar", "16000", "-ac", "1",
        str(clip_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, shell=False)
    except subprocess.CalledProcessError as exc:
        logger.warning("ffmpeg clip extraction failed for %s: %s", clip_path.name, exc.stderr)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
