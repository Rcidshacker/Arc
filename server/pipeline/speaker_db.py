"""
Arc pipeline — Steps 4 & 5: Speaker embedding matching and clip extraction.

For each unique speaker_label in the aligned segments:
  1. Concatenate that speaker's audio from the WAV.
  2. Compute a resemblyzer embedding.
  3. Compare against all stored DB embeddings (cosine similarity).
  4. If best similarity >= 0.75 → resolve the label to the known speaker.
  5. If < 0.75 → speaker is unknown → extract a 10-second clip and report
     the label as unresolved.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_SIMILARITY_THRESHOLD = 0.75
_CLIP_DURATION = 10.0  # seconds


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def match_and_embed_speakers(
    conn: sqlite3.Connection,
    meeting_id: str,
    wav_path: Path,
    aligned_segments: list[dict],
) -> list[str]:
    """
    Identify known speakers, resolve segment labels in DB, extract clips for unknown.

    Parameters
    ----------
    conn:
        Open SQLite connection.
    meeting_id:
        UUID of the meeting being processed.
    wav_path:
        Path to the normalised 16 kHz mono WAV.
    aligned_segments:
        Output of :func:`aligner.align_segments`.

    Returns
    -------
    list[str]
        Speaker labels (e.g. ``"SPEAKER_00"``) that could not be matched to any
        stored embedding.  Clips for these labels are written to the ``clips/``
        directory adjacent to the WAV's parent.
    """
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "resemblyzer is not installed. Run: pip install resemblyzer"
        ) from exc

    encoder = VoiceEncoder()

    # Group segments by speaker label
    label_to_segs: dict[str, list[dict]] = {}
    for seg in aligned_segments:
        label = seg["speaker_label"]
        if label == "UNKNOWN":
            continue
        label_to_segs.setdefault(label, []).append(seg)

    # Load all stored speaker embeddings once
    stored: list[dict] = _load_stored_embeddings(conn)

    clips_dir = wav_path.parent.parent / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    unresolved: list[str] = []

    for label, segs in label_to_segs.items():
        logger.info("Processing speaker label '%s' (%d segments).", label, len(segs))

        speaker_audio = extract_speaker_audio(wav_path, segs)
        if speaker_audio.size == 0:
            logger.warning("No audio extracted for label '%s'; skipping.", label)
            unresolved.append(label)
            continue

        # resemblyzer expects 16 kHz float32 audio
        processed = preprocess_wav(speaker_audio, source_sr=16000)
        embedding: np.ndarray = encoder.embed_utterance(processed)

        best_id, best_sim = _find_best_match(embedding, stored)

        if best_sim >= _SIMILARITY_THRESHOLD and best_id is not None:
            logger.info(
                "Label '%s' matched to speaker_id '%s' (similarity %.3f).",
                label,
                best_id,
                best_sim,
            )
            _resolve_label(conn, meeting_id, label, best_id, embedding)
        else:
            logger.info(
                "Label '%s' unresolved (best similarity %.3f < %.2f). Extracting clip.",
                label,
                best_sim,
                _SIMILARITY_THRESHOLD,
            )
            # Extract a 10-second clip from the first segment for the naming UI
            first_seg = segs[0]
            clip_path = clips_dir / f"{meeting_id}_{label}.wav"
            extract_clip(wav_path, first_seg["start"], clip_path, duration=_CLIP_DURATION)
            unresolved.append(label)

    return unresolved


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_speaker_audio(wav_path: Path, segments: list[dict]) -> np.ndarray:
    """
    Concatenate all audio chunks for one speaker from *wav_path*.

    Parameters
    ----------
    wav_path:
        16 kHz mono WAV.
    segments:
        List of segment dicts with ``start`` and ``end`` keys (seconds).

    Returns
    -------
    np.ndarray
        Concatenated float32 audio samples at 16 kHz.
        Returns an empty array if no valid audio is found.
    """
    try:
        import soundfile as sf  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "soundfile is not installed. Run: pip install soundfile"
        ) from exc

    chunks: list[np.ndarray] = []

    with sf.SoundFile(str(wav_path)) as f:
        sample_rate: int = f.samplerate
        total_frames: int = f.frames

        for seg in segments:
            start_frame = int(seg["start"] * sample_rate)
            end_frame = int(seg["end"] * sample_rate)
            # Clamp to file bounds
            start_frame = max(0, min(start_frame, total_frames))
            end_frame = max(0, min(end_frame, total_frames))
            if end_frame <= start_frame:
                continue

            f.seek(start_frame)
            chunk = f.read(end_frame - start_frame, dtype="float32", always_2d=False)
            if chunk.ndim > 1:
                chunk = chunk[:, 0]  # take first channel (should already be mono)
            chunks.append(chunk)

    if not chunks:
        return np.array([], dtype=np.float32)

    return np.concatenate(chunks, axis=0)


def extract_clip(
    wav_path: Path,
    start: float,
    clip_path: Path,
    duration: float = _CLIP_DURATION,
) -> None:
    """
    Write *duration* seconds of audio starting at *start* seconds to *clip_path*.

    Parameters
    ----------
    wav_path:
        Source 16 kHz mono WAV.
    start:
        Start time in seconds.
    clip_path:
        Destination path for the clip WAV.
    duration:
        Length of the clip in seconds (default 10.0).
    """
    try:
        import soundfile as sf  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "soundfile is not installed. Run: pip install soundfile"
        ) from exc

    clip_path.parent.mkdir(parents=True, exist_ok=True)

    with sf.SoundFile(str(wav_path)) as f:
        sample_rate: int = f.samplerate
        total_frames: int = f.frames
        start_frame = max(0, int(start * sample_rate))
        end_frame = min(total_frames, int((start + duration) * sample_rate))

        if end_frame <= start_frame:
            logger.warning(
                "extract_clip: empty range for start=%.2f, duration=%.2f in %s",
                start,
                duration,
                wav_path,
            )
            return

        f.seek(start_frame)
        audio = f.read(end_frame - start_frame, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio[:, 0]

    with sf.SoundFile(
        str(clip_path),
        mode="w",
        samplerate=sample_rate,
        channels=1,
        format="WAV",
        subtype="PCM_16",
    ) as out:
        out.write(audio)

    logger.info("Clip extracted: %s (%.1f KB)", clip_path, clip_path.stat().st_size / 1024)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Compute cosine similarity between two 1-D float32 vectors.

    Returns 0.0 if either vector has zero norm.
    """
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_stored_embeddings(conn: sqlite3.Connection) -> list[dict]:
    """Return all speaker rows that have a non-empty embedding BLOB."""
    rows = conn.execute(
        "SELECT id, name, embedding FROM speakers WHERE embedding IS NOT NULL"
    ).fetchall()
    result = []
    for row in rows:
        blob = row["embedding"]
        if not blob:
            continue
        try:
            emb = np.frombuffer(blob, dtype=np.float32).copy()
        except Exception:
            logger.warning("Could not deserialise embedding for speaker %s; skipping.", row["id"])
            continue
        result.append({"id": row["id"], "name": row["name"], "embedding": emb})
    return result


