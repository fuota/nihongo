import { useAuth } from '@clerk/expo';
import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { apiFetch } from '@/lib/api';
import type { FuriganaSegment, VocabWord } from '@/lib/types';

type Props = {
  label?: string;
  sentence: string;
  translation: string | null;
  segments: FuriganaSegment[] | null;
};

// Punctuation-only chunks ("。", "、", ...) aren't worth looking up --
// everything else (including pure-kana words like "ここ") is tappable.
const PUNCTUATION_ONLY = /^[\s。、！？!?「」『』・~〜,.]*$/;
function isLookupable(surface: string): boolean {
  return surface.length > 0 && !PUNCTUATION_ONLY.test(surface);
}

/**
 * Renders a Japanese example sentence with furigana above kanji-bearing
 * chunks and an English translation below. Any furigana chunk is
 * tappable: it resolves through GET /vocab/lookup (the Day 2 hybrid
 * DB/API path) and navigates to that word's own detail screen, so a
 * user reading either a Vocab or Grammar example can drill into an
 * unfamiliar word it uses.
 */
export function ExampleSentence({ label = 'Example', sentence, translation, segments }: Props) {
  const { getToken } = useAuth();
  const [lookingUp, setLookingUp] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const lookupSegment = async (surface: string) => {
    setLookingUp(surface);
    setError(null);
    try {
      const token = await getToken();
      const result = await apiFetch(`/vocab/lookup?word=${encodeURIComponent(surface)}`, token);
      if (result.status === 'unavailable') {
        setError(`No dictionary entry found for "${surface}"`);
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
      setLookingUp(null);
    }
  };

  return (
    <View style={styles.box}>
      <Text style={styles.label}>{label}</Text>

      {segments && segments.length > 0 ? (
        <View style={styles.furiganaRow}>
          {segments.map((seg, i) =>
            isLookupable(seg.surface) ? (
              <Pressable
                key={i}
                style={styles.furiganaChunk}
                onPress={() => lookupSegment(seg.surface)}
                disabled={lookingUp !== null}>
                <Text style={styles.furiganaReading}>{seg.reading ?? ' '}</Text>
                <Text style={[styles.text, styles.tappableSurface]}>{seg.surface}</Text>
                {lookingUp === seg.surface && (
                  <ActivityIndicator size="small" style={styles.furiganaSpinner} />
                )}
              </Pressable>
            ) : (
              <Text key={i} style={styles.text}>
                {seg.surface}
              </Text>
            )
          )}
        </View>
      ) : (
        <Text style={styles.text}>{sentence}</Text>
      )}

      {translation && <Text style={styles.translation}>{translation}</Text>}
      {error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    backgroundColor: '#f5f5f5',
    borderRadius: 10,
    padding: 16,
    marginTop: 16,
  },
  label: {
    fontSize: 12,
    color: '#999',
    marginBottom: 10,
    textTransform: 'uppercase',
  },
  text: {
    fontSize: 18,
    lineHeight: 24,
  },
  furiganaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'flex-end',
  },
  furiganaChunk: {
    alignItems: 'center',
    marginRight: 1,
  },
  furiganaReading: {
    fontSize: 11,
    color: '#1565c0',
    lineHeight: 14,
  },
  tappableSurface: {
    color: '#1565c0',
    fontFamily: 'Poppins_700Bold',
  },
  furiganaSpinner: {
    position: 'absolute',
    top: -18,
    alignSelf: 'center',
  },
  translation: {
    fontSize: 14,
    color: '#666',
    marginTop: 12,
    fontStyle: 'italic',
  },
  error: {
    color: '#c0392b',
    fontSize: 13,
    marginTop: 8,
  },
});
