// mongo.user.services.test.ts
//
// These tests use mongodb-memory-server to spin up a real (but in-memory) MongoDB
// instance. This is better than mocking Mongoose because it actually exercises
// the query logic — things like $set behavior and upsert semantics.
//
// The tradeoff: these tests are slower (~1-2s startup) and need the binary to be
// downloaded on first run. Worth it because the conditional refresh token write
// is genuinely tricky logic that a mock wouldn't catch bugs in.

import { MongoMemoryServer } from "mongodb-memory-server";
import mongoose from "mongoose";
import { UserModel } from "../../models/User";
import {
    upsertUser,
    getUserInfo,
    getRefreshToken,
    updateRefreshToken,
} from "../../services/mongo.user.services";
import type { BaseUser } from "../../types/user.types";

let mongod: MongoMemoryServer;

// ─── Lifecycle ────────────────────────────────────────────────────────────────
// beforeAll: start in-memory MongoDB once before all tests in this file.
// afterAll: stop it and disconnect when all tests are done.
// afterEach: drop the database between tests so each test starts with a clean slate.
// This prevents test ordering issues — test B can't accidentally rely on data
// created by test A.

beforeAll(async () => {
    mongod = await MongoMemoryServer.create();
    await mongoose.connect(mongod.getUri());
});

afterAll(async () => {
    await mongoose.disconnect();
    await mongod.stop();
});

afterEach(async () => {
    await mongoose.connection.dropDatabase();
});

// ─── Helpers ──────────────────────────────────────────────────────────────────
// Reusable test data. We define it once so tests stay readable.
const baseUser: BaseUser = {
    spotifyId: "spotify-123",
    displayName: "Test User",
    profilePictureUrl: "https://example.com/pic.jpg",
    refreshToken: "initial-refresh-token",
};

// =============================================================================
// upsertUser
// =============================================================================
describe("upsertUser", () => {

    // ── New user ──────────────────────────────────────────────────────────────
    it("creates a new user document when the spotifyId doesn't exist", async () => {
        await upsertUser(baseUser);

        const found = await UserModel.findOne({ spotifyId: "spotify-123" });
        expect(found).not.toBeNull();
        expect(found!.displayName).toBe("Test User");
        expect(found!.profilePictureUrl).toBe("https://example.com/pic.jpg");
        expect(found!.refreshToken).toBe("initial-refresh-token");
    });

    // ── Existing user, new refresh token ─────────────────────────────────────
    // This is THE tricky case. When a user logs in again and Spotify sends a
    // refresh token, we must overwrite the old one. This test verifies the
    // conditional $set in upsertUser correctly writes it.
    it("updates the refresh token when a new one is provided", async () => {
        // First insert the user
        await upsertUser(baseUser);

        // Now simulate a second login where Spotify returns a new refresh token
        await upsertUser({
            ...baseUser,
            refreshToken: "new-refresh-token",
        });

        const found = await UserModel.findOne({ spotifyId: "spotify-123" });
        expect(found!.refreshToken).toBe("new-refresh-token");
    });

    // ── Existing user, NO refresh token returned ──────────────────────────────
    // Spotify doesn't always return a refresh token on repeat logins.
    // When refreshToken is absent from BaseUser, we must NOT overwrite the
    // stored one — otherwise the user would be permanently logged out.
    // This is the most important behavioral test in the whole file.
    it("preserves the existing refresh token when none is provided on re-login", async () => {
        // First login: user has a refresh token
        await upsertUser(baseUser);

        // Second login: Spotify didn't return a refresh token
        // Note: omitting refreshToken entirely (not setting it to undefined)
        // because exactOptionalPropertyTypes is on
        const { refreshToken: _, ...userWithoutToken } = baseUser;
        await upsertUser(userWithoutToken);

        const found = await UserModel.findOne({ spotifyId: "spotify-123" });
        // The original refresh token should still be there
        expect(found!.refreshToken).toBe("initial-refresh-token");
    });

    // ── Upsert updates display fields ─────────────────────────────────────────
    it("updates displayName and profilePictureUrl on re-login", async () => {
        await upsertUser(baseUser);
        await upsertUser({
            ...baseUser,
            displayName: "New Display Name",
            profilePictureUrl: "https://example.com/new.jpg",
        });

        const found = await UserModel.findOne({ spotifyId: "spotify-123" });
        expect(found!.displayName).toBe("New Display Name");
        expect(found!.profilePictureUrl).toBe("https://example.com/new.jpg");
    });
});

// =============================================================================
// getUserInfo
// =============================================================================
describe("getUserInfo", () => {
    it("returns PublicUser fields for a known spotifyId", async () => {
        await upsertUser(baseUser);

        const result = await getUserInfo("spotify-123");

        expect(result).not.toBeNull();
        // PublicUser = spotifyId + displayName + profilePictureUrl only
        // refreshToken should NOT be included
        expect(result!.spotifyId).toBe("spotify-123");
        expect(result!.displayName).toBe("Test User");
        expect(result!.profilePictureUrl).toBe("https://example.com/pic.jpg");
        expect((result as any).refreshToken).toBeUndefined();
    });

    it("returns null for an unknown spotifyId", async () => {
        const result = await getUserInfo("does-not-exist");
        expect(result).toBeNull();
    });
});

// =============================================================================
// getRefreshToken
// =============================================================================
describe("getRefreshToken", () => {
    it("returns the stored refresh token for a known user", async () => {
        await upsertUser(baseUser);

        const token = await getRefreshToken("spotify-123");

        expect(token).toBe("initial-refresh-token");
    });

    it("returns null for an unknown user", async () => {
        const token = await getRefreshToken("does-not-exist");
        expect(token).toBeNull();
    });
});

// =============================================================================
// updateRefreshToken
// =============================================================================
describe("updateRefreshToken", () => {
    it("overwrites the refresh token for an existing user", async () => {
        await upsertUser(baseUser);

        await updateRefreshToken("spotify-123", "rotated-token");

        const found = await UserModel.findOne({ spotifyId: "spotify-123" });
        expect(found!.refreshToken).toBe("rotated-token");
    });
});
