# Backend Schema — Arc
### Data Model, API Endpoints & Pipeline Specification

---

## Database: SQLite

File location: `C:\Users\Lenovo\Desktop\arc\arc.db`
Mode: WAL (Write-Ahead Logging) — enables concurrent reads while pipeline writes

---

## Tables

### Table: `meetings`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | TEXT | PRIMARY KEY | UUID v4 generated on upload |
| `filename` | TEXT | NOT NULL | Original filename from phone |
| `sha256_hash` | TEXT | UNIQUE, NOT NULL | Deduplication key |
| `upload_time` | TEXT | NOT NULL | ISO 8601 datetime |
| `duration_seconds` | INTEGER | NULLABLE | Populated after transcription |
| `audio_path` | TEXT | NOT NULL | Absolute path in intake dir |
| `archive_path` | TEXT | NULLABLE | Moved here after processing |
| `obsidian_note_path` | TEXT | NULLABLE | Absolute path to written .md file |
| `status` | TEXT | NOT NULL, DEFAULT 'uploaded' | See status enum below |
| `error_message` | TEXT | NULLABLE | Pipeline error detail if status = error |
| `created_at` | TEXT | DEFAULT current_timestamp | |
| `updated_at` | TEXT | DEFAULT current_timestamp | Updated on every status change |

**Status enum:** `uploaded` → `needs_naming` → `processing` → `done` → `error`

---

### Table: `speakers`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | TEXT | PRIMARY KEY | UUID v4 |
| `name` | TEXT | NOT NULL | Set by Ruchit in naming UI |
| `embedding` | BLOB | NOT NULL | resemblyzer 256-dim float32 vector, serialised as bytes |
| `embedding_source_meeting_id` | TEXT | FK → meetings.id | Meeting where embedding was first created |
| `first_seen` | TEXT | NOT NULL | ISO 8601 date |
| `created_at` | TEXT | DEFAULT current_timestamp | |

---

### Table: `meeting_speakers`

Junction table — many-to-many between meetings and speakers.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | TEXT | PRIMARY KEY | UUID v4 |
| `meeting_id` | TEXT | FK → meetings.id, NOT NULL | |
| `speaker_id` | TEXT | FK → speakers.id, NOT NULL | |
| `total_speaking_seconds` | INTEGER | NULLABLE | Populated after diarization |
| `segment_count` | INTEGER | NULLABLE | Number of speaking turns |

---

### Table: `transcript_segments`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | TEXT | PRIMARY KEY | UUID v4 |
| `meeting_id` | TEXT | FK → meetings.id, NOT NULL | |
| `speaker_id` | TEXT | FK → speakers.id, NULLABLE | NULL if speaker unknown/unresolved |
| `start_seconds` | REAL | NOT NULL | Segment start time in audio |
| `end_seconds` | REAL | NOT NULL | Segment end time in audio |
| `text` | TEXT | NOT NULL | Transcribed text for this segment |
| `confidence` | REAL | NULLABLE | Whisper confidence score 0.0–1.0 |

---

### Table: `upload_log`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | TEXT | PRIMARY KEY | UUID v4 |
| `sha256_hash` | TEXT | NOT NULL | Hash of uploaded file |
| `filename` | TEXT | NOT NULL | |
| `upload_time` | TEXT | NOT NULL | |
| `accepted` | INTEGER | NOT NULL | 1 = accepted, 0 = rejected |
| `rejection_reason` | TEXT | NULLABLE | "duplicate" / "invalid_format" / etc. |

---

### Table: `concepts`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | TEXT | PRIMARY KEY | UUID v4 |
| `label` | TEXT | UNIQUE, NOT NULL | Obsidian wikilink text e.g. "client-timeline" |
| `obsidian_wikilink` | TEXT | NOT NULL | `[[client-timeline]]` |
| `first_seen_meeting_id` | TEXT | FK → meetings.id | |
| `created_at` | TEXT | DEFAULT current_timestamp | |

---

### Table: `meeting_concepts`

Junction table — concepts extracted per meeting.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | TEXT | PRIMARY KEY | UUID v4 |
| `meeting_id` | TEXT | FK → meetings.id, NOT NULL | |
| `concept_id` | TEXT | FK → concepts.id, NOT NULL | |

---

## Relationships

```
meetings        → meeting_speakers  : one-to-many (meetings.id)
speakers        → meeting_speakers  : one-to-many (speakers.id)
meetings        → transcript_segments : one-to-many (meetings.id)
speakers        → transcript_segments : one-to-many (speakers.id, nullable)
meetings        → meeting_concepts  : one-to-many (meetings.id)
concepts        → meeting_concepts  : one-to-many (concepts.id)
```

---

## Indexes

```sql
CREATE INDEX idx_meetings_status ON meetings(status);
CREATE INDEX idx_meetings_sha256 ON meetings(sha256_hash);
CREATE INDEX idx_transcript_meeting ON transcript_segments(meeting_id);
CREATE INDEX idx_transcript_speaker ON transcript_segments(speaker_id);
CREATE INDEX idx_meeting_speakers_meeting ON meeting_speakers(meeting_id);
CREATE INDEX idx_upload_log_hash ON upload_log(sha256_hash);
```

---

## Sensitive Fields

| Field | Handling |
|-------|---------|
| `speakers.embedding` | Stored as binary blob in local SQLite — never transmitted externally |
| `transcript_segments.text` | Stored locally in SQLite — never transmitted externally |
| Audio files | Stored locally in intake/archive dirs — never uploaded to any external service |

---

## File Storage (Local)

