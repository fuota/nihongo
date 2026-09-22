import { useAuth } from '@clerk/expo';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from 'react-native';

import { DrillToggle } from '@/components/DrillToggle';
import { LearntToggle } from '@/components/LearntToggle';
import { apiFetch } from '@/lib/api';
import type { VocabWord } from '@/lib/types';

function formatTopic(topic: string): string {
  return topic
    .split('_')
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(' ');
}

export default function WordListScreen() {
  const { level, topic } = useLocalSearchParams<{ level: string; topic: string }>();
  const { getToken } = useAuth();

  const [words, setWords] = useState<VocabWord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const data = await apiFetch(`/vocab?level=${level}&topic=${topic}`, token);
      setWords(data.results);
    } catch (err: any) {
      setError(err?.message ?? 'Request failed');
    } finally {
      setLoading(false);
    }
    // getToken excluded on purpose -- see the Vocab topic screen for why.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level, topic]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const openWord = (word: VocabWord) => {
    router.push({
      pathname: '/learn/word/[id]',
      params: { id: word.id, data: JSON.stringify(word) },
    });
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{formatTopic(topic)}</Text>
      <Text style={styles.subtitle}>{level}</Text>

      {loading && <ActivityIndicator style={{ marginTop: 24 }} />}
      {error && <Text style={styles.error}>{error}</Text>}

      {!loading && (
        <FlatList
          style={styles.listContainer}
          data={words}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.list}
          renderItem={({ item }) => (
            <Pressable style={styles.row} onPress={() => openWord(item)}>
              <View style={{ flex: 1 }}>
                {item.kanji && <Text style={styles.rowFurigana}>{item.reading}</Text>}
                <Text style={styles.rowTitle}>{item.kanji ?? item.reading}</Text>
                <Text style={styles.rowSubtitle}>{item.meaning}</Text>
              </View>
              <View style={styles.rowActions}>
                <LearntToggle contentType="vocab" contentId={item.id} initialIsLearnt={item.is_learnt} />
                <DrillToggle contentType="vocab" contentId={item.id} initialInDrill={item.in_drill} />
              </View>
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 24,
    paddingTop: 24,
  },
  title: {
    fontSize: 24,
    fontFamily: 'Poppins_700Bold',
  },
  subtitle: {
    fontSize: 14,
    color: '#666',
    marginBottom: 16,
  },
  listContainer: {
    flex: 1,
  },
  list: {
    gap: 10,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#f5f5f5',
    borderRadius: 10,
    padding: 16,
  },
  rowFurigana: {
    fontSize: 12,
    color: '#888',
    marginBottom: 2,
  },
  rowTitle: {
    fontSize: 17,
    fontFamily: 'Poppins_600SemiBold',
  },
  rowSubtitle: {
    fontSize: 13,
    color: '#666',
    marginTop: 2,
  },
  rowActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  error: {
    color: '#c0392b',
    marginTop: 12,
  },
});
