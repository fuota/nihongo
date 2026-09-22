import { Stack } from 'expo-router';

export default function DrillLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="play" />
    </Stack>
  );
}
