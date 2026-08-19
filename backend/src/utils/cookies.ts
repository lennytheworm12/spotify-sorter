// Shared cookie configuration so set/clear always use identical options.
import type { CookieOptions, Response } from "express";
import { env } from "../env";

export const JWT_COOKIE_NAME = "jwt";
export const OAUTH_STATE_COOKIE_NAME = "spotify_auth_state";

const JWT_MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000;
const OAUTH_STATE_MAX_AGE_MS = 10 * 60 * 1000;

const isProduction = env.NODE_ENV === "production";
const sameSite: CookieOptions["sameSite"] =
    env.COOKIE_SAME_SITE ?? (isProduction ? "none" : "lax");
const secure = env.COOKIE_SECURE ?? isProduction;

const baseCookieOptions: CookieOptions = {
    httpOnly: true,
    sameSite,
    secure,
    ...(env.COOKIE_DOMAIN ? { domain: env.COOKIE_DOMAIN } : {}),
};

export const jwtCookieOptions: CookieOptions = {
    ...baseCookieOptions,
    maxAge: JWT_MAX_AGE_MS,
};

export const oauthStateCookieOptions: CookieOptions = {
    ...baseCookieOptions,
    maxAge: OAUTH_STATE_MAX_AGE_MS,
};

// clearCookie mirrors the set options (maxAge is irrelevant when clearing).
export const clearJwtCookieOptions: CookieOptions = baseCookieOptions;
export const clearOauthStateCookieOptions: CookieOptions = baseCookieOptions;

export function setJwtCookie(res: Response, token: string): void {
    res.cookie(JWT_COOKIE_NAME, token, jwtCookieOptions);
}

export function clearJwtCookie(res: Response): void {
    res.clearCookie(JWT_COOKIE_NAME, clearJwtCookieOptions);
}

export function setOAuthStateCookie(res: Response, state: string): void {
    res.cookie(OAUTH_STATE_COOKIE_NAME, state, oauthStateCookieOptions);
}

export function clearOAuthStateCookie(res: Response): void {
    res.clearCookie(OAUTH_STATE_COOKIE_NAME, clearOauthStateCookieOptions);
}
