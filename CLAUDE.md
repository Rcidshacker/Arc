# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Arc Is

Local-first personal meeting intelligence. Android records Hinglish meetings with screen off → uploads to a FastAPI laptop server over WiFi → sequential ML pipeline (ffmpeg → transcription → pyannote → resemblyzer → llama-server/Gemma) → structured Obsidian vault note written in under 10 minutes. Zero cloud. Zero cost. Single user (Ruchit).

## Commands

```powershell
# Activate venv first (required — dependencies live in .venv, not global Python)
.\.venv\Scripts\Activate.ps1

# Start FastAPI server (from repo root)
# PYTHONPATH=server required — server/main.py imports 'database' as a top-level module
# Must use .venv\Scripts\uvicorn.exe, not system uvicorn
$env:PYTHONPATH="server"; .venv\Scripts\uvicorn.exe server.main:app --host 0.0.0.0 --port 8000 --reload

# Start pipeline watcher (separate terminal, from repo root — activate venv first)
$env:PYTHONPATH = "server"; python server/watcher.py

# Run API smoke tests (from server/ directory — imports relative to server/)
cd server
pytest ..\tests\ -v

# Mobile — build APK (requires Android Studio + JDK)
cd mobile
eas build --platform android --local
```

## Three Required Services

All three must be running before the pipeline can complete:

| Service | Port | Purpose |
|---------|------|---------|
| FastAPI (`uvicorn server.main:app`) | 8000 | Upload API + web UI + pipeline orchestration |
| llama-server | 8080 | Transcription (llamacpp provider) + note generation |
| Obsidian MCP SSE | 3100 | Vault writes (fallback: direct pathlib writes) |

`LLAMACPP_HOST` and `OBSIDIAN_MCP_URL` env vars configure their endpoints.

## Before First Run (One-Time Manual Steps)

```powershell
ffmpeg -version    # must be on PATH — install from ffmpeg.org if missing
```

Also required:
- Accept pyannote model terms at huggingface.co/pyannote/speaker-diarization-3.1
- Copy `.env.example` → `.env` and fill all values

## Environment Variables (`.env`)

```env
OBSIDIAN_VAULT_PATH=C:\Users\Lenovo\Desktop\Code\Obsidan Stronghold\MyBrain\Arc_holder
OBSIDIAN_MEETINGS_SUBFOLDER=Meetings
ARC_INTAKE_DIR=C:\Users\Lenovo\Desktop\arc\intake
ARC_TEMP_DIR=C:\Users\Lenovo\Desktop\arc\temp
ARC_DB_PATH=C:\Users\Lenovo\Desktop\arc\arc.db
ARC_SERVER_PORT=8000
HF_TOKEN=<your-huggingface-token>

# Transcription: llamacpp (default/local), groq, or gemini
TRANSCRIPTION_PROVIDER=llamacpp
LLAMACPP_HOST=http://localhost:8080

# Groq fallback (TRANSCRIPTION_PROVIDER=groq, files <20MB)
GROQ_API_KEY=<your-groq-key>

# Gemini fallback (TRANSCRIPTION_PROVIDER=gemini, files >=20MB)
GOOGLE_API_KEY=<your-google-key>

# Obsidian MCP SSE endpoint (vault_writer tries this before direct writes)
OBSIDIAN_MCP_URL=http://localhost:3100/sse

# DEPRECATED — Ollama replaced by llama-server for all inference
# OLLAMA_MODEL=gemma3:4b
# OLLAMA_HOST=http://localhost:11434
```

## Architecture

Two independent surfaces, one backend:

**Mobile** (`mobile/`) — React Native Expo bare workflow (Android only). Three screens: `QRScannerScreen` (one-time pairing), `RecorderScreen` (main UI), `UploadStatusScreen`. Foreground Service keeps recording alive with screen off.

**Server** (`server/`) — FastAPI process on Windows laptop. Serves both the REST upload API and Jinja2 web UI on the same port. `watcher.py` runs as a separate process (or thread) monitoring `intake/`.

**Pipeline** — sequential Python scripts in `server/pipeline/`. Must be sequential; RTX 4050 has 6GB VRAM (pyannote ~1GB, llama-server persists across calls — cannot co-run heavy models simultaneously).

```
server/
├── main.py              — FastAPI app, all routes, QR gen on startup
├── watcher.py           — polling loop (2s interval) on intake/; no watchdog Observer
├── database.py          — SQLite schema init + all queries
├── pipeline/
│   ├── normalizer.py    — ffmpeg subprocess: any format → WAV 16kHz mono
│   ├── transcriber.py   — multi-provider: llamacpp (default) / groq / gemini
│   ├── diarizer.py      — pyannote speaker-diarization-3.1 (max_speakers=8)
│   ├── aligner.py       — overlap-match whisper segments to pyannote labels
│   ├── speaker_db.py    — MVP: all speakers → naming UI (no embedding/matching yet)
│   ├── name_inferrer.py — Gemma: infer speaker names from vocative context
│   ├── note_generator.py— llama-server/Gemma 4 thinking mode → structured JSON
│   └── vault_writer.py  — MCP write (via llama-server proxy) → fallback direct write
└── templates/           — Jinja2 HTML (base, dashboard, naming, transcript)
```

