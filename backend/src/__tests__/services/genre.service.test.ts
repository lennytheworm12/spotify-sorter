import {
    assignTrackToBucket,
    buildBucketMap,
    buildPlaylistGenreProfile,
    matchBucketToPlaylist,
    validateEditablePlaylists,
} from "../../services/genre.service";
import type { SpotifyTrack, SpotifySimplifiedPlaylist } from "../../types/spotify.types";
import type { GenreBucket } from "../../utils/genreMap";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const makeTrack = (id: string, artistIds: string[]): SpotifyTrack => ({
    id,
    name: `Track ${id}`,
    duration_ms: 200000,
    explicit: false,
    track_number: 1,
    disc_number: 1,
    is_local: false,
    album: {
        id: 'album1', name: 'Album', album_type: 'album', total_tracks: 10,
        release_date: '2020-01-01', release_date_precision: 'day',
        images: [], artists: [], external_urls: { spotify: '' },
        href: '', uri: `spotify:album:album1`, type: 'album',
    },
    artists: artistIds.map(aid => ({
        id: aid, name: `Artist ${aid}`, href: '', uri: `spotify:artist:${aid}`,
        external_urls: { spotify: '' }, type: 'artist',
    })),
    external_urls: { spotify: '' },
    href: '',
    uri: `spotify:track:${id}`,
    type: 'track',
});

const makePlaylist = (id: string, name: string, ownerId: string, collaborative = false): SpotifySimplifiedPlaylist => ({
    id,
    name,
    description: null,
    collaborative,
    public: false,
    snapshot_id: 'snap',
    images: [],
    external_urls: { spotify: '' },
    href: '',
    uri: `spotify:playlist:${id}`,
    type: 'playlist',
    owner: { id: ownerId, href: '', uri: '', external_urls: { spotify: '' }, type: 'user' },
    items: { href: '', total: 0 },
});

// ─── assignTrackToBucket ──────────────────────────────────────────────────────

describe("assignTrackToBucket", () => {
    it("returns the first non-Other bucket from artist genres", () => {
        const track = makeTrack("t1", ["artist1"]);
        const genreMap = new Map([["artist1", ["hip hop", "rap"]]]);

        expect(assignTrackToBucket(track, genreMap)).toBe("Hip Hop");
    });

    it("checks genres across multiple artists", () => {
        const track = makeTrack("t1", ["artist1", "artist2"]);
        const genreMap = new Map([
            ["artist1", []],
            ["artist2", ["deep house"]],
        ]);

        expect(assignTrackToBucket(track, genreMap)).toBe("Electronic");
    });

    it("returns Other when no genres match", () => {
        const track = makeTrack("t1", ["artist1"]);
        const genreMap = new Map([["artist1", ["unknown genre xyz"]]]);

        expect(assignTrackToBucket(track, genreMap)).toBe("Other");
    });

    it("returns Other when artist not in genreMap", () => {
        const track = makeTrack("t1", ["artist1"]);
        const genreMap = new Map<string, string[]>();

        expect(assignTrackToBucket(track, genreMap)).toBe("Other");
    });
});

// ─── buildBucketMap ───────────────────────────────────────────────────────────

describe("buildBucketMap", () => {
    it("groups tracks by bucket", () => {
        const tracks = [makeTrack("t1", ["a1"]), makeTrack("t2", ["a2"]), makeTrack("t3", ["a1"])];
        const genreMap = new Map([
            ["a1", ["hip hop"]],
            ["a2", ["pop"]],
        ]);

        const result = buildBucketMap(tracks, genreMap);

        expect(result.get("Hip Hop")?.map(t => t.id)).toEqual(["t1", "t3"]);
        expect(result.get("Pop")?.map(t => t.id)).toEqual(["t2"]);
    });

    it("returns an empty map for empty track list", () => {
        const result = buildBucketMap([], new Map());
        expect(result.size).toBe(0);
    });

    it("puts unrecognized tracks in the Other bucket", () => {
        const tracks = [makeTrack("t1", ["a1"])];
        const genreMap = new Map([["a1", ["unknown genre"]]]);

        const result = buildBucketMap(tracks, genreMap);
        expect(result.get("Other")).toHaveLength(1);
    });
});

