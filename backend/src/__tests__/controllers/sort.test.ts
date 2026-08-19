// sort.test.ts
//
// End-to-end-ish controller tests for POST /sort. The Spotify data-access
// layer, token orchestration, and artist cache are mocked; the genre
// bucketing/matching logic is real.

import express from "express";
import request from "supertest";
import cookieParser from "cookie-parser";
import { sort } from "../../controllers/sort";
import { verifyUser } from "../../middleware/auth.middleware";

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

import {
    getUserLikedSongs,
    getPlaylistTracks,
    createPlaylist,
    addTracksToPlaylist,
    getUserPlaylists,
    getPlaylistSnapshot,
    replacePlaylistItems,
} from "../../services/spotify.playlist.service";
import { getArtistGenresCached } from "../../services/artist.cache.service";
import { createSortAction } from "../../services/sort.action.service";
import jwt from "jsonwebtoken";
import type { SpotifyTrack, SpotifySimplifiedPlaylist } from "../../types/spotify.types";

const mockGetUserLikedSongs = getUserLikedSongs as jest.Mock;
const mockGetPlaylistTracks = getPlaylistTracks as jest.Mock;
const mockCreatePlaylist = createPlaylist as jest.Mock;
const mockAddTracksToPlaylist = addTracksToPlaylist as jest.Mock;
const mockGetUserPlaylists = getUserPlaylists as jest.Mock;
const mockGetArtistGenresCached = getArtistGenresCached as jest.Mock;
const mockGetPlaylistSnapshot = getPlaylistSnapshot as jest.Mock;
const mockReplacePlaylistItems = replacePlaylistItems as jest.Mock;
const mockCreateSortAction = createSortAction as jest.Mock;
const mockJwtVerify = jwt.verify as jest.Mock;

const app = express();
app.use(express.json());
app.use(cookieParser());
app.post("/sort", verifyUser, sort);

// ─── Fixtures ────────────────────────────────────────────────────────────────

const makeTrack = (id: string, artistIds: string[], overrides: Partial<SpotifyTrack> = {}): SpotifyTrack => ({
    id,
    name: `Track ${id}`,
    duration_ms: 200000,
    explicit: false,
    track_number: 1,
    disc_number: 1,
    is_local: false,
    album: {
        id: "album1", name: "Album", album_type: "album", total_tracks: 10,
        release_date: "2020-01-01", release_date_precision: "day",
        images: [], artists: [], external_urls: { spotify: "" },
        href: "", uri: "spotify:album:album1", type: "album",
    },
    artists: artistIds.map(aid => ({
        id: aid, name: `Artist ${aid}`, href: "", uri: `spotify:artist:${aid}`,
        external_urls: { spotify: "" }, type: "artist" as const,
    })),
    external_urls: { spotify: "" },
    href: "",
    uri: `spotify:track:${id}`,
    type: "track" as const,
    ...overrides,
});

const makePlaylist = (id: string, name: string, ownerId: string, collaborative = false): SpotifySimplifiedPlaylist => ({
    id,
    name,
    description: null,
    collaborative,
    public: false,
    snapshot_id: "snap",
    images: [],
    external_urls: { spotify: "" },
    href: "",
    uri: `spotify:playlist:${id}`,
    type: "playlist",
    owner: { id: ownerId, href: "", uri: "", external_urls: { spotify: "" }, type: "user" },
    items: { href: "", total: 0 },
});

const likedItem = (track: SpotifyTrack) => ({ added_at: "2024-01-01T00:00:00Z", track });
const playlistItem = (track: SpotifyTrack | null) => ({
    added_at: null,
    added_by: null,
    is_local: false,
    item: track,
});

const DEFAULT_GENRES = new Map<string, string[]>([
    ["a1", ["hip hop"]],
    ["a2", ["pop"]],
    ["t-a1", ["hip hop"]],
    ["t-a2", ["pop"]],
]);

beforeEach(() => {
    jest.clearAllMocks();
    mockJwtVerify.mockReturnValue({ spotifyId: "user1" });
    (jest.requireMock("../../services/token.service").getValidAccessToken as jest.Mock).mockResolvedValue("access-token");
    mockGetArtistGenresCached.mockResolvedValue(new Map(DEFAULT_GENRES));
    mockCreatePlaylist.mockResolvedValue("new-playlist");
    mockAddTracksToPlaylist.mockResolvedValue(undefined);
    mockGetUserPlaylists.mockResolvedValue([]);
    mockGetPlaylistTracks.mockResolvedValue([]);
    mockGetPlaylistSnapshot.mockResolvedValue("snap-final");
    mockReplacePlaylistItems.mockResolvedValue("snap-undone");
    mockCreateSortAction.mockImplementation(async (input: { spotifyId: string; destinations: unknown[]; buckets: unknown[] }) => ({
        id: "action-1",
        spotifyId: input.spotifyId,
        createdAt: "2026-08-19T00:00:00.000Z",
        expiresAt: "2026-08-20T00:00:00.000Z",
        destinations: input.destinations,
        buckets: input.buckets,
    }));
});

// =============================================================================
// Validation (Zod)
// =============================================================================

describe("POST /sort — validation", () => {
    it("returns 400 for an invalid sourceType", async () => {
        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "radio", outputMode: "auto-create" });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("sourceType");
    });

    it("returns 400 for an invalid outputMode", async () => {
        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "magic" });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("outputMode");
    });

    it("returns 400 when playlistId is missing for a playlist source", async () => {
        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "playlist", outputMode: "auto-create" });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("playlistId is required");
    });

    it("returns 400 when editablePlaylistIds are missing for sort-into-existing", async () => {
        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "sort-into-existing" });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("editablePlaylistIds");
    });

    it("returns 400 when editablePlaylistIds is an empty array", async () => {
        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "sort-into-existing", editablePlaylistIds: [] });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("editablePlaylistIds");
    });

    it("returns 400 for createBackup on a liked source before any token/Spotify calls", async () => {
        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "auto-create", createBackup: true });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("createBackup");
        expect(jest.requireMock("../../services/token.service").getValidAccessToken).not.toHaveBeenCalled();
        expect(mockGetUserLikedSongs).not.toHaveBeenCalled();
    });

    it("returns 400 when the source playlist is also a destination, before any token/Spotify calls", async () => {
        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "playlist",
                playlistId: "src-pl",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["src-pl", "pl-hiphop"],
            });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("source playlist cannot be a destination");
        expect(jest.requireMock("../../services/token.service").getValidAccessToken).not.toHaveBeenCalled();
        expect(mockGetPlaylistTracks).not.toHaveBeenCalled();
    });

    it("rejects existingPlaylistWriteMode for auto-create before any token/Spotify calls", async () => {
        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "auto-create",
                existingPlaylistWriteMode: "direct",
            });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("existingPlaylistWriteMode is only valid");
        expect(jest.requireMock("../../services/token.service").getValidAccessToken).not.toHaveBeenCalled();
        expect(mockGetUserLikedSongs).not.toHaveBeenCalled();
    });

    it("returns 400 for a blank safeCopyNames value before any token/Spotify calls", async () => {
        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-hiphop"],
                safeCopyNames: { "pl-hiphop": "   " },
            });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("safe copy name must not be blank");
        expect(jest.requireMock("../../services/token.service").getValidAccessToken).not.toHaveBeenCalled();
        expect(mockGetUserLikedSongs).not.toHaveBeenCalled();
    });

    it("returns 400 for a >100 character safeCopyNames value before any token/Spotify calls", async () => {
        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-hiphop"],
                safeCopyNames: { "pl-hiphop": "x".repeat(101) },
            });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("at most 100 characters");
        expect(jest.requireMock("../../services/token.service").getValidAccessToken).not.toHaveBeenCalled();
        expect(mockGetUserLikedSongs).not.toHaveBeenCalled();
    });

    it("returns 400 when a safeCopyNames key is not in editablePlaylistIds, before any token/Spotify calls", async () => {
        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-hiphop"],
                safeCopyNames: { "pl-other": "Custom Name" },
            });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("'pl-other' is not in editablePlaylistIds");
        expect(jest.requireMock("../../services/token.service").getValidAccessToken).not.toHaveBeenCalled();
        expect(mockGetUserLikedSongs).not.toHaveBeenCalled();
    });

    it("rejects safeCopyNames for auto-create before any token/Spotify calls", async () => {
        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "auto-create",
                safeCopyNames: { "pl-any": "Custom Name" },
            });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("safeCopyNames is only valid when outputMode is sort-into-existing");
        expect(jest.requireMock("../../services/token.service").getValidAccessToken).not.toHaveBeenCalled();
        expect(mockGetUserLikedSongs).not.toHaveBeenCalled();
    });

    it("rejects safeCopyNames for direct mode before any token/Spotify calls", async () => {
        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-hiphop"],
                existingPlaylistWriteMode: "direct",
                safeCopyNames: { "pl-hiphop": "Custom Name" },
            });

        expect(res.status).toBe(400);
        expect(res.body.message).toContain("safeCopyNames is only valid when existingPlaylistWriteMode is copy");
        expect(jest.requireMock("../../services/token.service").getValidAccessToken).not.toHaveBeenCalled();
        expect(mockGetUserLikedSongs).not.toHaveBeenCalled();
    });
});

