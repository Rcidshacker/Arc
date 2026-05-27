"""
Arc pipeline — Step 7: Structured note generation via Gemma 4 (llama-server).

Reads all resolved transcript segments from the DB, sends a speaker-tagged
transcript to Gemma 4 via llama-server with thinking enabled, and returns
a structured dict matching the Obsidian note schema.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

# <|think|> prefix activates extended reasoning in Gemma 4 via llama-server
SYSTEM_PROMPT = """<|think|>
You are a meeting intelligence assistant. You receive a speaker-tagged \
transcript and return a structured JSON object. Return ONLY valid JSON. \
No preamble. No explanation. No markdown fences.

JSON schema:
{
  "summary": "string — 2-4 sentences",
  "discussed_topics": ["string"],
  "decisions": [{"decision": "string", "agreed_by": ["speaker_name"]}],
  "action_items": [{"task": "string", "owner": "speaker_name_or_unknown", "deadline": "string_or_null"}],
  "suggestions_debates": [
    {
      "topic": "string",
      "for": [{"speaker": "string", "point": "string"}],
      "against": [{"speaker": "string", "point": "string"}]
    }
  ],
  "next_meeting_notes": ["string"],
  "concepts": ["string"]
}"""

USER_PROMPT = """Meeting date: {date}
Duration: {duration} minutes
Participants: {participants}

Transcript:
{tagged_transcript}"""

_MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_note(conn: sqlite3.Connection, meeting_id: str) -> dict:
    """
    Generate a structured meeting note for *meeting_id*.

    Parameters
    ----------
    conn:
        Open SQLite connection.
    meeting_id:
        UUID of the meeting to process.

    Returns
    -------
    dict
        Keys: ``summary``, ``discussed_topics``, ``decisions``,
        ``action_items``, ``suggestions_debates``, ``next_meeting_notes``,
        ``concepts``.

    Raises
    ------
    RuntimeError
        If the meeting or its segments cannot be found, Ollama is unreachable,
        or JSON parsing fails after all retries.
    """
    meeting = _get_meeting(conn, meeting_id)
    segments = _get_segments_with_names(conn, meeting_id)

    if not segments:
        raise RuntimeError(
            f"No transcript segments found for meeting {meeting_id}. "
            "Run transcription and alignment steps first."
        )

    tagged_transcript = _build_tagged_transcript(segments)
    participants = _unique_participant_names(segments)
    duration_minutes = _compute_duration_minutes(segments)
    meeting_date = _parse_meeting_date(meeting.get("upload_time", ""))

    user_msg = USER_PROMPT.format(
        date=meeting_date,
        duration=duration_minutes,
        participants=", ".join(participants) if participants else "Unknown",
        tagged_transcript=tagged_transcript,
    )

    logger.info(
        "Sending transcript to llama-server for note generation (%d segments, %d participants).",
        len(segments),
        len(participants),
    )

    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 2):  # up to _MAX_RETRIES + 1 attempts total
        raw = _call_llamacpp(user_msg)
        logger.debug("Raw llama-server response (attempt %d):\n%s", attempt, raw)
        stripped = _strip_thinking(raw)
        try:
            note = _parse_json_response(stripped)
            logger.info("Note generation succeeded on attempt %d.", attempt)
            return note
        except ValueError as exc:
            last_error = exc
            logger.warning(
                "Attempt %d/%d: JSON parse failed — %s",
                attempt,
                _MAX_RETRIES + 1,
                exc,
            )

    raise RuntimeError(
        f"Note generation failed after {_MAX_RETRIES + 1} attempts. "
        f"Last error: {last_error}"
    )


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
    """
    Return all segments for the meeting, joining speaker name where resolved.
    For unresolved segments, falls back to speaker_label.
    """
    rows = conn.execute(
        """
        SELECT
            ts.start_seconds,
            ts.end_seconds,
            ts.text,
            ts.confidence,
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
# Transcript formatting
# ---------------------------------------------------------------------------

