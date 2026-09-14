import { useAuth, useUser, useClerk } from '@clerk/expo';
import { useState } from 'react';
import * as Speech from 'expo-speech';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

type VocabCard = {
  id: string;
  kanji: string | null;
  reading: string;
  meaning: string;
  example_sentence: string | null;
};

export default function HomeScreen() {
  const { getToken } = useAuth();
  const { user } = useUser();
  const { signOut } = useClerk();

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [vocab, setVocab] = useState<VocabCard[]>([]);
  const [vocabLoading, setVocabLoading] = useState(false);
  const [vocabError, setVocabError] = useState<string | null>(null);

  const loadVocab = async () => {
    setVocabLoading(true);
    setVocabError(null);

    try {
      const response = await fetch(`${process.env.EXPO_PUBLIC_API_URL}/vocab?level=N5&limit=20`);
      const data = await response.json();

      if (!response.ok) {
        setVocabError(`${response.status}: ${JSON.stringify(data)}`);
      } else {
        setVocab(data.results);
      }
    } catch (err: any) {
      setVocabError(err?.message ?? 'Request failed');
    } finally {
      setVocabLoading(false);
    }
  };

  const speak = (word: VocabCard) => {
    Speech.speak(word.kanji ?? word.reading, { language: 'ja-JP' });
  };

  const testMeEndpoint = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const token = await getToken();

      const response = await fetch(`${process.env.EXPO_PUBLIC_API_URL}/me`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      const data = await response.json();

      if (!response.ok) {
        setError(`${response.status}: ${JSON.stringify(data)}`);
      } else {
        setResult(JSON.stringify(data, null, 2));
      }
    } catch (err: any) {
      setError(err?.message ?? 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Nihongo</Text>
      <Text style={styles.welcome}>
        Welcome, {user?.primaryEmailAddress?.emailAddress ?? user?.firstName ?? 'there'}!
      </Text>

      <Pressable style={styles.button} onPress={testMeEndpoint} disabled={loading}>
        {loading ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.buttonText}>Test GET /me</Text>
        )}
      </Pressable>

      {result && (
        <View style={styles.resultBox}>
          <Text style={styles.resultLabel}>✅ Success:</Text>
          <Text style={styles.resultText}>{result}</Text>
        </View>
      )}

      {error && (
        <View style={[styles.resultBox, styles.errorBox]}>
          <Text style={styles.resultLabel}>❌ Error:</Text>
          <Text style={styles.resultText}>{error}</Text>
        </View>
      )}

      <Pressable style={styles.button} onPress={loadVocab} disabled={vocabLoading}>
        {vocabLoading ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.buttonText}>Load N5 vocab</Text>
        )}
      </Pressable>

      {vocabError && (
        <View style={[styles.resultBox, styles.errorBox]}>
          <Text style={styles.resultLabel}>❌ Error:</Text>
          <Text style={styles.resultText}>{vocabError}</Text>
        </View>
      )}

      {vocab.map((word) => (
        <View key={word.id} style={styles.vocabRow}>
          <View style={styles.vocabText}>
            <Text style={styles.vocabWord}>{word.kanji ?? word.reading}</Text>
            <Text style={styles.vocabReading}>{word.reading}</Text>
            <Text style={styles.vocabMeaning}>{word.meaning}</Text>
          </View>
          <Pressable style={styles.speakerButton} onPress={() => speak(word)}>
            <Text style={styles.speakerIcon}>🔊</Text>
          </Pressable>
        </View>
      ))}

      <Pressable style={styles.signOutButton} onPress={() => signOut()}>
        <Text style={styles.signOutText}>Sign out</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    padding: 24,
    paddingTop: 80,
    gap: 16,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
  },
  welcome: {
    fontSize: 16,
    color: '#666',
    marginBottom: 16,
  },
  button: {
    backgroundColor: '#000',
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: 'center',
  },
  buttonText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 16,
  },
  vocabRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#f5f5f5',
    borderRadius: 8,
    padding: 12,
  },
  vocabText: {
    flex: 1,
  },
  vocabWord: {
    fontSize: 18,
    fontWeight: '600',
  },
  vocabReading: {
    fontSize: 14,
    color: '#666',
  },
  vocabMeaning: {
    fontSize: 14,
    color: '#333',
    marginTop: 2,
  },
  speakerButton: {
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  speakerIcon: {
    fontSize: 22,
  },
  resultBox: {
    backgroundColor: '#f0f9f0',
    borderRadius: 8,
    padding: 12,
    marginTop: 8,
  },
  errorBox: {
    backgroundColor: '#fdf0f0',
  },
  resultLabel: {
    fontWeight: '600',
    marginBottom: 4,
  },
  resultText: {
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' }),
    fontSize: 12,
  },
  signOutButton: {
    marginTop: 24,
    alignItems: 'center',
  },
  signOutText: {
    color: '#999',
    fontSize: 14,
  },
});