// ─── buildPlaylistGenreProfile ────────────────────────────────────────────────

describe("buildPlaylistGenreProfile", () => {
    it("returns empty map for empty track list", () => {
        const result = buildPlaylistGenreProfile([], new Map());
        expect(result.size).toBe(0);
    });

    it("returns correct percentages", () => {
        const tracks = [
            makeTrack("t1", ["a1"]),
            makeTrack("t2", ["a1"]),
            makeTrack("t3", ["a2"]),
        ];
        const genreMap = new Map([
            ["a1", ["hip hop"]],
            ["a2", ["pop"]],
        ]);

        const profile = buildPlaylistGenreProfile(tracks, genreMap);

        expect(profile.get("Hip Hop")).toBeCloseTo(2 / 3);
        expect(profile.get("Pop")).toBeCloseTo(1 / 3);
    });
});

// ─── matchBucketToPlaylist ────────────────────────────────────────────────────

describe("matchBucketToPlaylist", () => {
    it("returns the playlist with the highest profile score for the bucket", () => {
        const profiles = new Map<string, Map<GenreBucket, number>>([
            ["pl1", new Map([["Hip Hop", 0.2], ["Pop", 0.8]])],
            ["pl2", new Map([["Hip Hop", 0.9], ["Pop", 0.1]])],
        ]);
        const names = new Map([["pl1", "Pop Vibes"], ["pl2", "Hip Hop Hits"]]);

        expect(matchBucketToPlaylist("Hip Hop", profiles, names)).toBe("pl2");
    });

    it("returns null when playlistProfiles is empty", () => {
        expect(matchBucketToPlaylist("Hip Hop", new Map(), new Map())).toBeNull();
    });

    it("uses name keyword matching for empty playlists (no profile)", () => {
        const profiles = new Map<string, Map<GenreBucket, number>>([
            ["pl1", new Map()],  // empty playlist
        ]);
        const names = new Map([["pl1", "My Hip Hop Mix"]]);

        expect(matchBucketToPlaylist("Hip Hop", profiles, names)).toBe("pl1");
    });

    it("scores empty playlist with non-matching name lower than scored playlist", () => {
        const profiles = new Map<string, Map<GenreBucket, number>>([
            ["pl1", new Map()],                              // empty, name mismatch
            ["pl2", new Map([["Hip Hop", 0.5]])],            // has score
        ]);
        const names = new Map([["pl1", "Classical Piano"], ["pl2", "Random Mix"]]);

        expect(matchBucketToPlaylist("Hip Hop", profiles, names)).toBe("pl2");
    });
});

// ─── validateEditablePlaylists ────────────────────────────────────────────────

describe("validateEditablePlaylists", () => {
    it("includes playlists owned by the user with a name", () => {
        const playlist = makePlaylist("pl1", "My Playlist", "user1");
        const result = validateEditablePlaylists([playlist], "user1");
        expect(result.valid).toHaveLength(1);
        expect(result.excluded).toHaveLength(0);
    });

    it("includes collaborative playlists regardless of owner", () => {
        const playlist = makePlaylist("pl1", "Collab", "other-user", true);
        const result = validateEditablePlaylists([playlist], "user1");
        expect(result.valid).toHaveLength(1);
    });

    it("excludes playlists not owned by user and not collaborative", () => {
        const playlist = makePlaylist("pl1", "Not Mine", "other-user", false);
        const result = validateEditablePlaylists([playlist], "user1");
        expect(result.excluded[0].reason).toBe("not editable");
    });

    it("excludes playlists with no name", () => {
        const playlist = makePlaylist("pl1", "", "user1");
        const result = validateEditablePlaylists([playlist], "user1");
        expect(result.excluded[0].reason).toBe("no name");
    });

    it("excludes playlists with whitespace-only name", () => {
        const playlist = makePlaylist("pl1", "   ", "user1");
        const result = validateEditablePlaylists([playlist], "user1");
        expect(result.excluded[0].reason).toBe("no name");
    });
});
