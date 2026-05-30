"""
Arc – main.py
FastAPI application. Serves both REST API and the Jinja2 web UI from a single
process. Registers the file-system watcher as a background thread on startup.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import socket
import threading
import uuid
from pathlib import Path
from typing import Optional

import qrcode
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

OBSIDIAN_VAULT_PATH = Path(os.environ["OBSIDIAN_VAULT_PATH"])
OBSIDIAN_MEETINGS_SUBFOLDER = os.getenv("OBSIDIAN_MEETINGS_SUBFOLDER", "Meetings")

ARC_INTAKE_DIR = Path(os.environ["ARC_INTAKE_DIR"])
ARC_TEMP_DIR = Path(os.environ["ARC_TEMP_DIR"])
ARC_DB_PATH = Path(os.environ["ARC_DB_PATH"])
ARC_SERVER_PORT = int(os.getenv("ARC_SERVER_PORT", "8000"))

CLIPS_DIR = ARC_TEMP_DIR.parent / "clips"

# Resolve server/ directory
SERVER_DIR = Path(__file__).parent
STATIC_DIR = SERVER_DIR / "static"
TEMPLATES_DIR = SERVER_DIR / "templates"

# ---------------------------------------------------------------------------
# Lazy imports — pipeline modules live alongside this file
# ---------------------------------------------------------------------------

from database import (  # noqa: E402 – must come after env load
    create_meeting,
    get_all_meetings,
    get_all_speakers,
    get_db,
    get_meeting,
    get_meeting_speakers,
    get_segments,
    get_unknown_speaker_labels,
    init_db,
    is_duplicate,
    link_speaker_to_meeting,
    log_upload,
    mark_audio_deleted,
    resolve_segment_speaker,
    save_speaker,
    update_meeting_note_path,
    update_meeting_status,
    update_meeting_temp_path,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Arc Meeting Intelligence", version="0.1.0")

# Allow Expo web dev server (localhost:19006) to reach the API during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ARC_INTAKE_DIR.mkdir(parents=True, exist_ok=True)
ARC_TEMP_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(data=None) -> dict:
    return {"success": True, "data": data, "error": None}


def _err(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "data": None, "error": message},
    )


def _get_local_ip() -> str:
    """Best-effort LAN IP detection."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _generate_qr(url: str, save_path: Path) -> None:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(str(save_path))


def _sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Startup event
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event() -> None:
    # Initialise database
    init_db(ARC_DB_PATH)

    # Generate QR code pointing to this server's LAN address
    local_ip = _get_local_ip()
    server_url = f"http://{local_ip}:{ARC_SERVER_PORT}"
    qr_path = STATIC_DIR / "qr.png"
    _generate_qr(server_url, qr_path)

    print("=" * 60)
    print(f"  Arc server running at {server_url}")
    print(f"  QR code saved to {qr_path}")
    print(f"  Scan the QR from your phone to open the upload UI")
    print("=" * 60)

    # Start the file-system watcher in a daemon thread
    _start_watcher()


def _start_watcher() -> None:
    """Import and launch the watchdog observer as a background daemon thread."""
    try:
        from watcher import start_observer  # type: ignore[import]

        t = threading.Thread(
            target=start_observer,
            args=(ARC_INTAKE_DIR, ARC_DB_PATH),
            daemon=True,
            name="arc-watcher",
        )
        t.start()
    except Exception as exc:  # pragma: no cover
        print(f"[Arc] WARNING: watcher failed to start — {exc}")


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.post("/upload")
async def upload_audio(file: UploadFile = File(...)) -> JSONResponse:
    content = await file.read()
    sha256 = _sha256_of_bytes(content)

    with get_db(ARC_DB_PATH) as conn:
        if is_duplicate(conn, sha256):
            log_upload(conn, sha256, file.filename or "unknown", accepted=False,
                       rejection_reason="duplicate")
            return _err("duplicate", status_code=409)

        # Persist file with a UUID prefix to avoid collisions
        suffix = Path(file.filename or "audio").suffix or ".audio"
        stored_name = f"{uuid.uuid4()}{suffix}"
        dest = ARC_INTAKE_DIR / stored_name
        dest.write_bytes(content)

        meeting_id = str(uuid.uuid4())
        create_meeting(
            conn,
            id=meeting_id,
            filename=file.filename or stored_name,
            sha256_hash=sha256,
            audio_path=str(dest),
        )
        log_upload(conn, sha256, file.filename or stored_name, accepted=True)

    return JSONResponse(
        status_code=200,
        content=_ok({"meeting_id": meeting_id, "sha256": sha256}),
    )


@app.get("/status/{meeting_id}")
async def get_status(meeting_id: str) -> JSONResponse:
    with get_db(ARC_DB_PATH) as conn:
        meeting = get_meeting(conn, meeting_id)

    if not meeting:
        return _err("not found", status_code=404)

    return JSONResponse(
        status_code=200,
        content=_ok({
            "meeting_id": meeting["id"],
            "status": meeting["status"],
            "filename": meeting["filename"],
            "upload_time": meeting["upload_time"],
            "duration_seconds": meeting.get("duration_seconds"),
            "error_message": meeting["error_message"],
        }),
    )


@app.get("/speakers")
async def list_speakers() -> JSONResponse:
    with get_db(ARC_DB_PATH) as conn:
        speakers = get_all_speakers(conn)
    # Strip embedding bytes from JSON response
    for s in speakers:
        s.pop("embedding", None)
    return JSONResponse(status_code=200, content=_ok(speakers))


