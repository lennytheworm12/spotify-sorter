//build methods to read and write access token in our redis db
import redis from "../utils/redis";
import { getRefreshToken, updateRefreshToken } from "../services/mongo.user.services";
import type { SpotifyToken } from "../types/spotify.types";
import {refreshAccessToken} from "../services/spotify.user.service";

//write the access token to the redis db 
export const setAccessToken = async (spotifyId: string, accessToken: string): Promise<void> => {
    await redis.set(`user:${spotifyId}:accessToken`, accessToken, 'EX', 3600)
}


//read the token from redis
export const getAccessToken = async (spotifyId: string): Promise<string | null> => {
    const token = (await redis.get(`user:${spotifyId}:accessToken`));
    if (!token) {
        return null;
    }
    return token;

}

//when the user logs out delete 
export const deleteAccessToken = async (spotifyId: string): Promise<void> => {
    await redis.del(`user:${spotifyId}:accessToken`)
}


//method called grab valid accessToken
export const getValidAccessToken = async (spotifyId: string): Promise<string> => {
    const token = await getAccessToken(spotifyId);
    if (token) return token;

    //if the access token could not be found
    const refreshToken = await getRefreshToken(spotifyId);
    if (!refreshToken) throw new Error("no refresh token found for this id");
    const responseSpotifyToken = await refreshAccessToken(refreshToken);
    
    if (responseSpotifyToken.refresh_token && responseSpotifyToken.refresh_token != refreshToken) {
        await updateRefreshToken(spotifyId, responseSpotifyToken.refresh_token);
    }
    await setAccessToken(spotifyId, responseSpotifyToken.access_token);
    return responseSpotifyToken.access_token;



}


