// spotify.playlist.service.test.ts
//
// Thin axios-wrapper tests for the playlist/library data-access layer:
// paginated reads via the `next` pointer, playlist creation, and 100-item
// batched writes.

import {
    getUserPlaylists,
    getUserLikedSongs,
    getPlaylistTracks,
    createPlaylist,
    addTracksToPlaylist,
    getPlaylistSnapshot,
    replacePlaylistItems,
    BATCH_DELAY_MS,
    MAX_429_RETRIES,
} from "../../services/spotify.playlist.service";

jest.mock("axios", () => ({
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
}));

import axios from "axios";
const mockAxiosGet = axios.get as jest.Mock;
const mockAxiosPost = axios.post as jest.Mock;
const mockAxiosPut = axios.put as jest.Mock;

const authHeader = { headers: { Authorization: "Bearer access-token" } };

const makeItem = (id: string) => ({
    added_at: null,
    added_by: null,
    is_local: false,
    item: { id, uri: `spotify:track:${id}` },
});

beforeEach(() => {
    jest.clearAllMocks();
});

describe("getUserPlaylists", () => {
    it("follows the next pointer until pagination is exhausted", async () => {
        mockAxiosGet
            .mockResolvedValueOnce({
                data: {
                    items: [{ id: "pl1" }, { id: "pl2" }],
                    next: "https://api.spotify.com/v1/me/playlists?offset=50&limit=50",
                },
            })
            .mockResolvedValueOnce({
                data: {
                    items: [{ id: "pl3" }],
                    next: null,
                },
            });

        const result = await getUserPlaylists("access-token");

        expect(result.map(p => p.id)).toEqual(["pl1", "pl2", "pl3"]);
        expect(mockAxiosGet).toHaveBeenCalledTimes(2);
        expect(mockAxiosGet).toHaveBeenNthCalledWith(
            1,
            "https://api.spotify.com/v1/me/playlists?limit=50",
            authHeader
        );
        expect(mockAxiosGet).toHaveBeenNthCalledWith(
            2,
            "https://api.spotify.com/v1/me/playlists?offset=50&limit=50",
            authHeader
        );
    });
});

describe("getUserLikedSongs", () => {
    it("follows the next pointer until pagination is exhausted", async () => {
        mockAxiosGet
            .mockResolvedValueOnce({
                data: {
                    items: [makeItem("t1")],
                    next: "https://api.spotify.com/v1/me/tracks?offset=50&limit=50",
                },
            })
            .mockResolvedValueOnce({
                data: {
                    items: [makeItem("t2")],
                    next: null,
                },
            });

        const result = await getUserLikedSongs("access-token");

        expect(result).toHaveLength(2);
        expect(mockAxiosGet).toHaveBeenCalledTimes(2);
        expect(mockAxiosGet).toHaveBeenNthCalledWith(
            1,
            "https://api.spotify.com/v1/me/tracks?limit=50",
            authHeader
        );
    });
});

describe("getPlaylistTracks", () => {
    it("paginates playlist items and keeps null items (caller filters)", async () => {
        mockAxiosGet
            .mockResolvedValueOnce({
                data: {
                    items: [makeItem("t1")],
                    next: "https://api.spotify.com/v1/playlists/pl1/items?offset=50&limit=50",
                },
            })
            .mockResolvedValueOnce({
                data: {
                    items: [null],
                    next: null,
                },
            });

        const result = await getPlaylistTracks("access-token", "pl1");

        expect(result).toHaveLength(2);
        expect(mockAxiosGet).toHaveBeenNthCalledWith(
            1,
            "https://api.spotify.com/v1/playlists/pl1/items?limit=50",
            authHeader
        );
    });
});

