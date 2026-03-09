//controller to log the user in from spotify
//this can stay as a controller since its essentially a pure https request
import type { Request, Response } from "express";
import crypto from "crypto";
import { env } from "../env";

export const SpotifyUserLogin = async (_req: Request, res: Response) => {
    //login a user by redirecting them to spotify login but with extra requests
    //in the header
    try {
        const state = crypto.randomUUID();//get a random state for the req

        //define the scope of our request
        let scope= [
            "playlist-read-private",
            "playlist-read-collaborative",
            "playlist-modify-private",
            "playlist-modify-public",
            "user-library-read",
            "ugc-image-upload",
            "user-read-email", "user-read-private"
        ]
        const scopeString = scope.join(' ');
        const params = new URLSearchParams({
            response_type: "code",
            client_id: env.SPOTIFY_CLIENT_ID,
            scope :scopeString,
            redirect_uri: env.SPOTIFY_REDIRECT_URI,
            state,
            

        })
        res.cookie('spotify_auth_state', state, { httpOnly: true, maxAge: 10 * 60 * 1000 })
        //we store the state in the cookies to expire in 10 minutes
        res.redirect(`https://accounts.spotify.com/authorize?${params.toString()}`);

    } catch (error) {
        console.error(error);
        res.status(500).json({error: "failed to initiate login"});
    }
}
