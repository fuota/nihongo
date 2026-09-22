import { useAuth } from '@clerk/expo';
import { useLocalSearchParams } from 'expo-router';
import { useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { DrillToggle } from '@/components/DrillToggle';
import { ExampleSentence } from '@/components/ExampleSentence';
import { apiFetch } from '@/lib/api';
import type { GrammarPattern } from '@/lib/types';

export default function GrammarPatternDetailScreen() {
  const { data } = useLocalSearchParams<{ id: string; data: string }>();
  const pattern: GrammarPattern = useMemo(() => JSON.parse(data), [data]);
  const { getToken } = useAuth();

  const [isLearnt, setIsLearnt] = useState(pattern.is_learnt);
  const [learning, setLearning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleLearnt = async () => {
    setLearning(true);
    setError(null);
    try {
      const token = await getToken();
      await apiFetch('/learn', token, {
        method: isLearnt ? 'DELETE' : 'POST',
        body: JSON.stringify({ content_type: 'grammar', content_id: pattern.id }),
      });
      setIsLearnt(!isLearnt);
    } catch (err: any) {
      setError(err?.message ?? 'Request failed');
    } finally {
      setLearning(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.pattern}>{pattern.pattern}</Text>
        <DrillToggle contentType="grammar" contentId={pattern.id} initialInDrill={pattern.in_drill} />
      </View>
      <Text style={styles.explanation}>{pattern.explanation}</Text>

      {pattern.example_sentence && (
        <ExampleSentence
          sentence={pattern.example_sentence}
          translation={pattern.example_sentence_en}
          segments={pattern.example_sentence_furigana}
        />
      )}

      {pattern.drill_sentence && (
        <View style={styles.box}>
          <Text style={styles.boxLabel}>Drill Sentence</Text>
          <Text style={styles.boxText}>{pattern.drill_sentence}</Text>
        </View>
      )}

      {error && <Text style={styles.error}>{error}</Text>}

      <Pressable
        style={[styles.actionButton, isLearnt && styles.actionButtonDone]}
        onPress={toggleLearnt}
        disabled={learning}>
        {learning ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.actionButtonText}>{isLearnt ? '✓ Learnt' : 'Mark as Learnt'}</Text>
        )}
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    padding: 24,
    paddingTop: 24,
    gap: 8,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
  },
  pattern: {
    fontSize: 32,
    fontFamily: 'Poppins_700Bold',
  },
  explanation: {
    fontSize: 16,
    color: '#333',
    marginTop: 8,
    lineHeight: 22,
  },
  box: {
    backgroundColor: '#f5f5f5',
    borderRadius: 10,
    padding: 16,
    marginTop: 16,
  },
  boxLabel: {
    fontSize: 12,
    color: '#999',
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  boxText: {
    fontSize: 16,
    lineHeight: 22,
  },
  actionButton: {
    backgroundColor: '#000',
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 20,
  },
  secondaryButton: {
    backgroundColor: '#444',
    marginTop: 12,
  },
  actionButtonDone: {
    backgroundColor: '#2e7d32',
  },
  actionButtonText: {
    color: '#fff',
    fontFamily: 'Poppins_600SemiBold',
    fontSize: 16,
  },
  error: {
    color: '#c0392b',
    marginTop: 12,
  },
});
