import React, { useEffect, useState } from 'react';
import {
  Alert,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import type { StackScreenProps } from '@react-navigation/stack';
import type { RootStackParamList } from '../../App';
import { Colors } from '../theme/colors';
import { Typography } from '../theme/typography';
import { getUserName, setUserName, getDeviceId } from '../services/storage';

type Props = StackScreenProps<RootStackParamList, 'Profile'>;

export function ProfileScreen({ navigation }: Props): React.JSX.Element {
  const [name, setName] = useState('');
  const [deviceId, setDeviceId] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    async function load(): Promise<void> {
      const [n, d] = await Promise.all([getUserName(), getDeviceId()]);
      if (n) setName(n);
      setDeviceId(d);
    }
    void load();
  }, []);

  async function handleSave(): Promise<void> {
    const trimmed = name.trim();
    if (!trimmed) {
      Alert.alert('Name required', 'Please enter your name.');
      return;
    }
    await setUserName(trimmed);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color={Colors.textMuted} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Profile</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.body}>
        <Text style={styles.label}>Your name</Text>
        <TextInput
          style={styles.input}
          value={name}
          onChangeText={setName}
          placeholder="e.g. Ruchit"
          placeholderTextColor={Colors.textMuted}
          autoCapitalize="words"
          returnKeyType="done"
          onSubmitEditing={handleSave}
          testID="name-input"
        />
        <Text style={styles.hint}>Used to label your recordings on the laptop</Text>

        <TouchableOpacity
          style={styles.saveButton}
          onPress={handleSave}
          activeOpacity={0.85}
          testID="save-btn"
        >
          <Text style={styles.saveButtonText}>{saved ? 'Saved ✓' : 'Save'}</Text>
        </TouchableOpacity>

        {deviceId.length > 0 && (
          <Text style={styles.deviceId} testID="device-id">Device ID: {deviceId}</Text>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  backBtn: { width: 40, height: 40, justifyContent: 'center', alignItems: 'center' },
  headerTitle: {
    fontFamily: Typography.family.bold,
    fontSize: Typography.size.lg,
    color: Colors.text,
  },
  body: { paddingHorizontal: 24, paddingTop: 24 },
  label: {
    fontFamily: Typography.family.ui,
    fontSize: Typography.size.sm,
    color: Colors.textMuted,
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  input: {
    backgroundColor: Colors.bgElevated,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontFamily: Typography.family.ui,
    fontSize: Typography.size.base,
    color: Colors.text,
    marginBottom: 8,
  },
  hint: {
    fontFamily: Typography.family.ui,
    fontSize: Typography.size.xs,
    color: Colors.textMuted,
    marginBottom: 24,
  },
  saveButton: {
    backgroundColor: Colors.accent,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    marginBottom: 32,
  },
  saveButtonText: {
    fontFamily: Typography.family.bold,
    fontSize: Typography.size.base,
    color: Colors.text,
  },
  deviceId: {
    fontFamily: Typography.family.mono,
    fontSize: Typography.size.xs,
    color: Colors.textMuted,
  },
});
