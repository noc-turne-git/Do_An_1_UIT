import { useState } from 'react';
import { router } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { Pressable, StyleSheet, Switch, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';

export default function NotificationsScreen() {
  const [unreadOnly, setUnreadOnly] = useState(false);

  return (
    <View style={styles.screen}>
      <View style={styles.panel}>
        <View style={styles.header}>
          <View style={styles.titleContainer}>
            <ThemedText style={styles.title}>Notifications</ThemedText>
            <ThemedText style={styles.count}>0</ThemedText>
          </View>
          <View style={styles.headerActions}>
            <ThemedText style={styles.unreadText}>Unread</ThemedText>
            <Switch value={unreadOnly} onValueChange={setUnreadOnly} accessibilityLabel="Show unread notifications only" />
            <Pressable style={styles.moreButton} accessibilityRole="button" accessibilityLabel="More notification options">
              <SymbolView name={{ ios: 'ellipsis', android: 'more_horiz', web: 'more_horiz' }} size={20} tintColor="#333" />
            </Pressable>
          </View>
        </View>

        <View style={styles.emptyState}>
          <View style={styles.iconCircle}>
            <SymbolView name={{ ios: 'bell', android: 'notifications', web: 'notifications' }} size={32} tintColor="#fff" />
            <View style={styles.notificationDot} />
          </View>
          <ThemedText style={styles.emptyTitle}>No notifications yet. Let’s fix that.</ThemedText>
          <ThemedText style={styles.description}>
            You’ll get alerts when you invite someone{'\n'}to your trip or follow a Mindtrip Creator.
          </ThemedText>
          <Pressable style={styles.button} onPress={() => router.push('/explore')} accessibilityRole="button">
            <ThemedText style={styles.buttonText}>Get inspired</ThemedText>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#fff' },
  panel: {
    flex: 0,
    width: '35%',
    minWidth: 280,
    maxWidth: 420,
    height: '100%',
    padding: 20,
    backgroundColor: '#fff',
  },
  header: { minHeight: 64, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#eee' },
  titleContainer: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: 16, fontWeight: '600', color: '#111' },
  count: { fontSize: 13, color: '#888' },
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  unreadText: { fontSize: 13, fontWeight: '500', color: '#111' },
  moreButton: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center', borderRadius: 18 },
  emptyState: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24, paddingBottom: 40 },
  iconCircle: { width: 84, height: 84, borderRadius: 42, backgroundColor: '#ff8a65', alignItems: 'center', justifyContent: 'center', marginBottom: 28 },
  notificationDot: { position: 'absolute', top: 23, right: 24, width: 10, height: 10, borderRadius: 5, backgroundColor: '#e60000', borderWidth: 1, borderColor: '#ff8a65' },
  emptyTitle: { fontSize: 18, fontWeight: '700', color: '#111', textAlign: 'center', marginBottom: 12 },
  description: { fontSize: 15, lineHeight: 22, color: '#444', textAlign: 'center', marginBottom: 24 },
  button: { backgroundColor: '#000', paddingHorizontal: 28, paddingVertical: 14, borderRadius: 28 },
  buttonText: { color: '#fff', fontSize: 15, fontWeight: '600' },
});
