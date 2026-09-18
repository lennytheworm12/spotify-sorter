import type { Request, Response } from "express";
import { getValidAccessToken } from "../services/token.service";
import {
    getUserLikedSongs,
    getPlaylistTracks,
    createPlaylist,
    addTracksToPlaylist,
    getUserPlaylists,
    getPlaylistSnapshot,
} from "../services/spotify.playlist.service";
import { getArtistGenresCached } from "../services/artist.cache.service";
import { buildBucketMap, buildPlaylistGenreProfile, matchBucketToPlaylist, validateEditablePlaylists } from "../services/genre.service";
import { sortRequestSchema } from "../schemas/sort.schema";
import { likedTracksToSortable, playlistTracksToSortable, playlistTracksToCopyableUris, dedupeArtistIds, trackToSummary, type TrackSummary } from "../utils/trackFilters";
import type { SpotifyPlaylistItem, SpotifyTrack, SpotifySimplifiedPlaylist } from "../types/spotify.types";
import type { GenreBucket } from "../utils/genreMap";
import type { ExcludedPlaylist } from "../services/genre.service";
import { createSortAction } from "../services/sort.action.service";
import type { SortActionDestination, SortActionBucket } from "../types/sortAction.types";

interface BucketResult {
    bucket: GenreBucket;
    playlistId: string;
    playlistName: string;
    tracksAdded: number;
    tracks: TrackSummary[];
    status: 'success' | 'failed';
    error?: string;
}

interface BackupResult {
    playlistId: string;
    playlistName: string;
    tracksCopied: number;
    status: 'success';
}

interface DestinationCopyResult {
    sourcePlaylistId: string;
    sourcePlaylistName: string;
    playlistId: string;
    playlistName: string;
    tracksCopied: number;
    status: 'success' | 'failed';
    error?: string;
}

interface BucketAssignment {
    bucket: GenreBucket;
    tracks: SpotifyTrack[];
    originalPlaylistId: string;
}

interface RecordedBucketWrite {
    bucket: GenreBucket;
    playlistId: string;
    playlistName: string;
    trackUris: string[];
    tracks: TrackSummary[];
}

// Direct mode appends candidates to originals, which undo must be able to
// rebuild exactly. A destination is only replay-safe when every original item
// maps to a Web-API-replayable URI (playlistTracksToCopyableUris semantics);
// local/unavailable/null/unplayable/malformed items make it unsafe.
const DIRECT_NOT_REPLAY_SAFE_ERROR =
    "playlist contains items the Spotify Web API cannot replay (local, unavailable, unplayable, or malformed); " +
    "direct modification cannot be safely undone — choose \"Create safe copies\" instead";

