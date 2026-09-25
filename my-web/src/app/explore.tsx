import { Image } from 'expo-image';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SymbolView } from 'expo-symbols';

const categories = ['For you', 'Experiences', 'Restaurants', 'Stays', 'Locations', 'Guides'];
const places = [
  { name: 'Hon Chong Promontory', rating: '4.8', category: 'Scenic viewpoint · Vĩnh Phước', mentions: 'Mentioned by Linh and 8 others', image: 'photo-1500530855697-b586d89ba3ee' },
  { name: 'Po Nagar Cham Towers', rating: '4.7', category: 'Historic site · Vĩnh Phước', mentions: 'Mentioned by Alex and 5 others', image: 'photo-1564013799919-ab600027ffc6' },
  { name: 'Nha Trang Beach', rating: '4.9', category: 'Beach · Lộc Thọ', mentions: 'Mentioned by 12 travelers', image: 'photo-1507525428034-b723cf961d3e' },
  { name: 'Long Son Pagoda', rating: '4.6', category: 'Temple · Phương Sơn', mentions: 'Mentioned by Mai and 4 others', image: 'photo-1548013146-72479768bada' },
];

export default function ExplorePage() {
  const [selectedCategory, setSelectedCategory] = useState('For you');
  const [favorites, setFavorites] = useState<string[]>([]);
  const [query, setQuery] = useState('');
  const shownPlaces = places.filter((place) => place.name.toLowerCase().includes(query.toLowerCase()));

  return (
    <View style={styles.page}>
      <ScrollView style={styles.results} contentContainerStyle={styles.resultsContent} showsVerticalScrollIndicator={false}>
        <View style={styles.headingRow}>
          <Pressable style={styles.destination} accessibilityRole="button">
            <Text style={styles.destinationText}>Nha Trang</Text>
            <SymbolView name={{ ios: 'chevron.down', android: 'keyboard_arrow_down', web: 'keyboard_arrow_down' }} tintColor="#171717" size={16} />
          </Pressable>
          <Pressable style={styles.profile} accessibilityLabel="Profile"><Text style={styles.profileText}>L</Text></Pressable>
        </View>

        <View style={styles.searchRow}>
          <View style={styles.searchBox}>
            <SymbolView name={{ ios: 'magnifyingglass', android: 'search', web: 'search' }} tintColor="#777" size={18} />
            <TextInput value={query} onChangeText={setQuery} placeholder="Search" placeholderTextColor="#888" style={styles.searchInput} />
            {query.length > 0 && <Pressable onPress={() => setQuery('')}><SymbolView name={{ ios: 'xmark.circle.fill', android: 'cancel', web: 'cancel' }} tintColor="#999" size={17} /></Pressable>}
          </View>
          <Pressable style={styles.filterButton} accessibilityRole="button">
            <SymbolView name={{ ios: 'slider.horizontal.3', android: 'tune', web: 'tune' }} tintColor="#171717" size={17} />
            <Text style={styles.filterText}>Filters</Text>
          </Pressable>
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.categoryRow}>
          {categories.map((category) => <Pressable key={category} onPress={() => setSelectedCategory(category)} style={[styles.categoryPill, selectedCategory === category && styles.categoryActive]}><Text style={[styles.categoryText, selectedCategory === category && styles.categoryTextActive]}>{category}</Text></Pressable>)}
        </ScrollView>

        <View style={styles.sectionTitleRow}><Text style={styles.sectionTitle}>Experiences</Text><Pressable accessibilityRole="button"><Text style={styles.seeAll}>See all</Text></Pressable></View>
        <View style={styles.grid}>
          {shownPlaces.map((place, index) => {
            const saved = favorites.includes(place.name);
            return <View key={place.name} style={styles.card}>
              <View style={styles.imageWrap}>
                <Image source={{ uri: `https://images.unsplash.com/${place.image}?auto=format&fit=crop&w=850&q=85` }} style={styles.cardImage} contentFit="cover" transition={180} />
                <View style={styles.cardActions}>
                  <Pressable style={styles.roundAction} onPress={() => setFavorites((current) => saved ? current.filter((item) => item !== place.name) : [...current, place.name])} accessibilityLabel={saved ? 'Remove from saved' : 'Save place'}>
                    <SymbolView name={{ ios: saved ? 'heart.fill' : 'heart', android: 'favorite', web: 'favorite' }} tintColor={saved ? '#e34e4e' : '#222'} size={17} />
                  </Pressable>
                  <Pressable style={styles.roundAction} accessibilityLabel="Add to trip"><SymbolView name={{ ios: 'plus', android: 'add', web: 'add' }} tintColor="#222" size={18} /></Pressable>
                </View>
                {index === 0 && <View style={styles.photoTag}><Text style={styles.photoTagText}>Popular</Text></View>}
              </View>
              <View style={styles.cardTitleRow}><Text style={styles.placeName} numberOfLines={1}>{place.name}</Text><Text style={styles.rating}>★ {place.rating}</Text></View>
              <Text style={styles.placeCategory} numberOfLines={1}>{place.category}</Text>
              <View style={styles.mentionRow}><View style={styles.avatarStack}><Text style={styles.avatar}>L</Text><Text style={[styles.avatar, styles.avatarSecond]}>A</Text></View><Text style={styles.mentionText} numberOfLines={1}>{place.mentions}</Text></View>
            </View>;
          })}
          {shownPlaces.length === 0 && <Text style={styles.emptyText}>No places match “{query}”.</Text>}
        </View>
      </ScrollView>
      <ExploreMap />
    </View>
  );
}

