import { useAuth } from '@clerk/expo';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { DrillToggle } from '@/components/DrillToggle';
import { LearntToggle } from '@/components/LearntToggle';
import { apiFetch } from '@/lib/api';
import { JLPT_LEVELS, type GrammarPattern } from '@/lib/types';

const SEARCH_DEBOUNCE_MS = 350;

export default function GrammarLevelPicker() {
  const { getToken } = useAuth();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<GrammarPattern[] | null>(null);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [level, setLevel] = useState<(typeof JLPT_LEVELS)[number]>('N5');
  const [levelReady, setLevelReady] = useState(false);
  const [mode, setMode] = useState<'browse' | 'my_grammar'>('browse');
  const [patterns, setPatterns] = useState<GrammarPattern[]>([]);
  const [loadingLevel, setLoadingLevel] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const token = await getToken();
        const data = await apiFetch('/me', token);
        if (data.jlpt_level && (JLPT_LEVELS as readonly string[]).includes(data.jlpt_level)) {
          setLevel(data.jlpt_level);
        }
      } catch {
        // fall back to the default level
      } finally {
        setLevelReady(true);
      }
    })();
    // only need the user's level once, to pick a default
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadForLevel = useCallback(async () => {
    setLoadingLevel(true);
    try {
      const token = await getToken();
      const learntParam = mode === 'my_grammar' ? '&learnt=true' : '';
      const data = await apiFetch(`/grammar?level=${level}${learntParam}`, token);
      setPatterns(data.results);
    } catch {
      setPatterns([]);
    } finally {
      setLoadingLevel(false);
    }
    // getToken excluded on purpose -- see the Vocab screen for why.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level, mode]);

  useFocusEffect(
    useCallback(() => {
      if (levelReady) loadForLevel();
    }, [levelReady, loadForLevel])
  );

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const trimmed = query.trim();
    if (!trimmed) {
      setResults(null);
      setSearching(false);
      return;
    }

    setSearching(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const token = await getToken();
        const data = await apiFetch(`/grammar?q=${encodeURIComponent(trimmed)}&limit=30`, token);
        setResults(data.results);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  const openPattern = (pattern: GrammarPattern) => {
    router.push({
      pathname: '/learn/grammar/pattern/[id]',
      params: { id: pattern.id, data: JSON.stringify(pattern) },
    });
  };

  return (
    <View style={styles.container}>
      <View style={styles.searchBar}>
        <MaterialIcons name="search" size={20} color="#999" />
        <TextInput
          style={styles.searchInput}
          value={query}
          onChangeText={setQuery}
          placeholder="Search grammar (pattern or explanation)"
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

      {results === null ? (
        <>
          <View style={styles.levelRow}>
            {JLPT_LEVELS.map((lvl) => (
              <Pressable
                key={lvl}
                style={[styles.levelPill, lvl === level && styles.levelPillActive]}
                onPress={() => setLevel(lvl)}>
                <Text style={[styles.levelPillText, lvl === level && styles.levelPillTextActive]}>
                  {lvl}
                </Text>
              </Pressable>
            ))}
          </View>

          <View style={styles.toggleRow}>
            <Pressable
              style={[styles.toggleButton, mode === 'browse' && styles.toggleButtonActive]}
              onPress={() => setMode('browse')}>
              <Text style={[styles.toggleText, mode === 'browse' && styles.toggleTextActive]}>
                Browse
              </Text>
            </Pressable>
            <Pressable
              style={[styles.toggleButton, mode === 'my_grammar' && styles.toggleButtonActive]}
              onPress={() => setMode('my_grammar')}>
              <Text style={[styles.toggleText, mode === 'my_grammar' && styles.toggleTextActive]}>
                My Grammar
              </Text>
            </Pressable>
          </View>

          {loadingLevel && <ActivityIndicator style={{ marginTop: 24 }} />}

          {!loadingLevel && (
            <FlatList
              data={patterns}
              keyExtractor={(item) => item.id}
              contentContainerStyle={styles.list}
              ListEmptyComponent={
                <Text style={styles.empty}>
                  {mode === 'browse'
                    ? 'No grammar patterns seeded for this level yet.'
                    : "Nothing learnt at this level yet -- mark a pattern as Learnt to see it here."}
                </Text>
              }
              renderItem={({ item }) => (
                <Pressable style={styles.row} onPress={() => openPattern(item)}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>{item.pattern}</Text>
                    <Text style={styles.rowSubtitle} numberOfLines={1}>
                      {item.explanation}
                    </Text>
                  </View>
                  <View style={styles.rowActions}>
                    <LearntToggle contentType="grammar" contentId={item.id} initialIsLearnt={item.is_learnt} />
                    <DrillToggle contentType="grammar" contentId={item.id} initialInDrill={item.in_drill} />
                  </View>
                </Pressable>
              )}
            />
          )}
        </>
      ) : (
        <View style={styles.resultsWrap}>
          {searching && <ActivityIndicator style={{ marginTop: 8 }} />}
          {!searching && results.length === 0 && (
            <Text style={styles.emptyText}>No matches for "{query.trim()}".</Text>
          )}
          <FlatList
            data={results}
            keyExtractor={(item) => item.id}
            contentContainerStyle={{ gap: 10 }}
            keyboardShouldPersistTaps="handled"
            renderItem={({ item }) => (
              <Pressable style={styles.resultRow} onPress={() => openPattern(item)}>
                <Text style={styles.resultTitle}>{item.pattern}</Text>
                <Text style={styles.resultSubtitle} numberOfLines={2}>
                  {item.explanation}
                </Text>
              </Pressable>
            )}
          />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 24,
    paddingTop: 16,
    gap: 12,
  },
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#f5f5f5',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  searchInput: {
    flex: 1,
    fontSize: 15,
  },
  levelRow: {
    flexDirection: 'row',
    gap: 6,
  },
  levelPill: {
    flex: 1,
    backgroundColor: '#f5f5f5',
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
  },
  levelPillActive: {
    backgroundColor: '#5b4fe9',
  },
  levelPillText: {
    fontSize: 15,
    fontFamily: 'Poppins_600SemiBold',
    color: '#333',
  },
  levelPillTextActive: {
    color: '#fff',
  },
  toggleRow: {
    flexDirection: 'row',
    backgroundColor: '#f0f0f0',
    borderRadius: 10,
    padding: 4,
  },
  toggleButton: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
  },
  toggleButtonActive: {
    backgroundColor: '#000',
  },
  toggleText: {
    fontFamily: 'Poppins_600SemiBold',
    color: '#666',
  },
  toggleTextActive: {
    color: '#fff',
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
  empty: {
    color: '#999',
    marginTop: 24,
    textAlign: 'center',
  },
  resultsWrap: {
    flex: 1,
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
  resultTitle: {
    fontSize: 17,
    fontFamily: 'Poppins_600SemiBold',
  },
  resultSubtitle: {
    fontSize: 13,
    color: '#666',
    marginTop: 4,
  },
});
