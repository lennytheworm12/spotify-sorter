// auth.middleware.test.ts
//
// verifyUser is middleware — it sits between the route and the controller.
// Its job: read the JWT from cookies, verify it, and attach req.user.spotifyId.
//
// Testing strategy: we use Supertest to fire real HTTP requests against a tiny
// Express app that has verifyUser wired up. This lets us test the actual cookie
// parsing + jwt.verify interaction without needing a running server.
//
// We mock jwt.verify so we don't need a real JWT_SECRET in the test environment
// and can simulate expiry/tampered tokens trivially.

import express from "express";
import request from "supertest";
import cookieParser from "cookie-parser";
import { verifyUser } from "../../middleware/auth.middleware";

// ─── Mock jsonwebtoken ─────────────────────────────────────────────────────────
// jwt.verify normally checks the signature against the secret. We mock it so
// we can control exactly what it returns (or throws) per test.
jest.mock("jsonwebtoken", () => ({
    verify: jest.fn(),
    sign: jest.fn(),
}));

import jwt from "jsonwebtoken";
const mockJwtVerify = jwt.verify as jest.Mock;

// ─── Mock env ─────────────────────────────────────────────────────────────────
// auth.middleware.ts reads env.JWT_SECRET on import. We stub it out so the
// module can load without a real .env file.
jest.mock("../../env", () => ({
    env: { JWT_SECRET: "test-secret" },
}));

// ─── Build a mini Express app ─────────────────────────────────────────────────
// We create a throwaway app just for these tests. The protected route echoes
// back req.user so we can assert it was set correctly.
const app = express();
app.use(cookieParser()); // needed for req.cookies to work
app.get("/protected", verifyUser, (req, res) => {
    // If middleware called next(), we reach here and return req.user
    res.status(200).json({ user: req.user });
});

beforeEach(() => {
    jest.resetAllMocks();
});

// =============================================================================
// verifyUser
// =============================================================================
describe("verifyUser middleware", () => {

    // ── No cookies at all ─────────────────────────────────────────────────────
    // If there's no cookie header the middleware should immediately 401.
    // We never call jwt.verify because there's nothing to verify.
    it("returns 401 when no cookies are present on the request", async () => {
        const res = await request(app).get("/protected");

        expect(res.status).toBe(401);
        expect(res.body.message).toBe("request not authenticated");
        expect(mockJwtVerify).not.toHaveBeenCalled();
    });

    // ── Cookie present but JWT is invalid ─────────────────────────────────────
    // jwt.verify throws a JsonWebTokenError for a tampered/bad token.
    // Our middleware catches that and returns 401.
    it("returns 401 when the JWT is invalid or tampered", async () => {
        mockJwtVerify.mockImplementation(() => {
            throw new Error("invalid signature");
        });

        const res = await request(app)
            .get("/protected")
            .set("Cookie", "jwt=bad-token-value");

        expect(res.status).toBe(401);
        expect(res.body.message).toBe("could not verify token");
    });

    // ── Cookie present but JWT is expired ─────────────────────────────────────
    // jwt.verify throws a TokenExpiredError for an expired token.
    // Same result — 401 — but we test it explicitly because it's a common case
    // that might be handled differently in future (e.g. auto-refresh).
    it("returns 401 when the JWT is expired", async () => {
        mockJwtVerify.mockImplementation(() => {
            const err = new Error("jwt expired");
            err.name = "TokenExpiredError";
            throw err;
        });

        const res = await request(app)
            .get("/protected")
            .set("Cookie", "jwt=expired-token");

        expect(res.status).toBe(401);
        expect(res.body.message).toBe("could not verify token");
    });

    // ── Valid JWT ──────────────────────────────────────────────────────────────
    // jwt.verify returns the decoded payload. Middleware should:
    //   1. Attach { spotifyId } to req.user
    //   2. Call next() so the request continues to the controller
    it("attaches req.user.spotifyId and calls next() on a valid JWT", async () => {
        // Simulate jwt.verify successfully returning a decoded payload
        mockJwtVerify.mockReturnValue({ spotifyId: "spotify-user-abc" });

        const res = await request(app)
            .get("/protected")
            .set("Cookie", "jwt=valid-token");

        expect(res.status).toBe(200);
        // Our test route echoes req.user back — so if this is set, next() was called
        expect(res.body.user).toEqual({ spotifyId: "spotify-user-abc" });
    });

    // ── Verify jwt.verify is called with the right secret ─────────────────────
    // This is a subtle but important check: we want to make sure the middleware
    // is verifying against the JWT_SECRET from env, not a hardcoded value.
    it("verifies the JWT against the JWT_SECRET from env", async () => {
        mockJwtVerify.mockReturnValue({ spotifyId: "some-user" });

        await request(app)
            .get("/protected")
            .set("Cookie", "jwt=some-token");

        expect(mockJwtVerify).toHaveBeenCalledWith("some-token", "test-secret");
    });
});
