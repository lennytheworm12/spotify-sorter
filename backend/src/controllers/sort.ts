import type { Request, Response } from "express";
import { getValidAccessToken } from "../services/token.service";
import { getUserLikedSongs, getPlaylistTracks, createPlaylist, addTracksToPlaylist } from "../services/spotify.playlist.service";
import { getArtistGenres } from "../services/spotify.artist.service";
import { buildBucketMap, buildPlaylistGenreProfile, matchBucketToPlaylist, validateEditablePlaylists } from "../services/genre.service";
import { getUserPlaylists } from "../services/spotify.playlist.service";
import type { SpotifyTrack, SpotifySimplifiedPlaylist } from "../types/spotify.types";
import type { GenreBucket } from "../utils/genreMap";

interface SortBody {
    sourceType: 'liked' | 'playlist';
    playlistId?: string;
    outputMode: 'auto-create' | 'sort-into-existing';
    editablePlaylistIds?: string[];
}

interface BucketResult {
    bucket: GenreBucket;
    playlistId: string;
    playlistName: string;
    tracksAdded: number;
    status: 'success' | 'failed';
    error?: string;
}

export const sort = async (req: Request, res: Response) => {
    const { sourceType, playlistId, outputMode, editablePlaylistIds }: SortBody = req.body;
    const spotifyId = req.user!.spotifyId;

    if (outputMode === 'sort-into-existing' && (!editablePlaylistIds || editablePlaylistIds.length === 0)) {
        return res.status(400).json({ message: 'editablePlaylistIds required for sort-into-existing mode' });
    }
    if (sourceType === 'playlist' && !playlistId) {
        return res.status(400).json({ message: 'playlistId required when sourceType is playlist' });
    }

    try {
        const accessToken = await getValidAccessToken(spotifyId);

        // 1. Fetch source tracks
        let tracks: SpotifyTrack[];
        if (sourceType === 'liked') {
            const likedItems = await getUserLikedSongs(accessToken);
            tracks = likedItems.map(item => item.track);
        } else {
            const playlistItems = await getPlaylistTracks(accessToken, playlistId!);
            tracks = playlistItems.map(item => item.item).filter((t): t is SpotifyTrack => t !== null);
        }

        if (tracks.length === 0) {
            return res.status(200).json({ results: [], excluded: [] });
        }

        // 2. Batch fetch artist genres
        const artistIds = [...new Set(tracks.flatMap(t => t.artists.map(a => a.id)))];
        const artistGenres = await getArtistGenres(accessToken, artistIds);

        // 3. Build bucket map
        const bucketMap = buildBucketMap(tracks, artistGenres);

        const results: BucketResult[] = [];

        if (outputMode === 'auto-create') {
            // Create one playlist per bucket and add tracks
            for (const [bucket, bucketTracks] of bucketMap) {
                const uris = bucketTracks.map(t => t.uri);
                try {
                    const newPlaylistId = await createPlaylist(accessToken, spotifyId, bucket);
                    await addTracksToPlaylist(accessToken, newPlaylistId, uris);
                    results.push({ bucket, playlistId: newPlaylistId, playlistName: bucket, tracksAdded: uris.length, status: 'success' });
                } catch (err) {
                    const message = err instanceof Error ? err.message : 'unknown error';
                    results.push({ bucket, playlistId: '', playlistName: bucket, tracksAdded: 0, status: 'failed', error: message });
                }
            }
        } else {
            // sort-into-existing: build genre profiles for each editable playlist, then match
            const targetPlaylists = await getUserPlaylists(accessToken);
            const selected = targetPlaylists.filter(p => editablePlaylistIds!.includes(p.id));
            const { valid, excluded } = validateEditablePlaylists(selected, spotifyId);

            // Build profiles for each valid playlist
            const playlistProfiles = new Map<string, Map<GenreBucket, number>>();
            const playlistNames = new Map<string, string>();
            for (const playlist of valid) {
                playlistNames.set(playlist.id, playlist.name);
                const ptItems = await getPlaylistTracks(accessToken, playlist.id);
                const ptTracks = ptItems.map(i => i.item).filter((t): t is SpotifyTrack => t !== null);

                // Fetch artist genres for this playlist's tracks if not already cached
                const ptArtistIds = [...new Set(ptTracks.flatMap(t => t.artists.map(a => a.id)))].filter(id => !artistGenres.has(id));
                if (ptArtistIds.length > 0) {
                    const ptGenres = await getArtistGenres(accessToken, ptArtistIds);
                    for (const [id, genres] of ptGenres) artistGenres.set(id, genres);
                }

                playlistProfiles.set(playlist.id, buildPlaylistGenreProfile(ptTracks, artistGenres));
            }

            // Match each bucket to a playlist and write tracks
            for (const [bucket, bucketTracks] of bucketMap) {
                const matchedId = matchBucketToPlaylist(bucket, playlistProfiles, playlistNames);
                if (!matchedId) {
                    results.push({ bucket, playlistId: '', playlistName: '', tracksAdded: 0, status: 'failed', error: 'no matching playlist' });
                    continue;
                }
                const uris = bucketTracks.map(t => t.uri);
                try {
                    await addTracksToPlaylist(accessToken, matchedId, uris);
                    results.push({ bucket, playlistId: matchedId, playlistName: playlistNames.get(matchedId)!, tracksAdded: uris.length, status: 'success' });
                } catch (err) {
                    const message = err instanceof Error ? err.message : 'unknown error';
                    results.push({ bucket, playlistId: matchedId, playlistName: playlistNames.get(matchedId)!, tracksAdded: 0, status: 'failed', error: message });
                }
            }

            return res.status(200).json({ results, excluded });
        }

        return res.status(200).json({ results });
    } catch (error) {
        return res.status(500).json({ message: 'sort failed' });
    }
}
