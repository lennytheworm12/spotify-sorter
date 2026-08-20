// scale.synthetic.profile.test.ts
//
// Deterministic synthetic scale profile for the service pipeline:
//   getPlaylistTracks -> playlistTracksToSortable + dedupeArtistIds ->
//   getArtistGenresCached -> buildBucketMap -> addTracksToPlaylist
//
// The Spotify HTTP boundary (axios) and the ArtistModel persistence boundary
// are mocked; nothing touches a real network, MongoMemoryServer, or Spotify
// credentials. Profiles run 1,000 / 5,000 / 10,000 unique sortable tracks
// (one unique artist each, all with a recognized "rock" genre). 10,000 is a
// verified synthetic scale profile, NOT a claim that Spotify currently caps
// playlists at 10,000 tracks and NOT a live Spotify/load benchmark.

import axios from "axios";
import {
    addTracksToPlaylist,
    getPlaylistTracks,
    BATCH_DELAY_MS,
} from "../../services/spotify.playlist.service";
import { getArtistGenresCached } from "../../services/artist.cache.service";
import { buildBucketMap } from "../../services/genre.service";
import { dedupeArtistIds, playlistTracksToSortable } from "../../utils/trackFilters";
import { ArtistModel } from "../../models/Artist";
import type {
    SpotifyArtist,
    SpotifyPlaylistItem,
    SpotifyTrack,
} from "../../types/spotify.types";

jest.mock("axios", () => ({
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
}));

// ArtistModel persistence is a mocked boundary: find() returns an empty fresh
// cache (so every artist must be fetched + upserted) and bulkWrite() records
// every upsert. No mongoose connection is opened.
jest.mock("../../models/Artist", () => ({
    ArtistModel: {
        find: jest.fn(),
        bulkWrite: jest.fn(),
    },
}));

const mockAxiosGet = axios.get as jest.Mock;
const mockAxiosPost = axios.post as jest.Mock;
const mockArtistFind = ArtistModel.find as unknown as jest.Mock;
const mockArtistBulkWrite = ArtistModel.bulkWrite as unknown as jest.Mock;

const ACCESS_TOKEN = "access-token";
const SOURCE_PLAYLIST_ID = "source-pl";
const DEST_PLAYLIST_ID = "dest-pl";
const READ_PAGE_SIZE = 50; // Spotify GET page limit
const WRITE_BATCH_SIZE = 100; // Spotify POST /items request limit
const ARTIST_BATCH_SIZE = 50; // Spotify GET /artists?ids= limit

const makeTrack = (index: number): SpotifyTrack => {
    const id = `track-${index}`;
    const artistId = `artist-${index}`;
    return {
        id,
        name: `Track ${index}`,
        duration_ms: 180_000,
        explicit: false,
        track_number: 1,
        disc_number: 1,
        is_local: false,
        album: {
            id: `album-${index}`,
            name: `Album ${index}`,
            album_type: "album",
            total_tracks: 1,
            release_date: "2020-01-01",
            release_date_precision: "day",
            images: [],
            artists: [],
            external_urls: { spotify: `https://open.spotify.com/album/album-${index}` },
            href: `https://api.spotify.com/v1/albums/album-${index}`,
            uri: `spotify:album:album-${index}`,
            type: "album",
        },
        artists: [
            {
                id: artistId,
                name: `Artist ${index}`,
                href: `https://api.spotify.com/v1/artists/${artistId}`,
                uri: `spotify:artist:${artistId}`,
                external_urls: { spotify: `https://open.spotify.com/artist/${artistId}` },
                type: "artist",
            },
        ],
        external_urls: { spotify: `https://open.spotify.com/track/${id}` },
        href: `https://api.spotify.com/v1/tracks/${id}`,
        uri: `spotify:track:${id}`,
        type: "track",
    };
};

const makePlaylistItems = (count: number): SpotifyPlaylistItem[] =>
    Array.from({ length: count }, (_, index) => ({
        added_at: "2020-01-01T00:00:00Z",
        added_by: null,
        is_local: false,
        item: makeTrack(index),
    }));

// Artist responses are derived from the actual IDs in each requested URL.
const makeArtist = (id: string): SpotifyArtist => ({
    id,
    name: `Artist ${id}`,
    href: `https://api.spotify.com/v1/artists/${id}`,
    uri: `spotify:artist:${id}`,
    external_urls: { spotify: `https://open.spotify.com/artist/${id}` },
    type: "artist",
    genres: ["rock"],
    images: [],
    followers: { href: null, total: 0 },
    popularity: 50,
});

