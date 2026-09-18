// mappers.test.ts
//
// mapSpotifyUserToDBUser is a pure function — no I/O, no side effects.
// It just transforms data from one shape to another.
//
// Pure functions are the easiest things to test: give it inputs, assert outputs.
// No mocking needed at all here. This is what testing nirvana looks like.
//
// The tricky parts to cover:
//   1. profilePictureUrl: uses optional chaining + nullish coalescing
//   2. refreshToken: uses conditional spread — must be ABSENT (not undefined)
//      from the returned object when token.refresh_token isn't present.
//      This is critical because exactOptionalPropertyTypes is on.

import { mapSpotifyUserToDBUser } from "../../utils/mappers";
import type { SpotifyUser, SpotifyToken } from "../../types/spotify.types";

// ─── Test data ────────────────────────────────────────────────────────────────
const baseSpotifyUser: SpotifyUser = {
  id: "spotify-123",
  display_name: "Test User",
  images: [{ url: "https://example.com/pic.jpg", height: 100, width: 100 }],
  uri: "spotify:user:123",
  href: "https://api.spotify.com/v1/users/123",
  external_urls: { spotify: "https://open.spotify.com/user/123" },
  type: "user",
};

const tokenWithRefresh: SpotifyToken = {
  access_token: "access-abc",
  token_type: "Bearer",
  scope: "playlist-read-private",
  expires_in: 3600,
  refresh_token: "refresh-xyz",
};

const tokenWithoutRefresh: SpotifyToken = {
  access_token: "access-abc",
  token_type: "Bearer",
  scope: "playlist-read-private",
  expires_in: 3600,
  // No refresh_token — Spotify omits it on repeat logins
};

// =============================================================================
// mapSpotifyUserToDBUser
// =============================================================================
describe("mapSpotifyUserToDBUser", () => {

  // ── Core field mapping ────────────────────────────────────────────────────
  it("maps spotifyId from user.id", () => {
    const result = mapSpotifyUserToDBUser(baseSpotifyUser, tokenWithRefresh);
    expect(result.spotifyId).toBe("spotify-123");
  });

  it("maps displayName from user.display_name", () => {
    const result = mapSpotifyUserToDBUser(baseSpotifyUser, tokenWithRefresh);
    expect(result.displayName).toBe("Test User");
  });

  it("maps profilePictureUrl from the first image's url", () => {
    const result = mapSpotifyUserToDBUser(baseSpotifyUser, tokenWithRefresh);
    expect(result.profilePictureUrl).toBe("https://example.com/pic.jpg");
  });

  // ── profilePictureUrl edge cases ──────────────────────────────────────────
  // The mapper uses `user.images[0]?.url ?? null`
  // If Spotify returns no images (common for accounts without a photo set),
  // this should be null, not undefined or throwing.
  it("sets profilePictureUrl to null when images array is empty", () => {
    const userWithNoImages = { ...baseSpotifyUser, images: [] };
    const result = mapSpotifyUserToDBUser(userWithNoImages, tokenWithRefresh);
    expect(result.profilePictureUrl).toBeNull();
  });

  // ── refreshToken present ──────────────────────────────────────────────────
  it("includes refreshToken when token.refresh_token is present", () => {
    const result = mapSpotifyUserToDBUser(baseSpotifyUser, tokenWithRefresh);
    expect(result.refreshToken).toBe("refresh-xyz");
  });

  // ── refreshToken absent ───────────────────────────────────────────────────
  // This is the most important test in this file.
  //
  // When Spotify doesn't return a refresh token, the mapper uses a conditional
  // spread: `...(token.refresh_token && { refreshToken: token.refresh_token })`
  //
  // The result: the `refreshToken` key should be COMPLETELY ABSENT from the
  // returned object — not present as `undefined`.
  //
  // Why does this matter? In upsertUser we check `if (user.refreshToken)`.
  // If refreshToken is `undefined`, that condition is falsy and we don't update it.
  // But with exactOptionalPropertyTypes on, TypeScript enforces that optional
  // properties must either be their declared type OR absent — never explicitly undefined.
  //
  // `'refreshToken' in result` catches both:
  //   - `{ refreshToken: undefined }` → FAILS (key is present)
  //   - `{}` → PASSES (key is absent)
  it("omits refreshToken entirely (not undefined) when token has no refresh_token", () => {
    const result = mapSpotifyUserToDBUser(baseSpotifyUser, tokenWithoutRefresh);

    // .toBeUndefined() would pass even if the key exists as undefined.
    // 'in' checks whether the key is present in the object at all.
    expect("refreshToken" in result).toBe(false);
  });

  // ── displayName can be null ───────────────────────────────────────────────
  // SpotifyUser has `display_name: string | null`. Our BaseUser has
  // `displayName: string | null`. Make sure null passes through cleanly.
  it("preserves null displayName when Spotify returns no display name", () => {
    const userWithNullName = { ...baseSpotifyUser, display_name: null };
    const result = mapSpotifyUserToDBUser(userWithNullName, tokenWithRefresh);
    expect(result.displayName).toBeNull();
  });
});
