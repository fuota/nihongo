import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

const COUNT_OPTIONS = [5, 10, 15, 20] as const;

export default function DrillHome() {
  const [count, setCount] = useState<number>(10);

  const play = () => {
    router.push({ pathname: '/drill/play', params: { count: String(count) } });
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Drill</Text>
      <Text style={styles.subtitle}>
        Review the vocab, grammar, and writing items you've added to Drill.
      </Text>

      <Text style={styles.pickerLabel}>How many questions?</Text>
      <View style={styles.countRow}>
        {COUNT_OPTIONS.map((option) => (
          <Pressable
            key={option}
            style={[styles.countPill, count === option && styles.countPillActive]}
            onPress={() => setCount(option)}>
            <Text style={[styles.countPillText, count === option && styles.countPillTextActive]}>
              {option}
            </Text>
          </Pressable>
        ))}
      </View>

      <Pressable style={styles.playButton} onPress={play}>
        <Text style={styles.playButtonText}>Play</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 24,
    paddingTop: 80,
    gap: 8,
  },
  title: {
    fontSize: 28,
    fontFamily: 'Poppins_700Bold',
  },
  subtitle: {
    fontSize: 15,
    color: '#666',
  },
  pickerLabel: {
    fontSize: 15,
    fontFamily: 'Poppins_600SemiBold',
    marginTop: 32,
  },
  countRow: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 12,
  },
  countPill: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 10,
    backgroundColor: '#f5f5f5',
    alignItems: 'center',
  },
  countPillActive: {
    backgroundColor: '#5b4fe9',
  },
  countPillText: {
    fontSize: 16,
    fontFamily: 'Poppins_600SemiBold',
    color: '#333',
  },
  countPillTextActive: {
    color: '#fff',
  },
  playButton: {
    backgroundColor: '#5b4fe9',
    borderRadius: 999,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 32,
  },
  playButtonText: {
    color: '#fff',
    fontSize: 17,
    fontFamily: 'Poppins_600SemiBold',
  },
});
