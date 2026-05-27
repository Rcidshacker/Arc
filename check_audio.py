import soundfile as sf
from pathlib import Path

test = Path(r"C:\llama\test_audio.wav")
meeting = Path(r"C:\Users\Lenovo\Desktop\arc\temp\7373832e-c593-445b-86fd-850bd9658111_normalized.wav")

for f in [test, meeting]:
    if f.exists():
        info = sf.info(str(f))
        dur = info.frames / info.samplerate
        print(f"{f.name}: {dur:.1f}s, {f.stat().st_size/1024/1024:.2f} MB")
    else:
        print(f"{f.name}: NOT FOUND")
