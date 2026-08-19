/*
main file/server for the project
 */

import mongoose from "mongoose";
import { env } from "./env";
import { app } from "./app";
import "./utils/redis";

const PORT = env.PORT ?? 3000;
const mongoURI = env.MONGO_URI ?? "";

mongoose.connect(mongoURI).then(() => console.log("mongodb connected")).catch(err => console.error("mongodb connection failed: ", err));

app.listen(PORT, () => {

    console.log(`server up at http://localhost:${PORT}`);
    console.log(`env: ${env.NODE_ENV}`);
})
