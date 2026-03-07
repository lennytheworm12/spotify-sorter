/*
main file/server for the project 
 */

import express, { type Request, type Response } from 'express';
import helmet from 'helmet';
import cors from 'cors';
import { env } from './env';
import compression from "compression";

const app = express();
const PORT = env.PORT;


//middleware
app.use(helmet()); //security header
app.use(cors()); //enables cross origin requests
app.use(compression());
app.use(express.json({ limit: "1mb" })); //parses json bodies

//attach middleware to routes that need sessions later

app.get('/', (req: Request, res: Response) => {

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
