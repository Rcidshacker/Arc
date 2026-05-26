"""
Test environment bootstrap.
Must set all required env vars BEFORE any import of server/main.py,
because main.py reads os.environ at module level.
"""
import os
import sys
import tempfile
from pathlib import Path

# ── Add server/ to import path ──────────────────────────────────────────────
_SERVER_DIR = Path(__file__).parent.parent / "server"
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

# ── Create a shared temp dir for the test session ───────────────────────────
_TMP = Path(tempfile.mkdtemp(prefix="arc_test_"))
(_TMP / "vault").mkdir()
(_TMP / "intake").mkdir()
(_TMP / "temp").mkdir()
(_TMP / "clips").mkdir()

# ── Set env vars before main.py is imported ─────────────────────────────────
os.environ.setdefault("OBSIDIAN_VAULT_PATH", str(_TMP / "vault"))
os.environ.setdefault("OBSIDIAN_MEETINGS_SUBFOLDER", "Meetings")
os.environ.setdefault("ARC_INTAKE_DIR", str(_TMP / "intake"))
os.environ.setdefault("ARC_TEMP_DIR", str(_TMP / "temp"))
os.environ.setdefault("ARC_DB_PATH", str(_TMP / "arc.db"))
os.environ.setdefault("ARC_SERVER_PORT", "8001")
os.environ.setdefault("WHISPER_MODEL", "tiny")
os.environ.setdefault("WHISPER_DEVICE", "cpu")
os.environ.setdefault("OLLAMA_MODEL", "gemma3:4b")
os.environ.setdefault("OLLAMA_HOST", "http://localhost:11434")
os.environ.setdefault("HF_TOKEN", "test-token-placeholder")
