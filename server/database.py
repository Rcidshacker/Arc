"""
Arc – database.py
SQLite layer (WAL mode). All primary keys are UUID v4 strings.
All public functions accept an open sqlite3.Connection so callers control
transaction boundaries.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

def get_db(db_path: Path) -> sqlite3.Connection:
    """Return an open SQLite connection with WAL mode and row_factory set."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    sha256_hash TEXT UNIQUE NOT NULL,
    upload_time TEXT NOT NULL,
    duration_seconds INTEGER,
    audio_path TEXT NOT NULL,
    temp_path TEXT,
    obsidian_note_path TEXT,
    status TEXT NOT NULL DEFAULT 'uploaded',
    audio_deleted INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS speakers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    suggested_name TEXT,
    embedding BLOB NOT NULL,
    embedding_source_meeting_id TEXT REFERENCES meetings(id),
    first_seen TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meeting_speakers (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id),
    speaker_id TEXT NOT NULL REFERENCES speakers(id),
    total_speaking_seconds INTEGER,
    segment_count INTEGER
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id),
    speaker_id TEXT REFERENCES speakers(id),
    speaker_label TEXT,
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    text TEXT NOT NULL,
    confidence REAL
);

CREATE TABLE IF NOT EXISTS upload_log (
    id TEXT PRIMARY KEY,
    sha256_hash TEXT NOT NULL,
    filename TEXT NOT NULL,
    upload_time TEXT NOT NULL,
    accepted INTEGER NOT NULL,
    rejection_reason TEXT
);

CREATE TABLE IF NOT EXISTS concepts (
    id TEXT PRIMARY KEY,
    label TEXT UNIQUE NOT NULL,
    obsidian_wikilink TEXT NOT NULL,
    first_seen_meeting_id TEXT REFERENCES meetings(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meeting_concepts (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id),
    concept_id TEXT NOT NULL REFERENCES concepts(id)
);

CREATE INDEX IF NOT EXISTS idx_meetings_status       ON meetings(status);
CREATE INDEX IF NOT EXISTS idx_meetings_sha256       ON meetings(sha256_hash);
CREATE INDEX IF NOT EXISTS idx_transcript_meeting    ON transcript_segments(meeting_id);
CREATE INDEX IF NOT EXISTS idx_transcript_speaker    ON transcript_segments(speaker_id);
CREATE INDEX IF NOT EXISTS idx_meeting_speakers_meeting ON meeting_speakers(meeting_id);
CREATE INDEX IF NOT EXISTS idx_upload_log_hash       ON upload_log(sha256_hash);
"""


def init_db(db_path: Path) -> None:
    """Create all tables and indexes if they don't already exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db(db_path)
    try:
        conn.executescript(_DDL)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    return str(uuid.uuid4())


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# meetings
# ---------------------------------------------------------------------------

def create_meeting(
    conn: sqlite3.Connection,
    id: str,
    filename: str,
    sha256_hash: str,
    audio_path: str,
) -> None:
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO meetings (id, filename, sha256_hash, upload_time, audio_path,
                              status, audio_deleted, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'uploaded', 0, ?, ?)
        """,
        (id, filename, sha256_hash, now, audio_path, now, now),
    )
    conn.commit()


def get_meeting(conn: sqlite3.Connection, meeting_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
    ).fetchone()
    return _row_to_dict(row)


def get_all_meetings(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM meetings ORDER BY upload_time DESC"
    ).fetchall()
    return _rows_to_dicts(rows)


def update_meeting_status(
    conn: sqlite3.Connection,
    meeting_id: str,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    conn.execute(
        """
        UPDATE meetings
        SET status = ?, error_message = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, error_message, _now_iso(), meeting_id),
    )
    conn.commit()


def update_meeting_note_path(
    conn: sqlite3.Connection,
    meeting_id: str,
    relative_path: str,
) -> None:
    conn.execute(
        "UPDATE meetings SET obsidian_note_path = ?, updated_at = ? WHERE id = ?",
        (relative_path, _now_iso(), meeting_id),
    )
    conn.commit()


def update_meeting_temp_path(
    conn: sqlite3.Connection,
    meeting_id: str,
    temp_path: str,
) -> None:
    conn.execute(
        "UPDATE meetings SET temp_path = ?, updated_at = ? WHERE id = ?",
        (temp_path, _now_iso(), meeting_id),
    )
    conn.commit()


def mark_audio_deleted(conn: sqlite3.Connection, meeting_id: str) -> None:
    conn.execute(
        "UPDATE meetings SET audio_deleted = 1, updated_at = ? WHERE id = ?",
        (_now_iso(), meeting_id),
    )
    conn.commit()


