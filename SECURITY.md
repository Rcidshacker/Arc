# Security Policy

## Scope

Arc is a local-only personal tool. The server binds to LAN (`0.0.0.0`) and is not intended for public internet exposure. All data stays on the local machine.

## Known Design Constraints

| Surface | Risk | Mitigation |
|---|---|---|
| `/upload` endpoint | Anyone on LAN can upload audio | Designed for single-user home network only — do not expose to untrusted networks |
| SQLite DB | No authentication | Access is filesystem-level; protect via OS permissions |
| Ollama API | Unauthenticated local HTTP | Localhost only; `OLLAMA_HOST` defaults to `http://localhost:11434` |
| Audio file deletion | Path traversal | `Path.resolve()` + `relative_to(ARC_TEMP_DIR)` validation before any `unlink()` |
| ffmpeg subprocess | Command injection | Always uses list args with `shell=False`; no user-controlled args passed |

## Secret Hygiene

- `.env` is listed in `.gitignore` and must never be committed
- `HF_TOKEN` (Hugging Face) must be treated as a secret — rotate if exposed
- No other secrets are required; no external API keys beyond HF and Ollama (local)

## Reporting Issues

This is a personal hackathon project. If you discover a security issue, open an issue in the repository describing the vulnerability.

## Dependency Scanning

Run periodically:

```bash
pip install pip-audit
pip-audit -r requirements.txt
```