export const sort = async (req: Request, res: Response) => {
    const parsed = sortRequestSchema.safeParse(req.body);
    if (!parsed.success) {
        return res.status(400).json({
            message: parsed.error.issues[0]?.message ?? "invalid sort request",
            issues: parsed.error.issues,
        });
    }
    const { sourceType, playlistId, outputMode, editablePlaylistIds, createBackup, existingPlaylistWriteMode, safeCopyNames } = parsed.data;
    const spotifyId = req.user!.spotifyId;

    try {
        const accessToken = await getValidAccessToken(spotifyId);

        // Undo-tracking data collected across the write phases below. Only
        // successful candidate bucket additions are recorded; baselines and
        // expected snapshot ids are final post-sort values.
        const actionBaselines = new Map<string, string[]>();
        const actionSnapshots = new Map<string, string>();
        const actionWrites: RecordedBucketWrite[] = [];

        // Attaches the recorded action to a successful sort response. A Redis
        // persistence failure must never fail an otherwise-successful sort, so
        // it degrades to an explicit warning instead.
        const persistAction = async (base: Record<string, unknown>) => {
            if (actionWrites.length === 0) {
                return res.status(200).json(base);
            }

            // If a write's snapshot wasn't captured (e.g. a zero-length add),
            // read the final state once before recording the action.
            const playlistIds = [...new Set(actionWrites.map(write => write.playlistId))];
            for (const playlistId of playlistIds) {
                if (!actionSnapshots.has(playlistId)) {
                    try {
                        actionSnapshots.set(playlistId, await getPlaylistSnapshot(accessToken, playlistId));
                    } catch (err) {
                        const message = err instanceof Error ? err.message : "unknown error";
                        return res.status(200).json({
                            ...base,
                            actionWarning: `action tracking unavailable: could not read final snapshot for playlist '${playlistId}' (${message})`,
                        });
                    }
                }
            }

            const buckets: SortActionBucket[] = actionWrites.map(write => ({
                bucket: write.bucket,
                playlistId: write.playlistId,
                playlistName: write.playlistName,
                trackUris: write.trackUris,
                tracks: write.tracks,
                status: "applied",
            }));

            const destinations: SortActionDestination[] = [];
            const destinationIndex = new Map<string, number>();
            for (const write of actionWrites) {
                let index = destinationIndex.get(write.playlistId);
                if (index === undefined) {
                    index = destinations.length;
                    destinationIndex.set(write.playlistId, index);
                    destinations.push({
                        playlistId: write.playlistId,
                        playlistName: write.playlistName,
                        baselineUris: actionBaselines.get(write.playlistId) ?? [],
                        expectedSnapshotId: actionSnapshots.get(write.playlistId) ?? "",
                        bucketOrder: [],
                    });
                }
                destinations[index]!.bucketOrder.push(write.bucket);
            }

            try {
                const action = await createSortAction({ spotifyId, destinations, buckets });
                return res.status(200).json({ ...base, action });
            } catch (err) {
                const message = err instanceof Error ? err.message : "unknown error";
                return res.status(200).json({
                    ...base,
                    actionWarning: `action tracking unavailable: ${message}`,
                });
            }
        };

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
            const body = backup ? { results, excluded, backup } : { results, excluded };
            if (outputMode === 'sort-into-existing') {
                // No buckets means no matched destinations, so no clones.
                return res.status(200).json({ ...body, destinationCopies: [] });
            }
            return res.status(200).json(body);
        }

        // 2. Resolve editable target playlists (existing mode only)
        const allArtistIds = new Set(dedupeArtistIds(tracks));
        const validPlaylists: SpotifySimplifiedPlaylist[] = [];
        const playlistTracksByPlaylist = new Map<string, SpotifyTrack[]>();
        const playlistItemsByPlaylist = new Map<string, SpotifyPlaylistItem[]>();

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
                playlistItemsByPlaylist.set(playlist.id, items);
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
                    const snapshot = await addTracksToPlaylist(accessToken, newPlaylistId, uris);
                    actionBaselines.set(newPlaylistId, []);
                    if (snapshot) actionSnapshots.set(newPlaylistId, snapshot);
                    actionWrites.push({
                        bucket,
                        playlistId: newPlaylistId,
                        playlistName: bucket,
                        trackUris: uris,
                        tracks: bucketTracks.map(trackToSummary),
                    });
                    results.push({ bucket, playlistId: newPlaylistId, playlistName: bucket, tracksAdded: uris.length, tracks: bucketTracks.map(trackToSummary), status: 'success' });
                } catch (err) {
                    const message = err instanceof Error ? err.message : 'unknown error';
                    results.push({ bucket, playlistId: '', playlistName: bucket, tracksAdded: 0, tracks: bucketTracks.map(trackToSummary), status: 'failed', error: message });
                }
            }
            return persistAction(backup ? { results, excluded, backup } : { results, excluded });
        }

        // sort-into-existing: build genre profiles for each valid playlist,
        // then determine every bucket-to-original match up front.
        const playlistProfiles = new Map<string, Map<GenreBucket, number>>();
        const playlistNames = new Map<string, string>();
        const playlistById = new Map<string, SpotifySimplifiedPlaylist>();
        for (const playlist of validPlaylists) {
            playlistNames.set(playlist.id, playlist.name);
            playlistById.set(playlist.id, playlist);
            playlistProfiles.set(
                playlist.id,
                buildPlaylistGenreProfile(playlistTracksByPlaylist.get(playlist.id) ?? [], artistGenres)
            );
        }

        const bucketAssignments: BucketAssignment[] = [];
        for (const [bucket, bucketTracks] of bucketMap) {
            const matchedId = matchBucketToPlaylist(bucket, playlistProfiles, playlistNames);
            if (!matchedId) {
                results.push({
                    bucket,
                    playlistId: '',
                    playlistName: '',
                    tracksAdded: 0,
                    tracks: bucketTracks.map(trackToSummary),
                    status: 'failed',
                    error: 'no matching playlist',
                });
                continue;
            }
            bucketAssignments.push({ bucket, tracks: bucketTracks, originalPlaylistId: matchedId });
        }

        if (existingPlaylistWriteMode === 'direct') {
            // Explicit direct mode: append candidates to the selected originals.
            // Undo must be able to rebuild each original exactly, so before any
            // write we verify every assigned destination's full item list is
            // Web-API-replayable. playlistTracksToCopyableUris drops every
            // non-copyable item (local, unavailable/null, unplayable,
            // malformed, unsupported), so the copyable list accounts for every
            // original item in exact order exactly when its length matches the
            // original item count. Safety is computed once per unique
            // destination before any write; unsafe destinations are never
            // written, and every bucket assigned to them fails without touching
            // the playlist.
            const replaySafeBaselines = new Map<string, string[]>();
            const unsafeOriginalIds = new Set<string>();
            for (const assignment of bucketAssignments) {
                const originalId = assignment.originalPlaylistId;
                if (replaySafeBaselines.has(originalId) || unsafeOriginalIds.has(originalId)) continue;
                const originalItems = playlistItemsByPlaylist.get(originalId) ?? [];
                const replaySafeBaseline = playlistTracksToCopyableUris(originalItems);
                if (replaySafeBaseline.length === originalItems.length) {
                    replaySafeBaselines.set(originalId, replaySafeBaseline);
                } else {
                    unsafeOriginalIds.add(originalId);
                }
            }

            for (const assignment of bucketAssignments) {
                const originalId = assignment.originalPlaylistId;
                const originalName = playlistNames.get(originalId)!;
                const replaySafeBaseline = replaySafeBaselines.get(originalId);

                if (replaySafeBaseline === undefined) {
                    results.push({
                        bucket: assignment.bucket,
                        playlistId: originalId,
                        playlistName: originalName,
                        tracksAdded: 0,
                        tracks: assignment.tracks.map(trackToSummary),
                        status: 'failed',
                        error: DIRECT_NOT_REPLAY_SAFE_ERROR,
                    });
                    continue;
                }

                if (!actionBaselines.has(originalId)) {
                    actionBaselines.set(originalId, replaySafeBaseline);
                }
                const uris = assignment.tracks.map(t => t.uri);
                try {
                    const snapshot = await addTracksToPlaylist(accessToken, originalId, uris);
                    if (snapshot) actionSnapshots.set(originalId, snapshot);
                    actionWrites.push({
                        bucket: assignment.bucket,
                        playlistId: originalId,
                        playlistName: originalName,
                        trackUris: uris,
                        tracks: assignment.tracks.map(trackToSummary),
                    });
                    results.push({
                        bucket: assignment.bucket,
                        playlistId: originalId,
                        playlistName: originalName,
                        tracksAdded: uris.length,
                        tracks: assignment.tracks.map(trackToSummary),
                        status: 'success',
                    });
                } catch (err) {
                    const message = err instanceof Error ? err.message : 'unknown error';
                    results.push({
                        bucket: assignment.bucket,
                        playlistId: originalId,
                        playlistName: originalName,
                        tracksAdded: 0,
                        tracks: assignment.tracks.map(trackToSummary),
                        status: 'failed',
                        error: message,
                    });
                }
            }
            return persistAction(backup ? { results, excluded, backup } : { results, excluded });
        }

        // Default copy mode: clone each matched original once, copy its base
        // items into the clone first, then add candidates. Originals are never
        // written. A clone failure fails every bucket assigned to that
        // destination without affecting other destinations.
        const destinationCopies: DestinationCopyResult[] = [];
        const assignmentsByOriginal = new Map<string, BucketAssignment[]>();
        for (const assignment of bucketAssignments) {
            const list = assignmentsByOriginal.get(assignment.originalPlaylistId) ?? [];
            list.push(assignment);
            assignmentsByOriginal.set(assignment.originalPlaylistId, list);
        }

        const cloneIdsByOriginal = new Map<string, string>();
        const cloneNamesByOriginal = new Map<string, string>();
        const cloneErrorsByOriginal = new Map<string, string>();

        for (const [originalId, assignments] of assignmentsByOriginal) {
            const original = playlistById.get(originalId)!;
            // Custom names apply only to actual matched originals (validated
            // keys are selected editable playlists); omitted entries keep the
            // automatic fallback name.
            const cloneName = safeCopyNames?.[originalId] ?? `${original.name} — Spotify Sorter Copy`;
            const baseUris = playlistTracksToCopyableUris(playlistItemsByPlaylist.get(originalId) ?? []);
            let cloneId: string | undefined;
            try {
                cloneId = await createPlaylist(accessToken, cloneName);
                await addTracksToPlaylist(accessToken, cloneId, baseUris);
                actionBaselines.set(cloneId, baseUris);
            } catch (err) {
                const message = err instanceof Error ? err.message : 'unknown error';
                destinationCopies.push({
                    sourcePlaylistId: originalId,
                    sourcePlaylistName: original.name,
                    playlistId: cloneId ?? '',
                    playlistName: cloneName,
                    tracksCopied: 0,
                    status: 'failed',
                    error: message,
                });
                cloneErrorsByOriginal.set(originalId, message);
                continue;
            }
            cloneIdsByOriginal.set(originalId, cloneId);
            cloneNamesByOriginal.set(originalId, cloneName);
            destinationCopies.push({
                sourcePlaylistId: originalId,
                sourcePlaylistName: original.name,
                playlistId: cloneId,
                playlistName: cloneName,
                tracksCopied: baseUris.length,
                status: 'success',
            });
        }

        for (const assignment of bucketAssignments) {
            const cloneError = cloneErrorsByOriginal.get(assignment.originalPlaylistId);
            if (cloneError) {
                const originalName = playlistNames.get(assignment.originalPlaylistId)!;
                results.push({
                    bucket: assignment.bucket,
                    playlistId: '',
                    playlistName: originalName,
                    tracksAdded: 0,
                    tracks: assignment.tracks.map(trackToSummary),
                    status: 'failed',
                    error: cloneError,
                });
                continue;
            }
            const cloneId = cloneIdsByOriginal.get(assignment.originalPlaylistId);
            if (!cloneId) continue;
            const cloneName = cloneNamesByOriginal.get(assignment.originalPlaylistId)!;
            const uris = assignment.tracks.map(t => t.uri);
            try {
                const snapshot = await addTracksToPlaylist(accessToken, cloneId, uris);
                if (snapshot) actionSnapshots.set(cloneId, snapshot);
                actionWrites.push({
                    bucket: assignment.bucket,
                    playlistId: cloneId,
                    playlistName: cloneName,
                    trackUris: uris,
                    tracks: assignment.tracks.map(trackToSummary),
                });
                results.push({
                    bucket: assignment.bucket,
                    playlistId: cloneId,
                    playlistName: cloneName,
                    tracksAdded: uris.length,
                    tracks: assignment.tracks.map(trackToSummary),
                    status: 'success',
                });
            } catch (err) {
                const message = err instanceof Error ? err.message : 'unknown error';
                results.push({
                    bucket: assignment.bucket,
                    playlistId: cloneId,
                    playlistName: cloneName,
                    tracksAdded: 0,
                    tracks: assignment.tracks.map(trackToSummary),
                    status: 'failed',
                    error: message,
                });
            }
        }

        return persistAction(
            backup
                ? { results, excluded, backup, destinationCopies }
                : { results, excluded, destinationCopies }
        );
    } catch (error) {
        return res.status(500).json({ message: 'sort failed' });
    }
}
