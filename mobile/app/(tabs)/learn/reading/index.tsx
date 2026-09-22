import { useAuth } from '@clerk/expo';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from 'react-native';

import { IconSymbol } from '@/components/ui/icon-symbol';
import { apiFetch } from '@/lib/api';
import type { ReadingHistoryEntry } from '@/lib/types';

const UNLOCK_THRESHOLD = 10;

export default function ReadingHomeScreen() {
  const { getToken } = useAuth();

  const [loading, setLoading] = useState(true);
  const [locked, setLocked] = useState(false);
  const [learntCount, setLearntCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<ReadingHistoryEntry[]>([]);
  const [generating, setGenerating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const me = await apiFetch('/me', token);
      const total = (me.words_learnt ?? 0) + (me.grammar_learnt ?? 0);
      setLearntCount(total);
      setLocked(total < UNLOCK_THRESHOLD);

      const data = await apiFetch('/reading/history', token);
      setHistory(data.results);
    } catch (err: any) {
      setError(err?.message ?? "Couldn't load Reading.");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const startNewReading = async () => {
    setGenerating(true);
    setError(null);
    try {
      const token = await getToken();
      const data = await apiFetch('/reading/generate', token, { method: 'POST' });
      router.push(`/learn/reading/${data.session_id}` as any);
    } catch (err: any) {
      setError(err?.message ?? "Couldn't generate a passage.");
    } finally {
      setGenerating(false);
    }
  };

  const openSession = (sessionId: string) => {
    router.push(`/learn/reading/${sessionId}` as any);
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Pressable style={styles.backButton} onPress={() => router.replace('/learn')} hitSlop={8}>
          <IconSymbol name="chevron.left" size={22} color="#333" />
        </Pressable>
        <Text style={styles.title}>Reading</Text>
        <View style={{ width: 22 }} />
      </View>

      {locked ? (
        <View style={styles.lockedBox}>
          <Text style={styles.lockedText}>
            Learn a few more words or grammar patterns first ({learntCount}/{UNLOCK_THRESHOLD}) to
            unlock Reading.
          </Text>
        </View>
      ) : (
        <Pressable style={styles.newButton} onPress={startNewReading} disabled={generating}>
          {generating ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.newButtonText}>+ New Reading</Text>
          )}
        </Pressable>
      )}

      {error && <Text style={styles.error}>{error}</Text>}

      <Text style={styles.sectionTitle}>Your Readings</Text>
      <FlatList
        style={styles.list}
        data={history}
        keyExtractor={(item) => item.session_id}
        contentContainerStyle={styles.listContent}
        ListEmptyComponent={<Text style={styles.empty}>No readings yet -- start one above.</Text>}
        renderItem={({ item }) => (
          <Pressable style={styles.row} onPress={() => openSession(item.session_id)}>
            <Text style={styles.rowPreview} numberOfLines={1}>
              {item.passage_preview}
            </Text>
            <Text style={item.status === 'completed' ? styles.rowScore : styles.rowInProgress}>
              {item.status === 'completed' ? `${item.score} / ${item.total}` : 'In progress'}
            </Text>
          </Pressable>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingTop: 60,
    paddingHorizontal: 24,
    gap: 8,
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  backButton: {
    padding: 4,
    width: 22,
  },
  title: {
    fontSize: 18,
    fontFamily: 'Poppins_700Bold',
  },
  lockedBox: {
    backgroundColor: '#f5f5f5',
    borderRadius: 12,
    padding: 16,
    marginTop: 12,
  },
  lockedText: {
    fontSize: 14,
    color: '#666',
    textAlign: 'center',
  },
  newButton: {
    backgroundColor: '#5b4fe9',
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 12,
  },
  newButtonText: {
    color: '#fff',
    fontFamily: 'Poppins_600SemiBold',
    fontSize: 15,
  },
  sectionTitle: {
    fontSize: 14,
    fontFamily: 'Poppins_700Bold',
    color: '#999',
    textTransform: 'uppercase',
    marginTop: 20,
  },
  list: {
    flex: 1,
  },
  listContent: {
    gap: 8,
    paddingBottom: 24,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#f5f5f5',
    borderRadius: 10,
    padding: 14,
    gap: 12,
  },
  rowPreview: {
    flex: 1,
    fontSize: 14,
    color: '#333',
  },
  rowScore: {
    fontSize: 13,
    fontFamily: 'Poppins_600SemiBold',
    color: '#5b4fe9',
  },
  rowInProgress: {
    fontSize: 13,
    fontFamily: 'Poppins_600SemiBold',
    color: '#999',
  },
  empty: {
    color: '#999',
    textAlign: 'center',
    marginTop: 24,
  },
  error: {
    color: '#c0392b',
    textAlign: 'center',
    marginTop: 8,
  },
});
