// MongoDB-backed artist genre cache. Keeps Spotify calls to only missing or
// stale artists and persists genre results for 14 days.
import { ArtistModel } from "../models/Artist";
import { getArtists } from "./spotify.artist.service";
import type { SpotifyArtist } from "../types/spotify.types";
import type { CachedArtist } from "../types/artist.types";

export const ARTIST_CACHE_TTL_MS = 14 * 24 * 60 * 60 * 1000;
const ARTIST_BATCH_SIZE = 50; // Spotify limit — preserved at the cache layer too

// Returns only fresh (non-stale) cached artists for the given IDs.
export async function getFreshCachedArtists(
    artistIds: string[]
): Promise<Map<string, CachedArtist>> {
    const uniqueIds = [...new Set(artistIds)];
    if (uniqueIds.length === 0) return new Map();

    const cutoff = new Date(Date.now() - ARTIST_CACHE_TTL_MS);
    const docs = await ArtistModel.find({
        spotifyId: { $in: uniqueIds },
        lastFetchedAt: { $gte: cutoff },
    });

    const fresh = new Map<string, CachedArtist>();
    for (const doc of docs) {
        fresh.set(doc.spotifyId, doc.toObject());
    }
    return fresh;
}

async function upsertArtists(artists: SpotifyArtist[]): Promise<void> {
    if (artists.length === 0) return;
    const now = new Date();
    await ArtistModel.bulkWrite(
        artists.map(artist => ({
            updateOne: {
                filter: { spotifyId: artist.id },
                update: {
                    $set: {
                        name: artist.name,
                        genres: artist.genres,
                        lastFetchedAt: now,
                    },
                },
                upsert: true,
            },
        }))
    );
}

// Returns artistId -> genres for the requested IDs, reading fresh entries from
// the cache and fetching only missing/stale ones from Spotify (batched by 50).
export async function getArtistGenresCached(
    accessToken: string,
    artistIds: string[]
): Promise<Map<string, string[]>> {
    const uniqueIds = [...new Set(artistIds)].filter(id => id.length > 0);
    if (uniqueIds.length === 0) return new Map();

    const fresh = await getFreshCachedArtists(uniqueIds);
    const genresMap = new Map<string, string[]>();
    for (const [id, doc] of fresh) {
        genresMap.set(id, doc.genres);
    }

    const missing = uniqueIds.filter(id => !fresh.has(id));
    if (missing.length === 0) return genresMap;

    const fetched: SpotifyArtist[] = [];
    for (let i = 0; i < missing.length; i += ARTIST_BATCH_SIZE) {
        const batch = missing.slice(i, i + ARTIST_BATCH_SIZE);
        fetched.push(...(await getArtists(accessToken, batch)));
    }

    await upsertArtists(fetched);
    for (const artist of fetched) {
        genresMap.set(artist.id, artist.genres);
    }
    return genresMap;
}
