import { useAuth } from '@clerk/expo';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { KanjiStroke } from '@/components/KanjiStroke';
import { apiFetch } from '@/lib/api';
import type { KanjiDetail, VocabWord } from '@/lib/types';

export default function KanjiDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { getToken } = useAuth();

  const [kanji, setKanji] = useState<KanjiDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openingCompound, setOpeningCompound] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch(`/kanji/${id}`, null);
      setKanji(data);
    } catch (err: any) {
      setError(err?.message ?? 'Request failed');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const openCompound = async (word: string) => {
    setOpeningCompound(word);
    setError(null);
    try {
      const token = await getToken();
      const result = await apiFetch(`/vocab/lookup?word=${encodeURIComponent(word)}`, token);
      if (result.status === 'unavailable') {
        setError(`No dictionary entry found for "${word}"`);
        return;
      }
      const looked: VocabWord = {
        id: result.id,
        kanji: result.kanji,
        reading: result.reading,
        meaning: result.meaning,
        example_sentence: result.example_sentence,
        example_sentence_en: result.example_sentence_en,
        example_sentence_furigana: result.example_sentence_furigana,
        jlpt_level: result.jlpt_level,
        topic: result.topic,
        is_learnt: result.is_learnt,
        in_drill: result.in_drill,
        characters: result.characters,
      };
      router.push({
        pathname: '/learn/word/[id]',
        params: { id: looked.id, data: JSON.stringify(looked) },
      });
    } catch (err: any) {
      setError(err?.message ?? 'Lookup failed');
    } finally {
      setOpeningCompound(null);
    }
  };

  if (loading && !kanji) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator />
      </View>
    );
  }

  if (error && !kanji) {
    return (
      <View style={styles.centered}>
        <Text style={styles.error}>{error}</Text>
      </View>
    );
  }

  if (!kanji) return null;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.strokeWrap}>
        <KanjiStroke strokePaths={kanji.stroke_paths} />
      </View>

      <Text style={styles.meaning}>{kanji.meaning}</Text>

      <View style={styles.readingsRow}>
        {kanji.onyomi && kanji.onyomi.length > 0 && (
          <View style={styles.readingGroup}>
            <Text style={styles.readingLabel}>ON</Text>
            <Text style={styles.readingText}>{kanji.onyomi.join('、')}</Text>
          </View>
        )}
        {kanji.kunyomi && kanji.kunyomi.length > 0 && (
          <View style={styles.readingGroup}>
            <Text style={styles.readingLabel}>KUN</Text>
            <Text style={styles.readingText}>{kanji.kunyomi.join('、')}</Text>
          </View>
        )}
      </View>

      <Text style={styles.meta}>
        {kanji.stroke_count} strokes · {kanji.jlpt_level}
      </Text>

      {kanji.compounds.length > 0 && (
        <View style={styles.compoundsBox}>
          <Text style={styles.compoundsLabel}>Compounds</Text>
          {kanji.compounds.map((c) => (
            <Pressable
              key={c.id}
              style={styles.compoundRow}
              onPress={() => openCompound(c.kanji ?? c.reading)}
              disabled={openingCompound !== null}>
              <View style={{ flex: 1 }}>
                <Text style={styles.compoundWord}>{c.kanji ?? c.reading}</Text>
                <Text style={styles.compoundMeaning}>
                  {c.reading} -- {c.meaning}
                </Text>
              </View>
              {openingCompound === (c.kanji ?? c.reading) && <ActivityIndicator size="small" />}
            </Pressable>
          ))}
        </View>
      )}

      {error && <Text style={styles.error}>{error}</Text>}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    padding: 24,
    paddingTop: 24,
    alignItems: 'center',
    gap: 8,
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  strokeWrap: {
    marginBottom: 8,
  },
  meaning: {
    fontSize: 20,
    fontFamily: 'Poppins_600SemiBold',
  },
  readingsRow: {
    flexDirection: 'row',
    gap: 24,
    marginTop: 8,
  },
  readingGroup: {
    alignItems: 'center',
  },
  readingLabel: {
    fontSize: 11,
    color: '#999',
  },
  readingText: {
    fontSize: 15,
  },
  meta: {
    fontSize: 13,
    color: '#666',
    marginTop: 8,
  },
  compoundsBox: {
    width: '100%',
    backgroundColor: '#f5f5f5',
    borderRadius: 10,
    padding: 16,
    marginTop: 20,
    gap: 12,
  },
  compoundsLabel: {
    fontSize: 12,
    color: '#999',
    textTransform: 'uppercase',
  },
  compoundRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  compoundWord: {
    fontSize: 16,
    fontFamily: 'Poppins_600SemiBold',
  },
  compoundMeaning: {
    fontSize: 13,
    color: '#666',
    marginTop: 2,
  },
  error: {
    color: '#c0392b',
    marginTop: 12,
  },
});
