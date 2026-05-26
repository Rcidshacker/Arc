# PRD — Arc
### Product Requirements Document

---

## App Overview

| Field | Detail |
|-------|--------|
| **App Name** | Arc |
| **Tagline** | Your meetings, remembered. |
| **Platform** | Android (mobile) + Localhost Web UI (laptop) |
| **Version** | v1 — Personal Build |
| **Builder** | OpenAI Codex CLI |

**Problem:**
Meetings with 5–6+ Hinglish-speaking participants generate more context than can be manually captured. Who said what, why they said it, and how it connects to previous meetings is lost by end of day.

**Target User:**
Ruchit — solo personal use. One person. No team accounts, no sharing, no SaaS.

---

## Core Value Proposition

Every meeting tool on the market solves transcript and summary. Arc solves something different: it builds a persistent, relational memory of *why things were said*, *by whom*, and *how that connects to what was said in previous meetings*. It works silently in your pocket, requires zero note-taking during the meeting, and by the time you sit down at your desk, a fully structured Obsidian note is already waiting — speaker-named, wikilinked, and queryable in plain language via Claude Desktop.

The entire pipeline runs free and local. No subscriptions. No cloud. No data leaving your machine.

---

## Features

### Must Have (v1)

- Background audio recording on Android with screen off (Foreground Service)
- Minimal voice recorder UI — single large Record button, looks like a standard recorder app
- AAC/M4A recording at 128kbps (small file size, Whisper-compatible)
- QR code discovery — FastAPI server on laptop generates QR on startup containing local IP:port
- Phone scans QR once, stores server URL permanently
- **Two audio upload paths:**
  - Phone → HTTP multipart POST over local WiFi (2–4 second transfer for 1-hour meeting)
  - Laptop → drag-and-drop or file picker on web dashboard (any audio format)
- **Automatic format normalization** — any incoming audio format (.m4a, .mp3, .mp4, .webm, .wav, .ogg, .opus, .flac) converted to WAV 16kHz mono via ffmpeg before pipeline entry
- SHA256 deduplication — duplicate uploads silently rejected and logged
- Speaker diarization for 5–6+ speakers per session
- **Suggested speaker naming** — before prompting for manual input, pipeline infers each unknown speaker's name from transcript context (e.g. "Hey Rahul", "Priya what do you think"); user accepts with one tap or overrides
- One-time speaker naming — play 10-second clip per new speaker in web UI, accept suggestion or type name, stored as voice embedding permanently
- Automatic speaker matching in all future meetings via stored voice embeddings
- "New speaker detected" prompt only when someone genuinely new appears
- Hinglish transcription via faster-whisper large-v3 (local, GPU-accelerated, free)
- Auto-generated structured Obsidian note per meeting, written as a **meeting folder** containing:
  - `note.md` — summary, decisions, action items, wikilinked concepts
  - `transcript.md` — full speaker-tagged transcript
  - `audio_ref.txt` — path reference to audio file in temp storage
- Note content includes:
  - Speaker-tagged transcript
  - Summary of what was discussed
  - Decisions made
  - Action items (with owner if identifiable)
  - Pros and cons of key suggestions
  - Notes and open items for next meeting
  - Wikilinked concepts, speakers, and topics
  - Frontmatter: date, duration, participants list, tags, audio path reference
- Cross-meeting knowledge linking via Obsidian `[[wikilinks]]`
- **Audio temp storage** — processed audio files moved to a local `temp/` folder; never auto-deleted; user deletes manually via web UI when they want the space back
- Localhost web UI accessible from any browser on the same network:
  - All uploaded audio files with filename, date, duration, status
  - Processing status per file: pending / processing / done / error
  - File picker / drag-and-drop for laptop audio uploads
  - Speaker naming interface (clip playback + suggested name + accept/override input)
  - Transcript viewer per meeting
  - "Delete audio" button per meeting (removes from temp/, clears reference in note)
  - Deduplication log
- Natural language querying via existing Claude Desktop + Obsidian MCP (no new UI needed)

### Nice to Have (v2+)

- Multi-uploader network: colleagues install APK, connect to same laptop server via QR, upload their recordings, receive separate processed notes
- Cloudflare Tunnel for cross-network access when phone and laptop are on different WiFi
- Manual transcript correction UI in web interface
- Export meeting note as PDF
- Per-speaker analytics: who talks most, topic frequency per person
- In-app audio playback from temp/ linked directly in meeting detail page