def _find_best_match(
    embedding: np.ndarray,
    stored: list[dict],
) -> tuple[str | None, float]:
    """Return (speaker_id, similarity) of the closest stored embedding, or (None, 0.0)."""
    best_id: str | None = None
    best_sim: float = 0.0

    for entry in stored:
        sim = cosine_similarity(embedding, entry["embedding"])
        if sim > best_sim:
            best_sim = sim
            best_id = entry["id"]

    return best_id, best_sim


def _resolve_label(
    conn: sqlite3.Connection,
    meeting_id: str,
    speaker_label: str,
    speaker_id: str,
    embedding: np.ndarray,
) -> None:
    """
    Update transcript segments and link the speaker to the meeting.
    Also refreshes the stored embedding with the new sample (running average
    would require the old count — we just replace with the new one, which is
    the freshest sample).
    """
    from database import (  # type: ignore[import]  # noqa: E402
        resolve_segment_speaker,
        link_speaker_to_meeting,
    )

    resolve_segment_speaker(conn, meeting_id, speaker_label, speaker_id)
    link_speaker_to_meeting(conn, meeting_id, speaker_id)

    # Refresh embedding with latest audio sample
    conn.execute(
        "UPDATE speakers SET embedding = ?, embedding_source_meeting_id = ? WHERE id = ?",
        (embedding.tobytes(), meeting_id, speaker_id),
    )
    conn.commit()
    logger.info("Resolved label '%s' → speaker_id '%s'.", speaker_label, speaker_id)
