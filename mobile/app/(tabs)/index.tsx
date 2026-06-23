import { useAuth, useUser, useClerk } from '@clerk/expo';
import { useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

export default function HomeScreen() {
  const { getToken } = useAuth();
  const { user } = useUser();
  const { signOut } = useClerk();

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
