import { useAuth } from '@clerk/expo';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { IconSymbol } from '@/components/ui/icon-symbol';
import { apiFetch } from '@/lib/api';

type Props = {
  contentType: 'vocab' | 'grammar' | 'writing';
  contentId: string;
  initialInDrill: boolean;
  size?: number;
};

const TOAST_DURATION_MS = 1500;

/**
 * Small icon-only Add to Drill toggle, reused everywhere the app lets
 * a user add/remove an item from Drill (word detail, grammar pattern
 * detail, writing practice, Learning Session cards). Gray = not in
 * Drill, yellow (matching the tab bar's Drill icon) = in Drill.
 * Tapping toggles either way and shows a small self-dismissing prompt,
 * since this is meant to be undoable for an accidental tap.
 */
export function DrillToggle({ contentType, contentId, initialInDrill, size = 24 }: Props) {
  const { getToken } = useAuth();
  const [inDrill, setInDrill] = useState(initialInDrill);
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
    const next = !inDrill;
    try {
      const token = await getToken();
      await apiFetch('/drill/add', token, {
        method: next ? 'POST' : 'DELETE',
        body: JSON.stringify({ content_type: contentType, content_id: contentId }),
      });
      setInDrill(next);
      showToast(next ? 'Added to Drill' : 'Removed from Drill');
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
          <IconSymbol name="bolt.fill" size={size} color={inDrill ? '#f5b800' : '#c4c4c4'} />
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
