# Expo Go Physical Device Testing Guide

## Device & Server Setup

| Item | Value |
|------|-------|
| Expo Go version | 54.0.8 (SDK 54) |
| Laptop WiFi IP | 192.168.1.103 |
| Arc server URL | http://192.168.1.103:8000 |
| Expo dev server | exp://192.168.1.103:8081 |

Both laptop and phone must be on the same WiFi network.

---

## What Works in Expo Go

- **Splash screen** — video plays natively via expo-video
- **RecorderScreen** — audio recording via expo-audio (screen must stay ON)
- **Library** — playback, select mode, send flow all work
- **QRScanScreen** — native camera QR scan works (not the web URL-input fallback)
- **Upload to Arc server** — over WiFi to http://192.168.1.103:8000
- **Full pipeline trigger** — server receives file and begins processing

---

## What Does NOT Work in Expo Go

### Background recording (VIForegroundService)
- **Effect:** Recording stops immediately when screen is turned off or app is backgrounded
- **Why:** `VIForegroundService` is a custom native module not bundled in Expo Go
- **This is expected** — full background recording requires the release APK
- The screen-off notification is also missing for the same reason

---

## Manual Test Checklist

Run these in order on the physical device:

1. **Splash** — video plays fullscreen, auto-advances to RecorderScreen
2. **Record** — tap record, speak for 30s with screen ON, tap stop
3. **Toast** — "Saved to library" confirmation appears
4. **Library tab** — recording shows with correct duration
5. **Playback** — tap play, audio plays through speaker
6. **Select → Send** — enter `http://192.168.1.103:8000` in QRScan screen (or scan Arc server QR from laptop browser)
7. **Upload** — per-file progress bar visible during upload
8. **Dashboard** — visit http://192.168.1.103:8000 on laptop, confirm file received

---

## Pairing the App to the Arc Server

In QRScanScreen, either:
- **Scan** the QR code shown at http://192.168.1.103:8000 (auto-generated on startup)
- **Type** `http://192.168.1.103:8000` manually into the URL input

The placeholder text in the input already shows `http://192.168.x.x:8000`.  
No default URL is saved — the app opens QRScanScreen on first launch.

---

## Known Gap

Recording with screen off silently stops. Confirmed limitation of Expo Go.  
**Fix:** Build APK with `npx expo prebuild` + `eas build --platform android --local` after Expo Go validation passes.

---

## Start Commands (two terminals)

```powershell
# Terminal 1 — Arc server
cd C:\Users\Lenovo\Desktop\Code\2026\Arc
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="server"; .venv\Scripts\uvicorn.exe server.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Expo dev server
cd C:\Users\Lenovo\Desktop\Code\2026\Arc\mobile
npx expo start
```

Scan the QR code in Terminal 2 with Expo Go 54.0.8.
