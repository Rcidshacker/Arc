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
from watchdog.observers import Observer

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
        update_meeting_status(conn, meeting_id, "processing")

        # ------------------------------------------------------------------
        # Step 0: Normalise to 16kHz mono WAV
        # ------------------------------------------------------------------
        from pipeline.normalizer import normalize_audio  # type: ignore[import]

        wav_path: Path = normalize_audio(audio_path, temp_dir)

        # ------------------------------------------------------------------
        # Step 1: Transcribe with faster-whisper
        # ------------------------------------------------------------------
        from pipeline.transcriber import transcribe  # type: ignore[import]

        segments = transcribe(wav_path)

        # ------------------------------------------------------------------
        # Step 2: Diarise with pyannote.audio
        # ------------------------------------------------------------------
        from pipeline.diarizer import diarize  # type: ignore[import]

        diarization = diarize(wav_path)

        # ------------------------------------------------------------------
        # Step 3: Align transcript segments with diarization turns
        # ------------------------------------------------------------------
        from pipeline.aligner import align_segments  # type: ignore[import]

        aligned = align_segments(segments, diarization)

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
        from pipeline.speaker_db import match_and_embed_speakers  # type: ignore[import]

        unknown_labels: list[str] = match_and_embed_speakers(
            conn, meeting_id, wav_path, aligned
        )

        # ------------------------------------------------------------------
        # Step 5: If unknowns remain, infer names with Gemma then halt
        # ------------------------------------------------------------------
        if unknown_labels:
            from pipeline.name_inferrer import infer_names  # type: ignore[import]

            infer_names(conn, meeting_id, aligned, unknown_labels)
            update_meeting_status(conn, meeting_id, "needs_naming")
            # Halt here — POST /speaker/name will reset status to "uploaded"
            # which triggers the watcher again (or we re-enter via the
            # duplicate-hash guard bypassed check in the watcher handler).
            return

        # ------------------------------------------------------------------
        # Step 6: Generate structured note data
        # ------------------------------------------------------------------
        from pipeline.note_generator import generate_note  # type: ignore[import]

        note_data = generate_note(conn, meeting_id)

        # ------------------------------------------------------------------
        # Step 7: Write to Obsidian vault
        # ------------------------------------------------------------------
        from pipeline.vault_writer import write_vault  # type: ignore[import]

        vault_path = Path(os.environ["OBSIDIAN_VAULT_PATH"])
        meetings_subfolder = os.environ.get("OBSIDIAN_MEETINGS_SUBFOLDER", "Meetings")
        write_vault(conn, meeting_id, note_data, vault_path, meetings_subfolder)

        # ------------------------------------------------------------------
        # Move the normalised WAV to temp/ and mark done
        # ------------------------------------------------------------------
        dest_wav = temp_dir / wav_path.name
        if wav_path.resolve() != dest_wav.resolve():
            shutil.move(str(wav_path), str(dest_wav))

        update_meeting_temp_path(conn, meeting_id, wav_path.name)
        update_meeting_status(conn, meeting_id, "done")

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
    Start a blocking watchdog Observer.
    Intended to be run inside a daemon thread.
    """
    event_handler = AudioFileHandler(db_path=db_path)
    observer = Observer()
    observer.schedule(event_handler, str(intake_dir), recursive=False)
    observer.start()
    print(f"[Arc watcher] Watching {intake_dir}")
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        observer.stop()
    observer.join()


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
