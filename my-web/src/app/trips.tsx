import { useEffect, useState } from 'react';
import { Image } from 'expo-image';
import { router, useLocalSearchParams } from 'expo-router';
import { Alert, Modal, Platform, Pressable, ScrollView, Share, StyleSheet, TextInput, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { SharedChatInput } from '@/components/shared-chat-input';
import { useTheme } from '@/hooks/use-theme';
import { Luggage } from 'lucide-react';

export type Trip = {
  id: string;
  name: string;
  destination: string;
  duration: string;
  when: string;
  budget: string;
  cover: string;
  travelers: string[];
  chats: { id: string; name: string; updated: string; main?: boolean; messages: { from: string; text: string }[] }[];
};

export function EditChatNameModal({ visible, value, onChange, onClose, onSave }: { visible: boolean; value: string; onChange: (value: string) => void; onClose: () => void; onSave: () => void }) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.renameBackdrop} onPress={onClose}>
        <Pressable style={styles.renameDialog} onPress={(event) => event.stopPropagation()}>
          <Pressable accessibilityRole="button" accessibilityLabel="Close" onPress={onClose} style={styles.renameClose}><ThemedText style={styles.renameCloseText}>×</ThemedText></Pressable>
          <ThemedText style={styles.renameTitle}>Edit chat name</ThemedText>
          <TextInput autoFocus value={value} onChangeText={onChange} onSubmitEditing={onSave} accessibilityLabel="Chat name" style={styles.renameInput} />
          <Pressable accessibilityRole="button" onPress={onSave} style={styles.renameSave}><ThemedText style={styles.renameSaveText}>Save</ThemedText></Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

type WorkspaceTab = 'Ideas' | 'Itinerary' | 'Trip preferences' | 'Calendar' | 'Map';
type LocationItem = { id: string; name: string; subtitle: string; imageUrl?: string };
type TravelParty = { adults: number; children: number; infants: number; pets: number };
type BudgetOptionId = 'any' | 'budget' | 'sensibly' | 'upscale' | 'luxury';
type BudgetOption = { id: BudgetOptionId; symbols?: string; label: string };
const BUDGET_OPTIONS: BudgetOption[] = [
  { id: 'any', label: 'Any budget' },
  { id: 'budget', symbols: '$', label: 'On a budget' },
  { id: 'sensibly', symbols: '$$', label: 'Sensibly priced' },
  { id: 'upscale', symbols: '$$$', label: 'Upscale' },
  { id: 'luxury', symbols: '$$$$', label: 'Luxury' },
];
const WORKSPACE_TABS: WorkspaceTab[] = ['Ideas', 'Itinerary', 'Trip preferences', 'Calendar', 'Map'];

const TRIPS: Trip[] = [
  {
    id: 'dalat', name: 'Da Lat Adventure', destination: 'Da Lat, Vietnam', duration: '4 days in Dec', when: 'Dec 12 – 16', budget: '$1,200',
    cover: 'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=1200&q=85', travelers: ['AL', 'MK', 'JT', 'RS'],
    chats: [
      { id: 'main', name: 'Da Lat trip planning', updated: 'Updated today', main: true, messages: [{ from: 'AI', text: 'Your itinerary has lots of stops but no transport booked between Da Lat and TP.HCM on Day 4. Want help lining up a ride back and timing it with your last activities?' }] },
      { id: 'food', name: 'Food and coffee spots', updated: 'Updated yesterday', messages: [{ from: 'You', text: 'Let’s find a few local coffee shops.' }, { from: 'AI', text: 'I’ve gathered a few well-loved cafés around the city center.' }] },
      { id: 'packing', name: 'Packing ideas', updated: 'Updated Sep 18', messages: [{ from: 'You', text: 'What should we bring for the weather?' }, { from: 'AI', text: 'Bring a light jacket for the cool evenings.' }] },
    ],
  },
  {
    id: 'kyoto', name: 'Kyoto in Spring', destination: 'Kyoto, Japan', duration: '6 days in Apr', when: 'Apr 4 – 10', budget: '$2,400',
    cover: 'https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=1200&q=85', travelers: ['AL', 'MK'],
    chats: [{ id: 'main', name: 'Kyoto planning', updated: 'Updated Sep 20', main: true, messages: [{ from: 'AI', text: 'Your trip plan is coming together. You can review your ideas in the workspace.' }] }],
  },
  {
    id: 'lisbon', name: 'Lisbon Long Weekend', destination: 'Lisbon, Portugal', duration: '3 days in Jun', when: 'Jun 14 – 17', budget: '$1,600',
    cover: 'https://images.unsplash.com/photo-1555881400-74d7acaacd8b?w=1200&q=85', travelers: ['AL', 'MK', 'JT'],
    chats: [{ id: 'main', name: 'Lisbon trip', updated: 'Updated Sep 16', main: true, messages: [{ from: 'AI', text: 'Your Lisbon plans are ready to explore.' }] }],
  },
];

