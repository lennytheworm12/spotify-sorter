// sort.actions.test.ts
//
// Route-level tests for GET /sort/actions/latest and
// POST /sort/actions/:actionId/undo: authentication, snapshot-conflict
// preflight with zero writes, selective rebuild correctness, partial Spotify
// failures, and stored-state consistency.

import express from "express";
import request from "supertest";
import cookieParser from "cookie-parser";
import sortRouter from "../../routes/sort.routes";

jest.mock("../../services/token.service", () => ({
    getValidAccessToken: jest.fn(),
}));

jest.mock("../../services/spotify.playlist.service", () => ({
    getUserLikedSongs: jest.fn(),
    getPlaylistTracks: jest.fn(),
    createPlaylist: jest.fn(),
    addTracksToPlaylist: jest.fn(),
    getUserPlaylists: jest.fn(),
    getPlaylistSnapshot: jest.fn(),
    replacePlaylistItems: jest.fn(),
}));

jest.mock("../../services/artist.cache.service", () => ({
    getArtistGenresCached: jest.fn(),
}));

jest.mock("../../services/sort.action.service", () => ({
    createSortAction: jest.fn(),
    getLatestSortAction: jest.fn(),
    getSortAction: jest.fn(),
    updateSortAction: jest.fn(),
}));

jest.mock("jsonwebtoken", () => ({
    __esModule: true,
    default: {
        verify: jest.fn(),
        sign: jest.fn(),
    },
}));

jest.mock("../../env", () => ({
    env: { JWT_SECRET: "test-secret" },
}));

import jwt from "jsonwebtoken";
import { getValidAccessToken } from "../../services/token.service";
import {
    getPlaylistSnapshot,
    replacePlaylistItems,
} from "../../services/spotify.playlist.service";
import {
    getLatestSortAction,
    getSortAction,
    updateSortAction,
} from "../../services/sort.action.service";
import type { SortAction } from "../../types/sortAction.types";

const mockJwtVerify = jwt.verify as jest.Mock;
const mockGetValidAccessToken = getValidAccessToken as jest.Mock;
const mockGetPlaylistSnapshot = getPlaylistSnapshot as jest.Mock;
const mockReplacePlaylistItems = replacePlaylistItems as jest.Mock;
const mockGetLatestSortAction = getLatestSortAction as jest.Mock;
const mockGetSortAction = getSortAction as jest.Mock;
const mockUpdateSortAction = updateSortAction as jest.Mock;

const app = express();
app.use(express.json());
app.use(cookieParser());
app.use("/sort", sortRouter);

const makeAction = (overrides: Partial<SortAction> = {}): SortAction => ({
    id: "action-1",
    spotifyId: "user1",
    createdAt: "2026-08-19T00:00:00.000Z",
    expiresAt: "2026-08-20T00:00:00.000Z",
    destinations: [
        {
            playlistId: "pl-hiphop",
            playlistName: "Hip Hop Mix",
            baselineUris: ["spotify:track:base-1", "spotify:track:base-1"],
            expectedSnapshotId: "snap-sort",
            bucketOrder: ["Hip Hop"],
        },
    ],
    buckets: [
        {
            bucket: "Hip Hop",
            playlistId: "pl-hiphop",
            playlistName: "Hip Hop Mix",
            trackUris: ["spotify:track:t1"],
            tracks: [
                {
                    id: "t1",
                    name: "Track t1",
                    artists: ["Artist a1"],
                    albumName: "Album",
                    spotifyUrl: "",
                },
            ],
            status: "applied",
        },
    ],
    ...overrides,
});

const twoBucketAction = (): SortAction =>
    makeAction({
        destinations: [
            {
                playlistId: "pl-hiphop",
                playlistName: "Hip Hop Mix",
                baselineUris: ["spotify:track:base-1"],
                expectedSnapshotId: "snap-sort",
                bucketOrder: ["Hip Hop", "Pop"],
            },
        ],
        buckets: [
            {
                bucket: "Hip Hop",
                playlistId: "pl-hiphop",
                playlistName: "Hip Hop Mix",
                trackUris: ["spotify:track:t1"],
                tracks: [],
                status: "applied",
            },
            {
                bucket: "Pop",
                playlistId: "pl-hiphop",
                playlistName: "Hip Hop Mix",
                trackUris: ["spotify:track:t2"],
                tracks: [],
                status: "applied",
            },
        ],
    });

