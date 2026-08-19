import {
    isSortableTrack,
    isCopyableTrack,
    likedTracksToSortable,
    playlistTracksToSortable,
    playlistTracksToCopyableUris,
    dedupeArtistIds,
} from "../../utils/trackFilters";
import type { SpotifyPlaylistItem, SpotifyTrack } from "../../types/spotify.types";

const makeTrack = (overrides: Partial<SpotifyTrack> = {}): SpotifyTrack => ({
    id: "t1",
    name: "Track",
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
    artists: [{ id: "a1", name: "A1", href: "", uri: "", external_urls: { spotify: "" }, type: "artist" }],
    external_urls: { spotify: "" },
    href: "",
    uri: "spotify:track:t1",
    type: "track",
    ...overrides,
});

const makePlaylistItem = (track: SpotifyTrack | null): SpotifyPlaylistItem => ({
    added_at: null,
    added_by: null,
    is_local: false,
    item: track,
});

describe("isSortableTrack", () => {
    it("accepts a normal track", () => {
        expect(isSortableTrack(makeTrack())).toBe(true);
    });

    it("rejects null/undefined tracks", () => {
        expect(isSortableTrack(null)).toBe(false);
        expect(isSortableTrack(undefined)).toBe(false);
    });

    it("rejects local tracks", () => {
        expect(isSortableTrack(makeTrack({ is_local: true }))).toBe(false);
    });

    it("rejects unavailable/unplayable tracks", () => {
        expect(isSortableTrack(makeTrack({ is_playable: false }))).toBe(false);
    });

    it("rejects tracks without a uri or artists", () => {
        expect(isSortableTrack(makeTrack({ uri: "" }))).toBe(false);
        expect(isSortableTrack(makeTrack({ artists: [] }))).toBe(false);
    });
});

describe("likedTracksToSortable / playlistTracksToSortable", () => {
    it("extracts sortable tracks from liked-song items", () => {
        const items = [
            { added_at: "2024-01-01", track: makeTrack() },
            { added_at: "2024-01-01", track: makeTrack({ is_local: true }) },
        ];
        expect(likedTracksToSortable(items)).toHaveLength(1);
    });

    it("filters null playlist items", () => {
        const items = [
            { added_at: null, added_by: null, is_local: false, item: makeTrack() },
            { added_at: null, added_by: null, is_local: false, item: null },
        ];
        expect(playlistTracksToSortable(items)).toHaveLength(1);
    });
});

describe("isCopyableTrack / playlistTracksToCopyableUris", () => {
    it("accepts a track with no artists", () => {
        expect(isCopyableTrack(makeTrack({ artists: [] }))).toBe(true);
    });

    it("rejects null tracks, local tracks, and unavailable tracks", () => {
        expect(isCopyableTrack(null)).toBe(false);
        expect(isCopyableTrack(undefined)).toBe(false);
        expect(isCopyableTrack(makeTrack({ is_local: true }))).toBe(false);
        expect(isCopyableTrack(makeTrack({ is_playable: false }))).toBe(false);
    });

    it("rejects tracks without a non-empty id or uri", () => {
        expect(isCopyableTrack(makeTrack({ id: "" }))).toBe(false);
        expect(isCopyableTrack(makeTrack({ uri: "" }))).toBe(false);
    });

    it("derives copyable URIs, keeping order and duplicates, without requiring artists", () => {
        const noArtists = makeTrack({
            id: "t-no-artists",
            uri: "spotify:track:t-no-artists",
            artists: [],
        });
        const items = [
            makePlaylistItem(makeTrack({ id: "t1" })),
            makePlaylistItem(makeTrack({ id: "t2", uri: "spotify:track:t2" })),
            makePlaylistItem(noArtists),
            makePlaylistItem(makeTrack({ id: "t1" })), // duplicate URI
            makePlaylistItem(null),
            makePlaylistItem(makeTrack({ id: "t-local", is_local: true })),
            makePlaylistItem(makeTrack({ id: "t-unplayable", is_playable: false })),
            makePlaylistItem(makeTrack({ id: "t-no-uri", uri: "" })),
        ];

        expect(playlistTracksToCopyableUris(items)).toEqual([
            "spotify:track:t1",
            "spotify:track:t2",
            "spotify:track:t-no-artists",
            "spotify:track:t1",
        ]);
    });
});

describe("dedupeArtistIds", () => {
    it("collects unique artist ids across multi-artist tracks", () => {
        const t1 = makeTrack({ artists: [
            { id: "a1", name: "A1", href: "", uri: "", external_urls: { spotify: "" }, type: "artist" },
            { id: "a2", name: "A2", href: "", uri: "", external_urls: { spotify: "" }, type: "artist" },
        ] });
        const t2 = makeTrack({ id: "t2", artists: [
            { id: "a2", name: "A2", href: "", uri: "", external_urls: { spotify: "" }, type: "artist" },
            { id: "a3", name: "A3", href: "", uri: "", external_urls: { spotify: "" }, type: "artist" },
        ] });

        expect(dedupeArtistIds([t1, t2])).toEqual(["a1", "a2", "a3"]);
    });
});
