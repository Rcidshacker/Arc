import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
} from 'react-native';
import type { StackScreenProps } from '@react-navigation/stack';

import type { RootStackParamList } from '../../App';
import { uploadAudio, type UploadProgress } from '../services/uploader';

type Props = StackScreenProps<RootStackParamList, 'UploadStatus'>;

type UploadPhase = 'uploading' | 'success' | 'error';

interface UploadResult {
  meetingId: string;
  sha256: string;
}

function extractFilename(uri: string): string {
  const parts = uri.split('/');
  return parts[parts.length - 1] ?? 'recording.m4a';
}

export function UploadStatusScreen({ route, navigation }: Props): React.JSX.Element {
  const { fileUri, serverUrl } = route.params;

  const [phase, setPhase] = useState<UploadPhase>('uploading');
  const [progress, setProgress] = useState<UploadProgress>({
    loaded: 0,
    total: 1,
    percent: 0,
  });
  const [result, setResult] = useState<UploadResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>('');

  const filename = extractFilename(fileUri);

  const runUpload = useCallback(async (): Promise<void> => {
    setPhase('uploading');
    setErrorMessage('');
    setProgress({ loaded: 0, total: 1, percent: 0 });

    try {
      const uploadResult = await uploadAudio(fileUri, serverUrl, (p) => {
        setProgress(p);
      });
      setResult(uploadResult);
      setPhase('success');
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Upload failed. Please try again.';
      setErrorMessage(message);
      setPhase('error');
    }
  }, [fileUri, serverUrl]);

  useEffect(() => {
    runUpload();
  }, [runUpload]);

  function handleRecordAnother(): void {
    navigation.navigate('Recorder');
  }

  function handleRetry(): void {
    runUpload();
  }

  function handleBack(): void {
    navigation.navigate('Recorder');
  }

  return (
    <ScrollView
      style={styles.scrollView}
      contentContainerStyle={styles.container}
      bounces={false}
    >
      {/* Back button */}
      <TouchableOpacity style={styles.backButton} onPress={handleBack}>
        <Text style={styles.backButtonText}>← Back</Text>
      </TouchableOpacity>

      <View style={styles.content}>
        {/* Filename */}
        <Text style={styles.filenameText} numberOfLines={1} ellipsizeMode="middle">
          {filename}
        </Text>

        {/* Status icon area */}
        <View style={styles.iconContainer}>
          {phase === 'uploading' && (
            <View style={styles.uploadingIndicator}>
              <Text style={styles.uploadingIcon}>⏫</Text>
            </View>
          )}
          {phase === 'success' && (
            <View style={[styles.statusCircle, styles.successCircle]}>
              <Text style={styles.statusIcon}>✓</Text>
            </View>
          )}
          {phase === 'error' && (
            <View style={[styles.statusCircle, styles.errorCircle]}>
              <Text style={styles.statusIcon}>✕</Text>
            </View>
          )}
        </View>

        {/* Status text */}
        <Text style={styles.statusText}>
          {phase === 'uploading' && 'Uploading…'}
          {phase === 'success' && 'Upload complete — processing on laptop'}
          {phase === 'error' && 'Upload failed'}
        </Text>

        {/* Progress bar */}
        {phase === 'uploading' && (
          <View style={styles.progressContainer}>
            <View style={styles.progressTrack}>
              <View
                style={[
                  styles.progressFill,
                  { width: `${progress.percent}%` },
                ]}
              />
            </View>
            <Text style={styles.progressText}>{progress.percent}%</Text>
          </View>
        )}

        {/* Error details */}
        {phase === 'error' && (
          <Text style={styles.errorText}>{errorMessage}</Text>
        )}

        {/* Success details */}
        {phase === 'success' && result !== null && (
          <View style={styles.detailsContainer}>
            <Text style={styles.detailLabel}>Meeting ID</Text>
            <Text style={styles.detailValue} selectable>
              {result.meetingId}
            </Text>
            <Text style={styles.processingNote}>
              Arc is transcribing and analyzing your recording on the laptop.
            </Text>
          </View>
        )}

        {/* Action buttons */}
        {phase === 'success' && (
          <TouchableOpacity
            style={styles.primaryButton}
            onPress={handleRecordAnother}
            activeOpacity={0.8}
          >
            <Text style={styles.primaryButtonText}>Record another meeting</Text>
          </TouchableOpacity>
        )}

        {phase === 'error' && (
          <TouchableOpacity
            style={styles.primaryButton}
            onPress={handleRetry}
            activeOpacity={0.8}
          >
            <Text style={styles.primaryButtonText}>Retry</Text>
          </TouchableOpacity>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scrollView: {
    flex: 1,
    backgroundColor: '#0A0A0A',
  },
  container: {
    flexGrow: 1,
    backgroundColor: '#0A0A0A',
    paddingHorizontal: 24,
    paddingBottom: 48,
  },
  backButton: {
    marginTop: 56,
    marginBottom: 8,
    alignSelf: 'flex-start',
  },
  backButtonText: {
    color: '#6B7280',
    fontSize: 15,
    letterSpacing: 0.2,
  },
  content: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingTop: 40,
  },
  filenameText: {
    color: '#6B7280',
    fontSize: 13,
    marginBottom: 40,
    maxWidth: '80%',
    textAlign: 'center',
    letterSpacing: 0.2,
  },
  iconContainer: {
    marginBottom: 24,
  },
  uploadingIndicator: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#141414',
    justifyContent: 'center',
    alignItems: 'center',
  },
  uploadingIcon: {
    fontSize: 32,
  },
  statusCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  successCircle: {
    backgroundColor: '#14532D',
  },
  errorCircle: {
    backgroundColor: '#7F1D1D',
  },
  statusIcon: {
    color: '#F5F5F5',
    fontSize: 32,
    fontWeight: '600',
  },
  statusText: {
    color: '#F5F5F5',
    fontSize: 16,
    fontWeight: '500',
    textAlign: 'center',
    marginBottom: 24,
    letterSpacing: 0.3,
  },
  progressContainer: {
    width: '100%',
    alignItems: 'center',
    marginBottom: 16,
  },
  progressTrack: {
    width: '100%',
    height: 4,
    backgroundColor: '#1F1F1F',
    borderRadius: 2,
    overflow: 'hidden',
    marginBottom: 8,
  },
  progressFill: {
    height: '100%',
    backgroundColor: '#6366F1',
    borderRadius: 2,
  },
  progressText: {
    color: '#6B7280',
    fontSize: 12,
    letterSpacing: 0.5,
  },
  errorText: {
    color: '#EF4444',
    fontSize: 13,
    textAlign: 'center',
    paddingHorizontal: 16,
    lineHeight: 20,
    marginBottom: 32,
  },
  detailsContainer: {
    width: '100%',
    backgroundColor: '#141414',
    borderRadius: 12,
    padding: 16,
    marginBottom: 32,
  },
  detailLabel: {
    color: '#6B7280',
    fontSize: 11,
    letterSpacing: 1,
    textTransform: 'uppercase',
    marginBottom: 4,
  },
  detailValue: {
    color: '#F5F5F5',
    fontSize: 13,
    fontFamily: 'monospace',
    marginBottom: 16,
  },
  processingNote: {
    color: '#6B7280',
    fontSize: 13,
    lineHeight: 18,
  },
  primaryButton: {
    backgroundColor: '#6366F1',
    borderRadius: 14,
    paddingVertical: 14,
    paddingHorizontal: 32,
    alignItems: 'center',
    width: '100%',
  },
  primaryButtonText: {
    color: '#F5F5F5',
    fontSize: 15,
    fontWeight: '600',
    letterSpacing: 0.3,
  },
});
