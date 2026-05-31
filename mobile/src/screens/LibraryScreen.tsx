import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  FlatList,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Swipeable } from 'react-native-gesture-handler';
import { Ionicons } from '@expo/vector-icons';
import { useIsFocused, useFocusEffect } from '@react-navigation/native';
import type { CompositeScreenProps } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { StackScreenProps } from '@react-navigation/stack';
import { useAudioPlayer } from 'expo-audio';
import * as DocumentPicker from 'expo-document-picker';

import { Colors } from '../theme/colors';
import { Typography } from '../theme/typography';
import { getAllRecordings, deleteRecording, importRecording } from '../services/recordingStore';
import type { Recording } from '../services/recordingStore';
import { getServerUrl } from '../services/storage';
import type { RootStackParamList, MainTabParamList } from '../../App';

// ---------------------------------------------------------------------------
// Navigation type
// ---------------------------------------------------------------------------

type Props = CompositeScreenProps<
  BottomTabScreenProps<MainTabParamList, 'Library'>,
  StackScreenProps<RootStackParamList>
>;

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) {
    return 'Today, ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });
  }
  return (
    d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }) +
    ', ' +
    d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false })
  );
}

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function formatSize(bytes: number): string {
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

async function probeWebAudioDurationMs(uri: string): Promise<number> {
  if (typeof window === 'undefined') return 0;
  return new Promise((resolve) => {
    const audio = new (window as any).Audio();
    const cleanup = () => { audio.src = ''; };
    audio.onloadedmetadata = () => { resolve((audio.duration || 0) * 1000); cleanup(); };
    audio.onerror = () => { resolve(0); cleanup(); };
    audio.src = uri;
    setTimeout(() => resolve(0), 3000);
  });
}

// ---------------------------------------------------------------------------
// RecordingCard
// ---------------------------------------------------------------------------

interface RecordingCardProps {
  recording: Recording;
  isPlaying: boolean;
  isActive: boolean;
  selectMode: boolean;
  selected: boolean;
  onPlayPause: () => void;
  onDelete: () => void;
  onLongPress: () => void;
  onSelect: () => void;
}

function RecordingCard({
  recording,
  isPlaying,
  isActive,
  selectMode,
  selected,
  onPlayPause,
  onDelete,
  onLongPress,
  onSelect,
}: RecordingCardProps): React.JSX.Element {
  const swipeableRef = useRef<Swipeable>(null);

  const renderRightActions = useCallback(
    () => (
      <TouchableOpacity
        style={styles.deleteAction}
        onPress={() => {
          swipeableRef.current?.close();
          onDelete();
        }}
        accessibilityLabel="Delete recording"
      >
        <Ionicons name="trash-outline" size={22} color={Colors.text} />
        <Text style={styles.deleteActionText}>Delete</Text>
      </TouchableOpacity>
    ),
    [onDelete],
  );

  const cardStyle = [
    styles.card,
    isActive && styles.cardActive,
    selected && styles.cardSelected,
  ];

  return (
    <Swipeable
      ref={swipeableRef}
      renderRightActions={renderRightActions}
      rightThreshold={60}
      friction={2}
      overshootRight={false}
    >
      <Pressable
        style={cardStyle}
        onLongPress={onLongPress}
        onPress={selectMode ? onSelect : undefined}
        accessibilityRole={selectMode ? 'checkbox' : 'button'}
        accessibilityState={selectMode ? { checked: selected } : undefined}
      >
        <TouchableOpacity
          style={styles.playButton}
          onPress={onPlayPause}
          accessibilityLabel={isActive && isPlaying ? 'Pause' : 'Play'}
          disabled={selectMode}
        >
          <Ionicons
            name={isActive && isPlaying ? 'pause' : 'play'}
            size={20}
            color={Colors.text}
          />
        </TouchableOpacity>

        <View style={styles.cardMeta}>
          <Text style={styles.cardDate}>{formatDate(recording.createdAt)}</Text>
          <Text style={styles.cardStats}>
            {formatDuration(recording.duration)}{'  ·  '}{formatSize(recording.size)}
          </Text>
        </View>

        {selectMode && (
          <View style={[styles.checkbox, selected && styles.checkboxSelected]}>
            {selected && <Ionicons name="checkmark" size={14} color={Colors.text} />}
          </View>
        )}
      </Pressable>
    </Swipeable>
  );
}

// ---------------------------------------------------------------------------
// LibraryScreen
// ---------------------------------------------------------------------------

export function LibraryScreen({ navigation }: Props): React.JSX.Element {
  const isFocused = useIsFocused();

  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [isConnected, setIsConnected] = useState(false);
  const [importToast, setImportToast] = useState('');
  const importToastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const player = useAudioPlayer(null);

  // ------------------------------------------------------------------
  // Connection status
  // ------------------------------------------------------------------

  useFocusEffect(useCallback(() => {
    getServerUrl().then((url) => setIsConnected(url !== null)).catch(() => setIsConnected(false));
  }, []));

  // ------------------------------------------------------------------
  // Load / reload
  // ------------------------------------------------------------------

  const load = useCallback(async () => {
    const all = await getAllRecordings();
    const sorted = [...all].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    setRecordings(sorted);
  }, []);

  useEffect(() => {
    if (isFocused) void load();
  }, [isFocused, load]);

  // ------------------------------------------------------------------
  // Import
  // ------------------------------------------------------------------

  const handleImport = useCallback(async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: 'audio/*',
        multiple: true,
        copyToCacheDirectory: true,
      });
      if (result.canceled) return;

      let count = 0;
      for (const asset of result.assets) {
        try {
          let durationMs = 0;
          if (Platform.OS === 'web') {
            durationMs = await probeWebAudioDurationMs(asset.uri);
          }
          await importRecording(asset.uri, durationMs);
          count++;
        } catch { /* skip failed */ }
      }

      if (count > 0) {
        await load();
        showImportToast(count);
      }
    } catch { /* cancelled or error */ }
  }, [load]);

  function showImportToast(count: number): void {
    if (importToastTimer.current !== null) clearTimeout(importToastTimer.current);
    setImportToast(`${count} file${count !== 1 ? 's' : ''} imported`);
    importToastTimer.current = setTimeout(() => setImportToast(''), 2500);
  }

  // ------------------------------------------------------------------
  // Playback
  // ------------------------------------------------------------------

  const handlePlayPause = useCallback(
    (recording: Recording) => {
      if (activeId === recording.id) {
        if (player.playing) player.pause();
        else player.play();
      } else {
        setActiveId(recording.id);
        player.replace({ uri: recording.uri });
        player.play();
      }
    },
    [activeId, player],
  );

  // ------------------------------------------------------------------
  // Delete
  // ------------------------------------------------------------------

  const handleDelete = useCallback(
    (recording: Recording) => {
      Alert.alert(
        'Delete recording',
        `Delete "${formatDate(recording.createdAt)}"? This cannot be undone.`,
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Delete',
            style: 'destructive',
            onPress: async () => {
              if (activeId === recording.id) {
                player.pause();
                setActiveId(null);
              }
              await deleteRecording(recording.id);
              setSelected((prev) => {
                const next = new Set(prev);
                next.delete(recording.id);
                return next;
              });
              await load();
            },
          },
        ],
      );
    },
    [activeId, load, player],
  );

  // ------------------------------------------------------------------
  // Select mode
  // ------------------------------------------------------------------

  const enterSelectMode = useCallback(() => setSelectMode(true), []);
  const exitSelectMode = useCallback(() => { setSelectMode(false); setSelected(new Set()); }, []);

  const handleDeleteSelected = useCallback(() => {
    const count = selected.size;
    Alert.alert(
      `Delete ${count} recording${count !== 1 ? 's' : ''}`,
      'This cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            for (const id of selected) {
              if (activeId === id) {
                player.pause();
                setActiveId(null);
              }
              await deleteRecording(id);
            }
            exitSelectMode();
            await load();
          },
        },
      ],
    );
  }, [activeId, exitSelectMode, load, player, selected]);
  const toggleSelected = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  const renderItem = useCallback(
    ({ item }: { item: Recording }) => (
      <RecordingCard
        recording={item}
        isPlaying={player.playing}
        isActive={activeId === item.id}
        selectMode={selectMode}
        selected={selected.has(item.id)}
        onPlayPause={() => handlePlayPause(item)}
        onDelete={() => handleDelete(item)}
        onLongPress={() => { if (!selectMode) { enterSelectMode(); toggleSelected(item.id); } }}
        onSelect={() => toggleSelected(item.id)}
      />
    ),
    [activeId, enterSelectMode, handleDelete, handlePlayPause, player.playing, selectMode, selected, toggleSelected],
  );

  const keyExtractor = useCallback((item: Recording) => item.id, []);

  const ListEmpty = (
    <View style={styles.emptyState}>
      <Ionicons name="mic-off-outline" size={48} color={Colors.border} />
      <Text style={styles.emptyText}>Nothing recorded yet.</Text>
    </View>
  );

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Text style={styles.headerTitle}>Recordings</Text>
          {recordings.length > 0 && (
            <View style={styles.countChip}>
              <Text style={styles.countChipText}>{recordings.length}</Text>
            </View>
          )}
          <TouchableOpacity
            style={styles.importBtn}
            onPress={handleImport}
            accessibilityLabel="Import audio files"
            testID="import-btn"
          >
            <Ionicons name="folder-open-outline" size={20} color={Colors.accent} />
          </TouchableOpacity>
        </View>

        <View style={styles.headerRight}>
          <TouchableOpacity
            style={styles.wifiBtn}
            onPress={() => navigation.navigate('QRScan', { mode: 'settings' })}
            accessibilityLabel={isConnected ? 'Connected — tap to change' : 'Not connected — tap to pair'}
            testID="wifi-btn"
          >
            <Ionicons
              name={isConnected ? 'wifi' : 'wifi-outline'}
              size={20}
              color={Colors.textMuted}
            />
            <View style={[styles.dot, { backgroundColor: isConnected ? Colors.success : Colors.textMuted }]} />
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.selectButton}
            onPress={selectMode ? exitSelectMode : enterSelectMode}
            accessibilityLabel={selectMode ? 'Cancel selection' : 'Select recordings'}
          >
            <Text style={styles.selectButtonText}>{selectMode ? 'Cancel' : 'Select'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* List */}
      <FlatList
        data={recordings}
        keyExtractor={keyExtractor}
        renderItem={renderItem}
        ListEmptyComponent={ListEmpty}
        contentContainerStyle={recordings.length === 0 ? styles.listEmptyContent : styles.listContent}
        showsVerticalScrollIndicator={false}
        ItemSeparatorComponent={() => <View style={styles.separator} />}
      />

      {/* Select mode CTA */}
      {selectMode && selected.size > 0 && (
        <View style={styles.ctaContainer}>
          <View style={styles.ctaRow}>
            <TouchableOpacity
              style={[styles.ctaButton, { flex: 1 }]}
              onPress={() => navigation.navigate('SelectAndSend', { recordingIds: Array.from(selected) })}
              accessibilityLabel={`Send ${selected.size} recording${selected.size !== 1 ? 's' : ''} to laptop`}
            >
              <Ionicons name="cloud-upload-outline" size={18} color={Colors.text} style={styles.ctaIcon} />
              <Text style={styles.ctaText}>
                {`Send ${selected.size} recording${selected.size !== 1 ? 's' : ''}`}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.ctaDeleteButton}
              onPress={handleDeleteSelected}
              accessibilityLabel={`Delete ${selected.size} selected recordings`}
            >
              <Text style={styles.ctaDeleteText}>Delete {selected.size}</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {/* Import toast */}
      {importToast.length > 0 && (
        <View style={styles.toast}>
          <Text style={styles.toastText}>{importToast}</Text>
        </View>
      )}
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const CARD_H_PADDING = 16;
const CARD_V_PADDING = 14;
const PLAY_BTN_SIZE = 44;

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.bg },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: CARD_H_PADDING,
    paddingTop: Platform.OS === 'android' ? 12 : 8,
    paddingBottom: 12,
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  headerTitle: {
    fontFamily: Typography.family.bold,
    fontSize: Typography.size.xl,
    color: Colors.text,
  },
  countChip: {
    backgroundColor: Colors.bgElevated,
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  countChipText: {
    fontFamily: Typography.family.mono,
    fontSize: Typography.size.xs,
    color: Colors.textMuted,
  },
  importBtn: {
    padding: 4,
  },
  wifiBtn: {
    padding: 4,
    position: 'relative',
  },
  dot: {
    position: 'absolute',
    top: 2,
    right: 2,
    width: 7,
    height: 7,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: Colors.bg,
  },
  selectButton: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: Colors.bgElevated,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  selectButtonText: {
    fontFamily: Typography.family.ui,
    fontSize: Typography.size.sm,
    color: Colors.accent,
  },

  listContent: { paddingHorizontal: CARD_H_PADDING, paddingBottom: 24 },
  listEmptyContent: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: CARD_H_PADDING },
  separator: { height: 8 },

  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.bgElevated,
    borderRadius: 12,
    paddingHorizontal: CARD_H_PADDING,
    paddingVertical: CARD_V_PADDING,
    borderWidth: 1,
    borderColor: Colors.border,
    gap: 12,
  },
  cardActive: { borderColor: Colors.accentDim },
  cardSelected: { borderColor: Colors.accent },
  playButton: {
    width: PLAY_BTN_SIZE,
    height: PLAY_BTN_SIZE,
    borderRadius: PLAY_BTN_SIZE / 2,
    backgroundColor: Colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  cardMeta: { flex: 1, gap: 4 },
  cardDate: { fontFamily: Typography.family.ui, fontSize: Typography.size.base, color: Colors.text },
  cardStats: { fontFamily: Typography.family.mono, fontSize: Typography.size.sm, color: Colors.textMuted },

  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: Colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  checkboxSelected: { backgroundColor: Colors.accent, borderColor: Colors.accent },

  deleteAction: {
    backgroundColor: Colors.error,
    borderRadius: 12,
    marginLeft: 8,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
    gap: 4,
  },
  deleteActionText: { fontFamily: Typography.family.ui, fontSize: Typography.size.xs, color: Colors.text },

  emptyState: { alignItems: 'center', gap: 12 },
  emptyText: { fontFamily: Typography.family.ui, fontSize: Typography.size.base, color: Colors.textMuted },

  ctaContainer: {
    paddingHorizontal: CARD_H_PADDING,
    paddingBottom: Platform.OS === 'android' ? 16 : 24,
    paddingTop: 12,
    backgroundColor: Colors.bg,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
  },
  ctaRow: {
    flexDirection: 'row',
    gap: 10,
  },
  ctaButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.accent,
    borderRadius: 12,
    paddingVertical: 14,
    gap: 8,
  },
  ctaIcon: { marginRight: 2 },
  ctaText: { fontFamily: Typography.family.bold, fontSize: Typography.size.base, color: Colors.text },
  ctaDeleteButton: {
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 20,
    borderWidth: 1,
    borderColor: Colors.error,
    justifyContent: 'center',
    alignItems: 'center',
  },
  ctaDeleteText: {
    fontFamily: Typography.family.bold,
    fontSize: Typography.size.base,
    color: Colors.error,
  },

  toast: {
    position: 'absolute',
    bottom: 100,
    alignSelf: 'center',
    backgroundColor: Colors.bgElevated,
    borderRadius: 20,
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  toastText: { color: Colors.text, fontSize: Typography.size.sm, fontFamily: Typography.family.ui },
});
