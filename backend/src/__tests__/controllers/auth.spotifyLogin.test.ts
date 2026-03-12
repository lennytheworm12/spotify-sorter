// auth.spotifyLogin.test.ts
//
// SpotifyUserLogin is the simplest controller — it just builds a URL and redirects.
// No database, no Redis, no Spotify API calls.
//
// What we're testing:
//   1. It redirects (302) to the Spotify authorize URL
//   2. The redirect URL has all the correct query params
//   3. The state cookie is set correctly (httpOnly, 10min TTL)
//
// We mock crypto.randomUUID so the state value is predictable in assertions.

import express from "express";
import request from "supertest";
import cookieParser from "cookie-parser";
import { SpotifyUserLogin } from "../../controllers/auth.spotifyLogin";

jest.mock("../../env", () => ({
    env: {
        SPOTIFY_CLIENT_ID: "test-client-id",
        SPOTIFY_REDIRECT_URI: "http://localhost:3000/auth/spotify/callback",
        JWT_SECRET: "test-secret",
    },
}));

// Mock crypto.randomUUID so the state value is deterministic.
// Without this, the state changes every run and we can't assert on it.
jest.mock("crypto", () => ({
    ...jest.requireActual("crypto"),
    randomUUID: jest.fn().mockReturnValue("fixed-state-uuid"),
}));

const app = express();
app.use(cookieParser());
app.get("/auth/spotify/login", SpotifyUserLogin);

beforeEach(() => {
    jest.clearAllMocks();
});

describe("SpotifyUserLogin", () => {

    // ── Redirects to Spotify ───────────────────────────────────────────────────
    // The controller should return a 302 redirect, not a 200 with a body.
    it("redirects to the Spotify authorize URL", async () => {
        const res = await request(app).get("/auth/spotify/login");

        expect(res.status).toBe(302);
        expect(res.headers.location).toContain("https://accounts.spotify.com/authorize");
    });

    // ── Correct client_id ─────────────────────────────────────────────────────
    it("includes the correct client_id in the redirect URL", async () => {
        const res = await request(app).get("/auth/spotify/login");

        expect(res.headers.location).toContain("client_id=test-client-id");
    });

    // ── Correct redirect_uri ──────────────────────────────────────────────────
    it("includes the correct redirect_uri in the redirect URL", async () => {
        const res = await request(app).get("/auth/spotify/login");

        const location = res.headers.location as string;
        // redirect_uri is URL-encoded in the query string
        expect(decodeURIComponent(location)).toContain(
            "redirect_uri=http://localhost:3000/auth/spotify/callback"
        );
    });

    // ── response_type=code ────────────────────────────────────────────────────
    it("includes response_type=code in the redirect URL", async () => {
        const res = await request(app).get("/auth/spotify/login");

        expect(res.headers.location).toContain("response_type=code");
    });

    // ── Scopes are present ────────────────────────────────────────────────────
    // We don't assert the exact scope string (it's long and order could change),
    // but we verify the key scopes are included.
    it("includes required scopes in the redirect URL", async () => {
        const res = await request(app).get("/auth/spotify/login");

        const location = decodeURIComponent(res.headers.location as string);
        expect(location).toContain("playlist-read-private");
        expect(location).toContain("user-read-email");
        expect(location).toContain("playlist-modify-public");
    });

    // ── State param is set ────────────────────────────────────────────────────
    it("includes the state param in the redirect URL", async () => {
        const res = await request(app).get("/auth/spotify/login");

        expect(res.headers.location).toContain("state=fixed-state-uuid");
    });

    // ── State cookie is set ───────────────────────────────────────────────────
    // The state is also stored in a cookie so the callback can verify it.
    // This is the CSRF protection mechanism.
    it("sets the spotify_auth_state cookie with httpOnly and 10min TTL", async () => {
        const res = await request(app).get("/auth/spotify/login");

        const cookies = res.headers["set-cookie"] as string[] | string;
        const cookieString = Array.isArray(cookies) ? cookies.join(";") : cookies;

        expect(cookieString).toContain("spotify_auth_state=fixed-state-uuid");
        expect(cookieString).toContain("HttpOnly");
        // Max-Age should be 600 seconds (10 minutes)
        expect(cookieString).toContain("Max-Age=600");
    });

    // ── State in URL matches state in cookie ──────────────────────────────────
    // Both should be the same value — this is what the callback verifies.
    it("uses the same state value in both the URL and the cookie", async () => {
        const res = await request(app).get("/auth/spotify/login");

        const location = res.headers.location as string;
        const cookies = res.headers["set-cookie"] as string[] | string;
        const cookieString = Array.isArray(cookies) ? cookies.join(";") : cookies;

        expect(location).toContain("state=fixed-state-uuid");
        expect(cookieString).toContain("spotify_auth_state=fixed-state-uuid");
    });
    it("returns 500 when an unexpected error occurs", async () => {
        const crypto = require("crypto");
        crypto.randomUUID.mockImplementationOnce(() => {
            throw new Error("crypto failed");
        });

        const res = await request(app).get("/auth/spotify/login");

        expect(res.status).toBe(500);
        expect(res.body.error).toBe("failed to initiate login");
    });
});
