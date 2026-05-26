# TRD — Arc
### Technical Requirements Document

---

## Stack Overview

| Layer | Choice | Reason |
|-------|--------|--------|
| Mobile Frontend | React Native — Expo bare workflow | Bare workflow required for Android Foreground Service; Expo managed silently drops audio on screen lock |
| Web UI | FastAPI + Jinja2 HTML (served from same laptop server) | Single Python process serves both upload API and browser UI — zero extra infra |
| Backend Pipeline | Python 3.11+ scripts on Windows laptop | All ML libraries (pyannote, faster-whisper, resemblyzer) are Python-native |
| Database | SQLite | Local only, no server, zero config, sufficient for personal single-user scale |
| Knowledge Store | Obsidian vault (existing) | Already set up; wikilinks give free graph view; queried via existing MCP |
| Auth | None | Single user personal app — no login needed |
| Hosting | Localhost (laptop only) | No deployment, no cloud, no cost |
| LLM Runtime | Ollama — Gemma 4:4B | Free, local, runs on RTX 4050, sufficient for structured markdown generation |
| Transcription | faster-whisper large-v3 | Free, local, GPU-accelerated, best available for Hinglish without fine-tuning |
| Audio Normalization | ffmpeg (subprocess) | Universal format conversion to WAV 16kHz mono before pipeline entry |
| Builder | OpenAI Codex CLI | Hackathon requirement; driven by AGENTS.md in repo root |

---

## Hard Constraints

- Android only — no iOS
- All processing runs locally on Ruchit's laptop (RTX 4050 6GB VRAM, 24GB DDR5 RAM, Windows 11)
- Zero ongoing cost — no paid APIs, no subscriptions, no cloud services
- Audio never leaves local network — no external upload of recordings
- App must record cleanly with screen off (Foreground Service mandatory)
- Mobile recording format: AAC/M4A at 128kbps
- All audio normalized to WAV 16kHz mono before Whisper — regardless of input format
- Audio files are never auto-deleted — user deletes manually from temp/ via web UI
- Built using OpenAI Codex CLI with AGENTS.md for project context

---

## Third-Party Services

| Service | Purpose | Tier | Cost |
|---------|---------|------|------|
| Ollama | Local LLM runtime for Gemma 4:4B | Free / open source | $0 |
| Cloudflare Tunnel | Optional: expose localhost when on different WiFi | Free tier | $0 |

> No other third-party services. All ML models run locally.

---

## Key Libraries

### Mobile (React Native / Expo Bare)

| Library | Purpose |
|---------|---------|
| `expo-av` | Audio recording with background mode configuration |
| `@voximplant/react-native-foreground-service` | Keeps app alive and recording with screen off |
| `expo-camera` | QR code scanner for one-time server pairing |
| `expo-file-system` | Read audio file path after recording |
| `axios` | HTTP multipart upload to FastAPI endpoint |
| `react-native-reanimated` | Smooth recording pulse animation |

### Laptop Pipeline (Python)

| Library | Purpose |
|---------|---------|
| `fastapi` | Upload API endpoints + serves web UI |
| `uvicorn` | ASGI server to run FastAPI |
| `jinja2` | HTML templating for web UI |
| `python-multipart` | Parse multipart file uploads |
| `qrcode[pil]` | Generate QR code on server startup |
| `ffmpeg` (subprocess) | Audio format normalization — any format → WAV 16kHz mono |
| `faster-whisper` | Local Hinglish transcription (GPU via CUDA) |
| `pyannote.audio` | Speaker diarization — who spoke when |
| `resemblyzer` | Speaker voice embeddings + cross-session matching |
| `ollama` | Python client to call Gemma 4:4B locally (transcription + name inference + note gen) |
| `watchdog` | Monitor intake folder for new audio files |
| `python-frontmatter` | Generate Obsidian-compatible YAML frontmatter |
| `sqlite3` | Built-in Python — meetings, speakers, upload log |
| `hashlib` | SHA256 hash generation for deduplication |
| `soundfile` | Audio file reading for clip extraction (naming UI) |
| `numpy` | Vector operations for embedding similarity |

---

## Environment Variables

```env
# Obsidian Vault
OBSIDIAN_VAULT_PATH=C:\Users\Lenovo\Desktop\Code\Obsidan Stronghold\MyBrain\Arc_holder
OBSIDIAN_MEETINGS_SUBFOLDER=Meetings

# Arc Directories
ARC_INTAKE_DIR=C:\Users\Lenovo\Desktop\arc\intake
ARC_TEMP_DIR=C:\Users\Lenovo\Desktop\arc\temp
ARC_DB_PATH=C:\Users\Lenovo\Desktop\arc\arc.db

# Server
ARC_SERVER_PORT=8000

# Pipeline
WHISPER_MODEL=large-v3
WHISPER_DEVICE=cuda
OLLAMA_MODEL=gemma4:4b
OLLAMA_HOST=http://localhost:11434

# Optional - Cloudflare Tunnel
CLOUDFLARE_TUNNEL_URL=
```

