// sort.action.service.test.ts
//
// Unit tests for the user-scoped Redis sort-action store: key scoping,
// latest-pointer behavior, 24-hour TTL, ownership checks, and preserving the
// original expiry when an action is updated after an undo.

jest.mock("../../utils/redis", () => ({
    __esModule: true,
    default: {
        set: jest.fn(),
        get: jest.fn(),
        del: jest.fn(),
    },
}));

import {
    createSortAction,
    getSortAction,
    getLatestSortAction,
    updateSortAction,
    SORT_ACTION_TTL_SECONDS,
} from "../../services/sort.action.service";
import type { SortAction, NewSortActionInput } from "../../types/sortAction.types";

interface MockRedis {
    set: jest.Mock;
    get: jest.Mock;
    del: jest.Mock;
}

const mockRedis = (): MockRedis =>
    (jest.requireMock("../../utils/redis") as { default: MockRedis }).default;

const makeInput = (overrides: Partial<NewSortActionInput> = {}): NewSortActionInput => ({
    spotifyId: "user1",
    destinations: [
        {
            playlistId: "pl1",
            playlistName: "Hip Hop Mix",
            baselineUris: ["spotify:track:base-1"],
            expectedSnapshotId: "snap-sort",
            bucketOrder: ["Hip Hop"],
        },
    ],
    buckets: [
        {
            bucket: "Hip Hop",
            playlistId: "pl1",
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

beforeEach(() => {
    jest.clearAllMocks();
});

describe("createSortAction", () => {
    it("stores the record and latest pointer with a 24-hour TTL", async () => {
        const action = await createSortAction(makeInput());

        expect(action.id).toEqual(expect.any(String));
        expect(action.id.length).toBeGreaterThan(0);
        expect(action.spotifyId).toBe("user1");
        expect(action.createdAt).toEqual(expect.any(String));
        expect(action.expiresAt).toEqual(expect.any(String));
        expect(new Date(action.expiresAt).getTime() - new Date(action.createdAt).getTime())
            .toBe(SORT_ACTION_TTL_SECONDS * 1000);

        const redis = mockRedis();
        expect(redis.set).toHaveBeenCalledTimes(2);
        expect(redis.set).toHaveBeenNthCalledWith(
            1,
            `sort:action:user1:${action.id}`,
            JSON.stringify(action),
            "EX",
            SORT_ACTION_TTL_SECONDS
        );
        expect(redis.set).toHaveBeenNthCalledWith(
            2,
            "sort:action:user1:latest",
            action.id,
            "EX",
            SORT_ACTION_TTL_SECONDS
        );
    });
});

describe("getSortAction", () => {
    it("returns a parsed action for the owning user", async () => {
        const stored: SortAction = {
            id: "action-1",
            spotifyId: "user1",
            createdAt: "2026-08-19T00:00:00.000Z",
            expiresAt: "2026-08-20T00:00:00.000Z",
            destinations: [],
            buckets: [],
        };
        mockRedis().get.mockResolvedValue(JSON.stringify(stored));

        await expect(getSortAction("user1", "action-1")).resolves.toEqual(stored);
        expect(mockRedis().get).toHaveBeenCalledWith("sort:action:user1:action-1");
    });

    it("returns null when no record exists", async () => {
        mockRedis().get.mockResolvedValue(null);

        await expect(getSortAction("user1", "missing")).resolves.toBeNull();
    });

    it("rejects a record that belongs to a different user even if it ends up under the key", async () => {
        const foreign: SortAction = {
            id: "action-1",
            spotifyId: "someone-else",
            createdAt: "2026-08-19T00:00:00.000Z",
            expiresAt: "2026-08-20T00:00:00.000Z",
            destinations: [],
            buckets: [],
        };
        mockRedis().get.mockResolvedValue(JSON.stringify(foreign));

        await expect(getSortAction("user1", "action-1")).resolves.toBeNull();
    });

    it("returns null for malformed JSON", async () => {
        mockRedis().get.mockResolvedValue("{not json");

        await expect(getSortAction("user1", "action-1")).resolves.toBeNull();
    });
});

describe("getLatestSortAction", () => {
    it("follows the latest pointer back to the full action", async () => {
        const stored: SortAction = {
            id: "action-1",
            spotifyId: "user1",
            createdAt: "2026-08-19T00:00:00.000Z",
            expiresAt: "2026-08-20T00:00:00.000Z",
            destinations: [],
            buckets: [],
        };
        mockRedis().get
            .mockResolvedValueOnce("action-1")
            .mockResolvedValueOnce(JSON.stringify(stored));

        await expect(getLatestSortAction("user1")).resolves.toEqual(stored);
        expect(mockRedis().get).toHaveBeenNthCalledWith(1, "sort:action:user1:latest");
        expect(mockRedis().get).toHaveBeenNthCalledWith(2, "sort:action:user1:action-1");
    });

    it("returns null when there is no latest pointer", async () => {
        mockRedis().get.mockResolvedValue(null);

        await expect(getLatestSortAction("user1")).resolves.toBeNull();
        expect(mockRedis().del).not.toHaveBeenCalled();
    });

    it("cleans up a dangling pointer and returns null", async () => {
        mockRedis().get
            .mockResolvedValueOnce("action-gone")
            .mockResolvedValueOnce(null);

        await expect(getLatestSortAction("user1")).resolves.toBeNull();
        expect(mockRedis().del).toHaveBeenCalledWith("sort:action:user1:latest");
    });

    it("ignores a pointer to an action owned by another user", async () => {
        const foreign: SortAction = {
            id: "action-1",
            spotifyId: "someone-else",
            createdAt: "2026-08-19T00:00:00.000Z",
            expiresAt: "2026-08-20T00:00:00.000Z",
            destinations: [],
            buckets: [],
        };
        mockRedis().get
            .mockResolvedValueOnce("action-1")
            .mockResolvedValueOnce(JSON.stringify(foreign));

        await expect(getLatestSortAction("user1")).resolves.toBeNull();
    });
});

describe("updateSortAction", () => {
    afterEach(() => {
        jest.useRealTimers();
    });

    it("preserves the original expiry instead of extending the TTL", async () => {
        jest.useFakeTimers();
        jest.setSystemTime(new Date("2026-08-19T12:00:00.000Z"));

        const action: SortAction = {
            id: "action-1",
            spotifyId: "user1",
            createdAt: "2026-08-19T00:00:00.000Z",
            expiresAt: "2026-08-19T13:00:00.000Z", // one hour left
            destinations: [],
            buckets: [],
        };

        await updateSortAction(action);

        expect(mockRedis().set).toHaveBeenCalledTimes(1);
        expect(mockRedis().set).toHaveBeenCalledWith(
            "sort:action:user1:action-1",
            JSON.stringify(action),
            "EX",
            3600
        );
    });

    it("clamps an already-expired action to a one-second TTL", async () => {
        jest.useFakeTimers();
        jest.setSystemTime(new Date("2026-08-20T12:00:00.000Z"));

        const action: SortAction = {
            id: "action-1",
            spotifyId: "user1",
            createdAt: "2026-08-19T00:00:00.000Z",
            expiresAt: "2026-08-20T00:00:00.000Z", // already in the past
            destinations: [],
            buckets: [],
        };

        await updateSortAction(action);

        expect(mockRedis().set).toHaveBeenCalledWith(
            "sort:action:user1:action-1",
            JSON.stringify(action),
            "EX",
            1
        );
    });
});
