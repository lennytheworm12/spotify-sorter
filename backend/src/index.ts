/*
main file/server for the project 
 */

import express, { type Request, type Response } from 'express';
import helmet from 'helmet';
import cors from 'cors';
import { env } from './env';
import compression from "compression";
import mongoose from "mongoose";
import morgan from "morgan";
import authRouter from "./routes/auth.routes";
import playlistRouter from "./routes/playlist.routes";
import libraryRouter from "./routes/library.routes";
import "./utils/redis"

const app = express();
const PORT = env.PORT ?? 3000;
const mongoURI = env.MONGO_URI ?? "";

mongoose.connect(mongoURI).then(() => console.log("mongodb connected")).catch(err => console.error("mongodb connection failed: ", err));

//middleware
app.use(helmet()); //security header
app.use(cors()); //enables cross origin requests
app.use(compression());
app.use(morgan('dev'));
app.use(express.json({ limit: "1mb" })); //parses json bodies
app.use('/auth', authRouter);
app.use('/playlists', playlistRouter);
app.use('/library', libraryRouter);

//attach middleware to routes that need sessions later

app.get('/', (_req: Request, res: Response) => {

    res.send({
        status: 'online',
        message: 'spotify proj is running on linux',
    });
});
//testing 
//
app.listen(PORT, () => {

    console.log(`server up at https://localhost:${PORT}`);
    console.log(`env: ${env.NODE_ENV}`);
})
