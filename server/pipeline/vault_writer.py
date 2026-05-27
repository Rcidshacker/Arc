"""
Arc pipeline — Step 8: Write meeting output to the Obsidian vault.

Preferred path: MCP tool calls via llama-server proxy → Obsidian MCP server.
Fallback path:  Direct pathlib writes to vault directory on disk.

The fallback is always available — MCP failure never blocks note delivery.

Creates a meeting folder containing:
  note.md        — YAML-frontmattered structured meeting note
  transcript.md  — Full speaker-tagged transcript with [[wikilinks]]
  audio_ref.txt  — Absolute path to the source audio file in temp/

Updates the meetings table with the relative vault path and persists
any new concepts extracted by the note generator.
"""

from __future__ import annotations

import logging
import os
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

    Attempts MCP writes first; falls back to direct pathlib writes on any failure.

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
        Subfolder inside the vault where meeting folders live (e.g. ``"Meetings"``).
    """
    from database import (  # type: ignore[import]  # noqa: E402
        update_meeting_note_path,
        save_concept,
        link_concept_to_meeting,
    )

    meeting = _get_meeting(conn, meeting_id)
    segments = _get_segments_with_names(conn, meeting_id)

    participants = _unique_participant_names(segments)
    upload_time_str: str = meeting.get("upload_time", "")
    meeting_dt = _parse_dt(upload_time_str)

    date_str = meeting_dt.strftime("%Y-%m-%d")
    time_str = meeting_dt.strftime("%H%M")
    name_parts = [p.replace(" ", "") for p in participants[:2]]
    folder_name = "-".join(p for p in [date_str, time_str] + name_parts if p)

    rel_folder = str(Path(meetings_subfolder) / folder_name)
    audio_abs = meeting.get("temp_path") or meeting.get("audio_path") or ""

    # ---- Build file contents (shared by both write paths) --------------------
    note_content = _build_note_md_content(
        meeting_id, meeting_dt, participants, segments, note_data
    )
    transcript_content = _build_transcript_md_content(
        date_str, time_str, participants, segments
    )

    # ---- Attempt MCP write ---------------------------------------------------
    mcp_host = os.environ.get("LLAMACPP_HOST", "http://localhost:8080")
    mcp_server = os.environ.get("OBSIDIAN_MCP_URL", "http://localhost:3100/sse")
    mcp_ok = False

    try:
        mcp_ok = _mcp_write_artefacts(
            meeting_id=meeting_id,
            folder_name=folder_name,
            meetings_subfolder=meetings_subfolder,
            note_content=note_content,
            transcript_content=transcript_content,
            audio_abs=audio_abs,
            note_data=note_data,
            participants=participants,
            segments=segments,
            mcp_host=mcp_host,
            mcp_server=mcp_server,
        )
    except Exception as exc:
        logger.warning("MCP write raised unexpectedly — falling back: %s", exc)

    # ---- Fallback: direct pathlib write -------------------------------------
    if not mcp_ok:
        logger.info("Using direct pathlib write for meeting %s", meeting_id)
        meeting_folder: Path = vault_path / meetings_subfolder / folder_name
        meeting_folder.mkdir(parents=True, exist_ok=True)

        (meeting_folder / "note.md").write_text(note_content, encoding="utf-8")
        (meeting_folder / "transcript.md").write_text(transcript_content, encoding="utf-8")
        (meeting_folder / "audio_ref.txt").write_text(audio_abs, encoding="utf-8")

        logger.info("Direct write complete: %s", meeting_folder)

    # ---- Update DB (always) -------------------------------------------------
    update_meeting_note_path(conn, meeting_id, rel_folder)
    logger.info("Meeting note path saved to DB: %s", rel_folder)

    # ---- Persist concepts (always) ------------------------------------------
    concepts: list[str] = note_data.get("concepts") or []
    for concept_label in concepts:
        label = concept_label.strip()
        if not label:
            continue
        concept_id = save_concept(conn, label, meeting_id)
        link_concept_to_meeting(conn, meeting_id, concept_id)

    logger.info(
        "Vault write complete: folder=%s, concepts=%d, via_mcp=%s",
        rel_folder,
        len(concepts),
        mcp_ok,
    )


# ---------------------------------------------------------------------------
# MCP write layer
# ---------------------------------------------------------------------------

def _mcp_write_artefacts(
    *,
    meeting_id: str,
    folder_name: str,
    meetings_subfolder: str,
    note_content: str,
    transcript_content: str,
    audio_abs: str,
    note_data: dict,
    participants: list[str],
    segments: list[dict],
    mcp_host: str,
    mcp_server: str,
) -> bool:
    """
    Write meeting artefacts via Obsidian MCP tools proxied through llama-server.

    Returns True only if ALL required writes (note, transcript, audio_ref) succeed.
    Brain log and cross-linking are best-effort and do not affect the return value.
    """
    base_path = f"{meetings_subfolder}/{folder_name}"

    print(f"[ARC] MCP write: probing {mcp_host}/mcp/call ...", flush=True)

    # a) Duplicate check -------------------------------------------------------
    dup_result = _mcp_call(
        "obsidian_search",
        {"query": f"arc_meeting_id: {meeting_id}", "context_length": 50},
        mcp_host,
        mcp_server,
    )
    if dup_result is not None:
        hits = dup_result.get("results") or dup_result.get("matches") or []
        if hits:
            logger.warning(
                "MCP duplicate check: meeting %s already in vault — skipping MCP write.",
                meeting_id,
            )
            return True  # already written, not an error

    # b) Write note.md ---------------------------------------------------------
    note_result = _mcp_call(
        "obsidian_create_note",
        {"path": f"{base_path}/note.md", "content": note_content},
        mcp_host,
        mcp_server,
    )
    if note_result is None:
        logger.warning("MCP note.md write failed — falling back to direct write.")
        return False

    # c) Write transcript.md ---------------------------------------------------
    transcript_result = _mcp_call(
        "obsidian_create_note",
        {"path": f"{base_path}/transcript.md", "content": transcript_content},
        mcp_host,
        mcp_server,
    )
    if transcript_result is None:
        logger.warning("MCP transcript.md write failed — falling back to direct write.")
        return False

    # d) Write audio_ref.txt ---------------------------------------------------
    audio_result = _mcp_call(
        "obsidian_create_note",
        {"path": f"{base_path}/audio_ref.txt", "content": audio_abs},
        mcp_host,
        mcp_server,
    )
    if audio_result is None:
        logger.warning("MCP audio_ref.txt write failed — falling back to direct write.")
        return False

    print(f"[ARC] MCP write: 3 artefacts written to {base_path}", flush=True)

    # e) Brain log (best-effort) -----------------------------------------------
    n_speakers = len(participants)
    n_segments = len(segments)
    duration_min = _compute_duration_minutes(segments)
    log_entry = (
        f"op: meeting_processed | subject: {folder_name} | "
        f"summary: {n_speakers} speakers, {n_segments} segments, {duration_min} min"
    )
    _mcp_call("brain_log", {"content": log_entry}, mcp_host, mcp_server)

    # f) Concept cross-linking (best-effort) ------------------------------------
    concepts: list[str] = note_data.get("concepts") or []
    _mcp_crosslink_concepts(
        concepts=concepts,
        note_path=f"{base_path}/note.md",
        mcp_host=mcp_host,
        mcp_server=mcp_server,
    )

    return True


def _mcp_crosslink_concepts(
    concepts: list[str],
    note_path: str,
    mcp_host: str,
    mcp_server: str,
) -> None:
    """
    For each concept, search for previous meetings that share it.
    If found, patch the new note with a "## Related Meetings" wikilink section.
    """
    related_links: list[str] = []

    for concept in concepts:
        concept = concept.strip()
        if not concept:
            continue
        result = _mcp_call(
            "obsidian_search",
            {"query": concept, "context_length": 30},
            mcp_host,
            mcp_server,
        )
        if result is None:
            continue
        hits = result.get("results") or result.get("matches") or []
        for hit in hits:
            hit_path: str = hit.get("path") or hit.get("filename") or ""
            # Only link meeting notes, not the current note itself
            if "note.md" in hit_path and hit_path != note_path:
                # Extract folder name from path for the wikilink
                parts = hit_path.replace("\\", "/").split("/")
                if len(parts) >= 2:
                    link_target = parts[-2]  # folder name = meeting title
                    wikilink = f"- [[{link_target}]] *(shared concept: {concept})*"
                    if wikilink not in related_links:
                        related_links.append(wikilink)

    if not related_links:
        return

    cross_link_content = "\n".join(related_links)
    _mcp_call(
        "obsidian_patch_note",
        {
            "path": note_path,
            "heading": "## Related Meetings",
            "content": cross_link_content,
            "insert_after": True,
        },
        mcp_host,
        mcp_server,
    )
    logger.info("Cross-linked %d related meetings.", len(related_links))


def _mcp_call(
    tool: str,
    arguments: dict,
    mcp_host: str,
    mcp_server: str,
) -> dict | None:
    """
    POST a single MCP tool call to llama-server's proxy endpoint.

    Returns the parsed JSON response on success, or None on any failure.
    Never raises.
    """
    try:
        import requests  # type: ignore[import]
    except ImportError:
        logger.warning("requests not installed — MCP unavailable.")
        return None

    url = f"{mcp_host.rstrip('/')}/mcp/call"
    payload = {"server": mcp_server, "tool": tool, "arguments": arguments}

    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.debug("MCP call %s failed: %s", tool, exc)
        return None


# ---------------------------------------------------------------------------
# Content builders (shared by MCP and direct write paths)
# ---------------------------------------------------------------------------

def _build_note_md_content(
    meeting_id: str,
    meeting_dt: datetime,
    participants: list[str],
    segments: list[dict],
    note_data: dict,
) -> str:
    date_str = meeting_dt.strftime("%Y-%m-%d")
    time_str = meeting_dt.strftime("%H:%M")
    duration_min = _compute_duration_minutes(segments)
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    concepts: list[str] = note_data.get("concepts") or []

    fm_metadata: dict = {
        "title": f"Meeting — {date_str} {time_str}",
        "date": date_str,
        "time": time_str,
        "duration": f"{duration_min} minutes",
        "participants": participants,
        "tags": ["meeting"] + [c.lower().replace(" ", "-") for c in concepts],
        "arc_meeting_id": meeting_id,
    }

    discussed = note_data.get("discussed_topics") or []
    discussed_md = "\n".join(f"- {t}" for t in discussed) if discussed else "- (none recorded)"

    decisions_md = _format_decisions(note_data.get("decisions") or [])
    action_items_md = _format_action_items(note_data.get("action_items") or [])
    suggestions_md = _format_suggestions(note_data.get("suggestions_debates") or [])

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
    return frontmatter.dumps(post)


def _build_transcript_md_content(
    date_str: str,
    time_str: str,
    participants: list[str],
    segments: list[dict],
) -> str:
    title = f"Meeting — {date_str} {time_str}"
    lines: list[str] = [f"# Transcript — {title}", ""]

    for seg in segments:
        name = (seg.get("speaker_name") or seg.get("speaker_label") or "Unknown").strip()
        start = seg.get("start_seconds", 0.0)
        mm = int(start) // 60
        ss = int(start) % 60
        text = (seg.get("text") or "").strip()
        lines.append(f"**[[{name}]]** ({mm:02d}:{ss:02d}): {text}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

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
            lines.append(f"- {decision_text} *(agreed by: {', '.join(agreed_by)})*")
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