// =============================================================================
// All four source/output combinations
// =============================================================================

describe("POST /sort — happy paths", () => {
    it("liked + auto-create: creates one playlist per bucket and adds tracks", async () => {
        mockGetUserLikedSongs.mockResolvedValue([
            likedItem(makeTrack("t1", ["a1"])),
            likedItem(makeTrack("t2", ["a2"])),
        ]);
        mockCreatePlaylist
            .mockResolvedValueOnce("new-hiphop")
            .mockResolvedValueOnce("new-pop");

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "auto-create" });

        expect(res.status).toBe(200);
        expect(res.body.results).toHaveLength(2);
        expect(res.body.results[0]).toEqual({
            bucket: "Hip Hop",
            playlistId: "new-hiphop",
            playlistName: "Hip Hop",
            tracksAdded: 1,
            tracks: [
                {
                    id: "t1",
                    name: "Track t1",
                    artists: ["Artist a1"],
                    albumName: "Album",
                    spotifyUrl: "",
                },
            ],
            status: "success",
        });
        expect(res.body.results[1]).toEqual({
            bucket: "Pop",
            playlistId: "new-pop",
            playlistName: "Pop",
            tracksAdded: 1,
            tracks: [
                {
                    id: "t2",
                    name: "Track t2",
                    artists: ["Artist a2"],
                    albumName: "Album",
                    spotifyUrl: "",
                },
            ],
            status: "success",
        });
        expect(mockCreatePlaylist).toHaveBeenCalledWith("access-token", "Hip Hop");
        expect(mockCreatePlaylist).toHaveBeenCalledWith("access-token", "Pop");
        expect(mockAddTracksToPlaylist).toHaveBeenCalledWith("access-token", "new-hiphop", ["spotify:track:t1"]);
        expect(mockAddTracksToPlaylist).toHaveBeenCalledWith("access-token", "new-pop", ["spotify:track:t2"]);
    });

    it("playlist + auto-create: reads the source playlist tracks and creates buckets", async () => {
        mockGetPlaylistTracks.mockResolvedValue([playlistItem(makeTrack("t1", ["a1"]))]);

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "playlist", playlistId: "src-pl", outputMode: "auto-create" });

        expect(res.status).toBe(200);
        expect(mockGetPlaylistTracks).toHaveBeenCalledWith("access-token", "src-pl");
        expect(res.body.results[0].bucket).toBe("Hip Hop");
        expect(res.body.results[0].status).toBe("success");
    });

    it("liked + sort-into-existing: writes each bucket to its best matching editable playlist", async () => {
        mockGetUserLikedSongs.mockResolvedValue([likedItem(makeTrack("t1", ["a1"]))]);
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("pl-hiphop", "Hip Hop Mix", "user1"),
            makePlaylist("pl-pop", "Pop Mix", "user1"),
        ]);
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "pl-hiphop") return [playlistItem(makeTrack("pt1", ["t-a1"]))];
            if (id === "pl-pop") return [playlistItem(makeTrack("pt2", ["t-a2"]))];
            return [];
        });

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-hiphop", "pl-pop"],
                existingPlaylistWriteMode: "direct",
            });

        expect(res.status).toBe(200);
        expect(res.body.results[0]).toEqual({
            bucket: "Hip Hop",
            playlistId: "pl-hiphop",
            playlistName: "Hip Hop Mix",
            tracksAdded: 1,
            tracks: [
                {
                    id: "t1",
                    name: "Track t1",
                    artists: ["Artist a1"],
                    albumName: "Album",
                    spotifyUrl: "",
                },
            ],
            status: "success",
        });
        expect(mockAddTracksToPlaylist).toHaveBeenCalledWith("access-token", "pl-hiphop", ["spotify:track:t1"]);
        expect(res.body.excluded).toEqual([]);
        expect(res.body.destinationCopies).toBeUndefined();
    });

    it("playlist + sort-into-existing: copies source tracks into an existing playlist", async () => {
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "src-pl") return [playlistItem(makeTrack("t1", ["a1"]))];
            if (id === "pl-hiphop") return [playlistItem(makeTrack("pt1", ["t-a1"]))];
            return [];
        });
        mockGetUserPlaylists.mockResolvedValue([makePlaylist("pl-hiphop", "Hip Hop Mix", "user1")]);

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "playlist",
                playlistId: "src-pl",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-hiphop"],
                existingPlaylistWriteMode: "direct",
            });

        expect(res.status).toBe(200);
        expect(mockGetPlaylistTracks).toHaveBeenCalledWith("access-token", "src-pl");
        expect(mockGetPlaylistTracks).toHaveBeenCalledWith("access-token", "pl-hiphop");
        expect(mockAddTracksToPlaylist).toHaveBeenCalledWith("access-token", "pl-hiphop", ["spotify:track:t1"]);
        expect(res.body.results[0].status).toBe("success");
    });
});

// =============================================================================
// Edge cases
// =============================================================================

describe("POST /sort — edge cases", () => {
    it("returns empty results for an empty source", async () => {
        mockGetUserLikedSongs.mockResolvedValue([]);

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "auto-create" });

        expect(res.status).toBe(200);
        expect(res.body).toEqual({ results: [], excluded: [] });
        expect(mockCreatePlaylist).not.toHaveBeenCalled();
    });

    it("reports a bucket-level failure when no destination playlist matches", async () => {
        mockGetUserLikedSongs.mockResolvedValue([likedItem(makeTrack("t1", ["a1"]))]); // Hip Hop
        mockGetUserPlaylists.mockResolvedValue([makePlaylist("pl-pop", "Pop Mix", "user1")]);
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "pl-pop") return [playlistItem(makeTrack("pt2", ["t-a2"]))]; // Pop profile
            return [];
        });

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-pop"],
            });

        expect(res.status).toBe(200);
        expect(res.body.results[0]).toMatchObject({
            bucket: "Hip Hop",
            status: "failed",
            tracksAdded: 0,
            error: "no matching playlist",
        });
        expect(res.body.results[0].tracks).toEqual([
            {
                id: "t1",
                name: "Track t1",
                artists: ["Artist a1"],
                albumName: "Album",
                spotifyUrl: "",
            },
        ]);
        expect(mockAddTracksToPlaylist).not.toHaveBeenCalled();
    });

    it("keeps bucket-level partial failures (one bucket succeeds, another fails)", async () => {
        mockGetUserLikedSongs.mockResolvedValue([
            likedItem(makeTrack("t1", ["a1"])),
            likedItem(makeTrack("t2", ["a2"])),
        ]);
        mockCreatePlaylist
            .mockResolvedValueOnce("new-hiphop")
            .mockRejectedValueOnce(new Error("rate limited"));

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "auto-create" });

        expect(res.status).toBe(200);
        expect(res.body.results[0].status).toBe("success");
        expect(res.body.results[1]).toMatchObject({
            bucket: "Pop",
            status: "failed",
            tracksAdded: 0,
            error: "rate limited",
        });
    });

    it("returns 500 when the token layer fails at the top level", async () => {
        (jest.requireMock("../../services/token.service").getValidAccessToken as jest.Mock).mockRejectedValue(
            new Error("no refresh token")
        );

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "auto-create" });

        expect(res.status).toBe(500);
        expect(res.body.message).toBe("sort failed");
    });

    it("returns 500 when the source fetch fails at the top level", async () => {
        mockGetUserLikedSongs.mockRejectedValue(new Error("Spotify 429"));

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "auto-create" });

        expect(res.status).toBe(500);
        expect(res.body.message).toBe("sort failed");
    });
});

