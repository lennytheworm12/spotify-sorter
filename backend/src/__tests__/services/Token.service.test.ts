// token.service.test.ts
//
// We're testing the logic inside token.service.ts, specifically getValidAccessToken.
// That function touches THREE external systems: Redis, MongoDB, and Spotify's API.
//
// The trick is that we don't actually want to talk to any of them during tests.
// Instead we use jest.mock() to swap those modules out with fake versions we control.
// That way each test is just checking the *logic* in our code, not the network.

import {
    getAccessToken,
    setAccessToken,
    deleteAccessToken,
    getValidAccessToken,
} from "../../services/token.service";

// ─── 1. Mock ioredis ───────────────────────────────────────────────────────────
// redis.ts exports a single redis client instance. When token.service.ts does
// `import redis from "../utils/redis"` it will get THIS mock object instead.
// We give it get/set/del as jest.fn() so we can control what they return per test.
jest.mock("../../utils/redis", () => ({
    get: jest.fn(),
    set: jest.fn(),
    del: jest.fn(),
}));

// ─── 2. Mock mongo.user.services ──────────────────────────────────────────────
// token.service.ts imports getRefreshToken and updateRefreshToken from here.
// We mock the whole module so those functions are jest.fn() stubs.
jest.mock("../../services/mongo.user.services", () => ({
    getRefreshToken: jest.fn(),
    updateRefreshToken: jest.fn(),
}));

// ─── 3. Mock spotify.user.service ─────────────────────────────────────────────
// This is what hits the Spotify /token endpoint to get a new access token.
jest.mock("../../services/spotify.user.service", () => ({
    refreshAccessToken: jest.fn(),
}));

// Now import the mocked versions so we can control them in each test.
// We cast them `as jest.Mock` so TypeScript lets us call .mockResolvedValue() etc.
import redis from "../../utils/redis";
import { getRefreshToken, updateRefreshToken } from "../../services/mongo.user.services";
import { refreshAccessToken } from "../../services/spotify.user.service";

const mockRedisGet = redis.get as jest.Mock;
const mockRedisSet = redis.set as jest.Mock;
const mockRedisDel = redis.del as jest.Mock;
const mockGetRefreshToken = getRefreshToken as jest.Mock;
const mockUpdateRefreshToken = updateRefreshToken as jest.Mock;
const mockRefreshAccessToken = refreshAccessToken as jest.Mock;

// ─── beforeEach ────────────────────────────────────────────────────────────────
// We reset all mocks before every test so state from one test can't bleed into
// the next. Without this, a .mockResolvedValue() set in test 1 would still be
// active in test 2.
beforeEach(() => {
    jest.resetAllMocks();
});

// =============================================================================
// setAccessToken
// =============================================================================
describe("setAccessToken", () => {
    it("writes the token to Redis with the correct key and 3600s TTL", async () => {
        mockRedisSet.mockResolvedValue("OK");

        await setAccessToken("user123", "access-abc");

        // We're checking that redis.set was called with exactly these four arguments.
        // The key format is `user:<spotifyId>:accessToken`.
        // 'EX' and 3600 are the Redis TTL flag and value.
        expect(mockRedisSet).toHaveBeenCalledWith(
            "user:user123:accessToken",
            "access-abc",
            "EX",
            3600
        );
    });
});

// =============================================================================
// getAccessToken
// =============================================================================
describe("getAccessToken", () => {
    it("returns the token string when it exists in Redis", async () => {
        mockRedisGet.mockResolvedValue("access-abc");

        const result = await getAccessToken("user123");

        expect(result).toBe("access-abc");
        expect(mockRedisGet).toHaveBeenCalledWith("user:user123:accessToken");
    });

    it("returns null when the key doesn't exist in Redis", async () => {
        // Redis returns null when a key doesn't exist
        mockRedisGet.mockResolvedValue(null);

        const result = await getAccessToken("user123");

        expect(result).toBeNull();
    });
});

// =============================================================================
// deleteAccessToken
// =============================================================================
describe("deleteAccessToken", () => {
    it("calls redis.del with the correct key", async () => {
        mockRedisDel.mockResolvedValue(1);

        await deleteAccessToken("user123");

        expect(mockRedisDel).toHaveBeenCalledWith("user:user123:accessToken");
    });
});

