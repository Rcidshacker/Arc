# Arc — Project Memory

## What Arc Is

Local-first personal meeting intelligence. Single user (Ruchit). Android records Hinglish meetings → uploads to FastAPI laptop server over WiFi → 8-stage ML pipeline → structured Obsidian vault note. Zero cloud. Zero cost.

## Key Decisions

| Decision | Rationale |
|---|---|
| Sequential pipeline (no parallelism) | RTX 4050 has 6GB VRAM; Whisper large-v3 (~3GB) and pyannote (~1GB) cannot co-exist |
| resemblyzer cosine threshold 0.75 | Calibrated for Hinglish; lower to 0.65 if accuracy < 70% in Phase 3 testing |
| `pathlib.Path` everywhere | Windows 11 — never hardcode `/` separators |
| `subprocess.run(list, shell=False)` | ffmpeg safety; prevents shell injection |
| WAL mode SQLite | Server + watcher share DB concurrently |
| Obsidian paths stored relative to vault root | Resolved dynamically via `OBSIDIAN_VAULT_PATH` env var |
| Placeholder 256-dim zero embedding for named speakers | resemblyzer returns 256-d; real embed added on next meeting |

## Critical Bugs Fixed (2026-05-26)

1. `write_vault()` called with 3 args, needs 5 — added env var reads in `watcher.py` before call
2. Pipeline stalled after speaker naming — watchdog never re-fires for existing file — fixed via `run_pipeline_for_meeting()` + `BackgroundTasks`

## Pipeline Status Flow

```
uploaded → processing → needs_naming → processing → done
                                  ↓
                              (user names speakers via /naming)
```

## File Layout

```
server/
├── main.py          — FastAPI app + all routes
├── watcher.py       — watchdog FileSystemEventHandler
├── database.py      — SQLite layer (24 functions, WAL mode)
└── pipeline/
    ├── normalizer.py    — ffmpeg → WAV 16kHz mono
    ├── transcriber.py   — faster-whisper large-v3 (CUDA)
    ├── diarizer.py      — pyannote 3.x (max_speakers=8)
    ├── aligner.py       — overlap-match whisper↔pyannote
    ├── speaker_db.py    — resemblyzer embed/match + clip extraction
    ├── name_inferrer.py — Gemma infers names from vocatives
    ├── note_generator.py— Gemma → structured JSON note
    └── vault_writer.py  — writes meeting folder to Obsidian
mobile/              — React Native Expo bare (Android only)
tests/               — FastAPI smoke tests (no ML required)
```

## Environment Variables

All required. Loaded from `.env` via python-dotenv:

- `OBSIDIAN_VAULT_PATH`, `OBSIDIAN_MEETINGS_SUBFOLDER`
- `ARC_INTAKE_DIR`, `ARC_TEMP_DIR`, `ARC_DB_PATH`, `ARC_SERVER_PORT`
- `WHISPER_MODEL`, `WHISPER_DEVICE`
- `OLLAMA_MODEL`, `OLLAMA_HOST`
- `HF_TOKEN` (pyannote model access)

## What's Pending (as of 2026-05-26)

- [ ] git repo initialization
- [ ] Mobile APK build (`eas build --platform android --local`)
- [ ] `mobile/assets/icon.png` placeholder
- [ ] Post-prebuild Android manifest (VIForegroundService + ic_notification drawable)
- [ ] Phase 3 speaker matching spike (validate accuracy with real Hinglish audio)
- [ ] Phase 6–7: cross-meeting wikilinks, edge case polish
