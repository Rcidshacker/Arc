import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Alert,
  TouchableOpacity,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import type { StackScreenProps } from '@react-navigation/stack';

import type { RootStackParamList } from '../../App';
import { setServerUrl } from '../services/storage';

type Props = StackScreenProps<RootStackParamList, 'QRScanner'>;

export function QRScannerScreen({ navigation }: Props): React.JSX.Element {
  const [permission, requestPermission] = useCameraPermissions();
  const [hasScanned, setHasScanned] = useState(false);

  useEffect(() => {
    if (permission && !permission.granted && permission.canAskAgain) {
      requestPermission();
    }
  }, [permission, requestPermission]);

  function handleBarCodeScanned({ data }: { data: string }): void {
    if (hasScanned) return;

    const trimmed = data.trim();

    if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) {
      Alert.alert(
        'Invalid QR Code',
        'This QR code does not contain a valid server URL. Please scan the QR code shown on your laptop dashboard.',
        [{ text: 'Try Again', onPress: () => setHasScanned(false) }],
      );
      setHasScanned(true);
      return;
    }

    setHasScanned(true);

    setServerUrl(trimmed)
      .then(() => {
        navigation.replace('Recorder');
      })
      .catch(() => {
        Alert.alert('Error', 'Failed to save server URL. Please try again.', [
          { text: 'Retry', onPress: () => setHasScanned(false) },
        ]);
      });
  }

  if (!permission) {
    return (
      <View style={styles.container}>
        <Text style={styles.messageText}>Requesting camera permission…</Text>
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.container}>
        <Text style={styles.messageText}>Camera access is required to scan the QR code.</Text>
        <TouchableOpacity style={styles.permissionButton} onPress={requestPermission}>
          <Text style={styles.permissionButtonText}>Grant Permission</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.instructionContainer}>
        <Text style={styles.instructionText}>
          Scan the QR code from your laptop dashboard
        </Text>
      </View>

      <CameraView
        style={styles.camera}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={hasScanned ? undefined : handleBarCodeScanned}
      >
        <View style={styles.overlay}>
          <View style={styles.scanFrame} />
        </View>
      </CameraView>

      <View style={styles.bottomContainer}>
        <Text style={styles.subText}>
          Point your camera at the QR code displayed on Arc's laptop dashboard
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A0A0A',
    justifyContent: 'center',
    alignItems: 'center',
  },
  instructionContainer: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    paddingTop: 60,
    paddingHorizontal: 24,
    paddingBottom: 20,
    backgroundColor: 'rgba(10, 10, 10, 0.85)',
    zIndex: 10,
    alignItems: 'center',
  },
  instructionText: {
    color: '#F5F5F5',
    fontSize: 16,
    fontWeight: '500',
    textAlign: 'center',
    letterSpacing: 0.3,
  },
  camera: {
    flex: 1,
    width: '100%',
  },
  overlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'transparent',
  },
  scanFrame: {
    width: 240,
    height: 240,
    borderWidth: 2,
    borderColor: '#6366F1',
    borderRadius: 16,
    backgroundColor: 'transparent',
  },
  bottomContainer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    paddingBottom: 48,
    paddingHorizontal: 32,
    paddingTop: 20,
    backgroundColor: 'rgba(10, 10, 10, 0.85)',
    alignItems: 'center',
  },
  subText: {
    color: '#6B7280',
    fontSize: 13,
    textAlign: 'center',
    lineHeight: 18,
  },
  messageText: {
    color: '#F5F5F5',
    fontSize: 15,
    textAlign: 'center',
    paddingHorizontal: 32,
    marginBottom: 24,
  },
  permissionButton: {
    backgroundColor: '#6366F1',
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 28,
  },
  permissionButtonText: {
    color: '#F5F5F5',
    fontSize: 15,
    fontWeight: '600',
  },
});