export default function TripsScreen() {
  const params = useLocalSearchParams<{ tripId?: string; chatId?: string; newTrip?: string; newTripField?: 'where' | 'when' }>();
  const [newTripOpen, setNewTripOpen] = useState(params.newTrip === '1');
  const [createdTrips, setCreatedTrips] = useState<Trip[]>([]);
  const [tripOverride, setTripOverride] = useState<string | null>(null);
  const [chatOverride, setChatOverride] = useState<string | null>(null);
  const tripId = tripOverride ?? params.tripId ?? null;
  const activeChat = chatOverride === '' ? null : chatOverride ?? params.chatId ?? null;
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [renameChatId, setRenameChatId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState('');
  const [chatNames, setChatNames] = useState<Record<string, string>>({});
  const [hoveredCard, setHoveredCard] = useState<string | null>(null);
  const [hoveredChat, setHoveredChat] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [localMessages, setLocalMessages] = useState<Record<string, { from: string; text: string }[]>>({});
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState<WorkspaceTab>('Ideas');
  const [showDistances, setShowDistances] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [workspaceAction, setWorkspaceAction] = useState<'invite' | 'note' | null>(null);
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [noteDraft, setNoteDraft] = useState('');
  const [tripNotes, setTripNotes] = useState<string[]>([]);
  const [whereOpen, setWhereOpen] = useState(false);
  const [whenOpen, setWhenOpen] = useState(false);
  const [whoOpen, setWhoOpen] = useState(false);
  const [budgetOpen, setBudgetOpen] = useState(false);
  const [budget, setBudget] = useState<BudgetOptionId>('any');
  const [budgetDraft, setBudgetDraft] = useState<BudgetOptionId>('any');
  const [travelParty, setTravelParty] = useState<TravelParty>({ adults: 1, children: 0, infants: 0, pets: 0 });
  const [whenTab, setWhenTab] = useState<'dates' | 'flexible'>('dates');
  const [calendarMonth, setCalendarMonth] = useState(new Date(2026, 8, 1));
  const [selectedDates, setSelectedDates] = useState<string[]>([]);
  const [flexibleDays, setFlexibleDays] = useState(5);
  const [flexibleMonths, setFlexibleMonths] = useState<string[]>([]);
  const [whereLocations, setWhereLocations] = useState<LocationItem[]>([]);
  const [whereDraft, setWhereDraft] = useState('');
  const [addingLocation, setAddingLocation] = useState(false);
  const theme = useTheme();
  const trip = [...createdTrips, ...TRIPS].find((item) => item.id === tripId);

  if (!trip) {
    return (
      <>
      <ScrollView style={styles.page} contentContainerStyle={styles.pageContent}>
        <View style={styles.pageHeader}>
          <ThemedText style={styles.pageTitle}>Your trips</ThemedText>
          <Pressable accessibilityRole="button" onPress={() => setNewTripOpen(true)} style={styles.primaryButton}><ThemedText style={styles.primaryText}>+ New trip</ThemedText></Pressable>
        </View>
        <View style={styles.grid}>
          {[...createdTrips, ...TRIPS].map((item) => (
            <View key={item.id} onPointerEnter={() => setHoveredCard(item.id)} onPointerLeave={() => setHoveredCard(null)} style={styles.card}>
              <Pressable accessibilityRole="button" onPress={() => { setTripOverride(item.id); setChatOverride(''); setDraft(''); setActiveWorkspaceTab('Ideas'); }} style={StyleSheet.absoluteFill}>
                <Image source={{ uri: item.cover }} style={styles.cover} contentFit="cover" />
                <View style={styles.coverShade} />
                <View style={styles.cardDetails}>
                  <ThemedText style={styles.tripName}>{item.name}</ThemedText>
                  <ThemedText style={styles.tripMeta}>{item.destination}</ThemedText>
                  <View style={styles.durationRow}><ThemedText style={styles.tripMeta}>{item.duration}</ThemedText><View style={styles.avatarStack}>{item.travelers.slice(0, 3).map((avatar, i) => <View key={`${avatar}-${i}`} style={[styles.avatar, { marginLeft: i ? -9 : 0 }]}><ThemedText style={styles.avatarText}>{avatar}</ThemedText></View>)}{item.travelers.length > 3 && <View style={[styles.avatar, styles.moreAvatar, { marginLeft: -9 }]}><ThemedText style={styles.avatarText}>+{item.travelers.length - 3}</ThemedText></View>}</View></View>
                </View>
              </Pressable>
              {(Platform.OS !== 'web' || hoveredCard === item.id || openMenu === item.id) && <Pressable accessibilityRole="button" accessibilityLabel={`Trip menu for ${item.name}`} onPress={() => setOpenMenu(openMenu === item.id ? null : item.id)} style={styles.menuTrigger}><ThemedText style={styles.menuTriggerText}>···</ThemedText></Pressable>}
              {openMenu === item.id && <View style={styles.cardMenu}>{['Share trip', 'Change photo', 'Delete trip'].map((label) => <Pressable key={label} onPress={(event) => { event.stopPropagation(); setOpenMenu(null); }} style={styles.menuItem}><ThemedText style={label === 'Delete trip' ? styles.deleteText : styles.menuText}>{label}</ThemedText></Pressable>)}</View>}
            </View>
          ))}
        </View>
      </ScrollView>
      <NewTripModal key={params.newTripField ?? 'new-trip'} visible={newTripOpen || params.newTrip === '1'} initialField={params.newTripField} onClose={() => { setNewTripOpen(false); router.replace('/trips'); }} onCreate={(newTrip) => { setCreatedTrips((items) => [newTrip, ...items]); setNewTripOpen(false); setTripOverride(newTrip.id); setChatOverride(''); setActiveWorkspaceTab('Ideas'); router.replace({ pathname: '/trips', params: { tripId: newTrip.id } }); }} />
      </>
    );
  }

  const selectedChat = trip.chats.find((chat) => chat.id === activeChat);
  const mainChat = trip.chats.find((chat) => chat.main) ?? trip.chats[0];
  const submitMessage = (chatId: string) => {
    const text = draft.trim();
    if (!text) return;
    setLocalMessages((messages) => ({ ...messages, [chatId]: [...(messages[chatId] ?? []), { from: 'You', text }] }));
    setDraft('');
  };
  return (
    <View style={styles.detail}>
      <EditChatNameModal visible={renameChatId !== null} value={renameDraft} onChange={setRenameDraft} onClose={() => setRenameChatId(null)} onSave={() => { if (renameChatId && renameDraft.trim()) setChatNames((names) => ({ ...names, [renameChatId]: renameDraft.trim() })); setRenameChatId(null); }} />
      <NewTripModal visible={newTripOpen || params.newTrip === '1'} onClose={() => { setNewTripOpen(false); router.replace('/trips'); }} onCreate={(newTrip) => { setCreatedTrips((items) => [newTrip, ...items]); setNewTripOpen(false); setTripOverride(newTrip.id); setChatOverride(''); setActiveWorkspaceTab('Ideas'); router.replace({ pathname: '/trips', params: { tripId: newTrip.id } }); }} />
      <View style={[styles.leftPanel, { borderRightColor: theme.backgroundElement }]}>
        <View style={[styles.chatHeader, { borderBottomColor: theme.backgroundElement }]}>
          <View style={styles.tripHeading}>
            <Pressable accessibilityRole="button" onPress={() => activeChat ? setChatOverride('') : router.replace('/trips')} style={styles.backButton}><ThemedText style={styles.backText}>‹</ThemedText></Pressable>
            <View style={styles.headingText}><ThemedText numberOfLines={1} style={styles.detailTitle}>{trip.name}</ThemedText><ThemedText themeColor="textSecondary" style={styles.destination}>{trip.destination}</ThemedText></View>
          </View>
        </View>
        {!activeChat && <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 16, paddingHorizontal: 10, paddingVertical: 9, borderWidth: 1, borderColor: '#e2e5e9', borderRadius: 9, backgroundColor: '#fff' }}>
          <Pressable accessibilityRole="button" onPress={() => { setWhereDraft(''); setAddingLocation(false); setWhereOpen(true); }}><ThemedText style={{ fontSize: 11, color: '#475569' }}>{trip.destination.split(',')[0]}</ThemedText></Pressable><View style={{ width: 1, height: 16, backgroundColor: '#e2e5e9' }}/>
          <Pressable accessibilityRole="button" onPress={() => setWhenOpen(true)}><ThemedText style={{ fontSize: 11, color: '#475569' }}>{trip.duration}</ThemedText></Pressable><View style={{ width: 1, height: 16, backgroundColor: '#e2e5e9' }}/>
          <Pressable accessibilityRole="button" onPress={() => setWhoOpen(true)}><ThemedText style={{ fontSize: 11, color: '#475569' }}>{travelParty.adults + travelParty.children} {travelParty.adults + travelParty.children === 1 ? 'traveler' : 'travelers'}</ThemedText></Pressable><View style={{ width: 1, height: 16, backgroundColor: '#e2e5e9' }}/>
          <Pressable accessibilityRole="button" onPress={() => { setBudgetDraft(budget); setBudgetOpen(true); }}><ThemedText style={{ fontSize: 11, color: '#475569' }}>{trip.budget}</ThemedText></Pressable>
        </View>}
        {!activeChat && <View style={styles.alert}><ThemedText style={styles.alertLabel}>✦ Trip insight</ThemedText><ThemedText style={styles.alertText}>{mainChat?.messages[0]?.text}</ThemedText></View>}
        {!activeChat && <SharedChatInput value={draft} onChangeText={setDraft} onSend={() => submitMessage(mainChat.id)} />}
        {!activeChat ? (
          <ScrollView style={styles.chatArea} contentContainerStyle={styles.chatListContent}>
            <ThemedText themeColor="textSecondary" style={styles.sectionLabel}>TRIP CHATS</ThemedText>
            {trip.chats.map((chat) => <View key={chat.id} style={styles.chatRowWrap}>
              <View onPointerEnter={() => setHoveredChat(chat.id)} onPointerLeave={() => setHoveredChat(null)} style={[styles.chatRow, { backgroundColor: chat.main ? theme.backgroundElement : 'transparent' }]}>
                <Pressable accessibilityRole="button" onPress={() => setChatOverride(chat.id)} style={styles.chatRowText}>
                  <View style={styles.chatNameRow}><ThemedText style={styles.chatName}>{chatNames[`${trip.id}:${chat.id}`] ?? chat.name}</ThemedText>{chat.main && <View style={styles.mainBadge}><ThemedText style={styles.mainBadgeText}>Main</ThemedText></View>}</View><ThemedText themeColor="textSecondary" style={styles.updated}>{chat.updated}</ThemedText>
                </Pressable>
                {(Platform.OS !== 'web' || hoveredChat === chat.id || openMenu === chat.id) && <Pressable accessibilityRole="button" accessibilityLabel={`Menu for ${chat.name}`} onPress={() => setOpenMenu(openMenu === chat.id ? null : chat.id)} style={styles.chatMenuTrigger}><ThemedText>···</ThemedText></Pressable>}
              </View>
              {openMenu === chat.id && <View style={styles.chatMenu}>{['Rename chat', 'Set as main chat', 'Delete chat'].map((label) => <Pressable key={label} onPress={() => { setOpenMenu(null); if (label === 'Rename chat') { const key = `${trip.id}:${chat.id}`; setRenameChatId(key); setRenameDraft(chatNames[key] ?? chat.name); } }} style={styles.menuItem}><ThemedText style={label === 'Delete chat' ? styles.deleteText : styles.menuText}>{label}</ThemedText></Pressable>)}</View>}
            </View>)}
          </ScrollView>
        ) : (
          <View style={styles.conversation}>
            <ThemedText themeColor="textSecondary" style={styles.conversationTitle}>{selectedChat ? chatNames[`${trip.id}:${selectedChat.id}`] ?? selectedChat.name : ''}</ThemedText>
            <ScrollView style={styles.messages} contentContainerStyle={styles.messagesContent}>{[...(selectedChat?.messages ?? []), ...(localMessages[selectedChat?.id ?? ''] ?? [])].map((message, index) => <View key={`${message.from}-${index}`} style={[styles.messageBubble, message.from === 'You' ? styles.userMessage : styles.aiMessage]}><ThemedText style={styles.messageAuthor}>{message.from}</ThemedText><ThemedText>{message.text}</ThemedText></View>)}</ScrollView>
            <SharedChatInput value={draft} onChangeText={setDraft} onSend={() => selectedChat && submitMessage(selectedChat.id)} />
          </View>
        )}
      </View>
      <View style={styles.rightPanel}>
        <View style={[styles.workspaceHeader, { borderBottomColor: theme.backgroundElement }]}>
          <View style={styles.workspaceActions}>
            <View style={styles.participants}><View style={styles.avatarStack}>{trip.travelers.slice(0, 3).map((avatar, index) => <View key={`${avatar}-${index}`} style={[styles.avatar, { marginLeft: index ? -9 : 0 }]}><ThemedText style={styles.avatarText}>{avatar}</ThemedText></View>)}</View><Pressable accessibilityRole="button" onPress={() => setWorkspaceAction('invite')} style={[styles.utilityButton, styles.inviteButton]}><ThemedText style={styles.utilityText}>+ Invite</ThemedText></Pressable></View>
            <Pressable accessibilityRole="button" onPress={() => Share.share({ message: `Join me on ${trip.name}: ${typeof window !== 'undefined' ? window.location.href : `https://travel.example/trips/${trip.id}`}` })} style={styles.utilityButton}><ThemedText style={styles.utilityText}>Share / Export</ThemedText></Pressable>
            <Pressable accessibilityRole="button" onPress={() => { setNoteDraft(''); setWorkspaceAction('note'); }} style={styles.utilityButton}><ThemedText style={styles.utilityText}>Add note</ThemedText></Pressable>
            <View style={styles.workspaceMenuWrap}><Pressable accessibilityRole="button" accessibilityLabel="More trip actions" accessibilityState={{ expanded: workspaceMenuOpen }} onPress={() => setWorkspaceMenuOpen((open) => !open)} style={styles.utilityButton}><ThemedText style={styles.utilityText}>···</ThemedText></Pressable>{workspaceMenuOpen && <View style={styles.workspaceMenu}>{['Export trip data', 'Duplicate trip', 'Archive trip', 'Delete trip'].map((action) => <Pressable key={action} accessibilityRole="button" onPress={() => { setWorkspaceMenuOpen(false); if (action === 'Export trip data') Share.share({ message: `${trip.name} — ${trip.destination}\n${trip.when}\nBudget: ${trip.budget}` }); else Alert.alert(action, `${action} is not available yet.`); }} style={styles.menuItem}><ThemedText style={action === 'Delete trip' ? styles.deleteText : styles.menuText}>{action}</ThemedText></Pressable>)}</View>}</View>
          </View>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.workspaceTabs} contentContainerStyle={styles.workspaceTabsContent}>
          {WORKSPACE_TABS.map((tab) => <Pressable key={tab} accessibilityRole="button" accessibilityState={{ selected: activeWorkspaceTab === tab }} onPress={() => setActiveWorkspaceTab(tab)} style={[styles.tabButton, activeWorkspaceTab === tab && styles.activeTab]}><ThemedText style={[styles.tabText, activeWorkspaceTab === tab && styles.activeTabText]}>{tab}</ThemedText></Pressable>)}
        </ScrollView>
        <ScrollView key={activeWorkspaceTab} scrollEnabled={activeWorkspaceTab !== 'Calendar'} style={styles.workspaceContent} contentContainerStyle={[styles.workspaceContentInner, activeWorkspaceTab === 'Calendar' && styles.calendarWorkspaceContent]}>
          {tripNotes.length > 0 && <View style={styles.savedNotes}><ThemedText style={styles.notesTitle}>Trip notes</ThemedText>{tripNotes.map((note, index) => <ThemedText key={`${index}-${note}`} style={styles.savedNote}>{note}</ThemedText>)}</View>}
          <WorkspaceContent tab={activeWorkspaceTab} showDistances={showDistances} onToggleDistances={() => setShowDistances((value) => !value)} zoom={zoom} onZoom={setZoom} />
        </ScrollView>
      </View>
      <Modal visible={whereOpen} transparent animationType="fade" onRequestClose={() => setWhereOpen(false)}>
        <View style={styles.actionBackdrop}><View style={styles.whereDialog}>
          <View style={styles.whereHeader}><Pressable accessibilityRole="button" accessibilityLabel="Close" onPress={() => setWhereOpen(false)}><ThemedText style={styles.whereClose}>×</ThemedText></Pressable><ThemedText style={styles.whereTitle}>Where</ThemedText><View style={styles.whereCloseSpacer}/></View>
          {whereLocations.map((location) => <View key={location.id} style={styles.whereLocation}>
            {location.imageUrl ? <Image source={{ uri: location.imageUrl }} style={styles.whereImage} contentFit="cover" /> : <View style={styles.wherePin}><ThemedText>⌖</ThemedText></View>}
            <View style={styles.whereLocationText}><ThemedText style={styles.whereName}>{location.name}</ThemedText><ThemedText themeColor="textSecondary" style={styles.whereSubtitle}>{location.subtitle}</ThemedText></View>
            <Pressable accessibilityRole="button" accessibilityLabel={`Remove ${location.name}`} onPress={() => setWhereLocations((items) => items.filter((item) => item.id !== location.id))}><ThemedText style={styles.whereRemove}>×</ThemedText></Pressable>
          </View>)}
          {(whereLocations.length === 0 || addingLocation) && <TextInput autoFocus={addingLocation} value={whereDraft} onChangeText={setWhereDraft} onSubmitEditing={() => { const name = whereDraft.trim(); if (!name) return; setWhereLocations((items) => [...items, { id: `${Date.now()}`, name, subtitle: 'Vietnam' }]); setWhereDraft(''); setAddingLocation(false); }} returnKeyType="done" placeholder="Location" style={styles.whereInput} />}
          {whereLocations.length > 0 && !addingLocation && <Pressable accessibilityRole="button" onPress={() => setAddingLocation(true)} style={styles.whereAdd}><ThemedText style={styles.whereAddText}>＋  Add location</ThemedText></Pressable>}
          <Pressable accessibilityRole="button" disabled={whereLocations.length === 0} onPress={() => setWhereOpen(false)} style={[styles.whereSave, whereLocations.length === 0 && styles.whereSaveDisabled]}><ThemedText style={styles.whereSaveText}>Save</ThemedText></Pressable>
        </View></View>
      </Modal>
      <WhenModal visible={whenOpen} onClose={() => setWhenOpen(false)} tab={whenTab} onTabChange={setWhenTab} month={calendarMonth} onMonthChange={setCalendarMonth} selectedDates={selectedDates} onDateToggle={(date) => setSelectedDates((dates) => dates.includes(date) ? dates.filter((item) => item !== date) : [...dates, date].sort())} days={flexibleDays} onDaysChange={setFlexibleDays} selectedMonths={flexibleMonths} onMonthToggle={(month) => setFlexibleMonths((months) => months.includes(month) ? months.filter((item) => item !== month) : [...months, month])} />
      <WhoModal visible={whoOpen} onClose={() => setWhoOpen(false)} value={travelParty} onUpdate={setTravelParty} />
      <Modal visible={budgetOpen} transparent animationType="fade" onRequestClose={() => setBudgetOpen(false)}>
        <Pressable style={styles.actionBackdrop} onPress={() => setBudgetOpen(false)}>
          <Pressable style={styles.budgetDialog} onPress={(event) => event.stopPropagation()}>
            <View style={styles.budgetHeader}>
              <Pressable accessibilityRole="button" accessibilityLabel="Close" onPress={() => setBudgetOpen(false)}><ThemedText style={styles.whereClose}>×</ThemedText></Pressable>
              <View style={styles.budgetHeading}><ThemedText style={styles.whereTitle}>Budget</ThemedText><ThemedText themeColor="textSecondary" style={styles.budgetSubtitle}>Select your budget range</ThemedText></View>
              <View style={styles.whereCloseSpacer} />
            </View>
            <View style={styles.budgetOptions}>{BUDGET_OPTIONS.map((option) => {
              const selected = budgetDraft === option.id;
              return <Pressable key={option.id} accessibilityRole="radio" accessibilityState={{ checked: selected }} onPress={() => setBudgetDraft(option.id)} style={styles.budgetOption}>
                <View style={[styles.budgetRadio, selected && styles.budgetRadioSelected]}>{selected && <View style={styles.budgetRadioDot} />}</View>
                <View style={styles.budgetOptionText}>{option.symbols && <ThemedText style={styles.budgetSymbols}>{option.symbols}</ThemedText>}<ThemedText style={styles.budgetLabel}>{option.label}</ThemedText></View>
              </Pressable>;
            })}</View>
            <Pressable accessibilityRole="button" onPress={() => { setBudget(budgetDraft); setBudgetOpen(false); }} style={styles.whereSave}><ThemedText style={styles.whereSaveText}>Update</ThemedText></Pressable>
          </Pressable>
        </Pressable>
      </Modal>
      <Modal visible={workspaceAction !== null} transparent animationType="fade" onRequestClose={() => setWorkspaceAction(null)}>
        <View style={styles.actionBackdrop}><View style={styles.actionDialog}>
          <ThemedText style={styles.actionTitle}>{workspaceAction === 'invite' ? 'Invite travelers' : 'Add a trip note'}</ThemedText>
          <ThemedText themeColor="textSecondary" style={styles.actionDescription}>{workspaceAction === 'invite' ? `Invite someone to collaborate on ${trip.name}.` : 'Add a note for everyone in this trip workspace.'}</ThemedText>
          <TextInput autoFocus value={workspaceAction === 'invite' ? inviteEmail : noteDraft} onChangeText={workspaceAction === 'invite' ? setInviteEmail : setNoteDraft} placeholder={workspaceAction === 'invite' ? 'Email address' : 'Write a note...'} keyboardType={workspaceAction === 'invite' ? 'email-address' : 'default'} autoCapitalize="none" multiline={workspaceAction === 'note'} style={[styles.actionInput, workspaceAction === 'note' && styles.noteInput]} />
          <View style={styles.actionButtons}><Pressable accessibilityRole="button" onPress={() => setWorkspaceAction(null)} style={styles.cancelAction}><ThemedText>Cancel</ThemedText></Pressable><Pressable accessibilityRole="button" onPress={() => { if (workspaceAction === 'invite') { if (!inviteEmail.trim()) return; Alert.alert('Invitation ready', `An invitation for ${inviteEmail.trim()} is ready to send.`); setInviteEmail(''); } else { if (!noteDraft.trim()) return; setTripNotes((notes) => [...notes, noteDraft.trim()]); } setWorkspaceAction(null); }} style={styles.confirmAction}><ThemedText style={styles.confirmActionText}>{workspaceAction === 'invite' ? 'Invite' : 'Save note'}</ThemedText></Pressable></View>
        </View></View>
      </Modal>
    </View>
  );
}

export function NewTripModal({ visible, onClose, onCreate, initialField }: { visible: boolean; onClose: () => void; onCreate: (trip: Trip) => void; initialField?: 'where' | 'when' | 'who' | 'budget' }) {
  const [prompt, setPrompt] = useState('');
  const [whereDraft, setWhereDraft] = useState('');
  const [activeField, setActiveField] = useState<'where' | 'when' | 'who' | 'budget' | null>(initialField === 'when' || initialField === 'who' ? initialField : null);
  const [party, setParty] = useState<TravelParty>({ adults: 1, children: 0, infants: 0, pets: 0 });
  const [dates, setDates] = useState<string[]>([]);
  const [whenTab, setWhenTab] = useState<'dates' | 'flexible'>('dates');
  const [month, setMonth] = useState(new Date(2026, 8, 1));
  const [days, setDays] = useState(5);
  const [months, setMonths] = useState<string[]>([]);
  const [budget, setBudget] = useState<BudgetOptionId>('any');
  const [budgetDraft, setBudgetDraft] = useState<BudgetOptionId>('any');
  const [whereOpen, setWhereOpen] = useState(initialField === 'where');
  const [where, setWhere] = useState('');
  const [budgetOpen, setBudgetOpen] = useState(initialField === 'budget');
  useEffect(() => {
    if ((initialField === 'where' && !whereOpen)
      || ((initialField === 'when' || initialField === 'who') && activeField === null)
      || (initialField === 'budget' && !budgetOpen)) {
      onClose();
    }
  }, [activeField, budgetOpen, initialField, onClose, whereOpen]);
  const useful = Boolean(prompt.trim() || where.trim() || dates.length || months.length);
  const dateLabel = dates.length >= 2 ? `${dates[0]} – ${dates[dates.length - 1]}` : months.length ? `${days} days, ${months.join(', ')}` : '';
  const partyLabel = `${party.adults} adult${party.adults === 1 ? '' : 's'}${party.children ? `, ${party.children} child${party.children === 1 ? '' : 'ren'}` : ''}`;
  const budgetLabel = BUDGET_OPTIONS.find((item) => item.id === budget)?.label ?? '';
  const create = () => {
    if (!useful) return;
  const place = where.trim() || 'New trip';
    const id = `trip-${Date.now()}`;
    onCreate({ id, name: `${place} trip`, destination: place, duration: dateLabel || 'Dates flexible', when: dateLabel || 'Dates flexible', budget: budgetLabel, cover: 'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=1200&q=85', travelers: ['AL'], chats: [{ id: 'main', name: `${place} trip planning`, updated: 'Updated today', main: true, messages: [{ from: 'You', text: prompt.trim() || `Plan a trip to ${place}.` }] }] });
  };
  return <>
    <Modal visible={visible && !initialField} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.newTripBackdrop}><ScrollView keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false} style={styles.newTripDialog} contentContainerStyle={styles.newTripDialogContent}>
        <Pressable accessibilityRole="button" accessibilityLabel="Close new trip" onPress={onClose} style={styles.newTripClose}><ThemedText style={styles.whereClose}>×</ThemedText></Pressable>
        <View style={styles.newTripIcon}><Luggage size={24} color="#111" /></View>
        <ThemedText style={styles.newTripTitle}>What should I keep in{ '\n' }mind for this trip?</ThemedText>
        <View style={styles.newTripPromptWrap}><TextInput value={prompt} onChangeText={(text) => setPrompt(text.slice(0, 2000))} placeholder="Somewhere warm with 3 kids" placeholderTextColor="#888" multiline maxLength={2000} textAlignVertical="top" style={styles.newTripInput} /><Pressable accessibilityRole="button" accessibilityLabel="Voice input" style={styles.newTripMic}><ThemedText>♩</ThemedText></Pressable></View>
        <ThemedText style={styles.newTripCounter}>{prompt.length}/2000</ThemedText>
        <ThemedText themeColor="textSecondary" style={styles.newTripHelper}>Have details? Share what you know.</ThemedText>
        <View style={styles.newTripFields}>
          <TripFieldRow title="Where" value={where || 'Select destination'} selected={Boolean(where)} onPress={() => { setWhereDraft(where); setWhereOpen(true); }} />
          <TripFieldRow title="When" value={dateLabel || 'Select dates'} selected={Boolean(dateLabel)} onPress={() => setActiveField('when')} />
          <TripFieldRow title="Who" value={partyLabel} selected={party.adults > 1 || party.children > 0 || party.infants > 0 || party.pets > 0} onPress={() => setActiveField('who')} />
          <TripFieldRow title="Budget" value={budget === 'any' ? 'Set budget' : budgetLabel} selected={budget !== 'any'} onPress={() => { setBudgetDraft(budget); setBudgetOpen(true); }} />
        </View>
        <Pressable accessibilityRole="button" disabled={!useful} onPress={create} style={[styles.newTripCreate, !useful && styles.newTripCreateDisabled]}><ThemedText style={styles.primaryText}>Create</ThemedText></Pressable>
      </ScrollView></View>
    </Modal>
    <Modal visible={visible && whereOpen} transparent animationType="fade" onRequestClose={() => { setWhereOpen(false); if (initialField) onClose(); }}><View style={styles.actionBackdrop}><View style={styles.whereDialog}><View style={styles.whereHeader}><Pressable onPress={() => { setWhereOpen(false); if (initialField) onClose(); }}><ThemedText style={styles.whereClose}>×</ThemedText></Pressable><ThemedText style={styles.whereTitle}>Where</ThemedText><View style={styles.whereCloseSpacer}/></View><TextInput autoFocus value={whereDraft} onChangeText={setWhereDraft} placeholder="Location" style={styles.whereInput}/><Pressable disabled={!whereDraft.trim()} onPress={() => { setWhere(whereDraft.trim()); setWhereOpen(false); if (initialField) onClose(); }} style={styles.whereSave}><ThemedText style={styles.whereSaveText}>Save</ThemedText></Pressable></View></View></Modal>
    <WhenModal visible={visible && activeField === 'when'} onClose={() => { setActiveField(null); if (initialField) onClose(); }} tab={whenTab} onTabChange={setWhenTab} month={month} onMonthChange={setMonth} selectedDates={dates} onDateToggle={(date) => setDates((current) => current.includes(date) ? current.filter((item) => item !== date) : [...current, date].sort())} days={days} onDaysChange={setDays} selectedMonths={months} onMonthToggle={(value) => setMonths((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value])} />
    <WhoModal visible={visible && activeField === 'who'} onClose={() => { setActiveField(null); if (initialField) onClose(); }} value={party} onUpdate={setParty} />
    <Modal visible={visible && budgetOpen} transparent animationType="fade" onRequestClose={() => { setBudgetOpen(false); if (initialField) onClose(); }}><Pressable style={styles.actionBackdrop} onPress={() => { setBudgetOpen(false); if (initialField) onClose(); }}><Pressable style={styles.budgetDialog} onPress={(event) => event.stopPropagation()}><View style={styles.budgetHeader}><Pressable onPress={() => { setBudgetOpen(false); if (initialField) onClose(); }}><ThemedText style={styles.whereClose}>×</ThemedText></Pressable><View style={styles.budgetHeading}><ThemedText style={styles.whereTitle}>Budget</ThemedText><ThemedText themeColor="textSecondary" style={styles.budgetSubtitle}>Select your budget range</ThemedText></View><View style={styles.whereCloseSpacer}/></View><View style={styles.budgetOptions}>{BUDGET_OPTIONS.map((option) => <Pressable key={option.id} accessibilityRole="radio" accessibilityState={{ checked: budgetDraft === option.id }} onPress={() => setBudgetDraft(option.id)} style={styles.budgetOption}><View style={[styles.budgetRadio, budgetDraft === option.id && styles.budgetRadioSelected]}>{budgetDraft === option.id && <View style={styles.budgetRadioDot}/>}</View><View style={styles.budgetOptionText}>{option.symbols && <ThemedText style={styles.budgetSymbols}>{option.symbols}</ThemedText>}<ThemedText style={styles.budgetLabel}>{option.label}</ThemedText></View></Pressable>)}</View><Pressable onPress={() => { setBudget(budgetDraft); setBudgetOpen(false); if (initialField) onClose(); }} style={styles.whereSave}><ThemedText style={styles.whereSaveText}>Update</ThemedText></Pressable></Pressable></Pressable></Modal>
  </>;
}