// =============================================================================
// Filtering and safety
// =============================================================================

describe("POST /sort — track filtering and safety", () => {
    it("filters local, unavailable, and malformed liked tracks before sorting", async () => {
        mockGetUserLikedSongs.mockResolvedValue([
            likedItem(makeTrack("t-ok", ["a1"])),
            likedItem(makeTrack("t-local", ["a1"], { is_local: true })),
            likedItem(makeTrack("t-unplayable", ["a1"], { is_playable: false })),
            likedItem({ ...makeTrack("t-no-uri", ["a1"]), uri: "" }),
            likedItem({ ...makeTrack("t-no-artists", []), artists: [] }),
        ]);

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "auto-create" });

        expect(res.status).toBe(200);
        expect(mockAddTracksToPlaylist).toHaveBeenCalledWith("access-token", expect.any(String), ["spotify:track:t-ok"]);
        expect(mockAddTracksToPlaylist).not.toHaveBeenCalledWith(
            "access-token",
            expect.any(String),
            expect.arrayContaining(["spotify:track:t-local", "spotify:track:t-unplayable"])
        );
    });

    it("filters null playlist items (removed/unavailable tracks)", async () => {
        mockGetPlaylistTracks.mockResolvedValue([
            playlistItem(makeTrack("t-ok", ["a1"])),
            playlistItem(null),
        ]);

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "playlist", playlistId: "src-pl", outputMode: "auto-create" });

        expect(res.status).toBe(200);
        expect(res.body.results[0].tracksAdded).toBe(1);
        expect(mockAddTracksToPlaylist).toHaveBeenCalledWith("access-token", expect.any(String), ["spotify:track:t-ok"]);
    });

    it("supports multi-artist tracks and dedupes artist ids for the cache", async () => {
        mockGetUserLikedSongs.mockResolvedValue([
            likedItem(makeTrack("t1", ["a1", "a3", "a1"])), // duplicate artist id
        ]);
        mockGetArtistGenresCached.mockResolvedValue(new Map([
            ["a1", ["hip hop"]],
            ["a3", []],
        ]));

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "auto-create" });

        expect(res.status).toBe(200);
        expect(mockGetArtistGenresCached).toHaveBeenCalledWith("access-token", ["a1", "a3"]);
        expect(res.body.results[0].bucket).toBe("Hip Hop");
    });
});

// =============================================================================
// Existing-mode safety
// =============================================================================

describe("POST /sort — existing-mode exclusions", () => {
    it("reports missing and uneditable selected playlists and never writes to them", async () => {
        mockGetUserLikedSongs.mockResolvedValue([likedItem(makeTrack("t1", ["a1"]))]);
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("pl-owned", "Hip Hop Mix", "user1"),
            makePlaylist("pl-not-mine", "Not Mine", "other-user"),
            makePlaylist("pl-unselected", "Unselected", "user1"),
        ]);
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "pl-owned") return [playlistItem(makeTrack("pt1", ["t-a1"]))];
            return [];
        });

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-owned", "pl-not-mine", "pl-missing"],
                existingPlaylistWriteMode: "direct",
            });

        expect(res.status).toBe(200);
        expect(res.body.excluded).toEqual([
            { id: "pl-missing", name: "", reason: "not found" },
            { id: "pl-not-mine", name: "Not Mine", reason: "not editable" },
        ]);
        expect(mockAddTracksToPlaylist).toHaveBeenCalledTimes(1);
        expect(mockAddTracksToPlaylist).toHaveBeenCalledWith("access-token", "pl-owned", ["spotify:track:t1"]);
        expect(mockGetPlaylistTracks).not.toHaveBeenCalledWith("access-token", "pl-not-mine");
        expect(mockGetPlaylistTracks).not.toHaveBeenCalledWith("access-token", "pl-unselected");
    });
});

// =============================================================================
// Existing-mode copy protection
// =============================================================================

