export type SuggestedCard = { title: string; detail?: string; tag?: string; image: string }
export const chatService = {
  async inspirations(): Promise<{ trips: SuggestedCard[]; places: SuggestedCard[]; guides: SuggestedCard[] }> {
    return {
      trips: [
        { title: 'Trip to Da Lat', detail: 'Lam Dong Province Â· 4 days in Dec', tag: 'Trip', image: 'photo-1500530855697-b586d89ba3ee' },
        { title: 'Nha Trang', detail: '1 place', tag: 'Collection', image: 'photo-1555396273-367ea4eb4db5' },
        { title: 'Nha Trang in two days', tag: 'Chat', image: 'photo-1511818966892-d7d671e672a2' },
      ],
      places: [
        { title: 'Glow Beer Garden', detail: 'Vietnamese', image: 'photo-1517248135467-4c7edcad34c4' },
        { title: 'Independence Palace', detail: 'Attraction', image: 'photo-1565967511849-76a60a516170' },
        { title: 'Aroma Cocktail Bar', detail: 'Cocktail Bar', image: 'photo-1514933651103-005eec06c04b' },
      ],
      guides: [
        { title: 'Explore Vietnam', image: 'photo-1528127269322-539801943592' },
        { title: 'A night in the city', image: 'photo-1519608487953-e999c86e7455' },
        { title: 'Places to unwind', image: 'photo-1441986300917-64674bd600d8' },
      ],
    }
  },
}

