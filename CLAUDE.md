# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Arc Is

Local-first personal meeting intelligence. Android records Hinglish meetings with screen off → uploads to a FastAPI laptop server over WiFi → sequential ML pipeline (ffmpeg → faster-whisper → pyannote → resemblyzer → Gemma) → structured Obsidian vault note written in under 10 minutes. Zero cloud. Zero cost. Single user (Ruchit).

## Commands

```powershell
# Start server (from repo root)
uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

# Start pipeline watcher (separate terminal)
python server/watcher.py

# Mobile — build APK (requires Android Studio + JDK)
cd mobile
eas build --platform android --local
```

## Before First Run (One-Time Manual Steps)

```powershell
ollama pull gemma3:4b           # download model (~2.5GB)
ffmpeg -version                 # must be on PATH — install from ffmpeg.org if missing
```

Also required (cannot be automated):
- Accept pyannote model terms at huggingface.co/pyannote/speaker-diarization-3.1
- Copy `.env.example` → `.env` and set all values (especially `OBSIDIAN_VAULT_PATH`, `HF_TOKEN`)

## Environment Variables (`.env`)

```env
OBSIDIAN_VAULT_PATH=C:\Users\Lenovo\Desktop\Code\Obsidan Stronghold\MyBrain\Brain (ruchitdas36)
OBSIDIAN_MEETINGS_SUBFOLDER=Meetings
ARC_INTAKE_DIR=C:\Users\Lenovo\Desktop\arc\intake
ARC_TEMP_DIR=C:\Users\Lenovo\Desktop\arc\temp
ARC_DB_PATH=C:\Users\Lenovo\Desktop\arc\arc.db
ARC_SERVER_PORT=8000
WHISPER_MODEL=large-v3
WHISPER_DEVICE=cuda
OLLAMA_MODEL=gemma3:4b
OLLAMA_HOST=http://localhost:11434
HF_TOKEN=<your-huggingface-token>
```

## Architecture

Two independent surfaces, one backend:

**Mobile** (`mobile/`) — React Native Expo bare workflow (Android only). Three screens: `QRScannerScreen` (one-time pairing), `RecorderScreen` (main UI), `UploadStatusScreen`. Foreground Service keeps recording alive with screen off.

**Server** (`server/`) — FastAPI process on Windows laptop. Serves both the REST upload API and Jinja2 web UI on the same port. `watcher.py` runs as a separate process monitoring `intake/`.

**Pipeline** — sequential Python scripts in `server/pipeline/`. Must be sequential; RTX 4050 has 6GB VRAM (Whisper large-v3 ~3GB, pyannote ~1GB — cannot co-exist).

```
server/
├── main.py              — FastAPI app, all routes, QR gen on startup
├── watcher.py           — watchdog FileSystemEventHandler on intake/
├── database.py          — SQLite schema init + all queries
├── pipeline/
│   ├── normalizer.py    — ffmpeg subprocess: any format → WAV 16kHz mono
│   ├── transcriber.py   — faster-whisper large-v3 (CUDA)
│   ├── diarizer.py      — pyannote speaker-diarization-3.1 (max_speakers=8)
│   ├── aligner.py       — overlap-match whisper segments to pyannote labels
│   ├── speaker_db.py    — resemblyzer embeddings: extract, cosine match, store
│   ├── name_inferrer.py — Gemma: infer speaker names from vocative context
│   ├── note_generator.py— Gemma: transcript → structured JSON → Obsidian markdown
│   └── vault_writer.py  — write meeting folder to Obsidian vault
└── templates/           — Jinja2 HTML (base, dashboard, naming, transcript)
```

**Pipeline flow** (triggered per new file in `intake/`):
1. ffmpeg normalize → WAV 16kHz mono
2. faster-whisper → `{start, end, text, confidence}[]`
3. pyannote → `{start, end, speaker_label}[]`
4. aligner → `{start, end, speaker_label, text}[]`
5. resemblyzer → match each speaker_label to stored embedding (threshold 0.75)
6. If unknown speakers: Gemma infers names from transcript → set status `needs_naming` → halt
7. Web UI: play 10s clip, show inferred name suggestion, user accepts/overrides
8. Pipeline resumes: Gemma generates structured JSON note → vault_writer writes meeting folder
9. Audio moved from `intake/` to `temp/`; status → `done`

**Obsidian output** — each meeting writes a folder:
```
Meetings/YYYY-MM-DD-HHMM-Speaker1-Speaker2/
├── note.md          — YAML frontmatter + summary/decisions/actions/wikilinks
├── transcript.md    — speaker-tagged full transcript in JetBrains Mono
└── audio_ref.txt    — one line: absolute path to file in temp/
```

**SQLite** (`arc.db`) — WAL mode. Tables: `meetings`, `speakers`, `meeting_speakers`, `transcript_segments`, `upload_log`, `concepts`, `meeting_concepts`.

Meeting status flow: `uploaded` → `needs_naming` → `processing` → `done` / `error`

## Hard Rules

**Windows path safety** — use `pathlib.Path` everywhere. Never hardcode `/` separators.

**ffmpeg subprocess** — always use list args, `shell=False`:
```python
subprocess.run(["ffmpeg", "-y", "-i", str(input_path), "-ar", "16000", "-ac", "1", str(output_path)], check=True)
```

**SQLite** — always open with `WAL` mode and `check_same_thread=False`. Server and watcher share the DB concurrently.

**Audio deletion** — audio is never auto-deleted. Only via explicit `DELETE /meeting/{id}/audio`. Validate deletion paths with `pathlib.Path.resolve()` and confirm the target is a child of `ARC_TEMP_DIR` before deleting (path traversal risk).

**Ollama** — check Ollama is alive before name inference and note generation. If not running, set meeting status `error` with a clear message rather than crashing.

**Obsidian paths in DB** — store meeting folder paths relative to vault root (e.g., `Meetings/2025-05-26-1430-Rahul-Priya/`), not absolute. Resolve dynamically using `OBSIDIAN_VAULT_PATH` env var.

**API response format** — all JSON responses: `{success: bool, data: any, error: str | null}`.

**Pipeline is sequential** — do not parallelise pipeline steps. VRAM is the bottleneck.

## Schema Notes (vs `05-BackendSchema.md`)

The audit identified two schema gaps to fix during build:
- `speakers` table needs: `suggested_name TEXT NULLABLE` (stores Gemma inference between pipeline steps)
- `meetings` table: rename `archive_path` → `temp_path`; add `audio_deleted INTEGER DEFAULT 0`

## Speaker Matching Calibration

Resemblyzer cosine threshold is `0.75`. If speaker matching accuracy falls below 70% during Phase 3 testing with real Hinglish audio:
1. Lower threshold to `0.65` and retest
2. If still insufficient, replace resemblyzer with speechbrain `SpeakerRecognition`

**Do not build Phase 4 (naming UI) until Phase 3 spike passes.**

## Build Sequence (Hackathon)

Phase 1 → FastAPI server + QR + upload + dedup  
Phase 2 → Android app (recording + upload)  
Phase 3 → Transcription + diarization + speaker matching (**spike — validate before continuing**)  
Phase 4 → Speaker naming UI + pipeline resume  
Phase 5 → Note generation + Obsidian vault write  
Phase 6 → Cross-meeting wikilinks + MCP validation  
Phase 7 → Edge cases + polish  
