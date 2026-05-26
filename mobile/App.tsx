import React, { useEffect, useState } from 'react';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { StatusBar } from 'expo-status-bar';

import { getServerUrl } from '@/services/storage';
import { QRScannerScreen } from '@/screens/QRScannerScreen';
import { RecorderScreen } from '@/screens/RecorderScreen';
import { UploadStatusScreen } from '@/screens/UploadStatusScreen';

export type RootStackParamList = {
  QRScanner: undefined;
  Recorder: undefined;
  UploadStatus: {
    fileUri: string;
    serverUrl: string;
  };
};

const Stack = createStackNavigator<RootStackParamList>();

const ArcDarkTheme = {
  ...DefaultTheme,
  dark: true,
  colors: {
    ...DefaultTheme.colors,
    background: '#0A0A0A',
    card: '#141414',
    text: '#F5F5F5',
    border: '#1F1F1F',
    notification: '#6366F1',
    primary: '#6366F1',
  },
};

export default function App(): React.JSX.Element {
  const [initialRoute, setInitialRoute] = useState<
    'QRScanner' | 'Recorder' | null
  >(null);

  useEffect(() => {
    async function determineInitialRoute(): Promise<void> {
      const savedUrl = await getServerUrl();
      setInitialRoute(savedUrl !== null ? 'Recorder' : 'QRScanner');
    }
    determineInitialRoute();
  }, []);

  if (initialRoute === null) {
    return (
      <View style={styles.loadingContainer}>
        <StatusBar style="light" />
        <ActivityIndicator color="#6366F1" size="large" />
      </View>
    );
  }

  return (
    <NavigationContainer theme={ArcDarkTheme}>
      <StatusBar style="light" />
      <Stack.Navigator
        initialRouteName={initialRoute}
        screenOptions={{
          headerShown: false,
          cardStyle: { backgroundColor: '#0A0A0A' },
          animationEnabled: true,
        }}
      >
        <Stack.Screen name="QRScanner" component={QRScannerScreen} />
        <Stack.Screen name="Recorder" component={RecorderScreen} />
        <Stack.Screen name="UploadStatus" component={UploadStatusScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    backgroundColor: '#0A0A0A',
    justifyContent: 'center',
    alignItems: 'center',
  },
});
