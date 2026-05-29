import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  FlatList,
  Platform,
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Swipeable } from 'react-native-gesture-handler';
import { Ionicons } from '@expo/vector-icons';
import { useIsFocused } from '@react-navigation/native';
import type { CompositeScreenProps } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { StackScreenProps } from '@react-navigation/stack';
import { useAudioPlayer } from 'expo-audio';

import { Colors } from '../theme/colors';
import { Typography } from '../theme/typography';
import { getAllRecordings, deleteRecording } from '../services/recordingStore';
import type { Recording } from '../services/recordingStore';
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
        {/* Play / pause button */}
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

        {/* Meta */}
        <View style={styles.cardMeta}>
          <Text style={styles.cardDate}>{formatDate(recording.createdAt)}</Text>
          <Text style={styles.cardStats}>
            {formatDuration(recording.duration)}{'  ·  '}{formatSize(recording.size)}
          </Text>
        </View>

        {/* Select checkbox */}
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

  const player = useAudioPlayer(null);

  // ------------------------------------------------------------------
  // Load / reload
  // ------------------------------------------------------------------

  const load = useCallback(async () => {
    const all = await getAllRecordings();
    // newest first — store already returns sorted but ensure it here
    const sorted = [...all].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    setRecordings(sorted);
  }, []);

  useEffect(() => {
    if (isFocused) {
      void load();
    }
  }, [isFocused, load]);

  // ------------------------------------------------------------------
  // Playback
  // ------------------------------------------------------------------

  const handlePlayPause = useCallback(
    (recording: Recording) => {
      if (activeId === recording.id) {
        // Toggle current track
        if (player.playing) {
          player.pause();
        } else {
          player.play();
        }
      } else {
        // Switch to new track
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

  const enterSelectMode = useCallback(() => {
    setSelectMode(true);
  }, []);

  const exitSelectMode = useCallback(() => {
    setSelectMode(false);
    setSelected(new Set());
  }, []);

  const toggleSelected = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
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
        onLongPress={() => {
          if (!selectMode) {
            enterSelectMode();
            toggleSelected(item.id);
          }
        }}
        onSelect={() => toggleSelected(item.id)}
      />
    ),
    [
      activeId,
      enterSelectMode,
      handleDelete,
      handlePlayPause,
      player.playing,
      selectMode,
      selected,
      toggleSelected,
    ],
  );

  const keyExtractor = useCallback((item: Recording) => item.id, []);

  const ListEmpty = (
    <View style={styles.emptyState}>
      <Ionicons name="mic-off-outline" size={48} color={Colors.border} />
      <Text style={styles.emptyText}>Nothing recorded yet.</Text>
    </View>
  );

  return (
    <SafeAreaView style={styles.root}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Text style={styles.headerTitle}>Recordings</Text>
          {recordings.length > 0 && (
            <View style={styles.countChip}>
              <Text style={styles.countChipText}>{recordings.length}</Text>
            </View>
          )}
        </View>

        <TouchableOpacity
          style={styles.selectButton}
          onPress={selectMode ? exitSelectMode : enterSelectMode}
          accessibilityLabel={selectMode ? 'Cancel selection' : 'Select recordings'}
        >
          <Text style={styles.selectButtonText}>{selectMode ? 'Cancel' : 'Select'}</Text>
        </TouchableOpacity>
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

      {/* Fixed CTA in select mode */}
      {selectMode && selected.size > 0 && (
        <View style={styles.ctaContainer}>
          <TouchableOpacity
            style={styles.ctaButton}
            onPress={() => {
              navigation.navigate('SelectAndSend', {
                recordingIds: Array.from(selected),
              });
            }}
            accessibilityLabel={`Send ${selected.size} recording${selected.size !== 1 ? 's' : ''} to laptop`}
          >
            <Ionicons name="cloud-upload-outline" size={18} color={Colors.text} style={styles.ctaIcon} />
            <Text style={styles.ctaText}>
              {`Send ${selected.size} recording${selected.size !== 1 ? 's' : ''} to laptop`}
            </Text>
          </TouchableOpacity>
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
  root: {
    flex: 1,
    backgroundColor: Colors.bg,
  },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: CARD_H_PADDING,
    paddingTop: Platform.OS === 'android' ? 20 : 12,
    paddingBottom: 12,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
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

  // List
  listContent: {
    paddingHorizontal: CARD_H_PADDING,
    paddingBottom: 24,
  },
  listEmptyContent: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: CARD_H_PADDING,
  },
  separator: {
    height: 8,
  },

  // Card
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
  cardActive: {
    borderColor: Colors.accentDim,
  },
  cardSelected: {
    borderColor: Colors.accent,
  },
  playButton: {
    width: PLAY_BTN_SIZE,
    height: PLAY_BTN_SIZE,
    borderRadius: PLAY_BTN_SIZE / 2,
    backgroundColor: Colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  cardMeta: {
    flex: 1,
    gap: 4,
  },
  cardDate: {
    fontFamily: Typography.family.ui,
    fontSize: Typography.size.base,
    color: Colors.text,
  },
  cardStats: {
    fontFamily: Typography.family.mono,
    fontSize: Typography.size.sm,
    color: Colors.textMuted,
  },

  // Checkbox (select mode)
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
  checkboxSelected: {
    backgroundColor: Colors.accent,
    borderColor: Colors.accent,
  },

  // Swipe delete
  deleteAction: {
    backgroundColor: Colors.error,
    borderRadius: 12,
    marginLeft: 8,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
    gap: 4,
  },
  deleteActionText: {
    fontFamily: Typography.family.ui,
    fontSize: Typography.size.xs,
    color: Colors.text,
  },

  // Empty state
  emptyState: {
    alignItems: 'center',
    gap: 12,
  },
  emptyText: {
    fontFamily: Typography.family.ui,
    fontSize: Typography.size.base,
    color: Colors.textMuted,
  },

  // CTA
  ctaContainer: {
    paddingHorizontal: CARD_H_PADDING,
    paddingBottom: Platform.OS === 'android' ? 16 : 24,
    paddingTop: 12,
    backgroundColor: Colors.bg,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
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
  ctaIcon: {
    marginRight: 2,
  },
  ctaText: {
    fontFamily: Typography.family.bold,
    fontSize: Typography.size.base,
    color: Colors.text,
  },
});
