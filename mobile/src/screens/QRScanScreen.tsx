import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
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

function WebUrlInput({ onConnect }: { onConnect: (url: string) => void }): React.JSX.Element {
  const [inputUrl, setInputUrl] = useState('');
  const [error, setError] = useState('');

  function handleConnect(): void {
    const trimmed = inputUrl.trim();
    if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) {
      setError('URL must start with http:// or https://');
      return;
    }
    setError('');
    onConnect(trimmed);
  }

  return (
    <KeyboardAvoidingView style={styles.center} behavior="padding">
      <Text style={styles.title}>Pair with Laptop</Text>
      <Text style={styles.subtitle}>Enter the URL shown on your Arc dashboard</Text>
      <TextInput
        style={styles.input}
        value={inputUrl}
        onChangeText={(v) => { setInputUrl(v); setError(''); }}
        placeholder="http://192.168.x.x:8000"
        placeholderTextColor={Colors.textMuted}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        onSubmitEditing={handleConnect}
        returnKeyType="go"
      />
      {error.length > 0 && <Text style={styles.errorText}>{error}</Text>}
      <TouchableOpacity style={styles.button} onPress={handleConnect} activeOpacity={0.8}>
        <Text style={styles.buttonText}>Connect</Text>
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );
}

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
    return (
      <View style={styles.container}>
        <Text style={styles.subtitle}>Requesting camera…</Text>
      </View>
    );
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

export function QRScanScreen({ navigation }: Props): React.JSX.Element {
  async function handleConnect(url: string): Promise<void> {
    try { await setServerUrl(url); } catch { /* non-fatal on web */ }
    navigation.goBack();
  }

  if (Platform.OS === 'web') {
    return (
      <View style={styles.container}>
        <WebUrlInput onConnect={handleConnect} />
      </View>
    );
  }
  return <NativeScanner onSuccess={handleConnect} />;
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
