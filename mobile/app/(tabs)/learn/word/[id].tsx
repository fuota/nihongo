import { useAuth } from '@clerk/expo';
import { router, useLocalSearchParams } from 'expo-router';
import * as Speech from 'expo-speech';
import { useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { DrillToggle } from '@/components/DrillToggle';
import { ExampleSentence } from '@/components/ExampleSentence';
import { apiFetch } from '@/lib/api';
import type { VocabWord } from '@/lib/types';

export default function WordDetailScreen() {
  const { data } = useLocalSearchParams<{ id: string; data: string }>();
  const word: VocabWord = useMemo(() => JSON.parse(data), [data]);
  const { getToken } = useAuth();

  const [isLearnt, setIsLearnt] = useState(word.is_learnt);
  const [learning, setLearning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const speak = () => {
    Speech.speak(word.kanji ?? word.reading, { language: 'ja-JP' });
  };

  const toggleLearnt = async () => {
    setLearning(true);
    setError(null);
    try {
      const token = await getToken();
      await apiFetch('/learn', token, {
        method: isLearnt ? 'DELETE' : 'POST',
        body: JSON.stringify({ content_type: 'vocab', content_id: word.id }),
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
        <Text style={styles.kanji}>{word.kanji ?? word.reading}</Text>
        <View style={styles.headerButtons}>
          <Pressable style={styles.speakerButton} onPress={speak}>
            <Text style={styles.speakerIcon}>🔊</Text>
          </Pressable>
          {word.characters && word.characters.length > 0 && (
            <Pressable
              style={styles.practiceButton}
              onPress={() => router.push(`/learn/kanji/${word.characters![0].id}` as any)}>
              <Text style={styles.practiceButtonText}>✏️ Practice</Text>
            </Pressable>
          )}
          <DrillToggle contentType="vocab" contentId={word.id} initialInDrill={word.in_drill} />
        </View>
      </View>
      <Text style={styles.reading}>{word.reading}</Text>
      <Text style={styles.meaning}>{word.meaning}</Text>

      {word.example_sentence && (
        <ExampleSentence
          sentence={word.example_sentence}
          translation={word.example_sentence_en}
          segments={word.example_sentence_furigana}
        />
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
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  kanji: {
    fontSize: 40,
    fontFamily: 'Poppins_700Bold',
  },
  headerButtons: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  speakerButton: {
    padding: 8,
  },
  speakerIcon: {
    fontSize: 28,
  },
  practiceButton: {
    backgroundColor: '#eef4fb',
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  practiceButtonText: {
    fontSize: 14,
    fontFamily: 'Poppins_600SemiBold',
    color: '#1565c0',
  },
  reading: {
    fontSize: 18,
    color: '#666',
  },
  meaning: {
    fontSize: 18,
    marginTop: 4,
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
