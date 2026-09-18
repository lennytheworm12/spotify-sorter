export interface CachedArtist {
    spotifyId: string;
    name: string;
    genres: string[];
    lastFetchedAt: Date;
    createdAt: Date;
    updatedAt: Date;
}
