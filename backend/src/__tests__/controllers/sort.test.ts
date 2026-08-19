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
}));

jest.mock("../../services/artist.cache.service", () => ({
    getArtistGenresCached: jest.fn(),
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
} from "../../services/spotify.playlist.service";
import { getArtistGenresCached } from "../../services/artist.cache.service";
import jwt from "jsonwebtoken";
import type { SpotifyTrack, SpotifySimplifiedPlaylist } from "../../types/spotify.types";

const mockGetUserLikedSongs = getUserLikedSongs as jest.Mock;
const mockGetPlaylistTracks = getPlaylistTracks as jest.Mock;
const mockCreatePlaylist = createPlaylist as jest.Mock;
const mockAddTracksToPlaylist = addTracksToPlaylist as jest.Mock;
const mockGetUserPlaylists = getUserPlaylists as jest.Mock;
const mockGetArtistGenresCached = getArtistGenresCached as jest.Mock;
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
            status: "success",
        });
        expect(res.body.results[1]).toEqual({
            bucket: "Pop",
            playlistId: "new-pop",
            playlistName: "Pop",
            tracksAdded: 1,
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
            });

        expect(res.status).toBe(200);
        expect(res.body.results[0]).toEqual({
            bucket: "Hip Hop",
            playlistId: "pl-hiphop",
            playlistName: "Hip Hop Mix",
            tracksAdded: 1,
            status: "success",
        });
        expect(mockAddTracksToPlaylist).toHaveBeenCalledWith("access-token", "pl-hiphop", ["spotify:track:t1"]);
        expect(res.body.excluded).toEqual([]);
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
