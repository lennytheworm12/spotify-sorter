//handles spotify servers hitting the callback 
import type { Request, Response } from "express";
import { exchangeToken } from "../services/spotify.auth.service";
import { getSpotifyUserData } from "../services/spotify.user.service";
import { mapSpotifyUserToDBUser } from "../utils/mappers";
import { upsertUser } from "../services/mongo.user.services";
import { setAccessToken } from "../services/token.service"
import jwt from "jsonwebtoken";
import { env } from "../env";

//spotify redirects after the user logs in into this api call
export const SpotifyCallback = async (req: Request, res: Response) => {
    //it needs state stored in cookies and the code 
    const { code, state, error } = req.query;
    const storedState = req.cookies['spotify_auth_state'];
    //if the user access was denied
    if (error) return res.status(404).json({ message: "user access was denied" });
    if (!state || state !== storedState) {
        return res.status(404).json({ message: "state was not matched" });
    }
    if (!code) return res.status(404).json({ message: "code was not found" });
    try {
        //we call exchange token with our code to get the token
        const responseToken = await exchangeToken(code as string);
        const responseSpotifyUser = await getSpotifyUserData(responseToken.access_token);
        const completeBaseUser = mapSpotifyUserToDBUser(responseSpotifyUser, responseToken);
        await upsertUser(completeBaseUser); //append user to our database
        await setAccessToken(responseSpotifyUser.id, responseToken.access_token);

        //set data into jwt
        const JsonToken = jwt.sign({ spotifyId: completeBaseUser.spotifyId }, env.JWT_SECRET, { expiresIn: '14d' });

        res.cookie('jwt', JsonToken, { httpOnly: true, maxAge: 14 * 24 * 60 * 60 * 1000 });

        return res.status(200).json({ message: "successfully logged in and added user" });

        //if we have all this information from callback we are able to 
    } catch (error) {
        console.error(error);
        res.status(500).json({ error: "failed to initiate callback" });
    }


}