@app.get("/clip/{meeting_id}/{speaker_label}")
async def serve_clip(meeting_id: str, speaker_label: str) -> FileResponse:
    clip_filename = f"{meeting_id}_{speaker_label}.wav"
    clip_path = CLIPS_DIR / clip_filename
    if not clip_path.exists():
        return JSONResponse(
            status_code=404,
            content={"success": False, "data": None, "error": "clip not found"},
        )  # type: ignore[return-value]
    return FileResponse(str(clip_path), media_type="audio/wav", filename=clip_filename)


@app.delete("/meeting/{meeting_id}/audio")
async def delete_audio(meeting_id: str) -> JSONResponse:
    with get_db(ARC_DB_PATH) as conn:
        meeting = get_meeting(conn, meeting_id)
        if not meeting:
            return _err("not found", status_code=404)

        temp_path_str = meeting.get("temp_path")
        if temp_path_str:
            # SECURITY: resolve and verify child of ARC_TEMP_DIR
            candidate = (ARC_TEMP_DIR / Path(temp_path_str).name).resolve()
            temp_resolved = ARC_TEMP_DIR.resolve()
            try:
                candidate.relative_to(temp_resolved)
            except ValueError:
                return _err("path traversal detected", status_code=400)

            if candidate.exists():
                candidate.unlink()

        mark_audio_deleted(conn, meeting_id)

        # Optionally clear audio_ref.txt in Obsidian note folder
        note_rel = meeting.get("obsidian_note_path")
        if note_rel:
            audio_ref = OBSIDIAN_VAULT_PATH / note_rel / "audio_ref.txt"
            if audio_ref.exists():
                audio_ref.unlink(missing_ok=True)

    return JSONResponse(status_code=200, content=_ok(None))


@app.post("/speaker/name")
async def name_speakers(
    request: Request,
    background_tasks: BackgroundTasks,
    meeting_id: str = Form(...),
) -> RedirectResponse:
    form_data = await request.form()

    audio_path: Optional[Path] = None
    with get_db(ARC_DB_PATH) as conn:
        meeting = get_meeting(conn, meeting_id)
        if not meeting:
            return _err("not found", status_code=404)  # type: ignore[return-value]

        audio_path = Path(meeting["audio_path"])

        for key, value in form_data.items():
            if key.startswith("name_") and value:
                label = key[len("name_"):]
                name = str(value).strip()
                if not name:
                    continue

                import numpy as np  # local import – numpy may not be at top level
                placeholder_embedding = np.zeros(256, dtype=np.float32).tobytes()

                speaker_id = save_speaker(
                    conn,
                    name=name,
                    embedding_bytes=placeholder_embedding,
                    meeting_id=meeting_id,
                )
                resolve_segment_speaker(conn, meeting_id, label, speaker_id)
                link_speaker_to_meeting(conn, meeting_id, speaker_id)

        update_meeting_status(conn, meeting_id, "uploaded")

    # Directly retrigger the pipeline — no new FileCreatedEvent fires for a
    # file already sitting in intake/, so we call run_pipeline_for_meeting
    # explicitly in a background thread.
    if audio_path is not None:
        from watcher import run_pipeline_for_meeting  # type: ignore[import]
        background_tasks.add_task(run_pipeline_for_meeting, meeting_id, audio_path, ARC_DB_PATH)

    return RedirectResponse(url="/", status_code=303)


# ---------------------------------------------------------------------------
# Template routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    with get_db(ARC_DB_PATH) as conn:
        meetings = get_all_meetings(conn)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "meetings": meetings},
    )


@app.get("/meeting/{meeting_id}", response_class=HTMLResponse)
async def meeting_detail(request: Request, meeting_id: str) -> HTMLResponse:
    with get_db(ARC_DB_PATH) as conn:
        meeting = get_meeting(conn, meeting_id)
        if not meeting:
            return HTMLResponse("<h1>Meeting not found</h1>", status_code=404)
        segments = get_segments(conn, meeting_id)
        meeting_speakers = get_meeting_speakers(conn, meeting_id)

    return templates.TemplateResponse(
        "transcript.html",
        {
            "request": request,
            "meeting": meeting,
            "segments": segments,
            "speakers": meeting_speakers,
        },
    )


@app.get("/naming/{meeting_id}", response_class=HTMLResponse)
async def naming_page(request: Request, meeting_id: str) -> HTMLResponse:
    with get_db(ARC_DB_PATH) as conn:
        meeting = get_meeting(conn, meeting_id)
        if not meeting:
            return HTMLResponse("<h1>Meeting not found</h1>", status_code=404)

        unknown_labels = get_unknown_speaker_labels(conn, meeting_id)

        # For each unknown label, check if a suggested_name exists in speakers
        label_suggestions: dict[str, Optional[str]] = {}
        for label in unknown_labels:
            row = conn.execute(
                """
                SELECT s.suggested_name FROM transcript_segments ts
                JOIN speakers s ON s.id = ts.speaker_id
                WHERE ts.meeting_id = ? AND ts.speaker_label = ?
                  AND s.suggested_name IS NOT NULL
                LIMIT 1
                """,
                (meeting_id, label),
            ).fetchone()
            label_suggestions[label] = row["suggested_name"] if row else None

    return templates.TemplateResponse(
        "naming.html",
        {
            "request": request,
            "meeting": meeting,
            "unknown_labels": unknown_labels,
            "label_suggestions": label_suggestions,
        },
    )


@app.get("/landing", response_class=HTMLResponse)
async def landing_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/qr", response_class=HTMLResponse)
async def qr_page(request: Request) -> HTMLResponse:
    local_ip = _get_local_ip()
    server_url = f"http://{local_ip}:{ARC_SERVER_PORT}"
    return templates.TemplateResponse(
        "qr.html",
        {"request": request, "server_url": server_url},
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=ARC_SERVER_PORT,
        reload=False,
    )