describe("createPlaylist", () => {
    it("posts a private playlist and returns its id", async () => {
        mockAxiosPost.mockResolvedValue({ data: { id: "new-pl" } });

        const result = await createPlaylist("access-token", "Hip Hop");

        expect(result).toBe("new-pl");
        expect(mockAxiosPost).toHaveBeenCalledWith(
            "https://api.spotify.com/v1/me/playlists",
            { name: "Hip Hop", public: false },
            { headers: { Authorization: "Bearer access-token", "Content-Type": "application/json" } }
        );
    });
});

describe("getPlaylistSnapshot", () => {
    it("reads only the snapshot_id field", async () => {
        mockAxiosGet.mockResolvedValue({ data: { snapshot_id: "snap-now" } });

        const result = await getPlaylistSnapshot("access-token", "pl1");

        expect(result).toBe("snap-now");
        expect(mockAxiosGet).toHaveBeenCalledWith(
            "https://api.spotify.com/v1/playlists/pl1?fields=snapshot_id",
            authHeader
        );
    });
});

describe("addTracksToPlaylist", () => {
    it("batches writes in groups of 100", async () => {
        const uris = Array.from({ length: 250 }, (_, i) => `spotify:track:t${i}`);
        const mockSleep = jest.fn().mockResolvedValue(undefined);

        await addTracksToPlaylist("access-token", "pl1", uris, { sleep: mockSleep });

        expect(mockAxiosPost).toHaveBeenCalledTimes(3);
        const callArgs = mockAxiosPost.mock.calls;
        expect((callArgs[0][1] as { uris: string[] }).uris).toHaveLength(100);
        expect((callArgs[1][1] as { uris: string[] }).uris).toHaveLength(100);
        expect((callArgs[2][1] as { uris: string[] }).uris).toHaveLength(50);
        expect((callArgs[0][1] as { uris: string[] }).uris[0]).toBe("spotify:track:t0");
        expect((callArgs[2][1] as { uris: string[] }).uris[49]).toBe("spotify:track:t249");
        expect(mockAxiosPost).toHaveBeenCalledWith(
            "https://api.spotify.com/v1/playlists/pl1/items",
            expect.any(Object),
            { headers: { Authorization: "Bearer access-token", "Content-Type": "application/json" } }
        );
    });

    it("paces batches with the configured delay and never sleeps after the final batch", async () => {
        const uris = Array.from({ length: 250 }, (_, i) => `spotify:track:t${i}`);
        const mockSleep = jest.fn().mockResolvedValue(undefined);

        await addTracksToPlaylist("access-token", "pl1", uris, { sleep: mockSleep });

        expect(mockSleep).toHaveBeenCalledTimes(2); // between batches 1->2 and 2->3 only
        expect(mockSleep).toHaveBeenNthCalledWith(1, BATCH_DELAY_MS);
        expect(mockSleep).toHaveBeenNthCalledWith(2, BATCH_DELAY_MS);
    });

    it("does not sleep for a single batch", async () => {
        const mockSleep = jest.fn().mockResolvedValue(undefined);

        await addTracksToPlaylist("access-token", "pl1", ["spotify:track:t1"], { sleep: mockSleep });

        expect(mockAxiosPost).toHaveBeenCalledTimes(1);
        expect(mockSleep).not.toHaveBeenCalled();
    });

    it("makes no requests for an empty track list", async () => {
        const result = await addTracksToPlaylist("access-token", "pl1", []);
        expect(result).toBeUndefined();
        expect(mockAxiosPost).not.toHaveBeenCalled();
    });

    it("returns the snapshot id from the final successful batch", async () => {
        const uris = Array.from({ length: 250 }, (_, i) => `spotify:track:t${i}`);
        mockAxiosPost
            .mockResolvedValueOnce({ data: { snapshot_id: "snap-batch-1" } })
            .mockResolvedValueOnce({ data: { snapshot_id: "snap-batch-2" } })
            .mockResolvedValueOnce({ data: { snapshot_id: "snap-batch-3" } });

        const result = await addTracksToPlaylist("access-token", "pl1", uris, {
            sleep: jest.fn().mockResolvedValue(undefined),
        });

        expect(result).toBe("snap-batch-3");
        expect(mockAxiosPost).toHaveBeenCalledTimes(3);
    });

    it("retries a 429 batch, honoring Retry-After seconds", async () => {
        const mockSleep = jest.fn().mockResolvedValue(undefined);
        mockAxiosPost
            .mockRejectedValueOnce({
                response: { status: 429, headers: { "retry-after": "2" } },
            })
            .mockRejectedValueOnce({
                response: { status: 429, headers: { "Retry-After": "1" } },
            })
            .mockResolvedValueOnce({ data: {} });

        await addTracksToPlaylist("access-token", "pl1", ["spotify:track:t1"], { sleep: mockSleep });

        expect(mockAxiosPost).toHaveBeenCalledTimes(3);
        expect(mockSleep).toHaveBeenCalledTimes(2);
        expect(mockSleep).toHaveBeenNthCalledWith(1, 2000);
        expect(mockSleep).toHaveBeenNthCalledWith(2, 1000);
    });

    it("uses bounded exponential backoff when Retry-After is absent or invalid", async () => {
        const mockSleep = jest.fn().mockResolvedValue(undefined);
        mockAxiosPost
            .mockRejectedValueOnce({
                response: { status: 429, headers: { "retry-after": "later" } },
            })
            .mockRejectedValueOnce({
                response: { status: 429, headers: {} },
            })
            .mockResolvedValueOnce({ data: {} });

        await addTracksToPlaylist("access-token", "pl1", ["spotify:track:t1"], { sleep: mockSleep });

        expect(mockAxiosPost).toHaveBeenCalledTimes(3);
        expect(mockSleep).toHaveBeenNthCalledWith(1, 250);
        expect(mockSleep).toHaveBeenNthCalledWith(2, 500);
    });

    it("gives up after the bounded retry count on persistent 429s", async () => {
        const mockSleep = jest.fn().mockResolvedValue(undefined);
        mockAxiosPost.mockRejectedValue({
            response: { status: 429, headers: {} },
        });

        await expect(
            addTracksToPlaylist("access-token", "pl1", ["spotify:track:t1"], { sleep: mockSleep })
        ).rejects.toEqual({ response: { status: 429, headers: {} } });

        expect(mockAxiosPost).toHaveBeenCalledTimes(1 + MAX_429_RETRIES);
        expect(mockSleep).toHaveBeenCalledTimes(MAX_429_RETRIES);
        expect(mockSleep).toHaveBeenNthCalledWith(1, 250);
        expect(mockSleep).toHaveBeenNthCalledWith(2, 500);
        expect(mockSleep).toHaveBeenNthCalledWith(3, 1000);
    });

    it("does not retry non-429 errors", async () => {
        const mockSleep = jest.fn().mockResolvedValue(undefined);
        mockAxiosPost.mockRejectedValue({ response: { status: 500 } });

        await expect(
            addTracksToPlaylist("access-token", "pl1", ["spotify:track:t1"], { sleep: mockSleep })
        ).rejects.toEqual({ response: { status: 500 } });

        expect(mockAxiosPost).toHaveBeenCalledTimes(1);
        expect(mockSleep).not.toHaveBeenCalled();
    });
});

