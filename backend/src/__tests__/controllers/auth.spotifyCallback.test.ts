// auth.spotifyCallback.test.ts
//
// SpotifyCallback is a controller that orchestrates the whole OAuth flow.
// It calls 5 different service functions in sequence. We mock ALL of them
// and just verify that given certain inputs, the controller:
//   - calls the right functions
//   - handles error cases correctly
//   - sets the right cookie
//
// We use Supertest + a mini Express app again (same pattern as middleware tests).
// The key difference: here we're mocking entire service modules, not low-level libs.

import express from "express";
import request from "supertest";
import cookieParser from "cookie-parser";
import { SpotifyCallback } from "../../controllers/auth.spotifyCallback";

// ─── Mock all service dependencies ────────────────────────────────────────────
// Each of these is a jest.fn() that we can configure per test.
jest.mock("../../services/spotify.auth.service", () => ({
    exchangeToken: jest.fn(),
}));
jest.mock("../../services/spotify.user.service", () => ({
    getSpotifyUserData: jest.fn(),
}));
jest.mock("../../services/mongo.user.services", () => ({
    upsertUser: jest.fn(),
}));
jest.mock("../../services/token.service", () => ({
    setAccessToken: jest.fn(),
}));

// We mock jwt.sign because we don't want real crypto in unit tests,
// and we can verify it was called with the right payload.
jest.mock("jsonwebtoken", () => ({
    __esModule: true,
    default: {
        sign: jest.fn().mockReturnValue("mock-jwt-token"),
        verify: jest.fn(),
    },
}));

jest.mock("../../env", () => ({
    env: {
        JWT_SECRET: "test-secret",
        SPOTIFY_CLIENT_ID: "test-client-id",
        SPOTIFY_CLIENT_SECRET: "test-client-secret",
        SPOTIFY_REDIRECT_URI: "http://localhost:3000/auth/spotify/callback",
    },
}));

// ─── Import mocked modules ────────────────────────────────────────────────────
import { exchangeToken } from "../../services/spotify.auth.service";
import { getSpotifyUserData } from "../../services/spotify.user.service";
import { upsertUser } from "../../services/mongo.user.services";
import { setAccessToken } from "../../services/token.service";

const mockExchangeToken = exchangeToken as jest.Mock;
const mockGetSpotifyUserData = getSpotifyUserData as jest.Mock;
const mockUpsertUser = upsertUser as jest.Mock;
const mockSetAccessToken = setAccessToken as jest.Mock;

// ─── Mini app ─────────────────────────────────────────────────────────────────
const app = express();
app.use(cookieParser());
app.get("/auth/spotify/callback", SpotifyCallback);

// ─── Shared happy-path data ───────────────────────────────────────────────────
// These are the mocked return values for the successful flow.
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

// ─── The stored state we'll put in cookies ────────────────────────────────────
// The state cookie is set by the login route. We simulate it being present here.
const STORED_STATE = "correct-state-value";

beforeEach(() => {
    jest.clearAllMocks();  // ← not resetAllMocks
    mockExchangeToken.mockResolvedValue(mockToken);
    mockGetSpotifyUserData.mockResolvedValue(mockSpotifyUser);
    mockUpsertUser.mockResolvedValue(undefined);
    mockSetAccessToken.mockResolvedValue(undefined);
});

