// artist.cache.service.test.ts
//
// Uses a real in-memory MongoDB (mongodb-memory-server) for persistence and
// mocks the Spotify artist data-access function. Covers freshness, staleness,
// partial hits, dedupe, zero-genre artists, persistence, and 50-item batching.

import { MongoMemoryServer } from "mongodb-memory-server";
import mongoose from "mongoose";
import { ArtistModel } from "../../models/Artist";
import {
    getArtistGenresCached,
    getFreshCachedArtists,
    ARTIST_CACHE_TTL_MS,
} from "../../services/artist.cache.service";

jest.mock("../../services/spotify.artist.service", () => ({
    getArtists: jest.fn(),
}));

import { getArtists } from "../../services/spotify.artist.service";
import type { SpotifyArtist } from "../../types/spotify.types";

const mockGetArtists = getArtists as jest.Mock;

let mongod: MongoMemoryServer;

// The first MongoMemoryServer.create() on a fresh runner downloads the MongoDB
// binary (~120 MB), which can exceed Jest's default 5s hook timeout. Give the
// startup hook an explicit generous timeout so a legitimate cold-start download
// doesn't fail the suite. Teardown is guarded so a failed startup can't mask the
// original setup error with undefined stop() calls or disconnected dropDatabase
// noise.
const MONGO_STARTUP_TIMEOUT_MS = 120_000;

beforeAll(async () => {
    mongod = await MongoMemoryServer.create();
    await mongoose.connect(mongod.getUri());
}, MONGO_STARTUP_TIMEOUT_MS);

afterAll(async () => {
    if (mongod) {
        await mongoose.disconnect();
        await mongod.stop();
    }
});

afterEach(async () => {
    jest.clearAllMocks();
    if (mongoose.connection.readyState === 1) {
        await mongoose.connection.dropDatabase();
    }
});

const makeArtist = (id: string, genres: string[]): SpotifyArtist => ({
    id,
    name: `Artist ${id}`,
    href: `https://api.spotify.com/v1/artists/${id}`,
    uri: `spotify:artist:${id}`,
    external_urls: { spotify: `https://open.spotify.com/artist/${id}` },
    type: "artist",
    genres,
    images: [],
    followers: { href: null, total: 0 },
    popularity: 50,
});

const now = () => new Date();
const staleDate = () => new Date(Date.now() - ARTIST_CACHE_TTL_MS - 60_000);