beforeEach(() => {
    jest.clearAllMocks();
    mockJwtVerify.mockReturnValue({ spotifyId: "user1" });
    mockGetValidAccessToken.mockResolvedValue("access-token");
    mockGetPlaylistSnapshot.mockResolvedValue("snap-sort");
    mockReplacePlaylistItems.mockResolvedValue("snap-undone");
    mockUpdateSortAction.mockResolvedValue(undefined);
});

// =============================================================================
// GET /sort/actions/latest
// =============================================================================

describe("GET /sort/actions/latest", () => {
    it("returns the latest action for the authenticated user", async () => {
        const action = makeAction();
        mockGetLatestSortAction.mockResolvedValue(action);

        const res = await request(app)
            .get("/sort/actions/latest")
            .set("Cookie", "jwt=valid");

        expect(res.status).toBe(200);
        expect(res.body).toEqual(action);
        expect(mockGetLatestSortAction).toHaveBeenCalledWith("user1");
    });

    it("returns 204 when there is no latest action", async () => {
        mockGetLatestSortAction.mockResolvedValue(null);

        const res = await request(app)
            .get("/sort/actions/latest")
            .set("Cookie", "jwt=valid");

        expect(res.status).toBe(204);
        expect(res.body).toEqual({});
    });

    it("requires authentication", async () => {
        const res = await request(app).get("/sort/actions/latest");

        expect(res.status).toBe(401);
        expect(mockGetLatestSortAction).not.toHaveBeenCalled();
    });
});

// =============================================================================
// POST /sort/actions/:actionId/undo — validation and ownership
// =============================================================================

describe("POST /sort/actions/:actionId/undo — validation", () => {
    it("rejects a missing buckets body with 400", async () => {
        const res = await request(app)
            .post("/sort/actions/action-1/undo")
            .set("Cookie", "jwt=valid")
            .send({});

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("expected array");
        expect(mockGetSortAction).not.toHaveBeenCalled();
    });

    it("rejects an empty buckets array with 400", async () => {
        const res = await request(app)
            .post("/sort/actions/action-1/undo")
            .set("Cookie", "jwt=valid")
            .send({ buckets: [] });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("at least one bucket");
    });

    it("rejects duplicate bucket names with 400", async () => {
        const res = await request(app)
            .post("/sort/actions/action-1/undo")
            .set("Cookie", "jwt=valid")
            .send({ buckets: ["Hip Hop", "Hip Hop"] });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("duplicates");
    });

    it("returns 404 for an unknown action id", async () => {
        mockGetSortAction.mockResolvedValue(null);

        const res = await request(app)
            .post("/sort/actions/missing/undo")
            .set("Cookie", "jwt=valid")
            .send({ buckets: ["Hip Hop"] });

        expect(res.status).toBe(404);
        expect(mockGetSortAction).toHaveBeenCalledWith("user1", "missing");
    });

    it("rejects a bucket name that does not exist in the action with 400", async () => {
        mockGetSortAction.mockResolvedValue(makeAction());

        const res = await request(app)
            .post("/sort/actions/action-1/undo")
            .set("Cookie", "jwt=valid")
            .send({ buckets: ["Metal"] });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("unknown bucket");
        expect(res.body.unknown).toEqual(["Metal"]);
        expect(mockGetPlaylistSnapshot).not.toHaveBeenCalled();
        expect(mockReplacePlaylistItems).not.toHaveBeenCalled();
    });

    it("rejects an already-undone bucket with 400", async () => {
        mockGetSortAction.mockResolvedValue(
            makeAction({
                buckets: [
                    {
                        bucket: "Hip Hop",
                        playlistId: "pl-hiphop",
                        playlistName: "Hip Hop Mix",
                        trackUris: ["spotify:track:t1"],
                        tracks: [],
                        status: "undone",
                    },
                ],
            })
        );

        const res = await request(app)
            .post("/sort/actions/action-1/undo")
            .set("Cookie", "jwt=valid")
            .send({ buckets: ["Hip Hop"] });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("already undone");
        expect(res.body.alreadyUndone).toEqual(["Hip Hop"]);
        expect(mockGetPlaylistSnapshot).not.toHaveBeenCalled();
        expect(mockReplacePlaylistItems).not.toHaveBeenCalled();
    });

    it("requires authentication", async () => {
        const res = await request(app)
            .post("/sort/actions/action-1/undo")
            .send({ buckets: ["Hip Hop"] });

        expect(res.status).toBe(401);
        expect(mockGetSortAction).not.toHaveBeenCalled();
    });
});