**Pipeline flow** (triggered per new file in `intake/`):
1. ffmpeg normalize → WAV 16kHz mono
2. Transcription via `TRANSCRIPTION_PROVIDER` (llamacpp/groq/gemini) → `{start, end, text, confidence}[]`
3. pyannote → `{start, end, speaker}[]`
4. aligner → `{start, end, speaker_label, text}[]`
5. speaker_db MVP → extracts 10s clip per label, returns all labels as unknown
6. Always halts at `needs_naming` → web UI shows clips, user names speakers
7. Pipeline resumes: llama-server/Gemma generates structured JSON note (thinking mode)
8. vault_writer: tries MCP → falls back to direct pathlib write → status `done`
9. WAV moved from intake/ to temp/

**Obsidian output** — each meeting writes a folder:
```
Meetings/YYYY-MM-DD-HHMM-Speaker1-Speaker2/
├── note.md          — YAML frontmatter + summary/decisions/actions/wikilinks
├── transcript.md    — speaker-tagged full transcript with [[wikilinks]]
└── audio_ref.txt    — absolute path to file in temp/
```

**SQLite** (`arc.db`) — WAL mode. Tables: `meetings`, `speakers`, `meeting_speakers`, `transcript_segments`, `upload_log`, `concepts`, `meeting_concepts`.

Meeting status flow: `uploaded` → `needs_naming` → `processing` → `done` / `error`

## Hard Rules

**Windows path safety** — use `pathlib.Path` everywhere. Never hardcode `/` separators.

**ffmpeg subprocess** — always list args, `shell=False`:
```python
subprocess.run(["ffmpeg", "-y", "-i", str(input_path), "-ar", "16000", "-ac", "1", str(output_path)], check=True)
```

**SQLite** — always open with WAL mode and `check_same_thread=False`. Server and watcher share the DB concurrently. All queries parameterized — no f-string interpolation into SQL.

**Audio deletion** — audio is never auto-deleted. Only via explicit `DELETE /meeting/{id}/audio`. Validate paths with `Path.resolve()` and confirm target is a child of `ARC_TEMP_DIR` (path traversal risk).

**llama-server** — check connectivity before note generation. If unreachable, set meeting status `error` with a clear message. `LLAMACPP_HOST` defaults to `http://localhost:8080`.

**Obsidian paths in DB** — store paths relative to vault root (e.g. `Meetings/2025-05-26-1430-Rahul-Priya/`). Resolve dynamically using `OBSIDIAN_VAULT_PATH` env var.

**API response format** — all JSON responses: `{success: bool, data: any, error: str | null}`. Return 409 for duplicate uploads (sha256 match), 400 for path traversal, 422 for bad input.

**Pipeline is sequential** — do not parallelise pipeline steps. VRAM is the bottleneck.

**FastAPI route handlers** — no blocking ML/ffmpeg calls inline. Offload to background tasks or the watcher process.

## Key Implementation Details

**diarizer.py** has three compatibility patches applied at runtime (not monkey-patched globally):
1. SpeechBrain optional module stubs — pre-registers missing `k2_fsa`, `huggingface`, etc. in `sys.modules`
2. `torch.load` weights_only patch — PyTorch 2.6 sets `weights_only=True` by default; pyannote checkpoints need `False`
3. `hf_hub_download` token param patch — huggingface_hub ≥0.24 renamed `use_auth_token` → `token`

**transcriber.py** provider routing: `TRANSCRIPTION_PROVIDER=llamacpp` sends base64-encoded WAV in OpenAI-compatible chat request. Groq and Gemini providers return timestamped segments; llamacpp returns a single segment spanning the full file (aligner handles this).

**note_generator.py** uses `<|think|>` prefix in system prompt to activate Gemma 4 extended reasoning via llama-server. `_strip_thinking()` removes `<|think|>…</|think|>` blocks before JSON parsing.

**vault_writer.py** MCP layer: POSTs to `{LLAMACPP_HOST}/mcp/call` with `{"server": OBSIDIAN_MCP_URL, "tool": "obsidian_create_note", ...}`. MCP failure is non-fatal; falls back to direct pathlib writes. Also does best-effort concept cross-linking and brain_log entries.

**speaker_db.py** is intentionally an MVP stub — `match_and_embed_speakers()` always returns all labels as unknown. Cross-session resemblyzer matching is v2.

**watcher.py** uses a pure-Python polling loop (`start_observer`) instead of watchdog's `Observer` — avoids a `BaseThread` issue on Python 3.13. Polls every 2s.

## Speaker Matching Calibration (v2 target)

When cross-session speaker matching is added in v2:
- Resemblyzer cosine threshold: start at `0.75`
- If accuracy < 70% on real Hinglish audio: lower to `0.65`, then consider speechbrain `SpeakerRecognition`
