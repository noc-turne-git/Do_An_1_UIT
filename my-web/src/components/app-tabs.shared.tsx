import { Children, useState, type ReactNode } from 'react';
import {
  Tabs,
  TabList,
  TabTrigger,
  TabSlot,
  TabTriggerSlotProps,
  TabListProps,
} from 'expo-router/ui';
import { Bell, Bookmark, Briefcase, Compass, MessageCircle, Search } from 'lucide-react-native';
import type { Href } from 'expo-router';
import { router } from 'expo-router';
import { Pressable, View, StyleSheet, Switch, TextInput, ScrollView } from 'react-native';

import { ThemedText } from './themed-text';
import { ThemedView } from './themed-view';

import { SymbolView } from 'expo-symbols';

const SIDEBAR_WIDTH = 54;
type Panel = 'chats' | 'notifications' | null;

export default function AppTabs() {
  const [openPanel, setOpenPanel] = useState<Panel>(null);
  const closePanel = () => setOpenPanel(null);

  return (
    <Tabs asChild>
      <View style={styles.app}>
        <TabList asChild>
          <Sidebar openPanel={openPanel} onPanelPress={(panel) => setOpenPanel((open) => open === panel ? null : panel)}>
            <TabTrigger name="trips" href={'/trips' as Href} asChild><NavButton openPanel={openPanel} closePanel={closePanel}>Trips</NavButton></TabTrigger>
            <TabTrigger name="explore" href="/explore" asChild><NavButton openPanel={openPanel} closePanel={closePanel}>Explore</NavButton></TabTrigger>
            <TabTrigger name="saved" href={'/saved' as Href} asChild><NavButton openPanel={openPanel} closePanel={closePanel}>Saved</NavButton></TabTrigger>
            <TabTrigger name="chats" href="/chats" asChild><View style={styles.hiddenTab} /></TabTrigger>
          </Sidebar>
        </TabList>
        <TabSlot style={styles.content} />
        {openPanel && (
          <ThemedView style={styles.panel}>
            {openPanel === 'chats' ? <ChatsPanel onNavigate={closePanel} /> : <NotificationsPanel />}
          </ThemedView>
        )}
      </View>
    </Tabs>
  );
}

function Sidebar({ children, openPanel, onPanelPress, ...props }: TabListProps & { openPanel: Panel; onPanelPress: (panel: 'chats' | 'notifications') => void }) {
  const tabItems = Children.toArray(children);
  return (
    <View {...props} style={styles.sidebar}>
      <View style={styles.brandMark}><Compass color="#111" size={19} /></View>
      <TooltipIcon label="Chats" active={openPanel === 'chats'} onPress={() => onPanelPress('chats')} accessibilityLabel="Chats">
        <MessageCircle color={openPanel === 'chats' ? '#fff' : '#111'} size={21} />
      </TooltipIcon>
      {tabItems[0]}
      <TooltipIcon label="Notification" active={openPanel === 'notifications'} onPress={() => onPanelPress('notifications')} accessibilityLabel="Notifications">
        <Bell color={openPanel === 'notifications' ? '#fff' : '#111'} size={21} />
      </TooltipIcon>
      {tabItems.slice(1)}
    </View>
  );
}

function NavButton({ children, isFocused, openPanel, closePanel, ...props }: TabTriggerSlotProps & { openPanel: Panel; closePanel: () => void }) {

  // console.log('========== NAV BUTTON ==========');
  // console.log('children:', children);
  // console.log('children type:', typeof children);
  // console.log('is Trips:', children === 'Trips');
  // console.log('is Explore:', children === 'Explore');


  const [hovered, setHovered] = useState(false);
  const selected = Boolean(isFocused && !openPanel);
  const isExplore = children === 'Explore';
  const Icon = children === 'Trips' ? Briefcase : isExplore ? Search : Bookmark;
  return (
    <Pressable {...props} onHoverIn={() => setHovered(true)} onHoverOut={() => setHovered(false)} onPress={(event) => { closePanel(); props.onPress?.(event); }} accessibilityRole="button" accessibilityLabel={String(children)} accessibilityState={{ selected }}>
      <View style={[styles.iconNavButton, selected && !isExplore && styles.activeIconButton]}>
        <Icon color={selected && !isExplore ? '#fff' : '#111'} size={21} strokeWidth={selected && isExplore ? 2.5 : 2} />
      </View>
      {selected && isExplore && <View style={styles.exploreIndicator} />}
      {hovered && <View pointerEvents="none" style={styles.tooltip}><ThemedText style={styles.tooltipText}>{String(children)}</ThemedText></View>}
    </Pressable>
  );
}