def _build_tagged_transcript(segments: list[dict]) -> str:
    lines: list[str] = []
    for seg in segments:
        name = seg.get("speaker_name") or seg.get("speaker_label") or "Unknown"
        start = seg.get("start_seconds", 0.0)
        mm = int(start) // 60
        ss = int(start) % 60
        text = (seg.get("text") or "").strip()
        lines.append(f"[{name}] ({mm:02d}:{ss:02d}): {text}")
    return "\n".join(lines)


def _unique_participant_names(segments: list[dict]) -> list[str]:
    seen: dict[str, int] = {}
    for seg in segments:
        name = (seg.get("speaker_name") or "Unknown").strip()
        seen[name] = seen.get(name, 0) + 1
    # Sort by frequency (most talkative first)
    return [n for n, _ in sorted(seen.items(), key=lambda x: -x[1])]


def _compute_duration_minutes(segments: list[dict]) -> int:
    if not segments:
        return 0
    max_end = max(seg.get("end_seconds", 0.0) for seg in segments)
    return max(1, round(max_end / 60))


def _parse_meeting_date(upload_time: str) -> str:
    try:
        dt = datetime.fromisoformat(upload_time.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# llama-server (OpenAI-compatible)
# ---------------------------------------------------------------------------

_LLAMACPP_MODEL: str | None = None


def _get_model_name(host: str) -> str:
    global _LLAMACPP_MODEL
    if _LLAMACPP_MODEL is not None:
        return _LLAMACPP_MODEL

    import requests  # type: ignore[import]

    try:
        resp = requests.get(f"{host}/v1/models", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # Accept both /models (ollama-style) and OpenAI data[] format
        models = data.get("data") or data.get("models") or []
        if models:
            _LLAMACPP_MODEL = models[0].get("id") or models[0].get("name") or "local"
        else:
            _LLAMACPP_MODEL = "local"
    except Exception:
        _LLAMACPP_MODEL = "local"

    print(f"[ARC] llama-server model: {_LLAMACPP_MODEL}", flush=True)
    return _LLAMACPP_MODEL


def _call_llamacpp(user_message: str) -> str:
    try:
        import requests  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "requests is not installed. Run: pip install requests"
        ) from exc

    host: str = os.environ.get("LLAMACPP_HOST", "http://localhost:8080")
    model = _get_model_name(host)
    url = f"{host}/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "temperature": 0.2,
        "max_tokens": 2048,
    }

    try:
        resp = requests.post(url, json=payload, timeout=180)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            f"llama-server is not reachable at {host}. "
            "Ensure llama-server is running and LLAMACPP_HOST is correct."
        ) from exc
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(f"llama-server HTTP error: {exc}") from exc

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, TypeError, IndexError) as exc:
        raise RuntimeError(f"Unexpected llama-server response shape: {data}") from exc


# ---------------------------------------------------------------------------
# Thinking token stripping
# ---------------------------------------------------------------------------

def _strip_thinking(text: str) -> str:
    """Remove <|think|>...</|think|> reasoning blocks before JSON parsing."""
    return re.sub(r"<\|think\|>.*?<\|/think\|>", "", text, flags=re.DOTALL).strip()


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {
    "summary",
    "discussed_topics",
    "decisions",
    "action_items",
    "suggestions_debates",
    "next_meeting_notes",
    "concepts",
}

_DEFAULTS: dict = {
    "summary": "",
    "discussed_topics": [],
    "decisions": [],
    "action_items": [],
    "suggestions_debates": [],
    "next_meeting_notes": [],
    "concepts": [],
}


def _parse_json_response(raw: str) -> dict:
    """
    Extract and validate the JSON object from Gemma's response.

    Raises
    ------
    ValueError
        If no valid JSON object is found.
    """
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in response: {cleaned[:300]!r}")

    try:
        parsed: dict = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON decode error: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object, got {type(parsed).__name__}.")

    # Merge with defaults so all keys are always present
    result = {**_DEFAULTS, **parsed}
    return result
