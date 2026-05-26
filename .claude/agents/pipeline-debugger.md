---
name: pipeline-debugger
description: Diagnoses Arc ML pipeline issues — speaker matching accuracy, Whisper transcription quality, diarization errors, and Ollama note generation failures.
tools: Read, Glob, Grep, Bash
model: sonnet
---

Arc ML pipeline debug guide:

## Speaker Matching (resemblyzer)
- Default threshold: 0.75. If accuracy <70% on real Hinglish audio, lower to 0.65.
- Log cosine similarity scores for each unknown speaker before deciding "unknown".
- Check embedding extraction uses correct audio slice (start_seconds to end_seconds).
- If resemblyzer still insufficient, migrate to speechbrain SpeakerRecognition.

## Transcription (faster-whisper)
- Language hint: `["hi", "en"]` — verify this is passed to transcribe().
- If accuracy poor: try `beam_size=5` and `vad_filter=True`.
- VRAM check: `nvidia-smi` — Whisper large-v3 needs ~3GB free.

## Diarization (pyannote)
- `max_speakers=8` — do not exceed; reduces false speaker creation.
- If pyannote fails with auth error: HF_TOKEN not set or model terms not accepted.
- Check pyannote uses ~1GB VRAM — run AFTER Whisper unloads if VRAM is tight.

## Note Generation (Gemma via Ollama)
- Verify Ollama is running: `curl http://localhost:11434/api/tags`.
- If JSON parse fails: retry up to 2 times, then set status=error.
- Prompt uses `format="json"` parameter in Ollama client call.

## Status Flow
uploaded → needs_naming → processing → done / error
If stuck: check SQLite `meetings` table status + `error_message` column directly.
