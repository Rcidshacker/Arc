import { Audio } from 'expo-av';
import VIForegroundService from '@voximplant/react-native-foreground-service';

export interface RecordingState {
  isRecording: boolean;
  durationMs: number;
  uri: string | null;
}

let activeRecording: Audio.Recording | null = null;
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

async function requestPermissions(): Promise<void> {
  const { status } = await Audio.requestPermissionsAsync();
  if (status !== 'granted') {
    throw new Error('Microphone permission denied. Please enable it in Settings.');
  }
}

export async function startRecording(): Promise<void> {
  if (activeRecording !== null) {
    throw new Error('A recording is already in progress.');
  }

  await requestPermissions();

  await Audio.setAudioModeAsync({
    allowsRecordingIOS: true,
    playsInSilentModeIOS: true,
    shouldDuckAndroid: false,
    playThroughEarpieceAndroid: false,
  });

  // Start foreground service BEFORE recording (Android 14 requirement)
  await VIForegroundService.getInstance().startService(FOREGROUND_SERVICE_CONFIG);

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

export async function stopRecording(): Promise<string> {
  if (activeRecording === null) {
    throw new Error('No active recording to stop.');
  }

  await VIForegroundService.getInstance().stopService();

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

export function getRecordingStatus(): RecordingState {
  if (activeRecording === null) {
    return {
      isRecording: false,
      durationMs: 0,
      uri: null,
    };
  }

  return {
    isRecording: true,
    durationMs: Date.now() - recordingStartTime,
    uri: null,
  };
}