// =============================================================================
// POST /sort/actions/:actionId/undo — successful rebuilds
// =============================================================================

describe("POST /sort/actions/:actionId/undo — success", () => {
    it("rebuilds a single destination as baseline plus remaining applied buckets", async () => {
        const action = twoBucketAction();
        mockGetSortAction.mockResolvedValue(action);

        const res = await request(app)
            .post("/sort/actions/action-1/undo")
            .set("Cookie", "jwt=valid")
            .send({ buckets: ["Hip Hop"] });

        expect(res.status).toBe(200);
        expect(res.body.status).toBe("complete");
        expect(mockGetPlaylistSnapshot).toHaveBeenCalledWith("access-token", "pl-hiphop");
        // Pop is still applied, so it remains after the baseline.
        expect(mockReplacePlaylistItems).toHaveBeenCalledWith("access-token", "pl-hiphop", [
            "spotify:track:base-1",
            "spotify:track:t2",
        ]);
        expect(res.body.undoneDestinations).toEqual([
            {
                playlistId: "pl-hiphop",
                playlistName: "Hip Hop Mix",
                undoneBuckets: ["Hip Hop"],
                newSnapshotId: "snap-undone",
            },
        ]);
        expect(res.body.action.buckets[0].status).toBe("undone");
        expect(res.body.action.buckets[1].status).toBe("applied");
        expect(res.body.action.destinations[0].expectedSnapshotId).toBe("snap-undone");
        expect(mockUpdateSortAction).toHaveBeenCalledWith(res.body.action);
    });

    it("preserves baseline duplicates and undoing the last bucket replaces with the baseline only", async () => {
        const action = makeAction();
        mockGetSortAction.mockResolvedValue(action);

        const res = await request(app)
            .post("/sort/actions/action-1/undo")
            .set("Cookie", "jwt=valid")
            .send({ buckets: ["Hip Hop"] });

        expect(res.status).toBe(200);
        expect(mockReplacePlaylistItems).toHaveBeenCalledWith("access-token", "pl-hiphop", [
            "spotify:track:base-1",
            "spotify:track:base-1",
        ]);
    });

    it("rebuilds each selected destination exactly once when buckets span playlists", async () => {
        const action = makeAction({
            destinations: [
                {
                    playlistId: "pl-hiphop",
                    playlistName: "Hip Hop Mix",
                    baselineUris: ["spotify:track:base-1"],
                    expectedSnapshotId: "snap-sort-1",
                    bucketOrder: ["Hip Hop"],
                },
                {
                    playlistId: "pl-pop",
                    playlistName: "Pop Mix",
                    baselineUris: ["spotify:track:base-2"],
                    expectedSnapshotId: "snap-sort-2",
                    bucketOrder: ["Pop"],
                },
            ],
            buckets: [
                {
                    bucket: "Hip Hop",
                    playlistId: "pl-hiphop",
                    playlistName: "Hip Hop Mix",
                    trackUris: ["spotify:track:t1"],
                    tracks: [],
                    status: "applied",
                },
                {
                    bucket: "Pop",
                    playlistId: "pl-pop",
                    playlistName: "Pop Mix",
                    trackUris: ["spotify:track:t2"],
                    tracks: [],
                    status: "applied",
                },
            ],
        });
        mockGetSortAction.mockResolvedValue(action);
        mockGetPlaylistSnapshot
            .mockResolvedValueOnce("snap-sort-1")
            .mockResolvedValueOnce("snap-sort-2");
        mockReplacePlaylistItems
            .mockResolvedValueOnce("snap-undone-1")
            .mockResolvedValueOnce("snap-undone-2");

        const res = await request(app)
            .post("/sort/actions/action-1/undo")
            .set("Cookie", "jwt=valid")
            .send({ buckets: ["Hip Hop", "Pop"] });

        expect(res.status).toBe(200);
        expect(res.body.status).toBe("complete");
        expect(mockReplacePlaylistItems).toHaveBeenCalledTimes(2);
        expect(mockReplacePlaylistItems).toHaveBeenNthCalledWith(
            1,
            "access-token",
            "pl-hiphop",
            ["spotify:track:base-1"]
        );
        expect(mockReplacePlaylistItems).toHaveBeenNthCalledWith(
            2,
            "access-token",
            "pl-pop",
            ["spotify:track:base-2"]
        );
        expect(res.body.undoneDestinations).toHaveLength(2);
        expect(res.body.action.destinations[0].expectedSnapshotId).toBe("snap-undone-1");
        expect(res.body.action.destinations[1].expectedSnapshotId).toBe("snap-undone-2");
        expect(res.body.action.buckets.every((bucket: { status: string }) => bucket.status === "undone"))
            .toBe(true);
    });
});

