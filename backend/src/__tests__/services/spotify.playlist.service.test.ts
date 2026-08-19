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
} from "../../services/spotify.playlist.service";

jest.mock("axios", () => ({
    get: jest.fn(),
    post: jest.fn(),
}));

import axios from "axios";
const mockAxiosGet = axios.get as jest.Mock;
const mockAxiosPost = axios.post as jest.Mock;

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

describe("addTracksToPlaylist", () => {
    it("batches writes in groups of 100", async () => {
        const uris = Array.from({ length: 250 }, (_, i) => `spotify:track:t${i}`);

        await addTracksToPlaylist("access-token", "pl1", uris);

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

    it("makes no requests for an empty track list", async () => {
        await addTracksToPlaylist("access-token", "pl1", []);
        expect(mockAxiosPost).not.toHaveBeenCalled();
    });
});
