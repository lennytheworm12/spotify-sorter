// startup.test.ts
//
// Readiness sequencing for startServer: the HTTP server must not listen until
// BOTH MongoDB connect and Redis ping have succeeded, and a failure in either
// must reject startup without opening the port. All infrastructure is injected
// or mocked — no real Mongo/Redis sockets are created.

import { startServer } from "../../startup";

jest.mock("../../utils/redis", () => ({
    ping: jest.fn(),
    quit: jest.fn(),
}));

jest.mock("../../env", () => ({
    env: {
        NODE_ENV: "test",
        PORT: 3000,
        HOST: "0.0.0.0",
        MONGO_URI: "mongodb://localhost:27017/spotify",
        REDIS_URI: "redis://localhost:6379",
        SPOTIFY_CLIENT_ID: "test-client-id",
        SPOTIFY_CLIENT_SECRET: "test-client-secret",
        SPOTIFY_REDIRECT_URI: "http://127.0.0.1:3000/auth/spotify/callback",
        JWT_SECRET: "test-secret-with-enough-length-1234567890",
        FRONTEND_URL: "http://127.0.0.1:5173",
    },
}));

const deferred = <T,>() => {
    let resolve!: (value: T) => void;
    let reject!: (reason?: unknown) => void;
    const promise = new Promise<T>((res, rej) => {
        resolve = res;
        reject = rej;
    });
    return { promise, resolve, reject };
};

const flush = () => new Promise<void>(resolve => setImmediate(resolve));

describe("startServer", () => {
    it("does not listen until MongoDB connect AND Redis ping both succeed", async () => {
        const mongo = deferred<void>();
        const redis = deferred<void>();
        const listen = jest.fn();
        const log = jest.fn();

        const started = startServer({
            mongoConnect: () => mongo.promise,
            redisPing: () => redis.promise,
            listen: listen as never,
            log,
        });

        // Nothing resolved yet — the port must stay closed.
        await flush();
        expect(listen).not.toHaveBeenCalled();

        // Redis alone is not enough.
        redis.resolve();
        await flush();
        expect(listen).not.toHaveBeenCalled();

        // Both ready — only now does the server listen.
        mongo.resolve();
        await started;
        expect(listen).toHaveBeenCalledTimes(1);
        expect(listen).toHaveBeenCalledWith(3000, "0.0.0.0", expect.any(Function));
    });

    it("listens on the configured HOST from env", async () => {
        const mockedEnv = jest.requireMock("../../env").env as { HOST: string };
        const originalHost = mockedEnv.HOST;
        mockedEnv.HOST = "127.0.0.1";
        try {
            const listen = jest.fn();
            const log = jest.fn();

            await startServer({
                mongoConnect: () => Promise.resolve(),
                redisPing: () => Promise.resolve("PONG"),
                listen: listen as never,
                log,
            });

            expect(listen).toHaveBeenCalledWith(3000, "127.0.0.1", expect.any(Function));
        } finally {
            mockedEnv.HOST = originalHost;
        }
    });

    it("rejects without listening when MongoDB connect fails", async () => {
        const listen = jest.fn();

        await expect(
            startServer({
                mongoConnect: () => Promise.reject(new Error("mongo down")),
                redisPing: () => Promise.resolve("PONG"),
                listen: listen as never,
            })
        ).rejects.toThrow("mongo down");

        expect(listen).not.toHaveBeenCalled();
    });

    it("rejects without listening when Redis ping fails", async () => {
        const listen = jest.fn();

        await expect(
            startServer({
                mongoConnect: () => Promise.resolve(),
                redisPing: () => Promise.reject(new Error("redis down")),
                listen: listen as never,
            })
        ).rejects.toThrow("redis down");

        expect(listen).not.toHaveBeenCalled();
    });

    it("logs the bind address and browser API URL only inside the listen callback", async () => {
        const listen = jest.fn();
        const log = jest.fn();

        await startServer({
            mongoConnect: () => Promise.resolve(),
            redisPing: () => Promise.resolve("PONG"),
            listen: listen as never,
            log,
        });

        expect(log).not.toHaveBeenCalled();

        const callback = listen.mock.calls[0]?.[2] as (() => void) | undefined;
        callback?.();
        expect(log).toHaveBeenCalledWith("server listening on 0.0.0.0:3000");
        expect(log).toHaveBeenCalledWith("browser API URL: http://127.0.0.1:3000");
        expect(log).toHaveBeenCalledWith("env: test");
    });
});
