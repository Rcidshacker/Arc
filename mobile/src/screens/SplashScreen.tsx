import React, { useEffect, useRef } from 'react';
import { Platform, StyleSheet, View } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  runOnJS,
  Easing,
} from 'react-native-reanimated';
import { useVideoPlayer, VideoView } from 'expo-video';
import type { StackScreenProps } from '@react-navigation/stack';
import type { RootStackParamList } from '../../App';
import { Colors } from '../theme/colors';

type Props = StackScreenProps<RootStackParamList, 'Splash'>;

const VIDEO_SOURCE = require('../../assets/splash.mp4');
const FALLBACK_TIMEOUT_MS = 3000;

function SplashWeb({ navigation }: Props): React.JSX.Element {
  const logoOpacity = useSharedValue(0);
  const logoScale = useSharedValue(0.92);
  const screenOpacity = useSharedValue(1);

  const logoStyle = useAnimatedStyle(() => ({
    opacity: logoOpacity.value,
    transform: [{ scale: logoScale.value }],
  }));

  const screenStyle = useAnimatedStyle(() => ({
    opacity: screenOpacity.value,
  }));

  useEffect(() => {
    logoOpacity.value = withTiming(1, { duration: 800, easing: Easing.out(Easing.ease) });
    logoScale.value = withTiming(1, { duration: 800, easing: Easing.out(Easing.ease) });

    const advance = () => { navigation.replace('MainTabs'); };

    const timer = setTimeout(() => {
      screenOpacity.value = withTiming(0, { duration: 350 }, () => {
        runOnJS(advance)();
      });
    }, 2500);

    return () => clearTimeout(timer);
  }, []);

  return (
    <Animated.View style={[styles.container, screenStyle]}>
      <Animated.Image
        source={require('../../assets/icon.png')}
        style={[styles.logo, logoStyle]}
        resizeMode="contain"
      />
    </Animated.View>
  );
}

function SplashNative({ navigation }: Props): React.JSX.Element {
  const didAdvance = useRef(false);

  const advance = () => {
    if (didAdvance.current) return;
    didAdvance.current = true;
    navigation.replace('MainTabs');
  };

  const player = useVideoPlayer(VIDEO_SOURCE, (p) => {
    p.loop = false;
    p.muted = true;
    p.play();
  });

  useEffect(() => {
    const fallback = setTimeout(advance, FALLBACK_TIMEOUT_MS);

    const sub = player.addListener('playingChange', (event) => {
      if (!event.isPlaying && didAdvance.current === false) {
        if (player.currentTime > 0) {
          clearTimeout(fallback);
          advance();
        }
      }
    });

    return () => {
      clearTimeout(fallback);
      sub.remove();
    };
  }, [player]);

  return (
    <View style={styles.container}>
      <VideoView
        player={player}
        style={styles.video}
        nativeControls={false}
        allowsFullscreen={false}
      />
    </View>
  );
}

export function SplashScreen(props: Props): React.JSX.Element {
  if (Platform.OS === 'web') {
    return <SplashWeb {...props} />;
  }
  return <SplashNative {...props} />;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.bg,
    justifyContent: 'center',
    alignItems: 'center',
  },
  logo: {
    width: 160,
    height: 160,
  },
  video: {
    position: 'absolute',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
  },
});
