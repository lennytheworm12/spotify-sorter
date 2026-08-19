// playlist.library.routes.test.ts
//
// Focused route/controller boundary tests for the three read endpoints that
// broker a token then delegate to a Spotify service:
//   GET /playlists, GET /playlists/:id/tracks, GET /library/liked
//
// The real routers and controllers are mounted; token orchestration and the
// Spotify playlist service are mocked. Covers auth requirement, correct
// token/service delegation, success, and service-failure responses.

import express from "express";
import request from "supertest";
import cookieParser from "cookie-parser";
import playlistRouter from "../../routes/playlist.routes";
import libraryRouter from "../../routes/library.routes";

jest.mock("../../env", () => ({
    env: { JWT_SECRET: "test-secret" },
}));

jest.mock("jsonwebtoken", () => ({
    __esModule: true,
    default: {
        verify: jest.fn(),
        sign: jest.fn(),
    },
}));

jest.mock("../../services/token.service", () => ({
    getValidAccessToken: jest.fn(),
}));

jest.mock("../../services/spotify.playlist.service", () => ({
    getUserPlaylists: jest.fn(),
    getUserLikedSongs: jest.fn(),
    getPlaylistTracks: jest.fn(),
}));

import jwt from "jsonwebtoken";
import { getValidAccessToken } from "../../services/token.service";
import {
    getUserPlaylists,
    getPlaylistTracks,
    getUserLikedSongs,
} from "../../services/spotify.playlist.service";

const mockJwtVerify = jwt.verify as jest.Mock;
const mockGetValidAccessToken = getValidAccessToken as jest.Mock;
const mockGetUserPlaylists = getUserPlaylists as jest.Mock;
const mockGetPlaylistTracks = getPlaylistTracks as jest.Mock;
const mockGetUserLikedSongs = getUserLikedSongs as jest.Mock;

const app = express();
app.use(cookieParser());
app.use("/playlists", playlistRouter);
app.use("/library", libraryRouter);

beforeEach(() => {
    jest.clearAllMocks();
    mockJwtVerify.mockReturnValue({ spotifyId: "spotify-user-123" });
    mockGetValidAccessToken.mockResolvedValue("access-token-abc");
    mockGetUserPlaylists.mockResolvedValue([]);
    mockGetPlaylistTracks.mockResolvedValue([]);
    mockGetUserLikedSongs.mockResolvedValue([]);
});

const authedGet = (path: string) =>
    request(app).get(path).set("Cookie", "jwt=valid-token");

// =============================================================================
// GET /playlists
// =============================================================================
describe("GET /playlists", () => {
    it("returns 401 without a valid JWT", async () => {
        const res = await request(app).get("/playlists");
        expect(res.status).toBe(401);
        expect(mockGetValidAccessToken).not.toHaveBeenCalled();
    });

    it("delegates with the valid access token and returns the playlists", async () => {
        const playlists = [{ id: "pl1", name: "One" }];
        mockGetUserPlaylists.mockResolvedValue(playlists);

        const res = await authedGet("/playlists");

        expect(res.status).toBe(200);
        expect(res.body).toEqual(playlists);
        expect(mockGetValidAccessToken).toHaveBeenCalledWith("spotify-user-123");
        expect(mockGetUserPlaylists).toHaveBeenCalledWith("access-token-abc");
    });

    it("returns a generic 500 when the playlist service fails", async () => {
        mockGetUserPlaylists.mockRejectedValue(new Error("Spotify down"));

        const res = await authedGet("/playlists");

        expect(res.status).toBe(500);
        expect(res.body).toEqual({ message: "failed to fetch playlists" });
    });
});

// =============================================================================
// GET /playlists/:id/tracks
// =============================================================================
describe("GET /playlists/:id/tracks", () => {
    it("returns 401 without a valid JWT", async () => {
        const res = await request(app).get("/playlists/pl1/tracks");
        expect(res.status).toBe(401);
    });

    it("delegates with the token and id and returns the tracks", async () => {
        const tracks = [{ added_at: "2024-01-01", added_by: null, is_local: false, item: { id: "t1" } }];
        mockGetPlaylistTracks.mockResolvedValue(tracks);

        const res = await authedGet("/playlists/pl1/tracks");

        expect(res.status).toBe(200);
        expect(res.body).toEqual(tracks);
        expect(mockGetValidAccessToken).toHaveBeenCalledWith("spotify-user-123");
        expect(mockGetPlaylistTracks).toHaveBeenCalledWith("access-token-abc", "pl1");
    });

    it("returns a generic 500 when the tracks service fails", async () => {
        mockGetPlaylistTracks.mockRejectedValue(new Error("Spotify down"));

        const res = await authedGet("/playlists/pl1/tracks");

        expect(res.status).toBe(500);
        expect(res.body).toEqual({ message: "failed to fetch playlist tracks" });
    });
});

// =============================================================================
// GET /library/liked
// =============================================================================
describe("GET /library/liked", () => {
    it("returns 401 without a valid JWT", async () => {
        const res = await request(app).get("/library/liked");
        expect(res.status).toBe(401);
    });

    it("delegates with the valid access token and returns the liked songs", async () => {
        const songs = [{ added_at: "2024-01-01", track: { id: "t1" } }];
        mockGetUserLikedSongs.mockResolvedValue(songs);

        const res = await authedGet("/library/liked");

        expect(res.status).toBe(200);
        expect(res.body).toEqual(songs);
        expect(mockGetValidAccessToken).toHaveBeenCalledWith("spotify-user-123");
        expect(mockGetUserLikedSongs).toHaveBeenCalledWith("access-token-abc");
    });

    it("returns a generic 500 when the liked-songs service fails", async () => {
        mockGetUserLikedSongs.mockRejectedValue(new Error("Spotify down"));

        const res = await authedGet("/library/liked");

        expect(res.status).toBe(500);
        expect(res.body).toEqual({ message: "failed to fetch liked songs" });
    });
});
