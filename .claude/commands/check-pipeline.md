---
name: check-pipeline
---

Diagnose Arc pipeline health:
1. Check Ollama: `curl http://localhost:11434/api/tags` — verify `gemma4:4b` in list
2. Check ffmpeg: `ffmpeg -version` — verify on PATH
3. Check Python env: `python -c "import faster_whisper, pyannote, resemblyzer; print('OK')"` in server venv
4. Check SQLite: open `arc.db`, run `SELECT status, COUNT(*) FROM meetings GROUP BY status`
5. Check directories exist: `intake/`, `temp/`, `clips/`, `arc.db`
6. Check env vars loaded: `python -c "from dotenv import dotenv_values; print(dotenv_values('.env').keys())"` — no missing keys
7. Report: which checks passed, which failed, fix instructions for each failure
