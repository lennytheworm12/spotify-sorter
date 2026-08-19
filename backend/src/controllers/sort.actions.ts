import type { Request, Response } from "express";
import { getValidAccessToken } from "../services/token.service";
import {
    getPlaylistSnapshot,
    replacePlaylistItems,
} from "../services/spotify.playlist.service";
import {
    getLatestSortAction,
    getSortAction,
    updateSortAction,
} from "../services/sort.action.service";
import { undoSortActionSchema } from "../schemas/sort.action.schema";

interface SnapshotConflict {
    playlistId: string;
    playlistName: string;
    expectedSnapshotId: string;
    actualSnapshotId: string;
    buckets: string[];
}

interface UndoneDestination {
    playlistId: string;
    playlistName: string;
    undoneBuckets: string[];
    newSnapshotId: string;
}

interface FailedDestination {
    playlistId: string;
    playlistName: string;
    buckets: string[];
    error: string;
}

// Returns the authenticated user's most recent sort action, 204 when none.
export const getLatestAction = async (req: Request, res: Response) => {
    const spotifyId = req.user!.spotifyId;
    try {
        const action = await getLatestSortAction(spotifyId);
        if (!action) return res.status(204).send();
        return res.status(200).json(action);
    } catch {
        return res.status(500).json({ message: "could not retrieve latest sort action" });
    }
};

// Selectively undoes buckets from a sort action. All affected destinations
// are preflighted against their expected snapshot ids before any write; any
// mismatch aborts the entire operation with 409 and zero playlist writes.
export const undoAction = async (req: Request, res: Response) => {
    const parsed = undoSortActionSchema.safeParse(req.body);
    if (!parsed.success) {
        return res.status(400).json({
            message: parsed.error.issues[0]?.message ?? "invalid undo request",
            issues: parsed.error.issues,
        });
    }

    const spotifyId = req.user!.spotifyId;
    const actionId = req.params.actionId;
    if (!actionId) {
        return res.status(404).json({ message: "sort action not found" });
    }

    try {
        // Fetch strictly under the authenticated user's key: another user's
        // action id resolves to null here and never leaks into the undo.
        const action = await getSortAction(spotifyId, actionId);
        if (!action) {
            return res.status(404).json({ message: "sort action not found" });
        }

        const selected = parsed.data.buckets;
        const bucketByName = new Map(action.buckets.map(bucket => [bucket.bucket, bucket]));

        const unknown = selected.filter(name => !bucketByName.has(name));
        if (unknown.length > 0) {
            return res.status(400).json({
                message: "unknown bucket(s) in undo selection",
                unknown,
            });
        }

        const alreadyUndone = selected.filter(
            name => bucketByName.get(name)!.status === "undone"
        );
        if (alreadyUndone.length > 0) {
            return res.status(400).json({
                message: "bucket(s) already undone",
                alreadyUndone,
            });
        }

        // Group the selection by destination playlist. A destination can be
        // rebuilt exactly once even when several of its buckets are selected.
        const destinationByPlaylist = new Map(
            action.destinations.map(destination => [destination.playlistId, destination])
        );
        const selectedByPlaylist = new Map<string, string[]>();
        for (const name of selected) {
            const bucket = bucketByName.get(name)!;
            const names = selectedByPlaylist.get(bucket.playlistId) ?? [];
            names.push(name);
            selectedByPlaylist.set(bucket.playlistId, names);
        }

        const accessToken = await getValidAccessToken(spotifyId);

        // Preflight: read every selected destination's current snapshot before
        // any write. Any mismatch rejects the whole operation with 409.
        const conflicts: SnapshotConflict[] = [];
        for (const [playlistId, names] of selectedByPlaylist) {
            const destination = destinationByPlaylist.get(playlistId);
            if (!destination) {
                return res.status(500).json({
                    message: `action is missing destination '${playlistId}'`,
                });
            }
            const actualSnapshotId = await getPlaylistSnapshot(accessToken, playlistId);
            if (actualSnapshotId !== destination.expectedSnapshotId) {
                conflicts.push({
                    playlistId: destination.playlistId,
                    playlistName: destination.playlistName,
                    expectedSnapshotId: destination.expectedSnapshotId,
                    actualSnapshotId,
                    buckets: names,
                });
            }
        }
        if (conflicts.length > 0) {
            return res.status(409).json({
                message: "destination playlist changed since the sort action; undo aborted",
                conflicts,
            });
        }

        // All preflights passed: rebuild each affected destination once as
        // baseline + every still-applied bucket except the selection.
        const selectedSet = new Set(selected);
        const undoneDestinations: UndoneDestination[] = [];
        const failedDestinations: FailedDestination[] = [];
        for (const [playlistId, names] of selectedByPlaylist) {
            const destination = destinationByPlaylist.get(playlistId)!;
            const stillApplied = action.buckets.filter(
                bucket =>
                    bucket.playlistId === playlistId &&
                    bucket.status === "applied" &&
                    !selectedSet.has(bucket.bucket)
            );
            const rebuiltUris = [
                ...destination.baselineUris,
                ...stillApplied.flatMap(bucket => bucket.trackUris),
            ];

            try {
                const newSnapshotId = await replacePlaylistItems(
                    accessToken,
                    playlistId,
                    rebuiltUris
                );
                destination.expectedSnapshotId = newSnapshotId;
                for (const bucket of action.buckets) {
                    if (bucket.playlistId === playlistId && selectedSet.has(bucket.bucket)) {
                        bucket.status = "undone";
                    }
                }
                undoneDestinations.push({
                    playlistId: destination.playlistId,
                    playlistName: destination.playlistName,
                    undoneBuckets: names,
                    newSnapshotId,
                });
            } catch (err) {
                const message = err instanceof Error ? err.message : "unknown error";
                failedDestinations.push({
                    playlistId: destination.playlistId,
                    playlistName: destination.playlistName,
                    buckets: names,
                    error: message,
                });
            }
        }

        // Persist only the confirmed state, with the action's original expiry.
        // If persistence fails after successful Spotify writes, the response
        // still reports exactly which destinations were undone.
        let actionPersistWarning: string | undefined;
        try {
            await updateSortAction(action);
        } catch (err) {
            const message = err instanceof Error ? err.message : "unknown error";
            actionPersistWarning =
                `undo succeeded but action state could not be persisted: ${message}`;
        }

        const body: Record<string, unknown> = {
            status: failedDestinations.length > 0 ? "partial" : "complete",
            undoneDestinations,
            action,
        };
        if (failedDestinations.length > 0) {
            body.failedDestinations = failedDestinations;
        }
        if (actionPersistWarning) {
            body.actionPersistWarning = actionPersistWarning;
        }

        return res.status(200).json(body);
    } catch {
        return res.status(500).json({ message: "undo failed" });
    }
};