// =============================================================================
// Snapshot conflict preflight
// =============================================================================

describe("POST /sort/actions/:actionId/undo — snapshot conflicts", () => {
    it("returns 409 with a conflict payload and performs zero playlist writes on any mismatch", async () => {
        const action = makeAction();
        mockGetSortAction.mockResolvedValue(action);
        mockGetPlaylistSnapshot.mockResolvedValue("snap-someone-else-edited");

        const res = await request(app)
            .post("/sort/actions/action-1/undo")
            .set("Cookie", "jwt=valid")
            .send({ buckets: ["Hip Hop"] });

        expect(res.status).toBe(409);
        expect(res.body.message).toContain("changed since the sort action");
        expect(res.body.conflicts).toEqual([
            {
                playlistId: "pl-hiphop",
                playlistName: "Hip Hop Mix",
                expectedSnapshotId: "snap-sort",
                actualSnapshotId: "snap-someone-else-edited",
                buckets: ["Hip Hop"],
            },
        ]);
        expect(mockReplacePlaylistItems).not.toHaveBeenCalled();
        expect(mockUpdateSortAction).not.toHaveBeenCalled();
        expect(action.buckets[0].status).toBe("applied");
    });

    it("preflights every selected destination before performing any write", async () => {
        const action = makeAction({
            destinations: [
                {
                    playlistId: "pl-hiphop",
                    playlistName: "Hip Hop Mix",
                    baselineUris: ["spotify:track:base-1"],
                    expectedSnapshotId: "snap-sort-1",
                    bucketOrder: ["Hip Hop"],
                },
                {
                    playlistId: "pl-pop",
                    playlistName: "Pop Mix",
                    baselineUris: ["spotify:track:base-2"],
                    expectedSnapshotId: "snap-sort-2",
                    bucketOrder: ["Pop"],
                },
            ],
            buckets: [
                {
                    bucket: "Hip Hop",
                    playlistId: "pl-hiphop",
                    playlistName: "Hip Hop Mix",
                    trackUris: ["spotify:track:t1"],
                    tracks: [],
                    status: "applied",
                },
                {
                    bucket: "Pop",
                    playlistId: "pl-pop",
                    playlistName: "Pop Mix",
                    trackUris: ["spotify:track:t2"],
                    tracks: [],
                    status: "applied",
                },
            ],
        });
        mockGetSortAction.mockResolvedValue(action);
        mockGetPlaylistSnapshot
            .mockResolvedValueOnce("snap-sort-1") // first matches
            .mockResolvedValueOnce("snap-sort-2-edited"); // second conflicts

        const res = await request(app)
            .post("/sort/actions/action-1/undo")
            .set("Cookie", "jwt=valid")
            .send({ buckets: ["Hip Hop", "Pop"] });

        expect(res.status).toBe(409);
        expect(res.body.conflicts).toHaveLength(1);
        expect(res.body.conflicts[0].playlistId).toBe("pl-pop");
        expect(mockGetPlaylistSnapshot).toHaveBeenCalledTimes(2);
        expect(mockReplacePlaylistItems).not.toHaveBeenCalled();
        expect(mockUpdateSortAction).not.toHaveBeenCalled();
        // Neither bucket was marked undone.
        expect(action.buckets[0].status).toBe("applied");
        expect(action.buckets[1].status).toBe("applied");
    });
});

