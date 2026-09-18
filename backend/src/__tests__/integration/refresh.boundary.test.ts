// refresh.boundary.test.ts
//
// End-to-end refresh orchestration through a real protected HTTP route
// (GET /playlists). Unlike the unit tests, token.service.getValidAccessToken is
// NOT mocked: the full Redis-miss -> Mongo refresh-token load -> Spotify
// refresh -> Mongo rotation -> Redis write -> playlist fetch chain runs for
// real inside the route. Redis, Mongo CRUD, Spotify refresh, and the playlist
// API are mocked; no real sockets are opened.

import request from "supertest";
import { app } from "../../app";

jest.mock("../../env", () => ({
    env: {
        NODE_ENV: "test",
        PORT: 3000,
        MONGO_URI: "mongodb://localhost:27017/spotify",
        REDIS_URI: "redis://localhost:6379",
        SPOTIFY_CLIENT_ID: "test-client-id",
        SPOTIFY_CLIENT_SECRET: "test-client-secret",
        SPOTIFY_REDIRECT_URI: "http://127.0.0.1:3000/auth/spotify/callback",
        JWT_SECRET: "test-secret-with-enough-length-1234567890",
        FRONTEND_URL: "http://127.0.0.1:5173",
    },
}));

jest.mock("jsonwebtoken", () => ({
    __esModule: true,
    default: {
        sign: jest.fn(),
        verify: jest.fn().mockReturnValue({ spotifyId: "spotify-user-123" }),
    },
}));

jest.mock("../../utils/redis", () => ({
    get: jest.fn(),
    set: jest.fn(),
    del: jest.fn(),
}));

jest.mock("../../services/mongo.user.services", () => ({
    upsertUser: jest.fn(),
    getUserInfo: jest.fn(),
    getRefreshToken: jest.fn(),
    updateRefreshToken: jest.fn(),
}));

jest.mock("../../services/spotify.user.service", () => ({
    getSpotifyUserData: jest.fn(),
    refreshAccessToken: jest.fn(),
}));

jest.mock("../../services/spotify.playlist.service", () => ({
    getUserPlaylists: jest.fn(),
    getUserLikedSongs: jest.fn(),
    getPlaylistTracks: jest.fn(),
    getPlaylistSnapshot: jest.fn(),
    createPlaylist: jest.fn(),
    addTracksToPlaylist: jest.fn(),
    replacePlaylistItems: jest.fn(),
}));

jest.mock("../../services/sort.action.service", () => ({
    createSortAction: jest.fn(),
    getLatestSortAction: jest.fn(),
    getSortAction: jest.fn(),
    updateSortAction: jest.fn(),
}));

import redis from "../../utils/redis";
import { getRefreshToken, updateRefreshToken } from "../../services/mongo.user.services";
import { refreshAccessToken } from "../../services/spotify.user.service";
import { getUserPlaylists } from "../../services/spotify.playlist.service";

const mockRedisGet = redis.get as jest.Mock;
const mockRedisSet = redis.set as jest.Mock;
const mockGetRefreshToken = getRefreshToken as jest.Mock;
const mockUpdateRefreshToken = updateRefreshToken as jest.Mock;
const mockRefreshAccessToken = refreshAccessToken as jest.Mock;
const mockGetUserPlaylists = getUserPlaylists as jest.Mock;

beforeEach(() => {
    jest.clearAllMocks();
    mockGetUserPlaylists.mockResolvedValue([]);
});

describe("GET /playlists — real refresh orchestration through a protected route", () => {
    it("refreshes on a Redis miss: loads refresh token, rotates it, persists both, then fetches playlists", async () => {
        mockRedisGet.mockResolvedValue(null); // access token expired/missing
        mockGetRefreshToken.mockResolvedValue("stored-refresh-token");
        mockRefreshAccessToken.mockResolvedValue({
            access_token: "refreshed-access-token",
            token_type: "Bearer",
            scope: "playlist-read-private",
            expires_in: 3600,
            refresh_token: "rotated-refresh-token", // Spotify rotated it
        });
        mockGetUserPlaylists.mockResolvedValue([{ id: "pl1", name: "One" }]);

        const res = await request(app)
            .get("/playlists")
            .set("Cookie", "jwt=valid-token");

        expect(res.status).toBe(200);
        expect(res.body).toEqual([{ id: "pl1", name: "One" }]);

        // Redis miss → Mongo refresh token load.
        expect(mockRedisGet).toHaveBeenCalledWith("user:spotify-user-123:accessToken");
        expect(mockGetRefreshToken).toHaveBeenCalledWith("spotify-user-123");

        // Real Spotify refresh call with the stored refresh token.
        expect(mockRefreshAccessToken).toHaveBeenCalledTimes(1);
        expect(mockRefreshAccessToken).toHaveBeenCalledWith("stored-refresh-token");

        // Rotated refresh token persisted to Mongo, new access token to Redis.
        expect(mockUpdateRefreshToken).toHaveBeenCalledWith("spotify-user-123", "rotated-refresh-token");
        expect(mockRedisSet).toHaveBeenCalledWith(
            "user:spotify-user-123:accessToken",
            "refreshed-access-token",
            "EX",
            3600
        );

        // Playlist service receives the refreshed token.
        expect(mockGetUserPlaylists).toHaveBeenCalledWith("refreshed-access-token");
    });

    it("serves the cached token through the same route without touching Mongo or Spotify", async () => {
        mockRedisGet.mockResolvedValue("cached-access-token");
        mockGetUserPlaylists.mockResolvedValue([{ id: "pl2", name: "Two" }]);

        const res = await request(app)
            .get("/playlists")
            .set("Cookie", "jwt=valid-token");

        expect(res.status).toBe(200);
        expect(res.body).toEqual([{ id: "pl2", name: "Two" }]);

        expect(mockGetRefreshToken).not.toHaveBeenCalled();
        expect(mockRefreshAccessToken).not.toHaveBeenCalled();
        expect(mockUpdateRefreshToken).not.toHaveBeenCalled();
        expect(mockRedisSet).not.toHaveBeenCalled();
        expect(mockGetUserPlaylists).toHaveBeenCalledWith("cached-access-token");
    });

    it("does not rewrite Mongo when Spotify echoes the same refresh token", async () => {
        mockRedisGet.mockResolvedValue(null);
        mockGetRefreshToken.mockResolvedValue("same-refresh-token");
        mockRefreshAccessToken.mockResolvedValue({
            access_token: "refreshed-access-token",
            token_type: "Bearer",
            scope: "playlist-read-private",
            expires_in: 3600,
            refresh_token: "same-refresh-token",
        });

        const res = await request(app)
            .get("/playlists")
            .set("Cookie", "jwt=valid-token");

        expect(res.status).toBe(200);
        expect(mockUpdateRefreshToken).not.toHaveBeenCalled();
        expect(mockRedisSet).toHaveBeenCalledWith(
            "user:spotify-user-123:accessToken",
            "refreshed-access-token",
            "EX",
            3600
        );
    });
});
