<div align="center">

# Arc

**Local meeting intelligence for Hinglish conversations**

`Local-First` &nbsp;·&nbsp; `Hinglish-Native` &nbsp;·&nbsp; `Zero Cloud`

</div>

---

Android records your meeting with screen off → uploads over WiFi to a laptop FastAPI server → sequential ML pipeline transcribes, diarizes, and generates structured notes → writes to your Obsidian vault in under 10 minutes. No cloud APIs required for the default path. Single-user, zero cost.

<!-- Add demo GIF here -->

---

## How It Works

1. 🎙️ **Record** — Android app runs a foreground service, keeps recording alive with screen off
2. 📤 **Upload** — one-tap WiFi upload to the FastAPI server on the same network
3. 🔊 **Normalize** — `ffmpeg` converts any format to 16 kHz mono WAV
4. 📝 **Transcribe** — `whisper-cli.exe` (`ggml-large-v3-turbo`) via subprocess; fallback to Groq or Gemini
5. 👥 **Diarize** — `pyannote/speaker-diarization-3.1` segments by speaker (up to 8)
6. 🔗 **Align** — overlap-match whisper segments to pyannote speaker labels
7. 🗂️ **Speaker DB** — extracts 10s clip per label; pipeline halts at `needs_naming`
8. ✍️ **Name** — web UI plays clips, you assign names to `SPEAKER_00`, `SPEAKER_01`, etc.
9. 🧠 **Generate note** — Gemma 4 via llama-server (thinking mode) → structured JSON
10. 📓 **Write to vault** — Obsidian folder with `note.md`, `transcript.md`, `audio_ref.txt`

---

## Features

| | Feature | Details |
|---|---|---|
| 🔒 | Local-first | No audio leaves the machine |
| 🌐 | Multi-provider transcription | llamacpp (default) · Groq · Gemini |
| 👤 | Speaker diarization | pyannote 3.1, up to 8 speakers |
| 🎵 | Audio clip preview | 10s per-speaker WAV clips in naming UI |
| 📊 | Web dashboard | Status polling, transcript view, speaker summary |
| 📓 | Obsidian output | YAML frontmatter, wikilinks, full transcript |
| 🔄 | Duplicate detection | SHA-256 hash check on upload (409 on collision) |
| 🗄️ | SQLite WAL | Concurrent server + watcher access, all queries parameterized |

---

## Tech Stack

### Audio Pipeline
| Component | Library / Tool |
|---|---|
| Normalization | ffmpeg subprocess (`shell=False`) |
| Transcription (default) | whisper-cli.exe · ggml-large-v3-turbo |
| Transcription (cloud fallback) | Groq whisper-large-v3-turbo · Gemini 2.5 Flash |
| Diarization | pyannote/speaker-diarization-3.1 |
| Speaker alignment | custom overlap matcher |

### Intelligence Layer
| Component | Library / Tool |
|---|---|
| Note generation | Gemma 4 via llama-server (port 8081) |
| Reasoning | `<\|think\|>` prefix → extended thinking mode |
| Speaker naming inference | `name_inferrer.py` (wired up, inactive by default) |

### Application Layer
| Component | Library / Tool |
|---|---|
| API server | FastAPI + uvicorn |
| Web UI | Jinja2 templates |
| Database | SQLite WAL |
| Mobile app | React Native · Expo SDK 54 (Android) |
| QR pairing | qrcode library |

---

## Getting Started

### Prerequisites

- Python 3.13
- Node.js (for mobile)
- ffmpeg on `PATH` — verify with `ffmpeg -version`
- llama-server running with a Gemma 4 model on port 8081
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

# llama-server for note generation
LLAMACPP_HOST=http://localhost:8081

# Cloud fallbacks (only needed if using groq or gemini provider)
GROQ_API_KEY=your_groq_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
```

### Running

Three processes required:

```powershell
# Terminal 1: llama-server with Gemma 4 (manage separately)
# e.g. llama-server -m gemma-4-e4b.gguf --port 8081

# Terminal 2: FastAPI server (also starts the watcher as a background thread)
uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

# Optional Terminal 3: standalone watcher (if not using --reload)
python server/watcher.py
```

Open `http://localhost:8000` for the dashboard. Open `http://localhost:8000/qr` to pair the mobile app.

---

## Project Structure

```
Arc/
├── server/
│   ├── main.py              # FastAPI app — REST API + Jinja2 web UI
│   ├── watcher.py           # Polling loop (2s) on intake/; Python 3.13 safe
│   ├── database.py          # SQLite schema + all queries
│   ├── pipeline/
│   │   ├── normalizer.py    # ffmpeg → 16 kHz mono WAV
│   │   ├── transcriber.py   # llamacpp / groq / gemini provider routing
│   │   ├── diarizer.py      # pyannote 3.1 with three runtime patches
│   │   ├── aligner.py       # overlap-match transcript ↔ speaker turns
│   │   ├── speaker_db.py    # clip extraction; all labels → needs_naming
│   │   ├── name_inferrer.py # Gemma — infer names from vocative context
│   │   ├── note_generator.py# Gemma 4 thinking mode → structured JSON
│   │   └── vault_writer.py  # write Obsidian folder (MCP → pathlib fallback)
│   └── templates/           # dashboard, transcript, naming, qr, landing
├── mobile/
│   ├── App.tsx              # React Navigation + gesture handler setup
│   └── src/
│       ├── screens/         # RecorderScreen, QRScannerScreen
│       └── services/        # audioRecorder.ts, uploader.ts
├── tests/                   # pytest suite (skip ml-tagged tests locally)
├── requirements.txt
├── .env.example
└── CLAUDE.md
```

---

## Roadmap

- **Speaker embedding matching** — `speaker_db.py` is an intentional MVP stub. Cross-session resemblyzer cosine matching (threshold `0.75`) is v2; all speakers currently go through the naming UI every time.
- **name_inferrer activation** — `name_inferrer.py` exists and calls Gemma for vocative-context inference but is not wired into the pipeline execution path yet.
- **pyannote.audio install** — diarization degrades to single-speaker fallback if pyannote is missing. Full multi-speaker output requires `pip install pyannote.audio` and accepted model terms.
- **Mobile Android build** — Expo SDK 54 configured; native APK build requires Android Studio + JDK + `eas build --platform android --local`.

---

## Contributing

Single-user personal project. PRs not expected. If you fork and adapt it, the key constraint is sequential pipeline execution — the RTX 4050 has 6 GB VRAM and cannot run pyannote and llama-server simultaneously.

## License

Private — no public license granted.