// =============================================================================
// Partial failures and persistence
// =============================================================================

describe("POST /sort/actions/:actionId/undo — failures", () => {
    it("reports an explicit partial result and keeps stored state consistent with confirmed destinations", async () => {
        const action = makeAction({
            destinations: [
                {
                    playlistId: "pl-hiphop",
                    playlistName: "Hip Hop Mix",
                    baselineUris: ["spotify:track:base-1"],
                    expectedSnapshotId: "snap-sort-1",
                    bucketOrder: ["Hip Hop"],
                },
                {
                    playlistId: "pl-pop",
                    playlistName: "Pop Mix",
                    baselineUris: ["spotify:track:base-2"],
                    expectedSnapshotId: "snap-sort-2",
                    bucketOrder: ["Pop"],
                },
            ],
            buckets: [
                {
                    bucket: "Hip Hop",
                    playlistId: "pl-hiphop",
                    playlistName: "Hip Hop Mix",
                    trackUris: ["spotify:track:t1"],
                    tracks: [],
                    status: "applied",
                },
                {
                    bucket: "Pop",
                    playlistId: "pl-pop",
                    playlistName: "Pop Mix",
                    trackUris: ["spotify:track:t2"],
                    tracks: [],
                    status: "applied",
                },
            ],
        });
        mockGetSortAction.mockResolvedValue(action);
        mockGetPlaylistSnapshot
            .mockResolvedValueOnce("snap-sort-1")
            .mockResolvedValueOnce("snap-sort-2");
        mockReplacePlaylistItems
            .mockResolvedValueOnce("snap-undone-1")
            .mockRejectedValueOnce(new Error("Spotify 500"));

        const res = await request(app)
            .post("/sort/actions/action-1/undo")
            .set("Cookie", "jwt=valid")
            .send({ buckets: ["Hip Hop", "Pop"] });

        expect(res.status).toBe(200);
        expect(res.body.status).toBe("partial");
        expect(res.body.undoneDestinations).toEqual([
            {
                playlistId: "pl-hiphop",
                playlistName: "Hip Hop Mix",
                undoneBuckets: ["Hip Hop"],
                newSnapshotId: "snap-undone-1",
            },
        ]);
        expect(res.body.failedDestinations).toEqual([
            {
                playlistId: "pl-pop",
                playlistName: "Pop Mix",
                buckets: ["Pop"],
                error: "Spotify 500",
            },
        ]);
        // Confirmed destination is undone; the failed destination is untouched.
        expect(res.body.action.buckets[0].status).toBe("undone");
        expect(res.body.action.buckets[1].status).toBe("applied");
        expect(res.body.action.destinations[0].expectedSnapshotId).toBe("snap-undone-1");
        expect(res.body.action.destinations[1].expectedSnapshotId).toBe("snap-sort-2");
        expect(mockUpdateSortAction).toHaveBeenCalledWith(res.body.action);
    });

    it("warns when action state cannot be persisted after successful Spotify writes", async () => {
        const action = makeAction();
        mockGetSortAction.mockResolvedValue(action);
        mockUpdateSortAction.mockRejectedValue(new Error("redis down"));

        const res = await request(app)
            .post("/sort/actions/action-1/undo")
            .set("Cookie", "jwt=valid")
            .send({ buckets: ["Hip Hop"] });

        expect(res.status).toBe(200);
        expect(res.body.status).toBe("complete");
        expect(res.body.actionPersistWarning).toContain("could not be persisted");
        expect(res.body.action.buckets[0].status).toBe("undone");
        expect(mockReplacePlaylistItems).toHaveBeenCalledTimes(1);
    });
});
