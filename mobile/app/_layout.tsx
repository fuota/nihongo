import {
  Poppins_400Regular,
  Poppins_500Medium,
  Poppins_600SemiBold,
  Poppins_700Bold,
  useFonts,
} from '@expo-google-fonts/poppins';
import { DarkTheme, DefaultTheme, ThemeProvider } from '@react-navigation/native';
import { ClerkProvider, ClerkLoaded, useAuth } from '@clerk/expo';
import { tokenCache } from '@clerk/expo/token-cache';
import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import 'react-native-reanimated';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { apiFetch } from '@/lib/api';

export const unstable_settings = {
  anchor: '(tabs)',
};

// Applies Poppins as the default font for every <Text> in the app
// without needing to touch every existing StyleSheet. Explicit
// fontFamily set locally still wins -- see the Poppins_600SemiBold /
// Poppins_700Bold usages that replace fontWeight, since custom fonts
// (unlike system fonts) don't synthesize bold/semibold from a single
// regular-weight file.
// @ts-expect-error -- defaultProps isn't in RN's Text types, but is honored at runtime
Text.defaultProps = Text.defaultProps || {};
// @ts-expect-error -- see above
Text.defaultProps.style = [{ fontFamily: 'Poppins_400Regular' }, Text.defaultProps.style];

const publishableKey = process.env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY!;

if (!publishableKey) {
  throw new Error('Add EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY to your .env file');
}

function AuthGate() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const segments = useSegments();
  // useSegments() returns a new array each render, so it must NOT be an
  // effect dependency below -- that caused the effect (and its /me
  // fetch) to refire on every render in a tight loop. Read the current
  // path via this ref instead, which needs no dependency at all.
  const segmentsRef = useRef(segments);
  segmentsRef.current = segments;

  const router = useRouter();
  // Whether we've already resolved onboarding status for the current
  // sign-in -- runs the /me check at most once per sign-in, not once
  // per navigation, and avoids bouncing back to onboarding after it
  // completes (that PATCH doesn't update this gate's state, so the
  // decision here is made once, not re-derived from stale data).
  const checkedRef = useRef(false);

  useEffect(() => {
    if (!isLoaded) return;

    if (!isSignedIn) {
      checkedRef.current = false;
      if (segmentsRef.current[0] !== '(auth)') router.replace('/(auth)/sign-in');
      return;
    }

    if (checkedRef.current) return;
    // Set before the async call (not after) so a second effect firing
    // before this one resolves can't also start a second /me fetch.
    checkedRef.current = true;

    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        const data = await apiFetch('/me', token);
        if (cancelled) return;
        const inAuthGroup = segmentsRef.current[0] === '(auth)';
        const onOnboarding = segmentsRef.current[0] === 'onboarding';
        if (!data.name) {
          router.replace('/onboarding');
        } else if (inAuthGroup || onOnboarding) {
          router.replace('/');
        }
      } catch {
        // fail open -- don't trap the user behind a broken onboarding check
        if (!cancelled && segmentsRef.current[0] === '(auth)') router.replace('/');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn]);

  if (!isLoaded) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return (
    <Stack>
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="(auth)/sign-in" options={{ headerShown: false }} />
      <Stack.Screen name="onboarding" options={{ headerShown: false, gestureEnabled: false }} />
      <Stack.Screen name="modal" options={{ presentation: 'modal', title: 'Modal' }} />
    </Stack>
  );
}

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const [fontsLoaded] = useFonts({
    Poppins_400Regular,
    Poppins_500Medium,
    Poppins_600SemiBold,
    Poppins_700Bold,
  });

  if (!fontsLoaded) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <ClerkProvider publishableKey={publishableKey} tokenCache={tokenCache}>
        <ClerkLoaded>
          <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
            <AuthGate />
            <StatusBar style="auto" />
          </ThemeProvider>
        </ClerkLoaded>
      </ClerkProvider>
    </GestureHandlerRootView>
  );
}