function TooltipIcon({ label, active, onPress, accessibilityLabel, children }: { label: string; active: boolean; onPress: () => void; accessibilityLabel: string; children: ReactNode }) {
  const [hovered, setHovered] = useState(false);
  return <Pressable onPress={onPress} onHoverIn={() => setHovered(true)} onHoverOut={() => setHovered(false)} accessibilityRole="button" accessibilityLabel={accessibilityLabel} accessibilityState={{ selected: active }}>
    <View style={[styles.iconNavButton, active && styles.activeIconButton]}>{children}</View>
    {hovered && <View pointerEvents="none" style={styles.tooltip}><ThemedText style={styles.tooltipText}>{label}</ThemedText></View>}
  </Pressable>;
}

function ChatsPanel({ onNavigate }: { onNavigate: () => void }) {
  const [search, setSearch] = useState('');
  const trips = [
    { id: 'dalat', name: 'Da Lat Adventure' },
    { id: 'kyoto', name: 'Kyoto in Spring' },
    { id: 'lisbon', name: 'Lisbon Long Weekend' },
  ];
  const chats = [
    { id: 'dalat', chatId: 'main', name: 'Da Lat trip planning', trip: 'Da Lat Adventure' },
    { id: 'kyoto', chatId: 'main', name: 'Kyoto planning', trip: 'Kyoto in Spring' },
  ].filter((chat) => `${chat.name} ${chat.trip}`.toLowerCase().includes(search.trim().toLowerCase()));
  const visibleTrips = trips.filter((trip) => trip.name.toLowerCase().includes(search.trim().toLowerCase()));
  return (
    <ScrollView style={styles.chatsScroll} contentContainerStyle={styles.chatsContent} keyboardShouldPersistTaps="handled">
      <View style={styles.searchBar}>
        <SymbolView name={{ ios: 'magnifyingglass', android: 'search', web: 'search' }} tintColor="#111" size={18} />
        <TextInput value={search} onChangeText={setSearch} placeholder="Search..." placeholderTextColor="#858585" accessibilityLabel="Search trips and chats" style={styles.searchInput} />
      </View>
      <View style={styles.actions}>
        <Pressable style={styles.actionRow} accessibilityRole="button" onPress={() => { onNavigate(); router.push('/chats'); }}><SymbolView name={{ ios: 'square.and.pencil', android: 'edit', web: 'edit' }} tintColor="#111" size={21} /><ThemedText style={styles.actionText}>New chat</ThemedText></Pressable>
        <Pressable style={styles.actionRow} accessibilityRole="button" onPress={() => { onNavigate(); router.push({ pathname: '/trips', params: { newTrip: '1' } }); }}><SymbolView name={{ ios: 'calendar.badge.plus', android: 'event', web: 'event' }} tintColor="#111" size={21} /><ThemedText style={styles.actionText}>New trip</ThemedText></Pressable>
      </View>
      <ThemedText style={styles.sectionLabel}>Trips</ThemedText>
      <View style={styles.list} accessibilityRole="list">
        {visibleTrips.map((trip) => <Pressable key={trip.id} onPress={() => { onNavigate(); router.push({ pathname: '/trips', params: { tripId: trip.id } }); }} style={styles.tripItem} accessibilityRole="button"><View style={styles.tripThumb}><SymbolView name={{ ios: 'mappin.and.ellipse', android: 'location_on', web: 'location_on' }} tintColor="#333" size={17} /></View><ThemedText style={styles.listText}>{trip.name}</ThemedText></Pressable>)}
      </View>
      <ThemedText style={[styles.sectionLabel, styles.chatsHeading]}>Chats</ThemedText>
      <View style={styles.chatList} accessibilityRole="list">
        {chats.map((chat) => <Pressable key={chat.name} onPress={() => { onNavigate(); router.push({ pathname: '/trips', params: { tripId: chat.id, chatId: chat.chatId } }); }} style={styles.chatItem} accessibilityRole="button"><ThemedText style={styles.listText}>{chat.name}</ThemedText><ThemedText style={styles.chatSubtitle}>{chat.trip}</ThemedText></Pressable>)}
      </View>
    </ScrollView>
  );
}

