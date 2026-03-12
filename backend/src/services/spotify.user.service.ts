//fetching user information given a access token
import axios from "axios";
import type { SpotifyUser, SpotifyToken } from "../types/spotify.types";
import { env } from "../env";


export const getSpotifyUserData = async (accessToken: string): Promise<SpotifyUser> => {
    //try to access /me endpoint
    //if this err's from spotify throw up for controller to handle
    const response = await axios.get<SpotifyUser>(
        'https://api.spotify.com/v1/me',
        {
            headers: {
                Authorization: `Bearer ${accessToken}`
            }
        }

    )
    return response.data;


}


export const refreshAccessToken = async (refreshToken: string):Promise<SpotifyToken>  => {
    //method to given refresh token from our db to grab a new access token
    const url = 'https://accounts.spotify.com/api/token';
    const crendentials = `${env.SPOTIFY_CLIENT_ID}:${env.SPOTIFY_CLIENT_SECRET}`;
    const encoded = Buffer.from(crendentials).toString('base64');
    const paramBody = new URLSearchParams({
        grant_type: 'refresh_token',
        refresh_token: refreshToken,
    })

    const response = await axios.post<SpotifyToken>(
        url,
        paramBody.toString(),
        {
            headers: {
                Authorization: `Basic ${encoded}`,
                'Content-Type': "application/x-www-form-urlencoded"
            }
        }
    )
    return response.data;

}


