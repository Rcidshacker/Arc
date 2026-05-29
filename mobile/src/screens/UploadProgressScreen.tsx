import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { StackScreenProps } from '@react-navigation/stack';
import type { RootStackParamList } from '../../App';
import { Colors } from '../theme/colors';
import { Typography } from '../theme/typography';
import { getAllRecordings, getRecordingBlob, type Recording } from '../services/recordingStore';
import { uploadAudio, type UploadProgress } from '../services/uploader';

type Props = StackScreenProps<RootStackParamList, 'UploadProgress'>;

type FileStatus = 'pending' | 'uploading' | 'done' | 'error';

interface FileState {
  rec: Recording;
  status: FileStatus;
  progress: number;
  loaded: number;
  total: number;
  eta: number | null;
  error: string | null;
  meetingId: string | null;
}

function formatDuration(sec: number): string {
  const total = Math.floor(sec);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function formatEta(sec: number): string {
  if (sec < 2) return '< 1s remaining';
  if (sec < 60) return `~${sec}s remaining`;
  return `~${Math.ceil(sec / 60)}m remaining`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

export function UploadProgressScreen({ route, navigation }: Props): React.JSX.Element {
  const { recordingIds, serverUrl } = route.params;
  const [files, setFiles] = useState<FileState[]>([]);
  const [doneCount, setDoneCount] = useState(0);
  const speedWindowRef = useRef<{ ts: number; bytes: number }[]>([]);

  useEffect(() => {
    async function init(): Promise<void> {
      try {
        const all = await getAllRecordings();
        const selected = recordingIds
          .map((id) => all.find((r) => r.id === id))
          .filter((r): r is Recording => r !== undefined);

        setFiles(selected.map((rec) => ({
          rec,
          status: 'pending',
          progress: 0,
          loaded: 0,
          total: rec.size,
          eta: null,
          error: null,
          meetingId: null,
        })));

        for (const rec of selected) {
          await uploadOne(rec);
        }
      } catch {
        // init error — individual files handle their own errors in uploadOne
      }
    }
    init();
  }, []);

  function computeEta(remaining: number): number | null {
    const window = speedWindowRef.current;
    const now = Date.now();
    const recent = window.filter((e) => now - e.ts < 3000);
    speedWindowRef.current = recent;
    if (recent.length < 2) return null;
    const totalBytes = recent.reduce((s, e) => s + e.bytes, 0);
    const elapsed = (now - recent[0].ts) / 1000;
    const bps = totalBytes / elapsed;
    if (bps <= 0) return null;
    return Math.round(remaining / bps);
  }

  async function uploadOne(rec: Recording): Promise<void> {
    setFiles((prev) => prev.map((f) =>
      f.rec.id === rec.id ? { ...f, status: 'uploading' } : f,
    ));

    try {
      const source = await getRecordingBlob(rec.id);
      let lastLoaded = 0;

      const onProgress = (p: UploadProgress) => {
        const delta = p.loaded - lastLoaded;
        lastLoaded = p.loaded;
        speedWindowRef.current.push({ ts: Date.now(), bytes: delta });

        const remaining = p.total - p.loaded;
        const eta = computeEta(remaining);

        setFiles((prev) => prev.map((f) =>
          f.rec.id === rec.id
            ? { ...f, progress: p.percent, loaded: p.loaded, total: p.total, eta }
            : f,
        ));
      };

      const uri = typeof source === 'string' ? source : URL.createObjectURL(source as Blob);
      const result = await uploadAudio(uri, serverUrl, onProgress);

      setFiles((prev) => prev.map((f) =>
        f.rec.id === rec.id
          ? { ...f, status: 'done', progress: 100, eta: null, meetingId: result.meetingId }
          : f,
      ));
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Upload failed.';
      setFiles((prev) => prev.map((f) =>
        f.rec.id === rec.id ? { ...f, status: 'error', eta: null, error: msg } : f,
      ));
    } finally {
      setDoneCount((n) => n + 1);
    }
  }

  async function handleRetry(rec: Recording): Promise<void> {
    setDoneCount((n) => n - 1);
    await uploadOne(rec);
  }

  const allDone = files.length > 0 && doneCount >= files.length;
  const uploadingIdx = files.findIndex((f) => f.status === 'uploading');
  const currentUploading = uploadingIdx + 1;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>
          {allDone
            ? 'All done'
            : files.length > 0
              ? `Sending ${currentUploading > 0 ? currentUploading : '…'} of ${files.length}`
              : 'Preparing…'}
        </Text>
      </View>

      <ScrollView contentContainerStyle={styles.list}>
        {files.map((f) => (
          <View key={f.rec.id} style={styles.fileCard}>
            <View style={styles.fileHeader}>
              <Text style={styles.fileLabel} numberOfLines={1}>
                {formatDuration(f.rec.duration)} · {new Date(f.rec.createdAt).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
              </Text>
              <View style={styles.statusIcon}>
                {f.status === 'pending' && <Ionicons name="time-outline" size={16} color={Colors.textMuted} />}
                {f.status === 'uploading' && <Ionicons name="cloud-upload-outline" size={16} color={Colors.accent} />}
                {f.status === 'done' && <Ionicons name="checkmark-circle" size={16} color={Colors.success} />}
                {f.status === 'error' && <Ionicons name="close-circle" size={16} color={Colors.error} />}
              </View>
            </View>

            <View style={styles.progressTrack}>
              <View
                style={[
                  styles.progressFill,
                  {
                    width: `${f.progress}%` as any,
                    backgroundColor: f.status === 'error' ? Colors.error : f.status === 'done' ? Colors.success : Colors.accent,
                  },
                ]}
              />
            </View>

            <View style={styles.statusLine}>
              {f.status === 'uploading' && (
                <>
                  <Text style={styles.statusText}>{f.progress}% · {formatBytes(f.loaded)}</Text>
                  {f.eta !== null && <Text style={styles.etaText}>{formatEta(f.eta)}</Text>}
                </>
              )}
              {f.status === 'done' && (
                <Text style={[styles.statusText, { color: Colors.success }]}>Uploaded</Text>
              )}
              {f.status === 'error' && (
                <View style={styles.errorRow}>
                  <Text style={[styles.statusText, { color: Colors.error, flex: 1 }]} numberOfLines={1}>{f.error}</Text>
                  <TouchableOpacity onPress={() => handleRetry(f.rec)}>
                    <Text style={styles.retryText}>Retry</Text>
                  </TouchableOpacity>
                </View>
              )}
            </View>
          </View>
        ))}
      </ScrollView>

      {allDone && (
        <TouchableOpacity
          style={styles.doneButton}
          onPress={() => navigation.navigate('MainTabs')}
          activeOpacity={0.85}
        >
          <Text style={styles.doneButtonText}>Done</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  header: {
    paddingTop: 60, paddingBottom: 20, paddingHorizontal: 24,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
  },
  headerTitle: {
    color: Colors.text, fontSize: Typography.size.xl,
    fontFamily: Typography.family.bold,
  },
  list: { padding: 16 },
  fileCard: {
    backgroundColor: Colors.bgElevated, borderRadius: 12,
    padding: 14, marginBottom: 10,
    borderWidth: 1, borderColor: Colors.border,
  },
  fileHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  fileLabel: { color: Colors.text, fontSize: Typography.size.sm, fontFamily: Typography.family.ui, flex: 1, marginRight: 8 },
  statusIcon: { width: 20, alignItems: 'center' },
  progressTrack: { height: 3, backgroundColor: Colors.border, borderRadius: 2, overflow: 'hidden', marginBottom: 8 },
  progressFill: { height: '100%', borderRadius: 2 },
  statusLine: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  statusText: { color: Colors.textMuted, fontSize: Typography.size.xs, fontFamily: Typography.family.mono },
  etaText: { color: Colors.textMuted, fontSize: Typography.size.xs, fontFamily: Typography.family.mono },
  errorRow: { flexDirection: 'row', alignItems: 'center', flex: 1 },
  retryText: { color: Colors.accent, fontSize: Typography.size.xs, fontFamily: Typography.family.bold, marginLeft: 8 },
  doneButton: {
    marginHorizontal: 16, marginBottom: 32, backgroundColor: Colors.accent,
    borderRadius: 14, paddingVertical: 16, alignItems: 'center',
  },
  doneButtonText: { color: Colors.text, fontSize: Typography.size.base, fontFamily: Typography.family.bold },
});
