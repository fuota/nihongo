import { useAuth } from '@clerk/expo';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { IconSymbol } from '@/components/ui/icon-symbol';
import { apiFetch } from '@/lib/api';

type Props = {
  contentType: 'vocab' | 'grammar';
  contentId: string;
  initialIsLearnt: boolean;
  size?: number;
};

const TOAST_DURATION_MS = 1500;

/**
 * Small icon-only Mark as Learnt toggle -- the Learnt-side counterpart
 * to DrillToggle, same shape and interaction (undoable tap, self-
 * dismissing toast). Gray = not learnt, green = learnt. Lets a list
 * row (e.g. the Vocab/Grammar word list) be marked without opening the
 * word's own detail screen.
 */
export function LearntToggle({ contentType, contentId, initialIsLearnt, size = 24 }: Props) {
  const { getToken } = useAuth();
  const [isLearnt, setIsLearnt] = useState(initialIsLearnt);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, []);

  const showToast = (message: string) => {
    setToast(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), TOAST_DURATION_MS);
  };

  const toggle = async () => {
    setBusy(true);
    const next = !isLearnt;
    try {
      const token = await getToken();
      await apiFetch('/learn', token, {
        method: next ? 'POST' : 'DELETE',
        body: JSON.stringify({ content_type: contentType, content_id: contentId }),
      });
      setIsLearnt(next);
      showToast(next ? 'Marked as Learnt' : 'Removed from Learnt');
    } catch {
      // leave the icon state as-is; user can just tap again
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.container}>
      <Pressable style={styles.button} onPress={toggle} disabled={busy}>
        {busy ? (
          <ActivityIndicator size="small" color="#bbb" />
        ) : (
          <IconSymbol
            name="checkmark.circle.fill"
            size={size}
            color={isLearnt ? '#2e7d32' : '#c4c4c4'}
          />
        )}
      </Pressable>
      {toast && (
        <View style={styles.toast}>
          <Text style={styles.toastText} numberOfLines={1}>
            {toast}
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'flex-end',
  },
  button: {
    padding: 6,
  },
  toast: {
    position: 'absolute',
    top: '100%',
    right: 0,
    width: 150,
    alignItems: 'center',
    backgroundColor: '#333',
    borderRadius: 6,
    paddingVertical: 4,
    paddingHorizontal: 8,
    marginTop: 2,
    zIndex: 10,
  },
  toastText: {
    color: '#fff',
    fontSize: 11,
  },
});
