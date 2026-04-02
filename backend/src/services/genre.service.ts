import { normalizeGenre, type GenreBucket } from "../utils/genreMap";
import type { SpotifyTrack, SpotifySimplifiedPlaylist } from "../types/spotify.types";

// ─── Bucketing ────────────────────────────────────────────────────────────────

// Assigns a single genre bucket to a track by looking up all its artists' genres.
// Returns the first non-"Other" bucket found across all artists/genres, or "Other".
export function assignTrackToBucket(
    track: SpotifyTrack,
    artistGenres: Map<string, string[]>
): GenreBucket {
    for (const artist of track.artists) {
        const genres = artistGenres.get(artist.id) ?? [];
        for (const genre of genres) {
            const bucket = normalizeGenre(genre);
            if (bucket !== 'Other') return bucket;
        }
    }
    return 'Other';
}

// Single O(N) pass over all tracks — returns a map of bucket -> tracks in that bucket.
export function buildBucketMap(
    tracks: SpotifyTrack[],
    artistGenres: Map<string, string[]>
): Map<GenreBucket, SpotifyTrack[]> {
    const bucketMap = new Map<GenreBucket, SpotifyTrack[]>();
    for (const track of tracks) {
        const bucket = assignTrackToBucket(track, artistGenres);
        const existing = bucketMap.get(bucket) ?? [];
        existing.push(track);
        bucketMap.set(bucket, existing);
    }
    return bucketMap;
}

// ─── Playlist Matching ────────────────────────────────────────────────────────

// Returns a profile: bucket -> fraction (0–1) of the playlist's tracks in that bucket.
// Returns an empty map if the playlist has no tracks.
export function buildPlaylistGenreProfile(
    tracks: SpotifyTrack[],
    artistGenres: Map<string, string[]>
): Map<GenreBucket, number> {
    const profile = new Map<GenreBucket, number>();
    if (tracks.length === 0) return profile;

    const bucketMap = buildBucketMap(tracks, artistGenres);
    for (const [bucket, bucketTracks] of bucketMap) {
        profile.set(bucket, bucketTracks.length / tracks.length);
    }
    return profile;
}

// Scores each playlist against a bucket and returns the best-matching playlist ID.
// Empty named playlists (no profile data) fall back to name keyword matching.
// Returns null if no playlists provided.
export function matchBucketToPlaylist(
    bucket: GenreBucket,
    playlistProfiles: Map<string, Map<GenreBucket, number>>,
    playlistNames: Map<string, string>
): string | null {
    let bestId: string | null = null;
    let bestScore = -1;

    for (const [playlistId, profile] of playlistProfiles) {
        let score: number;

        if (profile.size === 0) {
            // Empty playlist — fall back to name keyword matching
            const name = (playlistNames.get(playlistId) ?? '').toLowerCase();
            const bucketKeywords = bucket.toLowerCase().split(/[\s/&]+/);
            score = bucketKeywords.some(kw => name.includes(kw)) ? 0.1 : 0;
        } else {
            score = profile.get(bucket) ?? 0;
        }

        if (score > bestScore) {
            bestScore = score;
            bestId = playlistId;
        }
    }

    return bestId;
}

// ─── Playlist Validation ──────────────────────────────────────────────────────

export interface ExcludedPlaylist {
    id: string;
    name: string;
    reason: string;
}

export interface ValidationResult {
    valid: SpotifySimplifiedPlaylist[];
    excluded: ExcludedPlaylist[];
}

// Filters playlists to those the user can sort into:
// - Must have a non-empty name
// - Must be owned by the user or collaborative
export function validateEditablePlaylists(
    playlists: SpotifySimplifiedPlaylist[],
    userId: string
): ValidationResult {
    const valid: SpotifySimplifiedPlaylist[] = [];
    const excluded: ExcludedPlaylist[] = [];

    for (const playlist of playlists) {
        if (!playlist.name || playlist.name.trim() === '') {
            excluded.push({ id: playlist.id, name: playlist.name, reason: 'no name' });
        } else if (playlist.owner.id !== userId && !playlist.collaborative) {
            excluded.push({ id: playlist.id, name: playlist.name, reason: 'not editable' });
        } else {
            valid.push(playlist);
        }
    }

    return { valid, excluded };
}
