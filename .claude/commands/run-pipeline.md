---
name: run-pipeline
argument-hint: [path-to-audio-file]
---

Run the full Arc pipeline on a test audio file:
1. Copy $ARGUMENTS into `intake/` directory
2. Confirm `uvicorn server.main:app` is running on port 8000
3. Confirm `python server/watcher.py` is running and watching `intake/`
4. Open http://localhost:8000 — verify new meeting row appears with status `uploaded` → `processing`
5. If status becomes `needs_naming`: open naming UI, verify Gemma suggestion appears, submit a name
6. Wait for status `done`
7. Verify meeting folder created in Obsidian vault: `note.md` + `transcript.md` + `audio_ref.txt`
8. Report: total processing time, speaker count, any errors
