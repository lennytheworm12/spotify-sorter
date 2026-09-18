//handles spotify servers hitting the callback
import type { Request, Response } from "express";
import { exchangeToken } from "../services/spotify.auth.service";
import { getSpotifyUserData } from "../services/spotify.user.service";
import { mapSpotifyUserToDBUser } from "../utils/mappers";
import { upsertUser } from "../services/mongo.user.services";
import { setAccessToken } from "../services/token.service"
import jwt from "jsonwebtoken";
import { env } from "../env";
import { OAUTH_STATE_COOKIE_NAME, clearOAuthStateCookie, setJwtCookie } from "../utils/cookies";
import { frontendRedirect } from "../utils/frontendRedirect";

//spotify redirects after the user logs in into this api call
export const SpotifyCallback = async (req: Request, res: Response) => {
    //it needs state stored in cookies and the code 
    const { code, state, error } = req.query;
    const storedState = req.cookies[OAUTH_STATE_COOKIE_NAME];
    clearOAuthStateCookie(res); // state is single-use — always clear it
    //if the user access was denied
    if (error) return res.redirect(frontendRedirect({ auth: "error", reason: "access_denied" }));
    if (!state) return res.redirect(frontendRedirect({ auth: "error", reason: "missing_state" }));
    if (state !== storedState) {
        return res.redirect(frontendRedirect({ auth: "error", reason: "state_mismatch" }));
    }
    if (!code || typeof code !== "string") return res.redirect(frontendRedirect({ auth: "error", reason: "missing_code" }));
    try {
        //we call exchange token with our code to get the token
        const responseToken = await exchangeToken(code);
        const responseSpotifyUser = await getSpotifyUserData(responseToken.access_token);
        const completeBaseUser = mapSpotifyUserToDBUser(responseSpotifyUser, responseToken);
        await upsertUser(completeBaseUser); //append user to our database
        await setAccessToken(responseSpotifyUser.id, responseToken.access_token);

        //set data into jwt
        const JsonToken = jwt.sign({ spotifyId: completeBaseUser.spotifyId }, env.JWT_SECRET, { expiresIn: '14d' });

        setJwtCookie(res, JsonToken);

        return res.redirect(frontendRedirect({ auth: "success" }));

        //if we have all this information from callback we are able to 
    } catch (error) {
        console.error(error);
        return res.redirect(frontendRedirect({ auth: "error", reason: "callback_failed" }));
    }
}
