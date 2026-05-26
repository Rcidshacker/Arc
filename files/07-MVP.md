# MVP Specification — Arc (2-Day Sprint)

This document establishes the streamlined, high-priority scope and implementation roadmap to achieve a fully functional end-to-end MVP of **Arc** by Wednesday (2 days from now). By leveraging Claude Code, we focus on minimizing architectural overhead while delivering the core value loop.

---

## The MVP Value Loop

The absolute success criterion for Wednesday is:
> **Record a Hinglish conversation on phone (or upload an audio file on laptop) $\rightarrow$ process it locally $\rightarrow$ generate a structured, speaker-named meeting folder in the Obsidian vault within 10 minutes.**

---

## Streamlined Scope for Wednesday

To hit the 2-day deadline, we strip all non-essential features and prioritize a single-process FastAPI backend + simple React Native audio client.

### In-Scope (Must Have for Wednesday)
1.  **Dual Upload Paths & Normalization:**
    *   Android app recording upload (multipart POST).
    *   Laptop dashboard file picker upload (drag-and-drop).
    *   Immediate normalization of all files to standard **WAV 16kHz mono** via a Python subprocess call to `ffmpeg`.
2.  **Sequential ML Pipeline:**
    *   `faster-whisper` (running `large-v3` on CUDA, falling back to `medium` or CPU if CUDA drivers block).
    *   `pyannote.audio` diarization (max speakers = 8).
    *   Overlay alignment to match transcript segments to speaker labels.
3.  **Basic Speaker Match & suggested Naming:**
    *   `resemblyzer` cosine similarity check (threshold `0.75`).
    *   **Gemma Name Inference:** A simple prompt requesting Gemma to inspect aligned segment chunks for vocative addressing (e.g. "Rahul, check this") to pre-fill the name suggestion.
4.  **Consolidated Single-Page Dashboard Web UI:**
    *   Displays all meetings, status badges (`pending`, `processing`, `needs_naming`, `done`, `error`).
    *   Laptop file upload form.
    *   **Inline Naming Panel:** Shows unknown speakers, plays their 10s audio clip using standard HTML `<audio>` elements, pre-fills the Gemma-inferred name suggestion, and allows a single-button "Save Names" action.
    *   "Delete Audio" button to purge `temp/` folder files and clear reference paths.
5.  **Obsidian Vault Write (Folder Structure):**
    *   Writes directly to a dedicated meeting folder containing:
        *   `note.md` (metadata frontmatter, summary, decisions, action items).
        *   `transcript.md` (tagged dialogue in monospace layout).
        *   `audio_ref.txt` (local temp path pointer).

### Out-of-Scope (Deferred to Post-Wednesday)
*   **Cross-meeting concept graphs / backlinks:** Rerunning index checks across past notes. Claude Desktop MCP can query across separate notes without custom backlinks.
*   **Complex audio waveforms / custom visual playback:** Replace with native HTML5 audio controls.
*   **Multi-vector prototype voice tracking:** Keep comparison strictly against the latest single vector.
*   **Multiple pages in Web UI:** Consolidate detail views and naming panels into the dashboard interface.

---

## 2-Day Implementation Roadmap (For Claude Code)

### Day 1: Backend Infrastructure, DB, & Pipeline Core
*   **Milestone 1: Database & File Setup**
    *   Initialize SQLite database with `meetings`, `speakers`, `meeting_speakers`, `transcript_segments`, and `upload_log` tables.
    *   Create directories: `intake/`, `temp/`, `clips/`.
*   **Milestone 2: Normalization & Watchdog Runner**
    *   Write `normalizer.py` wrapping the `ffmpeg` subprocess.
    *   Set up `watcher.py` (watchdog) monitoring `intake/` to auto-trigger the pipeline.
*   **Milestone 3: Transcriber & Diarizer Alignment**
    *   Write `transcriber.py` and `diarizer.py`.
    *   Write `aligner.py` to map Whisper segments to Pyannote speaker labels using overlap heuristics.
*   **Milestone 4: Resemblyzer Matching & Clip Slicing**
    *   Write `speaker_db.py` to extract speaker embeddings, run cosine checks, and slice 10-second clips for unknown voices using `soundfile`.

### Day 2: LLM Integrations, Web UI, & Mobile Client
*   **Milestone 5: Gemma Name Inference & Summarization**
    *   Implement `name_inferrer.py` to extract names from conversational transcripts using Gemma.
    *   Implement `note_generator.py` using Ollama's `format="json"` to generate structured summaries.
*   **Milestone 6: FastAPI Web UI Dashboard**
    *   Build `main.py` serving a single Jinja2 dashboard containing:
        *   Meeting status table.
        *   Upload widget.
        *   Dynamic modal/card sections for naming unknown speakers.
        *   "/upload", "/status", and "/speaker/name" API routes.
    *   Add path-validated "Delete Audio" routing.
*   **Milestone 7: Android Recording Client**
    *   Initialize bare Expo workflow.
    *   Build simple `QRScannerScreen` and `RecorderScreen` with basic record triggers.
    *   Verify background service lifecycle persistence.

---

## Happy-Path Verification Test

Validate the Wednesday MVP end-to-end:
1.  Launch uvicorn server: `uvicorn server.main:app --host 0.0.0.0 --port 8000`
2.  Open dashboard in browser $\rightarrow$ upload a 3-minute test `.mp3` containing two speakers.
3.  Ensure state updates to `needs_naming` $\rightarrow$ verify Gemma-inferred name suggestions appear next to the audio clip inputs.
4.  Type speaker names $\rightarrow$ tap "Save Names".
5.  Pipeline resumes $\rightarrow$ verify status changes to `done`.
6.  Open Obsidian $\rightarrow$ confirm meeting folder is populated with `note.md`, `transcript.md`, and `audio_ref.txt` containing valid markdown.
