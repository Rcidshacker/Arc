---
paths:
  - "server/database.py"
  - "server/pipeline/speaker_db.py"
---

- Open SQLite with `PRAGMA journal_mode=WAL` and `check_same_thread=False` — both required
- Speaker embeddings stored as `BLOB` — serialize float32 numpy array with `embedding.tobytes()`, deserialize with `np.frombuffer(blob, dtype=np.float32)`
- `meetings.obsidian_note_path` stores path relative to vault root, not absolute — e.g. `Meetings/2025-05-26-1430-Rahul-Priya/`
- `meetings.audio_deleted` flag (INTEGER 0/1) — set to 1 after successful temp file deletion
- `speakers.suggested_name` (TEXT NULLABLE) — Gemma inference stored here between pipeline steps; cleared after user confirms name
- Use UUID v4 for all primary keys — `str(uuid.uuid4())`
- Update `meetings.updated_at` on every status change
- All schema changes via explicit `ALTER TABLE` — no dropping columns
