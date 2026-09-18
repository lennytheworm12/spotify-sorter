//file for spotify services like getting user playlists etc
//



import axios from "axios";
import type { SpotifySimplifiedPlaylist, SpotifyUserPlaylistsResponse, SpotifyLikedTrack, SpotifyLikedSongsResponse, SpotifyPlaylistItem, SpotifyPlaylistItemsResponse, SpotifySnapshotResponse } from "../types/spotify.types";

//request to get user playlist

export const getUserPlaylists = async (accessToken: string): Promise<SpotifySimplifiedPlaylist[]> => {
    //asks spotify for user playlist via /v1/me/playlists
    const allPlaylists: SpotifySimplifiedPlaylist[] = [];
    let url = `https://api.spotify.com/v1/me/playlists?limit=50`

    while (url) {
        const response = await axios.get<SpotifyUserPlaylistsResponse>(url, {
            headers: { Authorization: `Bearer ${accessToken}` }
        })
        allPlaylists.push(...response.data.items);
        url = response.data.next ?? ''; //update to the next fetch url
    }
    return allPlaylists;


}



export const getUserLikedSongs = async (accessToken: string): Promise<SpotifyLikedTrack[]> => {

    //gets the user's liked songs through 
    const allTracks: SpotifyLikedTrack[] = [];
    let url = `https://api.spotify.com/v1/me/tracks?limit=50`
    while (url) {
        const response = await axios.get<SpotifyLikedSongsResponse>(url, {
            headers: { Authorization: `Bearer ${accessToken}` }
        })
        allTracks.push(...response.data.items);
        url = response.data.next ?? '';
    }
    return allTracks;


}


//method to get the tracks on a playlist
export const getPlaylistTracks = async (accessToken: string, playlistId: string): Promise<SpotifyPlaylistItem[]> => {
    const allTracks: SpotifyPlaylistItem[] = [];

    let url = `https://api.spotify.com/v1/playlists/${playlistId}/items?limit=50`;

    while (url) {
        const response = await axios.get<SpotifyPlaylistItemsResponse>(url, {
            headers: { Authorization: `Bearer ${accessToken}` }
        })
        allTracks.push(...response.data.items);
        url = response.data.next ?? '';
    }
    return allTracks;
}

// Reads a playlist's current Spotify snapshot id without pulling the full
// playlist object.
export const getPlaylistSnapshot = async (
    accessToken: string,
    playlistId: string
): Promise<string> => {
    const response = await axios.get<SpotifySnapshotResponse>(
        `https://api.spotify.com/v1/playlists/${playlistId}?fields=snapshot_id`,
        { headers: { Authorization: `Bearer ${accessToken}` } }
    );
    return response.data.snapshot_id;
}


