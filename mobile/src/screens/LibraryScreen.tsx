import React from 'react';
import { View, Text } from 'react-native';
import { Colors } from '../theme/colors';
export function LibraryScreen(): React.JSX.Element {
  return <View style={{ flex: 1, backgroundColor: Colors.bg, justifyContent: 'center', alignItems: 'center' }}>
    <Text style={{ color: Colors.textMuted }}>Library — coming soon</Text>
  </View>;
}
