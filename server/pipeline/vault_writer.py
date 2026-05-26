"""
Arc pipeline — Step 8: Write meeting output to the Obsidian vault.

Creates a meeting folder containing:
  note.md        — YAML-frontmattered structured meeting note
  transcript.md  — Full speaker-tagged transcript with [[wikilinks]]
  audio_ref.txt  — Absolute path to the source audio file in temp/

Updates the meetings table with the relative vault path and persists
any new concepts extracted by the note generator.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import frontmatter  # type: ignore[import]  # python-frontmatter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_vault(
    conn: sqlite3.Connection,
    meeting_id: str,
    note_data: dict,
    vault_path: Path,
    meetings_subfolder: str,
) -> None:
    """
    Write all meeting artefacts to the Obsidian vault.

    Parameters
    ----------
    conn:
        Open SQLite connection.
    meeting_id:
        UUID of the meeting being processed.
    note_data:
        Structured dict returned by :func:`note_generator.generate_note`.
    vault_path:
        Absolute path to the Obsidian vault root.
    meetings_subfolder:
        Subfolder inside the vault where meeting folders live
        (e.g. ``"Meetings"``).
    """
    from database import (  # type: ignore[import]  # noqa: E402
        update_meeting_note_path,
        save_concept,
        link_concept_to_meeting,
    )

    meeting = _get_meeting(conn, meeting_id)
    segments = _get_segments_with_names(conn, meeting_id)

    # ---- Resolve participant names ----------------------------------------
    participants = _unique_participant_names(segments)
    upload_time_str: str = meeting.get("upload_time", "")
    meeting_dt = _parse_dt(upload_time_str)

    # ---- Build folder name ---------------------------------------------------
    date_str = meeting_dt.strftime("%Y-%m-%d")
    time_str = meeting_dt.strftime("%H%M")
    name_parts = [p.replace(" ", "") for p in participants[:2]]
    folder_name_parts = [date_str, time_str] + name_parts
    folder_name = "-".join(p for p in folder_name_parts if p)

    meeting_folder: Path = vault_path / meetings_subfolder / folder_name
    meeting_folder.mkdir(parents=True, exist_ok=True)
    logger.info("Writing vault artefacts to: %s", meeting_folder)

    # ---- Write note.md -------------------------------------------------------
    note_path = meeting_folder / "note.md"
    _write_note_md(note_path, meeting_id, meeting_dt, participants, segments, note_data)

    # ---- Write transcript.md -------------------------------------------------
    transcript_path = meeting_folder / "transcript.md"
    _write_transcript_md(transcript_path, date_str, time_str, participants, segments)

    # ---- Write audio_ref.txt -------------------------------------------------
    audio_ref_path = meeting_folder / "audio_ref.txt"
    audio_abs = meeting.get("temp_path") or meeting.get("audio_path") or ""
    audio_ref_path.write_text(audio_abs, encoding="utf-8")

    # ---- Update DB -----------------------------------------------------------
    relative_folder = str(Path(meetings_subfolder) / folder_name)
    update_meeting_note_path(conn, meeting_id, relative_folder)
    logger.info("Meeting note path saved to DB: %s", relative_folder)

    # ---- Persist concepts ----------------------------------------------------
    concepts: list[str] = note_data.get("concepts") or []
    for concept_label in concepts:
        label = concept_label.strip()
        if not label:
            continue
        concept_id = save_concept(conn, label, meeting_id)
        link_concept_to_meeting(conn, meeting_id, concept_id)

    logger.info(
        "Vault write complete: folder=%s, concepts=%d", meeting_folder, len(concepts)
    )


# ---------------------------------------------------------------------------
# note.md writer
# ---------------------------------------------------------------------------

def _write_note_md(
    note_path: Path,
    meeting_id: str,
    meeting_dt: datetime,
    participants: list[str],
    segments: list[dict],
    note_data: dict,
) -> None:
    date_str = meeting_dt.strftime("%Y-%m-%d")
    time_str = meeting_dt.strftime("%H:%M")
    duration_min = _compute_duration_minutes(segments)
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ---- YAML frontmatter ---------------------------------------------------
    yaml_participants = "\n".join(f"  - {p}" for p in participants)
    concepts: list[str] = note_data.get("concepts") or []
    yaml_concept_tags = (
        "\n".join(f"  - {c.lower().replace(' ', '-')}" for c in concepts)
        if concepts
        else ""
    )

    # We build frontmatter manually via python-frontmatter Post object so the
    # library handles escaping correctly.
    fm_metadata: dict = {
        "title": f"Meeting — {date_str} {time_str}",
        "date": date_str,
        "time": time_str,
        "duration": f"{duration_min} minutes",
        "participants": participants,
        "tags": ["meeting"] + [c.lower().replace(" ", "-") for c in concepts],
        "arc_meeting_id": meeting_id,
    }

    # ---- Body sections -------------------------------------------------------
    discussed = note_data.get("discussed_topics") or []
    discussed_md = "\n".join(f"- {t}" for t in discussed) if discussed else "- (none recorded)"

    decisions = note_data.get("decisions") or []
    decisions_md = _format_decisions(decisions)

    action_items = note_data.get("action_items") or []
    action_items_md = _format_action_items(action_items)

    suggestions = note_data.get("suggestions_debates") or []
    suggestions_md = _format_suggestions(suggestions)

    next_notes = note_data.get("next_meeting_notes") or []
    next_notes_md = "\n".join(f"- {n}" for n in next_notes) if next_notes else "- (none)"

    summary = note_data.get("summary") or ""

    body = f"""## Summary
{summary}

