// auth.logoutUser.test.ts
//
// logoutUser has two responsibilities:
//   1. Clear the JWT cookie
//   2. Delete the access token from Redis via deleteAccessToken
//
// The interesting case is the graceful fallback — if Redis throws,
// the controller still returns 200. Logout should never fail from
// the user's perspective even if Redis is down.

import express from "express";
import request from "supertest";
import cookieParser from "cookie-parser";
import { logoutUser } from "../../controllers/auth.logoutUser";
import { verifyUser } from "../../middleware/auth.middleware";

jest.mock("../../services/token.service", () => ({
  deleteAccessToken: jest.fn(),
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

import { deleteAccessToken } from "../../services/token.service";
import jwt from "jsonwebtoken";

const mockDeleteAccessToken = deleteAccessToken as jest.Mock;
const mockJwtVerify = jwt.verify as jest.Mock;

const app = express();
app.use(cookieParser());
app.post("/auth/logout", verifyUser, logoutUser);

beforeEach(() => {
  jest.clearAllMocks();
  mockJwtVerify.mockReturnValue({ spotifyId: "spotify-user-123" });
  mockDeleteAccessToken.mockResolvedValue(undefined);
});

describe("logoutUser", () => {

  // ── Middleware blocks unauthenticated requests ─────────────────────────────
  it("returns 401 when no JWT cookie is present", async () => {
    const res = await request(app).post("/auth/logout");

    expect(res.status).toBe(401);
    expect(mockDeleteAccessToken).not.toHaveBeenCalled();
  });

  // ── Successful logout ──────────────────────────────────────────────────────
  it("returns 200 on successful logout", async () => {
    const res = await request(app)
      .post("/auth/logout")
      .set("Cookie", "jwt=valid-token");

    expect(res.status).toBe(200);
    expect(res.body.message).toBe("logged out");
  });

  // ── JWT cookie is cleared ──────────────────────────────────────────────────
  // After logout the JWT cookie should be cleared so the user can't keep
  // using it. We check the set-cookie header for the cleared cookie.
  it("clears the JWT cookie on logout", async () => {
    const res = await request(app)
      .post("/auth/logout")
      .set("Cookie", "jwt=valid-token");

    const cookies = res.headers["set-cookie"] as string[] | string;
    const cookieString = Array.isArray(cookies) ? cookies.join(";") : cookies;

    // A cleared cookie is set with Max-Age=0 or Expires in the past
    expect(cookieString).toContain("jwt=");
    expect(cookieString).toMatch(/Max-Age=0|Expires=.*1970/);
  });

  // ── deleteAccessToken called with correct spotifyId ────────────────────────
  it("calls deleteAccessToken with the spotifyId from the JWT", async () => {
    await request(app)
      .post("/auth/logout")
      .set("Cookie", "jwt=valid-token");

    expect(mockDeleteAccessToken).toHaveBeenCalledWith("spotify-user-123");
  });

  // ── Redis throws → still 200 ───────────────────────────────────────────────
  // This is the most important behavioral test in this file.
  // If Redis is down or the key doesn't exist, logout should still succeed
  // from the user's perspective. The JWT cookie is already cleared by this point.
  it("returns 200 even when deleteAccessToken throws", async () => {
    mockDeleteAccessToken.mockRejectedValue(new Error("Redis connection lost"));

    const res = await request(app)
      .post("/auth/logout")
      .set("Cookie", "jwt=valid-token");

    expect(res.status).toBe(200);
    expect(res.body.message).toBe("logged out");
  });
});
