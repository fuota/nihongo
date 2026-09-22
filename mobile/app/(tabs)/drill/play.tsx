import { useAuth } from '@clerk/expo';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { DrawingCanvas } from '@/components/DrawingCanvas';
import { IconSymbol } from '@/components/ui/icon-symbol';
import { apiFetch } from '@/lib/api';
import type { DrillQuestion } from '@/lib/types';

type Result = {
  content_type: string;
  content_id: string;
  is_correct: boolean;
  user_answer: string | null;
};

export default function DrillPlayScreen() {
  const { count } = useLocalSearchParams<{ count: string }>();
  const targetCount = Number(count) || 10;
  const { getToken } = useAuth();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [questions, setQuestions] = useState<DrillQuestion[]>([]);
  const [index, setIndex] = useState(0);
  const [results, setResults] = useState<Result[]>([]);

  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [answered, setAnswered] = useState(false);
  const [isCorrect, setIsCorrect] = useState<boolean | null>(null);
  const [writingFeedback, setWritingFeedback] = useState<string | null>(null);
  const [checkingDrawing, setCheckingDrawing] = useState(false);

  const [finishing, setFinishing] = useState(false);
  const [summary, setSummary] = useState<{
    session_id: string;
    correct_count: number;
    total: number;
  } | null>(null);

  const [review, setReview] = useState<string | null>(null);
  const [loadingReview, setLoadingReview] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const token = await getToken();
        const data = await apiFetch(`/review/due?limit=${targetCount}`, token);
        setQuestions(data.results);
      } catch (err: any) {
        setError(err?.message ?? "Couldn't load your Drill questions.");
      } finally {
        setLoading(false);
      }
    })();
  }, [targetCount]);

  const question = questions[index];

  const recordResult = (result: Result) => {
    setResults((prev) => [...prev, result]);
  };

  const selectOption = (option: string) => {
    if (answered || !question || question.content_type === 'writing') return;
    const correct = option === question.correct_answer;
    setSelectedOption(option);
    setIsCorrect(correct);
    setAnswered(true);
    recordResult({
      content_type: question.content_type,
      content_id: question.content_id,
      is_correct: correct,
      user_answer: option,
    });
  };

  const submitDrawing = async (base64Png: string) => {
    if (!question || question.content_type !== 'writing') return;
    setCheckingDrawing(true);
    try {
      const token = await getToken();
      const recognized = await apiFetch('/kanji/recognize', token, {
        method: 'POST',
        body: JSON.stringify({ image_base64: base64Png }),
      });
      const feedback = await apiFetch('/kanji/feedback', token, {
        method: 'POST',
        body: JSON.stringify({
          character_id: question.content_id,
          recognized_character: recognized.character,
          confidence: recognized.confidence,
          mode: 'drill',
        }),
      });
      setWritingFeedback(feedback.feedback);
      setIsCorrect(feedback.is_correct);
      setAnswered(true);
      recordResult({
        content_type: 'writing',
        content_id: question.content_id,
        is_correct: feedback.is_correct,
        user_answer: recognized.character,
      });
    } catch (err: any) {
      setError(err?.message ?? "Couldn't check your drawing, try again.");
    } finally {
      setCheckingDrawing(false);
    }
  };

  const next = async () => {
    setSelectedOption(null);
    setAnswered(false);
    setIsCorrect(null);
    setWritingFeedback(null);

    if (index + 1 < questions.length) {
      setIndex(index + 1);
      return;
    }

    setFinishing(true);
    try {
      const token = await getToken();
      const data = await apiFetch('/drill/complete', token, {
        method: 'POST',
        body: JSON.stringify({ results }),
      });
      setSummary({ session_id: data.session_id, correct_count: data.correct_count, total: data.total });
    } catch (err: any) {
      setError(err?.message ?? "Couldn't save your results.");
    } finally {
      setFinishing(false);
    }
  };

  const requestReview = async () => {
    if (!summary) return;
    setLoadingReview(true);
    setReviewError(null);
    try {
      const token = await getToken();
      const data = await apiFetch(`/drill/${summary.session_id}/review`, token, { method: 'POST' });
      setReview(data.review);
    } catch (err: any) {
      setReviewError(err?.message ?? "Couldn't load feedback, try again.");
    } finally {
      setLoadingReview(false);
    }
  };

  const exit = () => router.replace('/drill');

  const questionPrompt = (q: DrillQuestion): string => {
    if (q.content_type === 'vocab') return q.prompt;
    if (q.content_type === 'grammar') return q.drill_sentence;
    return q.character;
  };

  const questionCorrectAnswer = (q: DrillQuestion): string => {
    if (q.content_type === 'writing') return q.character;
    return q.correct_answer;
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator />
      </View>
    );
  }

  if (error && !summary) {
    return (
      <View style={styles.centered}>
        <Text style={styles.error}>{error}</Text>
        <Pressable style={styles.doneButton} onPress={exit}>
          <Text style={styles.doneButtonText}>Back to Drill</Text>
        </Pressable>
      </View>
    );
  }

  if (summary) {
    return (
      <View style={styles.container}>
        <ScrollView contentContainerStyle={styles.summaryBody}>
          <Text style={styles.summaryTitle}>
            {summary.correct_count} / {summary.total}
          </Text>
          <Text style={styles.summarySubtitle}>correct</Text>

          <View style={styles.resultsList}>
            {questions.map((q, i) => {
              const result = results[i];
              if (!result) return null;
              return (
                <View key={i} style={styles.resultRow}>
                  <Text style={result.is_correct ? styles.resultMarkCorrect : styles.resultMarkIncorrect}>
                    {result.is_correct ? '✓' : '✗'}
                  </Text>
                  <View style={styles.resultTextBlock}>
                    <Text style={styles.resultPrompt} numberOfLines={1}>
                      {questionPrompt(q)}
                    </Text>
                    {!result.is_correct && (
                      <Text style={styles.resultAnswers} numberOfLines={1}>
                        You said: {result.user_answer ?? '--'}  ·  Correct: {questionCorrectAnswer(q)}
                      </Text>
                    )}
                  </View>
                </View>
              );
            })}
          </View>

          {!review && (
            <Pressable style={styles.aiFeedbackButton} onPress={requestReview} disabled={loadingReview}>
              {loadingReview ? (
                <ActivityIndicator color="#5b4fe9" />
              ) : (
                <Text style={styles.aiFeedbackButtonText}>✨ AI Detailed Feedback</Text>
              )}
            </Pressable>
          )}
          {reviewError && <Text style={styles.error}>{reviewError}</Text>}
          {review && (
            <View style={styles.reviewCard}>
              <Text style={styles.reviewTitle}>AI Detailed Feedback</Text>
              <Text style={styles.reviewText}>{review}</Text>
            </View>
          )}
        </ScrollView>

        <Pressable style={styles.doneButton} onPress={() => router.replace('/drill')}>
          <Text style={styles.doneButtonText}>Done</Text>
        </Pressable>
      </View>
    );
  }

  if (questions.length === 0) {
    return (
      <View style={styles.centered}>
        <Text style={styles.emptyText}>
          Nothing in Drill yet! Add some words, grammar, or kanji to Drill first.
        </Text>
        <Pressable style={styles.doneButton} onPress={exit}>
          <Text style={styles.doneButtonText}>Back to Drill</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <Pressable style={styles.backButton} onPress={exit} hitSlop={8}>
          <IconSymbol name="chevron.left" size={22} color="#333" />
        </Pressable>
        <Text style={styles.counter}>
          {index + 1} / {questions.length}
        </Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={styles.body}>
        {question.content_type === 'vocab' && (
          <>
            <Text style={styles.instruction}>
              {question.question_kind === 'reading' ? "What's the reading?" : 'What does this mean?'}
            </Text>
            <Text style={styles.prompt}>{question.prompt}</Text>
            <View style={styles.options}>
              {question.options.map((option) => {
                const isSelected = option === selectedOption;
                const isTheCorrectAnswer = option === question.correct_answer;
                const showGreen = answered && isTheCorrectAnswer;
                const showRed = answered && isSelected && !isTheCorrectAnswer;
                return (
                  <Pressable
                    key={option}
                    style={[
                      styles.optionButton,
                      showGreen && styles.optionCorrect,
                      showRed && styles.optionIncorrect,
                    ]}
                    onPress={() => selectOption(option)}
                    disabled={answered}>
                    <Text style={styles.optionText}>{option}</Text>
                  </Pressable>
                );
              })}
            </View>
          </>
        )}

        {question.content_type === 'grammar' && (
          <>
            <Text style={styles.instruction}>Which pattern completes this sentence?</Text>
            <Text style={styles.prompt}>{question.drill_sentence}</Text>
            <View style={styles.options}>
              {question.options.map((option) => {
                const isSelected = option === selectedOption;
                const isTheCorrectAnswer = option === question.correct_answer;
                const showGreen = answered && isTheCorrectAnswer;
                const showRed = answered && isSelected && !isTheCorrectAnswer;
                return (
                  <Pressable
                    key={option}
                    style={[
                      styles.optionButton,
                      showGreen && styles.optionCorrect,
                      showRed && styles.optionIncorrect,
                    ]}
                    onPress={() => selectOption(option)}
                    disabled={answered}>
                    <Text style={styles.optionText}>{option}</Text>
                  </Pressable>
                );
              })}
            </View>
          </>
        )}

        {question.content_type === 'writing' && (
          <>
            <Text style={styles.instruction}>Draw this character</Text>
            <Text style={styles.prompt}>
              {question.meaning}
              {question.romaji ? ` (${question.romaji})` : ''}
            </Text>
            <DrawingCanvas
              key={index}
              size={250}
              onSubmit={submitDrawing}
              submitting={checkingDrawing}
              showControls={!answered}
            />
            {answered && (
              <View style={styles.writingResult}>
                <Text style={isCorrect ? styles.optionCorrectText : styles.optionIncorrectText}>
                  {isCorrect ? 'Correct!' : `Incorrect -- it was ${question.character}`}
                </Text>
                {writingFeedback && <Text style={styles.feedbackText}>{writingFeedback}</Text>}
              </View>
            )}
          </>
        )}
      </ScrollView>

      {answered && (
        <Pressable style={styles.nextButton} onPress={next} disabled={finishing}>
          {finishing ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.nextButtonText}>
              {index + 1 < questions.length ? 'Next' : 'Finish'}
            </Text>
          )}
        </Pressable>
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
  counter: {
    fontSize: 14,
    color: '#999',
    fontFamily: 'Poppins_600SemiBold',
  },
  body: {
    paddingTop: 24,
    paddingBottom: 24,
    gap: 12,
    alignItems: 'center',
  },
  instruction: {
    fontSize: 14,
    color: '#999',
  },
  prompt: {
    fontSize: 32,
    fontFamily: 'Poppins_700Bold',
    textAlign: 'center',
    marginBottom: 12,
  },
  options: {
    width: '100%',
    gap: 10,
  },
  optionButton: {
    backgroundColor: '#f5f5f5',
    borderRadius: 10,
    paddingVertical: 16,
    alignItems: 'center',
  },
  optionCorrect: {
    backgroundColor: '#c8e6c9',
  },
  optionIncorrect: {
    backgroundColor: '#ffcdd2',
  },
  optionText: {
    fontSize: 16,
    fontFamily: 'Poppins_600SemiBold',
    color: '#333',
  },
  optionCorrectText: {
    fontSize: 17,
    fontFamily: 'Poppins_600SemiBold',
    color: '#2e7d32',
  },
  optionIncorrectText: {
    fontSize: 17,
    fontFamily: 'Poppins_600SemiBold',
    color: '#c0392b',
  },
  writingResult: {
    alignItems: 'center',
    gap: 6,
    marginTop: 4,
  },
  feedbackText: {
    fontSize: 13,
    color: '#333',
    textAlign: 'center',
    lineHeight: 18,
    paddingHorizontal: 12,
  },
  nextButton: {
    backgroundColor: '#5b4fe9',
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    marginBottom: 16,
  },
  nextButtonText: {
    color: '#fff',
    fontFamily: 'Poppins_600SemiBold',
    fontSize: 15,
  },
  error: {
    color: '#c0392b',
    textAlign: 'center',
  },
  emptyText: {
    fontSize: 15,
    color: '#666',
    textAlign: 'center',
  },
  summaryBody: {
    paddingTop: 60,
    paddingHorizontal: 24,
    paddingBottom: 24,
    alignItems: 'center',
  },
  summaryTitle: {
    fontSize: 48,
    fontFamily: 'Poppins_700Bold',
  },
  summarySubtitle: {
    fontSize: 16,
    color: '#666',
    marginBottom: 20,
  },
  resultsList: {
    width: '100%',
    gap: 4,
  },
  resultRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  resultMarkCorrect: {
    fontSize: 16,
    fontFamily: 'Poppins_700Bold',
    color: '#2e7d32',
    width: 18,
  },
  resultMarkIncorrect: {
    fontSize: 16,
    fontFamily: 'Poppins_700Bold',
    color: '#c0392b',
    width: 18,
  },
  resultTextBlock: {
    flex: 1,
    gap: 2,
  },
  resultPrompt: {
    fontSize: 15,
    fontFamily: 'Poppins_600SemiBold',
    color: '#333',
  },
  resultAnswers: {
    fontSize: 12,
    color: '#999',
  },
  aiFeedbackButton: {
    backgroundColor: '#efecff',
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    width: '100%',
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
    width: '100%',
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
  doneButton: {
    backgroundColor: '#5b4fe9',
    borderRadius: 999,
    paddingVertical: 14,
    paddingHorizontal: 32,
    alignSelf: 'center',
    marginBottom: 16,
  },
  doneButtonText: {
    color: '#fff',
    fontFamily: 'Poppins_600SemiBold',
    fontSize: 15,
  },
});