// =============================================================================
// SpotifyCallback — error/guard cases
// =============================================================================
describe("SpotifyCallback — guard cases", () => {

    // ── Spotify returned an error ─────────────────────────────────────────────
    // User denied access on the Spotify consent screen.
    // The 'error' query param will be set, e.g. ?error=access_denied
    it("returns 404 when Spotify returns an error param", async () => {
        const res = await request(app)
            .get("/auth/spotify/callback")
            .set("Cookie", `spotify_auth_state=${STORED_STATE}`)
            .query({ error: "access_denied", state: STORED_STATE });

        expect(res.status).toBe(404);
        expect(res.body.message).toBe("user access was denied");
    });

    // ── State mismatch ────────────────────────────────────────────────────────
    // The state in the URL doesn't match the cookie. This is a CSRF check.
    // We reject immediately — don't proceed with the code.
    it("returns 404 when state param doesn't match the stored cookie", async () => {
        const res = await request(app)
            .get("/auth/spotify/callback")
            .set("Cookie", `spotify_auth_state=${STORED_STATE}`)
            .query({ code: "some-code", state: "WRONG-STATE" });

        expect(res.status).toBe(404);
        expect(res.body.message).toBe("state was not matched");
        expect(mockExchangeToken).not.toHaveBeenCalled();
    });

    // ── Missing state ─────────────────────────────────────────────────────────
    it("returns 404 when state param is missing entirely", async () => {
        const res = await request(app)
            .get("/auth/spotify/callback")
            .set("Cookie", `spotify_auth_state=${STORED_STATE}`)
            .query({ code: "some-code" }); // no state

        expect(res.status).toBe(404);
    });

    // ── No code ───────────────────────────────────────────────────────────────
    // State matched but no authorization code — shouldn't happen in normal flow,
    // but we guard against it anyway.
    it("returns 404 when code is missing from query params", async () => {
        const res = await request(app)
            .get("/auth/spotify/callback")
            .set("Cookie", `spotify_auth_state=${STORED_STATE}`)
            .query({ state: STORED_STATE }); // no code

        expect(res.status).toBe(404);
        expect(res.body.message).toBe("code was not found");
    });
});

// =============================================================================
// SpotifyCallback — happy path
// =============================================================================
describe("SpotifyCallback — successful OAuth flow", () => {
    // Helper to send a valid callback request
    const validCallbackRequest = () =>
        request(app)
            .get("/auth/spotify/callback")
            .set("Cookie", `spotify_auth_state=${STORED_STATE}`)
            .query({ code: "auth-code-123", state: STORED_STATE });

    it("calls exchangeToken with the authorization code", async () => {
        await validCallbackRequest();
        expect(mockExchangeToken).toHaveBeenCalledWith("auth-code-123");
    });

    it("calls getSpotifyUserData with the access token from exchangeToken", async () => {
        await validCallbackRequest();
        expect(mockGetSpotifyUserData).toHaveBeenCalledWith("access-abc");
    });

    it("calls upsertUser to store the user in MongoDB", async () => {
        await validCallbackRequest();
        // upsertUser should be called — we don't assert the exact shape here
        // because mapSpotifyUserToDBUser is tested separately in mappers.test.ts
        expect(mockUpsertUser).toHaveBeenCalledTimes(1);
    });

    it("calls setAccessToken with the spotifyId and access token", async () => {
        await validCallbackRequest();
        expect(mockSetAccessToken).toHaveBeenCalledWith(
            "spotify-user-123",
            "access-abc"
        );
    });

    it("sets an httpOnly JWT cookie on success", async () => {
        const res = await validCallbackRequest();

        // Supertest exposes set-cookie headers
        const cookies = res.headers["set-cookie"] as string[] | string;
        const cookieString = Array.isArray(cookies) ? cookies.join(";") : cookies;

        expect(cookieString).toContain("jwt=mock-jwt-token");
        expect(cookieString).toContain("HttpOnly");
    });

    it("returns 200 on a fully successful flow", async () => {
        const res = await validCallbackRequest();
        expect(res.status).toBe(200);
    });
});

// =============================================================================
// SpotifyCallback — service throws
// =============================================================================
describe("SpotifyCallback — service error handling", () => {

    it("returns 500 when exchangeToken throws", async () => {
        mockExchangeToken.mockRejectedValue(new Error("Spotify API down"));

        const res = await request(app)
            .get("/auth/spotify/callback")
            .set("Cookie", `spotify_auth_state=${STORED_STATE}`)
            .query({ code: "auth-code-123", state: STORED_STATE });

        expect(res.status).toBe(500);
        expect(res.body.error).toBe("failed to initiate callback");
    });

    it("returns 500 when getSpotifyUserData throws", async () => {
        mockGetSpotifyUserData.mockRejectedValue(new Error("rate limited"));

        const res = await request(app)
            .get("/auth/spotify/callback")
            .set("Cookie", `spotify_auth_state=${STORED_STATE}`)
            .query({ code: "auth-code-123", state: STORED_STATE });

        expect(res.status).toBe(500);
    });

    it("returns 500 when upsertUser throws", async () => {
        mockUpsertUser.mockRejectedValue(new Error("DB write failed"));

        const res = await request(app)
            .get("/auth/spotify/callback")
            .set("Cookie", `spotify_auth_state=${STORED_STATE}`)
            .query({ code: "auth-code-123", state: STORED_STATE });

        expect(res.status).toBe(500);
    });
});
