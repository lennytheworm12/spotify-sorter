// spotify.user.service.test.ts
//
// Both getSpotifyUserData AND refreshAccessToken live in spotify.user.service.ts
// so both are tested here. We mock axios get and post since both are used.

import { getSpotifyUserData, refreshAccessToken } from "../../services/spotify.user.service";

jest.mock("axios", () => ({
    get: jest.fn(),
    post: jest.fn(),
}));

jest.mock("../../env", () => ({
    env: {
        SPOTIFY_CLIENT_ID: "test-client-id",
        SPOTIFY_CLIENT_SECRET: "test-client-secret",
        SPOTIFY_REDIRECT_URI: "http://localhost:3000/auth/spotify/callback",
    },
}));

import axios from "axios";
const mockAxiosGet = axios.get as jest.Mock;
const mockAxiosPost = axios.post as jest.Mock;

const expectedBasicAuth =
    "Basic " + Buffer.from("test-client-id:test-client-secret").toString("base64");

const mockSpotifyUser = {
    id: "spotify-user-123",
    display_name: "Test User",
    images: [{ url: "https://example.com/pic.jpg", height: 100, width: 100 }],
    uri: "spotify:user:123",
    href: "https://api.spotify.com/v1/users/123",
    external_urls: { spotify: "https://open.spotify.com/user/123" },
    type: "user",
};

const mockSpotifyToken = {
    access_token: "access-abc",
    token_type: "Bearer",
    scope: "playlist-read-private",
    expires_in: 3600,
    refresh_token: "refresh-xyz",
};

beforeEach(() => {
    jest.clearAllMocks();
});

// =============================================================================
// getSpotifyUserData
// =============================================================================
describe("getSpotifyUserData", () => {

    it("returns a SpotifyUser on success", async () => {
        mockAxiosGet.mockResolvedValue({ data: mockSpotifyUser });
        const result = await getSpotifyUserData("access-abc");
        expect(result).toEqual(mockSpotifyUser);
    });

    it("calls the correct Spotify /me endpoint", async () => {
        mockAxiosGet.mockResolvedValue({ data: mockSpotifyUser });
        await getSpotifyUserData("access-abc");
        expect(mockAxiosGet).toHaveBeenCalledWith(
            "https://api.spotify.com/v1/me",
            expect.any(Object)
        );
    });

    it("sends the correct Authorization: Bearer header", async () => {
        mockAxiosGet.mockResolvedValue({ data: mockSpotifyUser });
        await getSpotifyUserData("access-abc");
        const headers = mockAxiosGet.mock.calls[0][1].headers;
        expect(headers.Authorization).toBe("Bearer access-abc");
    });

    it("throws when Spotify returns an error", async () => {
        mockAxiosGet.mockRejectedValue(new Error("401 Unauthorized"));
        await expect(getSpotifyUserData("bad-token")).rejects.toThrow("401 Unauthorized");
    });
});

// =============================================================================
// refreshAccessToken
// =============================================================================
describe("refreshAccessToken", () => {

    it("returns a SpotifyToken on success", async () => {
        mockAxiosPost.mockResolvedValue({ data: mockSpotifyToken });
        const result = await refreshAccessToken("refresh-xyz");
        expect(result).toEqual(mockSpotifyToken);
    });

    it("calls the correct Spotify token endpoint", async () => {
        mockAxiosPost.mockResolvedValue({ data: mockSpotifyToken });
        await refreshAccessToken("refresh-xyz");
        expect(mockAxiosPost).toHaveBeenCalledWith(
            "https://accounts.spotify.com/api/token",
            expect.any(String),
            expect.any(Object)
        );
    });

    it("sends the correct Authorization: Basic header", async () => {
        mockAxiosPost.mockResolvedValue({ data: mockSpotifyToken });
        await refreshAccessToken("refresh-xyz");
        const headers = mockAxiosPost.mock.calls[0][2].headers;
        expect(headers.Authorization).toBe(expectedBasicAuth);
    });

    it("sends grant_type=refresh_token and the refresh token in the body", async () => {
        mockAxiosPost.mockResolvedValue({ data: mockSpotifyToken });
        await refreshAccessToken("refresh-xyz");
        const body = mockAxiosPost.mock.calls[0][1] as string;
        expect(body).toContain("grant_type=refresh_token");
        expect(body).toContain("refresh_token=refresh-xyz");
    });

    it("throws when Spotify returns an error", async () => {
        mockAxiosPost.mockRejectedValue(new Error("400 Bad Request"));
        await expect(refreshAccessToken("expired-token")).rejects.toThrow("400 Bad Request");
    });
});
