import sys, os, requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

wav = Path(r"C:\Users\Lenovo\Desktop\arc\temp\7373832e-c593-445b-86fd-850bd9658111_normalized.wav")
host = os.environ.get("LLAMACPP_HOST", "http://localhost:8080")

print(f"WAV size: {wav.stat().st_size / 1024 / 1024:.2f} MB")
print()

# Try Whisper-compatible transcription endpoint (multipart form, no context limit issue)
url = f"{host}/v1/audio/transcriptions"
print(f"=== Trying Whisper endpoint: POST {url} ===")
with open(wav, "rb") as f:
    resp = requests.post(url, files={"file": (wav.name, f, "audio/wav")}, data={"model": "gemma4"}, timeout=300)
print(f"HTTP {resp.status_code}")
if resp.ok:
    data = resp.json()
    text = data.get("text", "")
    print(f"--- TRANSCRIPT ({len(text)} chars) ---")
    print(text)
else:
    print(f"Error: {resp.text[:500]}")
