"""
Arc pipeline — Step 0: Audio normalization.
Converts any audio format to WAV 16 kHz mono via ffmpeg.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def normalize_audio(input_path: Path, output_dir: Path) -> Path:
    """
    Convert *input_path* to a WAV file at 16 kHz mono.

    Parameters
    ----------
    input_path:
        Source audio file (any format supported by ffmpeg).
    output_dir:
        Directory where the normalized file will be written.

    Returns
    -------
    Path
        Absolute path to the normalized WAV file.

    Raises
    ------
    RuntimeError
        If ffmpeg is not found on PATH or if the conversion fails.
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg not found on PATH. Install ffmpeg and ensure it is accessible."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{input_path.stem}_normalized.wav"

    cmd = [
        "ffmpeg",
        "-y",                    # overwrite output without prompting
        "-i", str(input_path),
        "-ar", "16000",          # sample rate 16 kHz
        "-ac", "1",              # mono
        str(output_path),
    ]

    logger.info("Normalizing audio: %s -> %s", input_path, output_path)
    logger.debug("ffmpeg command: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            shell=False,
            check=False,          # we inspect returncode ourselves for better messages
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"ffmpeg executable not found when attempting to run: {exc}"
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg conversion failed (exit {result.returncode}).\n"
            f"stderr:\n{result.stderr}"
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(
            f"ffmpeg exited successfully but output file is missing or empty: {output_path}"
        )

    logger.info("Normalization complete: %s (%.1f KB)", output_path, output_path.stat().st_size / 1024)
    return output_path
