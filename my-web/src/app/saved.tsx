import { useMemo, useState } from 'react';
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { Pressable, ScrollView, StyleSheet, TextInput, useWindowDimensions, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';

type Category = 'All' | 'Stays' | 'Restaurants' | 'Events' | 'Attractions' | 'Activities' | 'Locations';
type Place = {
  id: string;
  title: string;
  rating: number;
  category: Exclude<Category, 'All'>;
  location: string;
  savedByCount: number;
  imageUrl: string;
  isLiked?: boolean;
  isChecked?: boolean;
};

const CATEGORIES: Category[] = ['All', 'Stays', 'Restaurants', 'Events', 'Attractions', 'Activities', 'Locations'];
const MOCK_PLACES: Place[] = [
  {
    id: '1',
    title: 'Chợ Cũ Tôn Thất Đạm',
    rating: 4.1,
    category: 'Attractions',
    location: 'Phú Hữu, Hồ Chí Minh',
    savedByCount: 2,
    imageUrl: 'https://images.unsplash.com/photo-1555396273-367ea4eb4db5?auto=format&fit=crop&w=900&q=85',
  },
  {
    id: '2',
    title: 'Yersin Park',
    rating: 4.3,
    category: 'Attractions',
    location: 'Đà Lạt, Lâm Đồng',
    savedByCount: 1,
    imageUrl: 'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=900&q=85',
    isLiked: true,
    isChecked: true,
  },
];

export default function SavedScreen() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<Category>('All');
  const { width } = useWindowDimensions();
  const columns = width >= 1120 ? 3 : width >= 700 ? 2 : 1;
  const filteredPlaces = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    return MOCK_PLACES.filter((place) => {
      const matchesCategory = selectedCategory === 'All' || place.category === selectedCategory;
      const matchesSearch = place.title.toLocaleLowerCase().includes(query) || place.location.toLocaleLowerCase().includes(query);
      return matchesCategory && matchesSearch;
    });
  }, [searchQuery, selectedCategory]);

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      <View style={styles.container}>
        <View style={styles.header}>
          <ThemedText style={styles.title}>Your saved places</ThemedText>
          <View style={styles.headerActions}>
            <Pressable style={styles.headerButton} accessibilityRole="button" accessibilityLabel="Map">
              <SymbolView name={{ ios: 'map', android: 'map', web: 'map' }} size={16} tintColor="#171717" />
              <ThemedText style={styles.buttonLabel}>Map</ThemedText>
            </Pressable>
            <Pressable style={styles.headerButton} onPress={() => router.push('/trips')} accessibilityRole="button">
              <SymbolView name={{ ios: 'suitcase.rolling', android: 'work', web: 'work' }} size={16} tintColor="#171717" />
              <ThemedText style={styles.buttonLabel}>Trips</ThemedText>
            </Pressable>
          </View>
        </View>

        <View style={styles.searchWrap}>
          <SymbolView name={{ ios: 'magnifyingglass', android: 'search', web: 'search' }} size={17} tintColor="#777" />
          <TextInput
            accessibilityLabel="Search my saved places"
            placeholder="Search my saved places"
            placeholderTextColor="#858585"
            value={searchQuery}
            onChangeText={setSearchQuery}
            style={styles.searchInput}
            returnKeyType="search"
          />
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>
          {CATEGORIES.map((category) => {
            const active = selectedCategory === category;
            return (
              <Pressable
                key={category}
                onPress={() => setSelectedCategory(category)}
                style={[styles.chip, active && styles.chipActive]}
                accessibilityRole="button"
                accessibilityState={{ selected: active }}>
                <ThemedText style={[styles.chipText, active && styles.chipTextActive]}>{category}</ThemedText>
              </Pressable>
            );
          })}
        </ScrollView>

        {filteredPlaces.length > 0 ? (
          <View style={styles.grid}>
            {filteredPlaces.map((place) => <PlaceCard key={place.id} place={place} columns={columns} />)}
          </View>
        ) : (
          <View style={styles.emptyState}>
            <ThemedText style={styles.emptyTitle}>No saved places found</ThemedText>
            <ThemedText themeColor="textSecondary">Try another search or category.</ThemedText>
          </View>
        )}
      </View>
    </ScrollView>
  );
}

