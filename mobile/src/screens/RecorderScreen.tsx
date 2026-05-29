import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Alert,
  Platform,
} from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  withSequence,
  cancelAnimation,
  Easing,
} from 'react-native-reanimated';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';

import type { MainTabParamList } from '../../App';
import { startRecording, stopRecording } from '../services/audioRecorder';
import { getServerUrl } from '../services/storage';

type Props = BottomTabScreenProps<MainTabParamList, 'Recorder'>;

function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  const mm = String(minutes).padStart(2, '0');
  const ss = String(seconds).padStart(2, '0');

  if (hours > 0) {
    const hh = String(hours).padStart(2, '0');
    return `${hh}:${mm}:${ss}`;
  }
  return `${mm}:${ss}`;
}

export function RecorderScreen({ navigation }: Props): React.JSX.Element {
  const [isRecording, setIsRecording] = useState(false);
  const [durationMs, setDurationMs] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);

  // Pulse animation for recording state
  const pulseScale = useSharedValue(1);
  const pulseOpacity = useSharedValue(0);

  const pulseStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pulseScale.value }],
    opacity: pulseOpacity.value,
  }));

  const startPulse = useCallback(() => {
    pulseScale.value = 1;
    pulseOpacity.value = 0.6;
    pulseScale.value = withRepeat(
      withSequence(
        withTiming(1.5, { duration: 900, easing: Easing.out(Easing.ease) }),
        withTiming(1, { duration: 0 }),
      ),
      -1,
      false,
    );
    pulseOpacity.value = withRepeat(
      withSequence(
        withTiming(0, { duration: 900, easing: Easing.out(Easing.ease) }),
        withTiming(0.6, { duration: 0 }),
      ),
      -1,
      false,
    );
  }, [pulseScale, pulseOpacity]);

  const stopPulse = useCallback(() => {
    cancelAnimation(pulseScale);
    cancelAnimation(pulseOpacity);
    pulseScale.value = withTiming(1, { duration: 200 });
    pulseOpacity.value = withTiming(0, { duration: 200 });
  }, [pulseScale, pulseOpacity]);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
      }
    };
  }, []);

  async function handleToggleRecording(): Promise<void> {
    if (isProcessing) return;

    if (!isRecording) {
      await handleStartRecording();
    } else {
      await handleStopRecording();
    }
  }

  async function handleStartRecording(): Promise<void> {
    setIsProcessing(true);
    try {
      await startRecording();
      startTimeRef.current = Date.now();
      setDurationMs(0);
      setIsRecording(true);
      startPulse();

      timerRef.current = setInterval(() => {
        setDurationMs(Date.now() - startTimeRef.current);
      }, 500);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to start recording.';
      Alert.alert('Recording Error', message);
    } finally {
      setIsProcessing(false);
    }
  }

  async function handleStopRecording(): Promise<void> {
    setIsProcessing(true);
    stopPulse();

    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    try {
      const fileUri = await stopRecording();
      setIsRecording(false);
      setDurationMs(0);

      const serverUrl = await getServerUrl();
      if (serverUrl === null) {
        Alert.alert(
          'Server Not Configured',
          'No server URL found. Please scan the QR code again.',
          [{ text: 'Scan QR', onPress: () => (navigation as any).navigate('QRScan') }],
        );
        return;
      }

      (navigation as any).navigate('UploadProgress', { recordingIds: [fileUri], serverUrl });
    } catch (err) {
      setIsRecording(false);
      setDurationMs(0);
      const message =
        err instanceof Error ? err.message : 'Failed to stop recording.';
      Alert.alert('Recording Error', message);
    } finally {
      setIsProcessing(false);
    }
  }

  const buttonColor = isRecording ? '#EF4444' : '#FFFFFF';
  const statusText = isProcessing
    ? isRecording
      ? 'Stopping…'
      : 'Starting…'
    : isRecording
      ? 'Recording… tap to stop'
      : 'Tap to record';

  return (
    <View style={styles.container}>
      {Platform.OS === 'web' && (
        <View style={styles.webBanner}>
          <Text style={styles.webBannerText}>
            Background recording not available in browser — use Android app for full functionality
          </Text>
        </View>
      )}

      <View style={styles.timerContainer}>
        <Text style={styles.timerText}>{formatDuration(durationMs)}</Text>
      </View>

      <View style={styles.buttonWrapper}>
        {/* Animated pulse ring */}
        <Animated.View
          style={[
            styles.pulseRing,
            { borderColor: '#EF4444' },
            pulseStyle,
          ]}
        />

        <TouchableOpacity
          style={[styles.recordButton, { backgroundColor: buttonColor }]}
          onPress={handleToggleRecording}
          activeOpacity={0.8}
          disabled={isProcessing}
        />
      </View>

      <Text style={styles.statusText}>{statusText}</Text>
    </View>
  );
}

const BUTTON_SIZE = 96;
const PULSE_SIZE = BUTTON_SIZE + 32;

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A0A0A',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 24,
  },
  timerContainer: {
    marginBottom: 64,
  },
  timerText: {
    color: '#F5F5F5',
    fontSize: 48,
    fontWeight: '300',
    fontFamily: 'Inter',
    letterSpacing: 2,
    textAlign: 'center',
  },
  buttonWrapper: {
    width: PULSE_SIZE,
    height: PULSE_SIZE,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 32,
  },
  pulseRing: {
    position: 'absolute',
    width: PULSE_SIZE,
    height: PULSE_SIZE,
    borderRadius: PULSE_SIZE / 2,
    borderWidth: 2,
    backgroundColor: 'transparent',
  },
  recordButton: {
    width: BUTTON_SIZE,
    height: BUTTON_SIZE,
    borderRadius: BUTTON_SIZE / 2,
  },
  statusText: {
    color: '#6B7280',
    fontSize: 14,
    letterSpacing: 0.5,
    textAlign: 'center',
  },
  webBanner: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    backgroundColor: '#141414',
    paddingVertical: 8,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  webBannerText: {
    color: '#6B7280',
    fontSize: 11,
    textAlign: 'center',
    letterSpacing: 0.2,
  },
});
