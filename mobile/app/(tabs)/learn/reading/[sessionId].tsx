import { useAuth } from '@clerk/expo';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { PassageText } from '@/components/PassageText';
import { IconSymbol } from '@/components/ui/icon-symbol';
import { apiFetch } from '@/lib/api';
import type { ReadingSession } from '@/lib/types';

export default function ReadingSessionScreen() {
  const { sessionId } = useLocalSearchParams<{ sessionId: string }>();
  const { getToken } = useAuth();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ReadingSession | null>(null);

  const [localAnswers, setLocalAnswers] = useState<(string | null)[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [redoing, setRedoing] = useState(false);

  const [loadingReview, setLoadingReview] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  const lookedUpIds = useRef<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const session = await apiFetch(`/reading/${sessionId}`, token);
      setData(session);
      if (session.status === 'in_progress') {
        setLocalAnswers(new Array(session.questions.length).fill(null));
      }
    } catch (err: any) {
      setError(err?.message ?? "Couldn't load this reading.");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const selectAnswer = (questionIndex: number, option: string) => {
    setLocalAnswers((prev) => {
      const next = [...prev];
      next[questionIndex] = option;
      return next;
    });
  };

  const allAnswered = data ? localAnswers.every((a) => a !== null) : false;

  const submit = async () => {
    if (!data) return;
    setSubmitting(true);
    setError(null);
    try {
      const token = await getToken();
      // This one call also generates and saves the AI Detailed Feedback
      // server-side, so it's already on `data.review` when this
      // resolves -- no separate request or loading state needed for it.
      const result = await apiFetch(`/reading/${sessionId}/complete`, token, {
        method: 'POST',
        body: JSON.stringify({
          answers: localAnswers,
          looked_up_vocab_ids: Array.from(lookedUpIds.current),
        }),
      });
      setData({
        ...data,
        status: 'completed',
        answers: localAnswers,
        score: result.score,
        review: result.review,
      });
    } catch (err: any) {
      setError(err?.message ?? "Couldn't save your results.");
    } finally {
      setSubmitting(false);
    }
  };

  // Fallback only: normally submit() already saved a review. This
  // covers sessions completed before that existed, or a retry if the
  // saved review is the generic "try again" fallback text.
  const requestReview = async () => {
    if (!data) return;
    setLoadingReview(true);
    setReviewError(null);
    try {
      const token = await getToken();
      const result = await apiFetch(`/reading/${sessionId}/review`, token, { method: 'POST' });
      setData({ ...data, review: result.review });
    } catch (err: any) {
      setReviewError(err?.message ?? "Couldn't load feedback, try again.");
    } finally {
      setLoadingReview(false);
    }
  };

  const redo = async () => {
    if (!data) return;
    setRedoing(true);
    setError(null);
    try {
      const token = await getToken();
      const session = await apiFetch(`/reading/${sessionId}/redo`, token, { method: 'POST' });
      setData(session);
      setLocalAnswers(new Array(session.questions.length).fill(null));
      lookedUpIds.current = new Set();
    } catch (err: any) {
      setError(err?.message ?? "Couldn't restart the questions.");
    } finally {
      setRedoing(false);
    }
  };

  const exit = () => router.replace('/learn/reading');

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator />
      </View>
    );
  }

  if (error && !data) {
    return (
      <View style={styles.centered}>
        <Text style={styles.error}>{error}</Text>
        <Pressable style={styles.primaryButton} onPress={exit}>
          <Text style={styles.primaryButtonText}>Back to Reading</Text>
        </Pressable>
      </View>
    );
  }

  if (!data) return null;

  const answers = data.status === 'completed' ? data.answers ?? [] : localAnswers;
  const isCompleted = data.status === 'completed';

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Pressable style={styles.backButton} onPress={exit} hitSlop={8}>
          <IconSymbol name="chevron.left" size={22} color="#333" />
        </Pressable>
        <Text style={styles.title}>Reading</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={styles.body}>
        <PassageText
          passage={data.passage}
          segments={data.passage_furigana}
          onLookup={(id) => lookedUpIds.current.add(id)}
        />

        <Text style={styles.questionsTitle}>Comprehension</Text>
        {data.questions.map((q, qIndex) => (
          <View key={qIndex} style={styles.questionBlock}>
            <Text style={styles.questionNumber}>
              Question {qIndex + 1} of {data.questions.length}
            </Text>
            <Text style={styles.questionText}>{q.question}</Text>
            <View style={styles.options}>
              {q.options.map((option) => {
                const isSelected = answers[qIndex] === option;
                const isTheCorrectAnswer = option === q.correct_answer;
                const showGreen = isCompleted && isTheCorrectAnswer;
                const showRed = isCompleted && isSelected && !isTheCorrectAnswer;
                return (
                  <Pressable
                    key={option}
                    style={[
                      styles.optionButton,
                      isSelected && !isCompleted && styles.optionSelected,
                      showGreen && styles.optionCorrect,
                      showRed && styles.optionIncorrect,
                    ]}
                    onPress={() => selectAnswer(qIndex, option)}
                    disabled={isCompleted}>
                    <Text style={styles.optionText}>{option}</Text>
                  </Pressable>
                );
              })}
            </View>
          </View>
        ))}

        {isCompleted && (
          <>
            <View style={styles.scoreCard}>
              <Text style={styles.scoreText}>
                {data.score} / {data.questions.length} correct
              </Text>
            </View>

            {!data.review && (
              <Pressable style={styles.aiFeedbackButton} onPress={requestReview} disabled={loadingReview}>
                {loadingReview ? (
                  <ActivityIndicator color="#5b4fe9" />
                ) : (
                  <Text style={styles.aiFeedbackButtonText}>✨ AI Detailed Feedback</Text>
                )}
              </Pressable>
            )}
            {reviewError && <Text style={styles.error}>{reviewError}</Text>}
            {data.review && (
              <View style={styles.reviewCard}>
                <Text style={styles.reviewTitle}>AI Detailed Feedback</Text>
                <Text style={styles.reviewText}>{data.review}</Text>
              </View>
            )}
          </>
        )}
      </ScrollView>

      {!isCompleted ? (
        <>
          {!allAnswered && (
            <Text style={styles.answeredHint}>
              {localAnswers.filter((a) => a !== null).length} of {localAnswers.length} answered --
              scroll up to answer the rest
            </Text>
          )}
          {error && <Text style={styles.error}>{error}</Text>}
          <Pressable
            style={[styles.primaryButton, !allAnswered && styles.primaryButtonDisabled]}
            onPress={submit}
            disabled={!allAnswered || submitting}>
            {submitting ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryButtonText}>Submit</Text>}
          </Pressable>
        </>
      ) : (
        <View style={styles.completedButtonRow}>
          <Pressable style={styles.redoButton} onPress={redo} disabled={redoing}>
            {redoing ? <ActivityIndicator color="#5b4fe9" /> : <Text style={styles.redoButtonText}>Redo</Text>}
          </Pressable>
          <Pressable style={[styles.primaryButton, styles.doneButton]} onPress={exit}>
            <Text style={styles.primaryButtonText}>Done</Text>
          </Pressable>
        </View>
      )}
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
    padding: 24,
    gap: 16,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  backButton: {
    padding: 4,
  },
  title: {
    fontSize: 18,
    fontFamily: 'Poppins_700Bold',
  },
  body: {
    paddingTop: 16,
    paddingBottom: 24,
    gap: 8,
  },
  questionsTitle: {
    fontSize: 16,
    fontFamily: 'Poppins_700Bold',
    marginTop: 24,
    marginBottom: 4,
  },
  questionBlock: {
    marginTop: 16,
    gap: 10,
  },
  questionNumber: {
    fontSize: 11,
    color: '#999',
    textTransform: 'uppercase',
  },
  questionText: {
    fontSize: 15,
    fontFamily: 'Poppins_600SemiBold',
    color: '#333',
  },
  options: {
    gap: 8,
  },
  optionButton: {
    backgroundColor: '#f5f5f5',
    borderRadius: 10,
    paddingVertical: 14,
    paddingHorizontal: 14,
  },
  optionSelected: {
    backgroundColor: '#e6e2ff',
  },
  optionCorrect: {
    backgroundColor: '#c8e6c9',
  },
  optionIncorrect: {
    backgroundColor: '#ffcdd2',
  },
  optionText: {
    fontSize: 14,
    color: '#333',
  },
  scoreCard: {
    marginTop: 24,
    alignItems: 'center',
  },
  scoreText: {
    fontSize: 24,
    fontFamily: 'Poppins_700Bold',
    color: '#5b4fe9',
  },
  aiFeedbackButton: {
    backgroundColor: '#efecff',
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 20,
  },
  aiFeedbackButtonText: {
    color: '#5b4fe9',
    fontFamily: 'Poppins_600SemiBold',
    fontSize: 15,
  },
  reviewCard: {
    backgroundColor: '#f5f5f5',
    borderRadius: 12,
    padding: 16,
    marginTop: 20,
    gap: 8,
  },
  reviewTitle: {
    fontSize: 14,
    fontFamily: 'Poppins_700Bold',
    color: '#5b4fe9',
  },
  reviewText: {
    fontSize: 14,
    color: '#333',
    lineHeight: 20,
  },
  answeredHint: {
    fontSize: 12,
    color: '#999',
    textAlign: 'center',
    marginBottom: 8,
  },
  primaryButton: {
    backgroundColor: '#5b4fe9',
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    marginBottom: 16,
  },
  primaryButtonDisabled: {
    opacity: 0.4,
  },
  primaryButtonText: {
    color: '#fff',
    fontFamily: 'Poppins_600SemiBold',
    fontSize: 15,
  },
  completedButtonRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 16,
  },
  doneButton: {
    flex: 1,
    marginBottom: 0,
  },
  redoButton: {
    flex: 1,
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#5b4fe9',
  },
  redoButtonText: {
    color: '#5b4fe9',
    fontFamily: 'Poppins_600SemiBold',
    fontSize: 15,
  },
  error: {
    color: '#c0392b',
    textAlign: 'center',
  },
});
