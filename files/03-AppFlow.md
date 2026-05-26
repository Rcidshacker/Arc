# App Flow — Arc
### Navigation & User Journey Map

---

## Surfaces Overview

Arc has two distinct surfaces. They are independent but connected through the same backend.

| Surface | What It Is | Who Uses It | Where |
|---------|-----------|------------|-------|
| Mobile App | Android recorder + uploader | Ruchit (in meetings) | Phone |
| Web UI | Processing dashboard + speaker naming + transcript viewer | Ruchit (at desk) | Laptop browser |

---

## Mobile App — Screens

| Screen | Description | Appears When |
|--------|-------------|-------------|
| `QRScannerScreen` | Camera view to scan laptop QR code | First launch only; again if server URL cleared |
| `RecorderScreen` | Main screen — large Record/Stop button, upload status | After pairing; every session |
| `UploadStatusScreen` | Shows upload progress + confirmation | After tapping Stop |

> No auth. No navigation drawer. No settings screen in v1.
> Three screens total — intentionally minimal.

---

## Web UI — Pages

| Route | Page | Description |
|-------|------|-------------|
| `GET /` | Dashboard | All meetings, status, sorted by upload time; file picker for laptop uploads |
| `GET /meeting/{id}` | Meeting Detail | Transcript viewer, speaker breakdown, note preview, delete audio option |
| `GET /naming/{id}` | Speaker Naming | Play 10-sec clips; suggested name + accept/override per unknown speaker |
| `GET /qr` | QR Code Display | Shows current QR for phone pairing |
| `POST /upload` | (API) | Receives audio file from phone or laptop file picker |
| `POST /speaker/name` | (API) | Saves speaker names from naming UI; triggers pipeline resume |
| `GET /status/{id}` | (API) | Returns processing status for a meeting — polled by dashboard |
| `DELETE /meeting/{id}/audio` | (API) | Removes audio from temp/, clears reference in note |

---

## Mobile Navigation Structure

```
App Launch
    │
    ├── First Launch (no server URL stored)
    │       └── QRScannerScreen
    │               └── Scan QR → save URL → RecorderScreen
    │
    └── Returning Launch (server URL exists)
            └── RecorderScreen
                    ├── [Tap Record] → Foreground Service starts
                    │                  Screen can turn off
                    │                  Persistent notification: "Arc is recording"
                    │
                    └── [Tap Stop]  → Audio saved to temp file
                                      Upload triggered automatically
                                      → UploadStatusScreen
                                            ├── Success: "Uploaded. Processing on laptop."
                                            └── Error: "Upload failed. Check WiFi." + retry
```

---

## Web UI Navigation Structure

```
Browser: http://[laptop-ip]:8000
    │
    └── Dashboard (/)
            ├── [Drop audio file / file picker] → POST /upload → new meeting row
            │
            ├── Meeting row [status: pending]
            ├── Meeting row [status: processing]
            ├── Meeting row [status: done] ──────→ Meeting Detail (/meeting/{id})
            │                                               ├── Transcript tab
            │                                               ├── Summary tab
            │                                               ├── Note preview tab
            │                                               └── [Delete audio] button
            │                                                     └── Confirm → DELETE /meeting/{id}/audio
            │
            └── Meeting row [status: needs_naming] → Speaker Naming (/naming/{id})
                                                            ├── Speaker 1:
                                                            │     [▶ play clip]
                                                            │     Suggested: "Rahul" (addressed 4×)
                                                            │     [✓ Accept]  [Edit → text input]
                                                            ├── Speaker 2:
                                                            │     [▶ play clip]
                                                            │     No name detected
                                                            │     [text input]
                                                            └── [Save All Names] → pipeline resumes
```

---

## Primary User Journey — In-Meeting Capture (Phone)

> Ruchit wants to capture a meeting without being seen to be doing so.

1. Ruchit opens Arc on his phone before entering the meeting room
2. RecorderScreen is showing — large Record button centered
3. Ruchit taps Record → button turns red → subtle pulse animation
4. Persistent notification appears: "Arc · Recording in progress"
5. Ruchit locks phone, puts it on the table
6. Meeting proceeds — recording continues via Foreground Service
7. Meeting ends → Ruchit unlocks phone → taps Stop
8. Recording stops → UploadStatusScreen with upload spinner
9. File transfers to laptop in 2–4 seconds over WiFi
10. UploadStatusScreen shows: "Uploaded ✓ — processing on your laptop"
11. Ruchit closes the app

---

## Primary User Journey — Laptop File Upload

> Ruchit has a Zoom cloud recording or any audio file on his laptop he wants processed.

