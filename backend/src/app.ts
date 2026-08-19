// Express app assembly. Kept separate from index.ts so integration tests can
// mount the full route stack without opening a port or connecting to Mongo.
import express, { type Request, type Response } from "express";
import helmet from "helmet";
import cors from "cors";
import cookieParser from "cookie-parser";
import compression from "compression";
import morgan from "morgan";
import { env } from "./env";
import authRouter from "./routes/auth.routes";
import playlistRouter from "./routes/playlist.routes";
import libraryRouter from "./routes/library.routes";
import sortRouter from "./routes/sort.routes";

export const app = express();

// security header
app.use(helmet());
app.use(cors({ origin: env.FRONTEND_URL, credentials: true }));
app.use(cookieParser());
app.use(compression());
if (env.NODE_ENV !== "test") {
    app.use(morgan("dev"));
}
app.use(express.json({ limit: "1mb" })); // parses json bodies
app.use("/auth", authRouter);
app.use("/playlists", playlistRouter);
app.use("/library", libraryRouter);
app.use("/sort", sortRouter);

app.get("/", (_req: Request, res: Response) => {
    res.send({
        status: "online",
        message: "spotify proj is running on linux",
    });
});

export default app;
