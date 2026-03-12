// spotify.auth.service.test.ts
//
// exchangeToken and refreshAccessToken are thin axios wrappers.
// We mock axios directly here since there's no service abstraction layer —
// the HTTP call IS the logic we're testing.
//
// What we're verifying:
//   - Correct URL is called
//   - Correct headers are set (Authorization: Basic <base64>)
//   - Correct body params are passed
//   - Returns the SpotifyToken on success
//   - Throws on error

import { exchangeToken } from "../../services/spotify.auth.service";
jest.mock("axios", () => ({
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
const mockAxiosPost = axios.post as jest.Mock;

const mockSpotifyToken = {
    access_token: "access-abc",
    token_type: "Bearer",
    scope: "playlist-read-private",
    expires_in: 3600,
    refresh_token: "refresh-xyz",
};

// The expected Basic auth header:
// base64("test-client-id:test-client-secret")
const expectedBasicAuth = "Basic " + Buffer.from("test-client-id:test-client-secret").toString("base64");

beforeEach(() => {
    jest.clearAllMocks();
});

// =============================================================================
// exchangeToken
// =============================================================================
describe("exchangeToken", () => {

    it("returns a SpotifyToken on success", async () => {
        mockAxiosPost.mockResolvedValue({ data: mockSpotifyToken });

        const result = await exchangeToken("auth-code-123");

        expect(result).toEqual(mockSpotifyToken);
    });

    it("calls the correct Spotify token endpoint", async () => {
        mockAxiosPost.mockResolvedValue({ data: mockSpotifyToken });

        await exchangeToken("auth-code-123");

        expect(mockAxiosPost).toHaveBeenCalledWith(
            "https://accounts.spotify.com/api/token",
            expect.any(String),
            expect.any(Object)
        );
    });

    it("sends the correct Authorization: Basic header", async () => {
        mockAxiosPost.mockResolvedValue({ data: mockSpotifyToken });

        await exchangeToken("auth-code-123");

        const callArgs = mockAxiosPost.mock.calls[0];
        const headers = callArgs[2].headers;
        expect(headers.Authorization).toBe(expectedBasicAuth);
    });

    it("sends grant_type, code, and redirect_uri in the request body", async () => {
        mockAxiosPost.mockResolvedValue({ data: mockSpotifyToken });

        await exchangeToken("auth-code-123");

        const callArgs = mockAxiosPost.mock.calls[0];
        const body = callArgs[1] as string;
        expect(body).toContain("grant_type=authorization_code");
        expect(body).toContain("code=auth-code-123");
        expect(body).toContain("redirect_uri=");
    });

    it("throws when Spotify returns an error", async () => {
        mockAxiosPost.mockRejectedValue(new Error("401 Unauthorized"));

        await expect(exchangeToken("bad-code")).rejects.toThrow("401 Unauthorized");
    });
});


