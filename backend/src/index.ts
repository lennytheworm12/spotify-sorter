// Server entrypoint: start only after Mongo + Redis are ready, then shut down
// cleanly on SIGINT/SIGTERM. The app itself lives in app.ts/startup.ts so it
// stays importable (and testable) without opening infrastructure.
import mongoose from "mongoose";
import type { Server } from "node:http";
import { startServer } from "./startup";
import redis from "./utils/redis";

let shuttingDown = false;

// Close HTTP, Mongo, and Redis exactly once per process. The flag plus
// process.once() guards against double-close races when both signals arrive.
const shutdown = async (server: Server, signal: NodeJS.Signals): Promise<void> => {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log(`received ${signal}, shutting down`);

    // Drop idle/keep-alive connections so close() does not hang on them.
    server.closeIdleConnections?.();
    server.closeAllConnections?.();
    const closeServer = server.listening
        ? new Promise<void>(resolve => server.close(() => resolve()))
        : Promise.resolve();
    const closeMongo = mongoose.disconnect().catch(() => undefined);
    const closeRedis = redis.quit().catch(() => undefined);

    await Promise.all([closeServer, closeMongo, closeRedis]);
};

const main = async (): Promise<void> => {
    const server = await startServer();

    const onSignal = (signal: NodeJS.Signals) => {
        shutdown(server, signal)
            .catch(err => {
                console.error("shutdown failed", err);
                process.exitCode = 1;
            })
            .finally(() => process.exit());
    };

    process.once("SIGINT", onSignal);
    process.once("SIGTERM", onSignal);
};

main().catch(err => {
    console.error("server failed to start:", err instanceof Error ? err.message : String(err));
    process.exit(1);
});
