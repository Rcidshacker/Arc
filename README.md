div align="center">

# 🌌 Arc

**Local-first personal meeting intelligence for Hinglish conversations.**

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com/)
[![React Native](https://img.shields.io/badge/React_Native-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://reactnative.dev/)
[![Expo](https://img.shields.io/badge/Expo-000020?style=for-the-badge&logo=expo&logoColor=white)](https://expo.dev/)
[![llama.cpp](https://img.shields.io/badge/llama.cpp-CUDA-orange?style=for-the-badge)](https://github.com/ggerganov/llama.cpp)
[![Obsidian](https://img.shields.io/badge/Obsidian-7C3AED?style=for-the-badge&logo=obsidian&logoColor=white)](https://obsidian.md/)

</div>

---

Arc is a local-first personal meeting intelligence system. Android records meetings (even with screen off) → uploads to a FastAPI laptop server over WiFi → sequential ML pipeline (ffmpeg → whisper-cli.exe → pyannote → Gemma 4 via llama-server) → structured Obsidian vault note in under 10 minutes. Zero cloud. Zero cost. Single user.

---

## 📱 Features

### 📱 Android App (Expo SDK 54)
- **Background audio recording** — continues with screen off (via Android Foreground Service)
- **Custom splash screen** with video animation
- **Library screen** — manage, playback, and select recordings to send
- **Import audio files** from phone storage
- **WiFi upload** with per-file progress bars and ETA
- **QR code pairing** with laptop server
- **Connection animation** with server health check
- **User profile** — name registration for meeting labels
- **Works in Expo Go** for testing; APK build for full background recording

### 🖥️ Web Dashboard
- **Meeting list** with status tracking (`uploaded` → `needs_naming` → `processing` → `done`/`error`)
- **Speaker naming UI** with audio clip playback
- **Delete individual meetings** or bulk-delete errors
- **Phone recordings** labelled with sender name and device source
- **QR Pair page** to display server connection QR code
- **Landing page**

### ⚙️ Pipeline (Laptop, fully local)
- **ffmpeg normalization** → WAV 16kHz mono
- **whisper-cli.exe** (whisper.cpp CUDA) transcription — Hinglish support
- **pyannote speaker diarization** (fault-tolerant, degrades to single speaker)
- **Speaker alignment** + name inference via Gemma 4
- **Note generation** with Gemma 4 thinking mode → structured JSON → Markdown
- **Obsidian vault write** via MCP or direct pathlib fallback
- **SQLite state machine**: `uploaded` → `needs_naming` → `processing` → `done`/`error`

### 💬 Arc Chat (RAG Chat Interface)
- **Claude.ai-style chat UI** on the web dashboard
- **Obsidian vault** as knowledge base (BM25 keyword search with score threshold)
- **Strict RAG** — answers only from your notes ("*I don't have notes on that topic.*" when no relevant content is found)
- **Thinking mode toggle** — Gemma 4 extended reasoning via `<|think|>`
- **Effort control** — Low / Medium / High (controls context depth and chunk count)
- **Internet toggle** — Gemma 4 tool calling with web search
- **File uploads** — images (Gemma 4 multimodal vision), PDFs, DOCX, TXT
- **Write back** to Obsidian vault from chat
- **Persistent chat sessions** with history
- **Streaming responses** with collapsible thinking blocks
- **Markdown rendering** with syntax highlighting

---

## 🏗️ Architecture

Arc uses a distributed local-first architecture optimized for single-GPU setups (e.g. laptop with RTX 4050 6GB VRAM) where VRAM constraints prevent running pyannote and llama-server simultaneously. 

### Core Components
- **mobile/**: React Native Expo SDK 54 app (bare workflow pending prebuild) handling low-power background recording and local WiFi transmission.
- **server/**: FastAPI server running on the laptop, serving endpoints, the web UI dashboard, and coordinate workflows.
- **server/chat/**: RAG engine, chat routes, file processor, and streaming engine.
- **server/pipeline/**: Sequential ML steps ensuring that only one model occupies the GPU at a time.

### Required Services
The system coordinates three running processes:
1. **FastAPI server** (`:8000`): Main API, dashboard UI, and file ingestion.
2. **llama-server** (`:8081`): Serves Gemma 4 for transcription (llamacpp) and note generation.
3. **Obsidian MCP server** (`:3100`): Allows write and query access to the Obsidian vault.

```
                      ┌─────────────────────────────────────────┐
                      │          📱 Android Mobile App          │
                      │        (React Native Expo SDK 54)       │
                      └────────────────────┬────────────────────┘
                                           │
                                           │ (WiFi Upload over HTTP)
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │         🖥️ FastAPI Laptop Server        │
                      │          (Port 8000, SQLite WAL)        │
                      └────────────┬─────────────────┬──────────┘
                                   │                 │
              (Triggers Watcher)   │                 │ (Arc Chat RAG UI)
                                   ▼                 ▼
 ┌─────────────────────────────────────────┐   ┌─────────────────────────────────────────┐
 │             ⚙️ ML Pipeline              │   │               💬 Arc Chat               │
 │     Sequential Execution (RTX CUDA)     │   │      (RAG, BM25 Search, Streaming)      │
 └─────────────────┬───────────────────────┘   └─────────────────┬───────────────────────┘
                   │                                             │
                   │ (ffmpeg → whisper → pyannote → Gemma 4)     │ (strict context answers)
                   ▼                                             ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │                                   📓 Obsidian Vault                                   │
 │             Structured Notes (Markdown + YAML) & Obsidian MCP (:3100)                 │
 └───────────────────────────────────────────────────────────────────────────────────────┘
```

### Project Structure

```
Arc/
├── server/
│   ├── main.py              # FastAPI app — REST API + Jinja2 web UI
│   ├── watcher.py           # Polling loop (2s) on intake/; Python 3.13 safe
│   ├── database.py          # SQLite schema + all queries
│   ├── chat/                # RAG engine, chat routes, file processor, streaming engine
│   │   ├── engine.py        # Chat response streaming & engine
│   │   ├── file_processor.py# PDF, docx, txt, and image parsing
│   │   ├── rag.py           # BM25 knowledge search over Obsidian vault
│   │   └── routes.py        # Web chat endpoints
│   ├── pipeline/
│   │   ├── normalizer.py    # ffmpeg → 16 kHz mono WAV
│   │   ├── transcriber.py   # llamacpp / groq / gemini provider routing
│   │   ├── diarizer.py      # pyannote 3.1 with three runtime patches
│   │   ├── aligner.py       # overlap-match transcript ↔ speaker turns
│   │   ├── speaker_db.py    # clip extraction; all labels → needs_naming
│   │   ├── name_inferrer.py # Gemma — infer names from vocative context
│   │   ├── note_generator.py# Gemma 4 thinking mode → structured JSON
│   │   └── vault_writer.py  # write Obsidian folder (MCP → pathlib fallback)
│   └── templates/           # dashboard, transcript, naming, qr, landing, chat
├── mobile/
│   ├── App.tsx              # React Navigation + gesture handler setup
│   └── src/
│       ├── screens/         # RecorderScreen, QRScannerScreen, LibraryScreen
│       └── services/        # audioRecorder.ts, uploader.ts
├── tests/                   # pytest suite (skip ml-tagged tests locally)
├── requirements.txt
├── .env.example
└── CLAUDE.md
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.13
- Node.js (for mobile)
- `ffmpeg` on your `PATH` — verify with `ffmpeg -version`
- llama-server running with a Gemma 4 model on port `8081`
- [Accept pyannote terms](https://huggingface.co/pyannote/speaker-diarization-3.1) on Hugging Face (required for diarization)
- Whisper CLI binary + `ggml-large-v3-turbo.bin` model (if using default llamacpp transcription)

### Installation

```powershell
# Create and activate venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install PyTorch with CUDA 12.4 first
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Windows prerequisite for resemblyzer
pip install webrtcvad-wheels

# Main dependencies
pip install -r requirements.txt

# resemblyzer needs --no-deps to avoid compile errors on Windows
pip install resemblyzer==0.1.1.dev0 --no-deps
pip install librosa
```

### Configuration

Copy `.env.example` to `.env` and fill in the required values:

```env
# Obsidian vault
OBSIDIAN_VAULT_PATH=C:\Users\YourName\path\to\obsidian\vault
OBSIDIAN_MEETINGS_SUBFOLDER=Meetings
# Obsidian MCP SSE endpoint (vault_writer tries this before direct writes)
OBSIDIAN_MCP_URL=http://localhost:3100/sse

# Arc working directories (created on first run)
ARC_INTAKE_DIR=C:\Users\YourName\Desktop\arc\intake
ARC_TEMP_DIR=C:\Users\YourName\Desktop\arc\temp
ARC_DB_PATH=C:\Users\YourName\Desktop\arc\arc.db

# Server
ARC_SERVER_PORT=8000

# HuggingFace token (required for pyannote diarization)
HF_TOKEN=your_hf_token_here

# Transcription: llamacpp (default), groq, or gemini
TRANSCRIPTION_PROVIDER=llamacpp

# whisper-cli paths (required if TRANSCRIPTION_PROVIDER=llamacpp)
WHISPER_CLI_PATH=C:\llama\whisper\whisper-cli.exe
WHISPER_MODEL_PATH=C:\llama\whisper\models\ggml-large-v3-turbo.bin
WHISPER_LANGUAGE=hi

# llama-server for note generation & transcription
LLAMACPP_HOST=http://localhost:8081

# Cloud fallbacks (only needed if using groq or gemini provider)
GROQ_API_KEY=your_groq_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
```

### Running the Services

Three services are required to run simultaneously:

```powershell
# 1. llama-server with Gemma 4 (manage in a separate terminal)
# e.g., llama-server -m gemma-4-e4b.gguf --port 8081

# 2. FastAPI Backend & Watcher (Windows PowerShell with PYTHONPATH fix)
$env:PYTHONPATH="server"; .venv\Scripts\uvicorn.exe server.main:app --host 0.0.0.0 --port 8000 --reload
```

Open these local URLs to interact with Arc:
- **Web Dashboard**: `http://localhost:8000`
- **Arc Chat Interface**: `http://localhost:8000/chat`
- **QR Pairing Page**: `http://localhost:8000/qr`

### Mobile App Setup

```powershell
cd mobile
npm install --legacy-peer-deps

# Start Expo Go testing
npx expo start          

# Build standalone APK
npx expo prebuild --platform android
# Build commands (requires Android Studio + JDK)
# (see mobile/android-setup-notes.md for detailed steps)
```

---

## ⚖️ Hard Rules

*Strict guidelines enforced across the codebase:*

- **Windows Path Safety**: Always use `pathlib.Path` for all filesystem operations. Never hardcode `/` or `\` path separators.
- **ffmpeg Subprocesses**: Never run ffmpeg with `shell=True`. Always pass arguments as a list of strings:
  ```python
  subprocess.run(["ffmpeg", "-y", "-i", str(input_path), "-ar", "16000", "-ac", "1", str(output_path)], check=True)
  ```
- **SQLite Concurrency**: Always open connection with WAL mode and `check_same_thread=False` to handle concurrent access from both server and watcher. All queries must be parameterized to prevent SQL injection.
- **Audio Deletion Safe Guards**: Audio is never auto-deleted. Deleting raw audio requires explicit `DELETE /meeting/{id}/audio`. Verify paths with `Path.resolve()` to ensure target file is a descendant of `ARC_TEMP_DIR` to prevent path traversal vulnerability.
- **llama-server Connectivity**: Validate llama-server availability before starting note generation. If down, immediately fail the pipeline with status `error`.
- **Obsidian DB Entries**: Store Obsidian paths in the DB relative to the vault root (e.g. `Meetings/2025-05-26-1430-Rahul-Priya/`). Resolve them dynamically using the `OBSIDIAN_VAULT_PATH` environment variable.
- **API Response Structure**: Every API response must strictly follow the format: `{success: bool, data: any, error: str | null}`. Return `409` for hash conflicts on duplicate uploads.

---

## 🔮 Roadmap

- **Speaker Embedding Matching** — `speaker_db.py` is currently an MVP stub. Cross-session resemblyzer cosine matching (threshold `0.75`) is planned for v2; speakers currently go through the naming UI every time.
- **Auto Name Inference** — `name_inferrer.py` calls Gemma for vocative-context inference but is not fully active by default in the pipeline flow.
- **Standalone pyannote Setup** — If `pyannote` is missing, the diarizer falls back to single-speaker mode. Full multi-speaker support requires `pip install pyannote.audio` and agreeing to model terms.

---

## 🤝 Contributing

This is a single-user personal project built for specific developer needs. Pull requests are not actively monitored.

## 📄 License

Private — all rights reserved. No public distribution or licensing granted.
