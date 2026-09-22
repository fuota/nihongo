import { useAuth } from '@clerk/expo';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { apiFetch } from '@/lib/api';

/**
 * Bare /learn/for-you (no session id) is just an entry point: resolve
 * the user's current session (creating one if needed) and redirect
 * into it. The Learn home screen normally navigates straight to
 * /learn/for-you/[sessionId], but this covers any other entry (e.g. a
 * deep link) that doesn't already know the id.
 */
export default function ForYouEntry() {
  const { getToken } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      (async () => {
        try {
          const token = await getToken();
          let current = await apiFetch('/session/current', token);
          if (!current) {
            current = await apiFetch('/session/generate', token, { method: 'POST' });
          }
          if (!cancelled) router.replace(`/learn/for-you/${current.session_id}` as any);
        } catch (err: any) {
          if (!cancelled) setError(err?.message ?? "Couldn't start a session, try again.");
        }
      })();
      return () => {
        cancelled = true;
      };
    }, [])
  );

  return (
    <View style={styles.container}>
      {error ? <Text style={styles.error}>{error}</Text> : <ActivityIndicator />}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  error: {
    color: '#c0392b',
    textAlign: 'center',
  },
});