def is_duplicate(conn: sqlite3.Connection, sha256_hash: str) -> bool:
    row = conn.execute(
        "SELECT id FROM meetings WHERE sha256_hash = ?", (sha256_hash,)
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# upload_log
# ---------------------------------------------------------------------------

def log_upload(
    conn: sqlite3.Connection,
    sha256_hash: str,
    filename: str,
    accepted: bool,
    rejection_reason: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO upload_log (id, sha256_hash, filename, upload_time, accepted, rejection_reason)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (_new_id(), sha256_hash, filename, _now_iso(), 1 if accepted else 0, rejection_reason),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# speakers
# ---------------------------------------------------------------------------

def save_speaker(
    conn: sqlite3.Connection,
    name: str,
    embedding_bytes: bytes,
    meeting_id: str,
    suggested_name: Optional[str] = None,
) -> str:
    speaker_id = _new_id()
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO speakers
            (id, name, suggested_name, embedding, embedding_source_meeting_id,
             first_seen, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (speaker_id, name, suggested_name, embedding_bytes, meeting_id, now, now),
    )
    conn.commit()
    return speaker_id


def get_all_speakers(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM speakers ORDER BY first_seen DESC").fetchall()
    return _rows_to_dicts(rows)


def get_speaker_by_id(conn: sqlite3.Connection, speaker_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM speakers WHERE id = ?", (speaker_id,)
    ).fetchone()
    return _row_to_dict(row)


def update_speaker_suggested_name(
    conn: sqlite3.Connection,
    speaker_id: str,
    suggested_name: str,
) -> None:
    conn.execute(
        "UPDATE speakers SET suggested_name = ? WHERE id = ?",
        (suggested_name, speaker_id),
    )
    conn.commit()


def update_speaker_name(
    conn: sqlite3.Connection,
    speaker_id: str,
    name: str,
) -> None:
    conn.execute(
        "UPDATE speakers SET name = ? WHERE id = ?",
        (name, speaker_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# meeting_speakers
# ---------------------------------------------------------------------------

def link_speaker_to_meeting(
    conn: sqlite3.Connection,
    meeting_id: str,
    speaker_id: str,
) -> None:
    """Insert a meeting_speakers row; silently skip if already linked."""
    existing = conn.execute(
        "SELECT id FROM meeting_speakers WHERE meeting_id = ? AND speaker_id = ?",
        (meeting_id, speaker_id),
    ).fetchone()
    if existing:
        return
    conn.execute(
        """
        INSERT INTO meeting_speakers (id, meeting_id, speaker_id)
        VALUES (?, ?, ?)
        """,
        (_new_id(), meeting_id, speaker_id),
    )
    conn.commit()


def get_meeting_speakers(conn: sqlite3.Connection, meeting_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT ms.id, ms.meeting_id, ms.speaker_id,
               ms.total_speaking_seconds, ms.segment_count,
               s.name, s.suggested_name, s.first_seen
        FROM meeting_speakers ms
        JOIN speakers s ON s.id = ms.speaker_id
        WHERE ms.meeting_id = ?
        """,
        (meeting_id,),
    ).fetchall()
    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# transcript_segments
# ---------------------------------------------------------------------------

def save_segment(
    conn: sqlite3.Connection,
    meeting_id: str,
    speaker_label: str,
    start: float,
    end: float,
    text: str,
    confidence: Optional[float] = None,
    speaker_id: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO transcript_segments
            (id, meeting_id, speaker_id, speaker_label,
             start_seconds, end_seconds, text, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (_new_id(), meeting_id, speaker_id, speaker_label, start, end, text, confidence),
    )
    conn.commit()


def get_segments(conn: sqlite3.Connection, meeting_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM transcript_segments
        WHERE meeting_id = ?
        ORDER BY start_seconds ASC
        """,
        (meeting_id,),
    ).fetchall()
    return _rows_to_dicts(rows)


def resolve_segment_speaker(
    conn: sqlite3.Connection,
    meeting_id: str,
    speaker_label: str,
    speaker_id: str,
) -> None:
    """Assign a resolved speaker_id to all segments that share a speaker_label."""
    conn.execute(
        """
        UPDATE transcript_segments
        SET speaker_id = ?
        WHERE meeting_id = ? AND speaker_label = ?
        """,
        (speaker_id, meeting_id, speaker_label),
    )
    conn.commit()


def get_unknown_speaker_labels(conn: sqlite3.Connection, meeting_id: str) -> list[str]:
    """Return distinct speaker_labels that have no resolved speaker_id yet."""
    rows = conn.execute(
        """
        SELECT DISTINCT speaker_label
        FROM transcript_segments
        WHERE meeting_id = ?
          AND speaker_id IS NULL
          AND speaker_label IS NOT NULL
        ORDER BY speaker_label
        """,
        (meeting_id,),
    ).fetchall()
    return [r["speaker_label"] for r in rows]


# ---------------------------------------------------------------------------
# concepts
# ---------------------------------------------------------------------------

def save_concept(
    conn: sqlite3.Connection,
    label: str,
    meeting_id: str,
) -> str:
    """Upsert a concept by label; return its concept_id."""
    existing = conn.execute(
        "SELECT id FROM concepts WHERE label = ?", (label,)
    ).fetchone()
    if existing:
        return existing["id"]

    concept_id = _new_id()
    wikilink = f"[[{label}]]"
    conn.execute(
        """
        INSERT INTO concepts (id, label, obsidian_wikilink, first_seen_meeting_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (concept_id, label, wikilink, meeting_id, _now_iso()),
    )
    conn.commit()
    return concept_id


def link_concept_to_meeting(
    conn: sqlite3.Connection,
    meeting_id: str,
    concept_id: str,
) -> None:
    existing = conn.execute(
        "SELECT id FROM meeting_concepts WHERE meeting_id = ? AND concept_id = ?",
        (meeting_id, concept_id),
    ).fetchone()
    if existing:
        return
    conn.execute(
        "INSERT INTO meeting_concepts (id, meeting_id, concept_id) VALUES (?, ?, ?)",
        (_new_id(), meeting_id, concept_id),
    )
    conn.commit()
