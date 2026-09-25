import { useState } from 'react';
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SymbolView } from 'expo-symbols';

import { ThemedText } from '@/components/themed-text';
import { SharedChatInput } from '@/components/shared-chat-input';
import { EditChatNameModal, NewTripModal, type Trip } from './trips';

const tripCards = [
  { title: 'Trip to Da Lat', detail: 'Lam Dong Province · 4 days in Dec', tag: 'Trip', image: 'photo-1500530855697-b586d89ba3ee' },
  { title: 'nha trang', detail: '1 place', tag: 'Collection', image: 'photo-1555396273-367ea4eb4db5' },
  { title: 'Lich Trinh Nha Trang 2 Ngày', detail: '', tag: 'Chat', image: 'photo-1511818966892-d7d671e672a2' },
];

const places = [
  { title: 'Glow Beer Garden', category: 'Vietnamese', image: 'photo-1517248135467-4c7edcad34c4' },
  { title: 'Independence Palace', category: 'Attraction', image: 'photo-1565967511849-76a60a516170' },
  { title: 'Aroma Cocktail Bar', category: 'Cocktail Bar', image: 'photo-1514933651103-005eec06c04b' },
];

const inspiration = [
  { title: 'Explore Vietnam', image: 'photo-1528127269322-539801943592' },
  { title: 'A night in the city', image: 'photo-1519608487953-e999c86e7455' },
  { title: 'Places to unwind', image: 'photo-1441986300917-64674bd600d8' },
];

function ImageCard({ title, subtitle, tag, image }: { title: string; subtitle?: string; tag?: string; image: string }) {
  return (
    <Pressable accessibilityRole="button" style={styles.imageCard}>
      <Image source={{ uri: `https://images.unsplash.com/${image}?auto=format&fit=crop&w=720&q=80` }} style={styles.cardImage} contentFit="cover" />
      <View style={styles.cardShade} />
      {tag ? <ThemedText style={styles.cardTag}>{tag}</ThemedText> : null}
      <View style={styles.cardCaption}>
        <ThemedText numberOfLines={2} style={styles.cardTitle}>{title}</ThemedText>
        {subtitle ? <ThemedText numberOfLines={2} style={styles.cardSubtitle}>{subtitle}</ThemedText> : null}
      </View>
    </Pressable>
  );
}

