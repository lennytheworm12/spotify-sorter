import type {
    SpotifyLikedTrack,
    SpotifyPlaylistItem,
    SpotifyTrack,
} from "../types/spotify.types";

// Tracks that cannot be copied (null, local, unavailable, or malformed) are
// filtered out before sorting. Playable status is unknown unless Spotify
// explicitly returns is_playable === false.
export function isSortableTrack(
    track: SpotifyTrack | null | undefined
): track is SpotifyTrack {
    if (!track) return false;
    if (track.is_local) return false;
    if (track.is_playable === false) return false;
    if (!track.id || !track.uri) return false;
    if (!track.artists || track.artists.length === 0) return false;
    return true;
}

export function likedTracksToSortable(items: SpotifyLikedTrack[]): SpotifyTrack[] {
    return items.map(item => item.track).filter(isSortableTrack);
}

export function playlistTracksToSortable(items: SpotifyPlaylistItem[]): SpotifyTrack[] {
    return items.map(item => item.item).filter(isSortableTrack);
}

// Tracks that can be copied into a backup playlist. Artist metadata is NOT
// required here: a non-local, playable Spotify track with a valid id+URI can
// be copied even when it cannot be genre-sorted.
export function isCopyableTrack(
    track: SpotifyTrack | null | undefined
): track is SpotifyTrack {
    if (!track) return false;
    if (track.is_local) return false;
    if (track.is_playable === false) return false;
    if (!track.id || !track.uri) return false;
    return true;
}

// Derives backup/copyable URIs from playlist items. Source order and
// duplicates are preserved; this is a playlist copy, not a deduped set.
export function playlistTracksToCopyableUris(items: SpotifyPlaylistItem[]): string[] {
    return items
        .map(item => item.item)
        .filter(isCopyableTrack)
        .map(track => track.uri);
}

export function dedupeArtistIds(tracks: SpotifyTrack[]): string[] {
    const ids = new Set<string>();
    for (const track of tracks) {
        for (const artist of track.artists) {
            if (artist.id) ids.add(artist.id);
        }
    }
    return [...ids];
}