function TripFieldRow({ title, value, selected, onPress }: { title: string; value: string; selected: boolean; onPress: () => void }) {
  return <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [styles.tripFieldRow, pressed && styles.tripFieldPressed]}><ThemedText style={styles.tripFieldTitle}>{title}</ThemedText><ThemedText numberOfLines={1} style={[styles.tripFieldValue, selected && styles.tripFieldSelected]}>{value}</ThemedText></Pressable>;
}

function WhoModal({ visible, onClose, value, onUpdate }: { visible: boolean; onClose: () => void; value: TravelParty; onUpdate: (value: TravelParty) => void }) {
  const categories: { key: keyof TravelParty; title: string; subtitle: string; min: number }[] = [
    { key: 'adults', title: 'Adults', subtitle: 'Ages 13 or above', min: 1 },
    { key: 'children', title: 'Children', subtitle: 'Ages 2–12', min: 0 },
    { key: 'infants', title: 'Infants', subtitle: 'Under 2', min: 0 },
    { key: 'pets', title: 'Pets', subtitle: 'Bringing a service animal?', min: 0 },
  ];
  const change = (key: keyof TravelParty, amount: number) => onUpdate({ ...value, [key]: Math.max(key === 'adults' ? 1 : 0, value[key] + amount) });
  const totalTravelers = value.adults + value.children;
  return <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
    <View style={styles.actionBackdrop}><View style={styles.whoDialog}>
      <View style={styles.whoHeader}><Pressable accessibilityRole="button" accessibilityLabel="Close" onPress={onClose}><ThemedText style={styles.whereClose}>×</ThemedText></Pressable><View style={styles.whoHeading}><ThemedText style={styles.whereTitle}>Who</ThemedText><ThemedText themeColor="textSecondary" style={styles.whoSummary}>{totalTravelers} {totalTravelers === 1 ? 'traveler' : 'travelers'}</ThemedText></View><View style={styles.whereCloseSpacer} /></View>
      <View>{categories.map(({ key, title, subtitle, min }) => <View key={key} style={styles.whoRow}>
        <View style={styles.whoCategory}><ThemedText style={styles.whoTitle}>{title}</ThemedText><ThemedText themeColor="textSecondary" style={styles.whoSubtitle}>{subtitle}</ThemedText></View>
        <View style={styles.whoControls}>
          <Pressable accessibilityRole="button" accessibilityLabel={`Remove ${title.toLowerCase()}`} accessibilityState={{ disabled: value[key] <= min }} disabled={value[key] <= min} onPress={() => change(key, -1)} style={[styles.whoCounter, value[key] <= min && styles.whoCounterDisabled]}><ThemedText style={styles.whoCounterText}>−</ThemedText></Pressable>
          <ThemedText style={styles.whoCount}>{value[key]}</ThemedText>
          <Pressable accessibilityRole="button" accessibilityLabel={`Add ${title.toLowerCase()}`} onPress={() => change(key, 1)} style={styles.whoCounter}><ThemedText style={styles.whoCounterText}>+</ThemedText></Pressable>
        </View>
      </View>)}</View>
      <Pressable accessibilityRole="button" onPress={onClose} style={styles.whereSave}><ThemedText style={styles.whereSaveText}>Update</ThemedText></Pressable>
    </View></View>
  </Modal>;
}

