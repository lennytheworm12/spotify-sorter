// Readiness-gated server startup.
//
// The HTTP server must not advertise "online" before MongoDB is connected and
// Redis answers a ping. Dependencies are injectable so the sequencing can be
// tested without opening any real sockets. app.ts stays importable without
// infrastructure, so tests never enter this module.
import type { Server } from "node:http";
import mongoose from "mongoose";
import { app } from "./app";
import { env } from "./env";
import redis from "./utils/redis";

// The bind host is intentionally separate from the browser-facing URL.
// Spotify's redirect rules reject `localhost` for local OAuth, so the
// browser-facing URLs (SPOTIFY_REDIRECT_URI, FRONTEND_URL) stay on the
// 127.0.0.1 loopback. The listener itself binds env.HOST (default 0.0.0.0) so
// traffic forwarded to the WSL private IP (e.g. via Windows `netsh portproxy`)
// is accepted instead of being rejected as non-loopback.

export interface StartupOptions {
    mongoConnect?: () => Promise<unknown>;
    redisPing?: () => Promise<unknown>;
    listen?: (port: number, host: string, callback: () => void) => Server;
    log?: (message: string) => void;
}

export const startServer = async (options: StartupOptions = {}): Promise<Server> => {
    const {
        mongoConnect = () => mongoose.connect(env.MONGO_URI),
        redisPing = () => redis.ping(),
        listen = (port, host, callback) => app.listen(port, host, callback),
        log = console.log,
    } = options;

    // Wait for both dependencies before exposing the port: a request must
    // never reach handlers before the stores behind them are ready.
    await Promise.all([mongoConnect(), redisPing()]);

    const port = env.PORT ?? 3000;
    const server = listen(port, env.HOST, () => {
        log(`server listening on ${env.HOST}:${port}`);
        log(`browser API URL: http://127.0.0.1:${port}`);
        log(`env: ${env.NODE_ENV}`);
    });
    return server;
};
