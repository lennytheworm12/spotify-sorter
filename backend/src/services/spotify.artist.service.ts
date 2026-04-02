import axios from "axios";
import type { SpotifyArtist } from "../types/spotify.types";

const ARTIST_BATCH_SIZE = 50; // Spotify limit for GET /v1/artists

// Given a list of artist IDs, returns a map of artistId -> genres[].
// Batches requests in groups of 50.
export const getArtistGenres = async (
    accessToken: string,
    artistIds: string[]
): Promise<Map<string, string[]>> => {
    const genreMap = new Map<string, string[]>();

    for (let i = 0; i < artistIds.length; i += ARTIST_BATCH_SIZE) {
        const batch = artistIds.slice(i, i + ARTIST_BATCH_SIZE);
        const response = await axios.get<{ artists: SpotifyArtist[] }>(
            `https://api.spotify.com/v1/artists?ids=${batch.join(',')}`,
            { headers: { Authorization: `Bearer ${accessToken}` } }
        );
        for (const artist of response.data.artists) {
            if (artist) {
                genreMap.set(artist.id, artist.genres);
            }
        }
    }

    return genreMap;
};
