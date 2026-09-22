import { useAuth } from '@clerk/expo';
import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { apiFetch } from '@/lib/api';
import type { FuriganaSegment, VocabWord } from '@/lib/types';

type Props = {
  passage: string;
  segments: FuriganaSegment[] | null;
  onLookup?: (vocabId: string) => void;
};

const PUNCTUATION_ONLY = /^[\s。、！？!?「」『』・~〜,.\n]*$/;
function isLookupable(surface: string): boolean {
  return surface.length > 0 && !PUNCTUATION_ONLY.test(surface);
}

/**
 * Renders a multi-sentence Japanese reading passage: a furigana on/off
 * toggle (unlike ExampleSentence, which always shows furigana for a
 * single short example) and tap-to-lookup on any word, same
 * GET /vocab/lookup path ExampleSentence uses. No boxed "Example"
 * callout and no translation -- this is the passage itself, not an
 * illustrative aside.
 */
export function PassageText({ passage, segments, onLookup }: Props) {
  const { getToken } = useAuth();
  const [showFurigana, setShowFurigana] = useState(true);
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
      onLookup?.(looked.id);
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
    <View>
      <Pressable style={styles.toggle} onPress={() => setShowFurigana((v) => !v)}>
        <Text style={styles.toggleText}>{showFurigana ? 'Hide furigana' : 'Show furigana'}</Text>
      </Pressable>

      <View style={styles.box}>
        {segments && segments.length > 0 ? (
          <View style={styles.furiganaRow}>
            {segments.map((seg, i) =>
              isLookupable(seg.surface) ? (
                <Pressable
                  key={i}
                  style={styles.chunk}
                  onPress={() => lookupSegment(seg.surface)}
                  disabled={lookingUp !== null}>
                  <Text style={styles.reading}>{showFurigana ? seg.reading ?? ' ' : ' '}</Text>
                  <Text style={[styles.text, styles.tappableSurface]}>{seg.surface}</Text>
                  {lookingUp === seg.surface && <ActivityIndicator size="small" style={styles.spinner} />}
                </Pressable>
              ) : (
                <Text key={i} style={styles.text}>
                  {seg.surface}
                </Text>
              )
            )}
          </View>
        ) : (
          <Text style={styles.text}>{passage}</Text>
        )}
      </View>

      {error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  toggle: {
    alignSelf: 'flex-end',
    marginBottom: 8,
  },
  toggleText: {
    fontSize: 13,
    color: '#5b4fe9',
    fontFamily: 'Poppins_600SemiBold',
  },
  box: {
    backgroundColor: '#f5f5f5',
    borderRadius: 12,
    padding: 18,
  },
  text: {
    fontSize: 19,
    lineHeight: 30,
  },
  furiganaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'flex-end',
  },
  chunk: {
    alignItems: 'center',
    marginRight: 1,
  },
  reading: {
    fontSize: 11,
    color: '#1565c0',
    lineHeight: 14,
  },
  tappableSurface: {
    color: '#1565c0',
    fontFamily: 'Poppins_700Bold',
  },
  spinner: {
    position: 'absolute',
    top: -18,
    alignSelf: 'center',
  },
  error: {
    color: '#c0392b',
    fontSize: 13,
    marginTop: 8,
  },
});