// =============================================================================
// getValidAccessToken — the main event
// =============================================================================
// This is the most important function to test. It has branching logic:
//   1. Fast path: token is in Redis → return immediately
//   2. Slow path: token not in Redis → get refresh token from Mongo → call Spotify
//      2a. Spotify returned a NEW refresh token → update Mongo
//      2b. Spotify returned the SAME refresh token → don't update Mongo
//   3. Error path: no refresh token exists → throw
describe("getValidAccessToken", () => {

    // ── Branch 1: Token already in Redis ──────────────────────────────────────
    it("returns the cached token immediately when Redis has it", async () => {
        mockRedisGet.mockResolvedValue("cached-access-token");

        const result = await getValidAccessToken("user123");

        expect(result).toBe("cached-access-token");

        // The important thing here: because we found it in Redis, we should
        // NEVER have touched Mongo or Spotify at all.
        expect(mockGetRefreshToken).not.toHaveBeenCalled();
        expect(mockRefreshAccessToken).not.toHaveBeenCalled();
    });

    // ── Branch 2: Token missing from Redis, refresh succeeds ─────────────────
    it("fetches a new access token via refresh when Redis returns null", async () => {
        mockRedisGet.mockResolvedValue(null); // simulate expired/missing token
        mockGetRefreshToken.mockResolvedValue("stored-refresh-token");
        mockRefreshAccessToken.mockResolvedValue({
            access_token: "new-access-token",
            token_type: "Bearer",
            scope: "playlist-read-private",
            expires_in: 3600,
            // No refresh_token — Spotify doesn't always return one
        });

        const result = await getValidAccessToken("user123");

        expect(result).toBe("new-access-token");

        // Verify the new access token was written back to Redis
        expect(mockRedisSet).toHaveBeenCalledWith(
            "user:user123:accessToken",
            "new-access-token",
            "EX",
            3600
        );
    });

    // ── Branch 2a: Spotify returns a NEW refresh token ────────────────────────
    // When Spotify rotates the refresh token we MUST update Mongo, otherwise
    // the user will be permanently logged out after the next token expiry.
    it("updates MongoDB refresh token when Spotify returns a different one", async () => {
        mockRedisGet.mockResolvedValue(null);
        mockGetRefreshToken.mockResolvedValue("old-refresh-token");
        mockRefreshAccessToken.mockResolvedValue({
            access_token: "new-access-token",
            token_type: "Bearer",
            scope: "playlist-read-private",
            expires_in: 3600,
            refresh_token: "brand-new-refresh-token", // different from "old-refresh-token"
        });

        await getValidAccessToken("user123");

        // updateRefreshToken must be called with the NEW refresh token
        expect(mockUpdateRefreshToken).toHaveBeenCalledWith(
            "user123",
            "brand-new-refresh-token"
        );
    });

    // ── Branch 2b: Spotify returns the SAME refresh token ─────────────────────
    // Spotify sometimes echoes back the same refresh token. In that case we
    // should NOT write to Mongo — it's a wasted write and we'd overwrite with identical data.
    it("does NOT update MongoDB when Spotify returns the same refresh token", async () => {
        mockRedisGet.mockResolvedValue(null);
        mockGetRefreshToken.mockResolvedValue("same-refresh-token");
        mockRefreshAccessToken.mockResolvedValue({
            access_token: "new-access-token",
            token_type: "Bearer",
            scope: "playlist-read-private",
            expires_in: 3600,
            refresh_token: "same-refresh-token", // identical to stored
        });

        await getValidAccessToken("user123");

        expect(mockUpdateRefreshToken).not.toHaveBeenCalled();
    });

    // ── Branch 3: No refresh token in Mongo → throw ───────────────────────────
    // If there's no refresh token we literally cannot get a new access token.
    // The function should throw so the caller can return a 401 or 500.
    it("throws when no refresh token exists in MongoDB", async () => {
        mockRedisGet.mockResolvedValue(null);
        mockGetRefreshToken.mockResolvedValue(null); // user has no refresh token

        await expect(getValidAccessToken("user123")).rejects.toThrow(
            "no refresh token found for this id"
        );

        // We should never have tried to call Spotify
        expect(mockRefreshAccessToken).not.toHaveBeenCalled();
    });
});