function PlaceCard({ place, columns }: { place: Place; columns: number }) {
  return (
    <View style={[styles.card, columns > 1 && { width: `${100 / columns - 2}%` }]}>
      <View style={styles.imageWrap}>
        <Image source={{ uri: place.imageUrl }} style={styles.image} contentFit="cover" transition={180} />
        <View style={styles.cardActions}>
          {place.isLiked && <View style={styles.iconButton}><ThemedText style={styles.heart}>♥</ThemedText></View>}
          {place.isChecked && <View style={styles.iconButton}><ThemedText style={styles.check}>✓</ThemedText></View>}
          {!place.isLiked && !place.isChecked && <View style={styles.iconButton}><ThemedText style={styles.add}>＋</ThemedText></View>}
        </View>
      </View>
      <View style={styles.cardInfo}>
        <View style={styles.cardHeading}>
          <ThemedText style={styles.cardTitle} numberOfLines={1}>{place.title}</ThemedText>
          <ThemedText style={styles.rating}>★ {place.rating.toFixed(1)}</ThemedText>
        </View>
        <ThemedText style={styles.category}>{place.category}</ThemedText>
        <ThemedText style={styles.location} numberOfLines={1}>{place.location}</ThemedText>
        <ThemedText style={styles.savedBy}>♥  Saved by {place.savedByCount} {place.savedByCount === 1 ? 'person' : 'people'}</ThemedText>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#fff' },
  content: { paddingHorizontal: 32, paddingVertical: 30 },
  container: { width: '100%', maxWidth: 1240, alignSelf: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 16, marginBottom: 22 },
  title: { fontSize: 30, lineHeight: 38, fontWeight: '700', letterSpacing: -0.6 },
  headerActions: { flexDirection: 'row', gap: 10 },
  headerButton: { height: 40, flexDirection: 'row', alignItems: 'center', gap: 7, paddingHorizontal: 15, borderRadius: 22, borderWidth: 1, borderColor: '#e0e0e0', backgroundColor: '#fff' },
  buttonLabel: { fontSize: 13, fontWeight: '600' },
  searchWrap: { minHeight: 46, flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 15, marginBottom: 18, borderRadius: 24, borderWidth: 1, borderColor: '#eaeaea', backgroundColor: '#f7f7f8' },
  searchInput: { flex: 1, minHeight: 44, padding: 0, color: '#171717', fontSize: 14, outlineStyle: 'none' as never },
  filters: { flexDirection: 'row', gap: 9, paddingBottom: 26 },
  chip: { minHeight: 36, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 15, borderRadius: 20, borderWidth: 1, borderColor: '#e0e0e0', backgroundColor: '#fff' },
  chipActive: { backgroundColor: '#171717', borderColor: '#171717' },
  chipText: { fontSize: 12, fontWeight: '600', color: '#333' },
  chipTextActive: { color: '#fff' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 20 },
  card: { flexGrow: 0, flexShrink: 0, marginBottom: 4 },
  imageWrap: { position: 'relative', width: '100%', aspectRatio: 1.48, overflow: 'hidden', borderRadius: 15, backgroundColor: '#eee' },
  image: { width: '100%', height: '100%' },
  cardActions: { position: 'absolute', top: 11, right: 11, flexDirection: 'row', gap: 7 },
  iconButton: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center', borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.92)' },
  heart: { color: '#ef4444', fontSize: 18, lineHeight: 22 },
  check: { color: '#3b82f6', fontSize: 17, fontWeight: '700' },
  add: { color: '#171717', fontSize: 23, lineHeight: 27 },
  cardInfo: { gap: 3, paddingHorizontal: 3, paddingTop: 11 },
  cardHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  cardTitle: { flex: 1, fontSize: 15, lineHeight: 21, fontWeight: '700' },
  rating: { fontSize: 12, fontWeight: '700' },
  category: { color: '#717171', fontSize: 12 },
  location: { color: '#8b8b8b', fontSize: 12, marginBottom: 4 },
  savedBy: { color: '#d84343', fontSize: 11, fontWeight: '500' },
  emptyState: { alignItems: 'center', justifyContent: 'center', paddingVertical: 64, gap: 7 },
  emptyTitle: { fontSize: 17, fontWeight: '700' },
});
