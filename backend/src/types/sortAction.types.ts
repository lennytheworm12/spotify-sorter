// Persisted sort-action types. A sort action records what a single
// `POST /sort` run successfully wrote so the user can later undo selected
// buckets. The snapshot id, not the timestamp, is the actual safety guard.
//
// Access and refresh tokens must never be stored in these records.

import type { TrackSummary } from "../utils/trackFilters";

export type SortActionBucketStatus = "applied" | "undone";

// One destination playlist touched by the sort action. `baselineUris` is the
// exact pre-sort URI list (order and duplicates preserved); `bucketOrder` is
// the order candidate buckets were appended to this destination, and
// `expectedSnapshotId` is the final post-sort Spotify snapshot id.
export interface SortActionDestination {
    playlistId: string;
    playlistName: string;
    baselineUris: string[];
    expectedSnapshotId: string;
    bucketOrder: string[];
}

// One successful candidate bucket addition.
export interface SortActionBucket {
    bucket: string;
    playlistId: string;
    playlistName: string;
    trackUris: string[];
    tracks: TrackSummary[];
    status: SortActionBucketStatus;
}

export interface SortAction {
    id: string;
    spotifyId: string;
    createdAt: string;
    expiresAt: string;
    destinations: SortActionDestination[];
    buckets: SortActionBucket[];
}

export interface NewSortActionInput {
    spotifyId: string;
    destinations: SortActionDestination[];
    buckets: SortActionBucket[];
}
