import { useAuth } from '@clerk/expo';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { apiFetch } from '@/lib/api';
import type { VocabWord } from '@/lib/types';

function pickRandom<T>(items: T[]): T | null {
  if (items.length === 0) return null;
  return items[Math.floor(Math.random() * items.length)];
}

export default function WritingEntryScreen() {
  const { getToken } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      (async () => {
        setError(null);
        try {
          const token = await getToken();
          const [learntData, drillData] = await Promise.all([
            apiFetch('/vocab?learnt=true&limit=200', token),
            apiFetch('/vocab?in_drill=true&limit=200', token),
          ]);
          const byId = new Map<string, VocabWord>();
          for (const word of [...learntData.results, ...drillData.results] as VocabWord[]) {
            if (word.kanji) byId.set(word.id, word);
          }
          const candidate = pickRandom(Array.from(byId.values()));
          if (cancelled) return;
          if (!candidate) {
            setError('No kanji words in My Words or Drill yet -- learn or drill some words first.');
            return;
          }
          router.replace({
            pathname: '/learn/writing/practice/[id]',
            params: { id: candidate.id, data: JSON.stringify(candidate) },
          });
        } catch {
          if (!cancelled) setError("Couldn't load words to practice -- try again.");
        }
      })();
      return () => {
        cancelled = true;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])
  );

  return (
    <View style={styles.container}>
      {error ? <Text style={styles.error}>{error}</Text> : <ActivityIndicator size="large" />}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  error: {
    color: '#666',
    textAlign: 'center',
    fontSize: 15,
  },
});
