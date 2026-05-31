import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  Alert,
  ActivityIndicator,
} from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  withRepeat,
  withSequence,
  Easing,
  cancelAnimation,
} from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import type { StackScreenProps } from '@react-navigation/stack';
import type { RootStackParamList } from '../../App';
import { Colors } from '../theme/colors';
import { Typography } from '../theme/typography';
import { setServerUrl } from '../services/storage';

let CameraView: React.ComponentType<any> | null = null;
let useCameraPermissions: (() => [any, () => Promise<any>]) | null = null;
if (Platform.OS !== 'web') {
  try {
    const m = require('expo-camera');
    CameraView = m.CameraView;
    useCameraPermissions = m.useCameraPermissions;
  } catch { /* no-op */ }
}

type Props = StackScreenProps<RootStackParamList, 'QRScan'>;
type ConnectStep = 'input' | 'connecting' | 'connected' | 'error';

// ---------------------------------------------------------------------------
// Connection animation overlay — shows after successful connect
// ---------------------------------------------------------------------------

function ConnectedOverlay({ url }: { url: string }): React.JSX.Element {
  const checkScale = useSharedValue(0);
  const ringScale = useSharedValue(0.4);
  const ringOpacity = useSharedValue(1);
  const textOpacity = useSharedValue(0);

  useEffect(() => {
    checkScale.value = withSpring(1, { damping: 10, stiffness: 120 });
    ringScale.value = withTiming(2.8, { duration: 900, easing: Easing.out(Easing.ease) });
    ringOpacity.value = withTiming(0, { duration: 900 });
    textOpacity.value = withTiming(1, { duration: 500 });
  }, []);

  const checkStyle = useAnimatedStyle(() => ({
    transform: [{ scale: checkScale.value }],
  }));
  const ringStyle = useAnimatedStyle(() => ({
    transform: [{ scale: ringScale.value }],
    opacity: ringOpacity.value,
  }));
  const textStyle = useAnimatedStyle(() => ({ opacity: textOpacity.value }));

  return (
    <View style={styles.center}>
      <View style={styles.animationWrapper}>
        <Animated.View style={[styles.ring, ringStyle]} />
        <Animated.View style={checkStyle}>
          <Ionicons name="checkmark-circle" size={72} color={Colors.success} />
        </Animated.View>
      </View>
      <Animated.Text style={[styles.connectedTitle, textStyle]}>Connected to Arc</Animated.Text>
      <Animated.Text style={[styles.connectedUrl, textStyle]} numberOfLines={1}>{url}</Animated.Text>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Connecting spinner
// ---------------------------------------------------------------------------

function ConnectingView(): React.JSX.Element {
  const spinnerOpacity = useSharedValue(0);
  useEffect(() => {
    spinnerOpacity.value = withTiming(1, { duration: 200 });
  }, []);
  const style = useAnimatedStyle(() => ({ opacity: spinnerOpacity.value }));
  return (
    <Animated.View style={[styles.center, style]}>
      <ActivityIndicator size="large" color={Colors.accent} />
      <Text style={[styles.subtitle, { marginTop: 20 }]}>Connecting to Arc…</Text>
    </Animated.View>
  );
}

// ---------------------------------------------------------------------------
// Web URL input form
// ---------------------------------------------------------------------------

function WebUrlInput({
  onConnect,
  errorMsg,
  onClearError,
}: {
  onConnect: (url: string) => void;
  errorMsg: string;
  onClearError: () => void;
}): React.JSX.Element {
  const [inputUrl, setInputUrl] = useState('');
  const [localError, setLocalError] = useState('');
  const [showHttpWarning, setShowHttpWarning] = useState(false);

  function handleConnect(): void {
    const trimmed = inputUrl.trim();
    try {
      const parsed = new URL(trimmed);
      if (!['http:', 'https:'].includes(parsed.protocol)) {
        setLocalError('URL must start with http:// or https://');
        return;
      }
      if (!parsed.hostname) {
        setLocalError('Enter a valid URL, e.g. http://192.168.1.10:8000');
        return;
      }
      setLocalError('');
      setShowHttpWarning(parsed.protocol === 'http:');
      onConnect(trimmed);
    } catch {
      setLocalError('Invalid URL format. Example: http://192.168.1.10:8000');
    }
  }

  const displayError = errorMsg || localError;

  return (
    <KeyboardAvoidingView style={styles.center} behavior="padding">
      <Text style={styles.title}>Pair with Laptop</Text>
      <Text style={styles.subtitle}>Enter the URL shown on your Arc dashboard</Text>
      <TextInput
        style={styles.input}
        value={inputUrl}
        onChangeText={(v) => { setInputUrl(v); setLocalError(''); onClearError(); }}
        placeholder="http://192.168.x.x:8000"
        placeholderTextColor={Colors.textMuted}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        onSubmitEditing={handleConnect}
        returnKeyType="go"
        testID="server-url-input"
      />
      {displayError.length > 0 && (
        <Text style={styles.errorText}>{displayError}</Text>
      )}
      <TouchableOpacity style={styles.button} onPress={handleConnect} activeOpacity={0.8}>
        <Text style={styles.buttonText}>Connect</Text>
      </TouchableOpacity>
      {showHttpWarning && !displayError && (
        <Text style={styles.httpWarningText}>⚠ Unencrypted — safe for local network</Text>
      )}
    </KeyboardAvoidingView>
  );
}

// ---------------------------------------------------------------------------
// Native QR scanner
// ---------------------------------------------------------------------------

function NativeScanner({ onSuccess }: { onSuccess: (url: string) => void }): React.JSX.Element {
  const [permission, requestPermission] = useCameraPermissions!();
  const [hasScanned, setHasScanned] = useState(false);

  useEffect(() => {
    if (permission && !permission.granted && permission.canAskAgain) requestPermission();
  }, [permission, requestPermission]);

  function handleBarCodeScanned({ data }: { data: string }): void {
    if (hasScanned) return;
    const trimmed = data.trim();
    if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) {
      Alert.alert('Invalid QR Code', 'Does not contain a valid server URL.', [
        { text: 'Try Again', onPress: () => setHasScanned(false) },
      ]);
      setHasScanned(true);
      return;
    }
    setHasScanned(true);
    onSuccess(trimmed);
  }

  if (!permission) {
    return <View style={styles.container}><Text style={styles.subtitle}>Requesting camera…</Text></View>;
  }
  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={styles.subtitle}>Camera access required to scan QR code.</Text>
        <TouchableOpacity style={styles.button} onPress={requestPermission}>
          <Text style={styles.buttonText}>Grant Permission</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const CameraComponent = CameraView!;
  return (
    <View style={styles.container}>
      <CameraComponent
        style={{ flex: 1, width: '100%' }}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={hasScanned ? undefined : handleBarCodeScanned}
      >
        <View style={styles.overlay}>
          <Text style={styles.instruction}>Scan the QR code from Arc dashboard</Text>
          <View style={styles.scanFrame} />
        </View>
      </CameraComponent>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Main screen
// ---------------------------------------------------------------------------

export function QRScanScreen({ navigation, route }: Props): React.JSX.Element {
  const [step, setStep] = useState<ConnectStep>('input');
  const [errorMsg, setErrorMsg] = useState('');
  const [connectedUrl, setConnectedUrl] = useState('');

  async function handleConnect(url: string): Promise<void> {
    setStep('connecting');
    setErrorMsg('');

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 4000);
      try {
        await fetch(`${url}/`, {
          signal: controller.signal,
          ...(Platform.OS === 'web' ? { mode: 'no-cors' as RequestMode } : {}),
        });
      } finally {
        clearTimeout(timeoutId);
      }
    } catch (fetchErr) {
      const isAbort = fetchErr instanceof Error && fetchErr.name === 'AbortError';
      setErrorMsg(isAbort ? 'Connection timed out. Check URL.' : 'Cannot reach server. Check URL and WiFi.');
      setStep('error');
      return;
    }

    // Save URL before showing animation
    try { await setServerUrl(url); } catch { /* non-fatal */ }
    setConnectedUrl(url);
    setStep('connected');

    // Wait for animation, then navigate
    await new Promise<void>((res) => setTimeout(res, 1200));
    navigation.goBack();
  }

  // Close/back button (shown in input and error states)
  const showCloseBtn = step === 'input' || step === 'error';

  return (
    <View style={styles.container}>
      {showCloseBtn && (
        <TouchableOpacity style={styles.closeBtn} onPress={() => navigation.goBack()}>
          <Ionicons name="close" size={26} color={Colors.textMuted} />
        </TouchableOpacity>
      )}

      {step === 'connected' && <ConnectedOverlay url={connectedUrl} />}
      {step === 'connecting' && <ConnectingView />}
      {(step === 'input' || step === 'error') && (
        Platform.OS === 'web'
          ? (
            <WebUrlInput
              onConnect={handleConnect}
              errorMsg={errorMsg}
              onClearError={() => setErrorMsg('')}
            />
          )
          : <NativeScanner onSuccess={handleConnect} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  center: {
    flex: 1,
    backgroundColor: Colors.bg,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 32,
  },
  closeBtn: {
    position: 'absolute',
    top: 56,
    right: 20,
    zIndex: 10,
    padding: 8,
  },
  // Connection animation
  animationWrapper: {
    width: 120,
    height: 120,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  ring: {
    position: 'absolute',
    width: 72,
    height: 72,
    borderRadius: 36,
    borderWidth: 2,
    borderColor: Colors.success,
  },
  connectedTitle: {
    color: Colors.success,
    fontSize: Typography.size.xl,
    fontFamily: Typography.family.bold,
    marginBottom: 8,
    textAlign: 'center',
  },
  connectedUrl: {
    color: Colors.textMuted,
    fontSize: Typography.size.sm,
    fontFamily: Typography.family.mono,
    textAlign: 'center',
    maxWidth: 280,
  },
  // Input form
  title: {
    color: Colors.text,
    fontSize: Typography.size.xl,
    fontFamily: Typography.family.bold,
    marginBottom: 8,
    textAlign: 'center',
  },
  subtitle: {
    color: Colors.textMuted,
    fontSize: Typography.size.sm,
    fontFamily: Typography.family.ui,
    textAlign: 'center',
    marginBottom: 32,
  },
  instruction: {
    color: Colors.text,
    fontSize: Typography.size.base,
    fontFamily: Typography.family.ui,
    textAlign: 'center',
    paddingTop: 60,
    paddingHorizontal: 24,
  },
  input: {
    width: '100%',
    maxWidth: 400,
    backgroundColor: Colors.bgElevated,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 16,
    color: Colors.text,
    fontSize: Typography.size.base,
    fontFamily: Typography.family.ui,
    marginBottom: 8,
  },
  errorText: {
    color: Colors.error,
    fontSize: Typography.size.sm,
    marginBottom: 12,
    textAlign: 'center',
  },
  httpWarningText: {
    color: Colors.textMuted,
    fontSize: Typography.size.sm,
    marginTop: 8,
    textAlign: 'center',
  },
  button: {
    backgroundColor: Colors.accent,
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 32,
    alignItems: 'center',
    width: '100%',
    maxWidth: 400,
    marginTop: 8,
  },
  buttonText: {
    color: Colors.text,
    fontSize: Typography.size.base,
    fontFamily: Typography.family.bold,
  },
  overlay: {
    flex: 1,
    justifyContent: 'flex-start',
    alignItems: 'center',
  },
  scanFrame: {
    width: 220,
    height: 220,
    borderWidth: 2,
    borderColor: Colors.accent,
    borderRadius: 12,
    marginTop: 80,
  },
});