describe("POST /sort — existing-mode copy protection", () => {
    it("defaults to copy mode: clones each matched destination once, copies base items before candidates, and never writes originals", async () => {
        mockGetUserLikedSongs.mockResolvedValue([
            likedItem(makeTrack("t1", ["a1"])), // Hip Hop
            likedItem(makeTrack("t2", ["a2"])), // Pop
        ]);
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("pl-hiphop", "Hip Hop Mix", "user1"),
            makePlaylist("pl-pop", "Pop Mix", "user1"),
            makePlaylist("pl-rock", "Rock Mix", "user1"),
        ]);
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "pl-hiphop") {
                // Duplicates and order preserved in the clone base copy.
                return [
                    playlistItem(makeTrack("pt1", ["t-a1"])),
                    playlistItem(makeTrack("pt1", ["t-a1"])),
                ];
            }
            if (id === "pl-pop") return [playlistItem(makeTrack("pt2", ["t-a2"]))];
            if (id === "pl-rock") return [playlistItem(makeTrack("pt3", ["t-a3"]))];
            return [];
        });
        mockCreatePlaylist
            .mockResolvedValueOnce("clone-hiphop")
            .mockResolvedValueOnce("clone-pop");

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-hiphop", "pl-pop", "pl-rock"],
                // existingPlaylistWriteMode intentionally omitted -> defaults to 'copy'
            });

        expect(res.status).toBe(200);
        // Only matched destinations are cloned, and each exactly once.
        expect(mockCreatePlaylist).toHaveBeenCalledTimes(2);
        expect(mockCreatePlaylist).toHaveBeenCalledWith(
            "access-token",
            "Hip Hop Mix — Spotify Sorter Copy"
        );
        expect(mockCreatePlaylist).toHaveBeenCalledWith(
            "access-token",
            "Pop Mix — Spotify Sorter Copy"
        );
        expect(mockCreatePlaylist).not.toHaveBeenCalledWith(
            "access-token",
            "Rock Mix — Spotify Sorter Copy"
        );

        // Base items are copied before any candidates are added.
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(1, "access-token", "clone-hiphop", [
            "spotify:track:pt1",
            "spotify:track:pt1",
        ]);
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(2, "access-token", "clone-pop", [
            "spotify:track:pt2",
        ]);
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(3, "access-token", "clone-hiphop", [
            "spotify:track:t1",
        ]);
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(4, "access-token", "clone-pop", [
            "spotify:track:t2",
        ]);

        // Candidates and base copies never target the originals.
        for (const [, id] of mockAddTracksToPlaylist.mock.calls) {
            expect(["pl-hiphop", "pl-pop", "pl-rock"]).not.toContain(id);
        }

        expect(res.body.destinationCopies).toEqual([
            {
                sourcePlaylistId: "pl-hiphop",
                sourcePlaylistName: "Hip Hop Mix",
                playlistId: "clone-hiphop",
                playlistName: "Hip Hop Mix — Spotify Sorter Copy",
                tracksCopied: 2,
                status: "success",
            },
            {
                sourcePlaylistId: "pl-pop",
                sourcePlaylistName: "Pop Mix",
                playlistId: "clone-pop",
                playlistName: "Pop Mix — Spotify Sorter Copy",
                tracksCopied: 1,
                status: "success",
            },
        ]);
        expect(res.body.results).toEqual([
            {
                bucket: "Hip Hop",
                playlistId: "clone-hiphop",
                playlistName: "Hip Hop Mix — Spotify Sorter Copy",
                tracksAdded: 1,
                tracks: [
                    {
                        id: "t1",
                        name: "Track t1",
                        artists: ["Artist a1"],
                        albumName: "Album",
                        spotifyUrl: "",
                    },
                ],
                status: "success",
            },
            {
                bucket: "Pop",
                playlistId: "clone-pop",
                playlistName: "Pop Mix — Spotify Sorter Copy",
                tracksAdded: 1,
                tracks: [
                    {
                        id: "t2",
                        name: "Track t2",
                        artists: ["Artist a2"],
                        albumName: "Album",
                        spotifyUrl: "",
                    },
                ],
                status: "success",
            },
        ]);
    });

    it("uses trimmed custom safe-copy names and propagates them into destination copies, results, and undo state", async () => {
        mockGetUserLikedSongs.mockResolvedValue([
            likedItem(makeTrack("t1", ["a1"])), // Hip Hop
            likedItem(makeTrack("t2", ["a2"])), // Pop
        ]);
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("pl-hiphop", "Hip Hop Mix", "user1"),
            makePlaylist("pl-pop", "Pop Mix", "user1"),
        ]);
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "pl-hiphop") return [playlistItem(makeTrack("pt1", ["t-a1"]))];
            if (id === "pl-pop") return [playlistItem(makeTrack("pt2", ["t-a2"]))];
            return [];
        });
        mockCreatePlaylist
            .mockResolvedValueOnce("clone-hiphop")
            .mockResolvedValueOnce("clone-pop");
        mockAddTracksToPlaylist
            .mockResolvedValueOnce("snap-base-1")
            .mockResolvedValueOnce("snap-base-2")
            .mockResolvedValueOnce("snap-hiphop")
            .mockResolvedValueOnce("snap-pop");

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-hiphop", "pl-pop"],
                safeCopyNames: {
                    "pl-hiphop": "  My Custom Hip Hop  ",
                    "pl-pop": "My Pop Copy",
                },
            });

        expect(res.status).toBe(200);
        // Values are trimmed before reaching the service boundary.
        expect(mockCreatePlaylist).toHaveBeenCalledWith("access-token", "My Custom Hip Hop");
        expect(mockCreatePlaylist).toHaveBeenCalledWith("access-token", "My Pop Copy");
        // Propagated into the response destination copies.
        expect(res.body.destinationCopies).toEqual([
            {
                sourcePlaylistId: "pl-hiphop",
                sourcePlaylistName: "Hip Hop Mix",
                playlistId: "clone-hiphop",
                playlistName: "My Custom Hip Hop",
                tracksCopied: 1,
                status: "success",
            },
            {
                sourcePlaylistId: "pl-pop",
                sourcePlaylistName: "Pop Mix",
                playlistId: "clone-pop",
                playlistName: "My Pop Copy",
                tracksCopied: 1,
                status: "success",
            },
        ]);
        // Propagated into per-bucket results.
        expect(res.body.results.map((r: { bucket: string; playlistName: string }) => [r.bucket, r.playlistName])).toEqual([
            ["Hip Hop", "My Custom Hip Hop"],
            ["Pop", "My Pop Copy"],
        ]);
        // Propagated into the recorded undo action state.
        const actionInput = mockCreateSortAction.mock.calls[0][0] as {
            destinations: { playlistName: string }[];
            buckets: { bucket: string; playlistName: string }[];
        };
        expect(actionInput.destinations.map(d => d.playlistName)).toEqual([
            "My Custom Hip Hop",
            "My Pop Copy",
        ]);
        expect(actionInput.buckets.map(b => [b.bucket, b.playlistName])).toEqual([
            ["Hip Hop", "My Custom Hip Hop"],
            ["Pop", "My Pop Copy"],
        ]);
        expect(res.body.action.destinations.map((d: { playlistName: string }) => d.playlistName)).toEqual([
            "My Custom Hip Hop",
            "My Pop Copy",
        ]);
    });

    it("falls back to the automatic copy name when safeCopyNames omits a matched destination", async () => {
        mockGetUserLikedSongs.mockResolvedValue([
            likedItem(makeTrack("t1", ["a1"])), // Hip Hop
            likedItem(makeTrack("t2", ["a2"])), // Pop
        ]);
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("pl-hiphop", "Hip Hop Mix", "user1"),
            makePlaylist("pl-pop", "Pop Mix", "user1"),
        ]);
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "pl-hiphop") return [playlistItem(makeTrack("pt1", ["t-a1"]))];
            if (id === "pl-pop") return [playlistItem(makeTrack("pt2", ["t-a2"]))];
            return [];
        });
        mockCreatePlaylist
            .mockResolvedValueOnce("clone-hiphop")
            .mockResolvedValueOnce("clone-pop");

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-hiphop", "pl-pop"],
                safeCopyNames: { "pl-hiphop": "Custom Hip Hop" },
            });

        expect(res.status).toBe(200);
        expect(mockCreatePlaylist).toHaveBeenCalledWith("access-token", "Custom Hip Hop");
        expect(mockCreatePlaylist).toHaveBeenCalledWith("access-token", "Pop Mix — Spotify Sorter Copy");
        expect(res.body.destinationCopies[0].playlistName).toBe("Custom Hip Hop");
        expect(res.body.destinationCopies[1].playlistName).toBe("Pop Mix — Spotify Sorter Copy");
        expect(res.body.results[0].playlistName).toBe("Custom Hip Hop");
        expect(res.body.results[1].playlistName).toBe("Pop Mix — Spotify Sorter Copy");
    });

    it("fails only the affected destination when its base-item copy fails, retaining the clone id", async () => {
        mockGetUserLikedSongs.mockResolvedValue([
            likedItem(makeTrack("t1", ["a1"])), // Hip Hop
            likedItem(makeTrack("t2", ["a2"])), // Pop
        ]);
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("pl-hiphop", "Hip Hop Mix", "user1"),
            makePlaylist("pl-pop", "Pop Mix", "user1"),
        ]);
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "pl-hiphop") return [playlistItem(makeTrack("pt1", ["t-a1"]))];
            if (id === "pl-pop") return [playlistItem(makeTrack("pt2", ["t-a2"]))];
            return [];
        });
        mockCreatePlaylist
            .mockResolvedValueOnce("clone-hiphop")
            .mockResolvedValueOnce("clone-pop");
        // First addTracksToPlaylist call is the hip hop clone's base-item copy.
        mockAddTracksToPlaylist
            .mockRejectedValueOnce(new Error("copy failed"))
            .mockResolvedValue(undefined);

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-hiphop", "pl-pop"],
            });

        expect(res.status).toBe(200);
        expect(res.body.destinationCopies[0]).toEqual({
            sourcePlaylistId: "pl-hiphop",
            sourcePlaylistName: "Hip Hop Mix",
            playlistId: "clone-hiphop", // partially-created copy retains its id
            playlistName: "Hip Hop Mix — Spotify Sorter Copy",
            tracksCopied: 0,
            status: "failed",
            error: "copy failed",
        });
        expect(res.body.destinationCopies[1]).toMatchObject({
            sourcePlaylistId: "pl-pop",
            status: "success",
        });
        // Hip Hop bucket failed and never received candidates; Pop continued.
        expect(res.body.results[0]).toEqual({
            bucket: "Hip Hop",
            playlistId: "",
            playlistName: "Hip Hop Mix",
            tracksAdded: 0,
            tracks: [
                {
                    id: "t1",
                    name: "Track t1",
                    artists: ["Artist a1"],
                    albumName: "Album",
                    spotifyUrl: "",
                },
            ],
            status: "failed",
            error: "copy failed",
        });
        expect(res.body.results[1]).toMatchObject({
            bucket: "Pop",
            playlistId: "clone-pop",
            tracksAdded: 1,
            status: "success",
        });
        // Failed clone: base copy only. Pop clone: base copy then candidates.
        expect(mockAddTracksToPlaylist).toHaveBeenCalledTimes(3);
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(1, "access-token", "clone-hiphop", [
            "spotify:track:pt1",
        ]);
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(2, "access-token", "clone-pop", [
            "spotify:track:pt2",
        ]);
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(3, "access-token", "clone-pop", [
            "spotify:track:t2",
        ]);
        for (const [, id] of mockAddTracksToPlaylist.mock.calls) {
            expect(["pl-hiphop", "pl-pop"]).not.toContain(id);
        }
    });

    it("fails only the affected destination when clone creation fails", async () => {
        mockGetUserLikedSongs.mockResolvedValue([
            likedItem(makeTrack("t1", ["a1"])), // Hip Hop
            likedItem(makeTrack("t2", ["a2"])), // Pop
        ]);
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("pl-hiphop", "Hip Hop Mix", "user1"),
            makePlaylist("pl-pop", "Pop Mix", "user1"),
        ]);
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "pl-hiphop") return [playlistItem(makeTrack("pt1", ["t-a1"]))];
            if (id === "pl-pop") return [playlistItem(makeTrack("pt2", ["t-a2"]))];
            return [];
        });
        mockCreatePlaylist
            .mockResolvedValueOnce("clone-hiphop")
            .mockRejectedValueOnce(new Error("create boom"));

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-hiphop", "pl-pop"],
            });

        expect(res.status).toBe(200);
        expect(res.body.destinationCopies[1]).toEqual({
            sourcePlaylistId: "pl-pop",
            sourcePlaylistName: "Pop Mix",
            playlistId: "",
            playlistName: "Pop Mix — Spotify Sorter Copy",
            tracksCopied: 0,
            status: "failed",
            error: "create boom",
        });
        expect(res.body.results[0]).toMatchObject({
            bucket: "Hip Hop",
            playlistId: "clone-hiphop",
            status: "success",
        });
        expect(res.body.results[1]).toMatchObject({
            bucket: "Pop",
            status: "failed",
            tracksAdded: 0,
            error: "create boom",
        });
        // No candidate or base writes for the failed destination.
        expect(mockAddTracksToPlaylist.mock.calls.map(call => call[1])).toEqual([
            "clone-hiphop",
            "clone-hiphop",
        ]);
        expect(res.body.results[1].tracks).toEqual([
            {
                id: "t2",
                name: "Track t2",
                artists: ["Artist a2"],
                albumName: "Album",
                spotifyUrl: "",
            },
        ]);
    });

    it("creates an empty clone for a matched empty destination and accepts explicit copy mode", async () => {
        mockGetUserLikedSongs.mockResolvedValue([likedItem(makeTrack("t1", ["a1"]))]); // Hip Hop
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("pl-empty", "Hip Hop Mix", "user1"), // empty -> name match
        ]);
        mockGetPlaylistTracks.mockResolvedValue([]);
        mockCreatePlaylist.mockResolvedValue("clone-empty");

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-empty"],
                existingPlaylistWriteMode: "copy",
            });

        expect(res.status).toBe(200);
        expect(mockCreatePlaylist).toHaveBeenCalledWith(
            "access-token",
            "Hip Hop Mix — Spotify Sorter Copy"
        );
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(1, "access-token", "clone-empty", []);
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(2, "access-token", "clone-empty", [
            "spotify:track:t1",
        ]);
        expect(res.body.destinationCopies).toEqual([
            {
                sourcePlaylistId: "pl-empty",
                sourcePlaylistName: "Hip Hop Mix",
                playlistId: "clone-empty",
                playlistName: "Hip Hop Mix — Spotify Sorter Copy",
                tracksCopied: 0,
                status: "success",
            },
        ]);
        expect(res.body.results[0]).toMatchObject({
            bucket: "Hip Hop",
            playlistId: "clone-empty",
            tracksAdded: 1,
            status: "success",
        });
    });
});

