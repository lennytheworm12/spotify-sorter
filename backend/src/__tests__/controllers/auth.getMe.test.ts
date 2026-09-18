// auth.getMe.test.ts
//
// getMe is a protected controller — verifyUser middleware runs first and
// attaches req.user.spotifyId. The controller itself just calls getUserInfo
// and returns the result or an appropriate error.
//
// Because verifyUser is middleware we have to wire it up in the test app too,
// but we mock jwt.verify so we can control whether it passes or fails.

import express from "express";
import request from "supertest";
import cookieParser from "cookie-parser";
import { getMe } from "../../controllers/auth.getMe";
import { verifyUser } from "../../middleware/auth.middleware";

jest.mock("../../services/mongo.user.services", () => ({
  getUserInfo: jest.fn(),
}));

jest.mock("jsonwebtoken", () => ({
  __esModule: true,
  default: {
    verify: jest.fn(),
    sign: jest.fn(),
  },
}));

jest.mock("../../env", () => ({
  env: { JWT_SECRET: "test-secret" },
}));

import { getUserInfo } from "../../services/mongo.user.services";
import jwt from "jsonwebtoken";

const mockGetUserInfo = getUserInfo as jest.Mock;
const mockJwtVerify = jwt.verify as jest.Mock;

const app = express();
app.use(cookieParser());
app.get("/auth/me", verifyUser, getMe);

beforeEach(() => {
  jest.clearAllMocks();
  // Default: JWT is valid
  mockJwtVerify.mockReturnValue({ spotifyId: "spotify-user-123" });
});

describe("getMe", () => {

  // ── Middleware blocks unauthenticated requests ─────────────────────────────
  // This is verifyUser doing its job — getMe itself never runs here.
  // We test it in this file too because it's the real user-facing behavior
  // of the /me route.
  it("returns 401 when no JWT cookie is present", async () => {
    const res = await request(app).get("/auth/me");

    expect(res.status).toBe(401);
    expect(mockGetUserInfo).not.toHaveBeenCalled();
  });

  // ── User found ────────────────────────────────────────────────────────────
  it("returns 200 with PublicUser when user exists in MongoDB", async () => {
    mockGetUserInfo.mockResolvedValue({
      spotifyId: "spotify-user-123",
      displayName: "Test User",
      profilePictureUrl: "https://example.com/pic.jpg",
    });

    const res = await request(app)
      .get("/auth/me")
      .set("Cookie", "jwt=valid-token");

    expect(res.status).toBe(200);
    expect(res.body).toEqual({
      spotifyId: "spotify-user-123",
      displayName: "Test User",
      profilePictureUrl: "https://example.com/pic.jpg",
    });
  });

  // ── getUserInfo called with correct spotifyId ─────────────────────────────
  // Verifies the controller correctly pulls spotifyId off req.user
  // (which was attached by verifyUser) and passes it to getUserInfo.
  it("calls getUserInfo with the spotifyId from the JWT", async () => {
    mockGetUserInfo.mockResolvedValue({
      spotifyId: "spotify-user-123",
      displayName: "Test User",
      profilePictureUrl: null,
    });

    await request(app)
      .get("/auth/me")
      .set("Cookie", "jwt=valid-token");

    expect(mockGetUserInfo).toHaveBeenCalledWith("spotify-user-123");
  });

  // ── User not found ────────────────────────────────────────────────────────
  // JWT is valid but no matching user in MongoDB — shouldn't normally happen
  // but we guard against it (user deleted from DB while still holding a JWT).
  it("returns 404 when getUserInfo returns null", async () => {
    mockGetUserInfo.mockResolvedValue(null);

    const res = await request(app)
      .get("/auth/me")
      .set("Cookie", "jwt=valid-token");

    expect(res.status).toBe(404);
    expect(res.body.message).toBe("user not found");
  });

  // ── Database error ────────────────────────────────────────────────────────
  it("returns 500 when getUserInfo throws", async () => {
    mockGetUserInfo.mockRejectedValue(new Error("DB connection lost"));

    const res = await request(app)
      .get("/auth/me")
      .set("Cookie", "jwt=valid-token");

    expect(res.status).toBe(500);
    expect(res.body.message).toBe("database error");
  });
});
