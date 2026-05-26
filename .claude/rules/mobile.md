---
paths:
  - "mobile/src/**/*.ts"
  - "mobile/src/**/*.tsx"
  - "mobile/App.tsx"
---

- Expo bare workflow only — no Expo Go, no managed workflow APIs
- Foreground Service must be started before recording begins and stopped after upload completes
- Server URL stored in AsyncStorage — never hardcoded
- Upload via `axios` with `onUploadProgress` callback for progress bar
- Recording format: AAC/M4A at 128kbps via `expo-av` Audio API
- `androidManifest.xml` must declare `android:foregroundServiceType="microphone"` and `POST_NOTIFICATIONS` permission
- Three screens total: QRScannerScreen → RecorderScreen → UploadStatusScreen; no navigation drawer
- Dark theme only: background `#0A0A0A`, surface `#141414`, accent `#6366F1`, record-active `#EF4444`
- Typography: Inter for all UI, timer display uses Inter weight 300 at 48px
- All API calls use server URL from AsyncStorage — must handle network errors with retry UI