```
C:\Users\Lenovo\Desktop\arc\
├── intake\          ← uploaded audio files land here (watched by watchdog)
├── archive\         ← audio moved here after successful processing
├── clips\           ← 10-second speaker clips for naming UI (temp, deleted after naming)
└── arc.db           ← SQLite database
```

---

## API Endpoints

### Upload API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/upload` | Receive audio file from phone; SHA256 check; save to intake; create meeting record |
| `GET` | `/status/{meeting_id}` | Return current status of a meeting (polled by phone app and dashboard) |

### Web UI Routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Dashboard — all meetings, status, sorted by upload_time DESC |
| `GET` | `/meeting/{id}` | Meeting detail — transcript, summary, note preview |
| `GET` | `/naming/{id}` | Speaker naming UI — clips + name inputs for unknown speakers |
| `GET` | `/qr` | QR code page — displays current server URL as QR |

### Speaker API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/speaker/name` | Save speaker names from naming UI; triggers pipeline resume |
| `GET` | `/speakers` | List all known speakers (for admin view) |

### Clip API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/clip/{meeting_id}/{speaker_label}` | Serve 10-second audio clip for speaker naming playback |

---

## Obsidian Note Schema

Every note written to the vault follows this structure:

```markdown
---
title: "Meeting — 2025-05-26 14:30"
date: 2025-05-26
time: "14:30"
duration: "47 minutes"
participants:
  - Ruchit
  - Rahul
  - Priya
tags:
  - meeting
  - [extracted concept tags]
arc_meeting_id: "uuid-here"
---

## Summary
[2–4 sentence overview of what the meeting was about]

## What Was Discussed
[Paragraph or bullet summary per major topic]

## Decisions Made
- [Decision 1] — agreed by [[Rahul]] and [[Priya]]
- [Decision 2]

## Action Items
- [ ] [Task] — [[Ruchit]] — by [date if mentioned]
- [ ] [Task] — [[Rahul]]

## Key Suggestions & Debates
### [Topic]
**For:** [arguments in favour — attributed to speakers]
**Against:** [arguments against — attributed to speakers]

## Notes for Next Meeting
- [Open item 1]
- [Open item 2]

## Speaker-Tagged Transcript
**[[Rahul]]** (00:02:14): Full sentence here...
**[[Priya]]** (00:03:41): Full sentence here...
**Ruchit** (00:04:02): Full sentence here...

---
*Generated by Arc · [timestamp]*
```

---

## Pipeline Specification

The pipeline runs as a Python process triggered by watchdog when a new file appears in `intake/`.

```
Step 1 — Transcription
  Input:  audio file (AAC/M4A)
  Tool:   faster-whisper large-v3 (CUDA)
  Output: list of {start, end, text} segments
  Note:   language detection set to ["hi", "en"] for Hinglish

Step 2 — Diarization
  Input:  same audio file
  Tool:   pyannote.audio speaker-diarization-3.1
  Output: list of {start, end, speaker_label} segments
  Note:   max_speakers=8 (safe upper bound)

Step 3 — Segment Alignment
  Input:  whisper segments + pyannote segments
  Logic:  overlap matching — assign speaker_label to each whisper segment
          based on which pyannote segment has maximum time overlap
  Output: list of {start, end, speaker_label, text}

Step 4 — Speaker Matching
  Input:  speaker_labels from diarization + speaker embeddings from SQLite
  Tool:   resemblyzer — extract embedding per speaker_label from audio
  Logic:  cosine similarity against all stored embeddings
          threshold: 0.75 (above = match, below = unknown)
  Output: {speaker_label → speaker_id or "unknown"}

Step 5 — Unknown Speaker Handling
  If any speaker_label maps to "unknown":
    → Create 10-second clip for each unknown speaker
    → Save clips to clips/ directory
    → Set meeting status = "needs_naming"
    → Halt pipeline — wait for naming UI input
  If all speakers known:
    → Continue to Step 6

Step 6 — Note Generation
  Input:  full speaker-named transcript + meeting metadata
  Tool:   Ollama Gemma 4:4B
  Prompt: structured prompt requesting JSON with fields:
          summary, discussed_topics, decisions, action_items,
          suggestions_debates, next_meeting_notes, concepts[]
  Output: structured JSON → converted to Obsidian markdown template

Step 7 — Vault Write
  Input:  rendered Obsidian markdown
  Action: write to OBSIDIAN_VAULT_PATH/OBSIDIAN_MEETINGS_SUBFOLDER/
          filename: YYYY-MM-DD-HH-MM-[first-speaker-names].md
          update meeting record: obsidian_note_path, status = done
          update concepts table with extracted concepts
          move audio from intake/ to archive/
```

---

## Gemma 4:4B Prompt Template

```python
SYSTEM_PROMPT = """
You are a meeting intelligence assistant. You receive a speaker-tagged 
transcript and return a structured JSON object. Return ONLY valid JSON. 
No preamble. No explanation. No markdown fences.

JSON schema:
{
  "summary": "string — 2-4 sentences",
  "discussed_topics": ["string"],
  "decisions": [{"decision": "string", "agreed_by": ["speaker_name"]}],
  "action_items": [{"task": "string", "owner": "speaker_name_or_unknown", "deadline": "string_or_null"}],
  "suggestions_debates": [
    {
      "topic": "string",
      "for": [{"speaker": "string", "point": "string"}],
      "against": [{"speaker": "string", "point": "string"}]
    }
  ],
  "next_meeting_notes": ["string"],
  "concepts": ["string"]
}
"""

USER_PROMPT = """
Meeting date: {date}
Duration: {duration} minutes
Participants: {participants}

Transcript:
{tagged_transcript}
"""
```
