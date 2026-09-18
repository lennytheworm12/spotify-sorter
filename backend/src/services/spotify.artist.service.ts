import axios from "axios";
import type { SpotifyArtist } from "../types/spotify.types";

const ARTIST_BATCH_SIZE = 50; // Spotify limit for GET /v1/artists

// Fetches full artist objects for the given IDs, batching in groups of 50
// (Spotify's limit for GET /v1/artists). Null entries are skipped.
export const getArtists = async (
    accessToken: string,
    artistIds: string[]
): Promise<SpotifyArtist[]> => {
    const artists: SpotifyArtist[] = [];

    for (let i = 0; i < artistIds.length; i += ARTIST_BATCH_SIZE) {
        const batch = artistIds.slice(i, i + ARTIST_BATCH_SIZE);
        const response = await axios.get<{ artists: (SpotifyArtist | null)[] }>(
            `https://api.spotify.com/v1/artists?ids=${batch.join(',')}`,
            { headers: { Authorization: `Bearer ${accessToken}` } }
        );
        for (const artist of response.data.artists) {
            if (artist) {
                artists.push(artist);
            }
        }
    }

    return artists;
};

// Given a list of artist IDs, returns a map of artistId -> genres[].
// Batches requests in groups of 50.
export const getArtistGenres = async (
    accessToken: string,
    artistIds: string[]
): Promise<Map<string, string[]>> => {
    const genreMap = new Map<string, string[]>();
    const artists = await getArtists(accessToken, artistIds);
    for (const artist of artists) {
        genreMap.set(artist.id, artist.genres);
    }
    return genreMap;
};
