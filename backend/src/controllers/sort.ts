import type { Request, Response } from "express";
import { getValidAccessToken } from "../services/token.service";
import {
    getUserLikedSongs,
    getPlaylistTracks,
    createPlaylist,
    addTracksToPlaylist,
    getUserPlaylists,
} from "../services/spotify.playlist.service";
import { getArtistGenresCached } from "../services/artist.cache.service";
import { buildBucketMap, buildPlaylistGenreProfile, matchBucketToPlaylist, validateEditablePlaylists } from "../services/genre.service";
import { sortRequestSchema } from "../schemas/sort.schema";
import { likedTracksToSortable, playlistTracksToSortable, playlistTracksToCopyableUris, dedupeArtistIds } from "../utils/trackFilters";
import type { SpotifyPlaylistItem, SpotifyTrack, SpotifySimplifiedPlaylist } from "../types/spotify.types";
import type { GenreBucket } from "../utils/genreMap";
import type { ExcludedPlaylist } from "../services/genre.service";

interface BucketResult {
    bucket: GenreBucket;
    playlistId: string;
    playlistName: string;
    tracksAdded: number;
    status: 'success' | 'failed';
    error?: string;
}

interface BackupResult {
    playlistId: string;
    playlistName: string;
    tracksCopied: number;
    status: 'success';
}

export const sort = async (req: Request, res: Response) => {
    const parsed = sortRequestSchema.safeParse(req.body);
    if (!parsed.success) {
        return res.status(400).json({
            message: parsed.error.issues[0]?.message ?? "invalid sort request",
            issues: parsed.error.issues,
        });
    }
    const { sourceType, playlistId, outputMode, editablePlaylistIds, createBackup } = parsed.data;
    const spotifyId = req.user!.spotifyId;

    try {
        const accessToken = await getValidAccessToken(spotifyId);

        // 1. Fetch source tracks
        let tracks: SpotifyTrack[];
        let sourcePlaylistItems: SpotifyPlaylistItem[] | undefined;
        if (sourceType === 'liked') {
            const likedItems = await getUserLikedSongs(accessToken);
            tracks = likedTracksToSortable(likedItems);
        } else {
            sourcePlaylistItems = await getPlaylistTracks(accessToken, playlistId!);
            tracks = playlistTracksToSortable(sourcePlaylistItems);
        }

        const excluded: ExcludedPlaylist[] = [];
        const results: BucketResult[] = [];

        // 1b. Optional pre-sort backup (playlist sources only). Create and fill
        // the backup before any artist lookup or genre destination writes; a
        // backup failure aborts the whole sort.
        let backup: BackupResult | undefined;
        let fetchedUserPlaylists: SpotifySimplifiedPlaylist[] | undefined;

        if (createBackup && playlistId) {
            fetchedUserPlaylists = await getUserPlaylists(accessToken);
            const sourcePlaylist = fetchedUserPlaylists.find(p => p.id === playlistId);
            if (!sourcePlaylist) {
                return res.status(404).json({
                    message: `source playlist '${playlistId}' not found; cannot create backup`,
                });
            }
            const backupName = `${sourcePlaylist.name} — Spotify Sorter Backup`;
            const backupUris = playlistTracksToCopyableUris(sourcePlaylistItems ?? []);
            try {
                const backupPlaylistId = await createPlaylist(accessToken, backupName);
                await addTracksToPlaylist(
                    accessToken,
                    backupPlaylistId,
                    backupUris
                );
                backup = {
                    playlistId: backupPlaylistId,
                    playlistName: backupName,
                    tracksCopied: backupUris.length,
                    status: 'success',
                };
            } catch (err) {
                const message = err instanceof Error ? err.message : 'unknown error';
                return res.status(500).json({ message: `backup creation failed: ${message}` });
            }
        }

        if (tracks.length === 0) {
            return res.status(200).json(
                backup ? { results, excluded, backup } : { results, excluded }
            );
        }

        // 2. Resolve editable target playlists (existing mode only)
        const allArtistIds = new Set(dedupeArtistIds(tracks));
        const validPlaylists: SpotifySimplifiedPlaylist[] = [];
        const playlistTracksByPlaylist = new Map<string, SpotifyTrack[]>();

        if (outputMode === 'sort-into-existing') {
            const allPlaylists = fetchedUserPlaylists ?? (await getUserPlaylists(accessToken));
            const selected = allPlaylists.filter(p => editablePlaylistIds!.includes(p.id));
            for (const id of editablePlaylistIds!) {
                if (!selected.some(p => p.id === id)) {
                    excluded.push({ id, name: '', reason: 'not found' });
                }
            }
            const validation = validateEditablePlaylists(selected, spotifyId);
            validPlaylists.push(...validation.valid);
            excluded.push(...validation.excluded);

            for (const playlist of validPlaylists) {
                const items = await getPlaylistTracks(accessToken, playlist.id);
                const ptTracks = playlistTracksToSortable(items);
                playlistTracksByPlaylist.set(playlist.id, ptTracks);
                for (const id of dedupeArtistIds(ptTracks)) {
                    allArtistIds.add(id);
                }
            }
        }

        // 3. Fetch artist genres through the cache (fresh + missing/stale only)
        const artistGenres = await getArtistGenresCached(accessToken, [...allArtistIds]);

        // 4. Build bucket map
        const bucketMap = buildBucketMap(tracks, artistGenres);

        if (outputMode === 'auto-create') {
            // Create one playlist per bucket and add tracks
            for (const [bucket, bucketTracks] of bucketMap) {
                const uris = bucketTracks.map(t => t.uri);
                try {
                    const newPlaylistId = await createPlaylist(accessToken, bucket);
                    await addTracksToPlaylist(accessToken, newPlaylistId, uris);
                    results.push({ bucket, playlistId: newPlaylistId, playlistName: bucket, tracksAdded: uris.length, status: 'success' });
                } catch (err) {
                    const message = err instanceof Error ? err.message : 'unknown error';
                    results.push({ bucket, playlistId: '', playlistName: bucket, tracksAdded: 0, status: 'failed', error: message });
                }
            }
            return res.status(200).json(backup ? { results, excluded, backup } : { results, excluded });
        }

        // sort-into-existing: build genre profiles for each valid playlist, then match
        const playlistProfiles = new Map<string, Map<GenreBucket, number>>();
        const playlistNames = new Map<string, string>();
        for (const playlist of validPlaylists) {
            playlistNames.set(playlist.id, playlist.name);
            playlistProfiles.set(
                playlist.id,
                buildPlaylistGenreProfile(playlistTracksByPlaylist.get(playlist.id) ?? [], artistGenres)
            );
        }

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

        return res.status(200).json(backup ? { results, excluded, backup } : { results, excluded });
    } catch (error) {
        return res.status(500).json({ message: 'sort failed' });
    }
}
