// mobile/src/services/recordingStore.ts
import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

export interface Recording {
  id: string;
  filename: string;
  duration: number;   // seconds
  size: number;       // bytes
  createdAt: string;  // ISO
  uri: string;        // blob: URL (web, session-only) | file:// (native)
}

// ---------------------------------------------------------------------------
// Web: in-memory session store — intentionally ephemeral.
// Blob URLs are revoked on page unload. IndexedDB not implemented.
// Adequate for Playwright smoke tests. Native is the real persistence layer.
// ---------------------------------------------------------------------------
const webStore = new Map<string, { meta: Recording; blob: Blob }>();

function makeId(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function makeFilename(ext: string): string {
  const now = new Date();
  const stamp = now.toISOString().slice(0, 19).replace(/[T:]/g, '-');
  return `arc-${stamp}.${ext}`;
}

// ---------------------------------------------------------------------------
// Web implementation
// ---------------------------------------------------------------------------

async function saveRecordingWeb(blob: Blob, durationMs: number): Promise<Recording> {
  const id = makeId();
  const filename = makeFilename('webm');
  const uri = URL.createObjectURL(blob);
  const meta: Recording = {
    id,
    filename,
    duration: Math.round(durationMs / 1000),
    size: blob.size,
    createdAt: new Date().toISOString(),
    uri,
  };
  webStore.set(id, { meta, blob });
  return meta;
}

function getAllRecordingsWeb(): Recording[] {
  return Array.from(webStore.values())
    .map((e) => e.meta)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

function getRecordingBlobWeb(id: string): Blob {
  const entry = webStore.get(id);
  if (!entry) throw new Error(`Recording ${id} not found in session store.`);
  return entry.blob;
}

function deleteRecordingWeb(id: string): void {
  const entry = webStore.get(id);
  if (entry) {
    URL.revokeObjectURL(entry.meta.uri);
    webStore.delete(id);
  }
}

// ---------------------------------------------------------------------------
// Native implementation
// ---------------------------------------------------------------------------

const RECORDINGS_KEY = 'arc_recordings';
// Use the legacy API which exposes documentDirectory + getInfoAsync/copyAsync/deleteAsync
let FileSystem: typeof import('expo-file-system/legacy') | null = null;
if (Platform.OS !== 'web') {
  FileSystem = require('expo-file-system/legacy');
}

async function getRecordingsDir(): Promise<string> {
  const dir = `${FileSystem!.documentDirectory}recordings/`;
  const info = await FileSystem!.getInfoAsync(dir);
  if (!info.exists) {
    await FileSystem!.makeDirectoryAsync(dir, { intermediates: true });
  }
  return dir;
}

async function loadMetadata(): Promise<Recording[]> {
  try {
    const raw = await AsyncStorage.getItem(RECORDINGS_KEY);
    return raw !== null ? (JSON.parse(raw) as Recording[]) : [];
  } catch {
    return [];
  }
}

async function saveMetadata(recordings: Recording[]): Promise<void> {
  await AsyncStorage.setItem(RECORDINGS_KEY, JSON.stringify(recordings));
}

async function saveRecordingNative(uri: string, durationMs: number): Promise<Recording> {
  const id = makeId();
  const ext = uri.endsWith('.m4a') ? 'm4a' : 'webm';
  const filename = makeFilename(ext);
  const dir = await getRecordingsDir();
  const destUri = `${dir}${filename}`;

  await FileSystem!.copyAsync({ from: uri, to: destUri });

  const info = await FileSystem!.getInfoAsync(destUri);
  const size = info.exists ? (info as { size?: number }).size ?? 0 : 0;

  const meta: Recording = {
    id,
    filename,
    duration: Math.round(durationMs / 1000),
    size,
    createdAt: new Date().toISOString(),
    uri: destUri,
  };

  const all = await loadMetadata();
  await saveMetadata([meta, ...all]);
  return meta;
}

async function getAllRecordingsNative(): Promise<Recording[]> {
  return loadMetadata();
}

function getRecordingBlobNative(id: string): Promise<string> {
  return loadMetadata().then((all) => {
    const rec = all.find((r) => r.id === id);
    if (!rec) throw new Error(`Recording ${id} not found.`);
    return rec.uri;
  });
}

async function deleteRecordingNative(id: string): Promise<void> {
  const all = await loadMetadata();
  const rec = all.find((r) => r.id === id);
  if (rec) {
    try { await FileSystem!.deleteAsync(rec.uri, { idempotent: true }); } catch { /* no-op */ }
  }
  await saveMetadata(all.filter((r) => r.id !== id));
}

// ---------------------------------------------------------------------------
// Public API — platform-transparent
// ---------------------------------------------------------------------------

export async function saveRecording(
  source: Blob | string,
  durationMs: number,
): Promise<Recording> {
  if (Platform.OS === 'web') {
    return saveRecordingWeb(source as Blob, durationMs);
  }
  return saveRecordingNative(source as string, durationMs);
}

export async function getAllRecordings(): Promise<Recording[]> {
  if (Platform.OS === 'web') {
    return getAllRecordingsWeb();
  }
  return getAllRecordingsNative();
}

export async function getRecordingBlob(id: string): Promise<Blob | string> {
  if (Platform.OS === 'web') {
    return getRecordingBlobWeb(id);
  }
  return getRecordingBlobNative(id);
}

export async function deleteRecording(id: string): Promise<void> {
  if (Platform.OS === 'web') {
    deleteRecordingWeb(id);
    return;
  }
  return deleteRecordingNative(id);
}
