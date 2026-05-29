// mobile/src/screens/SelectAndSendScreen.tsx
import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { StackScreenProps } from '@react-navigation/stack';
import type { RootStackParamList } from '../../App';
import { Colors } from '../theme/colors';
import { Typography } from '../theme/typography';
import { getAllRecordings, type Recording } from '../services/recordingStore';
import { getServerUrl } from '../services/storage';

type Props = StackScreenProps<RootStackParamList, 'SelectAndSend'>;

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
    + ' · ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function formatDuration(sec: number): string {
  const total = Math.floor(sec);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function SelectAndSendScreen({ route, navigation }: Props): React.JSX.Element {
  const { recordingIds } = route.params;
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [serverUrl, setServerUrlState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load(): Promise<void> {
      try {
        const [all, url] = await Promise.all([getAllRecordings(), getServerUrl()]);
        const selected = all.filter((r) => recordingIds.includes(r.id));
        setRecordings(selected);
        setServerUrlState(url);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [recordingIds]);

  function handlePair(): void {
    navigation.navigate('QRScan');
  }

  function handleSend(): void {
    if (serverUrl === null) return;
    navigation.navigate('UploadProgress', { recordingIds, serverUrl });
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={Colors.accent} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.closeBtn}>
          <Ionicons name="close" size={24} color={Colors.textMuted} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Send to Laptop</Text>
        <View style={{ width: 40 }} />
      </View>

      {/* Recordings list (read-only) */}
      <FlatList
        data={recordings}
        keyExtractor={(r) => r.id}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => (
          <View style={styles.card}>
            <Ionicons name="mic" size={18} color={Colors.textMuted} style={{ marginTop: 2 }} />
            <View style={{ flex: 1 }}>
              <Text style={styles.cardDate}>{formatDate(item.createdAt)}</Text>
              <Text style={styles.cardMeta}>{formatDuration(item.duration)}</Text>
            </View>
          </View>
        )}
      />

      {/* Server URL row */}
      <View style={styles.serverRow}>
        <View style={styles.serverInfo}>
          <Text style={styles.serverLabel}>Laptop</Text>
          <Text style={styles.serverUrl} numberOfLines={1}>
            {serverUrl ?? 'Not connected'}
          </Text>
        </View>
        <TouchableOpacity style={styles.pairBtn} onPress={handlePair}>
          <Text style={styles.pairBtnText}>{serverUrl !== null ? 'Change' : 'Pair →'}</Text>
        </TouchableOpacity>
      </View>

      {/* Send button */}
      <TouchableOpacity
        style={[styles.sendButton, serverUrl === null && styles.sendButtonDisabled]}
        onPress={handleSend}
        disabled={serverUrl === null}
        activeOpacity={0.85}
      >
        <Text style={styles.sendButtonText}>
          Send {recordingIds.length} recording{recordingIds.length > 1 ? 's' : ''}
        </Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  center: { flex: 1, backgroundColor: Colors.bg, justifyContent: 'center', alignItems: 'center' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingTop: 56, paddingBottom: 16, paddingHorizontal: 20,
  },
  closeBtn: { width: 40, height: 40, justifyContent: 'center', alignItems: 'flex-start' },
  headerTitle: { color: Colors.text, fontSize: Typography.size.lg, fontFamily: Typography.family.bold },
  list: { paddingHorizontal: 16, paddingTop: 8 },
  card: {
    flexDirection: 'row', gap: 12, alignItems: 'flex-start',
    backgroundColor: Colors.bgElevated, borderRadius: 10, padding: 14,
    marginBottom: 8, borderWidth: 1, borderColor: Colors.border,
  },
  cardDate: { color: Colors.text, fontSize: Typography.size.sm, fontFamily: Typography.family.ui },
  cardMeta: { color: Colors.textMuted, fontSize: Typography.size.xs, fontFamily: Typography.family.mono, marginTop: 2 },
  serverRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    marginHorizontal: 16, padding: 14,
    backgroundColor: Colors.bgElevated, borderRadius: 12,
    borderWidth: 1, borderColor: Colors.border, marginBottom: 12,
  },
  serverInfo: { flex: 1, marginRight: 12 },
  serverLabel: { color: Colors.textMuted, fontSize: Typography.size.xs, fontFamily: Typography.family.ui, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 2 },
  serverUrl: { color: Colors.text, fontSize: Typography.size.sm, fontFamily: Typography.family.mono },
  pairBtn: { backgroundColor: Colors.accentDim, borderRadius: 8, paddingVertical: 6, paddingHorizontal: 12 },
  pairBtnText: { color: Colors.accent, fontSize: Typography.size.sm, fontFamily: Typography.family.bold },
  sendButton: {
    marginHorizontal: 16, marginBottom: 32, backgroundColor: Colors.accent,
    borderRadius: 14, paddingVertical: 16, alignItems: 'center',
  },
  sendButtonDisabled: { opacity: 0.4 },
  sendButtonText: { color: Colors.text, fontSize: Typography.size.base, fontFamily: Typography.family.bold },
});