function NotificationsPanel() {
  const [unreadOnly, setUnreadOnly] = useState(false);
  return (
    <>
      <View style={styles.notificationHeader}>
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
        <ThemedText style={styles.description}>You’ll get alerts when you invite someone{ '\n' }to your trip or follow a Mindtrip Creator.</ThemedText>
        <Pressable style={styles.button} onPress={() => router.push('/explore')} accessibilityRole="button">
          <ThemedText style={styles.buttonText}>Get inspired</ThemedText>
        </Pressable>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  app: { flex: 1, flexDirection: 'row', position: 'relative' },
  hiddenTab: { display: 'none' },
  content: { flex: 1 },
  sidebar: {
    width: SIDEBAR_WIDTH,
    flexShrink: 0,
    height: '100%',
    alignItems: 'center',
    justifyContent: 'flex-start',
    paddingHorizontal: 7,
    paddingTop: 14,
    gap: 14,
    backgroundColor: 'rgba(255,255,255,0.9)',
    borderRightWidth: StyleSheet.hairlineWidth,
    borderRightColor: '#d8d8d8',
    zIndex: 2,
  },
  brandMark: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center', marginBottom: 26 },
  iconNavButton: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  tooltip: { position: 'absolute', left: 44, top: 5, zIndex: 20, backgroundColor: '#222', paddingHorizontal: 9, paddingVertical: 5, borderRadius: 6, elevation: 8, shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 5 },
  tooltipText: { color: '#fff', fontSize: 12, lineHeight: 16 },
  activeIconButton: { backgroundColor: '#111' },
  exploreIndicator: { position: 'absolute', right: -8, top: 2, width: 4, height: 30, borderRadius: 3, backgroundColor: '#111' },
  panel: {
    position: 'absolute',
    zIndex: 10,
    top: 0,
    bottom: 0,
    left: SIDEBAR_WIDTH,
    width: '35%',
    minWidth: 280,
    maxWidth: 420,
    paddingHorizontal: 24,
    paddingTop: 9,
    paddingBottom: 18,
    borderRightWidth: StyleSheet.hairlineWidth,
    borderRightColor: '#d8d8d8',
    shadowColor: '#000',
    shadowOpacity: 0.12,
    shadowRadius: 12,
    elevation: 8,
  },
  chatsScroll: { flex: 1 },
  chatsContent: { paddingBottom: 18 },
  searchBar: { height: 50, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, borderRadius: 26, backgroundColor: '#f1f1f1', marginBottom: 28 },
  searchInput: { flex: 1, height: '100%', padding: 0, color: '#111', fontSize: 16, outlineStyle: 'none' as never },
  actions: { gap: 4, marginBottom: 31 },
  actionRow: { minHeight: 47, flexDirection: 'row', alignItems: 'center', gap: 15 },
  actionText: { fontSize: 16, color: '#111' },
  sectionLabel: { marginBottom: 11, color: '#888', fontSize: 14 },
  chatsHeading: { marginTop: 26 },
  list: { minHeight: 12, gap: 5 },
  tripItem: { minHeight: 45, flexDirection: 'row', alignItems: 'center', gap: 11 },
  tripThumb: { width: 30, height: 30, alignItems: 'center', justifyContent: 'center', borderRadius: 8, backgroundColor: '#e7e9e9' },
  chatList: { gap: 5 },
  chatItem: { minHeight: 55, justifyContent: 'center', paddingVertical: 4 },
  listText: { color: '#171717', fontSize: 16 },
  chatSubtitle: { color: '#888', fontSize: 13 },
  notificationHeader: { minHeight: 64, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#eee' },
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