describe("replacePlaylistItems", () => {
    it("puts an empty list to clear the playlist and returns its snapshot", async () => {
        mockAxiosPut.mockResolvedValue({ data: { snapshot_id: "snap-empty" } });

        const result = await replacePlaylistItems("access-token", "pl1", []);

        expect(result).toBe("snap-empty");
        expect(mockAxiosPut).toHaveBeenCalledWith(
            "https://api.spotify.com/v1/playlists/pl1/items",
            { uris: [] },
            { headers: { Authorization: "Bearer access-token", "Content-Type": "application/json" } }
        );
        expect(mockAxiosPost).not.toHaveBeenCalled();
    });

    it("uses a single PUT when the list fits in one batch", async () => {
        const uris = Array.from({ length: 50 }, (_, i) => `spotify:track:t${i}`);
        mockAxiosPut.mockResolvedValue({ data: { snapshot_id: "snap-put" } });

        const result = await replacePlaylistItems("access-token", "pl1", uris);

        expect(result).toBe("snap-put");
        expect(mockAxiosPut).toHaveBeenCalledTimes(1);
        expect((mockAxiosPut.mock.calls[0][1] as { uris: string[] }).uris).toHaveLength(50);
        expect(mockAxiosPost).not.toHaveBeenCalled();
    });

    it("puts the first 100 then paces follow-up POST batches, returning the final snapshot", async () => {
        const uris = Array.from({ length: 250 }, (_, i) => `spotify:track:t${i}`);
        const mockSleep = jest.fn().mockResolvedValue(undefined);
        mockAxiosPut.mockResolvedValue({ data: { snapshot_id: "snap-put" } });
        mockAxiosPost
            .mockResolvedValueOnce({ data: { snapshot_id: "snap-post-1" } })
            .mockResolvedValueOnce({ data: { snapshot_id: "snap-post-2" } });

        const result = await replacePlaylistItems("access-token", "pl1", uris, {
            sleep: mockSleep,
        });

        expect(result).toBe("snap-post-2");
        expect(mockAxiosPut).toHaveBeenCalledTimes(1);
        expect((mockAxiosPut.mock.calls[0][1] as { uris: string[] }).uris).toEqual(
            uris.slice(0, 100)
        );
        expect(mockAxiosPost).toHaveBeenCalledTimes(2);
        expect((mockAxiosPost.mock.calls[0][1] as { uris: string[] }).uris).toEqual(
            uris.slice(100, 200)
        );
        expect((mockAxiosPost.mock.calls[1][1] as { uris: string[] }).uris).toEqual(
            uris.slice(200)
        );
        expect(mockSleep).toHaveBeenCalledTimes(2);
        expect(mockSleep).toHaveBeenNthCalledWith(1, BATCH_DELAY_MS);
        expect(mockSleep).toHaveBeenNthCalledWith(2, BATCH_DELAY_MS);
    });

    it("retries a 429 PUT with the shared backoff discipline before pacing the POSTs", async () => {
        const uris = Array.from({ length: 150 }, (_, i) => `spotify:track:t${i}`);
        const mockSleep = jest.fn().mockResolvedValue(undefined);
        mockAxiosPut
            .mockRejectedValueOnce({ response: { status: 429, headers: {} } })
            .mockResolvedValueOnce({ data: { snapshot_id: "snap-put" } });
        mockAxiosPost.mockResolvedValue({ data: { snapshot_id: "snap-post" } });

        const result = await replacePlaylistItems("access-token", "pl1", uris, {
            sleep: mockSleep,
        });

        expect(result).toBe("snap-post");
        expect(mockAxiosPut).toHaveBeenCalledTimes(2);
        expect(mockAxiosPost).toHaveBeenCalledTimes(1);
        expect(mockSleep).toHaveBeenCalledTimes(2);
        expect(mockSleep).toHaveBeenNthCalledWith(1, 250); // 429 backoff
        expect(mockSleep).toHaveBeenNthCalledWith(2, BATCH_DELAY_MS); // pacing
    });

    it("gives up after the bounded retry count on a persistent PUT 429 without any POSTs", async () => {
        const mockSleep = jest.fn().mockResolvedValue(undefined);
        mockAxiosPut.mockRejectedValue({ response: { status: 429, headers: {} } });

        await expect(
            replacePlaylistItems("access-token", "pl1", ["spotify:track:t1"], { sleep: mockSleep })
        ).rejects.toEqual({ response: { status: 429, headers: {} } });

        expect(mockAxiosPut).toHaveBeenCalledTimes(1 + MAX_429_RETRIES);
        expect(mockAxiosPost).not.toHaveBeenCalled();
    });
});