function WhenModal({ visible, onClose, tab, onTabChange, month, onMonthChange, selectedDates, onDateToggle, days, onDaysChange, selectedMonths, onMonthToggle }: {
  visible: boolean; onClose: () => void; tab: 'dates' | 'flexible'; onTabChange: (tab: 'dates' | 'flexible') => void;
  month: Date; onMonthChange: (month: Date) => void; selectedDates: string[]; onDateToggle: (date: string) => void;
  days: number; onDaysChange: (days: number) => void; selectedMonths: string[]; onMonthToggle: (month: string) => void;
}) {
  const monthNames = ['September', 'October', 'November', 'December', 'January', 'February'];
  const shiftMonth = (offset: number) => onMonthChange(new Date(month.getFullYear(), month.getMonth() + offset, 1));
  const renderCalendar = (date: Date) => {
    const year = date.getFullYear();
    const monthIndex = date.getMonth();
    const firstDay = new Date(year, monthIndex, 1).getDay();
    const mondayOffset = (firstDay + 6) % 7;
    const count = new Date(year, monthIndex + 1, 0).getDate();
    const key = (day: number) => `${year}-${String(monthIndex + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    return <View key={`${year}-${monthIndex}`} style={styles.calendarMonth}>
      <ThemedText style={styles.calendarTitle}>{date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</ThemedText>
      <View style={styles.calendarGrid}>{['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((day, index) => <ThemedText key={`${day}-${index}`} style={styles.calendarWeekday}>{day}</ThemedText>)}
        {Array.from({ length: mondayOffset }, (_, index) => <View key={`empty-${index}`} style={styles.calendarCell} />)}
        {Array.from({ length: count }, (_, index) => { const day = index + 1; const dateKey = key(day); const selected = selectedDates.includes(dateKey); return <Pressable key={day} accessibilityRole="button" accessibilityLabel={`${date.toLocaleDateString('en-US', { month: 'long' })} ${day}`} accessibilityState={{ selected }} onPress={() => onDateToggle(dateKey)} style={[styles.calendarCell, selected && styles.calendarSelected]}><ThemedText style={[styles.calendarDayText, selected && styles.calendarSelectedText]}>{day}</ThemedText></Pressable>; })}
      </View>
    </View>;
  };
  return <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
    <View style={styles.actionBackdrop}><View style={styles.whenDialog}>
      <View style={styles.whenHeader}><Pressable accessibilityRole="button" accessibilityLabel="Close" onPress={onClose}><ThemedText style={styles.whereClose}>×</ThemedText></Pressable><ThemedText style={styles.whereTitle}>When</ThemedText><View style={styles.whereCloseSpacer} /></View>
      <View style={styles.whenTabs}>{(['dates', 'flexible'] as const).map((item) => <Pressable key={item} accessibilityRole="button" accessibilityState={{ selected: tab === item }} onPress={() => onTabChange(item)} style={[styles.whenTab, tab === item && styles.whenTabActive]}><ThemedText style={[styles.whenTabText, tab === item && styles.whenTabTextActive]}>{item === 'dates' ? 'Dates' : 'Flexible'}</ThemedText></Pressable>)}</View>
      {tab === 'dates' ? <View style={styles.calendarArea}>
        <View style={styles.calendarNavigation}><Pressable accessibilityRole="button" accessibilityLabel="Previous month" onPress={() => shiftMonth(-1)} style={styles.calendarArrow}><ThemedText style={styles.calendarArrowText}>‹</ThemedText></Pressable><Pressable accessibilityRole="button" accessibilityLabel="Next month" onPress={() => shiftMonth(1)} style={styles.calendarArrow}><ThemedText style={styles.calendarArrowText}>›</ThemedText></Pressable></View>
        <View style={styles.calendarPair}>{renderCalendar(month)}{renderCalendar(new Date(month.getFullYear(), month.getMonth() + 1, 1))}</View>
      </View> : <View style={styles.flexibleArea}>
        <ThemedText style={styles.flexibleHeading}>How many days?</ThemedText><View style={styles.dayCounter}><Pressable accessibilityRole="button" accessibilityLabel="Remove a day" disabled={days <= 1} onPress={() => onDaysChange(Math.max(1, days - 1))} style={styles.counterButton}><ThemedText>−</ThemedText></Pressable><ThemedText style={styles.dayCount}>{days}</ThemedText><Pressable accessibilityRole="button" accessibilityLabel="Add a day" onPress={() => onDaysChange(days + 1)} style={styles.counterButton}><ThemedText>+</ThemedText></Pressable></View>
        <ThemedText style={styles.flexibleHeading}>Travel anytime</ThemedText><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.monthChoices}>{monthNames.map((name) => <Pressable key={name} accessibilityRole="button" accessibilityState={{ selected: selectedMonths.includes(name) }} onPress={() => onMonthToggle(name)} style={[styles.monthChoice, selectedMonths.includes(name) && styles.monthChoiceActive]}><ThemedText style={styles.monthIcon}>▦</ThemedText><ThemedText style={styles.monthChoiceText}>{name}</ThemedText></Pressable>)}</ScrollView>
      </View>}
      <View style={styles.whenFooter}><Pressable accessibilityRole="button" onPress={onClose} style={styles.whereSave}><ThemedText style={styles.whereSaveText}>Update</ThemedText></Pressable></View>
    </View></View>
  </Modal>;
}

function WorkspaceContent({ tab, showDistances, onToggleDistances, zoom, onZoom }: { tab: string; showDistances: boolean; onToggleDistances: () => void; zoom: number; onZoom: (value: number) => void }) {
  const [calendarOffset, setCalendarOffset] = useState(0);
  const [preferenceSuggestions, setPreferenceSuggestions] = useState(['Prefer short travel distances', 'Avoid rainy days']);
  const [preferences, setPreferences] = useState(['Local food and coffee shops']);
  const [preferenceDraft, setPreferenceDraft] = useState('');
  const [itinerary, setItinerary] = useState([
    { id: 'lake', day: 1, name: 'Xuan Huong Lake', start: '09:00', end: '10:30', distance: '8.95 km', image: 'photo-1470770841072-f978cf4d019e' },
    { id: 'park', day: 1, name: 'Yersin Park', start: '11:00', end: '12:00', distance: '2.4 km', image: 'photo-1500530855697-b586d89ba3ee' },
    { id: 'mountain', day: 2, name: 'Langbiang Mountain', start: '09:30', end: '12:30', distance: '12.1 km', image: 'photo-1464822759023-fed622ff2c3b' },
    { id: 'garden', day: 2, name: 'Dalat Flower Garden', start: '14:00', end: '16:00', distance: '5.6 km', image: 'photo-1490750967868-88aa4486c946' },
    { id: 'waterfall', day: 3, name: 'Datanla Waterfall', start: '10:00', end: '13:00', distance: '7.3 km', image: 'photo-1470770841072-f978cf4d019e'},
    { id: 'market', day: 3, name: 'Night Market', start: '18:00', end: '20:00', distance: '3.2 km', image: 'photo-1517248135467-4c7edcad34c4' },
    { id: 'coffee', day: 4, name: 'Cloud Garden Coffee', start: '09:00', end: '10:30', distance: '4.1 km', image: 'photo-1445116572660-236099ec97a0' },
    { id: 'last-day', day: 4, name: 'Last day in Da Lat', start: '12:00', end: '14:00', distance: '', image: 'photo-1500530855697-b586d89ba3ee' },
  ]);
  const [itineraryMenu, setItineraryMenu] = useState<string | null>(null);
  const [hoveredStop, setHoveredStop] = useState<string | null>(null);
  const [commentFor, setCommentFor] = useState<string | null>(null);
  const [comments, setComments] = useState<Record<string, string[]>>({});
  const [commentDraft, setCommentDraft] = useState('');
  const [addPlaceDay, setAddPlaceDay] = useState<number | null>(null);
  const [placeDraft, setPlaceDraft] = useState('');
  const [placeSearch, setPlaceSearch] = useState('');
  const [placeStartTime, setPlaceStartTime] = useState('15:00');
  const [addPlaceTab, setAddPlaceTab] = useState<'Search' | 'Ideas' | 'Saved' | 'Custom'>('Search');
  const [placeCategory, setPlaceCategory] = useState('For you');
  const [scheduleDetailsOpen, setScheduleDetailsOpen] = useState(false);
  const [scheduleDate, setScheduleDate] = useState('2026-12-24');
  const [draftScheduleDate, setDraftScheduleDate] = useState('2026-12-24');
  const [draftScheduleTime, setDraftScheduleTime] = useState('15:00');
  const [ideas, setIdeas] = useState([
    { name: 'Lam Vien Square', type: 'Attraction', image: 'photo-1519608487953-e999c86e7455' },
    { name: 'Dalat Flower Plateau', type: 'Nature', image: 'photo-1490750967868-88aa4486c946' },
    { name: 'Cloud Garden Coffee', type: 'Cafe', image: 'photo-1445116572660-236099ec97a0' },
    { name: 'Xuan Huong Lake', type: 'Outdoors', image: 'photo-1470770841072-f978cf4d019e' },
  ]);
  const [filter, setFilter] = useState('All types');
  const [likedIdeas, setLikedIdeas] = useState<string[]>([]);
  const [ideaMenu, setIdeaMenu] = useState<string | null>(null);
  const [hoveredIdea, setHoveredIdea] = useState<string | null>(null);
  const [ideaDialog, setIdeaDialog] = useState<'add' | 'edit' | 'details' | null>(null);
  const [editingIdea, setEditingIdea] = useState<string | null>(null);
  const [ideaName, setIdeaName] = useState('');
  const [ideaType, setIdeaType] = useState('Attraction');
  const [selectedMapPlace, setSelectedMapPlace] = useState<string | null>(null);
  const [mapLayer, setMapLayer] = useState<'Standard' | 'Terrain'>('Standard');
  const [mapRecentered, setMapRecentered] = useState(false);
  const visibleIdeas = ideas.filter((idea) => filter === 'All types' || idea.type === filter);
  const searchablePlaces = [
    ...ideas.map((idea) => ({ name: idea.name, type: idea.type, image: idea.image })),
    { name: 'Valley of Love', type: 'Attraction', image: 'photo-1500530855697-b586d89ba3ee' },
    { name: 'Datanla Waterfall', type: 'Nature', image: 'photo-1470770841072-f978cf4d019e' },
    { name: 'Da Lat Night Market', type: 'Food & drink', image: 'photo-1517248135467-4c7edcad34c4' },
  ].filter((place, index, places) => places.findIndex((item) => item.name === place.name) === index)
    .filter((place) => place.name.toLowerCase().includes(placeSearch.trim().toLowerCase()));
  const addPlaceToDay = (name: string, image = 'photo-1500530855697-b586d89ba3ee') => {
    if (addPlaceDay === null || !/^([01]\d|2[0-3]):[0-5]\d$/.test(placeStartTime)) return;
    const [hour, minute] = placeStartTime.split(':').map(Number);
    const end = new Date(2000, 0, 1, hour, minute + 60);
    const endTime = `${String(end.getHours()).padStart(2, '0')}:${String(end.getMinutes()).padStart(2, '0')}`;
    setItinerary((items) => [...items, { id: `custom-${Date.now()}-${Math.random()}`, day: addPlaceDay, name, start: placeStartTime, end: endTime, distance: '', image }]);
    setPlaceDraft('');
    setPlaceSearch('');
  };
  if (tab === 'Ideas') return <View>
    <View style={styles.contentHeading}><View><ThemedText style={styles.workspaceTitle}>Ideas</ThemedText><ThemedText themeColor="textSecondary">{visibleIdeas.length} {visibleIdeas.length === 1 ? 'item' : 'items'}</ThemedText></View><View style={styles.toolbar}><Pressable accessibilityRole="button" style={styles.smallButton} onPress={() => { setIdeaName(''); setIdeaType('Attraction'); setIdeaDialog('add'); }}><ThemedText>+ Add</ThemedText></Pressable><Pressable accessibilityRole="button" style={styles.smallButton} onPress={() => setIdeaMenu(ideaMenu === '__filter' ? null : '__filter')}><ThemedText>{filter === 'All types' ? 'Type ⌄' : `${filter} ⌄`}</ThemedText></Pressable><Pressable accessibilityRole="button" style={styles.smallButton} onPress={() => setIdeaMenu(ideaMenu === '__more' ? null : '__more')}><ThemedText>···</ThemedText></Pressable></View></View>
    {ideaMenu === '__filter' && <View style={styles.ideaFilterMenu}>{['All types', ...Array.from(new Set(ideas.map((idea) => idea.type)))].map((type) => <Pressable key={type} onPress={() => { setFilter(type); setIdeaMenu(null); }} style={styles.menuItem}><ThemedText style={styles.menuText}>{type}</ThemedText></Pressable>)}</View>}
    {ideaMenu === '__more' && <View style={styles.ideaFilterMenu}><Pressable onPress={() => { setIdeas((items) => [...items].sort((a, b) => a.name.localeCompare(b.name))); setIdeaMenu(null); }} style={styles.menuItem}><ThemedText style={styles.menuText}>Sort by name</ThemedText></Pressable><Pressable onPress={() => { setFilter('All types'); setIdeaMenu(null); }} style={styles.menuItem}><ThemedText style={styles.menuText}>Clear filters</ThemedText></Pressable></View>}
    <View style={styles.ideaGrid}>{visibleIdeas.map((idea) => <View key={idea.name} onPointerEnter={() => setHoveredIdea(idea.name)} onPointerLeave={() => setHoveredIdea(null)} style={styles.ideaCard}><View style={{ position: 'relative' }}><Pressable accessibilityRole="button" accessibilityLabel={`View ${idea.name} details`} onPress={() => { setEditingIdea(idea.name); setIdeaDialog('details'); }}><Image source={{ uri: `https://images.unsplash.com/${idea.image}?w=700&q=80` }} style={styles.ideaImage} contentFit="cover"/></Pressable><View style={{ position: 'absolute', top: 12, left: 12, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: 'rgba(15, 23, 42, 0.72)' }}><ThemedText style={{ color: '#fff', fontSize: 11, fontWeight: '600' }}>{idea.type}</ThemedText></View></View><View style={styles.ideaInfo}><View><ThemedText style={styles.ideaName}>{idea.name}</ThemedText><ThemedText themeColor="textSecondary" style={{ fontSize: 12, marginTop: 3 }}>{idea.type}</ThemedText></View><View style={{ flexDirection: 'row', justifyContent: 'space-between', borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#edf0f3', paddingTop: 10, marginTop: 10 }}><ThemedText themeColor="textSecondary" style={{ fontSize: 11 }}>{['1-2 hours', 'Half day', 'Morning or sunset', '2-3 hours'][ideas.findIndex((item) => item.name === idea.name)] ?? 'Flexible'}</ThemedText><ThemedText style={{ color: '#d99a22', fontSize: 11, fontWeight: '700' }}>★  {['4.7', '4.9', '4.8', '4.6'][ideas.findIndex((item) => item.name === idea.name)] ?? '4.8'}</ThemedText></View></View>{(Platform.OS !== 'web' || hoveredIdea === idea.name || ideaMenu === idea.name) && <View style={styles.ideaActions}><Pressable accessibilityRole="button" accessibilityLabel={`Save ${idea.name}`} onPress={() => setLikedIdeas((items) => items.includes(idea.name) ? items.filter((name) => name !== idea.name) : [...items, idea.name])} style={styles.ideaActionButton}><ThemedText style={likedIdeas.includes(idea.name) ? styles.likedIdea : styles.ideaActionText}>{likedIdeas.includes(idea.name) ? '♥' : '♡'}</ThemedText></Pressable><Pressable accessibilityRole="button" accessibilityLabel={`More actions for ${idea.name}`} onPress={() => setIdeaMenu(ideaMenu === idea.name ? null : idea.name)} style={styles.ideaActionButton}><ThemedText style={styles.ideaActionText}>···</ThemedText></Pressable></View>}{ideaMenu === idea.name && <View style={styles.ideaCardMenu}>{['Add to itinerary', 'Edit', 'View details', 'Delete'].map((action) => <Pressable key={action} style={styles.menuItem} onPress={() => { setIdeaMenu(null); setEditingIdea(idea.name); if (action === 'Delete') setIdeas((items) => items.filter((item) => item.name !== idea.name)); else if (action === 'Edit') { setIdeaName(idea.name); setIdeaType(idea.type); setIdeaDialog('edit'); } else if (action === 'View details') setIdeaDialog('details'); else Alert.alert('Added to itinerary', `${idea.name} is ready to schedule.`); }}><ThemedText style={action === 'Delete' ? styles.deleteText : styles.menuText}>{action}</ThemedText></Pressable>)}</View>}</View>)}</View>
    <Modal transparent visible={ideaDialog !== null} animationType="fade" onRequestClose={() => setIdeaDialog(null)}><View style={styles.ideaModalBackdrop}><View style={styles.ideaModal}><ThemedText style={styles.workspaceTitle}>{ideaDialog === 'add' ? 'Add an idea' : ideaDialog === 'edit' ? 'Edit idea' : 'Idea details'}</ThemedText>{ideaDialog === 'details' ? <><ThemedText style={styles.ideaName}>{ideas.find((idea) => idea.name === editingIdea)?.name}</ThemedText><ThemedText themeColor="textSecondary">{ideas.find((idea) => idea.name === editingIdea)?.type}</ThemedText><Pressable style={styles.smallButton} onPress={() => { const name = ideas.find((idea) => idea.name === editingIdea)?.name; if (name) Alert.alert('Added to itinerary', `${name} is ready to schedule.`); setIdeaDialog(null); }}><ThemedText>Add to itinerary</ThemedText></Pressable></> : <><TextInput autoFocus value={ideaName} onChangeText={setIdeaName} placeholder="Place or activity name" style={styles.ideaTextInput}/><TextInput value={ideaType} onChangeText={setIdeaType} placeholder="Type (e.g. Attraction)" style={styles.ideaTextInput}/><Pressable style={styles.primaryButton} onPress={() => { const name = ideaName.trim(); if (!name) return; if (ideaDialog === 'edit' && editingIdea) setIdeas((items) => items.map((item) => item.name === editingIdea ? { ...item, name, type: ideaType.trim() || 'Other' } : item)); else setIdeas((items) => [...items, { name, type: ideaType.trim() || 'Other', image: 'photo-1500530855697-b586d89ba3ee' }]); setIdeaDialog(null); }}><ThemedText style={styles.primaryText}>{ideaDialog === 'edit' ? 'Save changes' : 'Add idea'}</ThemedText></Pressable></>}<Pressable onPress={() => setIdeaDialog(null)} style={styles.ideaCancel}><ThemedText themeColor="textSecondary">Cancel</ThemedText></Pressable></View></View></Modal>
  </View>;
  if (tab === 'Itinerary') return <View>
    <View style={styles.contentHeading}><View><ThemedText style={styles.workspaceTitle}>Itinerary</ThemedText><ThemedText themeColor="textSecondary">4 days</ThemedText></View><View style={styles.toolbar}><Pressable accessibilityRole="button" accessibilityState={{ selected: showDistances }} onPress={onToggleDistances} style={[styles.smallButton, showDistances && styles.selectedSmallButton]}><ThemedText>Distances {showDistances ? 'On' : 'Off'}</ThemedText></Pressable><Pressable accessibilityRole="button" accessibilityLabel="Itinerary actions" onPress={() => setItineraryMenu(itineraryMenu === 'all' ? null : 'all')} style={styles.smallButton}><ThemedText>···</ThemedText></Pressable></View></View>
    {itineraryMenu === 'all' && <View style={styles.ideaFilterMenu}><Pressable onPress={() => { setItinerary((items) => [...items].sort((a, b) => a.start.localeCompare(b.start))); setItineraryMenu(null); }} style={styles.menuItem}><ThemedText style={styles.menuText}>Sort by start time</ThemedText></Pressable></View>}
    {[1, 2, 3, 4].map((day) => <View key={day} style={styles.daySection}><ThemedText style={styles.dayTitle}>Day {day}</ThemedText>{itinerary.filter((stop) => stop.day === day).map((stop) => <View key={stop.id} onPointerEnter={() => setHoveredStop(stop.id)} onPointerLeave={() => setHoveredStop(null)} style={styles.itineraryStopWrap}>
      <View style={styles.itineraryItem}><Image source={{ uri: `https://images.unsplash.com/${stop.image}?w=240&h=180&fit=crop&q=80` }} style={styles.stopImage} contentFit="cover"/><View style={styles.stopDetails}><ThemedText style={styles.ideaName}>{stop.name}</ThemedText><ThemedText themeColor="textSecondary">{stop.start} – {stop.end}</ThemedText>{showDistances && stop.distance !== '' && <ThemedText themeColor="textSecondary">{stop.distance} to next stop</ThemedText>}</View>{(Platform.OS !== 'web' || hoveredStop === stop.id || itineraryMenu === stop.id) && <View style={styles.stopActions}><Pressable accessibilityRole="button" onPress={() => setCommentFor(commentFor === stop.id ? null : stop.id)} style={styles.smallButton}><ThemedText>Comment</ThemedText></Pressable><Pressable accessibilityRole="button" accessibilityLabel={`Actions for ${stop.name}`} onPress={() => setItineraryMenu(itineraryMenu === stop.id ? null : stop.id)} style={styles.smallButton}><ThemedText>···</ThemedText></Pressable></View>}</View>
      {itineraryMenu === stop.id && <View style={styles.stopMenu}><Pressable onPress={() => { setItinerary((items) => items.filter((item) => item.id !== stop.id)); setItineraryMenu(null); }} style={styles.menuItem}><ThemedText style={styles.deleteText}>Remove from itinerary</ThemedText></Pressable></View>}
      {commentFor === stop.id && <View style={styles.commentPanel}><View style={styles.commentAvatar}><ThemedText style={styles.commentAvatarText}>AL</ThemedText></View><TextInput value={commentDraft} onChangeText={setCommentDraft} placeholder="Add a comment" style={styles.commentInput}/><Pressable accessibilityRole="button" onPress={() => { const text = commentDraft.trim(); if (!text) return; setComments((items) => ({ ...items, [stop.id]: [...(items[stop.id] ?? []), text] })); setCommentDraft(''); }} style={styles.commentSend}><ThemedText style={styles.primaryText}>Send</ThemedText></Pressable></View>}
      {comments[stop.id]?.map((comment, commentIndex) => <View key={`${stop.id}-comment-${commentIndex}`} style={styles.commentEntry}><ThemedText style={styles.commentAvatarText}>AL</ThemedText><ThemedText style={styles.commentText}>{comment}</ThemedText></View>)}
    </View>)}<Pressable accessibilityRole="button" style={styles.addPlace} onPress={() => { setAddPlaceDay(day); setPlaceDraft(''); setPlaceSearch(''); setPlaceStartTime('15:00'); }}><ThemedText>+ Add place</ThemedText></Pressable></View>)}
    <Modal transparent visible={addPlaceDay !== null} animationType="fade" onRequestClose={() => setAddPlaceDay(null)}><View style={styles.ideaModalBackdrop}><View style={styles.addPlaceDialog}>
      <View style={styles.addPlaceHeader}><Pressable accessibilityRole="button" accessibilityLabel="Close add place dialog" onPress={() => setAddPlaceDay(null)} style={styles.addPlaceClose}><ThemedText style={{ fontSize: 20 }}>×</ThemedText></Pressable><ThemedText style={styles.addPlaceTitle}>Add to trip</ThemedText><View style={{ width: 36 }}/></View>
      <ScrollView style={styles.addPlaceBody} contentContainerStyle={{ paddingBottom: 16 }} keyboardShouldPersistTaps="handled">
        <View style={styles.addPlaceTabs}>{(['Search', 'Ideas', 'Saved', 'Custom'] as const).map((tabName) => <Pressable key={tabName} accessibilityRole="tab" accessibilityState={{ selected: addPlaceTab === tabName }} onPress={() => setAddPlaceTab(tabName)} style={[styles.addPlaceTab, addPlaceTab === tabName && styles.addPlaceTabActive]}><ThemedText style={[styles.addPlaceTabText, addPlaceTab === tabName && styles.addPlaceTabTextActive]}>{tabName}</ThemedText></Pressable>)}</View>
        <ThemedText style={styles.addPlaceDestination}>Da Lat  ⌄</ThemedText>
        {addPlaceTab !== 'Custom' && <><View style={styles.addPlaceSearchRow}><TextInput value={placeSearch} onChangeText={setPlaceSearch} placeholder="Search experiences, places, restaurants..." style={styles.addPlaceSearch}/><Pressable accessibilityRole="button" style={styles.addPlaceFilter} onPress={() => setPlaceCategory(placeCategory === 'For you' ? 'Experiences' : 'For you')}><ThemedText>⚙ Filters</ThemedText></Pressable></View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.addPlaceCategories}>{['For you', 'Experiences', 'Restaurants', 'Stays', 'Locations'].map((category) => <Pressable key={category} onPress={() => setPlaceCategory(category)} style={[styles.addPlaceCategory, placeCategory === category && styles.addPlaceCategoryActive]}><ThemedText style={[styles.addPlaceCategoryText, placeCategory === category && styles.addPlaceCategoryTextActive]}>{category}</ThemedText></Pressable>)}</ScrollView>
        <View style={styles.addPlaceSectionHeading}><ThemedText style={styles.addPlaceSectionTitle}>{addPlaceTab === 'Saved' ? 'Saved places' : addPlaceTab === 'Ideas' ? 'Your ideas' : placeCategory === 'For you' ? 'Experiences' : placeCategory}</ThemedText><ThemedText themeColor="textSecondary" style={{ fontSize: 11 }}>Suggested for your schedule</ThemedText></View>
        <View style={styles.addPlaceCards}>{(addPlaceTab === 'Saved' ? searchablePlaces.filter((place) => likedIdeas.includes(place.name)) : addPlaceTab === 'Ideas' ? ideas : searchablePlaces).filter((place) => place.name.toLowerCase().includes(placeSearch.trim().toLowerCase())).map((place, index) => <View key={place.name} style={styles.addPlaceCard}><View style={styles.addPlaceCardImageWrap}><Image source={{ uri: `https://images.unsplash.com/${place.image}?w=500&h=500&fit=crop&q=80` }} style={styles.addPlaceCardImage} contentFit="cover"/><Pressable accessibilityRole="button" accessibilityLabel={`Add ${place.name} to Day ${addPlaceDay}`} disabled={!/^([01]\d|2[0-3]):[0-5]\d$/.test(placeStartTime)} onPress={() => { addPlaceToDay(place.name, place.image); setAddPlaceDay(null); }} style={styles.addPlaceCardButton}><ThemedText style={{ fontWeight: '700' }}>+  Add</ThemedText></Pressable></View><View style={styles.addPlaceCardInfo}><View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 4 }}><ThemedText numberOfLines={1} style={styles.whereName}>{place.name}</ThemedText><ThemedText style={styles.addPlaceRating}>★ {['4.4', '4.2', '4.5'][index % 3]}</ThemedText></View><ThemedText themeColor="textSecondary" style={styles.whereSubtitle}>{place.type}</ThemedText><ThemedText themeColor="textSecondary" style={styles.addPlaceLocation}>Da Lat, Lam Dong</ThemedText></View></View>)}</View>
        {searchablePlaces.length === 0 && <ThemedText themeColor="textSecondary" style={{ paddingVertical: 12 }}>No matching places. Try another search or add a custom place.</ThemedText>}</>}
        {addPlaceTab === 'Custom' && <View style={{ gap: 12, paddingTop: 20 }}><ThemedText style={styles.addPlaceSectionTitle}>Add a custom place</ThemedText><TextInput value={placeDraft} onChangeText={setPlaceDraft} placeholder="Place or activity name" style={styles.ideaTextInput}/><Pressable disabled={!placeDraft.trim() || !/^([01]\d|2[0-3]):[0-5]\d$/.test(placeStartTime)} style={[styles.primaryButton, (!placeDraft.trim() || !/^([01]\d|2[0-3]):[0-5]\d$/.test(placeStartTime)) && { opacity: 0.5 }]} onPress={() => { addPlaceToDay(placeDraft.trim()); setAddPlaceDay(null); }}><ThemedText style={styles.primaryText}>Add custom place</ThemedText></Pressable></View>}
      </ScrollView>
      <View style={styles.addPlaceFooter}><View style={styles.addPlaceFooterLabel}><View style={styles.addPlaceStatusDot}/><ThemedText themeColor="textSecondary" style={{ fontSize: 11 }}>Scheduling for <ThemedText style={{ fontWeight: '700' }}>Day {addPlaceDay} · {placeStartTime}</ThemedText></ThemedText></View><Pressable accessibilityRole="button" onPress={() => { setDraftScheduleDate(scheduleDate); setDraftScheduleTime(placeStartTime); setScheduleDetailsOpen(true); }}><ThemedText style={styles.addPlaceScheduleLink}>Change schedule details</ThemedText></Pressable></View>
      {scheduleDetailsOpen && <View style={styles.scheduleOverlay}><View style={styles.scheduleDialog}><View style={styles.whereHeader}><ThemedText style={styles.addPlaceSectionTitle}>Schedule details</ThemedText><Pressable accessibilityRole="button" accessibilityLabel="Close schedule details" onPress={() => setScheduleDetailsOpen(false)}><ThemedText style={styles.whereClose}>×</ThemedText></Pressable></View><ThemedText themeColor="textSecondary">Date</ThemedText><TextInput value={draftScheduleDate} onChangeText={setDraftScheduleDate} placeholder="YYYY-MM-DD" style={styles.ideaTextInput}/><ThemedText themeColor="textSecondary">Start time</ThemedText><TextInput value={draftScheduleTime} onChangeText={setDraftScheduleTime} placeholder="HH:MM" keyboardType="numbers-and-punctuation" style={styles.ideaTextInput}/><View style={styles.scheduleActions}><Pressable onPress={() => setScheduleDetailsOpen(false)} style={styles.ideaCancel}><ThemedText themeColor="textSecondary">Cancel</ThemedText></Pressable><Pressable onPress={() => { setScheduleDate(draftScheduleDate); setPlaceStartTime(draftScheduleTime); setScheduleDetailsOpen(false); }} style={styles.primaryButton}><ThemedText style={styles.primaryText}>Save schedule</ThemedText></Pressable></View></View></View>}
    </View></View></Modal>
  </View>;
  if (tab === 'Trip preferences') return <View>
    <ThemedText style={styles.workspaceTitle}>Trip preferences</ThemedText>
    {preferenceSuggestions.map((item) => <View key={item} style={styles.preferenceSuggestion}>
      <ThemedText style={{ flex: 1 }}>{item}</ThemedText>
      <Pressable accessibilityRole="button" accessibilityLabel={`Accept preference: ${item}`} onPress={() => { setPreferences((current) => current.includes(item) ? current : [...current, item]); setPreferenceSuggestions((current) => current.filter((suggestion) => suggestion !== item)); }} style={styles.smallButton}><ThemedText>Accept</ThemedText></Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel={`Dismiss preference: ${item}`} onPress={() => setPreferenceSuggestions((current) => current.filter((suggestion) => suggestion !== item))} style={styles.smallButton}><ThemedText>×</ThemedText></Pressable>
    </View>)}
    <View style={styles.preferenceInput}>
      <TextInput value={preferenceDraft} onChangeText={setPreferenceDraft} onSubmitEditing={() => { const value = preferenceDraft.trim(); if (value && !preferences.includes(value)) setPreferences((current) => [...current, value]); setPreferenceDraft(''); }} returnKeyType="done" placeholder="We prefer hotels with free breakfast" style={{ flex: 1, padding: 10 }}/>
      <Pressable accessibilityRole="button" accessibilityLabel="Add trip preference" onPress={() => { const value = preferenceDraft.trim(); if (value && !preferences.includes(value)) setPreferences((current) => [...current, value]); setPreferenceDraft(''); }} style={styles.primaryButton}><ThemedText style={styles.primaryText}>+</ThemedText></Pressable>
    </View>
    {preferences.map((item) => <View key={item} style={styles.preferencePill}><ThemedText>{item}</ThemedText></View>)}
  </View>;
  if (tab === 'Calendar') {
    const calendarEvents = [
      { day: 0, hour: 1, title: 'Xuan Huong Lake', tag: 'activity' },
      { day: 1, hour: 3, title: 'Yersin Park', tag: 'activity' },
      { day: 2, hour: 5, title: 'Da Lat Night Market', tag: 'activity' },
      { day: 0, title: 'D House Dalat', tag: 'stay' },
      { day: 1, title: 'D House Dalat', tag: 'stay' },
      { day: 2, title: 'D House Dalat', tag: 'stay' },
      { day: 3, title: 'D House Dalat', tag: 'stay' },
    ];
    return <View style={styles.calendarWorkspace}>
      <View style={styles.contentHeading}>
        <View><ThemedText style={styles.workspaceTitle}>Calendar</ThemedText><ThemedText themeColor="textSecondary">4 days · December 12–16</ThemedText></View>
        <View style={styles.toolbar}>
          <Pressable accessibilityRole="button" accessibilityLabel="Previous calendar days" onPress={() => setCalendarOffset((offset) => Math.max(0, offset - 4))} style={styles.smallButton}><ThemedText>‹</ThemedText></Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="Next calendar days" onPress={() => setCalendarOffset((offset) => offset + 4)} style={styles.smallButton}><ThemedText>›</ThemedText></Pressable>
        </View>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator>
        <View>
          <View style={styles.calendar}>
            <View style={styles.timeColumn}><ThemedText style={styles.timeLabel}>All-day</ThemedText></View>
            {Array.from({ length: 4 }, (_, i) => {
              const dayNumber = calendarOffset + i + 1;
              const stays = calendarEvents.filter((item) => item.day === dayNumber - 1 && item.tag === 'stay');
              return <View key={dayNumber} style={styles.calendarDay}>
                <ThemedText style={styles.calendarDayTitle}>Day {dayNumber}</ThemedText>
                <View style={styles.alldayEvent} accessibilityLabel={`All-day stays for Day ${dayNumber}`}>
                  {stays.length > 0 ? stays.map((stay, index) => <ThemedText key={`${stay.title}-${index}`} style={styles.calendarEventText}>{stay.title}</ThemedText>) : <ThemedText style={styles.calendarEventText}>—</ThemedText>}
                </View>
              </View>;
            })}
          </View>
          <ScrollView style={styles.calendarHours} showsVerticalScrollIndicator>
            <View style={styles.calendar}>
              <View style={styles.timeColumn}>{['1 PM','2 PM','3 PM','4 PM','5 PM','6 PM','7 PM','8 PM'].map((time) => <ThemedText key={time} style={styles.timeLabel}>{time}</ThemedText>)}</View>
              {Array.from({ length: 4 }, (_, i) => {
                const dayNumber = calendarOffset + i + 1;
                const dayEvents = calendarEvents.filter((item) => item.day === dayNumber - 1 && item.tag !== 'stay');
                return <View key={dayNumber} style={styles.calendarDay}>
                  {Array.from({ length: 8 }, (_, hour) => <View key={hour} style={styles.hourCell}>{dayEvents.filter((event) => event.hour === hour).map((event, index) => <View key={`${event.title}-${index}`} style={styles.calendarEvent}><ThemedText numberOfLines={2} style={styles.calendarEventText}>{event.title}</ThemedText></View>)}</View>)}
                </View>;
              })}
            </View>
          </ScrollView>
        </View>
        <NewTripModal visible={newTripOpen || params.newTrip === '1'} onClose={() => { setNewTripOpen(false); router.replace('/trips'); }} onCreate={(newTrip) => { setCreatedTrips((items) => [newTrip, ...items]); setNewTripOpen(false); setTripOverride(newTrip.id); setChatOverride(''); setActiveWorkspaceTab('Ideas'); router.replace({ pathname: '/trips', params: { tripId: newTrip.id } }); }} />
      </ScrollView>
    </View>;
  }
  const places = [
    { name: 'Langbiang Mountain', category: 'nature', icon: '▲', x: 22, y: 30 },
    { name: 'Puppy Farm', category: 'attraction', icon: '◎', x: 28, y: 35 },
    { name: 'Datanla Waterfall', category: 'nature', icon: '⌁', x: 62, y: 62 },
    { name: 'Tuyen Lam Lake', category: 'nature', icon: '◌', x: 67, y: 67 },
    { name: 'Cau Dat Farm', category: 'cafe', icon: '☕', x: 83, y: 39 },
  ];
  const clusters = zoom < 3
    ? [{ id: 'north', x: 25, y: 32, places: places.slice(0, 2) }, { id: 'south', x: 64, y: 65, places: places.slice(2, 4) }, { id: 'east', x: 83, y: 39, places: places.slice(4) }]
    : places.map((place) => ({ id: place.name, x: place.x, y: place.y, places: [place] }));
  return <View style={[styles.mapCanvas, mapLayer === 'Terrain' && styles.terrainMap]}>
    <View style={styles.mapPark} /><View style={styles.mapLake} /><View style={styles.mapRoadOne} /><View style={styles.mapRoadTwo} /><View style={styles.mapPath} />
    <View style={styles.mapTitle}><ThemedText style={styles.workspaceTitle}>Da Lat</ThemedText><ThemedText themeColor="textSecondary">Trip locations · {mapLayer}</ThemedText></View>
    {clusters.map((cluster) => {
      const isCluster = cluster.places.length > 1;
      const place = cluster.places[0];
      const selected = cluster.places.some((item) => item.name === selectedMapPlace);
      return <Pressable key={cluster.id} accessibilityRole="button" accessibilityLabel={isCluster ? `Zoom in to ${cluster.places.length} nearby locations` : `Show ${place.name} on map`} accessibilityState={{ selected }} onPress={() => {
        if (isCluster) onZoom(Math.min(zoom + 1, 4));
        else { setSelectedMapPlace(selectedMapPlace === place.name ? null : place.name); setMapRecentered(false); }
      }} style={[styles.mapMarker, { top: `${cluster.y}%`, left: `${cluster.x}%` }]}>
        <View style={[isCluster ? styles.mapCluster : styles.markerDot, selected && styles.selectedMarker]}><ThemedText style={[styles.markerIcon, (isCluster || selected) && styles.markerIconInverted]}>{isCluster ? String(cluster.places.length) : place.icon}</ThemedText></View>
        {!isCluster && <View style={[styles.markerLabel, selected && styles.selectedMarkerLabel]}><ThemedText style={styles.markerText}>{place.name}</ThemedText></View>}
      </Pressable>;
    })}
    <View style={styles.mapControls}>
      <Pressable accessibilityRole="button" accessibilityLabel="Zoom in" disabled={zoom >= 4} onPress={() => onZoom(Math.min(zoom + 1, 4))} style={styles.mapControlButton}><ThemedText>＋</ThemedText></Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Zoom out" disabled={zoom <= 1} onPress={() => onZoom(Math.max(zoom - 1, 1))} style={styles.mapControlButton}><ThemedText>−</ThemedText></Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Recenter map" onPress={() => { onZoom(2); setSelectedMapPlace(null); setMapRecentered(true); }} style={styles.mapControlButton}><ThemedText>⌖</ThemedText></Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Toggle map layer" accessibilityState={{ selected: mapLayer === 'Terrain' }} onPress={() => setMapLayer(mapLayer === 'Standard' ? 'Terrain' : 'Standard')} style={styles.mapControlButton}><ThemedText>{mapLayer === 'Standard' ? 'Terrain' : 'Map'}</ThemedText></Pressable>
    </View>
    {(selectedMapPlace || mapRecentered) && <View style={styles.mapSelection}><ThemedText style={styles.mapSelectionText}>{selectedMapPlace ?? 'Showing all trip locations'}</ThemedText><Pressable accessibilityRole="button" accessibilityLabel="Clear map selection" onPress={() => { setSelectedMapPlace(null); setMapRecentered(false); }}><ThemedText>×</ThemedText></Pressable></View>}
    <ThemedText style={styles.zoomLabel}>Zoom {zoom} · Map data © OpenStreetMap contributors</ThemedText>
  </View>;
}

