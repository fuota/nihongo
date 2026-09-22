import MaterialCommunityIcons from '@expo/vector-icons/MaterialCommunityIcons';
import { StyleSheet, View } from 'react-native';

export const AVATAR_CHOICES = ['cat', 'dog', 'panda', 'rabbit', 'koala'] as const;
export type AvatarKey = (typeof AVATAR_CHOICES)[number];

type Props = {
  avatar: string;
  size?: number;
  backgroundColor?: string;
  iconColor?: string;
  borderColor?: string;
};

/**
 * A circular avatar built from a MaterialCommunityIcons animal glyph,
 * not a photo or platform emoji -- deliberately not the iOS native
 * Memoji/animal icon look.
 */
export function AnimalAvatar({
  avatar,
  size = 96,
  backgroundColor = '#7c6ef0',
  iconColor = '#fff',
  borderColor,
}: Props) {
  const iconName = (AVATAR_CHOICES as readonly string[]).includes(avatar) ? (avatar as AvatarKey) : 'cat';

  return (
    <View
      style={[
        styles.circle,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor,
          ...(borderColor ? { borderWidth: Math.max(2, size * 0.03), borderColor } : null),
        },
      ]}>
      <MaterialCommunityIcons name={iconName} size={size * 0.58} color={iconColor} />
    </View>
  );
}

const styles = StyleSheet.create({
  circle: {
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 2,
  },
});
