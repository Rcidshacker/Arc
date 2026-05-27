"""
Arc – watcher.py
Watches ARC_INTAKE_DIR for new audio files and runs the full processing
pipeline on each one. Designed to run as a daemon thread launched by main.py.
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from typing import Optional

from watchdog.events import FileCreatedEvent, FileSystemEventHandler

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {".m4a", ".aac", ".mp3", ".mp4", ".webm", ".wav", ".ogg", ".opus", ".flac"}
)

# How long to wait after a file appears before treating it as fully written
SETTLE_DELAY_SECONDS: float = 0.5


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def _run_note_and_vault(conn, meeting_id: str, db_path: Path) -> None:
    """
    Run only note_generator + vault_writer for a meeting whose segments are
    already in the DB and all speakers are resolved. Used by the fast-path
    skip when the pipeline resumes after speaker naming.
    """
    import os
    import sqlite3

    from dotenv import load_dotenv
    load_dotenv()

    from database import update_meeting_status, update_meeting_temp_path

    try:
        print(f"[ARC] note_generator started (fast-path)", flush=True)
        from pipeline.note_generator import generate_note  # type: ignore[import]

        note_data = generate_note(conn, meeting_id)
        print(f"[ARC] note_generator done", flush=True)

        print(f"[ARC] vault_writer started (fast-path)", flush=True)
        from pipeline.vault_writer import write_vault  # type: ignore[import]

        vault_path = Path(os.environ["OBSIDIAN_VAULT_PATH"])
        meetings_subfolder = os.environ.get("OBSIDIAN_MEETINGS_SUBFOLDER", "Meetings")
        write_vault(conn, meeting_id, note_data, vault_path, meetings_subfolder)
        print(f"[ARC] vault_writer done", flush=True)

        update_meeting_status(conn, meeting_id, "done")
        print(f"[ARC] pipeline DONE (fast-path) -> status=done", flush=True)

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print(f"[Arc watcher] ERROR in fast-path note+vault: {error_msg}", file=sys.stderr)
        update_meeting_status(conn, meeting_id, "error", error_message=error_msg)


def _run_pipeline(audio_path: Path, meeting_id: str, db_path: Path) -> None:
    """
    Execute the full processing pipeline for a single audio file.
    All steps are imported inline so that heavy ML models are loaded only
    when a file actually arrives (not at watcher startup).
    """
    # Resolve temp dir from environment (same as main.py)
    import os

    from dotenv import load_dotenv

    load_dotenv()

    temp_dir = Path(os.environ["ARC_TEMP_DIR"])
    temp_dir.mkdir(parents=True, exist_ok=True)

    from database import (
        get_db,
        get_segments,
        get_unknown_speaker_labels,
        save_segment,
        update_meeting_status,
        update_meeting_temp_path,
    )

    conn = get_db(db_path)

    try:
        row = conn.execute(
            "SELECT status FROM meetings WHERE id = ?", (meeting_id,)
        ).fetchone()
        if row and row["status"] == "processing":
            print(f"[Arc watcher] Skipping {audio_path.name}: already processing.")
            return

        update_meeting_status(conn, meeting_id, "processing")

        # Fast-path: if segments already exist and all speakers are resolved,
        # the pipeline already completed steps 0–4. Jump straight to note_generator.
        existing_segs = get_segments(conn, meeting_id)
        unknown_labels_check = get_unknown_speaker_labels(conn, meeting_id)
        if existing_segs and not unknown_labels_check:
            print(f"[ARC] Fast-path: {len(existing_segs)} segments found, all speakers resolved — skipping to note_generator.", flush=True)
            _run_note_and_vault(conn, meeting_id, db_path)
            return

        # ------------------------------------------------------------------
        # Step 0: Normalise to 16kHz mono WAV
        # ------------------------------------------------------------------
        print(f"[ARC] normalize started", flush=True)
        from pipeline.normalizer import normalize_audio  # type: ignore[import]

        wav_path: Path = normalize_audio(audio_path, temp_dir)
        print(f"[ARC] normalize done -> {wav_path.name}", flush=True)

        # ------------------------------------------------------------------
        # Step 1: Transcribe with faster-whisper
        # ------------------------------------------------------------------
        print(f"[ARC] transcribe started", flush=True)
        from pipeline.transcriber import transcribe  # type: ignore[import]

        segments = transcribe(wav_path)
        print(f"[ARC] transcribe done -> {len(segments)} segments", flush=True)

        # ------------------------------------------------------------------
        # Step 2: Diarise with pyannote.audio
        # ------------------------------------------------------------------
        print(f"[ARC] diarize started", flush=True)
        from pipeline.diarizer import diarize  # type: ignore[import]

        diarization = diarize(wav_path)
        print(f"[ARC] diarize done -> {len(diarization)} turns", flush=True)

        # ------------------------------------------------------------------
        # Step 3: Align transcript segments with diarization turns
        # ------------------------------------------------------------------
        print(f"[ARC] align started", flush=True)
        from pipeline.aligner import align_segments  # type: ignore[import]

        aligned = align_segments(segments, diarization)
        print(f"[ARC] align done -> {len(aligned)} aligned segments", flush=True)

        # ------------------------------------------------------------------
        # Persist aligned segments to DB
        # ------------------------------------------------------------------
        for seg in aligned:
            save_segment(
                conn,
                meeting_id=meeting_id,
                speaker_label=seg.get("speaker_label", "UNKNOWN"),
                start=seg["start"],
                end=seg["end"],
                text=seg["text"],
                confidence=seg.get("confidence"),
                speaker_id=None,  # resolved in step 4
            )

        # ------------------------------------------------------------------
        # Step 4: Match / embed speakers via resemblyzer
        # ------------------------------------------------------------------
        print(f"[ARC] speaker_db started", flush=True)
        from pipeline.speaker_db import match_and_embed_speakers  # type: ignore[import]

        unknown_labels: list[str] = match_and_embed_speakers(
            conn, meeting_id, wav_path, aligned
        )
        print(f"[ARC] speaker_db done -> {len(unknown_labels)} unknown labels", flush=True)

        # ------------------------------------------------------------------
        # Step 5: If unknowns remain, halt for manual naming via web UI
        # ------------------------------------------------------------------
        if unknown_labels:
            update_meeting_status(conn, meeting_id, "needs_naming")
            print(f"[ARC] needs_naming -> unknown labels: {unknown_labels}", flush=True)
            # Halt here — POST /speaker/name will reset status to "uploaded"
            # which triggers the watcher again.
            return

        # ------------------------------------------------------------------
        # Step 6: Generate structured note data
        # ------------------------------------------------------------------
        print(f"[ARC] note_generator started", flush=True)
        from pipeline.note_generator import generate_note  # type: ignore[import]

        note_data = generate_note(conn, meeting_id)
        print(f"[ARC] note_generator done", flush=True)

        # ------------------------------------------------------------------
        # Step 7: Write to Obsidian vault
        # ------------------------------------------------------------------
        print(f"[ARC] vault_writer started", flush=True)
        from pipeline.vault_writer import write_vault  # type: ignore[import]

        vault_path = Path(os.environ["OBSIDIAN_VAULT_PATH"])
        meetings_subfolder = os.environ.get("OBSIDIAN_MEETINGS_SUBFOLDER", "Meetings")
        write_vault(conn, meeting_id, note_data, vault_path, meetings_subfolder)
        print(f"[ARC] vault_writer done", flush=True)

        # ------------------------------------------------------------------
        # Move the normalised WAV to temp/ and mark done
        # ------------------------------------------------------------------
        dest_wav = temp_dir / wav_path.name
        if wav_path.resolve() != dest_wav.resolve():
            shutil.move(str(wav_path), str(dest_wav))

        update_meeting_temp_path(conn, meeting_id, wav_path.name)
        update_meeting_status(conn, meeting_id, "done")
        print(f"[ARC] pipeline DONE -> status=done", flush=True)

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print(f"[Arc watcher] ERROR processing {audio_path.name}: {error_msg}",
              file=sys.stderr)
        try:
            from database import update_meeting_status as _ums  # already imported above
            _ums(conn, meeting_id, "error", error_message=error_msg)
        except Exception:
            pass  # DB may itself be broken; nothing we can do
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Watchdog event handler
# ---------------------------------------------------------------------------

class AudioFileHandler(FileSystemEventHandler):
    """Reacts to FileCreatedEvent events in the intake directory."""

    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self._db_path = db_path

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if file_path.suffix.lower() not in AUDIO_EXTENSIONS:
            return

        # Give the OS time to finish writing the file
        time.sleep(SETTLE_DELAY_SECONDS)

        # Wait a little longer if the file is still being written
        # (size must be stable across two consecutive checks)
        self._wait_for_stable_size(file_path)

        meeting_id = self._find_meeting_id(file_path)
        if not meeting_id:
            print(
                f"[Arc watcher] WARNING: no meeting record found for {file_path.name}; skipping.",
                file=sys.stderr,
            )
            return

        print(f"[Arc watcher] Processing: {file_path.name}  meeting={meeting_id}")
        _run_pipeline(file_path, meeting_id, self._db_path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _wait_for_stable_size(path: Path, checks: int = 3, interval: float = 0.2) -> None:
        """Poll until the file size stops changing (max ~1s extra wait)."""
        prev_size: Optional[int] = None
        stable_count = 0
        for _ in range(checks * 5):  # up to ~5s total
            try:
                current_size = path.stat().st_size
            except FileNotFoundError:
                time.sleep(interval)
                continue
            if current_size == prev_size:
                stable_count += 1
                if stable_count >= checks:
                    return
            else:
                stable_count = 0
            prev_size = current_size
            time.sleep(interval)

    def _find_meeting_id(self, audio_path: Path) -> Optional[str]:
        """Look up the meeting_id by matching the stored audio_path."""
        from database import get_db  # avoid circular at module level

        conn = get_db(self._db_path)
        try:
            row = conn.execute(
                "SELECT id FROM meetings WHERE audio_path = ? LIMIT 1",
                (str(audio_path),),
            ).fetchone()
            if row:
                return row["id"]

            # Fallback: match by filename stem (handles edge cases)
            row = conn.execute(
                "SELECT id FROM meetings WHERE audio_path LIKE ? LIMIT 1",
                (f"%{audio_path.name}",),
            ).fetchone()
            return row["id"] if row else None
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def run_pipeline_for_meeting(meeting_id: str, audio_path: Path, db_path: Path) -> None:
    """
    Directly trigger the pipeline for a meeting whose file is already in intake/.
    Called by main.py after /speaker/name resolves unknown speakers, since no
    new FileCreatedEvent fires for a file already present on disk.
    """
    _run_pipeline(audio_path, meeting_id, db_path)


def start_observer(intake_dir: Path, db_path: Path) -> None:
    """
    Poll intake_dir every 2 s for new audio files.
    Pure-Python loop — avoids watchdog's BaseThread which breaks on Python 3.13.
    """
    event_handler = AudioFileHandler(db_path=db_path)
    seen: set[Path] = set()
    print(f"[Arc watcher] Watching {intake_dir} (polling, 2s interval)")
    while True:
        try:
            for f in intake_dir.iterdir():
                if f not in seen and f.suffix.lower() in AUDIO_EXTENSIONS:
                    seen.add(f)
                    event_handler.on_created(FileCreatedEvent(str(f)))
        except Exception as exc:
            print(f"[Arc watcher] poll error: {exc}")
        time.sleep(2)


# ---------------------------------------------------------------------------
# CLI entry point (for standalone testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()

    _intake = Path(os.environ["ARC_INTAKE_DIR"])
    _db = Path(os.environ["ARC_DB_PATH"])
    start_observer(_intake, _db)
