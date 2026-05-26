# Implementation Plan — Arc
### Phased Build Sequence for Codex CLI

---

## Overall Done Criteria (v1)

Arc v1 is complete when:
- A 1-hour meeting recorded on Android with screen off produces a correctly structured, speaker-named Obsidian note in under 10 minutes
- The same speaker is correctly identified across at least 2 separate meetings without re-naming
- Claude Desktop can answer "what did [speaker] say about [topic]?" accurately via Obsidian MCP
- Zero manual steps required between recording and note appearing in vault (excluding one-time speaker naming on first encounter)

---

## Codex CLI Setup (Before Phase 1)

```bash
# Install Codex CLI on Windows
powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"

# Navigate to project root
cd C:\Users\Lenovo\Desktop\arc

# Initialise — creates AGENTS.md template
codex /init

# Replace AGENTS.md with the one from this repo
# Then start working phase by phase
codex "Build Phase 1: FastAPI server with QR code generation and upload endpoint"
```

---

## AGENTS.md Content (paste this into your repo root)

```markdown
# Arc — AGENTS.md

## Project
Arc is a personal meeting intelligence app. Android phone records meetings 
(screen off). Audio uploads to a local FastAPI server on a Windows laptop 
via WiFi. A Python pipeline transcribes (faster-whisper), diarizes 
(pyannote), matches speakers (resemblyzer), generates Obsidian notes 
(Ollama Gemma 4:4B), and writes them to a local Obsidian vault.

## Stack
- Mobile: React Native Expo bare workflow (Android only)
- Server: FastAPI + uvicorn on Windows localhost
- DB: SQLite with WAL mode
- LLM: Ollama Gemma 4:4B at http://localhost:11434
- Transcription: faster-whisper large-v3 (CUDA)
- Diarization: pyannote.audio 3.x
- Speaker matching: resemblyzer

## Rules
- Use pathlib.Path for all file paths — never hardcode separators
- All env vars loaded from .env via python-dotenv
- SQLite connections must use WAL mode and check_same_thread=False
- Never write audio files outside of intake/ or archive/ directories
- Pipeline steps are sequential — do not parallelise (VRAM constraint)
- All API responses must be JSON with {success: bool, data: any, error: str|null}
- Web UI templates live in server/templates/ as Jinja2 .html files
- Never install packages not in requirements.txt without asking
```

---

## Phase 1 — Project Setup + FastAPI Server + QR Upload

**Goal:** Phone can upload an audio file to laptop. Server generates QR. Deduplication works.

**Codex prompt:**
```
Build the FastAPI server in server/main.py with:
1. QR code generation on startup — detect local IP, generate QR containing 
   http://[local-ip]:8000, display in terminal and serve at GET /qr
2. POST /upload endpoint — receive multipart audio file, compute SHA256, 
   check upload_log table for duplicate, reject with 409 if duplicate, 
   save to intake/ dir if new, create meeting record in SQLite with 
   status="uploaded", return {success, meeting_id, sha256}
3. GET /status/{meeting_id} — return current meeting status from SQLite
4. SQLite initialisation — create all tables from schema on first run, 
   WAL mode enabled
5. GET / — basic dashboard HTML showing all meetings (Jinja2 template)
6. Serve static files from server/static/
Set up requirements.txt with all dependencies.
```

**Done when:**
- `uvicorn server.main:app` starts without errors
- QR code appears in terminal on startup containing correct local IP
- Curl upload of test MP3 returns meeting_id and sha256
- Second identical upload returns 409 with "duplicate" reason
- `http://localhost:8000` loads dashboard HTML

---

## Phase 2 — Android Recording App

**Goal:** Clean background recording on Android with screen off. QR scan pairing. One-tap upload.

**Codex prompt:**
```
Build the React Native Expo bare Android app in mobile/ with:
1. QRScannerScreen — camera view using expo-camera, scan QR containing 
   server URL, save URL to AsyncStorage, navigate to RecorderScreen
2. RecorderScreen — centered circle button (96px), white idle / red active,
   tap to start recording via expo-av in AAC format 128kbps,
   timer display showing elapsed time (HH:MM:SS),
   tap stop → save file → trigger upload → navigate to UploadStatusScreen
3. Android Foreground Service via @voximplant/react-native-foreground-service —
   start on record, stop on stop, notification: "Arc · Recording in progress"
4. UploadStatusScreen — show upload progress via axios with onUploadProgress,
   success message, error with retry button
5. App navigates to QRScannerScreen on first launch (no saved URL),
   RecorderScreen on subsequent launches
Dark theme throughout: background #0A0A0A, button #EF4444 when recording.
```

