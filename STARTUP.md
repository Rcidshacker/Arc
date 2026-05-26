# Arc — Startup Guide

Local-first meeting intelligence. Android records → uploads to laptop over WiFi → ML pipeline → Obsidian note.

---

## One-Time Setup

### 1. Python dependencies

PyTorch must be installed before the rest of the requirements, with the CUDA 12.4 index.

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
```

> **Python 3.13 caveat:** If `resemblyzer` fails during install with a `webrtcvad` build error, run:
> ```powershell
> pip install webrtcvad-wheels
> pip install resemblyzer==0.1.1.dev0
> ```

### 2. ffmpeg

Check if it is on PATH:

```powershell
ffmpeg -version
```

If missing, download from https://ffmpeg.org/download.html and add the `bin/` folder to your system PATH.

### 3. Ollama model

```powershell
ollama pull gemma3:4b
```

Downloads ~2.5 GB. Ollama must be installed first — https://ollama.com.

### 4. Accept pyannote terms

Go to https://huggingface.co/pyannote/speaker-diarization-3.1 and accept the model terms while logged in with the account whose token you will use in `.env`.

### 5. Environment file

```powershell
Copy-Item .env.example .env
```

Open `.env` and fill in the two required values:

| Variable | What to set |
|---|---|
| `OBSIDIAN_VAULT_PATH` | Absolute path to your Obsidian vault root |
| `HF_TOKEN` | Your HuggingFace access token (read scope is enough) |

All other defaults are fine for a first run. `ARC_INTAKE_DIR`, `ARC_TEMP_DIR`, and the directory containing `ARC_DB_PATH` are created automatically on first startup.

---

## Starting the Backend

Open two PowerShell terminals in the Arc repo root.

**Terminal 1 — Ollama**

```powershell
ollama serve
```

Must be running before any pipeline step that calls Gemma.

**Terminal 2 — FastAPI server**

```powershell
uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
```

On startup the server:
- Initialises the SQLite database (`arc.db`)
- Generates a pairing QR code at `http://localhost:8000/qr`
- Starts the `watcher.py` thread watching the `intake/` directory

**Useful URLs once running:**

| URL | Purpose |
|---|---|
| `http://localhost:8000` | Dashboard — list of all meetings |
| `http://localhost:8000/qr` | QR code for phone pairing |

> The watcher is embedded in the server process. You do not need to run `server/watcher.py` separately unless you want an isolated watcher process for debugging.

---

## Starting the Mobile App (dev)

### Prerequisites

- Node.js 18+
- Expo CLI: `npm install -g expo-cli`
- Android Studio with JDK 17 and an Android SDK installed
- Physical Android device or emulator on the **same WiFi network** as the laptop

### Install dependencies

```powershell
cd mobile
npm install
```

### Run in dev mode

```powershell
npx expo start --clear
```

Scan the Expo QR code with the Expo Go app on your phone, or press `a` to open in an Android emulator.

### Pair with the server

1. Open `http://localhost:8000/qr` in a browser on the laptop.
2. In the Arc mobile app, use the QR scanner screen to scan that code.
3. Pairing is stored on the device; you only do this once per install.

### Build a release APK

```powershell
npx expo prebuild --platform android
eas build --platform android --local
```

Requires EAS CLI (`npm install -g eas-cli`) and a configured `eas.json`.

---

## Running Tests

```powershell
pytest tests/ -m "not ml" --tb=short
```

Tests tagged `ml` require a GPU, CUDA, and the downloaded model files. They are excluded from CI and local runs where those are unavailable.

---

## Troubleshooting

**Ollama not running**
```
Error: connection refused at http://localhost:11434
```
Start Ollama in a separate terminal: `ollama serve`

**CUDA not found / pipeline falls back to CPU**
```powershell
nvidia-smi          # verify GPU is visible
python -c "import torch; print(torch.cuda.is_available())"
```
If `False`, reinstall PyTorch with the cu124 index (step 1 above).

**pyannote authentication fails**
```
401 Unauthorized
```
Check that `HF_TOKEN` in `.env` is correct and that you accepted the model terms at HuggingFace while logged into that account.

**resemblyzer install fails**
Install the pre-built VAD wheel first:
```powershell
pip install webrtcvad-wheels
pip install resemblyzer==0.1.1.dev0
```

**Port 8000 already in use**
Change `ARC_SERVER_PORT` in `.env` to a free port (e.g. `8001`), then restart the server.

**Meeting stuck at `needs_naming`**
The pipeline paused because it found an unknown speaker. Open `http://localhost:8000`, click the meeting, review the suggested name, and confirm or override. The pipeline resumes automatically.
