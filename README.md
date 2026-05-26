# ⚡ Arc — Local-First Personal Meeting Intelligence

<p align="center">
  <img src="ARC logo.png" alt="Arc Logo" width="200" style="border-radius: 10px;"/>
</p>

Arc is a fully local, privacy-respecting, zero-cost meeting intelligence pipeline. It records Hinglish/multilingual audio on an Android device, uploads it to a local FastAPI laptop server over WiFi, processes it through a state-of-the-art sequential ML pipeline, and writes structured summary notes directly to your Obsidian vault. 

**Zero Cloud. Zero Data Leaks. Zero Subscription Fees. Designed for single-user offline productivity.**

---

## 🚀 Key Features

* **📱 Background Android Recording:** A lightweight React Native Expo mobile app utilizing foreground services to record meetings reliably even with the screen locked or off.
* **⚡ WiFi Auto-Upload:** Seamless one-tap upload from your phone directly to your laptop backend server when connected to the same local network.
* **🎙️ Local ML Pipeline:**
  * **Audio Normalization:** `ffmpeg` transforms any format input into standard 16kHz mono WAV.
  * **Transcription:** `faster-whisper` (large-v3 model) optimized via CUDA.
  * **Speaker Diarization:** `pyannote.audio` (speaker-diarization-3.1) identifies who spoke when (supporting up to 8 speakers).
  * **Voice Embedding Matching:** `resemblyzer` extracts high-dimensional speaker voice embeddings and runs cosine-similarity matching (threshold `0.75`) to recognize return speakers.
* **🧠 Ollama (Gemma 3) Orchestration:**
  * **Speaker Naming Inference:** Infers names for unknown speakers from the conversation text (e.g. vocative contexts).
  * **Note Summary & Extraction:** Automatically constructs structured summaries, key decisions, and action items from transcripts.
* **📓 Obsidian Integration:** Dynamically writes structured markdown notes with cross-meeting wikilinks and transcripts directly to your local Obsidian vault in under 10 minutes.

---

## 🏗️ System Architecture

Arc is divided into a frontend mobile app and a backend processing pipeline:

```
                  ┌──────────────────────┐
                  │  Arc Android App     │ (React Native / Expo)
                  │  - Background Rec    │
                  │  - WiFi Upload       │
                  └──────────┬───────────┘
                             │ (WiFi HTTP POST)
                             ▼
                  ┌──────────────────────┐
                  │  FastAPI Backend     │ (Port 8000)
                  │  - REST API & Web UI │
                  │  - SQLite WAL DB     │
                  └──────────┬───────────┘
                             │ (Watcher triggers)
                             ▼
                  ┌──────────────────────┐
                  │  Sequential ML       │ (VRAM Optimized Pipeline)
                  │  Pipeline            │
                  └──────────┬───────────┘
                             ├─► normalizer.py (ffmpeg -> 16kHz mono WAV)
                             ├─► transcriber.py (faster-whisper CUDA)
                             ├─► diarizer.py (pyannote.audio 3.1)
                             ├─► aligner.py (overlap align transcripts & speakers)
                             ├─► speaker_db.py (resemblyzer embeddings comparison)
                             ├─► name_inferrer.py (Ollama Gemma 3:4b vocative naming)
                             ├─► note_generator.py (Ollama Gemma 3:4b structured JSON summary)
                             └─► vault_writer.py (Obsidian markdown exporter)
```

---

## 🛠️ One-Time Setup & Installation

### 1. Python Environment Setup
Create a virtual environment and install all dependencies. 
Note that PyTorch with CUDA 12.4 must be installed first:

```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install PyTorch with CUDA 12.4
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Install webrtcvad-wheels (Windows/Python 3.13 pre-requisite for resemblyzer)
pip install webrtcvad-wheels

# Install required main dependencies
pip install -r requirements.txt

# Install resemblyzer without dependencies to bypass compile errors
pip install resemblyzer==0.1.1.dev0 --no-deps

# Install remaining resemblyzer dependencies
pip install librosa

# Install test dependencies
pip install -r requirements-test.txt
```

### 2. External System Dependencies
* **FFmpeg:** Ensure `ffmpeg` is installed and added to your system's PATH. Verify using `ffmpeg -version`.
* **Ollama:** Download and install Ollama from [ollama.com](https://ollama.com). Pull the model:
  ```powershell
  ollama pull gemma3:4b
  ```
* **Hugging Face Account & PyAnnote Agreement:**
  1. Accept the model terms at [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1).
  2. Accept the model terms at [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0).
  3. Generate a read-scope Access Token in your Hugging Face account settings to place in your `.env`.

### 3. Environment Configuration
Copy `.env.example` to `.env` and fill in the required parameters:
```env
OBSIDIAN_VAULT_PATH=C:\Users\Lenovo\Desktop\Code\Obsidan Stronghold\MyBrain\Arc_holder
HF_TOKEN=hf_your_huggingface_access_token_here
```

---

## 🏃 Running the Application

### 1. Starting the Backend Server
First, make sure Ollama is running, then start the FastAPI application:

```powershell
# In terminal 1: Start Ollama (if not already running)
ollama serve

# In terminal 2: Start the FastAPI App
.\.venv\Scripts\uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

# In terminal 3: Start the directory Watcher
.\.venv\Scripts\python server/watcher.py
```
Open `http://localhost:8000` in your browser to view the meeting intelligence dashboard, or `http://localhost:8000/qr` to pair your mobile app.

### 2. Starting the React Native Mobile Client
Ensure Node.js is installed, then run the Expo server:
```powershell
cd mobile
npm install
npx expo start --clear
```
Scan the Expo QR code using your physical Android phone (running the Expo Go app) on the same WiFi network. Once opened, scan the dashboard pairing QR code (`http://localhost:8000/qr`) to pair your mobile app with your backend server.

---

## 🧪 Running Tests

Ensure test dependencies are installed, then run:
```powershell
.\.venv\Scripts\pytest tests/ -m "not ml" --tb=short
```
*Note: Tests marked `ml` require a GPU, CUDA, and model downloads, and are skipped locally by default.*

---

## 📂 Project Structure

```
Arc/
├── mobile/                   # React Native Expo Android App
│   ├── src/                  # App components & navigation
│   └── package.json          # Node dependencies & Expo config
├── server/                   # FastAPI backend server
│   ├── main.py               # REST API entrypoint & routes
│   ├── watcher.py            # Local directory watcher using watchdog
│   ├── database.py           # SQLite db initialization & queries
│   ├── pipeline/             # Sequential ML Pipeline
│   │   ├── normalizer.py     # ffmpeg audio normalizer
│   │   ├── transcriber.py    # faster-whisper transcribing
│   │   ├── diarizer.py       # pyannote speaker-diarization
│   │   ├── aligner.py        # speaker & transcript segment aligner
│   │   ├── speaker_db.py     # resemblyzer embedding database
│   │   ├── name_inferrer.py  # Gemma-based speaker naming
│   │   ├── note_generator.py # Gemma structured summary generation
│   │   └── vault_writer.py   # Obsidian vault output writer
│   └── templates/            # Jinja2 dashboard UI templates
├── files/                    # Project PRD, TRD and Design Briefs
├── tests/                    # Backend pytest suite
├── requirements.txt          # Python dependencies
└── requirements-test.txt     # Python test dependencies
```

---

## 🛡️ License

This project is personal and private, configured under [SECURITY.md](file:///C:/Users/Lenovo/Desktop/Code/2026/Arc/SECURITY.md) guidelines.