**Done when:**
- APK builds successfully with `eas build --platform android --local`
- 10-minute test recording completes with screen locked
- File uploads to FastAPI server — meeting appears in dashboard
- Duplicate upload shows error on UploadStatusScreen

---

## Phase 3 — Transcription + Diarization Pipeline

**Goal:** Audio file → speaker-segmented transcript JSON stored in SQLite.

**Codex prompt:**
```
Build the Python pipeline in server/pipeline/ with:
1. transcriber.py — load faster-whisper large-v3 on CUDA, transcribe 
   audio file, return list of {start, end, text, confidence} segments,
   language detection hint: ["hi", "en"]
2. diarizer.py — load pyannote speaker-diarization-3.1 using HF_TOKEN 
   from env, diarize audio file, return list of {start, end, speaker_label},
   max_speakers=8
3. aligner.py — merge whisper segments and pyannote segments by maximum 
   overlap matching, return list of {start, end, speaker_label, text}
4. speaker_db.py — resemblyzer integration:
   - extract_embedding(audio_path, start, end) → 256-dim float32 vector
   - match_speaker(embedding) → speaker_id if cosine_similarity > 0.75, 
     else None
   - save_speaker(name, embedding, meeting_id) → speaker_id
   - save all to SQLite speakers table as binary blob
5. watcher.py — watchdog FileSystemEventHandler monitoring intake/ dir,
   on new .m4a/.aac file: trigger full pipeline, update meeting status 
   at each step, handle exceptions → set status="error" with message
Build a CLI runner: python server/watcher.py to start monitoring.
```

**Done when:**
- `python server/watcher.py` starts without errors
- Drop test audio into intake/ → transcript_segments populated in SQLite within 5 minutes
- Same test speaker across 2 recordings matched to same speaker_id

---

## Phase 4 — Speaker Naming UI + Pipeline Resume

**Goal:** Unknown speakers flagged in web UI. Ruchit names them. Pipeline resumes.

**Codex prompt:**
```
Build the speaker naming flow:
1. When pipeline detects unknown speakers (match_speaker returns None):
   - Extract 10-second clip per unknown speaker_label using soundfile
   - Save to server/clips/{meeting_id}_{speaker_label}.wav
   - Set meeting status = "needs_naming"
2. GET /naming/{meeting_id} — Jinja2 template showing:
   - One card per unknown speaker
   - Play button serving GET /clip/{meeting_id}/{speaker_label}
   - Text input for speaker name
   - "Save Names" button
3. POST /speaker/name — receive {meeting_id, names: [{label, name}]},
   save each as new speaker with embedding in SQLite,
   update transcript_segments with resolved speaker_ids,
   set meeting status = "uploaded" to re-trigger pipeline from step 4
4. Dashboard badge: amber "Needs naming" on meetings awaiting this step,
   clickable → /naming/{id}
5. GET /clip/{meeting_id}/{speaker_label} — serve audio clip file
Style: dark theme, Inter font, consistent with design brief.
```

**Done when:**
- New meeting with unknown speaker → dashboard shows amber "Needs naming" badge
- Click badge → naming page loads with clip player and text inputs
- Submit names → pipeline resumes → note generated → status = "done"

---

## Phase 5 — Obsidian Note Generation

**Goal:** Speaker-named transcript → structured Obsidian markdown in vault.

**Codex prompt:**
```
Build note_generator.py and vault_writer.py:
1. note_generator.py:
   - Connect to Ollama at OLLAMA_HOST, use model OLLAMA_MODEL
   - Build prompt from system template and user template in schema doc
   - Send tagged transcript (format: "[SpeakerName] (MM:SS): text\n")
   - Parse JSON response — handle malformed JSON with retry (max 2)
   - Return structured dict matching schema
2. vault_writer.py:
   - Render Obsidian markdown from structured dict using the note template 
     in the schema doc
   - Speaker names wrapped in [[wikilinks]]
   - Concepts list → add to concepts table in SQLite + meeting_concepts
   - Write file to OBSIDIAN_VAULT_PATH/OBSIDIAN_MEETINGS_SUBFOLDER/
   - Filename: YYYY-MM-DD-HHMM-[first-two-speaker-names].md
   - Update meeting record: obsidian_note_path, status = "done"
   - Move audio from intake/ to archive/
3. Add meeting detail page GET /meeting/{id} showing:
   - Transcript tab: speaker-coloured segments in JetBrains Mono
   - Summary tab: rendered note sections
   - Link to open note path
```

**Done when:**
- End-to-end: upload audio → name speakers → note appears in Obsidian vault
- Note frontmatter is valid YAML (test: open in Obsidian, check graph view)
- Concepts appear as working [[wikilinks]] in Obsidian

