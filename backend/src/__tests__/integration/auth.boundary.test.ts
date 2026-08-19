// auth.boundary.test.ts
//
// Full HTTP boundary test over the real route stack (src/app.ts):
// callback establishes the JWT cookie → /auth/me succeeds with it →
// logout clears the cookie and the Redis token. Protected routes without a
// cookie are rejected. All external services (Spotify, Redis, Mongo) are
// mocked; no server port or database connection is opened.

import request from "supertest";
import { app } from "../../app";

jest.mock("../../env", () => ({
    env: {
        NODE_ENV: "test",
        PORT: 3000,
        JWT_SECRET: "test-secret-with-enough-length-1234567890",
        FRONTEND_URL: "http://localhost:5173",
        SPOTIFY_CLIENT_ID: "test-client-id",
        SPOTIFY_CLIENT_SECRET: "test-client-secret",
        SPOTIFY_REDIRECT_URI: "http://localhost:3000/auth/spotify/callback",
    },
}));

jest.mock("jsonwebtoken", () => ({
    __esModule: true,
    default: {
        sign: jest.fn().mockReturnValue("signed-jwt-token"),
        verify: jest.fn().mockReturnValue({ spotifyId: "spotify-user-123" }),
    },
}));

jest.mock("../../services/spotify.auth.service", () => ({
    exchangeToken: jest.fn(),
}));

jest.mock("../../services/spotify.user.service", () => ({
    getSpotifyUserData: jest.fn(),
}));

jest.mock("../../services/mongo.user.services", () => ({
    upsertUser: jest.fn(),
    getUserInfo: jest.fn(),
}));

jest.mock("../../services/token.service", () => ({
    setAccessToken: jest.fn(),
    deleteAccessToken: jest.fn(),
    getValidAccessToken: jest.fn(),
}));

jest.mock("../../services/sort.action.service", () => ({
    createSortAction: jest.fn(),
    getLatestSortAction: jest.fn(),
    getSortAction: jest.fn(),
    updateSortAction: jest.fn(),
}));

import { exchangeToken } from "../../services/spotify.auth.service";
import { getSpotifyUserData } from "../../services/spotify.user.service";
import { upsertUser, getUserInfo } from "../../services/mongo.user.services";
import { setAccessToken, deleteAccessToken } from "../../services/token.service";

const mockExchangeToken = exchangeToken as jest.Mock;
const mockGetSpotifyUserData = getSpotifyUserData as jest.Mock;
const mockUpsertUser = upsertUser as jest.Mock;
const mockSetAccessToken = setAccessToken as jest.Mock;
const mockDeleteAccessToken = deleteAccessToken as jest.Mock;
const mockGetUserInfo = getUserInfo as jest.Mock;

const STORED_STATE = "state-123";

const mockToken = {
    access_token: "access-abc",
    token_type: "Bearer",
    scope: "playlist-read-private",
    expires_in: 3600,
    refresh_token: "refresh-xyz",
};

const mockSpotifyUser = {
    id: "spotify-user-123",
    display_name: "Test User",
    images: [{ url: "https://example.com/pic.jpg", height: 100, width: 100 }],
    uri: "spotify:user:123",
    href: "https://api.spotify.com/v1/users/123",
    external_urls: { spotify: "https://open.spotify.com/user/123" },
    type: "user" as const,
};

beforeEach(() => {
    jest.clearAllMocks();
    mockExchangeToken.mockResolvedValue(mockToken);
    mockGetSpotifyUserData.mockResolvedValue(mockSpotifyUser);
    mockUpsertUser.mockResolvedValue(undefined);
    mockSetAccessToken.mockResolvedValue(undefined);
    mockDeleteAccessToken.mockResolvedValue(undefined);
    mockGetUserInfo.mockResolvedValue({
        spotifyId: "spotify-user-123",
        displayName: "Test User",
        profilePictureUrl: "https://example.com/pic.jpg",
    });
});

const login = async () => {
    const res = await request(app)
        .get("/auth/spotify/callback")
        .set("Cookie", `spotify_auth_state=${STORED_STATE}`)
        .query({ code: "auth-code", state: STORED_STATE });

    const cookies = res.headers["set-cookie"] as string[] | string;
    const cookieArray = Array.isArray(cookies) ? cookies : [cookies];
    const jwtCookie = cookieArray.find(c => c.startsWith("jwt="))!;
    return { res, jwtValue: jwtCookie.split(";")[0] };
};

describe("auth boundary", () => {
    it("rejects protected routes without a JWT cookie", async () => {
        const res = await request(app).get("/auth/me");
        expect(res.status).toBe(401);
    });

    it("callback establishes the JWT cookie, then /auth/me succeeds with it", async () => {
        const { res: callbackRes, jwtValue } = await login();

        expect(callbackRes.status).toBe(302);
        expect(callbackRes.headers.location).toBe("http://localhost:5173/?auth=success");
        expect(callbackRes.headers["set-cookie"]).toEqual(
            expect.arrayContaining([expect.stringContaining("jwt=signed-jwt-token")])
        );
        expect(mockSetAccessToken).toHaveBeenCalledWith("spotify-user-123", "access-abc");
        expect(mockUpsertUser).toHaveBeenCalledTimes(1);

        const meRes = await request(app)
            .get("/auth/me")
            .set("Cookie", jwtValue);

        expect(meRes.status).toBe(200);
        expect(meRes.body).toEqual({
            spotifyId: "spotify-user-123",
            displayName: "Test User",
            profilePictureUrl: "https://example.com/pic.jpg",
        });
    });

    it("logout clears the JWT cookie and deletes the Redis access token", async () => {
        const { jwtValue } = await login();

        const res = await request(app)
            .post("/auth/logout")
            .set("Cookie", jwtValue);

        expect(res.status).toBe(200);
        expect(mockDeleteAccessToken).toHaveBeenCalledWith("spotify-user-123");
        const cookies = res.headers["set-cookie"] as string[] | string;
        const cookieString = Array.isArray(cookies) ? cookies.join(";") : cookies;
        expect(cookieString).toContain("jwt=");
        expect(cookieString).toMatch(/Max-Age=0|Expires=.*1970/);
    });

    it("redirects to an error marker when the token exchange fails", async () => {
        mockExchangeToken.mockRejectedValue(new Error("Spotify API down"));

        const res = await request(app)
            .get("/auth/spotify/callback")
            .set("Cookie", `spotify_auth_state=${STORED_STATE}`)
            .query({ code: "bad-code", state: STORED_STATE });

        expect(res.status).toBe(302);
        expect(res.headers.location).toBe("http://localhost:5173/?auth=error&reason=callback_failed");
    });
});
