// spotify.artist.service.test.ts
//
// getArtistGenres is a thin axios wrapper that batches requests in groups of 50.
// We verify:
//   - Correct endpoint is called with batched IDs
//   - Returns a Map of artistId -> genres
//   - Makes multiple requests when artistIds.length > 50
//   - Skips null artists (Spotify can return null for unavailable artists)

import { getArtistGenres } from "../../services/spotify.artist.service";

jest.mock("axios", () => ({
    get: jest.fn(),
}));

import axios from "axios";
const mockAxiosGet = axios.get as jest.Mock;

const makeArtist = (id: string, genres: string[]) => ({
    id,
    name: `Artist ${id}`,
    href: `https://api.spotify.com/v1/artists/${id}`,
    uri: `spotify:artist:${id}`,
    external_urls: { spotify: `https://open.spotify.com/artist/${id}` },
    type: 'artist',
    genres,
    images: [],
    followers: { href: null, total: 0 },
    popularity: 50,
});

beforeEach(() => {
    jest.clearAllMocks();
});

describe("getArtistGenres", () => {
    it("returns an empty map when given no artist IDs", async () => {
        const result = await getArtistGenres("token", []);
        expect(result.size).toBe(0);
        expect(mockAxiosGet).not.toHaveBeenCalled();
    });

    it("returns a map of artistId -> genres", async () => {
        mockAxiosGet.mockResolvedValue({
            data: {
                artists: [
                    makeArtist("artist1", ["hip hop", "rap"]),
                    makeArtist("artist2", ["pop"]),
                ],
            },
        });

        const result = await getArtistGenres("token", ["artist1", "artist2"]);

        expect(result.get("artist1")).toEqual(["hip hop", "rap"]);
        expect(result.get("artist2")).toEqual(["pop"]);
    });

    it("calls the correct Spotify endpoint with IDs joined by comma", async () => {
        mockAxiosGet.mockResolvedValue({ data: { artists: [makeArtist("a1", [])] } });

        await getArtistGenres("mytoken", ["a1"]);

        expect(mockAxiosGet).toHaveBeenCalledWith(
            "https://api.spotify.com/v1/artists?ids=a1",
            { headers: { Authorization: "Bearer mytoken" } }
        );
    });

    it("batches requests when more than 50 IDs are provided", async () => {
        const ids = Array.from({ length: 75 }, (_, i) => `artist${i}`);
        mockAxiosGet.mockResolvedValue({ data: { artists: [] } });

        await getArtistGenres("token", ids);

        expect(mockAxiosGet).toHaveBeenCalledTimes(2);
        // first batch: 50 IDs
        const firstCallUrl: string = mockAxiosGet.mock.calls[0][0];
        expect(firstCallUrl.split('ids=')[1].split(',').length).toBe(50);
        // second batch: remaining 25
        const secondCallUrl: string = mockAxiosGet.mock.calls[1][0];
        expect(secondCallUrl.split('ids=')[1].split(',').length).toBe(25);
    });

    it("skips null artists in the response", async () => {
        mockAxiosGet.mockResolvedValue({
            data: { artists: [makeArtist("a1", ["pop"]), null] },
        });

        const result = await getArtistGenres("token", ["a1", "a2"]);

        expect(result.size).toBe(1);
        expect(result.get("a1")).toEqual(["pop"]);
    });

    it("throws when the Spotify API returns an error", async () => {
        mockAxiosGet.mockRejectedValue(new Error("429 Too Many Requests"));

        await expect(getArtistGenres("token", ["a1"])).rejects.toThrow("429 Too Many Requests");
    });
});
