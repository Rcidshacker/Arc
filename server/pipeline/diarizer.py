"""
Arc pipeline — Step 2: Speaker diarization via pyannote.audio 3.x.
Runs AFTER transcription so Whisper has already released its VRAM.
"""

from __future__ import annotations

import logging
import os
import subprocess
import traceback
from pathlib import Path

logger = logging.getLogger(__name__)

_PIPELINE_ID = "pyannote/speaker-diarization-3.1"


def _get_audio_duration(audio_path: Path) -> float:
    """Return audio duration via ffprobe. Returns 0.0 on failure."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except Exception as exc:
        logger.warning("ffprobe duration check failed: %s", exc)
        return 0.0


def diarize(audio_path: Path) -> list[dict]:
    """
    Run speaker diarization on *audio_path*.

    On any failure, logs the full traceback and returns a single-speaker
    fallback segment so the pipeline can continue to needs_naming.

    Returns
    -------
    list[dict]
        Each element: ``{"start": float, "end": float, "speaker": str}``
    """
    try:
        return _diarize_impl(audio_path)
    except Exception:
        logger.error(
            "Diarization failed — using single-speaker fallback.\n%s",
            traceback.format_exc(),
        )
        duration = _get_audio_duration(audio_path)
        return [{"start": 0.0, "end": duration, "speaker": "SPEAKER_00"}]


def _diarize_impl(audio_path: Path) -> list[dict]:
    try:
        from pyannote.audio import Pipeline  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "pyannote.audio is not installed. "
            "Run: pip install pyannote.audio"
        ) from exc

    hf_token = os.environ["HF_TOKEN"]  # KeyError caught by outer diarize() fallback

    # speechbrain lazily imports optional integrations (k2_fsa, huggingface wordemb,
    # etc.) that aren't installed. Pre-stub them so the lazy-loader never fires.
    import sys
    import types
    _sb_optional = [
        "speechbrain.integrations.k2_fsa",
        "speechbrain.integrations.huggingface",
        "speechbrain.integrations.huggingface.wordemb",
        "speechbrain.pretrained.fetching",
        "speechbrain.utils.superpowers",
    ]
    for _mod_name in _sb_optional:
        if _mod_name not in sys.modules:
            sys.modules[_mod_name] = types.ModuleType(_mod_name)

    # PyTorch 2.6 set weights_only=True by default. pyannote checkpoints contain
    # custom globals (TorchVersion, Specifications, etc.) not in the allowlist.
    # Patch torch.load to allow pyannote's trusted checkpoints.
    import torch as _torch
    _orig_torch_load = _torch.load
    def _torch_load_unsafe(*args, **kwargs):
        kwargs["weights_only"] = False
        return _orig_torch_load(*args, **kwargs)
    _torch.load = _torch_load_unsafe

    # pyannote.audio 3.x imports hf_hub_download locally and passes
    # use_auth_token to it. huggingface_hub >=0.24 renamed that param to `token`.
    # Patch pyannote's local module reference directly.
    import pyannote.audio.core.pipeline as _pyannote_pipeline
    import pyannote.audio.core.model as _pyannote_model
    import huggingface_hub as _hf_hub

    def _patched_hf_hub_download(*args, use_auth_token=None, **kwargs):
        if use_auth_token is not None and "token" not in kwargs:
            kwargs["token"] = use_auth_token
        return _hf_hub.hf_hub_download(*args, **kwargs)

    _orig_pipeline = _pyannote_pipeline.hf_hub_download
    _orig_model = _pyannote_model.hf_hub_download
    _pyannote_pipeline.hf_hub_download = _patched_hf_hub_download
    _pyannote_model.hf_hub_download = _patched_hf_hub_download

    logger.info("Loading pyannote pipeline '%s'", _PIPELINE_ID)
    try:
        pipeline = Pipeline.from_pretrained(
            _PIPELINE_ID,
            use_auth_token=hf_token,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load pyannote pipeline '{_PIPELINE_ID}': {exc}"
        ) from exc
    finally:
        _pyannote_pipeline.hf_hub_download = _orig_pipeline
        _pyannote_model.hf_hub_download = _orig_model
        _torch.load = _orig_torch_load

    # Move to GPU if available
    try:
        import torch  # type: ignore[import]
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
            logger.info("Pyannote pipeline moved to CUDA.")
    except ImportError:
        logger.warning("torch not available; pyannote will run on CPU.")

    logger.info("Running diarization on: %s", audio_path)
    try:
        diarization = pipeline(
            str(audio_path),
            max_speakers=8,
        )
    except Exception as exc:
        raise RuntimeError(f"Diarization failed: {exc}") from exc

    segments: list[dict] = []
    for turn, _track, speaker in diarization.itertracks(yield_label=True):
        segments.append(
            {
                "start": float(turn.start),
                "end": float(turn.end),
                "speaker": str(speaker),
            }
        )

    # itertracks is already time-ordered, but sort defensively
    segments.sort(key=lambda s: s["start"])

    logger.info("Diarization produced %d speaker segments.", len(segments))
    return segments
