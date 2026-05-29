// mobile/App.tsx
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import React from 'react';
import { Platform, StyleSheet, View } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';
import { useFonts, Syne_400Regular, Syne_700Bold } from '@expo-google-fonts/syne';
import { SpaceMono_400Regular } from '@expo-google-fonts/space-mono';

import { Colors } from './src/theme/colors';
import { SplashScreen } from './src/screens/SplashScreen';
import { RecorderScreen } from './src/screens/RecorderScreen';
import { LibraryScreen } from './src/screens/LibraryScreen';
import { SelectAndSendScreen } from './src/screens/SelectAndSendScreen';
import { QRScanScreen } from './src/screens/QRScanScreen';
import { UploadProgressScreen } from './src/screens/UploadProgressScreen';

export type RootStackParamList = {
  Splash: undefined;
  MainTabs: undefined;
  SelectAndSend: { recordingIds: string[] };
  QRScan: undefined;
  UploadProgress: { recordingIds: string[]; serverUrl: string };
};

export type MainTabParamList = {
  Recorder: undefined;
  Library: undefined;
};

const Stack = createStackNavigator<RootStackParamList>();
const Tab = createBottomTabNavigator<MainTabParamList>();

function MainTabs(): React.JSX.Element {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarStyle: {
          backgroundColor: Colors.bgElevated,
          borderTopWidth: 0,
          elevation: 8,
          shadowColor: '#000',
          shadowOpacity: 0.3,
          shadowOffset: { width: 0, height: -2 },
          shadowRadius: 8,
        },
        tabBarActiveTintColor: Colors.accent,
        tabBarInactiveTintColor: Colors.textMuted,
        tabBarLabelStyle: { fontFamily: 'Syne_400Regular', fontSize: 11 },
        tabBarIcon: ({ color, size }) => {
          const name = route.name === 'Recorder' ? 'mic' : 'library';
          return <Ionicons name={name as any} size={size} color={color} />;
        },
      })}
    >
      <Tab.Screen name="Recorder" component={RecorderScreen} />
      <Tab.Screen name="Library" component={LibraryScreen} />
    </Tab.Navigator>
  );
}

const ArcNavTheme = {
  dark: true,
  colors: {
    primary: Colors.accent,
    background: Colors.bg,
    card: Colors.bgElevated,
    text: Colors.text,
    border: Colors.border,
    notification: Colors.accent,
  },
  fonts: {
    regular: { fontFamily: 'Syne_400Regular', fontWeight: '400' as const },
    medium:  { fontFamily: 'Syne_400Regular', fontWeight: '500' as const },
    bold:    { fontFamily: 'Syne_700Bold',     fontWeight: '700' as const },
    heavy:   { fontFamily: 'Syne_700Bold',     fontWeight: '900' as const },
  },
};

export default function App(): React.JSX.Element {
  const [fontsLoaded] = useFonts({ Syne_400Regular, Syne_700Bold, SpaceMono_400Regular });

  if (!fontsLoaded) {
    return (
      <View style={styles.loading}>
        <StatusBar style="light" />
      </View>
    );
  }

  return (
    <GestureHandlerRootView style={Platform.OS === 'web' ? styles.webRoot : styles.nativeRoot}>
      <NavigationContainer theme={ArcNavTheme}>
        <StatusBar style="light" />
        <Stack.Navigator
          initialRouteName="Splash"
          screenOptions={{ headerShown: false, animationEnabled: true }}
        >
          <Stack.Screen name="Splash" component={SplashScreen} />
          <Stack.Screen name="MainTabs" component={MainTabs} />
          <Stack.Screen
            name="SelectAndSend"
            component={SelectAndSendScreen}
            options={{ presentation: 'modal' }}
          />
          <Stack.Screen
            name="QRScan"
            component={QRScanScreen}
            options={{ presentation: 'modal' }}
          />
          <Stack.Screen
            name="UploadProgress"
            component={UploadProgressScreen}
            options={{ presentation: 'modal' }}
          />
        </Stack.Navigator>
      </NavigationContainer>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, backgroundColor: Colors.bg },
  nativeRoot: { flex: 1 },
  webRoot: {
    // @ts-ignore
    height: '100vh',
    width: '100%',
    overflow: 'hidden',
    backgroundColor: Colors.bg,
  },
});