---

## Phase 6 — Cross-Meeting Linking + MCP Validation

**Goal:** Knowledge threads across meetings. MCP queries return accurate results.

**Codex prompt:**
```
Build cross-meeting concept threading:
1. When writing a new note, check concepts table for existing concepts 
   matching extracted concepts from the new meeting
2. In the new note, link to previous meetings that share the same concept:
   "This topic was also discussed in [[2025-05-20-1430-Rahul-Priya]]"
3. In the speaker section of each note, add a backlink section:
   "[[Rahul]] has also spoken in: [[previous-meeting-1]], [[previous-meeting-2]]"
4. Add a GET /stats endpoint to web UI showing:
   - Total meetings processed
   - Total speakers known  
   - Most discussed concepts
   - Speaker participation across meetings
Run end-to-end test with 3 real meeting recordings, then query Claude 
Desktop via Obsidian MCP to validate:
- "What did [speaker] say about [topic] across all meetings?"
- "What decisions were made this week?"
- "What are the open action items for [speaker]?"
```

**Done when:**
- 3 meetings processed, concepts linked across notes
- MCP query returns accurate speaker-attributed answers with meeting references

---

## Phase 7 — Polish + Edge Cases

**Goal:** App handles real-world messiness without crashing.

**Tasks:**
- Test with 60-minute meeting audio (stress test VRAM usage)
- Test with 6-speaker meeting (diarization accuracy check)
- Test with poor audio quality (mic covered, background noise)
- Test duplicate upload from phone (should silently reject)
- Test Ollama not running (should set status=error with clear message)
- Test Obsidian vault path wrong (should fail loudly on startup)
- Mobile: test upload on slow WiFi (large file, progress bar behaviour)
- Mobile: test app killed mid-recording by Android OS (foreground service robustness)
- Add retry button in web UI for error-status meetings
- Add pipeline re-run option (re-process already-uploaded audio)

**Done when:** All above scenarios tested. No unhandled exceptions. All errors surface clearly to the user.

---

## Riskiest Unknown

**Persistent speaker matching accuracy at 5–6 Hinglish speakers.**

resemblyzer cosine similarity at 0.75 threshold is calibrated for English speech in controlled conditions. Hinglish meetings with background noise may produce lower embedding quality.

**Mitigation:** Run Phase 3 as a spike with one real meeting recording before building Phase 4 and 5. If speaker matching accuracy is below 70%:
- Lower threshold to 0.65 and test again
- If still insufficient: fall back to AssemblyAI diarization API (cloud, ~$0.001/min — acceptable for testing)
- Alternatively: use speechbrain's SpeakerRecognition as replacement for resemblyzer

Do not build the naming UI (Phase 4) until Phase 3 spike passes. Everything downstream depends on this working.

---

## Open Decisions to Resolve Before Building

| # | Decision | Assumed Default | Consequence If Wrong |
|---|----------|----------------|---------------------|
| 1 | Whisper large-v3 Hinglish accuracy | Sufficient for meeting-quality audio | Fine-tune on Hinglish samples or accept ~80% accuracy + add manual correction in web UI |
| 2 | Gemma 4:4B note generation quality | 4B sufficient for structured formatting | Upgrade to Gemma 4:12B or 27B — still free, slower on RTX 4050 |
| 3 | pyannote.audio personal use licensing | Free for personal/non-commercial | Switch to speechbrain as replacement |
| 4 | Cross-network access (different WiFi) | Phone hotspot fallback is sufficient | Set up Cloudflare Tunnel once — free, exposes localhost to public URL |
| 5 | Codex CLI context via AGENTS.md | Full TRD + pipeline spec in AGENTS.md is sufficient for phase-by-phase builds | Break into per-phase AGENTS.md files, feed one at a time |
| 6 | Obsidian vault path | `C:\Users\Lenovo\Desktop\Code\Obsidan Stronghold\MyBrain\Brain (ruchitdas36)` | Set via OBSIDIAN_VAULT_PATH in .env before first run |

---

## Hackathon Timeline (OpenAI x Outskill)

| Day | Target |
|-----|--------|
| Mon May 26 | Repo live on GitHub. AGENTS.md written. Phase 1 complete (server + upload). |
| Tue May 27 | Phase 2 complete (Android app records + uploads). Phase 3 spike (test speaker matching). |
| Wed May 28 | **MVP submission deadline.** Phase 4 + 5 complete (naming UI + note generation). End-to-end demo recorded. Product brief submitted. |
| Thu May 29 | Phase 6 (cross-meeting links). Polish. Fix bugs from demo. |
| Fri May 30 | **Final live product.** Phase 7 edge cases. README written. Demo video recorded. |
