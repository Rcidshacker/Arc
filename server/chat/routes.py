"""Chat routes — /chat prefix."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from database import get_db  # type: ignore[import]
from chat.rag import EFFORT_CONFIG, bm25_search, format_context, load_vault_chunks  # type: ignore[import]
from chat.file_processor import process_uploaded_file  # type: ignore[import]
from chat.engine import build_system_prompt, stream_response  # type: ignore[import]

router = APIRouter(prefix="/chat", tags=["chat"])

_SERVER_DIR = Path(__file__).parent.parent
_templates = Jinja2Templates(directory=str(_SERVER_DIR / "templates"))

_ARC_DB_PATH = Path(os.environ["ARC_DB_PATH"])
_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "")
_MEETINGS_SUBFOLDER = os.getenv("OBSIDIAN_MEETINGS_SUBFOLDER", "Meetings")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ok(data=None) -> dict:
    return {"success": True, "data": data, "error": None}


def _err(msg: str, code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=code, content={"success": False, "data": None, "error": msg})


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _get_session(conn, session_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def _list_sessions(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM chat_sessions ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


def _create_session(conn, session_id: str, title: str = "New Chat") -> dict:
    now = _now()
    conn.execute(
        "INSERT INTO chat_sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (session_id, title, now, now),
    )
    conn.commit()
    return {"id": session_id, "title": title, "created_at": now, "updated_at": now,
            "effort": "medium", "thinking_enabled": 1, "internet_enabled": 0}


def _delete_session(conn, session_id: str) -> None:
    conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    conn.commit()


def _get_messages(conn, session_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _save_message(conn, session_id: str, role: str, content: str, sources: list[str] | None = None) -> str:
    msg_id = str(uuid.uuid4())
    now = _now()
    sources_json = json.dumps(sources) if sources else None
    conn.execute(
        "INSERT INTO chat_messages (id, session_id, role, content, created_at, sources) VALUES (?, ?, ?, ?, ?, ?)",
        (msg_id, session_id, role, content, now, sources_json),
    )
    conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    conn.commit()
    return msg_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
async def chat_page(request: Request) -> HTMLResponse:
    return _templates.TemplateResponse("chat.html", {"request": request})


@router.get("/api/sessions")
async def list_sessions() -> JSONResponse:
    with get_db(_ARC_DB_PATH) as conn:
        sessions = _list_sessions(conn)
    return JSONResponse(content=_ok(sessions))


@router.post("/api/sessions")
async def create_session() -> JSONResponse:
    session_id = str(uuid.uuid4())
    with get_db(_ARC_DB_PATH) as conn:
        session = _create_session(conn, session_id)
    return JSONResponse(content=_ok(session))


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str) -> JSONResponse:
    with get_db(_ARC_DB_PATH) as conn:
        if not _get_session(conn, session_id):
            return _err("not found", 404)
        _delete_session(conn, session_id)
    return JSONResponse(content=_ok(None))


@router.patch("/api/sessions/{session_id}")
async def update_session(request: Request, session_id: str) -> JSONResponse:
    body = await request.json()
    with get_db(_ARC_DB_PATH) as conn:
        if not _get_session(conn, session_id):
            return _err("not found", 404)
        now = _now()
        if "title" in body:
            conn.execute("UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
                         (body["title"][:80], now, session_id))
        if "effort" in body:
            conn.execute("UPDATE chat_sessions SET effort = ?, updated_at = ? WHERE id = ?",
                         (body["effort"], now, session_id))
        if "thinking_enabled" in body:
            conn.execute("UPDATE chat_sessions SET thinking_enabled = ?, updated_at = ? WHERE id = ?",
                         (1 if body["thinking_enabled"] else 0, now, session_id))
        if "internet_enabled" in body:
            conn.execute("UPDATE chat_sessions SET internet_enabled = ?, updated_at = ? WHERE id = ?",
                         (1 if body["internet_enabled"] else 0, now, session_id))
        conn.commit()
        session = _get_session(conn, session_id)
    return JSONResponse(content=_ok(session))


@router.get("/api/sessions/{session_id}/messages")
async def get_messages(session_id: str) -> JSONResponse:
    with get_db(_ARC_DB_PATH) as conn:
        if not _get_session(conn, session_id):
            return _err("not found", 404)
        messages = _get_messages(conn, session_id)
    return JSONResponse(content=_ok(messages))


@router.post("/api/sessions/{session_id}/send")
async def send_message(
    session_id: str,
    message: str = Form(...),
    effort: str = Form("medium"),
    thinking_enabled: str = Form("true"),
    internet_enabled: str = Form("false"),
    files: Optional[List[UploadFile]] = None,
) -> StreamingResponse:
    with get_db(_ARC_DB_PATH) as conn:
        session = _get_session(conn, session_id)
        if not session:
            return JSONResponse(status_code=404, content={"error": "session not found"})

        # Save user message
        _save_message(conn, session_id, "user", message)

        # Load history (last 20 non-thinking messages)
        all_msgs = _get_messages(conn, session_id)

    history = [m for m in all_msgs if m["role"] != "thinking"][-20:]

    # Process uploaded files
    processed_files: list[dict] = []
    if files:
        for f in files:
            if f and f.filename:
                raw = await f.read()
                try:
                    processed_files.append(process_uploaded_file(f.filename, raw))
                except ValueError:
                    pass

    # BM25 over vault
    effort_key = effort if effort in EFFORT_CONFIG else "medium"
    cfg = EFFORT_CONFIG[effort_key]
    chunks = load_vault_chunks(_VAULT_PATH, cfg["chunk_size"]) if _VAULT_PATH else []
    matched = bm25_search(message, chunks, cfg["top_k"])
    vault_context, sources = format_context(matched)
    has_context = bool(matched)

    system_prompt = build_system_prompt(vault_context, has_context, internet)
    thinking = thinking_enabled.lower() not in ("false", "0", "no")
    internet = internet_enabled.lower() not in ("false", "0", "no")

    async def _generate():
        thinking_acc: list[str] = []
        text_acc: list[str] = []
        response_sources: list[str] = []

        async for event in stream_response(
            messages=history,
            system_prompt=system_prompt,
            thinking_enabled=thinking,
            internet_enabled=internet,
            uploaded_files=processed_files,
            sources=sources,
        ):
            yield event
            if event.startswith("data:"):
                try:
                    data = json.loads(event[5:].strip())
                    t = data.get("type")
                    if t == "thinking":
                        thinking_acc.append(data.get("delta", ""))
                    elif t == "text":
                        text_acc.append(data.get("delta", ""))
                    elif t == "sources":
                        response_sources = data.get("sources", [])
                    elif t == "done":
                        full_text = "".join(text_acc)
                        full_thinking = "".join(thinking_acc)
                        with get_db(_ARC_DB_PATH) as conn:
                            _save_message(conn, session_id, "assistant", full_text, response_sources)
                            if full_thinking:
                                _save_message(conn, session_id, "thinking", full_thinking)
                except Exception:
                    pass

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/sessions/{session_id}/write-note")
async def write_note(session_id: str, request: Request) -> JSONResponse:
    if not _VAULT_PATH:
        return _err("OBSIDIAN_VAULT_PATH not configured", 500)

    body = await request.json()
    content: str = body.get("content", "").strip()
    filename: str = body.get("filename", "chat-note.md").strip()

    if not content:
        return _err("content required")
    if not filename.endswith(".md"):
        filename += ".md"

    # Sanitize filename
    safe_name = "".join(c for c in filename if c.isalnum() or c in ".-_ ").strip() or "chat-note.md"

    vault = Path(_VAULT_PATH)
    chat_dir = vault / "Chat"
    chat_dir.mkdir(parents=True, exist_ok=True)
    dest = chat_dir / safe_name

    # Path traversal guard
    try:
        dest.resolve().relative_to(vault.resolve())
    except ValueError:
        return _err("invalid path", 400)

    dest.write_text(content, encoding="utf-8")
    rel_path = f"Chat/{safe_name}"
    return JSONResponse(content=_ok({"path": rel_path}))
