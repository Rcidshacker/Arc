import React, { useEffect } from 'react';
import { StyleSheet } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  runOnJS,
  Easing,
} from 'react-native-reanimated';
import type { StackScreenProps } from '@react-navigation/stack';
import type { RootStackParamList } from '../../App';
import { Colors } from '../theme/colors';

type Props = StackScreenProps<RootStackParamList, 'Splash'>;

export function SplashScreen({ navigation }: Props): React.JSX.Element {
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
});
