//build methods to read and write access token in our redis db
import redis from "../utils/redis";

//write the access token to the redis db 
export const setAcessToken = async (spotifyId: string, accessToken: string): Promise<void> => {
    await redis.set(`user:${spotifyId}:accessToken`, accessToken, 'EX', 3600)
}


//read the token from redis
export const getAccessToken = async (spotifyId: string): Promise<string | null> => {
    return await redis.get(`user:${spotifyId}:accessToken`);
}

//when the user logs out delete 
export const deleteAccessToken = async (spotifyId: string): Promise<void> => {
    await redis.del(`user:${spotifyId}:accessToken`)
}