### Out of Scope (v1)

- This version does NOT support iOS
- This version does NOT support real-time live transcription during meetings
- This version does NOT store any data in the cloud
- This version does NOT require internet for core functionality
- This version does NOT have multi-user or team access
- This version does NOT have a separate query UI (MCP handles this)
- This version does NOT have any subscription, API cost, or ongoing fees
- This version does NOT deploy to any server or hosting platform
- This version does NOT auto-delete audio files under any circumstances

---

## User Stories

| Feature | User Story |
|---------|-----------|
| Background recording | As Ruchit, I want to record a meeting with my screen off so that nobody in the room knows I'm recording |
| QR pairing | As Ruchit, I want to scan a QR code once and have my phone permanently know where to send files so that I never have to configure the connection again |
| Audio upload (phone) | As Ruchit, I want the audio file to transfer to my laptop automatically after I stop recording so that I don't have to manually move files |
| Audio upload (laptop) | As Ruchit, I want to drag a Zoom recording or any audio file onto the web UI and have it processed the same way as a phone recording |
| Format flexibility | As Ruchit, I want to upload any audio format and have the system handle conversion so I don't have to pre-process files |
| Deduplication | As Ruchit, I want the system to reject duplicate uploads so that I don't accidentally process the same meeting twice |
| Speaker diarization | As Ruchit, I want the transcript to show who said each sentence so that context isn't lost when reviewing |
| Suggested naming | As Ruchit, I want the system to suggest a speaker's name based on how others addressed them in the meeting, so I only have to tap Accept instead of typing |
| One-time naming | As Ruchit, I want to name each voice once and never be asked again so that the process requires zero effort after initial setup |
| Hinglish transcription | As Ruchit, I want mixed Hindi-English speech transcribed accurately so that the notes reflect how the meeting actually sounded |
| Meeting folder | As Ruchit, I want each meeting to have its own folder in Obsidian with separate note and transcript files so that the vault stays navigable |
| Structured note | As Ruchit, I want a formatted Obsidian note with summary, decisions, and action items so that I don't have to organise raw transcript myself |
| Wikilinks | As Ruchit, I want concepts and people linked across meeting notes so that Obsidian's graph view shows how topics connect over time |
| Audio retention | As Ruchit, I want audio files kept in a temp folder so I can go back to them if needed, and delete them myself when I want the space back |
| MCP querying | As Ruchit, I want to ask Claude Desktop questions about past meetings in plain language so that I can prep for client calls without rereading transcripts |

---

## Primary User Journey

1. Open Arc on Android → tap the Record button
2. Phone screen turns off — meeting proceeds normally, app records via Foreground Service
3. Meeting ends → tap Stop
4. App automatically uploads AAC file to laptop via HTTP over local WiFi
5. Laptop web UI updates: new file appears with status "pending"
6. Watchdog script detects new file → **Step 0: ffmpeg normalizes to WAV 16kHz mono**
7. faster-whisper transcribes audio → pyannote diarizes speakers
8. **Gemma infers speaker names from transcript context** → resemblyzer matches to stored embeddings
9. If new speaker detected → web UI flags for naming; suggested name shown if found; one-tap accept or manual override
10. Gemma 4:4B generates structured Obsidian markdown
11. Meeting folder written to Obsidian vault: `note.md` + `transcript.md` + `audio_ref.txt`
12. Audio moved to `temp/` folder; backlink written into note frontmatter
13. Web UI status updates to "done"
14. Ruchit opens Obsidian at end of day — meeting folder is there
15. Queries Claude Desktop via Obsidian MCP in natural language

---

## Success Metrics

**Primary:** After any meeting, can ask "why did [person] push back on X?" via Claude Desktop MCP and receive an accurate answer that references the correct meeting and speaker — without having taken a single manual note.

**Secondary:**
- Time from Stop tap to note appearing in Obsidian vault: under 10 minutes for a 1-hour meeting
- Speaker identification accuracy after initial naming: correctly identifies recurring speakers in ≥90% of segments
- Suggested name accepted without manual correction: target ≥70% of unknown speakers
