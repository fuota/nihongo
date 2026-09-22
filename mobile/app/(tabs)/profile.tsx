import { useAuth, useClerk, useUser } from '@clerk/expo';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { AnimalAvatar, AVATAR_CHOICES } from '@/components/AnimalAvatar';
import { apiFetch } from '@/lib/api';

const MIN_ITEMS = 5;
const MAX_ITEMS = 15;

type MeData = {
  name: string | null;
  avatar: string;
  email: string | null;
  jlpt_level: string;
  created_at: string;
  session_item_count: number;
};

function formatMemberSince(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
}

export default function ProfileScreen() {
  const { signOut } = useClerk();
  const { getToken } = useAuth();
  // Clerk's session token doesn't carry an email claim by default, so
  // our own backend's User.email column is never reliably populated --
  // this reads the real, live email straight from Clerk on-device
  // instead of trusting that copy.
  const { user: clerkUser } = useUser();
  const email = clerkUser?.primaryEmailAddress?.emailAddress ?? null;

  const [me, setMe] = useState<MeData | null>(null);
  const [avatarPickerVisible, setAvatarPickerVisible] = useState(false);
  const [renameVisible, setRenameVisible] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [settingsVisible, setSettingsVisible] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const token = await getToken();
      const data = await apiFetch('/me', token);
      setMe(data);

      // Backfill the backend's copy once we know the real value --
      // Clerk's session token carries no email claim, so the backend
      // can never learn it on its own. Fire-and-forget, non-blocking.
      if (email && data.email !== email) {
        apiFetch('/me', token, { method: 'PATCH', body: JSON.stringify({ email }) }).catch(() => {});
      }
    } catch {
      // profile is a nice-to-have render; fail quietly
    }
  }, [email]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const chooseAvatar = async (avatar: string) => {
    if (!me) return;
    setAvatarPickerVisible(false);
    setMe({ ...me, avatar });
    try {
      const token = await getToken();
      await apiFetch('/me', token, { method: 'PATCH', body: JSON.stringify({ avatar }) });
    } catch {
      load(); // resync if the save failed
    }
  };

  const openRename = () => {
    setNameDraft(me?.name ?? '');
    setRenameVisible(true);
  };

  const saveName = async () => {
    const trimmed = nameDraft.trim();
    if (!trimmed || !me) return;
    setSaving(true);
    try {
      const token = await getToken();
      await apiFetch('/me', token, { method: 'PATCH', body: JSON.stringify({ name: trimmed }) });
      setMe({ ...me, name: trimmed });
      setRenameVisible(false);
    } catch {
      // keep the modal open so the user can retry
    } finally {
      setSaving(false);
    }
  };

  const changeCount = async (delta: number) => {
    if (!me) return;
    const next = Math.min(MAX_ITEMS, Math.max(MIN_ITEMS, me.session_item_count + delta));
    if (next === me.session_item_count) return;

    setMe({ ...me, session_item_count: next });
    try {
      const token = await getToken();
      await apiFetch('/me', token, { method: 'PATCH', body: JSON.stringify({ session_item_count: next }) });
    } catch {
      load();
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Your Profile</Text>
        <Pressable onPress={() => setSettingsVisible(true)} hitSlop={8}>
          <MaterialIcons name="settings" size={26} color="#fff" />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.body}>
        <Pressable style={styles.avatarWrap} onPress={() => setAvatarPickerVisible(true)}>
          <AnimalAvatar avatar={me?.avatar ?? 'cat'} size={104} />
          <View style={styles.avatarEditBadge}>
            <MaterialIcons name="edit" size={14} color="#fff" />
          </View>
        </Pressable>

        <Pressable style={styles.nameRow} onPress={openRename}>
          <Text style={styles.name}>{me?.name ?? '...'}</Text>
          <MaterialIcons name="edit" size={16} color="#5b4fe9" />
        </Pressable>

        <View style={styles.infoCard}>
          <MaterialIcons name="email" size={20} color="#5b4fe9" />
          <View style={styles.infoTextBlock}>
            <Text style={styles.infoLabel}>Email</Text>
            <Text style={styles.infoValue}>{email ?? '--'}</Text>
          </View>
        </View>

        <View style={styles.infoCard}>
          <MaterialIcons name="school" size={20} color="#5b4fe9" />
          <View style={styles.infoTextBlock}>
            <Text style={styles.infoLabel}>JLPT Level</Text>
            <Text style={styles.infoValue}>{me?.jlpt_level ?? '--'}</Text>
          </View>
        </View>

        <View style={styles.infoCard}>
          <MaterialIcons name="calendar-today" size={20} color="#5b4fe9" />
          <View style={styles.infoTextBlock}>
            <Text style={styles.infoLabel}>Member since</Text>
            <Text style={styles.infoValue}>{me ? formatMemberSince(me.created_at) : '--'}</Text>
          </View>
        </View>

        <Pressable style={styles.signOutButton} onPress={() => signOut()}>
          <Text style={styles.signOutText}>Sign out</Text>
        </Pressable>
      </ScrollView>

      <Modal visible={avatarPickerVisible} transparent animationType="fade">
        <Pressable style={styles.modalBackdrop} onPress={() => setAvatarPickerVisible(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>Change Avatar</Text>
            <View style={styles.avatarGrid}>
              {AVATAR_CHOICES.map((choice) => (
                <Pressable key={choice} onPress={() => chooseAvatar(choice)} style={styles.avatarOption}>
                  <AnimalAvatar
                    avatar={choice}
                    size={64}
                    backgroundColor={choice === me?.avatar ? '#5b4fe9' : '#c9c3f7'}
                  />
                </Pressable>
              ))}
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      <Modal visible={renameVisible} transparent animationType="fade">
        <Pressable style={styles.modalBackdrop} onPress={() => setRenameVisible(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>Change name</Text>
            <TextInput
              style={styles.renameInput}
              value={nameDraft}
              onChangeText={setNameDraft}
              placeholder="Your name"
              autoFocus
              maxLength={40}
              returnKeyType="done"
              onSubmitEditing={saveName}
            />
            <Pressable
              style={[styles.saveButton, !nameDraft.trim() && styles.saveButtonDisabled]}
              onPress={saveName}
              disabled={!nameDraft.trim() || saving}>
              {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveButtonText}>Save</Text>}
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>

      <Modal visible={settingsVisible} transparent animationType="fade">
        <Pressable style={styles.modalBackdrop} onPress={() => setSettingsVisible(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>Settings</Text>
            <Text style={styles.settingLabel}>Items per Learning Session</Text>
            <View style={styles.stepperRow}>
              <Pressable
                style={styles.stepperButton}
                onPress={() => changeCount(-1)}
                disabled={!me || me.session_item_count <= MIN_ITEMS}>
                <Text style={styles.stepperButtonText}>−</Text>
              </Pressable>
              <Text style={styles.stepperValue}>{me?.session_item_count ?? '--'}</Text>
              <Pressable
                style={styles.stepperButton}
                onPress={() => changeCount(1)}
                disabled={!me || me.session_item_count >= MAX_ITEMS}>
                <Text style={styles.stepperButtonText}>+</Text>
              </Pressable>
            </View>
            <Text style={styles.settingHint}>
              {MIN_ITEMS}-{MAX_ITEMS} items per For You session
            </Text>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#5b4fe9',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 64,
    paddingHorizontal: 24,
    paddingBottom: 16,
  },
  headerTitle: {
    color: '#fff',
    fontSize: 24,
    fontFamily: 'Poppins_700Bold',
  },
  body: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    alignItems: 'center',
    paddingTop: 24,
    paddingHorizontal: 24,
    paddingBottom: 40,
    flexGrow: 1,
  },
  avatarWrap: {
    marginTop: 8,
  },
  avatarEditBadge: {
    position: 'absolute',
    bottom: 2,
    right: 2,
    backgroundColor: '#5b4fe9',
    borderRadius: 12,
    width: 24,
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: '#fff',
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 16,
  },
  name: {
    fontSize: 22,
    fontFamily: 'Poppins_700Bold',
    color: '#5b4fe9',
  },
  infoCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#f5f5f5',
    borderRadius: 12,
    padding: 14,
    width: '100%',
    marginTop: 14,
  },
  infoTextBlock: {
    flex: 1,
  },
  infoLabel: {
    fontSize: 12,
    color: '#999',
  },
  infoValue: {
    fontSize: 15,
    fontFamily: 'Poppins_600SemiBold',
    marginTop: 1,
  },
  signOutButton: {
    marginTop: 28,
    alignItems: 'center',
  },
  signOutText: {
    color: '#999',
    fontSize: 14,
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  modalCard: {
    backgroundColor: '#fff',
    borderRadius: 20,
    padding: 24,
    width: '100%',
    gap: 8,
  },
  modalTitle: {
    fontSize: 17,
    fontFamily: 'Poppins_700Bold',
    textAlign: 'center',
    marginBottom: 12,
  },
  avatarGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: 14,
  },
  avatarOption: {
    borderRadius: 999,
  },
  renameInput: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 10,
    paddingVertical: 12,
    paddingHorizontal: 14,
    fontSize: 16,
    textAlign: 'center',
  },
  saveButton: {
    backgroundColor: '#5b4fe9',
    borderRadius: 999,
    paddingVertical: 13,
    alignItems: 'center',
    marginTop: 8,
  },
  saveButtonDisabled: {
    opacity: 0.4,
  },
  saveButtonText: {
    color: '#fff',
    fontFamily: 'Poppins_600SemiBold',
    fontSize: 15,
  },
  settingLabel: {
    fontSize: 14,
    fontFamily: 'Poppins_600SemiBold',
    textAlign: 'center',
    marginTop: 4,
  },
  stepperRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 10,
    gap: 4,
  },
  stepperButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#e5e5e5',
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepperButtonText: {
    fontSize: 20,
    fontFamily: 'Poppins_600SemiBold',
  },
  stepperValue: {
    width: 48,
    textAlign: 'center',
    fontSize: 18,
    fontFamily: 'Poppins_600SemiBold',
  },
  settingHint: {
    fontSize: 12,
    color: '#999',
    marginTop: 8,
    textAlign: 'center',
  },
});