describe("getArtistGenresCached", () => {
    it("returns an empty map and makes no Spotify calls for no IDs", async () => {
        const result = await getArtistGenresCached("token", []);
        expect(result.size).toBe(0);
        expect(mockGetArtists).not.toHaveBeenCalled();
    });

    it("serves all-fresh artists entirely from cache", async () => {
        await ArtistModel.create([
            { spotifyId: "a1", name: "Artist a1", genres: ["hip hop"], lastFetchedAt: now() },
            { spotifyId: "a2", name: "Artist a2", genres: ["pop"], lastFetchedAt: now() },
        ]);

        const result = await getArtistGenresCached("token", ["a1", "a2"]);

        expect(result.get("a1")).toEqual(["hip hop"]);
        expect(result.get("a2")).toEqual(["pop"]);
        expect(mockGetArtists).not.toHaveBeenCalled();
    });

    it("fetches and persists when nothing is cached", async () => {
        mockGetArtists.mockResolvedValue([makeArtist("a1", ["rock"]), makeArtist("a2", [])]);

        const result = await getArtistGenresCached("token", ["a1", "a2"]);

        expect(result.get("a1")).toEqual(["rock"]);
        expect(result.get("a2")).toEqual([]);
        expect(mockGetArtists).toHaveBeenCalledWith("token", ["a1", "a2"]);

        const doc = await ArtistModel.findOne({ spotifyId: "a1" });
        expect(doc).not.toBeNull();
        expect(doc!.name).toBe("Artist a1");
        expect(doc!.genres).toEqual(["rock"]);
        expect(doc!.lastFetchedAt.getTime()).toBeGreaterThan(Date.now() - 60_000);
    });

    it("fetches only the missing artists on a partial cache hit", async () => {
        await ArtistModel.create({
            spotifyId: "a1",
            name: "Artist a1",
            genres: ["hip hop"],
            lastFetchedAt: now(),
        });
        mockGetArtists.mockResolvedValue([makeArtist("a2", ["jazz"])]);

        const result = await getArtistGenresCached("token", ["a1", "a2"]);

        expect(mockGetArtists).toHaveBeenCalledTimes(1);
        expect(mockGetArtists).toHaveBeenCalledWith("token", ["a2"]);
        expect(result.get("a1")).toEqual(["hip hop"]);
        expect(result.get("a2")).toEqual(["jazz"]);
    });

    it("refetches stale artists and refreshes the cached document", async () => {
        await ArtistModel.create({
            spotifyId: "a1",
            name: "Artist a1",
            genres: ["old genre"],
            lastFetchedAt: staleDate(),
        });
        mockGetArtists.mockResolvedValue([makeArtist("a1", ["new genre"])]);

        const result = await getArtistGenresCached("token", ["a1"]);

        expect(mockGetArtists).toHaveBeenCalledWith("token", ["a1"]);
        expect(result.get("a1")).toEqual(["new genre"]);
        const doc = await ArtistModel.findOne({ spotifyId: "a1" });
        expect(doc!.genres).toEqual(["new genre"]);
        expect(doc!.lastFetchedAt.getTime()).toBeGreaterThan(Date.now() - 60_000);
    });

    it("dedupes artist ids before querying cache or Spotify", async () => {
        mockGetArtists.mockResolvedValue([makeArtist("a1", ["rock"]), makeArtist("a2", ["pop"])]);

        await getArtistGenresCached("token", ["a1", "a1", "a2", "a2", "a1"]);

        expect(mockGetArtists).toHaveBeenCalledTimes(1);
        expect(mockGetArtists).toHaveBeenCalledWith("token", ["a1", "a2"]);
    });

    it("caches artists with zero genres as an empty array", async () => {
        mockGetArtists.mockResolvedValue([makeArtist("a1", [])]);

        const first = await getArtistGenresCached("token", ["a1"]);
        expect(first.get("a1")).toEqual([]);

        // Second call must come from cache, not Spotify.
        mockGetArtists.mockClear();
        const second = await getArtistGenresCached("token", ["a1"]);
        expect(second.get("a1")).toEqual([]);
        expect(mockGetArtists).not.toHaveBeenCalled();
    });

    it("preserves the 50-item Spotify batching limit across 75 missing artists", async () => {
        const ids = Array.from({ length: 75 }, (_, i) => `artist${i}`);
        mockGetArtists.mockImplementation(async (_token: string, batch: string[]) =>
            batch.map(id => makeArtist(id, ["rock"]))
        );

        const result = await getArtistGenresCached("token", ids);

        expect(mockGetArtists).toHaveBeenCalledTimes(2);
        const firstBatch = mockGetArtists.mock.calls[0][1] as string[];
        const secondBatch = mockGetArtists.mock.calls[1][1] as string[];
        expect(firstBatch).toHaveLength(50);
        expect(secondBatch).toHaveLength(25);
        expect(result.size).toBe(75);
    });
});

describe("getFreshCachedArtists", () => {
    it("only returns non-stale documents", async () => {
        await ArtistModel.create([
            { spotifyId: "fresh", name: "Fresh", genres: ["pop"], lastFetchedAt: now() },
            { spotifyId: "stale", name: "Stale", genres: ["rock"], lastFetchedAt: staleDate() },
        ]);

        const fresh = await getFreshCachedArtists(["fresh", "stale"]);

        expect(fresh.has("fresh")).toBe(true);
        expect(fresh.has("stale")).toBe(false);
    });
});