const styles = StyleSheet.create({
  newTripBackdrop: { flex: 1, padding: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.48)' },
  newTripDialog: { width: '100%', maxWidth: 640, maxHeight: '94%', borderRadius: 20, backgroundColor: '#fff' },
  newTripDialogContent: { alignItems: 'center', paddingHorizontal: 30, paddingTop: 30, paddingBottom: 24 },
  newTripClose: { position: 'absolute', top: 15, left: 24, zIndex: 2, width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  newTripIcon: { width: 50, height: 50, borderRadius: 25, marginBottom: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: '#c8f4e8' },
  newTripTitle: { marginBottom: 22, textAlign: 'center', fontSize: 25, lineHeight: 31, fontWeight: '600', color: '#111' },
  newTripPromptWrap: { width: '100%', height: 132, position: 'relative', borderWidth: 1, borderColor: '#c9c9c9', borderRadius: 18 },
  newTripInput: { flex: 1, padding: 15, paddingBottom: 34, fontSize: 16, outlineStyle: 'none' as any },
  newTripMic: { position: 'absolute', right: 12, bottom: 8, width: 28, height: 28, alignItems: 'center', justifyContent: 'center' },
  newTripCounter: { width: '100%', marginTop: 4, textAlign: 'right', color: '#888', fontSize: 12 },
  newTripHelper: { width: '100%', marginTop: 20, marginBottom: 10, fontSize: 14 },
  newTripFields: { width: '100%', gap: 9 },
  tripFieldRow: { minHeight: 56, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingHorizontal: 20, borderWidth: 1, borderColor: '#dedede', borderRadius: 17, backgroundColor: '#fff' },
  tripFieldPressed: { backgroundColor: '#f6f7f6' },
  tripFieldTitle: { fontSize: 15, color: '#111' },
  tripFieldValue: { flexShrink: 1, fontSize: 13, color: '#888', textAlign: 'right' },
  tripFieldSelected: { color: '#333' },
  newTripCreate: { width: 210, minHeight: 50, alignItems: 'center', justifyContent: 'center', marginTop: 40, borderRadius: 26, backgroundColor: '#111' },
  newTripCreateDisabled: { backgroundColor: '#b5b5b5' },
  whoDialog: { width: '100%', maxWidth: 420, padding: 22, borderRadius: 22, backgroundColor: '#fff', gap: 12 }, whoHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }, whoHeading: { alignItems: 'center' }, whoSummary: { fontSize: 12, marginTop: 2 }, whoRow: { minHeight: 70, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#eee' }, whoCategory: { gap: 3 }, whoTitle: { fontSize: 14, fontWeight: '600' }, whoSubtitle: { fontSize: 12 }, whoControls: { flexDirection: 'row', alignItems: 'center', gap: 12 }, whoCounter: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#ddd', borderRadius: 17 }, whoCounterDisabled: { opacity: 0.35 }, whoCounterText: { fontSize: 18, color: '#333' }, whoCount: { minWidth: 18, textAlign: 'center', fontSize: 14, fontWeight: '600' },
  whenDialog: { width: '100%', maxWidth: 620, padding: 22, borderRadius: 22, backgroundColor: '#fff', gap: 14 }, whenHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }, whenTabs: { alignSelf: 'center', flexDirection: 'row', padding: 3, borderRadius: 22, backgroundColor: '#f2f2f2' }, whenTab: { minWidth: 95, alignItems: 'center', paddingVertical: 8, borderRadius: 20 }, whenTabActive: { backgroundColor: '#fff', shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 3, elevation: 1 }, whenTabText: { color: '#777', fontSize: 13 }, whenTabTextActive: { color: '#111' }, calendarArea: { minHeight: 300 }, calendarNavigation: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }, calendarArrow: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center', borderRadius: 17 }, calendarArrowText: { fontSize: 26, lineHeight: 30 }, calendarPair: { flexDirection: 'row', gap: 20 }, calendarMonth: { flex: 1 }, calendarTitle: { textAlign: 'center', fontSize: 14, fontWeight: '600', marginBottom: 12 }, calendarGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center' }, calendarWeekday: { width: '14.28%', textAlign: 'center', color: '#777', fontSize: 11, fontWeight: '600', paddingBottom: 7 }, calendarCell: { width: '14.28%', height: 34, alignItems: 'center', justifyContent: 'center', borderRadius: 18 }, calendarDayText: { fontSize: 12 }, calendarSelected: { backgroundColor: '#111' }, calendarSelectedText: { color: '#fff', fontWeight: '700' }, flexibleArea: { minHeight: 300, alignItems: 'center', gap: 14, paddingTop: 10 }, flexibleHeading: { fontSize: 15, fontWeight: '600' }, dayCounter: { flexDirection: 'row', alignItems: 'center', gap: 16, marginBottom: 8 }, counterButton: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#ddd', borderRadius: 18 }, dayCount: { minWidth: 25, textAlign: 'center', fontSize: 17, fontWeight: '600' }, monthChoices: { flexDirection: 'row', gap: 9, paddingVertical: 4 }, monthChoice: { width: 94, height: 94, alignItems: 'center', justifyContent: 'center', gap: 7, borderWidth: 1, borderColor: '#e5e5e5', borderRadius: 15 }, monthChoiceActive: { borderColor: '#111', backgroundColor: '#fafafa' }, monthIcon: { fontSize: 22, color: '#777' }, monthChoiceText: { fontSize: 11, fontWeight: '500' }, whenFooter: { alignItems: 'flex-end' },
  page: { flex: 1 }, pageContent: { padding: 32, gap: 24 }, pageHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }, pageTitle: { fontSize: 30, lineHeight: 38, fontWeight: '700' }, primaryButton: { backgroundColor: '#1c1c1c', minHeight: 42, paddingHorizontal: 16, borderRadius: 9, alignItems: 'center', justifyContent: 'center' }, primaryText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 20 }, card: { width: Platform.OS === 'web' ? '31%' : '100%', minWidth: 240, maxWidth: Platform.OS === 'web' ? 360 : undefined, aspectRatio: 1.18, borderRadius: 16, overflow: 'hidden', position: 'relative', backgroundColor: '#777' }, cover: { ...StyleSheet.absoluteFill, width: undefined, height: undefined }, coverShade: { ...StyleSheet.absoluteFill, backgroundColor: 'rgba(0,0,0,0.18)', borderRadius: 16 }, cardDetails: { position: 'absolute', left: 18, right: 16, bottom: 16, gap: 3 }, tripName: { color: '#fff', fontSize: 21, fontWeight: '700' }, tripMeta: { color: 'rgba(255,255,255,0.92)', fontSize: 13 }, durationRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 }, avatarStack: { flexDirection: 'row', alignItems: 'center' }, avatar: { width: 29, height: 29, borderRadius: 15, backgroundColor: '#f1d7bf', borderWidth: 2, borderColor: '#fff', justifyContent: 'center', alignItems: 'center' }, moreAvatar: { backgroundColor: '#343434' }, avatarText: { color: '#252525', fontSize: 8, fontWeight: '700' }, menuTrigger: { position: 'absolute', top: 12, right: 12, width: 36, height: 36, borderRadius: 18, backgroundColor: 'rgba(255,255,255,0.9)', alignItems: 'center', justifyContent: 'center' }, menuTriggerText: { color: '#111', fontSize: 22, lineHeight: 24 }, cardMenu: { position: 'absolute', zIndex: 4, top: 52, right: 12, width: 158, paddingVertical: 6, borderRadius: 10, backgroundColor: '#fff', shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 12, elevation: 8 }, menuItem: { paddingHorizontal: 13, paddingVertical: 10 }, menuText: { color: '#161616', fontSize: 13 }, deleteText: { color: '#c62828', fontSize: 13 },
  detail: { flex: 1, flexDirection: Platform.OS === 'web' ? 'row' : 'column', minHeight: 0 }, leftPanel: { flex: Platform.OS === 'web' ? 0.88 : 1, minWidth: 0, borderRightWidth: Platform.OS === 'web' ? StyleSheet.hairlineWidth : 0, padding: 18 }, rightPanel: { flex: Platform.OS === 'web' ? 1.12 : 1, minWidth: 0, padding: 18 }, chatHeader: { paddingBottom: 13, borderBottomWidth: StyleSheet.hairlineWidth }, tripHeading: { flexDirection: 'row', alignItems: 'center', gap: 10 }, backButton: { width: 34, height: 34, borderRadius: 17, backgroundColor: '#f3f3f3', alignItems: 'center', justifyContent: 'center' }, backText: { fontSize: 23, lineHeight: 26 }, headingText: { flex: 1 }, detailTitle: { fontSize: 19, fontWeight: '700' }, destination: { fontSize: 13 }, controls: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 7, marginTop: 12 }, control: { alignItems: 'center', paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, backgroundColor: '#f5f5f5' }, controlText: { fontSize: 12 }, alert: { padding: 12, marginTop: 12, borderRadius: 10, backgroundColor: '#f3f5ef', gap: 5 }, alertLabel: { fontSize: 12, fontWeight: '700' }, alertText: { fontSize: 12, lineHeight: 18 }, chatArea: { flex: 1 }, chatListContent: { paddingVertical: 14 }, sectionLabel: { fontSize: 10, letterSpacing: 1, marginBottom: 8 }, chatRowWrap: { position: 'relative' }, chatRow: { minHeight: 62, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10, borderRadius: 9 }, chatRowText: { flex: 1, gap: 4 }, chatNameRow: { flexDirection: 'row', alignItems: 'center', gap: 7 }, chatName: { fontSize: 14, fontWeight: '600' }, mainBadge: { paddingHorizontal: 7, paddingVertical: 2, borderRadius: 8, backgroundColor: '#e7e9e2' }, mainBadgeText: { fontSize: 10 }, updated: { fontSize: 11 }, chatMenuTrigger: { padding: 9 }, chatMenu: { position: 'absolute', zIndex: 5, right: 4, top: 48, minWidth: 170, borderRadius: 10, backgroundColor: '#fff', paddingVertical: 4, shadowColor: '#000', shadowOpacity: 0.16, shadowRadius: 9, elevation: 7 }, conversation: { flex: 1, minHeight: 180, paddingTop: 12 }, conversationTitle: { fontSize: 12, marginBottom: 8 }, messages: { flex: 1 }, messagesContent: { gap: 10, paddingVertical: 8 }, messageBubble: { maxWidth: '88%', padding: 11, borderRadius: 12, gap: 4 }, userMessage: { alignSelf: 'flex-end', backgroundColor: '#e9eee4' }, aiMessage: { alignSelf: 'flex-start', backgroundColor: '#f3f3f3' }, messageAuthor: { fontSize: 10, fontWeight: '700' }, inputRow: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderRadius: 10, padding: 4 }, input: { flex: 1, minHeight: 40, paddingHorizontal: 9 }, sendButton: { paddingHorizontal: 13, paddingVertical: 10, borderRadius: 8, backgroundColor: '#1c1c1c' }, workspaceHeader: { alignItems: 'flex-end', paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth }, workspaceActions: { flexDirection: 'row', gap: 6 }, utilityButton: { paddingHorizontal: 9, paddingVertical: 7, borderRadius: 8, backgroundColor: '#f4f4f4' }, utilityText: { fontSize: 12 }, workspaceTabs: { flexGrow: 0, marginVertical: 10 }, workspaceTabsContent: { gap: 5 }, tabButton: { paddingHorizontal: 12, paddingVertical: 9, borderRadius: 8 }, activeTab: { backgroundColor: '#1c1c1c' }, tabText: { fontSize: 13 }, activeTabText: { color: '#fff' }, workspaceContent: { flex: 1, minHeight: 0 }, workspaceContentInner: { paddingBottom: 24 }, calendarWorkspaceContent: { flexGrow: 1, paddingBottom: 0 }, calendarWorkspace: { flex: 1, minHeight: 0 }, contentHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }, workspaceTitle: { fontSize: 21, fontWeight: '700' }, toolbar: { flexDirection: 'row', alignItems: 'center', gap: 6 }, smallButton: { minHeight: 34, justifyContent: 'center', paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, backgroundColor: '#f3f3f3' }, selectedSmallButton: { backgroundColor: '#e4eadf' },
  ideaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 16, paddingBottom: 24 }, ideaCard: { width: Platform.OS === 'web' ? '48%' : '100%', minWidth: 170, maxWidth: 440, borderRadius: 14, overflow: 'visible', backgroundColor: '#fff', borderWidth: StyleSheet.hairlineWidth, borderColor: '#e7e7e7', position: 'relative' }, ideaImage: { width: '100%', height: 150, borderTopLeftRadius: 14, borderTopRightRadius: 14, backgroundColor: '#eee' }, ideaInfo: { paddingHorizontal: 14, paddingVertical: 12, gap: 3 }, ideaName: { fontSize: 15, fontWeight: '600' }, ideaActions: { position: 'absolute', top: 10, right: 10, flexDirection: 'row', gap: 7 }, ideaActionButton: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.95)' }, ideaActionText: { color: '#171717', fontSize: 19 }, likedIdea: { color: '#d34a56', fontSize: 19 }, ideaCardMenu: { position: 'absolute', zIndex: 8, top: 48, right: 10, width: 170, borderRadius: 10, backgroundColor: '#fff', paddingVertical: 5, shadowColor: '#000', shadowOpacity: 0.16, shadowRadius: 10, elevation: 8 }, ideaFilterMenu: { alignSelf: 'flex-end', zIndex: 9, minWidth: 150, marginTop: -12, marginBottom: 14, borderRadius: 10, backgroundColor: '#fff', paddingVertical: 4, shadowColor: '#000', shadowOpacity: 0.14, shadowRadius: 9, elevation: 7 }, ideaModalBackdrop: { flex: 1, padding: 24, backgroundColor: 'rgba(0,0,0,0.35)', alignItems: 'center', justifyContent: 'center' }, ideaModal: { width: '100%', maxWidth: 420, padding: 22, borderRadius: 16, backgroundColor: '#fff', gap: 14 }, ideaTextInput: { minHeight: 44, borderWidth: 1, borderColor: '#ddd', borderRadius: 9, paddingHorizontal: 12 }, ideaCancel: { alignSelf: 'center', padding: 8 },
  daySection: { paddingTop: 16, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#e7e7e7' }, dayTitle: { fontSize: 17, fontWeight: '700', marginBottom: 10 }, itineraryStopWrap: { position: 'relative' }, itineraryItem: { minHeight: 78, flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8 }, stopImage: { width: 64, height: 58, borderRadius: 9, backgroundColor: '#eee' }, stopDetails: { flex: 1, gap: 3 }, stopActions: { flexDirection: 'row', alignItems: 'center', gap: 5 }, stopMenu: { position: 'absolute', zIndex: 5, top: 48, right: 0, minWidth: 180, borderRadius: 10, backgroundColor: '#fff', paddingVertical: 4, shadowColor: '#000', shadowOpacity: 0.16, shadowRadius: 9, elevation: 7 }, routeConnector: { flexDirection: 'row', alignItems: 'center', gap: 9, marginLeft: 31, minHeight: 25 }, routeLine: { height: 18, borderLeftWidth: 1, borderStyle: 'dashed', borderColor: '#aaa' }, addPlace: { alignSelf: 'flex-end', paddingHorizontal: 12, paddingVertical: 10, borderRadius: 8, backgroundColor: '#f4f4f4', marginTop: 4 }, commentPanel: { minHeight: 52, flexDirection: 'row', alignItems: 'center', gap: 9, marginVertical: 6, paddingHorizontal: 10, borderRadius: 10, backgroundColor: '#f7f7f7' }, commentAvatar: { width: 28, height: 28, borderRadius: 14, backgroundColor: '#e8d7c8', alignItems: 'center', justifyContent: 'center' }, commentAvatarText: { color: '#444', fontSize: 10, fontWeight: '700' }, commentInput: { flex: 1, minHeight: 40, paddingHorizontal: 8 }, commentSend: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: '#1c1c1c' }, commentEntry: { flexDirection: 'row', alignItems: 'center', gap: 9, marginLeft: 8, marginBottom: 8, padding: 10, borderRadius: 9, backgroundColor: '#f7f7f7' }, commentText: { flex: 1, fontSize: 13 },
  preferenceSuggestion: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10, padding: 12, borderRadius: 10, backgroundColor: '#fff7da' }, preferenceInput: { flexDirection: 'row', alignItems: 'center', marginTop: 14, borderWidth: 1, borderColor: '#e5e5e5', borderRadius: 10 }, preferencePill: { alignSelf: 'flex-start', marginTop: 12, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 16, backgroundColor: '#f0f2ec' }, calendar: { flexDirection: 'row', paddingTop: 12, minWidth: 640 }, calendarHours: { flex: 1, minHeight: 0 }, timeColumn: { width: 64, gap: 0, paddingTop: 45 }, timeLabel: { height: 48, fontSize: 10, color: '#777' }, calendarDay: { flex: 1, minWidth: 130, borderLeftWidth: StyleSheet.hairlineWidth, borderColor: '#ddd' }, calendarDayTitle: { textAlign: 'center', padding: 10, fontWeight: '700' }, alldayEvent: { minHeight: 34, margin: 4, padding: 6, backgroundColor: '#eef1e9', borderRadius: 6, fontSize: 11 }, hourCell: { height: 48, borderTopWidth: StyleSheet.hairlineWidth, borderColor: '#eee', padding: 3 }, calendarEvent: { flex: 1, justifyContent: 'center', padding: 5, borderRadius: 5, backgroundColor: '#e4eadf' }, calendarEventText: { fontSize: 10 }, mapCanvas: { flex: 1, minHeight: 360, overflow: 'hidden', borderRadius: 14, backgroundColor: '#edf0e9' }, mapPark: { position: 'absolute', width: '32%', height: '38%', top: '19%', left: '7%', borderRadius: 80, backgroundColor: '#dce8d4' }, mapLake: { position: 'absolute', width: '24%', height: '18%', top: '64%', left: '57%', borderRadius: 60, backgroundColor: '#d5e5e8' }, terrainMap: { backgroundColor: '#e3eadb' }, mapRoadOne: { position: 'absolute', top: '48%', left: '-10%', width: '120%', height: 20, borderTopWidth: 2, borderBottomWidth: 2, borderColor: 'rgba(255,255,255,0.75)', transform: [{ rotate: '-16deg' }] }, mapRoadTwo: { position: 'absolute', top: '20%', left: '42%', width: 14, height: '100%', borderLeftWidth: 2, borderRightWidth: 2, borderColor: 'rgba(255,255,255,0.75)', transform: [{ rotate: '22deg' }] }, mapPath: { position: 'absolute', left: '20%', top: 100, width: '70%', height: 170, borderWidth: 2, borderStyle: 'dashed', borderColor: '#c2cbb9', borderRadius: 100, transform: [{ rotate: '-18deg' }] }, mapTitle: { position: 'absolute', top: 14, left: 14 }, mapMarker: { position: 'absolute', flexDirection: 'row', alignItems: 'center', gap: 6, transform: [{ translateX: -14 }, { translateY: -14 }] }, markerDot: { width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff', borderWidth: 1, borderColor: '#d6dccc' }, mapCluster: { width: 42, height: 42, borderRadius: 21, alignItems: 'center', justifyContent: 'center', backgroundColor: '#27352a', borderWidth: 4, borderColor: '#c4d1bd' }, selectedMarker: { backgroundColor: '#1c1c1c', borderColor: '#1c1c1c' }, markerIcon: { color: '#263126', fontSize: 13, fontWeight: '700' }, markerIconInverted: { color: '#fff' }, markerLabel: { maxWidth: 130, paddingHorizontal: 7, paddingVertical: 4, borderRadius: 6, backgroundColor: 'rgba(255,255,255,0.9)' }, selectedMarkerLabel: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#1c1c1c' }, markerText: { fontSize: 10 }, mapControls: { position: 'absolute', right: 10, bottom: 38, gap: 5 }, mapControlButton: { minHeight: 36, minWidth: 40, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 9, borderRadius: 8, backgroundColor: '#fff', shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 4, elevation: 2 }, mapSelection: { position: 'absolute', left: 12, bottom: 30, flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, backgroundColor: '#fff' }, mapSelectionText: { fontSize: 12 }, zoomLabel: { position: 'absolute', left: 10, bottom: 8, fontSize: 9, color: '#777' },
  participants: { flexDirection: 'row', alignItems: 'center', gap: 8 }, inviteButton: { backgroundColor: '#fff', borderWidth: StyleSheet.hairlineWidth, borderColor: '#ddd' }, workspaceMenuWrap: { position: 'relative', zIndex: 10 }, workspaceMenu: { position: 'absolute', zIndex: 10, right: 0, top: 38, minWidth: 175, borderRadius: 10, backgroundColor: '#fff', paddingVertical: 4, shadowColor: '#000', shadowOpacity: 0.16, shadowRadius: 9, elevation: 7 }, savedNotes: { padding: 12, marginBottom: 12, borderRadius: 10, backgroundColor: '#f7f7f3', gap: 5 }, notesTitle: { fontSize: 13, fontWeight: '700' }, savedNote: { fontSize: 13 }, actionBackdrop: { flex: 1, padding: 24, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.35)' }, whereDialog: { width: '100%', maxWidth: 420, padding: 22, borderRadius: 22, backgroundColor: '#fff', gap: 14 }, budgetDialog: { width: '100%', maxWidth: 420, padding: 24, borderRadius: 26, backgroundColor: '#fff', gap: 14 }, budgetHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }, budgetHeading: { flex: 1, alignItems: 'center', gap: 2 }, budgetSubtitle: { fontSize: 12 }, budgetOptions: { gap: 8, marginBottom: 6 }, budgetOption: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 2 }, budgetRadio: { width: 21, height: 21, borderRadius: 11, borderWidth: 1, borderColor: '#999', alignItems: 'center', justifyContent: 'center' }, budgetRadioSelected: { borderColor: '#111' }, budgetRadioDot: { width: 11, height: 11, borderRadius: 6, backgroundColor: '#111' }, budgetOptionText: { flexDirection: 'row', alignItems: 'center', gap: 6 }, budgetSymbols: { color: '#171717', fontSize: 15, fontWeight: '600', textDecorationLine: 'underline', textDecorationColor: '#999', textDecorationStyle: 'solid' }, budgetLabel: { color: '#333', fontSize: 15 }, whereHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }, whereTitle: { fontSize: 18, fontWeight: '600' }, whereClose: { width: 24, fontSize: 26, lineHeight: 28, color: '#666' }, whereCloseSpacer: { width: 24 }, whereLocation: { minHeight: 68, flexDirection: 'row', alignItems: 'center', gap: 12, padding: 10, borderRadius: 15, borderWidth: StyleSheet.hairlineWidth, borderColor: '#eee', backgroundColor: '#fafafa' }, whereImage: { width: 46, height: 46, borderRadius: 11 }, wherePin: { width: 46, height: 46, borderRadius: 11, alignItems: 'center', justifyContent: 'center', backgroundColor: '#eee' }, whereLocationText: { flex: 1, gap: 2 }, whereName: { fontSize: 14, fontWeight: '700' }, whereSubtitle: { fontSize: 12 }, whereRemove: { paddingHorizontal: 4, fontSize: 22, color: '#888' }, whereInput: { minHeight: 46, paddingHorizontal: 16, borderWidth: 1, borderColor: '#ccc', borderRadius: 24 }, whereAdd: { alignSelf: 'flex-start', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: '#f2f2f2' }, whereAddText: { fontSize: 12, fontWeight: '600' }, whereSave: { minHeight: 48, alignItems: 'center', justifyContent: 'center', marginTop: 4, borderRadius: 24, backgroundColor: '#111' }, whereSaveDisabled: { backgroundColor: '#ccc' }, whereSaveText: { color: '#fff', fontSize: 14, fontWeight: '600' }, actionDialog: { width: '100%', maxWidth: 420, padding: 22, borderRadius: 16, backgroundColor: '#fff', gap: 12 }, actionTitle: { fontSize: 20, fontWeight: '700' }, actionDescription: { fontSize: 13, lineHeight: 19 }, actionInput: { minHeight: 44, paddingHorizontal: 12, borderWidth: 1, borderColor: '#ddd', borderRadius: 9 }, noteInput: { minHeight: 100, paddingTop: 12, textAlignVertical: 'top' }, actionButtons: { flexDirection: 'row', justifyContent: 'flex-end', alignItems: 'center', gap: 10, marginTop: 4 }, cancelAction: { padding: 10 }, confirmAction: { paddingHorizontal: 15, paddingVertical: 10, borderRadius: 8, backgroundColor: '#1c1c1c' }, confirmActionText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  ...{
    calendarWorkspaceContent: { flexGrow: 1, paddingBottom: 0 },
    calendarWorkspace: { flex: 1, minHeight: 0 },
    detail: { flex: 1, height: Platform.OS === 'web' ? '100vh' as const : undefined, overflow: 'hidden', flexDirection: Platform.OS === 'web' ? 'row' as const : 'column' as const, minHeight: 0, backgroundColor: '#fafbfd' },
    leftPanel: { flex: Platform.OS === 'web' ? 0.92 : 1, minWidth: 0, borderRightWidth: Platform.OS === 'web' ? StyleSheet.hairlineWidth : 0, padding: Platform.OS === 'web' ? 28 : 16, backgroundColor: '#fff' },
    rightPanel: { flex: Platform.OS === 'web' ? 1.08 : 1, minWidth: 0, minHeight: 0, padding: Platform.OS === 'web' ? 28 : 16 },
    detailTitle: { fontSize: 26, fontWeight: '700' as const, letterSpacing: -0.5 },
    alert: { padding: 20, marginTop: 20, borderWidth: 1, borderColor: '#f2dfb6', borderRadius: 16, backgroundColor: '#fff8e9', gap: 10 },
    alertLabel: { fontSize: 11, fontWeight: '700' as const, letterSpacing: 1, color: '#946313' },
    alertText: { fontSize: 15, lineHeight: 23, color: '#4b3714' },
    chatRow: { minHeight: 76, flexDirection: 'row' as const, alignItems: 'center' as const, paddingHorizontal: 14, borderRadius: 12 },
    chatName: { fontSize: 15, fontWeight: '600' as const },
    mainBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: '#171717' },
    mainBadgeText: { fontSize: 10, color: '#fff' },
    updated: { fontSize: 12 },
    workspaceHeader: { alignItems: 'flex-end' as const, paddingBottom: 16, borderBottomWidth: StyleSheet.hairlineWidth },
    workspaceActions: { flexDirection: 'row' as const, gap: 8 },
    utilityButton: { paddingHorizontal: 12, paddingVertical: 9, borderWidth: 1, borderColor: '#e2e5e9', borderRadius: 9, backgroundColor: '#fff' },
    workspaceTabs: { flexGrow: 0, marginVertical: 15 },
    workspaceTabsContent: { gap: 17 },
    tabButton: { paddingHorizontal: 2, paddingVertical: 10, borderBottomWidth: 2, borderBottomColor: 'transparent' },
    activeTab: { backgroundColor: 'transparent', borderBottomColor: '#171717' },
    tabText: { fontSize: 13, color: '#64748b' },
    activeTabText: { color: '#171717' },
    contentHeading: { flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'space-between' as const, marginBottom: 18 },
    workspaceTitle: { fontSize: 24, fontWeight: '700' as const, letterSpacing: -0.4 },
    smallButton: { minHeight: 36, justifyContent: 'center' as const, paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderColor: '#e2e5e9', borderRadius: 9, backgroundColor: '#fff' },
    ideaGrid: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, gap: 20, paddingBottom: 24 },
    ideaCard: { width: Platform.OS === 'web' ? '48%' as const : '100%' as const, minWidth: 170, maxWidth: 520, borderRadius: 16, overflow: 'hidden' as const, backgroundColor: '#fff', borderWidth: StyleSheet.hairlineWidth, borderColor: '#e1e5eb', position: 'relative' as const },
    ideaImage: { width: '100%' as const, height: 180, backgroundColor: '#eee' },
    ideaInfo: { paddingHorizontal: 16, paddingVertical: 14, gap: 4 },
    ideaName: { fontSize: 16, fontWeight: '700' as const },
    addPlaceDialog: { width: '100%', maxWidth: 720, maxHeight: '92%', overflow: 'hidden', borderRadius: 20, backgroundColor: '#fff', shadowColor: '#000', shadowOpacity: 0.2, shadowRadius: 20, elevation: 12 },
    addPlaceHeader: { height: 62, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#eee' },
    addPlaceClose: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center', borderRadius: 18, backgroundColor: '#f7f7f6' },
    addPlaceTitle: { fontSize: 17, fontWeight: '700' as const, color: '#171717' },
    addPlaceBody: { paddingHorizontal: 20 },
    addPlaceTabs: { flexDirection: 'row', gap: 22, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#eee' },
    addPlaceTab: { paddingTop: 16, paddingBottom: 11, borderBottomWidth: 2, borderBottomColor: 'transparent' },
    addPlaceTabActive: { borderBottomColor: '#171717' },
    addPlaceTabText: { color: '#999', fontSize: 13 },
    addPlaceTabTextActive: { color: '#171717', fontWeight: '700' as const },
    addPlaceDestination: { marginTop: 17, color: '#171717', fontSize: 20, fontWeight: '700' as const },
    addPlaceSearchRow: { flexDirection: 'row', alignItems: 'center', gap: 9, marginTop: 14 },
    addPlaceSearch: { flex: 1, minHeight: 43, paddingHorizontal: 16, borderRadius: 24, backgroundColor: '#f4f4f2', fontSize: 13 },
    addPlaceFilter: { minHeight: 40, justifyContent: 'center', paddingHorizontal: 13, borderWidth: 1, borderColor: '#e5e5e5', borderRadius: 22 },
    addPlaceCategories: { gap: 8, paddingTop: 12, paddingBottom: 4 },
    addPlaceCategory: { paddingHorizontal: 15, paddingVertical: 8, borderRadius: 18, backgroundColor: '#f2f2f0' },
    addPlaceCategoryActive: { backgroundColor: '#171717' },
    addPlaceCategoryText: { fontSize: 11, color: '#444', fontWeight: '500' as const },
    addPlaceCategoryTextActive: { color: '#fff', fontWeight: '700' as const },
    addPlaceSectionHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 17, marginBottom: 11 },
    addPlaceSectionTitle: { color: '#171717', fontSize: 16, fontWeight: '700' as const },
    addPlaceCards: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, paddingBottom: 14 },
    addPlaceCard: { width: Platform.OS === 'web' ? '31.5%' as const : '48%' as const, minWidth: 150, flexGrow: 1 },
    addPlaceCardImageWrap: { position: 'relative', aspectRatio: 1, overflow: 'hidden', borderRadius: 12, backgroundColor: '#eee' },
    addPlaceCardImage: { width: '100%', height: '100%' },
    addPlaceCardButton: { position: 'absolute', top: 8, right: 8, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 18, backgroundColor: 'rgba(255,255,255,0.96)' },
    addPlaceCardInfo: { paddingTop: 8, gap: 3 },
    addPlaceRating: { color: '#171717', fontSize: 11, fontWeight: '700' as const },
    addPlaceLocation: { fontSize: 11 },
    addPlaceFooter: { minHeight: 48, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 8, paddingHorizontal: 20, paddingVertical: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#eee', backgroundColor: '#fafaf9' },
    addPlaceFooterLabel: { flexDirection: 'row', alignItems: 'center', gap: 7 },
    addPlaceStatusDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#10a66a' },
    addPlaceScheduleLink: { color: '#444', fontSize: 11, fontWeight: '600' as const, textDecorationLine: 'underline' as const },
    scheduleOverlay: { ...StyleSheet.absoluteFillObject, zIndex: 10, alignItems: 'center', justifyContent: 'center', padding: 20, backgroundColor: 'rgba(0,0,0,0.3)' },
    scheduleDialog: { width: '100%', maxWidth: 400, padding: 22, gap: 11, borderRadius: 18, backgroundColor: '#fff', shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 18, elevation: 10 },
    scheduleActions: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 10, marginTop: 8 },
    renameBackdrop: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.5)' },
    renameDialog: { width: '100%', maxWidth: 640, minHeight: 274, padding: 30, borderRadius: 20, backgroundColor: '#fff', justifyContent: 'space-between' },
    renameClose: { position: 'absolute', left: 28, top: 17, zIndex: 1, padding: 2 },
    renameCloseText: { color: '#111', fontSize: 24, lineHeight: 28 },
    renameTitle: { marginTop: 1, textAlign: 'center', fontSize: 24, fontWeight: '600' },
    renameInput: { minHeight: 50, marginTop: 22, paddingHorizontal: 14, borderWidth: 1, borderColor: '#ccc', borderRadius: 28, outlineStyle: 'none' as any },
    renameSave: { width: 210, minHeight: 50, alignSelf: 'flex-end', alignItems: 'center', justifyContent: 'center', marginTop: 24, borderRadius: 28, backgroundColor: '#050505' },
    renameSaveText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  },
});
