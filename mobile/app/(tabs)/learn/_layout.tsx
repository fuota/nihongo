import { router, Stack } from 'expo-router';
import { Pressable, StyleSheet } from 'react-native';

import { IconSymbol } from '@/components/ui/icon-symbol';

function BackButton() {
  return (
    <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backButton}>
      <IconSymbol name="chevron.left" size={26} color="#000" />
    </Pressable>
  );
}

export default function LearnLayout() {
  return (
    <Stack screenOptions={{ headerLeft: () => <BackButton /> }}>
      <Stack.Screen name="index" options={{ headerShown: false }} />
      <Stack.Screen name="vocab/index" options={{ title: 'Vocab' }} />
      <Stack.Screen name="vocab/[level]/index" options={{ title: '' }} />
      <Stack.Screen name="vocab/[level]/[topic]" options={{ title: '' }} />
      <Stack.Screen name="grammar/index" options={{ title: 'Grammar' }} />
      <Stack.Screen name="grammar/[level]" options={{ title: '' }} />
      <Stack.Screen name="grammar/pattern/[id]" options={{ title: 'Grammar' }} />
      <Stack.Screen name="word/[id]" options={{ title: 'Word' }} />
      <Stack.Screen name="kanji/[id]" options={{ title: 'Kanji' }} />
      <Stack.Screen name="writing/index" options={{ headerShown: false }} />
      <Stack.Screen name="writing/practice/[id]" options={{ headerShown: false }} />
      <Stack.Screen name="for-you/index" options={{ headerShown: false }} />
      <Stack.Screen name="for-you/[sessionId]" options={{ headerShown: false }} />
      <Stack.Screen name="reading/index" options={{ headerShown: false }} />
      <Stack.Screen name="reading/[sessionId]" options={{ headerShown: false }} />
    </Stack>
  );
}

const styles = StyleSheet.create({
  backButton: {
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
});
