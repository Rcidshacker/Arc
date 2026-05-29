/**
 * TESTING GUIDE:
 * - Web (npx expo start --web): Uses MediaRecorder API. Tests UI + upload flow.
 *   Background/screen-off recording is NOT available on web — that's fine.
 * - Expo Go: Uses expo-av. Tests recording + upload. VIForegroundService no-ops
 *   (custom native module not included in Expo Go).
 * - APK (after expo prebuild): Full background recording with screen off. Production behavior.
 */
import { Platform } from 'react-native';
import { Audio } from 'expo-av';

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

export interface RecordingState {
  isRecording: boolean;
  durationMs: number;
  uri: string | null;
}

// Native recording state
let activeRecording: Audio.Recording | null = null;

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
      // Revoke previous blob URLs to avoid memory leaks (best effort)
      const url = URL.createObjectURL(blob);
      resolve(url);
    };

    recorder.onerror = () => {
      webMediaRecorder = null;
      webChunks = [];
      reject(new Error('MediaRecorder error while stopping.'));
    };

    // Stop all audio tracks so the browser releases the microphone
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

  const { status } = await Audio.requestPermissionsAsync();
  if (status !== 'granted') {
    throw new Error('Microphone permission denied. Please enable it in Settings.');
  }

  await Audio.setAudioModeAsync({
    allowsRecordingIOS: true,
    playsInSilentModeIOS: true,
    shouldDuckAndroid: false,
    playThroughEarpieceAndroid: false,
  });

  // Start foreground service BEFORE recording (Android 14 requirement)
  // No-ops if VIForegroundService is null (Expo Go)
  if (VIForegroundService !== null) {
    await VIForegroundService.getInstance().startService(FOREGROUND_SERVICE_CONFIG);
  }

  const recordingOptions: Audio.RecordingOptions = {
    ...Audio.RecordingOptionsPresets.HIGH_QUALITY,
    android: {
      extension: '.m4a',
      outputFormat: Audio.AndroidOutputFormat.MPEG_4,
      audioEncoder: Audio.AndroidAudioEncoder.AAC,
      sampleRate: 44100,
      numberOfChannels: 2,
      bitRate: 128000,
    },
    ios: {
      ...Audio.RecordingOptionsPresets.HIGH_QUALITY.ios,
    },
    web: {
      ...Audio.RecordingOptionsPresets.HIGH_QUALITY.web,
    },
  };

  const { recording } = await Audio.Recording.createAsync(recordingOptions);
  activeRecording = recording;
  recordingStartTime = Date.now();
}

async function stopNativeRecording(): Promise<string> {
  if (activeRecording === null) {
    throw new Error('No active recording to stop.');
  }

  if (VIForegroundService !== null) {
    await VIForegroundService.getInstance().stopService();
  }

  await activeRecording.stopAndUnloadAsync();
  const uri = activeRecording.getURI();
  activeRecording = null;
  recordingStartTime = 0;

  if (uri === null || uri === undefined) {
    throw new Error('Recording completed but no file URI was returned.');
  }

  await Audio.setAudioModeAsync({
    allowsRecordingIOS: false,
  });

  return uri;
}