// Creates a new playlist for the current user and returns the new playlist ID.
export const createPlaylist = async (
    accessToken: string,
    name: string
): Promise<string> => {
    const response = await axios.post<{ id: string }>(
        `https://api.spotify.com/v1/me/playlists`,
        { name, public: false },
        { headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' } }
    );
    return response.data.id;
}


const TRACK_BATCH_SIZE = 100; // Spotify limit for POST /v1/playlists/{id}/items

// Pacing/retry knobs for playlist writes. Delays are injected via options in
// tests; production callers get the real sleep.
export const BATCH_DELAY_MS = 250;
export const MAX_429_RETRIES = 3;
const BACKOFF_BASE_MS = 250;
const BACKOFF_MAX_MS = 2000;

export const sleep = (ms: number): Promise<void> =>
    new Promise(resolve => setTimeout(resolve, ms));

export interface AddTracksToPlaylistOptions {
    sleep?: (ms: number) => Promise<void>;
}

function isRateLimited(err: unknown): boolean {
    if (typeof err !== "object" || err === null) return false;
    return (err as { response?: { status?: number } }).response?.status === 429;
}

// Returns the delay for a 429 retry. Honors a numeric Retry-After header in
// seconds; otherwise falls back to bounded exponential backoff.
function rateLimitDelayMs(err: unknown, attempt: number): number {
    const maybe = err as {
        response?: { headers?: Record<string, unknown> };
    };
    const retryAfter =
        maybe.response?.headers?.["retry-after"] ??
        maybe.response?.headers?.["Retry-After"];
    if (typeof retryAfter === "string") {
        const seconds = Number(retryAfter);
        if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1000;
    }
    return Math.min(BACKOFF_BASE_MS * 2 ** (attempt - 1), BACKOFF_MAX_MS);
}

async function postBatchWithRetry(
    accessToken: string,
    playlistId: string,
    batch: string[],
    wait: (ms: number) => Promise<void>
): Promise<string> {
    let attempt = 0;
    for (;;) {
        try {
            const response = await axios.post<SpotifySnapshotResponse>(
                `https://api.spotify.com/v1/playlists/${playlistId}/items`,
                { uris: batch },
                { headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' } }
            );
            return response.data.snapshot_id;
        } catch (err) {
            if (!isRateLimited(err) || attempt >= MAX_429_RETRIES) throw err;
            attempt += 1;
            await wait(rateLimitDelayMs(err, attempt));
        }
    }
}

async function putBatchWithRetry(
    accessToken: string,
    playlistId: string,
    batch: string[],
    wait: (ms: number) => Promise<void>
): Promise<string> {
    let attempt = 0;
    for (;;) {
        try {
            const response = await axios.put<SpotifySnapshotResponse>(
                `https://api.spotify.com/v1/playlists/${playlistId}/items`,
                { uris: batch },
                { headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' } }
            );
            return response.data.snapshot_id;
        } catch (err) {
            if (!isRateLimited(err) || attempt >= MAX_429_RETRIES) throw err;
            attempt += 1;
            await wait(rateLimitDelayMs(err, attempt));
        }
    }
}

// Adds track URIs to a playlist in batches of 100. Returns the final
// snapshot id from the last successful add-item response, or undefined when
// there is nothing to add. Existing callers that ignore the return value are
// unaffected.
export const addTracksToPlaylist = async (
    accessToken: string,
    playlistId: string,
    trackUris: string[],
    options: AddTracksToPlaylistOptions = {}
): Promise<string | undefined> => {
    if (trackUris.length === 0) return undefined;

    const wait = options.sleep ?? sleep;
    let snapshot: string | undefined;
    for (let i = 0; i < trackUris.length; i += TRACK_BATCH_SIZE) {
        // Pace batches so consecutive playlist writes do not burst the API.
        // No delay after the final batch.
        if (i > 0) await wait(BATCH_DELAY_MS);
        snapshot = await postBatchWithRetry(
            accessToken,
            playlistId,
            trackUris.slice(i, i + TRACK_BATCH_SIZE),
            wait
        );
    }
    return snapshot;
}

// Replaces a playlist's items with the given URIs: one PUT for the first
// (up to) 100 items — including an empty list, which clears the playlist —
// followed by paced POST batches for the remainder. Returns the final
// snapshot id. 429s are retried with the same discipline as item additions.
export const replacePlaylistItems = async (
    accessToken: string,
    playlistId: string,
    trackUris: string[],
    options: AddTracksToPlaylistOptions = {}
): Promise<string> => {
    const wait = options.sleep ?? sleep;
    const firstBatch = trackUris.slice(0, TRACK_BATCH_SIZE);
    let snapshot = await putBatchWithRetry(accessToken, playlistId, firstBatch, wait);

    const remaining = trackUris.slice(TRACK_BATCH_SIZE);
    if (remaining.length === 0) return snapshot;

    // Pace every follow-up POST so the PUT + POST sequence does not burst the
    // API. No delay after the final batch.
    for (let i = 0; i < remaining.length; i += TRACK_BATCH_SIZE) {
        await wait(BATCH_DELAY_MS);
        snapshot = await postBatchWithRetry(
            accessToken,
            playlistId,
            remaining.slice(i, i + TRACK_BATCH_SIZE),
            wait
        );
    }
    return snapshot;
}
