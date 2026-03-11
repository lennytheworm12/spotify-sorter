//we want to modularize making the request for the token here

import { env } from "../env";
import axios from "axios";
import type { SpotifyToken } from "../types/spotify.types";

export const exchangeToken = async (code: string): Promise<SpotifyToken> => {
    try {

        const credentials = `${env.SPOTIFY_CLIENT_ID}:${env.SPOTIFY_CLIENT_SECRET}`;
        const encoded = Buffer.from(credentials).toString('base64');

        const paramBody = new URLSearchParams({
            grant_type: 'authorization_code',
            code: code as string,
            redirect_uri: env.SPOTIFY_REDIRECT_URI,
        });
        const url = 'https://accounts.spotify.com/api/token';
        //given this information request with axios and returns a spotify token
        const response = await axios.post<SpotifyToken>(
            url,
            paramBody.toString(),
            {
                headers: {
                    Authorization: `Basic ${encoded}`,
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
            }
        )
        return response.data;
    } catch (error) {
        throw error;
    }
}
