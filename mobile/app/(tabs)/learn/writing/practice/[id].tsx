import { useAuth } from '@clerk/expo';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { DrawingCanvas } from '@/components/DrawingCanvas';
import { DrillToggle } from '@/components/DrillToggle';
import { KanjiStroke } from '@/components/KanjiStroke';
import { apiFetch } from '@/lib/api';
import { JLPT_LEVELS, type VocabWord } from '@/lib/types';

const SEARCH_DEBOUNCE_MS = 350;
const BROWSE_PAGE_SIZE = 10;

type BrowseFilter = 'my_words' | (typeof JLPT_LEVELS)[number];

type RecognitionResult = {
  character: string | null;
  confidence: number;
  message?: string;
};

type FeedbackResult = {
  feedback: string;
  is_correct: boolean;
  is_first_correct: boolean;
};

export default function WritingPracticeScreen() {
  const { data } = useLocalSearchParams<{ id: string; data: string }>();
  const { getToken } = useAuth();

  const [word, setWord] = useState<VocabWord>(() => JSON.parse(data));

  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<RecognitionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [strokePaths, setStrokePaths] = useState<string[] | null>(null);
  const [loadingGuide, setLoadingGuide] = useState(false);
  const [feedback, setFeedback] = useState<FeedbackResult | null>(null);
  const [loadingFeedback, setLoadingFeedback] = useState(false);

  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<VocabWord[] | null>(null);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [browseFilter, setBrowseFilter] = useState<BrowseFilter>('my_words');
  const [browseWords, setBrowseWords] = useState<VocabWord[]>([]);
  const [browseLoading, setBrowseLoading] = useState(false);
  // FlatList's onEndReached can fire again before a state update from the
  // previous fetch has flushed (e.g. it fires once immediately if the
  // first page doesn't fill the screen, racing the initial-load effect).
  // Refs -- not state -- track in-flight/offset/hasMore so that race can't
  // trigger two overlapping fetches of the same page and duplicate items.
  const browseNextOffsetRef = useRef(0);
  const browseHasMoreRef = useRef(true);
  const browseLoadingRef = useRef(false);

  const fetchBrowsePage = useCallback(
    async (filter: BrowseFilter, offset: number) => {
      const token = await getToken();
      const levelParam = filter === 'my_words' ? '' : `&level=${filter}`;
      const learntParam = filter === 'my_words' ? '&learnt=true' : '';
      const data = await apiFetch(
        `/vocab?limit=${BROWSE_PAGE_SIZE}&offset=${offset}${levelParam}${learntParam}`,
        token
      );
      const fullPage = (data.results as VocabWord[]).length === BROWSE_PAGE_SIZE;
      return { words: (data.results as VocabWord[]).filter((w) => w.kanji), fullPage };
    },
    // getToken excluded on purpose -- see the Vocab topic screen for why.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  useEffect(() => {
    if (!searchOpen) return;
    let cancelled = false;
    browseNextOffsetRef.current = 0;
    browseHasMoreRef.current = true;
    browseLoadingRef.current = true;
    setBrowseWords([]);
    setBrowseLoading(true);
    fetchBrowsePage(browseFilter, 0)
      .then(({ words, fullPage }) => {
        if (cancelled) return;
        setBrowseWords(words);
        browseNextOffsetRef.current = BROWSE_PAGE_SIZE;
        browseHasMoreRef.current = fullPage;
      })
      .catch(() => {
        if (!cancelled) setBrowseWords([]);
      })
      .finally(() => {
        browseLoadingRef.current = false;
        if (!cancelled) setBrowseLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [searchOpen, browseFilter, fetchBrowsePage]);

  const loadMoreBrowseWords = () => {
    if (browseLoadingRef.current || !browseHasMoreRef.current) return;
    browseLoadingRef.current = true;
    setBrowseLoading(true);
    const offset = browseNextOffsetRef.current;
    fetchBrowsePage(browseFilter, offset)
      .then(({ words, fullPage }) => {
        setBrowseWords((prev) => {
          const seen = new Set(prev.map((w) => w.id));
          return [...prev, ...words.filter((w) => !seen.has(w.id))];
        });
        browseNextOffsetRef.current = offset + BROWSE_PAGE_SIZE;
        browseHasMoreRef.current = fullPage;
      })
      .catch(() => {
        browseHasMoreRef.current = false;
      })
      .finally(() => {
        browseLoadingRef.current = false;
        setBrowseLoading(false);
      });
  };

  const target = word.characters?.[0]?.character ?? word.kanji?.[0] ?? null;
  const targetCharacterId = word.characters?.[0]?.id ?? null;

  const selectWord = (next: VocabWord) => {
    setWord(next);
    setResult(null);
    setFeedback(null);
    setError(null);
    setAttempt((n) => n + 1);
    setSearchOpen(false);
    setQuery('');
    setSearchResults(null);
  };

  useFocusEffect(
    useCallback(() => {
      if (!targetCharacterId) return;
      let cancelled = false;
      setLoadingGuide(true);
      apiFetch(`/kanji/${targetCharacterId}`, null)
        .then((data) => {
          if (!cancelled) setStrokePaths(data.stroke_paths ?? []);
        })
        .catch(() => {
          if (!cancelled) setStrokePaths(null);
        })
        .finally(() => {
          if (!cancelled) setLoadingGuide(false);
        });
      return () => {
        cancelled = true;
      };
    }, [targetCharacterId])
  );

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const trimmed = query.trim();
    if (!trimmed) {
      setSearchResults(null);
      setSearching(false);
      return;
    }

    setSearching(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const token = await getToken();
        const data = await apiFetch(`/vocab?q=${encodeURIComponent(trimmed)}&limit=30`, token);
        setSearchResults((data.results as VocabWord[]).filter((w) => w.kanji));
      } catch {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const handleSubmit = async (base64Png: string) => {
    setSubmitting(true);
    setError(null);
    setResult(null);
    setFeedback(null);
    try {
      const token = await getToken();
      const data = await apiFetch('/kanji/recognize', token, {
        method: 'POST',
        body: JSON.stringify({ image_base64: base64Png }),
      });
      setResult(data);

      if (targetCharacterId) {
        setLoadingFeedback(true);
        try {
          const feedbackData = await apiFetch('/kanji/feedback', token, {
            method: 'POST',
            body: JSON.stringify({
              character_id: targetCharacterId,
              recognized_character: data.character,
              confidence: data.confidence,
            }),
          });
          setFeedback(feedbackData);
        } catch {
          // feedback is a nice-to-have on top of the recognition result;
          // fail quietly rather than blocking the outcome the user cares about
        } finally {
          setLoadingFeedback(false);
        }
      }
    } catch (err: any) {
      setError(err?.message ?? "Couldn't reach the server, try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const retry = () => {
    setResult(null);
    setFeedback(null);
    setError(null);
    setAttempt((n) => n + 1);
  };

  const isMatch = !!(result?.character && target && result.character === target);

  return (
    <View style={styles.screen}>
      <View style={styles.topBar}>
        <Pressable
          onPress={() => {
            if (searchOpen) {
              setSearchOpen(false);
              setQuery('');
              setSearchResults(null);
            } else {
              router.replace('/learn');
            }
          }}
          hitSlop={12}
          style={styles.topBarButton}>
          <MaterialIcons name="chevron-left" size={28} color="#000" />
        </Pressable>

        {searchOpen ? (
          <View style={styles.searchBar}>
            <MaterialIcons name="search" size={18} color="#999" />
            <TextInput
              autoFocus
              style={styles.searchInput}
              value={query}
              onChangeText={setQuery}
              placeholder="Search a word to practice"
              placeholderTextColor="#999"
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="search"
            />
            {query.length > 0 && (
              <Pressable onPress={() => setQuery('')} hitSlop={8}>
                <MaterialIcons name="close" size={18} color="#999" />
              </Pressable>
            )}
          </View>
        ) : (
          <>
            <Text style={styles.topBarTitle}>Writing</Text>
            <View style={styles.topBarActions}>
              <Pressable onPress={() => setSearchOpen(true)} hitSlop={12} style={styles.topBarButton}>
                <MaterialIcons name="search" size={24} color="#000" />
              </Pressable>
            </View>
          </>
        )}
      </View>

      {searchOpen ? (
        <View style={styles.searchResultsWrap}>
          {searchResults === null && (
            <>
              <View style={styles.browseFilterRow}>
                <Pressable
                  style={[styles.browseFilterPill, browseFilter === 'my_words' && styles.browseFilterPillActive]}
                  onPress={() => setBrowseFilter('my_words')}>
                  <Text
                    style={[
                      styles.browseFilterText,
                      browseFilter === 'my_words' && styles.browseFilterTextActive,
                    ]}
                    numberOfLines={1}
                    adjustsFontSizeToFit>
                    My Words
                  </Text>
                </Pressable>
                {JLPT_LEVELS.map((lvl) => (
                  <Pressable
                    key={lvl}
                    style={[styles.browseFilterPill, browseFilter === lvl && styles.browseFilterPillActive]}
                    onPress={() => setBrowseFilter(lvl)}>
                    <Text style={[styles.browseFilterText, browseFilter === lvl && styles.browseFilterTextActive]}>
                      {lvl}
                    </Text>
                  </Pressable>
                ))}
              </View>

              {browseLoading && browseWords.length === 0 && <ActivityIndicator style={{ marginTop: 12 }} />}
              {!browseLoading && browseWords.length === 0 && (
                <Text style={styles.emptyText}>
                  {browseFilter === 'my_words'
                    ? 'No kanji words learnt yet -- mark some as Learnt in Vocab first.'
                    : 'No kanji words at this level yet.'}
                </Text>
              )}
              <FlatList
                data={browseWords}
                keyExtractor={(item) => item.id}
                contentContainerStyle={{ gap: 10, padding: 20 }}
                keyboardShouldPersistTaps="handled"
                onEndReached={loadMoreBrowseWords}
                onEndReachedThreshold={0.5}
                ListFooterComponent={
                  browseLoading && browseWords.length > 0 ? (
                    <ActivityIndicator style={{ marginTop: 12 }} />
                  ) : null
                }
                renderItem={({ item }) => (
                  <Pressable style={styles.resultRow} onPress={() => selectWord(item)}>
                    <Text style={styles.resultFurigana}>{item.reading}</Text>
                    <Text style={styles.resultTitle}>{item.kanji}</Text>
                    <Text style={styles.resultSubtitle}>{item.meaning}</Text>
                  </Pressable>
                )}
              />
            </>
          )}

          {searching && <ActivityIndicator style={{ marginTop: 12 }} />}
          {!searching && searchResults && searchResults.length === 0 && (
            <Text style={styles.emptyText}>No kanji words match "{query.trim()}".</Text>
          )}
          {searchResults && searchResults.length > 0 && (
            <FlatList
              data={searchResults}
              keyExtractor={(item) => item.id}
              contentContainerStyle={{ gap: 10, padding: 20 }}
              keyboardShouldPersistTaps="handled"
              renderItem={({ item }) => (
                <Pressable style={styles.resultRow} onPress={() => selectWord(item)}>
                  <Text style={styles.resultFurigana}>{item.reading}</Text>
                  <Text style={styles.resultTitle}>{item.kanji}</Text>
                  <Text style={styles.resultSubtitle}>{item.meaning}</Text>
                </Pressable>
              )}
            />
          )}
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.container}>
          <View style={styles.headerRow}>
            <View style={styles.wordMeaningGroup}>
              <View style={styles.wordBlock}>
                <Text style={styles.target}>{target ?? word.kanji}</Text>
                <Text style={styles.furigana}>{word.reading}</Text>
              </View>

              <View style={styles.meaningBlock}>
                <Text style={styles.meaningLabel}>Meaning</Text>
                <Text style={styles.meaningText}>{word.meaning}</Text>
              </View>
            </View>

            <View style={styles.rightColumn}>
              {targetCharacterId && (
                <DrillToggle contentType="writing" contentId={targetCharacterId} initialInDrill={false} />
              )}
              {loadingGuide && <ActivityIndicator style={{ marginTop: 10 }} />}
              {strokePaths && strokePaths.length > 0 && (
                <View style={styles.guideBlock}>
                  <Text style={styles.guideLabel}>Stroke Order</Text>
                  <KanjiStroke strokePaths={strokePaths} size={84} />
                </View>
              )}
            </View>
          </View>

          <View style={styles.canvasSection}>
            <DrawingCanvas
              key={attempt}
              size={250}
              onSubmit={handleSubmit}
              submitting={submitting}
              showControls={!result}
              hintPaths={strokePaths ?? undefined}
            />
          </View>

          {error && <Text style={styles.error}>{error}</Text>}

          {result && (
            <View style={styles.outcomeSection}>
              <View style={styles.outcomeRow}>
                <View style={[styles.outcomeBadge, isMatch ? styles.badgeCorrect : styles.badgeIncorrect]}>
                  <Text style={styles.badgeIcon}>{isMatch ? '✓' : '✗'}</Text>
                </View>
                <Text style={isMatch ? styles.outcomeTextCorrect : styles.outcomeTextIncorrect}>
                  {isMatch ? 'Correct' : 'Incorrect'}
                </Text>
                <Pressable style={styles.retryButton} onPress={retry}>
                  <Text style={styles.retryButtonText}>↻</Text>
                </Pressable>
              </View>

              {loadingFeedback && <ActivityIndicator style={{ marginTop: 8 }} />}
              {feedback && <Text style={styles.feedbackText}>{feedback.feedback}</Text>}

              <Text style={styles.debugText}>
                Recognized: {result.character ?? result.message ?? 'nothing'}
                {result.character ? ` (${Math.round(result.confidence * 100)}%)` : ''}
              </Text>
            </View>
          )}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingTop: 60,
    paddingHorizontal: 12,
    paddingBottom: 12,
    gap: 4,
  },
  topBarButton: {
    padding: 6,
  },
  topBarTitle: {
    flex: 1,
    fontSize: 17,
    fontFamily: 'Poppins_600SemiBold',
    textAlign: 'center',
  },
  topBarActions: {
    flexDirection: 'row',
  },
  searchBar: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#f5f5f5',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  searchInput: {
    flex: 1,
    fontSize: 15,
  },
  searchResultsWrap: {
    flex: 1,
  },
  browseFilterRow: {
    flexDirection: 'row',
    gap: 4,
    paddingHorizontal: 20,
    paddingTop: 12,
  },
  browseFilterPill: {
    flex: 1,
    backgroundColor: '#f5f5f5',
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 4,
    alignItems: 'center',
  },
  browseFilterPillActive: {
    backgroundColor: '#5b4fe9',
  },
  browseFilterText: {
    fontSize: 12,
    fontFamily: 'Poppins_600SemiBold',
    color: '#333',
  },
  browseFilterTextActive: {
    color: '#fff',
  },
  emptyText: {
    color: '#999',
    textAlign: 'center',
    marginTop: 24,
  },
  resultRow: {
    backgroundColor: '#f5f5f5',
    borderRadius: 10,
    padding: 16,
  },
  resultFurigana: {
    fontSize: 12,
    color: '#888',
    marginBottom: 2,
  },
  resultTitle: {
    fontSize: 17,
    fontFamily: 'Poppins_600SemiBold',
  },
  resultSubtitle: {
    fontSize: 13,
    color: '#666',
    marginTop: 2,
  },
  container: {
    flexGrow: 1,
    padding: 20,
    paddingTop: 8,
    alignItems: 'center',
    gap: 2,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    width: '100%',
  },
  wordMeaningGroup: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 20,
  },
  wordBlock: {
    alignItems: 'center',
    marginTop: 10,
  },
  target: {
    fontSize: 76,
    fontFamily: 'Poppins_700Bold',
    lineHeight: 84,
  },
  furigana: {
    fontSize: 15,
    color: '#666',
    marginTop: 2,
  },
  meaningBlock: {
    alignItems: 'flex-start',
    marginTop: 10,
  },
  meaningLabel: {
    fontSize: 11,
    color: '#999',
    textTransform: 'uppercase',
    fontFamily: 'Poppins_700Bold',
  },
  meaningText: {
    fontSize: 14,
    color: '#333',
    marginTop: 2,
  },
  rightColumn: {
    alignItems: 'flex-end',
    gap: 4,
  },
  guideBlock: {
    alignItems: 'flex-end',
  },
  guideLabel: {
    fontSize: 11,
    color: '#999',
    textTransform: 'uppercase',
    marginBottom: 6,
    fontFamily: 'Poppins_700Bold',
  },
  canvasSection: {
    marginTop: 4,
  },
  outcomeSection: {
    marginTop: 12,
    alignItems: 'center',
    gap: 4,
    width: '100%',
  },
  outcomeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  outcomeBadge: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeCorrect: {
    backgroundColor: '#4caf50',
  },
  badgeIncorrect: {
    backgroundColor: '#e53935',
  },
  badgeIcon: {
    fontSize: 14,
    fontFamily: 'Poppins_700Bold',
    color: '#fff',
  },
  outcomeTextCorrect: {
    fontSize: 17,
    fontFamily: 'Poppins_600SemiBold',
    color: '#2e7d32',
  },
  outcomeTextIncorrect: {
    fontSize: 17,
    fontFamily: 'Poppins_600SemiBold',
    color: '#c0392b',
  },
  retryButton: {
    marginLeft: 4,
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#f0f0f0',
    alignItems: 'center',
    justifyContent: 'center',
  },
  retryButtonText: {
    fontSize: 18,
  },
  feedbackText: {
    marginTop: 8,
    fontSize: 13,
    color: '#333',
    textAlign: 'center',
    lineHeight: 18,
    paddingHorizontal: 12,
  },
  debugText: {
    marginTop: 10,
    fontSize: 11,
    color: '#999',
  },
  error: {
    color: '#c0392b',
    marginTop: 12,
  },
});