export default function ChatsScreen() {
  const [prompt, setPrompt] = useState('');
  const [newMenuOpen, setNewMenuOpen] = useState(false);
  const [chatName, setChatName] = useState('New chat');
  const [renameDraft, setRenameDraft] = useState('New chat');
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [tripModalField, setTripModalField] = useState<'create' | 'where' | 'when' | 'who' | 'budget' | null>(null);
  const closeTripModal = () => setTripModalField(null);
  const handleTripCreate = (_trip: Trip) => closeTripModal();
  const saveChatName = () => {
    if (renameDraft.trim()) setChatName(renameDraft.trim());
    setRenameModalOpen(false);
  };

  return (
    <View style={styles.page}>
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Pressable accessibilityRole="button" accessibilityState={{ expanded: newMenuOpen }} onPress={() => setNewMenuOpen((open) => !open)} style={styles.newChatButton}>
            <ThemedText style={styles.headerText}>{chatName}</ThemedText>
            <SymbolView name={{ ios: 'chevron.down', android: 'keyboard_arrow_down', web: 'keyboard_arrow_down' }} tintColor="#111" size={14} />
          </Pressable>
          {newMenuOpen && <View style={styles.dropdown}><Pressable accessibilityRole="button" onPress={() => { setRenameDraft(chatName); setRenameModalOpen(true); setNewMenuOpen(false); }} style={styles.renameAction}><SymbolView name={{ ios: 'square.and.pencil', android: 'edit', web: 'edit' }} tintColor="#222" size={16} /><ThemedText style={styles.dropdownText}>Rename chat</ThemedText></Pressable></View>}
        </View>
        <View style={styles.planningPills}>{(['Where', 'When', 'Who', 'Budget'] as const).map((item) => <Pressable key={item} onPress={() => setTripModalField(item.toLowerCase() as 'where' | 'when' | 'who' | 'budget')} style={styles.planningPill}><ThemedText style={styles.planningText}>{item}</ThemedText></Pressable>)}</View>
        <Pressable accessibilityRole="button" onPress={() => setTripModalField('create')} style={styles.createTrip}><SymbolView name={{ ios: 'calendar.badge.plus', android: 'event', web: 'event' }} tintColor="#fff" size={17} /><ThemedText style={styles.createTripText}>Create a trip</ThemedText></Pressable>
      </View>
      <View style={styles.body}>
        <View style={styles.chatPane}>
          <View style={styles.welcome}>
            <View style={styles.welcomeArt}><SymbolView name={{ ios: 'sparkles', android: 'auto_awesome', web: 'auto_awesome' }} tintColor="#111" size={34} /><View style={styles.artDot}><SymbolView name={{ ios: 'location.fill', android: 'place', web: 'place' }} tintColor="#fff" size={13} /></View></View>
            <ThemedText style={styles.welcomeTitle}>Where to today, Lư?</ThemedText>
            <ThemedText style={styles.welcomeCopy}>Hey there, I’m here to assist you in planning your experience.{ '\n' }Ask me anything travel related.</ThemedText>
            <Pressable style={styles.updateAssistant}><SymbolView name={{ ios: 'waveform', android: 'graphic_eq', web: 'graphic_eq' }} tintColor="#222" size={16} /><ThemedText style={styles.updateText}>Update my assistant</ThemedText></Pressable>
          </View>
          <View style={styles.composerWrap}>
            <SharedChatInput value={prompt} onChangeText={setPrompt} accessibilityLabel="Ask anything else" />
            <ThemedText style={styles.disclaimer}>ⓘ Mindtrip can make mistakes. Check important info.</ThemedText>
          </View>
        </View>
        <ScrollView style={styles.discoverPane} contentContainerStyle={styles.discoverContent} showsVerticalScrollIndicator={false}>
          <View style={styles.discoverySection}><View style={styles.sectionHeading}><ThemedText style={styles.sectionTitle}>Jump back in</ThemedText></View><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.cardRow}>{tripCards.map((card) => <ImageCard key={card.title} {...card} />)}</ScrollView></View>
          <View style={styles.discoverySection}><View style={styles.sectionHeading}><ThemedText style={styles.sectionTitle}>For you in</ThemedText><SymbolView name={{ ios: 'mappin.and.ellipse', android: 'location_on', web: 'location_on' }} tintColor="#111" size={19} /><ThemedText style={styles.sectionTitle}>Ho Chi Minh City</ThemedText><Pressable style={styles.mapButton}><SymbolView name={{ ios: 'map', android: 'map', web: 'map' }} tintColor="#222" size={16} /><ThemedText style={styles.mapText}>Map</ThemedText></Pressable><Pressable onPress={() => router.push('/explore')} style={styles.seeAll}><ThemedText style={styles.seeAllText}>Explore</ThemedText></Pressable></View><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.cardRow}>{places.map((place) => <ImageCard key={place.title} {...place} />)}</ScrollView></View>
          <View style={styles.discoverySection}><View style={styles.sectionHeading}><ThemedText style={styles.sectionTitle}>Get inspired</ThemedText><Pressable style={styles.seeAll}><ThemedText style={styles.seeAllText}>See all</ThemedText></Pressable></View><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.cardRow}>{inspiration.map((card) => <ImageCard key={card.title} {...card} />)}</ScrollView></View>
        </ScrollView>
      </View>
      {tripModalField && <NewTripModal key={tripModalField} visible onClose={closeTripModal} onCreate={handleTripCreate} initialField={tripModalField === 'create' ? undefined : tripModalField} />}
      <EditChatNameModal visible={renameModalOpen} value={renameDraft} onChange={setRenameDraft} onClose={() => setRenameModalOpen(false)} onSave={saveChatName} />
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: '#fff' },
  header: { height: 60, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 24, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#eee', zIndex: 3 },
  headerLeft: { position: 'relative', zIndex: 4 },
  newChatButton: { flexDirection: 'row', alignItems: 'center', gap: 7, paddingVertical: 10, paddingHorizontal: 8 },
  headerText: { color: '#111', fontSize: 16, fontWeight: '600' },
  dropdown: { position: 'absolute', top: 42, left: 0, minWidth: 150, padding: 8, gap: 12, backgroundColor: '#fff', borderRadius: 10, shadowColor: '#000', shadowOpacity: 0.16, shadowRadius: 10, elevation: 8 },
  dropdownText: { padding: 8, color: '#222', fontSize: 14 },
  renameAction: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  planningPills: { position: 'absolute', left: '50%', flexDirection: 'row', transform: [{ translateX: -142 }], padding: 4, borderRadius: 24, borderWidth: 1, borderColor: '#e7e7e7' },
  planningPill: { paddingHorizontal: 13, paddingVertical: 7, borderRightWidth: StyleSheet.hairlineWidth, borderRightColor: '#eee' },
  planningText: { color: '#888', fontSize: 14 },
  createTrip: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 24, backgroundColor: '#050505' },
  createTripText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  body: { flex: 1, flexDirection: 'row', minHeight: 0 },
  chatPane: { width: '50%', position: 'relative', alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff' },
  welcome: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 28, paddingBottom: 90 },
  welcomeArt: { width: 120, height: 120, borderRadius: 60, backgroundColor: '#b8f2d8', alignItems: 'center', justifyContent: 'center', marginBottom: 23 },
  artDot: { position: 'absolute', top: 32, right: 31, width: 22, height: 22, borderRadius: 11, backgroundColor: '#f42d55', alignItems: 'center', justifyContent: 'center' },
  welcomeTitle: { color: '#111', fontSize: 36, fontWeight: '600', letterSpacing: -1, textAlign: 'center', marginBottom: 17 },
  welcomeCopy: { color: '#222', fontSize: 22, lineHeight: 32, textAlign: 'center' },
  updateAssistant: { flexDirection: 'row', alignItems: 'center', gap: 9, paddingHorizontal: 16, paddingVertical: 11, marginTop: 23, borderRadius: 24, backgroundColor: '#f1f1f1' },
  updateText: { color: '#222', fontSize: 15 },
  composerWrap: { position: 'absolute', left: 24, right: 24, bottom: 8 },
  disclaimer: { color: '#888', textAlign: 'center', fontSize: 13, marginTop: 8 },
  discoverPane: { width: '50%', flex: 1, marginTop: 0, backgroundColor: '#f8f8f8', borderTopLeftRadius: 22 },
  discoverContent: { paddingTop: 39, paddingBottom: 30 },
  discoverySection: { marginBottom: 35 },
  sectionHeading: { minHeight: 42, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 34, marginBottom: 14 },
  sectionTitle: { color: '#111', fontSize: 22, fontWeight: '600', letterSpacing: -0.3 },
  cardRow: { gap: 16, paddingHorizontal: 34, paddingRight: 34 },
  imageCard: { width: 272, height: 260, position: 'relative', overflow: 'hidden', borderRadius: 18, backgroundColor: '#ddd' },
  cardImage: { width: '100%', height: '100%' },
  cardShade: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.28)' },
  cardTag: { position: 'absolute', bottom: 71, left: 17, paddingHorizontal: 9, paddingVertical: 4, overflow: 'hidden', borderRadius: 10, color: '#fff', backgroundColor: 'rgba(70,70,70,0.8)', fontSize: 12, fontWeight: '600' },
  cardCaption: { position: 'absolute', left: 17, right: 14, bottom: 17 },
  cardTitle: { color: '#fff', fontSize: 17, lineHeight: 21, fontWeight: '700' },
  cardSubtitle: { color: '#f0f0f0', fontSize: 14, lineHeight: 19, marginTop: 2 },
  mapButton: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 13, paddingVertical: 8, borderWidth: 1, borderColor: '#ddd', borderRadius: 20 },
  mapText: { color: '#222', fontSize: 14 },
  seeAll: { marginLeft: 'auto', padding: 8 },
  seeAllText: { color: '#222', fontSize: 14 },
});
