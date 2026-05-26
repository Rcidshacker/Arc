"""
Arc API smoke tests — exercises FastAPI layer only (no ML pipeline).
All tests use TestClient with an isolated SQLite DB per session.
"""
import io

import pytest
from fastapi.testclient import TestClient

import conftest  # ensures env is set before app import  # noqa: F401
from main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── Helpers ──────────────────────────────────────────────────────────────────

def _audio_bytes(seed: str = "") -> bytes:
    """Return unique fake-audio bytes that won't collide with other tests."""
    marker = f"ARC_TEST_{seed}".encode()
    return marker + b"\x00" * 256


# ── Tests ────────────────────────────────────────────────────────────────────

class TestUpload:
    def test_first_upload_accepted(self, client):
        resp = client.post(
            "/upload",
            files={"file": ("meeting.wav", io.BytesIO(_audio_bytes("first")), "audio/wav")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "meeting_id" in body["data"]
        assert "sha256" in body["data"]

    def test_duplicate_upload_rejected(self, client):
        data = _audio_bytes("dup")
        client.post(
            "/upload",
            files={"file": ("dup.wav", io.BytesIO(data), "audio/wav")},
        )
        resp2 = client.post(
            "/upload",
            files={"file": ("dup.wav", io.BytesIO(data), "audio/wav")},
        )
        assert resp2.status_code == 409
        body = resp2.json()
        assert body["success"] is False
        assert body["error"] == "duplicate"


class TestStatus:
    def test_unknown_meeting_returns_404(self, client):
        resp = client.get("/status/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
        assert resp.json()["success"] is False

    def test_status_after_upload_is_uploaded_or_processing(self, client):
        resp = client.post(
            "/upload",
            files={"file": ("status_test.wav", io.BytesIO(_audio_bytes("status")), "audio/wav")},
        )
        meeting_id = resp.json()["data"]["meeting_id"]

        status_resp = client.get(f"/status/{meeting_id}")
        assert status_resp.status_code == 200
        body = status_resp.json()
        assert body["success"] is True
        # Watcher may have picked it up immediately in daemon thread
        assert body["data"]["status"] in ("uploaded", "processing", "needs_naming", "done", "error")


class TestUI:
    def test_dashboard_renders(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Arc" in resp.content

    def test_qr_page_renders(self, client):
        resp = client.get("/qr")
        assert resp.status_code == 200
        assert b"qr" in resp.content.lower()

    def test_unknown_meeting_detail_returns_404(self, client):
        resp = client.get("/meeting/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


class TestDeleteAudio:
    def test_delete_nonexistent_meeting_returns_404(self, client):
        resp = client.delete("/meeting/nonexistent-id/audio")
        assert resp.status_code == 404
        assert resp.json()["success"] is False
