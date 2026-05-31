/**
 * TESTING GUIDE:
 * - Web (npx expo start --web): Uses MediaRecorder API. Tests UI + upload flow.
 *   Background/screen-off recording is NOT available on web — that's fine.
 * - Expo Go: Uses expo-av for recording (expo-audio AudioRecorder not available
 *   in Expo Go bundle). Full expo-audio migration applies to APK build only.
 * - APK (after expo prebuild): Full background recording with screen off. Production behavior.
 */
import { Platform } from 'react-native';

// expo-av: used for recording on native (Expo Go compatible)
let ExpoAV: any = null;
if (Platform.OS !== 'web') {
  ExpoAV = require('expo-av');
}

// VIForegroundService: native only, not available in Expo Go or on web
let VIForegroundService: {
  getInstance(): {
    startService(config: unknown): Promise<void>;
    stopService(): Promise<void>;
  };
} | null = null;

if (Platform.OS !== 'web') {
  try {
    VIForegroundService = require('@voximplant/react-native-foreground-service').default;
  } catch {
    // Not available in Expo Go — VIForegroundService calls will no-op
  }
}
console.log('VIForegroundService loaded:', !!VIForegroundService);

export interface RecordingState {
  isRecording: boolean;
  durationMs: number;
  uri: string | null;
}

// Native recording state
let activeRecording: any | null = null;

// Web recording state
let webMediaRecorder: MediaRecorder | null = null;
let webChunks: BlobPart[] = [];
let lastWebBlob: Blob | null = null;

let recordingStartTime: number = 0;

const FOREGROUND_SERVICE_CONFIG = {
  channelId: 'arc_recording',
  channelName: 'Arc Recording',
  notificationTitle: 'Arc',
  notificationText: 'Recording in progress...',
  notificationIconName: 'ic_notification',
  id: 3456,
  button: false,
} as const;

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function startRecording(): Promise<void> {
  if (Platform.OS === 'web') {
    return startWebRecording();
  }
  return startNativeRecording();
}

export async function stopRecording(): Promise<string> {
  if (Platform.OS === 'web') {
    return stopWebRecording();
  }
  return stopNativeRecording();
}

export function getLastWebBlob(): Blob | null { return lastWebBlob; }

export function getRecordingStatus(): RecordingState {
  const isRecording = Platform.OS === 'web'
    ? webMediaRecorder !== null
    : activeRecording !== null;

  return {
    isRecording,
    durationMs: isRecording ? Date.now() - recordingStartTime : 0,
    uri: null,
  };
}

// ---------------------------------------------------------------------------
// Web implementation — MediaRecorder API
// ---------------------------------------------------------------------------

async function startWebRecording(): Promise<void> {
  if (webMediaRecorder !== null) {
    throw new Error('A recording is already in progress.');
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('Audio recording is not supported in this browser.');
  }

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  webChunks = [];
  const recorder = new MediaRecorder(stream);

  recorder.ondataavailable = (e: BlobEvent) => {
    if (e.data.size > 0) {
      webChunks.push(e.data);
    }
  };

  recorder.start(1000); // collect chunks every 1s
  webMediaRecorder = recorder;
  recordingStartTime = Date.now();
}

async function stopWebRecording(): Promise<string> {
  if (webMediaRecorder === null) {
    throw new Error('No active web recording to stop.');
  }

  return new Promise<string>((resolve, reject) => {
    const recorder = webMediaRecorder!;

    recorder.onstop = () => {
      const mimeType = recorder.mimeType || 'audio/webm';
      const blob = new Blob(webChunks, { type: mimeType });
      webChunks = [];
      webMediaRecorder = null;
      recordingStartTime = 0;

      lastWebBlob = blob;
      const url = URL.createObjectURL(blob);
      resolve(url);
    };

    recorder.onerror = () => {
      webMediaRecorder = null;
      webChunks = [];
      reject(new Error('MediaRecorder error while stopping.'));
    };

    recorder.stream.getTracks().forEach((track) => track.stop());
    recorder.stop();
  });
}

// ---------------------------------------------------------------------------
// Native implementation — expo-av + VIForegroundService
// ---------------------------------------------------------------------------

async function startNativeRecording(): Promise<void> {
  if (activeRecording !== null) {
    throw new Error('A recording is already in progress.');
  }

  const { Audio } = ExpoAV;
  const { status } = await Audio.requestPermissionsAsync();
  if (status !== 'granted') {
    throw new Error('Microphone permission denied.');
  }

  await Audio.setAudioModeAsync({
    allowsRecordingIOS: true,
    playsInSilentModeIOS: true,
  });

  // Start foreground service BEFORE recording (Android 14 requirement)
  // No-ops silently in Expo Go — recording still works, just no screen-off persistence
  try {
    const svc = VIForegroundService?.getInstance?.();
    if (svc) await svc.startService(FOREGROUND_SERVICE_CONFIG);
  } catch {
    // Expo Go: VIForegroundService not available, recording continues without FGS
  }

  const { recording } = await Audio.Recording.createAsync(
    Audio.RecordingOptionsPresets.HIGH_QUALITY,
  );
  activeRecording = recording;
  recordingStartTime = Date.now();
}

async function stopNativeRecording(): Promise<string> {
  if (activeRecording === null) {
    throw new Error('No active recording to stop.');
  }

  try {
    const svc = VIForegroundService?.getInstance?.();
    if (svc) await svc.stopService();
  } catch {
    // Expo Go: FGS not running, no-op
  }

  await activeRecording.stopAndUnloadAsync();
  const uri = activeRecording.getURI();
  activeRecording = null;
  recordingStartTime = 0;

  if (uri === null || uri === undefined) {
    throw new Error('Recording completed but no file URI was returned.');
  }

  await ExpoAV.Audio.setAudioModeAsync({ allowsRecordingIOS: false });

  return uri;
}
