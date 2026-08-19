// User-scoped Redis persistence for undoable sort actions.
//
// Each action is stored under `sort:action:<spotifyId>:<actionId>` and a
// per-user latest pointer under `sort:action:<spotifyId>:latest`. Actions
// expire after 24 hours. Updating an action (after an undo) preserves its
// original expiry rather than extending the TTL.

import { randomUUID } from "crypto";
import type Redis from "ioredis";
import redis from "../utils/redis";
import type {
    SortAction,
    SortActionBucketStatus,
    NewSortActionInput,
} from "../types/sortAction.types";

export const SORT_ACTION_TTL_SECONDS = 86400;

const actionKey = (spotifyId: string, actionId: string): string =>
    `sort:action:${spotifyId}:${actionId}`;

const latestKey = (spotifyId: string): string =>
    `sort:action:${spotifyId}:latest`;

function parseSortAction(raw: string, expectedSpotifyId: string): SortAction | null {
    let parsed: unknown;
    try {
        parsed = JSON.parse(raw);
    } catch {
        return null;
    }
    if (!parsed || typeof parsed !== "object") return null;

    const candidate = parsed as Partial<SortAction>;
    if (typeof candidate.id !== "string" || candidate.id.length === 0) return null;
    // The key already scopes by user; this is a defense against a record
    // belonging to another user ending up under the wrong key.
    if (candidate.spotifyId !== expectedSpotifyId) return null;
    if (typeof candidate.createdAt !== "string") return null;
    if (typeof candidate.expiresAt !== "string") return null;
    if (!Array.isArray(candidate.destinations)) return null;
    if (!Array.isArray(candidate.buckets)) return null;
    return candidate as SortAction;
}

function validStatus(value: unknown): value is SortActionBucketStatus {
    return value === "applied" || value === "undone";
}

// Creates and persists a new action, pointing the user's latest pointer at it.
// Returns the fully materialized record (including id and timestamps).
export const createSortAction = async (
    input: NewSortActionInput,
    client: Redis = redis
): Promise<SortAction> => {
    const now = Date.now();
    const action: SortAction = {
        id: randomUUID(),
        spotifyId: input.spotifyId,
        createdAt: new Date(now).toISOString(),
        expiresAt: new Date(now + SORT_ACTION_TTL_SECONDS * 1000).toISOString(),
        destinations: input.destinations,
        buckets: input.buckets.map(bucket => ({
            ...bucket,
            status: validStatus(bucket.status) ? bucket.status : "applied",
        })),
    };

    await client.set(
        actionKey(action.spotifyId, action.id),
        JSON.stringify(action),
        "EX",
        SORT_ACTION_TTL_SECONDS
    );
    await client.set(
        latestKey(action.spotifyId),
        action.id,
        "EX",
        SORT_ACTION_TTL_SECONDS
    );
    return action;
};

// Fetches an action strictly under the authenticated user's key. Returns null
// when the record is absent, malformed, or belongs to a different user.
export const getSortAction = async (
    spotifyId: string,
    actionId: string,
    client: Redis = redis
): Promise<SortAction | null> => {
    const raw = await client.get(actionKey(spotifyId, actionId));
    if (!raw) return null;
    return parseSortAction(raw, spotifyId);
};

// Follows the user-scoped latest pointer to the most recent sort action.
// Returns null when there is no action (including a dangling pointer to an
// expired record, which is cleaned up best-effort).
export const getLatestSortAction = async (
    spotifyId: string,
    client: Redis = redis
): Promise<SortAction | null> => {
    const pointer = latestKey(spotifyId);
    const actionId = await client.get(pointer);
    if (!actionId) return null;

    const action = await getSortAction(spotifyId, actionId, client);
    if (action) return action;

    try {
        await client.del(pointer);
    } catch {
        // Cleanup is best-effort; a stale pointer still resolves to null.
    }
    return null;
};

// Persists an updated action without extending its original 24-hour expiry.
export const updateSortAction = async (
    action: SortAction,
    client: Redis = redis
): Promise<void> => {
    const expiresAtMs = new Date(action.expiresAt).getTime();
    const remainingMs = expiresAtMs - Date.now();
    // Clamp to at least one second so an in-flight update never writes a key
    // that Redis expires in the same instant.
    const remainingSeconds = Math.max(1, Math.ceil(remainingMs / 1000));
    await client.set(
        actionKey(action.spotifyId, action.id),
        JSON.stringify(action),
        "EX",
        remainingSeconds
    );
};
