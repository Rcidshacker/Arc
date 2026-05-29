import React from 'react';
import { View } from 'react-native';
import type { StackScreenProps } from '@react-navigation/stack';
import type { RootStackParamList } from '../../App';
import { Colors } from '../theme/colors';
type Props = StackScreenProps<RootStackParamList, 'Splash'>;
export function SplashScreen({ navigation }: Props): React.JSX.Element {
  React.useEffect(() => { navigation.replace('MainTabs'); }, []);
  return <View style={{ flex: 1, backgroundColor: Colors.bg }} />;
}