beforeEach(() => {
    jest.clearAllMocks();
});

describe("synthetic scale profile", () => {
    it.each([1000, 5000, 10000])(
        "runs the production read -> filter -> cache -> bucket -> write pipeline for %i unique tracks",
        async (count: number) => {
            // Heap guardrail: measured from before fixture creation through
            // pipeline completion for the 10,000-track case only. Generous and
            // documented as a regression guardrail, not a universal benchmark.
            const heapBefore = count === 10000 ? process.memoryUsage().heapUsed : 0;

            const sourceItems = makePlaylistItems(count);
            const sourceUris = sourceItems.map(item => item.item!.uri);
            const expectedReadPages = Math.ceil(count / READ_PAGE_SIZE);
            const expectedArtistRequests = Math.ceil(count / ARTIST_BATCH_SIZE);
            const expectedWriteBatches = Math.ceil(count / WRITE_BATCH_SIZE);

            // Paginated playlist reads: 50 items per page, followed via `next`.
            const servedReadItems: SpotifyTrack[] = [];
            mockAxiosGet.mockImplementation((url: string) => {
                if (url.includes(`/playlists/${SOURCE_PLAYLIST_ID}/items`)) {
                    const offset = Number(new URL(url).searchParams.get("offset") ?? "0");
                    const chunk = sourceItems.slice(offset, offset + READ_PAGE_SIZE);
                    servedReadItems.push(...chunk.map(item => item.item!));
                    const nextOffset = offset + READ_PAGE_SIZE;
                    const next =
                        nextOffset < sourceItems.length
                            ? `https://api.spotify.com/v1/playlists/${SOURCE_PLAYLIST_ID}/items?offset=${nextOffset}&limit=${READ_PAGE_SIZE}`
                            : null;
                    return {
                        data: {
                            href: url,
                            limit: READ_PAGE_SIZE,
                            next,
                            offset,
                            previous: null,
                            total: sourceItems.length,
                            items: chunk,
                        },
                    };
                }

                // Artist lookups: derive the response strictly from the IDs in
                // the requested URL, one artist object per requested ID.
                const ids = new URL(url).searchParams.get("ids")!.split(",");
                return {
                    data: { artists: ids.map(makeArtist) },
                };
            });

            const mockSleep = jest.fn().mockResolvedValue(undefined);

            // Write boundary: batches of 100 succeed except for one
            // deterministic 429 on the first 10,000-profile write attempt,
            // which is retried with Retry-After and then succeeds.
            const acceptedBatches: string[][] = [];
            const rejectedBodies: string[][] = [];
            let writeAttempt = 0;
            mockAxiosPost.mockImplementation(
                async (_url: string, body: { uris: string[] }) => {
                    writeAttempt += 1;
                    if (count === 10000 && writeAttempt === 1) {
                        rejectedBodies.push(body.uris);
                        throw Object.assign(new Error("429 Too Many Requests"), {
                            response: { status: 429, headers: { "retry-after": "1" } },
                        });
                    }
                    acceptedBatches.push(body.uris);
                    return { data: { snapshot_id: `snap-${writeAttempt}` } };
                }
            );

            mockArtistFind.mockResolvedValue([]); // empty cache -> fetch all
            mockArtistBulkWrite.mockResolvedValue(undefined);

            // ─── 1. Read + filter ────────────────────────────────────────────
            const playlistItems = await getPlaylistTracks(ACCESS_TOKEN, SOURCE_PLAYLIST_ID);
            const tracks = playlistTracksToSortable(playlistItems);
            const artistIds = dedupeArtistIds(tracks);

            const trackGetCalls = mockAxiosGet.mock.calls.filter(([url]) =>
                String(url).includes(`/playlists/${SOURCE_PLAYLIST_ID}/items`)
            );
            expect(trackGetCalls).toHaveLength(expectedReadPages);
            expect(playlistItems).toHaveLength(count);
            expect(tracks).toHaveLength(count); // every item sortable
            expect(servedReadItems.map(track => track.uri)).toEqual(sourceUris);
            expect(artistIds).toHaveLength(count); // one unique artist per track

            // ─── 2. Artist genres through the cache ──────────────────────────
            const artistGenres = await getArtistGenresCached(ACCESS_TOKEN, artistIds);

            const artistGetCalls = mockAxiosGet.mock.calls.filter(([url]) =>
                String(url).includes("/v1/artists?ids=")
            );
            expect(artistGetCalls).toHaveLength(expectedArtistRequests);
            const requestedArtistIds: string[] = [];
            for (const [url] of artistGetCalls) {
                const ids = new URL(String(url)).searchParams.get("ids")!.split(",");
                expect(ids.length).toBeLessThanOrEqual(ARTIST_BATCH_SIZE);
                requestedArtistIds.push(...ids);
            }
            // Every unique artist requested exactly once, in dedupe order.
            expect(requestedArtistIds).toEqual(artistIds);
            expect(new Set(requestedArtistIds).size).toBe(count);
            expect(artistGenres.size).toBe(count);
            expect(artistGenres.get("artist-0")).toEqual(["rock"]);

            // Cache read hit the empty persistence boundary with every id...
            expect(mockArtistFind).toHaveBeenCalledTimes(1);
            expect(mockArtistFind.mock.calls[0][0]).toMatchObject({
                spotifyId: { $in: artistIds },
            });
            // ...and the bulk upsert received every artist exactly once.
            expect(mockArtistBulkWrite).toHaveBeenCalledTimes(1);
            const upsertOps = mockArtistBulkWrite.mock.calls[0][0] as Array<{
                updateOne: { filter: { spotifyId: string } };
            }>;
            const upsertedIds = upsertOps.map(op => op.updateOne.filter.spotifyId);
            expect(upsertedIds).toEqual(artistIds);
            expect(new Set(upsertedIds).size).toBe(count);

            // ─── 3. Bucket every track exactly once ──────────────────────────
            const bucketMap = buildBucketMap(tracks, artistGenres);
            const bucketedTracks = [...bucketMap.values()].flat();
            expect(bucketedTracks).toHaveLength(count);
            expect(bucketedTracks.map(track => track.uri)).toEqual(sourceUris);
            expect(bucketMap.get("Rock")).toHaveLength(count);

            // ─── 4. Batched, paced, retrying playlist writes ─────────────────
            const snapshot = await addTracksToPlaylist(
                ACCESS_TOKEN,
                DEST_PLAYLIST_ID,
                sourceUris,
                { sleep: mockSleep }
            );

            expect(snapshot).toMatch(/^snap-/);
            expect(mockAxiosPost).toHaveBeenCalledTimes(
                expectedWriteBatches + (count === 10000 ? 1 : 0)
            );
            expect(acceptedBatches).toHaveLength(expectedWriteBatches);
            for (const batch of acceptedBatches) {
                expect(batch.length).toBeLessThanOrEqual(WRITE_BATCH_SIZE);
                expect(batch.length).toBe(WRITE_BATCH_SIZE);
            }
            // Flattened successful writes equal the source exactly, in order:
            // no drops, no duplicates, no reordering.
            const flattenedWrites = acceptedBatches.flat();
            expect(flattenedWrites).toEqual(sourceUris);
            expect(new Set(flattenedWrites).size).toBe(count);
            expect(mockAxiosPost.mock.calls[0][0]).toBe(
                `https://api.spotify.com/v1/playlists/${DEST_PLAYLIST_ID}/items`
            );

            const sleepValues = mockSleep.mock.calls.map(call => call[0] as number);
            if (count === 10000) {
                // Exactly one retry: the rejected first batch is re-sent
                // unchanged, honoring Retry-After (1s -> 1000ms), and no
                // duplicate server-side accepted items appear.
                expect(rejectedBodies).toHaveLength(1);
                expect(rejectedBodies[0]).toEqual(acceptedBatches[0]);
                expect(mockAxiosPost).toHaveBeenCalledTimes(expectedWriteBatches + 1);
                expect(sleepValues).toEqual([
                    1000,
                    ...Array.from({ length: expectedWriteBatches - 1 }, () => BATCH_DELAY_MS),
                ]);
                expect(mockSleep).toHaveBeenCalledTimes(expectedWriteBatches);
            } else {
                // Pacing only between batches; never after the final batch.
                expect(sleepValues).toEqual(
                    Array.from({ length: expectedWriteBatches - 1 }, () => BATCH_DELAY_MS)
                );
            }

            if (count === 10000) {
                (globalThis as { gc?: () => void }).gc?.();
                const growthBytes = process.memoryUsage().heapUsed - heapBefore;
                expect(growthBytes).toBeLessThan(192 * 1024 * 1024);
            }
        },
        60_000
    );
});