1. Ruchit opens `http://localhost:8000` in browser
2. Drags audio file onto the drag-and-drop zone at top of dashboard (or clicks file picker)
3. File uploads instantly — new meeting row appears with status "pending"
4. Same pipeline runs — format normalized, transcribed, diarized, notes generated
5. Processing continues identically to phone upload path

---

## Secondary Journey — Speaker Naming with Suggestions

> Ruchit opens the laptop web UI after a meeting where someone new was present.

1. Browser at `http://localhost:8000`
2. Dashboard shows meeting with amber badge: "Needs naming — 2 new speakers"
3. Ruchit clicks row → `/naming/{id}`
4. **Speaker 1 card:** play button + "Suggested: Rahul (addressed by name 4 times)" + [✓ Accept] [Edit]
5. Ruchit taps Accept — done in one tap
6. **Speaker 2 card:** play button + "No name detected in transcript" + text input
7. Ruchit plays clip, types the name, hits Save
8. [Save All Names] → names stored as voice embeddings in SQLite
9. Pipeline resumes → status "processing" → note appears in Obsidian vault

---

## Secondary Journey — Deleting Audio from Temp

> Ruchit wants to free up disk space after confirming the notes are complete.

1. Ruchit opens Meeting Detail for a processed meeting
2. Scrolls to bottom of page — "Audio file: `arc/temp/2025-05-26-1430-meeting.wav` (47 min · 85MB)"
3. Clicks "Delete audio" → confirmation dialog: "This cannot be undone. The note and transcript will remain."
4. Confirms → `DELETE /meeting/{id}/audio` called
5. File removed from `temp/`; `audio_temp_path` cleared in DB; `audio_ref.txt` updated in Obsidian folder
6. Meeting detail now shows "Audio deleted" in place of the file reference

---

## Secondary Journey — End-of-Day Review via MCP

> Ruchit wants to recall what was discussed across three meetings this week.

1. Ruchit opens Claude Desktop (running with Obsidian MCP)
2. Types: "Summarise what Rahul has said about the client timeline across this week's meetings"
3. Claude reads Obsidian notes via MCP → returns speaker-attributed summary with meeting dates
4. Ruchit: "What did we decide about the budget in Tuesday's meeting?"
5. Claude returns exact decision with context from note
6. Ruchit: "Draft a brief for the client based on what we've agreed"
7. Claude synthesises across notes → produces draft

---

## States to Handle

### Empty States

| Screen | Empty State |
|--------|-------------|
| Dashboard (no meetings yet) | "No meetings yet. Record on your phone or drop an audio file here." + QR code displayed + file picker |
| Meeting Detail (transcript empty) | "Transcript is being processed. Refresh in a moment." |
| Speaker Naming (all named) | Should not appear — naming only triggers for genuinely unknown speakers |

### Error States

| Error | Where | Message |
|-------|-------|---------|
| Upload failed (no WiFi) | UploadStatusScreen | "Upload failed — check that your phone and laptop are on the same WiFi. Tap to retry." |
| Duplicate upload | UploadStatusScreen / Dashboard | "This recording was already uploaded. Nothing to do." |
| Unsupported format | Dashboard | "Could not read this audio format. Try MP3, M4A, WAV, or MP4." |
| ffmpeg not found | Pipeline / status | "Audio normalization failed. Is ffmpeg installed and on PATH?" |
| Transcription failed | Dashboard | Status badge: "Error" — hover: "Transcription failed. Check logs." |
| Ollama not running | Dashboard | Status badge: "Error" — "Note generation failed. Is Ollama running?" |
| Server unreachable (phone) | UploadStatusScreen | "Cannot reach Arc server. Is your laptop on the same WiFi?" |

### Loading States

| Action | Loading Indicator |
|--------|-----------------|
| File uploading | Upload spinner + percentage in UploadStatusScreen / dashboard |
| Normalizing audio | Sub-status: "Converting audio format..." |
| Processing (transcription + diarization) | Animated badge: "Processing..." |
| Name inference | Sub-status: "Inferring speaker names..." |
| Clip loading in naming UI | Waveform placeholder while clip buffers |
| Note generation | Sub-status: "Generating note with Gemma..." |

---

## Pipeline State Machine

```
uploaded
    │
    ▼
normalizing  (ffmpeg → WAV 16kHz mono)
    │
    ▼
transcribing (faster-whisper)
    │
    ▼
diarizing    (pyannote)
    │
    ▼
aligning     (merge segments)
    │
    ▼
matching     (resemblyzer → known speakers)
    │
    ├── [unknown speakers found]
    │       │
    │       ▼
    │   inferring_names  (Gemma → suggest from transcript)
    │       │
    │       ▼
    │   needs_naming     (halt — web UI naming flow)
    │       │
    │   [names saved]
    │       │
    │       ▼
    └── processing       (Gemma note generation)
            │
        [success] → done
            │
        [failure] → error (retriable)
```
