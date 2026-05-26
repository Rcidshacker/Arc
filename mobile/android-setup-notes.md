# Android Setup Notes — After `expo prebuild`

Run `expo prebuild --platform android` from the `mobile/` directory before the first native build.
After prebuild completes, verify the following manual additions are present.

---

## 1. AndroidManifest.xml

File path: `mobile/android/app/src/main/AndroidManifest.xml`

### Required permissions (should be auto-added by expo plugins, but verify):

```xml
<uses-permission android:name="android.permission.RECORD_AUDIO" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MICROPHONE" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.WAKE_LOCK" />
```

### Required service declaration (add inside `<application>` if missing):

```xml
<service
    android:name="com.voximplant.foregroundservice.VIForegroundService"
    android:foregroundServiceType="microphone"
    android:exported="false" />
```

This service declaration is required for `@voximplant/react-native-foreground-service` to function
on Android 14+ (API 34+). Without `foregroundServiceType="microphone"`, the foreground service
will crash when started during audio recording.

---

## 2. Notification Icon

The foreground service config references `ic_notification` as the icon name.

Create a notification icon at:
```
mobile/android/app/src/main/res/drawable/ic_notification.png
```

Recommended size: 24x24dp (generate for all densities: mdpi, hdpi, xhdpi, xxhdpi, xxxhdpi).
Use a white monochrome icon on a transparent background (Android notification icon requirement).

Alternatively, copy an existing drawable and rename it, or use Android Studio's
Image Asset Studio to generate the notification icon.

---

## 3. Gradle / React Native Reanimated

In `mobile/android/app/build.gradle`, confirm the reanimated plugin is applied.
It should be auto-added by `expo prebuild`, but verify the following at the bottom of the file:

```groovy
apply plugin: 'com.facebook.react'
```

And in `android/build.gradle`, confirm that the React Native version matches 0.74.x.

---

## 4. Build Commands

```powershell
# From the mobile/ directory:

# Run on a connected Android device or emulator
npx expo run:android

# Local EAS build (requires eas-cli installed globally)
eas build --platform android --local

# Install eas-cli if needed
npm install -g eas-cli
```

---

## 5. Android 14 Foreground Service Requirement

Android 14 (API 34) enforces that foreground services declare their type in the manifest
AND that the app holds the corresponding runtime permission before calling `startForegroundService()`.

The code in `src/services/audioRecorder.ts` calls `VIForegroundService.startService()` BEFORE
`Audio.Recording.createAsync()` to satisfy this requirement. Do not reorder these calls.

If the app targets API 34+ and the service declaration is missing `foregroundServiceType="microphone"`,
Android will throw a `ForegroundServiceStartNotAllowedException` at runtime.

---

## 6. Camera Permission Note

`expo-camera` handles camera permission at the JS layer via `useCameraPermissions()`.
The `CAMERA` permission in `app.json` ensures the manifest entry is present after prebuild.
No additional native configuration is needed for QR scanning.