function ExploreMap() {
  return <View style={styles.map}>
    <View style={styles.mapWater} />
    <View style={[styles.road, styles.roadOne]} /><View style={[styles.road, styles.roadTwo]} /><View style={[styles.road, styles.roadThree]} /><View style={[styles.road, styles.roadFour]} />
    <View style={[styles.road, styles.roadFive]} /><View style={[styles.road, styles.roadSix]} />
    <Text style={[styles.mapLabel, { top: '22%', left: '28%' }]}>VĨNH PHƯỚC</Text><Text style={[styles.mapLabel, { top: '50%', left: '36%' }]}>NHA TRANG</Text><Text style={[styles.mapLabel, { top: '78%', left: '22%' }]}>LỘC THỌ</Text>
    <MapMarker style={{ top: '24%', left: '47%' }} label="Po Nagar Cham Towers" color="#222" />
    <MapMarker style={{ top: '42%', left: '62%' }} label="Hon Chong" color="#fff" selected />
    <MapMarker style={{ top: '61%', left: '42%' }} label="Nha Trang Beach" color="#222" />
    <MapMarker style={{ top: '76%', left: '56%' }} label="Long Son Pagoda" color="#222" />
    <View style={styles.mapControls}><Pressable style={styles.mapControl}><SymbolView name={{ ios: 'plus', android: 'add', web: 'add' }} tintColor="#222" size={18} /></Pressable><View style={styles.controlDivider} /><Pressable style={styles.mapControl}><SymbolView name={{ ios: 'minus', android: 'remove', web: 'remove' }} tintColor="#222" size={18} /></Pressable></View>
    <Pressable style={styles.locateButton} accessibilityLabel="Show my location"><SymbolView name={{ ios: 'location.north.fill', android: 'my_location', web: 'my_location' }} tintColor="#222" size={18} /></Pressable>
    <View style={styles.mapAttribution}><Text style={styles.attributionText}>Map data © OpenStreetMap</Text></View>
  </View>;
}

function MapMarker({ style, label, color, selected = false }: { style: object; label: string; color: string; selected?: boolean }) {
  return <View style={[styles.marker, style]}>
    <View style={[styles.markerPin, selected && styles.markerPinSelected]}><SymbolView name={{ ios: 'mappin', android: 'location_on', web: 'location_on' }} tintColor={color} size={selected ? 22 : 19} /></View>
    {selected && <View style={styles.mapCallout}><Text style={styles.calloutName}>{label}</Text><Text style={styles.calloutMeta}>Top pick · 4.8 ★</Text></View>}
  </View>;
}

