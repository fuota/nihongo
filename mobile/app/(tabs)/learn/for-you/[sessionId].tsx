import { useAuth } from '@clerk/expo';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Dimensions,
  FlatList,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { DrillToggle } from '@/components/DrillToggle';
import { ExampleSentence } from '@/components/ExampleSentence';
import { IconSymbol } from '@/components/ui/icon-symbol';
import { apiFetch } from '@/lib/api';
import type { SessionItem } from '@/lib/types';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const CARD_WIDTH = SCREEN_WIDTH - 48;

export default function LearningSessionScreen() {
  const { sessionId } = useLocalSearchParams<{ sessionId: string }>();
  const { getToken } = useAuth();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<SessionItem[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [finishing, setFinishing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const data = await apiFetch(`/session/${sessionId}`, token);
      setItems(data.items);
    } catch (err: any) {
      setError(err?.message ?? "Couldn't load this session.");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const finishSession = () => {
    Alert.alert(
      'Finish this session?',
      "This marks everything in it as learnt, so it won't be taught again.",
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Finish',
          onPress: async () => {
            setFinishing(true);
            try {
              const token = await getToken();
              await apiFetch(`/session/${sessionId}/finish`, token, { method: 'POST' });
              router.replace('/learn');
            } catch (err: any) {
              setError(err?.message ?? 'Request failed');
            } finally {
              setFinishing(false);
            }
          },
        },
      ]
    );
  };

  const backToLearn = () => {
    router.replace('/learn');
  };

  const onScrollEnd = (e: any) => {
    const index = Math.round(e.nativeEvent.contentOffset.x / CARD_WIDTH);
    setActiveIndex(index);
  };

  if (loading && items.length === 0) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator />
      </View>
    );
  }

  if (error && items.length === 0) {
    return (
      <View style={styles.centered}>
        <Text style={styles.error}>{error}</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Pressable style={styles.backButton} onPress={backToLearn} hitSlop={8}>
          <IconSymbol name="chevron.left" size={22} color="#333" />
        </Pressable>
        <Text style={styles.title}>Learning Session</Text>
      </View>

      {items.length > 0 && (
        <>
          <Text style={styles.counter}>
            {activeIndex + 1} / {items.length}
          </Text>

          <FlatList
            data={items}
            keyExtractor={(item) => item.id}
            horizontal
            pagingEnabled
            showsHorizontalScrollIndicator={false}
            snapToInterval={CARD_WIDTH}
            decelerationRate="fast"
            onMomentumScrollEnd={onScrollEnd}
            style={styles.carousel}
            renderItem={({ item }) => (
              <ScrollView style={{ width: CARD_WIDTH }} contentContainerStyle={styles.card}>
                <View style={styles.cardHeaderRow}>
                  <Text style={styles.cardTarget}>
                    {item.content_type === 'vocab' ? item.kanji ?? item.reading : item.pattern}
                  </Text>
                  <DrillToggle
                    contentType={item.content_type}
                    contentId={item.id}
                    initialInDrill={item.in_drill}
                  />
                </View>
                {item.content_type === 'vocab' ? (
                  <>
                    <Text style={styles.cardReading}>{item.reading}</Text>
                    <Text style={styles.cardMeaning}>{item.meaning}</Text>
                  </>
                ) : (
                  <Text style={styles.cardMeaning}>{item.explanation}</Text>
                )}

                {item.example_sentence && (
                  <ExampleSentence
                    sentence={item.example_sentence}
                    translation={item.example_sentence_en}
                    segments={item.example_sentence_furigana}
                  />
                )}
              </ScrollView>
            )}
          />
        </>
      )}

      {error && <Text style={styles.error}>{error}</Text>}

      <Pressable style={styles.finishButton} onPress={finishSession} disabled={finishing}>
        {finishing ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.finishButtonText}>Finish Session</Text>
        )}
      </Pressable>
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
    gap: 8,
  },
  backButton: {
    padding: 4,
    marginLeft: -8,
  },
  title: {
    fontSize: 24,
    fontFamily: 'Poppins_700Bold',
  },
  counter: {
    fontSize: 13,
    color: '#999',
    textAlign: 'center',
    marginTop: 4,
  },
  carousel: {
    marginTop: 4,
    marginHorizontal: -24,
  },
  card: {
    paddingHorizontal: 24,
    paddingBottom: 24,
    gap: 4,
  },
  cardHeaderRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
  },
  cardTarget: {
    fontSize: 44,
    fontFamily: 'Poppins_700Bold',
  },
  cardReading: {
    fontSize: 16,
    color: '#666',
  },
  cardMeaning: {
    fontSize: 16,
    marginTop: 4,
  },
  finishButton: {
    backgroundColor: '#5b4fe9',
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    marginBottom: 16,
  },
  finishButtonText: {
    color: '#fff',
    fontFamily: 'Poppins_600SemiBold',
    fontSize: 15,
  },
  error: {
    color: '#c0392b',
    textAlign: 'center',
  },
});
