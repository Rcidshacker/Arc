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
  withSequence,
  withTiming,
  cancelAnimation,
  Easing,
} from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';

import type { MainTabParamList } from '../../App';
import { Colors } from '../theme/colors';
import { Typography } from '../theme/typography';
import { startRecording, stopRecording, getLastWebBlob } from '../services/audioRecorder';
import { saveRecording } from '../services/recordingStore';

type ToastState = 'hidden' | 'visible' | 'fading';

type Props = BottomTabScreenProps<MainTabParamList, 'Recorder'>;

function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const mm = String(minutes).padStart(2, '0');
  const ss = String(seconds).padStart(2, '0');
  if (hours > 0) return `${String(hours).padStart(2, '0')}:${mm}:${ss}`;
  return `${mm}:${ss}`;
}

function formatDateTime(): string {
  const now = new Date();
  return now.toLocaleDateString('en-GB', {
    weekday: 'short', day: 'numeric', month: 'short',
  }) + ' · ' + now.toLocaleTimeString('en-GB', {
    hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

export function RecorderScreen(_props: Props): React.JSX.Element {
  const [isRecording, setIsRecording] = useState(false);
  const [durationMs, setDurationMs] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [toast, setToast] = useState<ToastState>('hidden');
  const [dateLabel, setDateLabel] = useState(formatDateTime());

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const pulseScale = useSharedValue(1);
  const pulseOpacity = useSharedValue(0);
  const toastOpacity = useSharedValue(0);

  const pulseStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pulseScale.value }],
    opacity: pulseOpacity.value,
  }));

  const toastStyle = useAnimatedStyle(() => ({ opacity: toastOpacity.value }));

  useEffect(() => {
    const interval = setInterval(() => setDateLabel(formatDateTime()), 60_000);
    return () => {
      clearInterval(interval);
      if (timerRef.current !== null) clearInterval(timerRef.current);
      if (toastTimer.current !== null) clearTimeout(toastTimer.current);
    };
  }, []);

  const startPulse = useCallback(() => {
    pulseScale.value = 1;
    pulseOpacity.value = 0.7;
    pulseScale.value = withRepeat(
      withSequence(
        withTiming(1.8, { duration: 1000, easing: Easing.out(Easing.ease) }),
        withTiming(1, { duration: 0 }),
      ),
      -1,
      false,
    );
    pulseOpacity.value = withRepeat(
      withSequence(
        withTiming(0, { duration: 1000, easing: Easing.out(Easing.ease) }),
        withTiming(0.7, { duration: 0 }),
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

  function showToast(): void {
    toastOpacity.value = withTiming(1, { duration: 200 });
    setToast('visible');
    if (toastTimer.current !== null) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => {
      toastOpacity.value = withTiming(0, { duration: 400 });
      setToast('fading');
      setTimeout(() => setToast('hidden'), 400);
    }, 1500);
  }

  async function handleToggle(): Promise<void> {
    if (isProcessing) return;
    if (!isRecording) {
      await handleStart();
    } else {
      await handleStop();
    }
  }

  async function handleStart(): Promise<void> {
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
      Alert.alert('Error', err instanceof Error ? err.message : 'Failed to start recording.');
    } finally {
      setIsProcessing(false);
    }
  }

  async function handleStop(): Promise<void> {
    setIsProcessing(true);
    stopPulse();
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    const elapsed = Date.now() - startTimeRef.current;
    try {
      const uri = await stopRecording();
      const source: Blob | string = Platform.OS === 'web'
        ? (getLastWebBlob() ?? new Blob())
        : uri;
      await saveRecording(source, elapsed);
      showToast();
    } catch (err) {
      Alert.alert('Error', err instanceof Error ? err.message : 'Failed to save recording.');
    } finally {
      setIsRecording(false);
      setDurationMs(0);
      setIsProcessing(false);
    }
  }

  const ringColor = isRecording ? Colors.recording : Colors.accent;
  const statusText = isProcessing
    ? isRecording ? 'Stopping…' : 'Starting…'
    : isRecording ? 'Recording — tap to stop'
    : 'Tap to record';

  return (
    <View style={styles.container}>
      <Text style={styles.dateLabel}>{dateLabel}</Text>
      <Text style={styles.timer}>{formatDuration(durationMs)}</Text>

      <View style={styles.buttonWrapper}>
        <Animated.View
          style={[styles.pulseRing, { borderColor: ringColor }, pulseStyle]}
        />
        <TouchableOpacity
          style={[styles.recordButton, { backgroundColor: isRecording ? Colors.recording : Colors.bgElevated }]}
          onPress={handleToggle}
          activeOpacity={0.85}
          disabled={isProcessing}
        >
          <Ionicons
            name={isRecording ? 'stop' : 'mic'}
            size={40}
            color={isRecording ? Colors.text : Colors.accent}
          />
        </TouchableOpacity>
        <View style={[styles.accentRing, { borderColor: isRecording ? 'transparent' : Colors.accent }]} />
      </View>

      <Text style={styles.statusText}>{statusText}</Text>

      {toast !== 'hidden' && (
        <Animated.View style={[styles.toast, toastStyle]}>
          <Text style={styles.toastText}>Saved to library</Text>
        </Animated.View>
      )}

      {Platform.OS === 'web' && (
        <Text style={styles.webCaveat}>
          Background recording unavailable in browser — use Android app
        </Text>
      )}
    </View>
  );
}

const BUTTON_SIZE = 120;
const PULSE_SIZE = BUTTON_SIZE + 60;
const RING_SIZE = BUTTON_SIZE + 20;

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.bg,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 24,
  },
  dateLabel: {
    position: 'absolute',
    top: 56,
    left: 24,
    color: Colors.textMuted,
    fontSize: Typography.size.sm,
    fontFamily: Typography.family.mono,
  },
  timer: {
    color: Colors.text,
    fontSize: Typography.size.display,
    fontFamily: Typography.family.mono,
    letterSpacing: 4,
    marginBottom: 48,
  },
  buttonWrapper: {
    width: PULSE_SIZE,
    height: PULSE_SIZE,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  pulseRing: {
    position: 'absolute',
    width: PULSE_SIZE,
    height: PULSE_SIZE,
    borderRadius: PULSE_SIZE / 2,
    borderWidth: 2,
    backgroundColor: 'transparent',
    pointerEvents: 'none',
  },
  accentRing: {
    position: 'absolute',
    width: RING_SIZE,
    height: RING_SIZE,
    borderRadius: RING_SIZE / 2,
    borderWidth: 1.5,
    backgroundColor: 'transparent',
    pointerEvents: 'none',
  },
  recordButton: {
    width: BUTTON_SIZE,
    height: BUTTON_SIZE,
    borderRadius: BUTTON_SIZE / 2,
    justifyContent: 'center',
    alignItems: 'center',
  },
  statusText: {
    color: Colors.textMuted,
    fontSize: Typography.size.sm,
    fontFamily: Typography.family.ui,
    letterSpacing: 0.5,
  },
  toast: {
    position: 'absolute',
    bottom: 100,
    backgroundColor: Colors.bgElevated,
    borderRadius: 20,
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  toastText: {
    color: Colors.text,
    fontSize: Typography.size.sm,
    fontFamily: Typography.family.ui,
  },
  webCaveat: {
    position: 'absolute',
    bottom: 24,
    color: Colors.textMuted,
    fontSize: Typography.size.xs,
    fontFamily: Typography.family.ui,
    textAlign: 'center',
    paddingHorizontal: 32,
  },
});