// =============================================================================
// Playlist backups
// =============================================================================

describe("POST /sort — playlist backups", () => {
    it("creates and fills the backup before output writes and returns it on success", async () => {
        mockGetPlaylistTracks.mockResolvedValue([
            playlistItem(makeTrack("t1", ["a1"])),
            playlistItem(makeTrack("t2", ["a2"])),
        ]);
        mockGetUserPlaylists.mockResolvedValue([makePlaylist("src-pl", "My Mix", "user1")]);
        mockCreatePlaylist
            .mockResolvedValueOnce("backup-pl")
            .mockResolvedValueOnce("new-hiphop")
            .mockResolvedValueOnce("new-pop");

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "playlist", playlistId: "src-pl", outputMode: "auto-create", createBackup: true });

        expect(res.status).toBe(200);
        expect(res.body.backup).toEqual({
            playlistId: "backup-pl",
            playlistName: "My Mix — Spotify Sorter Backup",
            tracksCopied: 2,
            status: "success",
        });
        expect(res.body.results).toHaveLength(2);
        // Backup playlist is created before genre outputs.
        expect(mockCreatePlaylist.mock.invocationCallOrder[0]).toBeLessThan(
            mockCreatePlaylist.mock.invocationCallOrder[1]
        );
        expect(mockCreatePlaylist).toHaveBeenNthCalledWith(1, "access-token", "My Mix — Spotify Sorter Backup");
        // Backup item copy happens before artist lookup and any destination write.
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(1, "access-token", "backup-pl", [
            "spotify:track:t1",
            "spotify:track:t2",
        ]);
        expect(mockAddTracksToPlaylist.mock.invocationCallOrder[0]).toBeLessThan(
            mockGetArtistGenresCached.mock.invocationCallOrder[0]
        );
        expect(mockAddTracksToPlaylist).toHaveBeenCalledWith("access-token", "new-hiphop", ["spotify:track:t1"]);
        expect(mockAddTracksToPlaylist).toHaveBeenCalledWith("access-token", "new-pop", ["spotify:track:t2"]);
    });

    it("backs up copyable tracks without artists (and duplicates) that genre output omits", async () => {
        const noArtists = makeTrack("t-no-artists", []);
        mockGetPlaylistTracks.mockResolvedValue([
            playlistItem(makeTrack("t1", ["a1"])),
            playlistItem(noArtists),
            playlistItem(noArtists), // duplicate URI is preserved in the backup
        ]);
        mockGetUserPlaylists.mockResolvedValue([makePlaylist("src-pl", "My Mix", "user1")]);
        mockCreatePlaylist.mockResolvedValueOnce("backup-pl");

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "playlist", playlistId: "src-pl", outputMode: "auto-create", createBackup: true });

        expect(res.status).toBe(200);
        expect(res.body.backup).toEqual({
            playlistId: "backup-pl",
            playlistName: "My Mix — Spotify Sorter Backup",
            tracksCopied: 3,
            status: "success",
        });
        // Backup copies every copyable source URI, including the no-artists track twice.
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(1, "access-token", "backup-pl", [
            "spotify:track:t1",
            "spotify:track:t-no-artists",
            "spotify:track:t-no-artists",
        ]);
        // Genre output still only contains sortable tracks.
        expect(res.body.results).toHaveLength(1);
        expect(res.body.results[0]).toMatchObject({
            bucket: "Hip Hop",
            tracksAdded: 1,
            status: "success",
        });
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(2, "access-token", "new-playlist", [
            "spotify:track:t1",
        ]);
    });

    it("fails before any writes when the source playlist is not found", async () => {
        mockGetPlaylistTracks.mockResolvedValue([playlistItem(makeTrack("t1", ["a1"]))]);
        mockGetUserPlaylists.mockResolvedValue([makePlaylist("other-pl", "Other", "user1")]);

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "playlist", playlistId: "src-pl", outputMode: "auto-create", createBackup: true });

        expect(res.status).toBe(404);
        expect(res.body.message).toContain("source playlist 'src-pl' not found");
        expect(mockCreatePlaylist).not.toHaveBeenCalled();
        expect(mockGetArtistGenresCached).not.toHaveBeenCalled();
    });

    it("aborts the sort when backup copy fails, without genre outputs", async () => {
        mockGetPlaylistTracks.mockResolvedValue([playlistItem(makeTrack("t1", ["a1"]))]);
        mockGetUserPlaylists.mockResolvedValue([makePlaylist("src-pl", "My Mix", "user1")]);
        mockCreatePlaylist.mockResolvedValue("backup-pl");
        mockAddTracksToPlaylist.mockRejectedValue(new Error("Spotify 500"));

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "playlist", playlistId: "src-pl", outputMode: "auto-create", createBackup: true });

        expect(res.status).toBe(500);
        expect(res.body.message).toContain("backup creation failed");
        expect(mockCreatePlaylist).toHaveBeenCalledTimes(1);
        expect(mockCreatePlaylist).toHaveBeenCalledWith("access-token", "My Mix — Spotify Sorter Backup");
        expect(mockAddTracksToPlaylist).toHaveBeenCalledTimes(1);
        expect(mockAddTracksToPlaylist).toHaveBeenCalledWith("access-token", "backup-pl", ["spotify:track:t1"]);
        expect(mockGetArtistGenresCached).not.toHaveBeenCalled();
    });

    it("creates and returns an empty backup for an empty playlist source", async () => {
        mockGetPlaylistTracks.mockResolvedValue([]);
        mockGetUserPlaylists.mockResolvedValue([makePlaylist("src-pl", "Empty Mix", "user1")]);
        mockCreatePlaylist.mockResolvedValue("backup-pl");

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "playlist", playlistId: "src-pl", outputMode: "auto-create", createBackup: true });

        expect(res.status).toBe(200);
        expect(res.body).toEqual({
            results: [],
            excluded: [],
            backup: {
                playlistId: "backup-pl",
                playlistName: "Empty Mix — Spotify Sorter Backup",
                tracksCopied: 0,
                status: "success",
            },
        });
        expect(mockCreatePlaylist).toHaveBeenCalledWith("access-token", "Empty Mix — Spotify Sorter Backup");
        expect(mockAddTracksToPlaylist).toHaveBeenCalledWith("access-token", "backup-pl", []);
        expect(mockGetArtistGenresCached).not.toHaveBeenCalled();
    });

    it("reuses fetched playlists in existing mode and never uses the source as a destination", async () => {
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "src-pl") return [playlistItem(makeTrack("t1", ["a1"]))];
            if (id === "pl-hiphop") return [playlistItem(makeTrack("pt1", ["t-a1"]))];
            return [];
        });
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("src-pl", "My Mix", "user1"),
            makePlaylist("pl-hiphop", "Hip Hop Mix", "user1"),
        ]);
        mockCreatePlaylist.mockResolvedValue("backup-pl");

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "playlist",
                playlistId: "src-pl",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-hiphop"],
                existingPlaylistWriteMode: "direct",
                createBackup: true,
            });

        expect(res.status).toBe(200);
        expect(mockGetUserPlaylists).toHaveBeenCalledTimes(1);
        expect(res.body.backup).toEqual({
            playlistId: "backup-pl",
            playlistName: "My Mix — Spotify Sorter Backup",
            tracksCopied: 1,
            status: "success",
        });
        expect(res.body.results[0]).toMatchObject({
            bucket: "Hip Hop",
            playlistId: "pl-hiphop",
            status: "success",
        });
        expect(res.body.excluded).toEqual([]);
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(1, "access-token", "backup-pl", [
            "spotify:track:t1",
        ]);
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(2, "access-token", "pl-hiphop", [
            "spotify:track:t1",
        ]);
    });
});