> Note: `ARC_ARCHIVE_DIR` is replaced by `ARC_TEMP_DIR`. Audio is never considered "archived" — it's temporary storage the user controls.

---

## Folder Structure

```
arc/                                  ← project root (GitHub repo)
│
├── mobile/                           ← React Native / Expo bare app
│   ├── android/                      ← native Android config
│   ├── src/
│   │   ├── screens/
│   │   │   ├── RecorderScreen.tsx    ← main record UI
│   │   │   ├── QRScannerScreen.tsx   ← one-time pairing
│   │   │   └── UploadStatusScreen.tsx
│   │   ├── services/
│   │   │   ├── audioRecorder.ts      ← foreground service logic
│   │   │   ├── uploader.ts           ← HTTP multipart upload
│   │   │   └── storage.ts            ← server URL persistence
│   │   └── App.tsx
│   ├── app.json
│   └── package.json
│
├── server/                           ← FastAPI laptop server
│   ├── main.py                       ← FastAPI app, routes, QR gen
│   ├── pipeline/
│   │   ├── normalizer.py             ← ffmpeg format → WAV 16kHz mono
│   │   ├── transcriber.py            ← faster-whisper integration
│   │   ├── diarizer.py               ← pyannote diarization
│   │   ├── aligner.py                ← merge whisper + pyannote segments
│   │   ├── speaker_db.py             ← resemblyzer embedding store/match
│   │   ├── name_inferrer.py          ← Gemma: infer speaker names from transcript
│   │   ├── note_generator.py         ← Gemma: structured note JSON
│   │   └── vault_writer.py           ← Obsidian folder + markdown writer
│   ├── watcher.py                    ← watchdog folder monitor
│   ├── database.py                   ← SQLite schema + queries
│   ├── templates/                    ← Jinja2 HTML templates
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── naming.html
│   │   └── transcript.html
│   ├── static/                       ← CSS, JS for web UI
│   └── requirements.txt
│
├── intake/                           ← uploaded audio lands here (watched by watchdog)
├── temp/                             ← normalized audio kept here post-processing (user-managed)
├── clips/                            ← 10-second speaker clips for naming UI (deleted after naming)
├── arc.db                            ← SQLite database
│
├── AGENTS.md                         ← Codex CLI project context
├── .env                              ← environment variables (gitignored)
├── .env.example                      ← template (committed)
├── .gitignore
└── README.md
```

> Obsidian vault — meeting folder structure:
```
Meetings/
  2025-05-26-1430-Rahul-Priya/
    note.md             ← summary, decisions, action items, wikilinks
    transcript.md       ← full speaker-tagged transcript (JetBrains Mono)
    audio_ref.txt       ← single line: absolute path to file in arc/temp/
```

---

## Technical Constraints

| Constraint | Implication |
|-----------|------------|
| RTX 4050 — 6GB VRAM | Whisper large-v3 ~3GB VRAM; pyannote ~1GB; pipeline runs sequentially — not parallel |
| Windows 11 | Use `pathlib.Path` throughout — never hardcode `/` separators |
| Expo bare workflow | Requires Android Studio and Java JDK for builds; cannot use Expo Go |
| Local WiFi only | Phone and laptop must be on same network; phone hotspot is fallback |
| Ollama must be running | Pipeline checks Ollama is alive before name inference and note generation; fails gracefully with status "error" if not |
| pyannote requires HuggingFace token | One-time: accept HF terms for pyannote models, set HF_TOKEN env var |
| ffmpeg must be installed | Must be on system PATH; pipeline checks on startup and fails loudly if not found |
| SQLite concurrency | WAL mode — watchdog pipeline and FastAPI server share DB safely |
| Audio is never auto-deleted | Temp folder is user-managed; deletion only via explicit web UI action |

---

## Critical Setup Notes for Codex

When building this project via Codex CLI, the following must be completed manually before the pipeline can run:

1. `ollama pull gemma4:4b` — download model locally
2. Accept pyannote model terms at huggingface.co/pyannote/speaker-diarization-3.1
3. Set `HF_TOKEN` in `.env`
4. Install CUDA toolkit if not present (for faster-whisper GPU mode)
5. Install ffmpeg and confirm it is on system PATH (`ffmpeg -version` in terminal)
6. Configure Obsidian vault path in `.env`
