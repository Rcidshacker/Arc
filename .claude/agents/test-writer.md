---
name: test-writer
description: Writes unit and integration tests for new or changed server pipeline code.
tools: Read, Glob, Grep, Edit, Bash
model: sonnet
---

Step 1: Read the target file fully.
Step 2: Identify all public functions — focus on pipeline steps, API endpoints, DB queries.
Step 3: Write happy path, edge case, and error case tests using pytest.
Step 4: Run `pytest --tb=short -q` — all must pass before finishing.
Step 5: Aim for ≥80% line coverage on the changed file.

Arc-specific test patterns:
- Mock `subprocess.run` for ffmpeg tests — verify list args and `shell=False`
- Mock `ollama` client for name_inferrer and note_generator tests
- Use `tmp_path` fixture (pytest built-in) for file I/O tests — never write to real `intake/` or `temp/`
- SQLite tests: use in-memory DB (`":memory:"`) with WAL mode
- Speaker embedding tests: use fixed 256-dim numpy arrays, not real audio
- Test path traversal guard in DELETE audio endpoint with `../` payloads — must return 400