const styles = StyleSheet.create({
  page: { flex: 1, flexDirection: 'row', backgroundColor: '#fff', overflow: 'hidden' },
  results: { width: '52%', flexGrow: 0, flexShrink: 0, backgroundColor: '#fff' },
  resultsContent: { paddingHorizontal: 30, paddingTop: 25, paddingBottom: 34 },
  headingRow: { height: 42, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 },
  destination: { flexDirection: 'row', gap: 7, alignItems: 'center' }, destinationText: { color: '#171717', fontSize: 25, fontWeight: '700', letterSpacing: -0.6 },
  profile: { width: 32, height: 32, borderRadius: 16, backgroundColor: '#e6ded1', alignItems: 'center', justifyContent: 'center' }, profileText: { color: '#443d33', fontSize: 13, fontWeight: '700' },
  searchRow: { flexDirection: 'row', gap: 10, marginBottom: 19 }, searchBox: { height: 44, flex: 1, borderRadius: 10, borderWidth: 1, borderColor: '#dedede', flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 13 }, searchInput: { flex: 1, padding: 0, color: '#222', fontSize: 14, outlineStyle: 'none' as any },
  filterButton: { height: 44, paddingHorizontal: 14, borderRadius: 10, borderWidth: 1, borderColor: '#dedede', flexDirection: 'row', alignItems: 'center', gap: 8 }, filterText: { fontSize: 13, color: '#222', fontWeight: '600' },
  categoryRow: { gap: 8, paddingBottom: 24 }, categoryPill: { height: 34, paddingHorizontal: 15, alignItems: 'center', justifyContent: 'center', borderRadius: 20, backgroundColor: '#f4f4f3' }, categoryActive: { backgroundColor: '#171717' }, categoryText: { fontSize: 12, color: '#444', fontWeight: '600' }, categoryTextActive: { color: '#fff' },
  sectionTitleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 13 }, sectionTitle: { fontSize: 19, fontWeight: '700', color: '#191919', letterSpacing: -0.25 }, seeAll: { fontSize: 12, fontWeight: '600', color: '#555' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', rowGap: 22 }, card: { width: '48.4%', minWidth: 0 }, imageWrap: { width: '100%', aspectRatio: 1.22, borderRadius: 12, overflow: 'hidden', backgroundColor: '#e8e5df' }, cardImage: { width: '100%', height: '100%' }, cardActions: { position: 'absolute', top: 9, right: 9, flexDirection: 'row', gap: 6 }, roundAction: { width: 31, height: 31, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.96)' }, photoTag: { position: 'absolute', left: 9, bottom: 9, paddingHorizontal: 9, paddingVertical: 5, backgroundColor: 'rgba(255,255,255,0.94)', borderRadius: 12 }, photoTagText: { color: '#292929', fontSize: 10, fontWeight: '700' },
  cardTitleRow: { marginTop: 9, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 6 }, placeName: { flex: 1, color: '#222', fontSize: 13, fontWeight: '700' }, rating: { color: '#333', fontSize: 11, fontWeight: '600' }, placeCategory: { color: '#737373', fontSize: 11, marginTop: 4 }, mentionRow: { flexDirection: 'row', alignItems: 'center', gap: 7, marginTop: 9 }, avatarStack: { flexDirection: 'row' }, avatar: { width: 19, height: 19, overflow: 'hidden', textAlign: 'center', textAlignVertical: 'center', borderRadius: 10, backgroundColor: '#d6ddd3', color: '#445043', fontSize: 9, fontWeight: '700', borderWidth: 1, borderColor: '#fff' }, avatarSecond: { marginLeft: -5, backgroundColor: '#e9d4bf', color: '#655244' }, mentionText: { flex: 1, color: '#777', fontSize: 10 }, emptyText: { paddingVertical: 24, color: '#777', fontSize: 14 },
  map: { flex: 1, height: '100%', overflow: 'hidden', position: 'relative', backgroundColor: '#f1f0e9' }, mapWater: { position: 'absolute', width: '40%', height: '125%', right: '-7%', top: '-10%', borderTopLeftRadius: 150, borderBottomLeftRadius: 170, backgroundColor: '#d9e9e8', transform: [{ rotate: '8deg' }] },
  road: { position: 'absolute', height: 6, backgroundColor: '#fff', borderTopWidth: 1, borderBottomWidth: 1, borderColor: '#e5e2d8' }, roadOne: { width: '118%', top: '39%', left: '-7%', transform: [{ rotate: '-18deg' }] }, roadTwo: { width: '120%', top: '62%', left: '-8%', transform: [{ rotate: '13deg' }] }, roadThree: { width: '100%', top: '25%', left: '2%', transform: [{ rotate: '57deg' }] }, roadFour: { width: '100%', top: '70%', left: '15%', transform: [{ rotate: '-52deg' }] }, roadFive: { width: '100%', top: '48%', left: '-20%', transform: [{ rotate: '70deg' }] }, roadSix: { width: '95%', top: '82%', left: '10%', transform: [{ rotate: '40deg' }] },
  mapLabel: { position: 'absolute', color: '#9c9a8c', fontSize: 10, letterSpacing: 1.2, fontWeight: '600' }, marker: { position: 'absolute', alignItems: 'center' }, markerPin: { width: 35, height: 35, borderRadius: 18, backgroundColor: '#fff', alignItems: 'center', justifyContent: 'center', shadowColor: '#000', shadowOpacity: 0.16, shadowRadius: 5, elevation: 3 }, markerPinSelected: { width: 42, height: 42, borderRadius: 22, borderWidth: 2, borderColor: '#fff', backgroundColor: '#181818' }, mapCallout: { position: 'absolute', top: -56, left: 27, width: 156, paddingHorizontal: 11, paddingVertical: 9, borderRadius: 9, backgroundColor: '#fff', shadowColor: '#000', shadowOpacity: 0.14, shadowRadius: 8, elevation: 4 }, calloutName: { color: '#222', fontSize: 11, fontWeight: '700' }, calloutMeta: { marginTop: 3, color: '#777', fontSize: 10 },
  mapControls: { position: 'absolute', right: 18, top: 20, width: 38, borderRadius: 9, backgroundColor: '#fff', shadowColor: '#000', shadowOpacity: 0.14, shadowRadius: 8, elevation: 3 }, mapControl: { height: 38, alignItems: 'center', justifyContent: 'center' }, controlDivider: { height: StyleSheet.hairlineWidth, backgroundColor: '#e5e5e5' }, locateButton: { position: 'absolute', right: 18, top: 112, width: 38, height: 38, borderRadius: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff', shadowColor: '#000', shadowOpacity: 0.14, shadowRadius: 8, elevation: 3 }, mapAttribution: { position: 'absolute', bottom: 5, right: 8 }, attributionText: { color: '#737373', fontSize: 8 },
});