## What Was Discussed
{discussed_md}

## Decisions Made
{decisions_md}

## Action Items
{action_items_md}

## Key Suggestions & Debates
{suggestions_md}

## Notes for Next Meeting
{next_notes_md}

---
*Generated by Arc · {now_ts}*"""

    post = frontmatter.Post(body, **fm_metadata)
    note_path.write_text(frontmatter.dumps(post), encoding="utf-8")
    logger.debug("Wrote note.md: %s", note_path)


def _format_decisions(decisions: list) -> str:
    if not decisions:
        return "- (none recorded)"
    lines: list[str] = []
    for d in decisions:
        if not isinstance(d, dict):
            lines.append(f"- {d}")
            continue
        decision_text = d.get("decision", "")
        agreed_by: list = d.get("agreed_by") or []
        if agreed_by:
            agreed_str = ", ".join(agreed_by)
            lines.append(f"- {decision_text} *(agreed by: {agreed_str})*")
        else:
            lines.append(f"- {decision_text}")
    return "\n".join(lines)


def _format_action_items(items: list) -> str:
    if not items:
        return "- [ ] (none recorded)"
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            lines.append(f"- [ ] {item}")
            continue
        task = item.get("task", "")
        owner = item.get("owner") or "Unknown"
        deadline = item.get("deadline")
        suffix = f" — **{owner}**"
        if deadline:
            suffix += f" (by {deadline})"
        lines.append(f"- [ ] {task}{suffix}")
    return "\n".join(lines)


def _format_suggestions(suggestions: list) -> str:
    if not suggestions:
        return "*(none recorded)*"
    blocks: list[str] = []
    for s in suggestions:
        if not isinstance(s, dict):
            blocks.append(f"**{s}**")
            continue
        topic = s.get("topic", "Discussion")
        for_points: list = s.get("for") or []
        against_points: list = s.get("against") or []
        block_lines = [f"### {topic}"]
        if for_points:
            block_lines.append("**In favour:**")
            for pt in for_points:
                if isinstance(pt, dict):
                    block_lines.append(f"- **{pt.get('speaker', '?')}**: {pt.get('point', '')}")
                else:
                    block_lines.append(f"- {pt}")
        if against_points:
            block_lines.append("**Against:**")
            for pt in against_points:
                if isinstance(pt, dict):
                    block_lines.append(f"- **{pt.get('speaker', '?')}**: {pt.get('point', '')}")
                else:
                    block_lines.append(f"- {pt}")
        blocks.append("\n".join(block_lines))
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# transcript.md writer
# ---------------------------------------------------------------------------

def _write_transcript_md(
    transcript_path: Path,
    date_str: str,
    time_str: str,
    participants: list[str],
    segments: list[dict],
) -> None:
    title = f"Meeting — {date_str} {time_str}"
    lines: list[str] = [f"# Transcript — {title}", ""]

    for seg in segments:
        name = (seg.get("speaker_name") or seg.get("speaker_label") or "Unknown").strip()
        start = seg.get("start_seconds", 0.0)
        mm = int(start) // 60
        ss = int(start) % 60
        text = (seg.get("text") or "").strip()
        lines.append(f"**[[{name}]]** ({mm:02d}:{ss:02d}): {text}")

    transcript_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.debug("Wrote transcript.md: %s", transcript_path)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_meeting(conn: sqlite3.Connection, meeting_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Meeting not found: {meeting_id}")
    return dict(row)


def _get_segments_with_names(conn: sqlite3.Connection, meeting_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            ts.start_seconds,
            ts.end_seconds,
            ts.text,
            ts.speaker_label,
            COALESCE(s.name, ts.speaker_label, 'Unknown') AS speaker_name
        FROM transcript_segments ts
        LEFT JOIN speakers s ON s.id = ts.speaker_id
        WHERE ts.meeting_id = ?
        ORDER BY ts.start_seconds ASC
        """,
        (meeting_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _unique_participant_names(segments: list[dict]) -> list[str]:
    seen: dict[str, int] = {}
    for seg in segments:
        name = (seg.get("speaker_name") or "Unknown").strip()
        seen[name] = seen.get(name, 0) + 1
    return [n for n, _ in sorted(seen.items(), key=lambda x: -x[1])]


def _compute_duration_minutes(segments: list[dict]) -> int:
    if not segments:
        return 0
    max_end = max(seg.get("end_seconds", 0.0) for seg in segments)
    return max(1, round(max_end / 60))


def _parse_dt(upload_time: str) -> datetime:
    try:
        return datetime.fromisoformat(upload_time.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc)
