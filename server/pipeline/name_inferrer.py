"""
Arc pipeline — Step 6: Name inference via Gemma (Ollama).

For each unresolved speaker label the function:
1. Builds a context string from the aligned transcript.
2. Asks Gemma to identify the speaker by name (vocative addressing).
3. Persists inferences to a JSON sidecar file: ``clips/{meeting_id}_suggestions.json``
   so the naming UI can present them to the user.

The naming UI reads the sidecar, shows the audio clip + suggested name, and
on confirmation the server creates the real speaker record with a proper embedding.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM = """You identify speaker names from meeting transcripts.
Look for vocative addressing — when someone says a person's name directly.
Return ONLY a JSON object mapping speaker labels to inferred names.
If you cannot confidently identify a name for a speaker, use null.
Example: {"SPEAKER_00": "Rahul", "SPEAKER_01": null}"""

_USER_TEMPLATE = """Unknown speakers to identify: {labels}

Transcript context (last 20 segments):
{context}

Return JSON only."""

# Regex patterns for vocative detection (used to rank context segments)
_VOCATIVE_PATTERNS = [
    re.compile(r"\bHey\s+([A-Z][a-z]+)\b"),
    re.compile(r"\bThanks?\s+([A-Z][a-z]+)\b"),
    re.compile(r"\b([A-Z][a-z]+)\s*,?\s+what\s+do\s+you\s+think\b", re.IGNORECASE),
    re.compile(r"\b([A-Z][a-z]+)\s*,\s+(?:can|could|would|do|did)\s+you\b", re.IGNORECASE),
    re.compile(r"\bRight,?\s+([A-Z][a-z]+)\b"),
    re.compile(r"\bOkay,?\s+([A-Z][a-z]+)\b"),
    re.compile(r"\bYeah,?\s+([A-Z][a-z]+)\b"),
    re.compile(r"\bSo,?\s+([A-Z][a-z]+)\b"),
    re.compile(r"\b([A-Z][a-z]+)\s*[,.]?\s+I\s+(?:think|agree|disagree|want)\b"),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def infer_names(
    conn: sqlite3.Connection,
    meeting_id: str,
    aligned_segments: list[dict],
    unknown_labels: list[str],
    clips_dir: Path | None = None,
) -> None:
    """
    Infer speaker names from transcript context and persist to a sidecar JSON.

    Parameters
    ----------
    conn:
        Open SQLite connection (read-only usage here; no writes).
    meeting_id:
        UUID of the current meeting.
    aligned_segments:
        Full list of aligned segments (used for context building).
    unknown_labels:
        Speaker labels that could not be matched in speaker_db.
    clips_dir:
        Directory where clip files live; sidecar JSON is written here.
        Defaults to ``{ARC_TEMP_DIR}/clips/`` or a ``clips/`` sibling of
        the temp directory.
    """
    if not unknown_labels:
        logger.info("infer_names: no unknown labels; skipping Ollama call.")
        return

    clips_dir = _resolve_clips_dir(clips_dir)
    clips_dir.mkdir(parents=True, exist_ok=True)

    context_str = _build_context(aligned_segments)
    labels_str = ", ".join(unknown_labels)

    user_msg = _USER_TEMPLATE.format(labels=labels_str, context=context_str)

    logger.info("Calling Gemma for name inference of labels: %s", labels_str)
    raw_response = _call_ollama(user_msg)

    inferences = _parse_json_response(raw_response, unknown_labels)
    logger.info("Name inferences: %s", inferences)

    # Persist to sidecar file
    sidecar_path = clips_dir / f"{meeting_id}_suggestions.json"
    _write_sidecar(sidecar_path, inferences)
    logger.info("Suggestions written to: %s", sidecar_path)


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------

def _build_context(aligned_segments: list[dict]) -> str:
    """
    Return the last 20 segments as a readable transcript block.
    Segments containing vocative patterns are prioritised by being included
    even if they fall outside the last-20 window (up to 5 bonus segments).
    """
    last_20 = aligned_segments[-20:] if len(aligned_segments) > 20 else aligned_segments[:]

    # Collect up to 5 vocative-rich segments from the full transcript that
    # are not already in last_20
    last_20_ids = {id(s) for s in last_20}
    bonus: list[dict] = []
    for seg in aligned_segments:
        if id(seg) in last_20_ids:
            continue
        if any(pat.search(seg.get("text", "")) for pat in _VOCATIVE_PATTERNS):
            bonus.append(seg)
            if len(bonus) >= 5:
                break

    combined = sorted(bonus + last_20, key=lambda s: s["start"])

    lines: list[str] = []
    for seg in combined:
        label = seg.get("speaker_label", "UNKNOWN")
        start = _fmt_time(seg.get("start", 0.0))
        text = seg.get("text", "").strip()
        lines.append(f"[{label}] ({start}): {text}")

    return "\n".join(lines)


def _fmt_time(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

def _call_ollama(user_message: str) -> str:
    """Send a chat request to Ollama and return the response content string."""
    try:
        import requests  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "requests is not installed. Run: pip install requests"
        ) from exc

    ollama_host: str = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model: str = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
    url = f"{ollama_host.rstrip('/')}/api/chat"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,   # low temp for deterministic JSON
            "num_predict": 256,
        },
    }

    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            f"Ollama is not reachable at {ollama_host}. "
            "Ensure Ollama is running and OLLAMA_HOST is correct."
        ) from exc
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(f"Ollama returned an error: {exc}") from exc

    data = resp.json()
    try:
        return data["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            f"Unexpected Ollama response shape: {data}"
        ) from exc


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def _parse_json_response(raw: str, expected_labels: list[str]) -> dict[str, str | None]:
    """
    Extract a JSON object from Gemma's response.
    Falls back to returning ``null`` for all labels if parsing fails.
    """
    # Strip markdown fences if present
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    # Find first { ... } block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            result: dict = json.loads(match.group(0))
            # Ensure all expected labels are present
            for label in expected_labels:
                result.setdefault(label, None)
            # Filter out keys that are not speaker labels we care about
            return {k: (v if isinstance(v, str) and v.strip() else None) for k, v in result.items() if k in expected_labels}
        except json.JSONDecodeError:
            logger.warning("Failed to parse Gemma JSON response: %s", cleaned[:300])

    logger.warning("Name inference returned no parseable JSON; defaulting all to null.")
    return {label: None for label in expected_labels}


# ---------------------------------------------------------------------------
# Sidecar file
# ---------------------------------------------------------------------------

def _write_sidecar(sidecar_path: Path, inferences: dict[str, str | None]) -> None:
    """Write inferences dict to a JSON sidecar file (atomically)."""
    tmp_path = sidecar_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(inferences, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(sidecar_path)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _resolve_clips_dir(clips_dir: Path | None) -> Path:
    if clips_dir is not None:
        return clips_dir
    temp_dir = os.environ.get("ARC_TEMP_DIR")
    if temp_dir:
        return Path(temp_dir).parent / "clips"
    # Final fallback: project-root-relative clips/
    return Path(__file__).parent.parent.parent / "clips"
