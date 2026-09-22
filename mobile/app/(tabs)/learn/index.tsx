import { useAuth } from '@clerk/expo';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { apiFetch } from '@/lib/api';

const SECTIONS = [
  { key: 'vocab', label: 'Vocab', subtitle: 'Words by JLPT level and topic', icon: 'translate' },
  { key: 'grammar', label: 'Grammar', subtitle: 'Patterns by JLPT level', icon: 'rule' },
  { key: 'writing', label: 'Writing', subtitle: 'Practice drawing from My Words', icon: 'draw' },
  { key: 'reading', label: 'Reading', subtitle: 'A passage built from what you know', icon: 'auto-stories' },
] as const;

type MeStats = {
  jlpt_level: string;
  days_attended: number;
  words_learnt: number;
  streak_count: number;
};

type CurrentSession = {
  session_id: string;
  item_count: number;
} | null;

export default function LearnHome() {
  const { getToken } = useAuth();
  const [stats, setStats] = useState<MeStats | null>(null);
  const [currentSession, setCurrentSession] = useState<CurrentSession>(null);
  const [loadingSession, setLoadingSession] = useState(false);
  const [startingSession, setStartingSession] = useState(false);
  const [finishing, setFinishing] = useState(false);

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      (async () => {
        try {
          const token = await getToken();
          const data = await apiFetch('/me', token);
          if (!cancelled) setStats(data);
        } catch {
          // stats are a nice-to-have on this screen; fail quietly
        }
      })();

      (async () => {
        setLoadingSession(true);
        try {
          const token = await getToken();
          const data = await apiFetch('/session/current', token);
          if (!cancelled) setCurrentSession(data);
        } catch {
          if (!cancelled) setCurrentSession(null);
        } finally {
          if (!cancelled) setLoadingSession(false);
        }
      })();

      return () => {
        cancelled = true;
      };
    }, [])
  );

  const startLesson = async () => {
    setStartingSession(true);
    try {
      const token = await getToken();
      const data = await apiFetch('/session/generate', token, { method: 'POST' });
      setCurrentSession({ session_id: data.session_id, item_count: data.items.length });
      router.push(`/learn/for-you/${data.session_id}` as any);
    } catch {
      // if generation fails, the user just sees Start Lesson again
    } finally {
      setStartingSession(false);
    }
  };

  const continueLearning = () => {
    if (currentSession) router.push(`/learn/for-you/${currentSession.session_id}` as any);
  };

  const finishSession = () => {
    if (!currentSession) return;
    Alert.alert(
      'Finish this session?',
      "This marks everything in it as learnt, so it won't be taught again.",
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Finish',
          style: 'default',
          onPress: async () => {
            setFinishing(true);
            try {
              const token = await getToken();
              await apiFetch(`/session/${currentSession.session_id}/finish`, token, {
                method: 'POST',
              });
              setCurrentSession(null);
            } catch {
              // leave the session active if finishing failed; user can retry
            } finally {
              setFinishing(false);
            }
          },
        },
      ]
    );
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.greetingRow}>
        <View style={styles.greetingCard}>
          <Text style={styles.greeting}>こんにちは!</Text>
          <Text style={styles.greetingSubtitle}>Ready to learn Japanese?</Text>
        </View>
        {stats && (
          <View style={styles.streakBadge}>
            <MaterialIcons name="local-fire-department" size={30} color="#e2711d" />
            <Text style={styles.streakText}>{stats.streak_count}</Text>
          </View>
        )}
      </View>

      {loadingSession && <ActivityIndicator style={{ marginTop: 8 }} />}

      {!loadingSession && !currentSession && (
        <Pressable style={styles.startLessonButton} onPress={startLesson} disabled={startingSession}>
          {startingSession ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.startLessonText}>Start Lesson</Text>
          )}
        </Pressable>
      )}

      {!loadingSession && currentSession && (
        <View style={styles.sessionCard}>
          <Text style={styles.sessionCardTitle}>
            Current Session ({currentSession.item_count} items)
          </Text>
          <View style={styles.sessionCardButtons}>
            <Pressable style={styles.continueButton} onPress={continueLearning}>
              <Text style={styles.continueButtonText}>Continue Learning</Text>
            </Pressable>
            <Pressable style={styles.finishButton} onPress={finishSession} disabled={finishing}>
              {finishing ? (
                <ActivityIndicator color="#444" />
              ) : (
                <Text style={styles.finishButtonText}>Finish Session</Text>
              )}
            </Pressable>
          </View>
        </View>
      )}

      <Text style={styles.progressTitle}>Your progress</Text>
      <View style={styles.statsRow}>
        <View style={styles.statCard}>
          <Text style={styles.statValue}>{stats?.days_attended ?? '--'}</Text>
          <Text style={styles.statLabel}>Days attended</Text>
        </View>
        <View style={styles.statCard}>
          <Text style={styles.statValue}>{stats?.words_learnt ?? '--'}</Text>
          <Text style={styles.statLabel}>Words learned</Text>
        </View>
        <View style={styles.statCard}>
          <Text style={styles.statValue}>{stats?.jlpt_level ?? '--'}</Text>
          <Text style={styles.statLabel}>Level</Text>
        </View>
      </View>

      <View style={styles.cardsGrid}>
        {SECTIONS.map((section) => (
          <Pressable
            key={section.key}
            style={styles.card}
            onPress={() => router.push(`/learn/${section.key}` as any)}>
            <View style={styles.cardTitleRow}>
              <MaterialIcons name={section.icon} size={18} color="#333" />
              <Text style={styles.cardTitle}>{section.label}</Text>
            </View>
            <Text style={styles.cardSubtitle}>{section.subtitle}</Text>
          </Pressable>
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    padding: 20,
    paddingTop: 56,
    gap: 8,
  },
  greetingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  greetingCard: {
    flex: 1,
  },
  greeting: {
    fontSize: 23,
    fontFamily: 'Poppins_700Bold',
  },
  greetingSubtitle: {
    fontSize: 13,
    color: '#666',
    marginTop: 2,
  },
  streakBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    paddingHorizontal: 8,
  },
  streakText: {
    fontSize: 18,
    fontFamily: 'Poppins_700Bold',
    color: '#e2711d',
  },
  startLessonButton: {
    backgroundColor: '#5b4fe9',
    borderRadius: 999,
    paddingVertical: 13,
    alignItems: 'center',
  },
  startLessonText: {
    color: '#fff',
    fontSize: 16,
    fontFamily: 'Poppins_600SemiBold',
  },
  sessionCard: {
    borderRadius: 14,
    padding: 12,
    gap: 8,
  },
  sessionCardTitle: {
    fontSize: 14,
    fontFamily: 'Poppins_600SemiBold',
    color: '#1a3a5c',
  },
  sessionCardButtons: {
    flexDirection: 'row',
    gap: 8,
  },
  continueButton: {
    flex: 1,
    backgroundColor: '#5b4fe9',
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: 'center',
  },
  continueButtonText: {
    color: '#fff',
    fontFamily: 'Poppins_600SemiBold',
    fontSize: 13,
  },
  finishButton: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#ccc',
  },
  finishButtonText: {
    color: '#444',
    fontFamily: 'Poppins_600SemiBold',
    fontSize: 13,
  },
  progressTitle: {
    fontSize: 14,
    fontFamily: 'Poppins_600SemiBold',
    marginTop: 4,
  },
  statsRow: {
    flexDirection: 'row',
    gap: 8,
  },
  statCard: {
    flex: 1,
    backgroundColor: '#f5f5f5',
    borderRadius: 12,
    paddingVertical: 10,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 17,
    fontFamily: 'Poppins_700Bold',
  },
  statLabel: {
    fontSize: 10,
    color: '#666',
    marginTop: 1,
    textAlign: 'center',
  },
  cardsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  card: {
    width: '48%',
    backgroundColor: '#f5f5f5',
    borderRadius: 12,
    padding: 12,
    justifyContent: 'center',
    minHeight: 84,
  },
  cardTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  cardTitle: {
    fontSize: 15,
    fontFamily: 'Poppins_600SemiBold',
  },
  cardSubtitle: {
    fontSize: 11,
    color: '#666',
    marginTop: 2,
  },
});