// =============================================================================
// Undo action recording
// =============================================================================

describe("POST /sort — undo action recording", () => {
    it("records an auto-create action with empty baselines and the final add snapshot", async () => {
        mockGetUserLikedSongs.mockResolvedValue([likedItem(makeTrack("t1", ["a1"]))]);
        mockCreatePlaylist.mockResolvedValueOnce("new-hiphop");
        mockAddTracksToPlaylist.mockResolvedValueOnce("snap-hiphop");

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "auto-create" });

        expect(res.status).toBe(200);
        expect(mockCreateSortAction).toHaveBeenCalledTimes(1);
        expect(mockCreateSortAction).toHaveBeenCalledWith({
            spotifyId: "user1",
            destinations: [
                {
                    playlistId: "new-hiphop",
                    playlistName: "Hip Hop",
                    baselineUris: [],
                    expectedSnapshotId: "snap-hiphop",
                    bucketOrder: ["Hip Hop"],
                },
            ],
            buckets: [
                {
                    bucket: "Hip Hop",
                    playlistId: "new-hiphop",
                    playlistName: "Hip Hop",
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
        });
        expect(res.body.action).toMatchObject({
            id: "action-1",
            spotifyId: "user1",
            destinations: [
                {
                    playlistId: "new-hiphop",
                    baselineUris: [],
                    expectedSnapshotId: "snap-hiphop",
                },
            ],
        });
    });

    it("records copy-mode baselines exactly as copied (order + duplicates) and the final snapshot after all buckets", async () => {
        mockGetUserLikedSongs.mockResolvedValue([
            likedItem(makeTrack("t1", ["a1"])), // Hip Hop
            likedItem(makeTrack("t2", ["a2"])), // Pop
        ]);
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("pl-mix", "Hip Hop & Pop Mix", "user1"),
        ]);
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "pl-mix") {
                return [
                    playlistItem(makeTrack("pt1", ["t-a1"])),
                    playlistItem(makeTrack("pt1", ["t-a1"])),
                    playlistItem(makeTrack("pt2", ["t-a2"])),
                ];
            }
            return [];
        });
        mockCreatePlaylist.mockResolvedValueOnce("clone-mix");
        mockAddTracksToPlaylist
            .mockResolvedValueOnce("snap-base") // base copy (not the final state)
            .mockResolvedValueOnce("snap-hiphop") // Hip Hop candidates
            .mockResolvedValueOnce("snap-pop"); // Pop candidates = final state

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-mix"],
            });

        expect(res.status).toBe(200);
        expect(mockCreateSortAction).toHaveBeenCalledWith({
            spotifyId: "user1",
            destinations: [
                {
                    playlistId: "clone-mix",
                    playlistName: "Hip Hop & Pop Mix — Spotify Sorter Copy",
                    baselineUris: [
                        "spotify:track:pt1",
                        "spotify:track:pt1",
                        "spotify:track:pt2",
                    ],
                    expectedSnapshotId: "snap-pop",
                    bucketOrder: ["Hip Hop", "Pop"],
                },
            ],
            buckets: expect.arrayContaining([
                {
                    bucket: "Hip Hop",
                    playlistId: "clone-mix",
                    playlistName: "Hip Hop & Pop Mix — Spotify Sorter Copy",
                    trackUris: ["spotify:track:t1"],
                    tracks: expect.any(Array),
                    status: "applied",
                },
                {
                    bucket: "Pop",
                    playlistId: "clone-mix",
                    playlistName: "Hip Hop & Pop Mix — Spotify Sorter Copy",
                    trackUris: ["spotify:track:t2"],
                    tracks: expect.any(Array),
                    status: "applied",
                },
            ]),
        });
    });

    it("records direct-mode baselines exactly as the replay-safe copyable URIs, including duplicates", async () => {
        mockGetUserLikedSongs.mockResolvedValue([likedItem(makeTrack("t1", ["a1"]))]);
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("pl-owned", "Hip Hop Mix", "user1"),
        ]);
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "pl-owned") {
                return [
                    playlistItem(makeTrack("pt1", ["t-a1"])),
                    playlistItem(makeTrack("pt1", ["t-a1"])),
                    playlistItem(makeTrack("pt2", ["t-a2"])),
                ];
            }
            return [];
        });
        mockAddTracksToPlaylist.mockResolvedValueOnce("snap-after");

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-owned"],
                existingPlaylistWriteMode: "direct",
            });

        expect(res.status).toBe(200);
        const input = mockCreateSortAction.mock.calls[0][0] as {
            destinations: { playlistId: string; baselineUris: string[] }[];
        };
        expect(input.destinations[0]).toEqual({
            playlistId: "pl-owned",
            playlistName: "Hip Hop Mix",
            baselineUris: [
                "spotify:track:pt1",
                "spotify:track:pt1",
                "spotify:track:pt2",
            ],
            expectedSnapshotId: "snap-after",
            bucketOrder: ["Hip Hop"],
        });
        expect(mockGetPlaylistSnapshot).not.toHaveBeenCalled();
    });

    it("blocks every direct write to a destination with a local item and records no undo action for those buckets", async () => {
        mockGetUserLikedSongs.mockResolvedValue([
            likedItem(makeTrack("t1", ["a1"])), // Hip Hop
            likedItem(makeTrack("t2", ["a2"])), // Pop
        ]);
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("pl-mix", "Hip Hop & Pop Mix", "user1"),
        ]);
        const localTrack = makeTrack("local-1", ["a1"], {
            is_local: true,
            uri: "spotify:local:artist:album:track:123",
        });
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "pl-mix") return [playlistItem(localTrack)];
            return [];
        });

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-mix"],
                existingPlaylistWriteMode: "direct",
            });

        expect(res.status).toBe(200);
        expect(mockAddTracksToPlaylist).not.toHaveBeenCalled();
        expect(mockGetPlaylistSnapshot).not.toHaveBeenCalled();
        expect(mockCreateSortAction).not.toHaveBeenCalled();
        expect(res.body.action).toBeUndefined();
        expect(res.body.actionWarning).toBeUndefined();
        // Every bucket assigned to the unsafe destination fails with zero adds.
        expect(res.body.results).toHaveLength(2);
        for (const result of res.body.results) {
            expect(result).toMatchObject({
                playlistId: "pl-mix",
                playlistName: "Hip Hop & Pop Mix",
                tracksAdded: 0,
                status: "failed",
            });
            expect(result.error).toContain("Create safe copies");
            expect(result.error).toContain("cannot be safely undone");
        }
    });

    it("blocks every direct write to a destination with a null/unavailable item", async () => {
        mockGetUserLikedSongs.mockResolvedValue([likedItem(makeTrack("t1", ["a1"]))]); // Hip Hop
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("pl-mix", "Hip Hop & Pop Mix", "user1"),
        ]);
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "pl-mix") return [playlistItem(null)]; // removed/unavailable
            return [];
        });

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-mix"],
                existingPlaylistWriteMode: "direct",
            });

        expect(res.status).toBe(200);
        expect(mockAddTracksToPlaylist).not.toHaveBeenCalled();
        expect(mockCreateSortAction).not.toHaveBeenCalled();
        expect(res.body.action).toBeUndefined();
        expect(res.body.results).toHaveLength(1);
        expect(res.body.results[0]).toMatchObject({
            bucket: "Hip Hop",
            playlistId: "pl-mix",
            tracksAdded: 0,
            status: "failed",
        });
        expect(res.body.results[0].error).toContain("Create safe copies");
    });

    it("blocks an unsafe destination without blocking a separate replay-safe destination", async () => {
        mockGetUserLikedSongs.mockResolvedValue([
            likedItem(makeTrack("t1", ["a1"])), // Hip Hop
            likedItem(makeTrack("t2", ["a2"])), // Pop
        ]);
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("pl-unsafe", "Hip Hop Mix", "user1"),
            makePlaylist("pl-safe", "Pop Mix", "user1"),
        ]);
        const localTrack = makeTrack("local-1", ["a1"], {
            is_local: true,
            uri: "spotify:local:artist:album:track:123",
        });
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "pl-unsafe") return [playlistItem(localTrack)];
            if (id === "pl-safe") return [playlistItem(makeTrack("pt2", ["t-a2"]))];
            return [];
        });
        mockAddTracksToPlaylist.mockResolvedValueOnce("snap-safe");

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-unsafe", "pl-safe"],
                existingPlaylistWriteMode: "direct",
            });

        expect(res.status).toBe(200);
        // Only the replay-safe destination is written; the unsafe one gets zero
        // add/write calls.
        expect(mockAddTracksToPlaylist).toHaveBeenCalledTimes(1);
        expect(mockAddTracksToPlaylist).toHaveBeenCalledWith("access-token", "pl-safe", [
            "spotify:track:t2",
        ]);

        expect(res.body.results[0]).toMatchObject({
            bucket: "Hip Hop",
            playlistId: "pl-unsafe",
            playlistName: "Hip Hop Mix",
            tracksAdded: 0,
            status: "failed",
        });
        expect(res.body.results[0].error).toContain("Create safe copies");
        expect(res.body.results[1]).toMatchObject({
            bucket: "Pop",
            playlistId: "pl-safe",
            playlistName: "Pop Mix",
            tracksAdded: 1,
            status: "success",
        });

        // The recorded undo action only covers the replay-safe destination.
        expect(mockCreateSortAction).toHaveBeenCalledTimes(1);
        const input = mockCreateSortAction.mock.calls[0][0] as {
            destinations: { playlistId: string; baselineUris: string[] }[];
            buckets: { bucket: string; playlistId: string }[];
        };
        expect(input.destinations).toEqual([
            {
                playlistId: "pl-safe",
                playlistName: "Pop Mix",
                baselineUris: ["spotify:track:pt2"],
                expectedSnapshotId: "snap-safe",
                bucketOrder: ["Pop"],
            },
        ]);
        expect(input.buckets).toEqual([
            expect.objectContaining({ bucket: "Pop", playlistId: "pl-safe", status: "applied" }),
        ]);
        expect(res.body.action).toMatchObject({
            destinations: [{ playlistId: "pl-safe" }],
        });
    });

    it("direct mode keeps result and write order in original bucket order when a destination is assigned twice", async () => {
        mockGetUserLikedSongs.mockResolvedValue([
            likedItem(makeTrack("t1", ["a1"])), // Hip Hop -> pl-mix
            likedItem(makeTrack("t2", ["a2"])), // Pop -> pl-pop
            likedItem(makeTrack("t3", ["a3"])), // Rock -> pl-mix
        ]);
        mockGetArtistGenresCached.mockResolvedValue(new Map([
            ...DEFAULT_GENRES,
            ["a3", ["rock"]],
            ["t-a3", ["rock"]],
        ]));
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("pl-mix", "Hip Hop & Rock Mix", "user1"),
            makePlaylist("pl-pop", "Pop Mix", "user1"),
        ]);
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "pl-mix") {
                return [
                    playlistItem(makeTrack("pt1", ["t-a1"])),
                    playlistItem(makeTrack("pt3", ["t-a3"])),
                ];
            }
            if (id === "pl-pop") return [playlistItem(makeTrack("pt2", ["t-a2"]))];
            return [];
        });
        mockAddTracksToPlaylist
            .mockResolvedValueOnce("snap-mix-1")
            .mockResolvedValueOnce("snap-pop")
            .mockResolvedValueOnce("snap-mix-2");

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-mix", "pl-pop"],
                existingPlaylistWriteMode: "direct",
            });

        expect(res.status).toBe(200);
        // Results keep the original assignment order (Hip Hop -> pl-mix,
        // Pop -> pl-pop, Rock -> pl-mix) instead of being grouped by
        // destination.
        expect(res.body.results.map((r: { bucket: string; playlistId: string; status: string }) => [r.bucket, r.playlistId, r.status])).toEqual([
            ["Hip Hop", "pl-mix", "success"],
            ["Pop", "pl-pop", "success"],
            ["Rock", "pl-mix", "success"],
        ]);
        // Add writes happen in the same original bucket order.
        expect(mockAddTracksToPlaylist.mock.calls.map(call => call[1])).toEqual([
            "pl-mix",
            "pl-pop",
            "pl-mix",
        ]);
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(1, "access-token", "pl-mix", [
            "spotify:track:t1",
        ]);
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(2, "access-token", "pl-pop", [
            "spotify:track:t2",
        ]);
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(3, "access-token", "pl-mix", [
            "spotify:track:t3",
        ]);

        // The undo action records each destination once, with the twice-written
        // destination keeping both buckets in original order.
        const input = mockCreateSortAction.mock.calls[0][0] as {
            destinations: {
                playlistId: string;
                playlistName: string;
                baselineUris: string[];
                expectedSnapshotId: string;
                bucketOrder: string[];
            }[];
        };
        expect(input.destinations).toEqual([
            {
                playlistId: "pl-mix",
                playlistName: "Hip Hop & Rock Mix",
                baselineUris: ["spotify:track:pt1", "spotify:track:pt3"],
                expectedSnapshotId: "snap-mix-2",
                bucketOrder: ["Hip Hop", "Rock"],
            },
            {
                playlistId: "pl-pop",
                playlistName: "Pop Mix",
                baselineUris: ["spotify:track:pt2"],
                expectedSnapshotId: "snap-pop",
                bucketOrder: ["Pop"],
            },
        ]);
    });

    it("copy mode still filters uncopyable destination items because originals remain untouched", async () => {
        mockGetUserLikedSongs.mockResolvedValue([likedItem(makeTrack("t1", ["a1"]))]); // Hip Hop
        mockGetUserPlaylists.mockResolvedValue([
            makePlaylist("pl-mix", "Hip Hop & Pop Mix", "user1"),
        ]);
        const localTrack = makeTrack("local-1", ["a1"], {
            is_local: true,
            uri: "spotify:local:artist:album:track:123",
        });
        mockGetPlaylistTracks.mockImplementation(async (_token: string, id: string) => {
            if (id === "pl-mix") return [playlistItem(localTrack), playlistItem(null)];
            return [];
        });
        mockCreatePlaylist.mockResolvedValue("clone-mix");
        mockAddTracksToPlaylist
            .mockResolvedValueOnce("snap-base") // empty base copy (both filtered)
            .mockResolvedValueOnce("snap-candidate");

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({
                sourceType: "liked",
                outputMode: "sort-into-existing",
                editablePlaylistIds: ["pl-mix"],
                existingPlaylistWriteMode: "copy",
            });

        expect(res.status).toBe(200);
        // Copy mode proceeds: the clone receives the empty base copy then the
        // candidate; the original is never written.
        expect(mockAddTracksToPlaylist).toHaveBeenCalledTimes(2);
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(1, "access-token", "clone-mix", []);
        expect(mockAddTracksToPlaylist).toHaveBeenNthCalledWith(2, "access-token", "clone-mix", [
            "spotify:track:t1",
        ]);
        for (const [, id] of mockAddTracksToPlaylist.mock.calls) {
            expect(id).not.toBe("pl-mix");
        }
        expect(res.body.destinationCopies[0]).toEqual({
            sourcePlaylistId: "pl-mix",
            sourcePlaylistName: "Hip Hop & Pop Mix",
            playlistId: "clone-mix",
            playlistName: "Hip Hop & Pop Mix — Spotify Sorter Copy",
            tracksCopied: 0,
            status: "success",
        });
        expect(res.body.results[0]).toMatchObject({
            bucket: "Hip Hop",
            playlistId: "clone-mix",
            tracksAdded: 1,
            status: "success",
        });
    });

    it("falls back to a final snapshot read when the add response did not carry one", async () => {
        mockGetUserLikedSongs.mockResolvedValue([likedItem(makeTrack("t1", ["a1"]))]);
        mockCreatePlaylist.mockResolvedValueOnce("new-hiphop");
        mockAddTracksToPlaylist.mockResolvedValueOnce(undefined);
        mockGetPlaylistSnapshot.mockResolvedValue("snap-fetched");

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "auto-create" });

        expect(res.status).toBe(200);
        expect(mockGetPlaylistSnapshot).toHaveBeenCalledWith("access-token", "new-hiphop");
        const input = mockCreateSortAction.mock.calls[0][0] as {
            destinations: { expectedSnapshotId: string }[];
        };
        expect(input.destinations[0].expectedSnapshotId).toBe("snap-fetched");
        expect(res.body.action.destinations[0].expectedSnapshotId).toBe("snap-fetched");
    });

    it("returns a warning instead of an action when Redis persistence fails", async () => {
        mockGetUserLikedSongs.mockResolvedValue([likedItem(makeTrack("t1", ["a1"]))]);
        mockCreatePlaylist.mockResolvedValueOnce("new-hiphop");
        mockAddTracksToPlaylist.mockResolvedValueOnce("snap-hiphop");
        mockCreateSortAction.mockRejectedValueOnce(new Error("redis down"));

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "auto-create" });

        expect(res.status).toBe(200);
        expect(res.body.results[0].status).toBe("success");
        expect(res.body.action).toBeUndefined();
        expect(res.body.actionWarning).toContain("action tracking unavailable");
        expect(res.body.actionWarning).toContain("redis down");
    });

    it("returns a warning without an action when the final snapshot cannot be read", async () => {
        mockGetUserLikedSongs.mockResolvedValue([likedItem(makeTrack("t1", ["a1"]))]);
        mockCreatePlaylist.mockResolvedValueOnce("new-hiphop");
        mockAddTracksToPlaylist.mockResolvedValueOnce(undefined);
        mockGetPlaylistSnapshot.mockRejectedValueOnce(new Error("Spotify 500"));

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "auto-create" });

        expect(res.status).toBe(200);
        expect(res.body.results[0].status).toBe("success");
        expect(res.body.action).toBeUndefined();
        expect(res.body.actionWarning).toContain("action tracking unavailable");
        expect(mockCreateSortAction).not.toHaveBeenCalled();
    });

    it("records no action when every bucket fails", async () => {
        mockGetUserLikedSongs.mockResolvedValue([likedItem(makeTrack("t1", ["a1"]))]);
        mockCreatePlaylist.mockRejectedValueOnce(new Error("create boom"));

        const res = await request(app)
            .post("/sort")
            .set("Cookie", "jwt=valid")
            .send({ sourceType: "liked", outputMode: "auto-create" });

        expect(res.status).toBe(200);
        expect(res.body.action).toBeUndefined();
        expect(res.body.actionWarning).toBeUndefined();
        expect(mockCreateSortAction).not.toHaveBeenCalled();
        expect(mockGetPlaylistSnapshot).not.toHaveBeenCalled();
    });
});
