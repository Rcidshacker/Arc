---
paths:
  - "server/main.py"
  - "server/pipeline/**/*"
  - "server/watcher.py"
  - "server/database.py"
---

- All user-supplied paths resolved with `Path.resolve()` and validated as child of allowed dir before use
- ffmpeg: always `subprocess.run(["ffmpeg", ...], shell=False, check=True)` — list args only
- FastAPI route handlers: no blocking ML/ffmpeg calls inline — offload to background tasks or watcher process
- All API JSON responses: `{"success": bool, "data": any, "error": str | null}`
- Return 409 for duplicate uploads (sha256 match), 400 for path traversal attempts, 422 for bad input
- SQLite: all queries parameterized — no f-string or `.format()` interpolation into SQL
- Ollama: check connectivity before calling — set meeting `status="error"` with `error_message` if Ollama unreachable
- Pipeline steps are sequential — do not `asyncio.gather` or thread ML steps (VRAM constraint)
- Watchdog file events: ignore non-audio file extensions; handle `FileNotFoundError` (file moved between event and processing)
